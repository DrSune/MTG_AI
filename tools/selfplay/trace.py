"""Readable game traces: what the network saw, what it considered, what it chose.

    .venv/bin/python -m tools.selfplay.trace --net runs/selfplay/NAME/v6.pt --opp heuristic \
        --seed 900007 --deck-mode coherent --out /tmp/trace.txt

Every real decision (more than one option) of a network seat is logged with the engine's own
prompt and option labels, the network's probabilities over its top options and its value
estimate (its predicted outcome in [-1, 1] for the deciding seat); the heuristic's decisions are
logged with the option it picked. A board summary opens every turn. --opp can be "heuristic" or
another checkpoint (self-play). --mask-names plays the network with every card name hidden
(the unknown-card embedding), so it can only read the card components and live state.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

import torch

from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND
from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import play_game


class Tracer:
    def __init__(self, out: Any) -> None:
        self.out = out
        self.turn_seen: tuple | None = None  # (turn, active player) of the last board

    def board(self, obs: Any) -> None:
        ex = obs.executor
        world = ex.world
        if (world.turn, world.active_player) == self.turn_seen:
            return
        self.turn_seen = (world.turn, world.active_player)
        if world.active_player is None:  # the mulligans, before the first turn (CR 103.5)
            self.out.write("\n=== opening hands ===\n")
        else:
            active = world.players[world.active_player].seat
            self.out.write(f"\n=== turn {world.turn} (seat {active} active) ===\n")
        for p in world.player_order:
            pl = world.players[p]
            bf = []
            for h in pl.zone(ZONE_BATTLEFIELD).entries:
                card = world.cards[h]
                pw, tg = ex.ledger.effective_pt(card.identity, h, card.counters)
                pt = f" {pw}/{tg}" if pw is not None else ""
                bf.append(f"{card.identity.name}{pt}{' (T)' if card.tapped else ''}")
            hand = [world.cards[h].identity.name for h in pl.zone(ZONE_HAND).entries]
            self.out.write(f"  seat {pl.seat}: life {pl.life}, hand {len(hand)}, "
                           f"graveyard {len(pl.zone(ZONE_GRAVEYARD).entries)}\n"
                           f"    battlefield: {', '.join(bf) or '-'}\n"
                           f"    hand: {', '.join(hand) or '-'}\n")


class TracedNet:
    def __init__(self, slot: M.LocalSlot, table: FT.CardTable, tracer: Tracer, name: str,
                 mask_names: bool = False) -> None:
        self.slot = slot
        self.table = table
        self.tracer = tracer
        self.name = name
        self.mask = mask_names
        self.fallback = HeuristicAgent()

    def decide(self, ask: Any, obs: Any) -> int:
        n = len(ask.options)
        if n == 1:
            return 0
        self.tracer.board(obs)
        if n > FT.MAX_OPTIONS or ask.kind == "name":
            idx = self.fallback.decide(ask, obs)
            self.tracer.out.write(f"  [{self.name} seat {ask.seat}] {ask.prompt}\n"
                                  f"      fallback -> {ask.options[idx].label}\n")
            return idx
        feats = FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx)
        if self.mask:
            feats = dict(feats)
            ci = feats["cards_i"].copy()
            ci[:, 0] = FT.UNK
            feats["cards_i"] = ci
        a, value, probs = self.slot.infer((0, ask.seat, self.name, True, False, feats, 2))
        ranked = sorted(range(n), key=lambda i: -probs[i])[:4]
        alts = "; ".join(f"{probs[i]:.2f} {ask.options[i].label}" for i in ranked)
        self.tracer.out.write(f"  [{self.name} seat {ask.seat}] {ask.prompt}\n"
                              f"      value {value:+.2f} | {alts}\n"
                              f"      -> {ask.options[int(a)].label}\n")
        return int(a)


class TracedHeuristic:
    def __init__(self, tracer: Tracer) -> None:
        self.inner = HeuristicAgent()
        self.tracer = tracer
        self.name = "heuristic"

    def decide(self, ask: Any, obs: Any) -> int:
        idx = self.inner.decide(ask, obs)
        if len(ask.options) > 1:
            self.tracer.board(obs)
            self.tracer.out.write(f"  [heuristic seat {ask.seat}] {ask.prompt}\n"
                                  f"      -> {ask.options[idx].label}\n")
        return idx


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--net", required=True)
    ap.add_argument("--opp", default="heuristic", help="'heuristic' or a checkpoint path")
    ap.add_argument("--seed", type=int, default=900007)
    ap.add_argument("--deck-mode", default="coherent")
    ap.add_argument("--pool", default="verified", choices=("verified", "compiled", "castable"),
                    help="the cards the decks are dealt from (the learner's --pool)")
    ap.add_argument("--set", default="M21", help="the set the decks are dealt from")
    ap.add_argument("--net-seat", type=int, default=0)
    ap.add_argument("--mask-names", action="store_true")
    ap.add_argument("--out", default="-")
    a = ap.parse_args(argv)
    out = sys.stdout if a.out == "-" else open(a.out, "w")  # noqa: SIM115
    net, table, _ = M.load(a.net, "cuda")
    nets = {"net": net.to(torch.bfloat16).eval()}
    if a.opp != "heuristic":
        opp, _, _ = M.load(a.opp, "cuda")
        nets["opp"] = opp.to(torch.bfloat16).eval()
    slot = M.LocalSlot(nets)
    tracer = Tracer(out)
    agents: list[Any] = [None, None]
    agents[a.net_seat] = TracedNet(slot, table, tracer, "net", a.mask_names)
    agents[1 - a.net_seat] = (TracedHeuristic(tracer) if a.opp == "heuristic"
                              else TracedNet(slot, table, tracer, "opp"))
    res = play_game(a.seed, agents, deck_mode=a.deck_mode, pool_mode=a.pool, set_code=a.set)
    out.write(f"\nRESULT: {res['outcome']} winner seat {res['winner']} after {res['turns']} turns "
              f"({res['reason']}); lives {res['lives']}; crash {res['crash']}\n")
    if out is not sys.stdout:
        out.close()
    print(f"seed {a.seed}: {res['outcome']} winner {res['winner']} turns {res['turns']} "
          f"lives {res['lives']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
