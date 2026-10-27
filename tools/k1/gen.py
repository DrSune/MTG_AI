"""Kill test K1, data: (card, state before, state change) from engine-played games.

    .venv/bin/python tools/k1/gen.py --set M21 --pool castable --games 3000 --out FILE.jsonl
    MTG_REPO=/path/to/worktree .venv/bin/python tools/k1/gen.py ...    # play another tree

K1 (docs/REVIEW_ARCHITECTURE_2026-10-27.md §4) asks whether a learned encoder over the compiled
atoms predicts what a card DOES on cards and atom combinations it never trained on. The labels come
from the engine itself: every cast and every non-mana activation a RandomPolicy makes is recorded
with a 24-number summary of the board just before it and the change just after it resolved
(triggers included), both from the acting seat's side ("me") and the other side ("opp").

The recorder subclasses RandomPolicy and wraps only its own play_cast / play_activation, so the
engine is not patched (B-35) and every game is the same seeded game play_game would play.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path
from typing import Any

REPO = Path(os.environ.get("MTG_REPO", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(REPO))

from MTG_bot.core.executor.games import (
    TURN_CAP,
    RandomPolicy,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_HAND,
    ZONE_LIBRARY,
)

FEATURES = (
    "life", "hand", "library", "graveyard", "exile", "creatures", "power", "toughness",
    "tokens", "counters", "tapped", "lands",
)
SIDES = ("me", "opp")
COLUMNS = tuple(f"{side}.{f}" for side in SIDES for f in FEATURES)


def board(game: Any, me: Any) -> list[int]:
    """The 24-number summary of the board, from seat ``me``'s side."""
    executor = game.executor
    world = executor.world
    order = list(world.player_order)
    rows: list[int] = []
    for seat in (me, next(s for s in order if s != me)):
        player = world.players[seat]
        creatures = power = toughness = tokens = counters = tapped = lands = 0
        for other in order:
            for handle in world.players[other].zone(ZONE_BATTLEFIELD).entries:
                if executor.controller_of(handle) != seat:
                    continue
                card = world.cards[handle]
                ident = card.identity
                tapped += bool(card.tapped)
                tokens += bool(ident.is_token)
                counters += sum(int(n) for n in card.counters.values())
                lands += "Land" in ident.type_line
                if "Creature" in ident.type_line:
                    creatures += 1
                    try:
                        p, t = executor.ledger.effective_pt(ident, handle, card.counters)
                    except Exception:  # noqa: BLE001 - '*' P/T outside the ledger's reach
                        p, t = 0, 0
                    power += int(p or 0)
                    toughness += int(t or 0)
        rows += [
            int(player.life),
            len(player.zone(ZONE_HAND).entries),
            len(player.zone(ZONE_LIBRARY).entries),
            len(player.zone("graveyard").entries),
            len(player.zone("exile").entries),
            creatures, power, toughness, tokens, counters, tapped, lands,
        ]
    return rows


class RecordingPolicy(RandomPolicy):
    def __init__(self, seed: int, sink: list[dict[str, Any]]) -> None:
        super().__init__(seed)
        self.sink = sink

    def _record(self, game: Any, seat: Any, before: list[int], acts: int, **row: Any) -> None:
        if game.acts == acts:  # the act was declined (multi-slot or infeasible): nothing ran
            return
        after = board(game, seat)
        self.sink.append({**row, "turn": self.turn, "pre": before,
                          "delta": [a - b for a, b in zip(after, before)]})

    def play_cast(self, game: Any, seat: Any, row: Any) -> None:
        before, acts = board(game, seat), game.acts
        oid = game.world.cards[row.handle].identity.oracle_id
        super().play_cast(game, seat, row)
        self._record(game, seat, before, acts, oid=oid, unit="card", kicked=bool(row.kicked))

    def play_activation(self, game: Any, seat: Any, option: Any) -> None:
        if option in self.mana_activations([option]):
            super().play_activation(game, seat, option)  # tapping for mana: not an effect to learn
            return
        before, acts = board(game, seat), game.acts
        oid = game.world.cards[option.source].identity.oracle_id
        super().play_activation(game, seat, option)
        self._record(game, seat, before, acts, oid=oid, unit=f"ability:{option.ability_idx}",
                     kicked=False)


def play(args: tuple[str, str, int, str]) -> list[dict[str, Any]]:
    set_code, pool, seed, deck_mode = args
    supply = get_supply(pool, set_code)
    sink: list[dict[str, Any]] = []
    # deck_mode exists only from the sets/onboarding merge on; the default call works on any tree
    decks = (deal_decks(seed, 1409, supply) if deck_mode == "stress"
             else deal_decks(seed, 1409, supply, deck_mode))
    game = _setup_game(seed, supply, decks)
    try:
        _play(game, RecordingPolicy(seed, sink), game.world.player_order, TURN_CAP)
    except Exception:  # noqa: BLE001, S110 - a crashed game keeps the rows it settled before it
        pass
    return [{"set": set_code, "seed": seed, **row} for row in sink]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--set", default="M21")
    ap.add_argument("--pool", default="castable")
    ap.add_argument("--deck-mode", default="stress")
    ap.add_argument("--games", type=int, default=1000)
    ap.add_argument("--first-seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    jobs = [(args.set, args.pool, s, args.deck_mode)
            for s in range(args.first_seed, args.first_seed + args.games)]
    rows = 0
    with Pool(args.workers) as pool, open(args.out, "w", encoding="utf-8") as out:
        out.write(json.dumps({"kind": "manifest", "columns": COLUMNS, "set": args.set,
                              "pool": args.pool, "deck_mode": args.deck_mode,
                              "games": args.games, "first_seed": args.first_seed,
                              "repo": str(REPO)}) + "\n")
        for batch in pool.imap_unordered(play, jobs, chunksize=4):
            for row in batch:
                out.write(json.dumps(row) + "\n")
                rows += 1
    print(f"{args.set}: {args.games} games -> {rows} rows -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
