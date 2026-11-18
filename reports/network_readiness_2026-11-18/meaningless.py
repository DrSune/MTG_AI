"""Which decisions are decisions of nothing? A detector, run on recorded self-play games
(docs/PLAN_NETWORK_READINESS.md §2; CPU only).

Games: a network on both seats, sampling as training does (coherent decks, M21 with M20 at the
mix share, the verified pool). At every decision with two or more options of either seat, each
option (all of them up to --max-opts, else a sample that keeps every encoding-duplicate pair) is
played once from a copy of the game:
- a copy is taken at the last pause point (an ``act`` or ``priority`` ask: no engine call in
  flight, the planning solver's mechanism, tools/puzzles/solver.py), and the answers both seats gave
  since are replayed, then the option under test;
- then the null continuation: both seats pass at every priority point, and every other ask takes
  its canonically smallest option (handles read as the objects they name), until the first
  priority point with an empty stack (or a guard: 400 continuation decisions, or two turns on);
- there the game's canonical signature is taken: every zone's cards by oracle id (libraries and
  graveyards in order, hands and exile as multisets), each permanent's live state (controller,
  tapped, counters, damage, P/T, keywords, host, entered this turn, phased out, chosen values),
  the stack, combat, life, mana pools, the step, priority, the turn's counts, the live layer,
  replacement and return rows. No engine handle enters it: two copies of a card are one card.

Options with equal signatures are one state class. Per decision: options, state classes, and the
classes of what the network can tell apart (``search.option_classes`` over its own encoding).
- one state class: a decision of nothing;
- fewer state classes than options: redundant options (one move offered several times);
- two options in one encoding class with different signatures: the network cannot tell apart
  options that differ (an observation gap).

The signature is a function of the state, so different signatures are different states. Equal
signatures may still differ in what it leaves out (the journal's history beyond the turn's counts,
timestamps): the meaningless counts are an upper bound, examined by hand per kind.

Also recorded per decision: the value head's reading (EV by turn), and cheap indicators of the
observation gaps of docs/BACKLOG.md "What the network sees" and of the knowledge memory would add.

    CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=1 nice -n 19 .venv/bin/python \
        reports/network_readiness_2026-11-18/meaningless.py --ckpt runs/r29_ab/b100.pt \
        --games 60 --seed0 77000000 --out reports/network_readiness_2026-11-18/out_a.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
import torch  # noqa: E402

from MTG_bot.bench.router import SeatRouter  # noqa: E402
from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions  # noqa: E402
from MTG_bot.core.executor import permits as PM  # noqa: E402
from MTG_bot.core.executor.events import KIND_ZONE_CHANGE  # noqa: E402
from MTG_bot.core.executor.games import TURN_CAP, _play, get_supply  # noqa: E402
from MTG_bot.core.identity import Handle  # noqa: E402
from MTG_bot.core.state import (  # noqa: E402
    ZONE_BATTLEFIELD,
    ZONE_COMMAND,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
)
from tools.search.fork import fork  # noqa: E402
from tools.selfplay import features as FT  # noqa: E402
from tools.selfplay import model as M  # noqa: E402
from tools.selfplay.rig import play_game  # noqa: E402
from tools.selfplay.search import fork_live  # noqa: E402

CLEAN = ("act", "priority")
PUBLIC = (ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_EXILE, ZONE_COMMAND, "stack")
_H = re.compile(r"\b(card|player|ability|emblem):(\d+)\b")
_SEQ = re.compile(r"\bseq=\d+|\bclock=\d+")
CONT_MAX = 400


class Stop(Exception):
    pass


# ----------------------------------------------------------------------- canonical signature


def _desc(game: Any, h: Handle) -> str:
    """What an object is, without its handle: a card by oracle id, zone and controller; a player
    by seat; an ability on the stack by its source; an emblem by its oracle id."""
    world, ex = game.world, game.executor
    order = world.player_order
    if h.namespace == "player":
        return f"seat{order.index(h)}" if h in order else "player?"
    if h.namespace == "emblem":
        e = ex.emblems.get(h)
        return f"emblem:{e[1]}" if e else "emblem?"
    if h.namespace == "ability":
        frame = next((f for f in ex.stack.frames if f.handle == h), None)
        return f"ab<{_desc(game, frame.source)}>" if frame is not None else "ability?"
    if h not in world.cards:
        return "gone"
    try:
        zone = world.zone_of(h)
        where = f"{zone.kind}@{order.index(zone.controller)}"
    except KeyError:
        where = "nowhere"
    return f"{world.cards[h].identity.oracle_id}|{where}"


def _canon_text(game: Any, text: str) -> str:
    def sub(m: re.Match) -> str:
        return _desc(game, Handle(m.group(1), int(m.group(2))))

    return _SEQ.sub("", _H.sub(sub, text))


def signature(game: Any, shuffled: frozenset = frozenset()) -> str:
    """``shuffled``: the players whose library a shuffle reordered after the decision. A shuffle
    makes every order of the same cards equally likely, so those libraries compare as multisets
    (equal in distribution), the others in order."""
    world, ex = game.world, game.executor
    order = world.player_order
    seat = {p: i for i, p in enumerate(order)}
    parts: list[Any] = [("turn", world.turn, ex.phase, seat.get(world.active_player),
                         seat.get(ex.priority_holder), ex.passes, game.reason or "")]
    sick, counts = FT._this_turn(ex)
    for p in order:
        pl = world.players[p]
        z = pl.zones
        oid = lambda hs: [world.cards[h].identity.oracle_id for h in hs]  # noqa: E731
        parts.append(("player", seat[p], pl.life, tuple(sorted(pl.mana_pool.items())),
                      p in ex.lost_players, tuple(sorted(ex.layers.keywords(p))),
                      tuple(counts.get(p, ()))))
        parts.append(("hand", tuple(sorted(oid(z[ZONE_HAND].entries)))))
        lib = tuple(reversed(oid(z[ZONE_LIBRARY].entries)))
        parts.append(("library", tuple(sorted(lib)) if str(p) in shuffled else lib))
        parts.append(("graveyard", tuple(oid(z[ZONE_GRAVEYARD].entries))))
        parts.append(("exile", tuple(sorted(oid(z[ZONE_EXILE].entries)))))
        if ZONE_COMMAND in z:
            parts.append(("command", tuple(sorted(oid(z[ZONE_COMMAND].entries)))))
        perms = []
        for h in z[ZONE_BATTLEFIELD].entries:
            card = world.cards[h]
            ident = card.identity
            pt = None
            if ident.power is not None or ident.toughness is not None:
                try:
                    pt = ex.ledger.effective_pt(ident, h, card.counters)
                except Exception:  # noqa: BLE001 - a signature never crashes the census
                    pt = "?"
            host = ex.attachments.get(h)
            chosen = tuple(sorted(str(v) for (s, q), v in ex.name_choices.items() if s == h))
            perms.append((ident.oracle_id, seat.get(ex.control_overlay.get(h, p)), bool(card.tapped),
                          tuple(sorted(card.counters.items())), ex.damage.get(h, 0), str(pt),
                          tuple(sorted(ex.layers.keywords(h))),
                          _desc(game, host) if host is not None else "",
                          h in sick, h in ex.phased_out, chosen,
                          len(ex.layers.granted_abilities(h)),
                          h in ex.attackers, _desc(game, ex.attacked[h]) if h in ex.attacked else "",
                          tuple(sorted(_desc(game, b) for b in ex.blocked_by.get(h, ())))))
        parts.append(("battlefield", seat[p], tuple(sorted(perms, key=repr))))
    stack = []
    for f in reversed(ex.stack.frames):
        src = f.source if f.spell_kind in ("ACTIVATED", "TRIGGERED") else f.handle
        stack.append((f.spell_kind, _desc(game, src), seat.get(f.controller), f.x_value,
                      bool(getattr(f, "kicked", False)),
                      tuple(_desc(game, t) for t in f.declared_targets)))
    parts.append(("stack", tuple(stack)))
    parts.append(("waiting", len(world.triggers)))
    live = [r for r in ex.layers.dump() if r[5] not in ("expired",)]
    parts.append(("layers", tuple(sorted(_canon_text(game, repr(r[1:8])) for r in live))))
    parts.append(("repl", tuple(sorted(_canon_text(game, repr(r)) for r in ex.replacements.dump()))))
    if ex.returns.rows:
        parts.append(("returns", tuple(sorted(_canon_text(game, repr(r)) for r in ex.returns.dump()))))
    return repr(parts)


# ----------------------------------------------------------------------- the copies


class ScriptDriver:
    """Both seats in a copy: the script, then the option under test, then the null continuation."""

    name = "detector-script"

    def __init__(self, script: list[str], test: str) -> None:
        self.script, self.i, self.test = script, 0, test
        self.answered = False
        self.cont = 0
        self.shuffles0: Counter = Counter()

    def decide(self, ask: Any, obs: Any) -> int:
        if len(ask.options) == 1:
            return 0
        tokens = [o.token for o in ask.options]
        if self.i < len(self.script):
            word = self.script[self.i]
            self.i += 1
            if word not in tokens:
                raise Stop(f"replay diverged at {ask.site}: {word!r} not in {tokens[:8]}")
            return tokens.index(word)
        if not self.answered:
            self.answered = True
            # the shuffles so far: only a shuffle AFTER the answer makes order a multiset
            self.shuffles0 = _shuffles(obs.executor)
            if self.test not in tokens:
                raise Stop(f"test option {self.test!r} not offered at {ask.site}")
            return tokens.index(self.test)
        self.cont += 1
        if self.cont > CONT_MAX:
            raise Stop("continuation guard")
        if ask.kind in CLEAN:
            return tokens.index("PASS") if "PASS" in tokens else 0
        game_like = _GameView(obs.executor)
        keys = [_canon_text(game_like, t) for t in tokens]
        return min(range(len(tokens)), key=lambda k: (keys[k], k))


class _GameView:
    """What _desc needs from a game, built from an executor."""

    def __init__(self, executor: Any) -> None:
        self.executor = executor
        self.world = executor.world


def run_option(base: Any, supply: Any, oracle: Any, script: list[str], test: str,
               turn0: int) -> tuple[str, str]:
    """(signature, status) after replaying ``script`` then ``test`` from a copy of ``base``."""
    game = fork(base, supply)
    drv = ScriptDriver(script, test)
    router = SeatRouter(game, [drv, drv], [SeatLens(s, oracle, ViewOptions()) for s in (0, 1)],
                        supply=supply)

    def stop_after(g: Any, boundary: str) -> bool:
        if not drv.answered:
            return False
        if g.world.turn > turn0 + 1:
            return True
        return boundary == "priority" and not g.executor.stack.frames

    status = "ok"
    try:
        _play(game, router, list(game.world.player_order), TURN_CAP, resumed=True,
              stop_after=stop_after)
    except Stop as e:
        status = str(e)[:80]
        if not drv.answered:
            return "", status
    except Exception as e:  # noqa: BLE001 - an engine error in a copy is reported, never fatal
        return "", f"error {type(e).__name__}: {str(e)[:60]}"
    if status == "ok" and drv.cont > CONT_MAX:
        status = "guard"
    shuffles = _shuffles(game.executor)
    return signature(game, frozenset(k for k in shuffles if shuffles[k] > drv.shuffles0[k])), status


def _shuffles(executor: Any) -> Counter:
    """SHUFFLE audit rows per library owner (verbs._v_shuffle)."""
    return Counter(r[2] for r in executor.events if len(r) > 2 and r[1] == "SHUFFLE")


# ----------------------------------------------------------------------- the recorded game


def _name(game: Any, token: str) -> str:
    """A token's card name (handles only), for reading the examples."""
    h = FT._handle(token)
    if h is None or h not in game.world.cards:
        return token
    return game.world.cards[h].identity.name


class Recorder:
    def __init__(self, gid: int, supply: Any, oracle: Any, max_opts: int, rng: np.random.Generator,
                 out: Any, set_code: str) -> None:
        self.gid, self.supply, self.oracle = gid, supply, oracle
        self.max_opts, self.rng, self.out, self.set_code = max_opts, rng, out, set_code
        self.pause = None  # a copy at the last pause point
        self.script: list[str] = []
        self.values: list[tuple[int, int, float]] = []  # seat, turn, v
        self.rows = 0
        self.known_from_public: dict[Handle, int] = {}  # card -> journal index it entered a hand
        self.j_seen = 0
        self.t_detect = 0.0
        self.game = None
        self.kw_names: Counter = Counter()

    def scan_journal(self, ex: Any) -> None:
        """Cards a hand received from a public zone (known to every player while they stay)."""
        events = ex.journal.events
        for row in events[self.j_seen:]:
            if row.kind == KIND_ZONE_CHANGE and row.zone_move is not None:
                src, dst = row.zone_move[0], row.zone_move[1]
                if dst == ZONE_HAND and src in PUBLIC:
                    self.known_from_public[row.subject] = 1
                elif src == ZONE_HAND:
                    self.known_from_public.pop(row.subject, None)
        self.j_seen = len(events)

    def gaps(self, game: Any, ask: Any, seat: int) -> dict:
        ex, world = game.executor, game.world
        order = world.player_order
        me, opp = order[seat], order[1 - seat]
        g: dict[str, int] = {}
        blocked = [a for a, bs in ex.blocked_by.items() if bs]
        g["pairs"] = int(len(blocked) >= 2)
        g["pw_attacked"] = int(any(d.namespace == "card" for d in ex.attacked.values()))
        kw = sorted({k for p in order for k in ex.layers.keywords(p)})
        g["player_kw"] = int(bool(kw))
        if kw:
            self.kw_names.update(kw)
        g["emblem"] = int(bool(ex.emblems))
        g["phased"] = int(bool(ex.phased_out))
        g["returns"] = int(bool(ex.returns.rows))
        multi = gone = delayed = 0
        for f in ex.stack.frames:
            multi |= len(f.declared_targets) > 1
            if f.spell_kind in ("ACTIVATED", "TRIGGERED"):
                gone |= f.source not in world.cards
                if f.spell_kind == "TRIGGERED" and f.source in world.cards:
                    delayed |= FT._ability_index(ex, f) == -1
        g["stack_multi_target"], g["token_source_gone"], g["delayed_idx"] = int(multi), int(gone), int(delayed)
        if ask.kind not in ("act", "act_second_main"):
            try:
                g["permit_hidden"] = int(bool(PM.playable(ex, me)))
            except Exception:  # noqa: BLE001
                g["permit_hidden"] = 0
        if ask.kind == "target":
            m = re.match(r"pick:card:(\d+)", ask.site)
            if m:
                h = Handle("card", int(m.group(1)))
                cost = world.cards[h].identity.mana_cost if h in world.cards else ""
                g["x_target"] = int("X" in (cost or ""))
        self.scan_journal(ex)
        hand = set(world.players[opp].zones[ZONE_HAND].entries)
        g["known_opp_hand"] = sum(1 for h in self.known_from_public if h in hand)
        own = set(world.players[me].zones[ZONE_HAND].entries)
        g["opp_knows_mine"] = sum(1 for h in self.known_from_public if h in own)
        return g

    def knowledge_events(self) -> dict:
        """The game's knowledge-making events (memory's reach, PLAN_NETWORK_READINESS §4): the
        audit rows REVEAL, LOOK_AT, SCRY, SHUFFLE, SEARCH, and zone moves into a hand or a library
        by where they came from."""
        if self.game is None:
            return {}
        ex = self.game.executor
        out: Counter = Counter()
        for row in ex.events:
            if len(row) > 1 and row[1] in ("REVEAL", "LOOK_AT", "SCRY", "SHUFFLE", "SEARCH"):
                out[row[1]] += 1
        for row in ex.journal.events:
            if row.kind == KIND_ZONE_CHANGE and row.zone_move is not None:
                src, dst = row.zone_move[0], row.zone_move[1]
                if dst in (ZONE_HAND, ZONE_LIBRARY) and src != dst:
                    out[f"{src}->{dst}"] += 1
        return dict(out)

    def decision(self, ask: Any, obs: Any, feats: dict, pick: int, v: float, p_pick: float) -> None:
        game = obs.game
        self.game = game
        seat = ask.seat
        tokens = [o.token for o in ask.options]
        row: dict[str, Any] = {"gid": self.gid, "set": self.set_code, "turn": game.world.turn,
                               "seat": seat, "kind": ask.kind, "site": ask.site[:60],
                               "n": len(tokens), "pick": pick, "v": round(v, 4),
                               "p": round(p_pick, 4)}
        enc = enc_classes(feats)
        ids: dict[Any, int] = {}
        row["enc"] = [ids.setdefault(k, len(ids)) for k in enc]
        row["gaps"] = self.gaps(game, ask, seat)
        clean = ask.kind in CLEAN
        if ask.kind.startswith("mulligan"):
            # no pause point before the first turn: the bottom choice's copies are counted by name
            if ask.kind == "mulligan_bottom":
                names = [_desc(game, FT._handle(t)) if FT._handle(t) else t for t in tokens]
                cid: dict[str, int] = {}
                row["cls"] = [cid.setdefault(nm.split("|")[0], len(cid)) for nm in names]
                row["how"] = "by-name"
        elif clean or self.pause is not None:
            t0 = time.perf_counter()
            base = fork_live(game, self.supply) if clean else self.pause
            script = [] if clean else list(self.script)
            idx = list(range(len(tokens)))
            if len(idx) > self.max_opts:
                # keep every option that shares an encoding class with another, then sample
                dup = [i for i in idx if row["enc"].count(row["enc"][i]) > 1]
                rest = [i for i in idx if i not in dup]
                k = max(0, self.max_opts - len(dup))
                idx = sorted(set(dup[: self.max_opts]) | set(self.rng.choice(rest, size=min(k, len(rest)), replace=False).tolist()))
            sigs: dict[str, int] = {}
            cls = [-1] * len(tokens)
            status = Counter()
            first = ""
            for i in idx:
                sig, st = run_option(base, self.supply, self.oracle, script, tokens[i],
                                     game.world.turn)
                status[st if not st.startswith("error") else "error"] += 1
                if sig:
                    cls[i] = sigs.setdefault(sig, len(sigs))
                    first = first or sig
            if first and self.rows % 10 == 0:
                # the copies are deterministic: the first tested option again, the same signature
                again, _ = run_option(base, self.supply, self.oracle, script,
                                      tokens[next(i for i in idx if cls[i] == 0)], game.world.turn)
                row["det"] = again == first
            row["cls"] = cls
            row["status"] = dict(status)
            row["how"] = "fork"
            if len({c for c in cls if c >= 0}) < sum(c >= 0 for c in cls):
                row["toks"] = [t[:40] for t in tokens[:16]]
                row["names"] = [_name(game, t) for t in tokens[:16]]
                src = re.search(r"(card|emblem):\d+", ask.site)
                row["src"] = _name(game, src.group(0)) if src else ""
            if clean:
                self.pause = base
                self.script = []
            self.t_detect += time.perf_counter() - t0
        if not ask.kind.startswith("mulligan"):
            self.script.append(tokens[pick])
        self.values.append((seat, game.world.turn, v))
        self.out.write(json.dumps(row) + "\n")
        self.rows += 1


def enc_classes(feats: dict) -> list[tuple]:
    """Per option, everything of its encoding: its whole opts_i and opts_f rows, and the encoded
    rows of the entities it points at (``search.option_classes`` leaves out O_NAMED). Equal keys:
    options whose own tokens the network cannot tell apart (context could still, by attention)."""
    ci, cf, oi, of = feats["cards_i"], feats["cards_f"], feats["opts_i"], feats["opts_f"]

    def entity(e: int) -> Any:
        return (ci[e - 3].tobytes(), cf[e - 3].tobytes()) if e >= 3 else e

    def own(k: int) -> bytes:
        # the option's row without its entity references (columns 1 and 2), which are positions
        # in the entity list: two copies are two positions, the same token to the network
        row = oi[k].copy()
        row[1:3] = 0
        return row.tobytes()

    return [(own(k), of[k].tobytes(), entity(int(oi[k, 1])), entity(int(oi[k, 2])))
            for k in range(len(oi))]


class NetDriver:
    """The network on CPU, sampling as a training seat does; every decision goes to the recorder."""

    def __init__(self, net: Any, table: Any, rec: Recorder, rng: np.random.Generator) -> None:
        self.net, self.table, self.rec, self.rng = net, table, rec, rng
        self.name = "net"

    @torch.no_grad()
    def decide(self, ask: Any, obs: Any) -> int:
        if len(ask.options) == 1:
            return 0
        feats = FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx)
        b = M.collate([feats], "cpu")
        logits, value = self.net(b)
        probs = torch.softmax(logits[0, : len(ask.options)].float(), -1).numpy().astype(np.float64)
        probs /= probs.sum()
        pick = int(self.rng.choice(len(probs), p=probs))
        self.rec.decision(ask, obs, feats, pick, float(value[0]), float(probs[pick]))
        return pick


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--seed0", type=int, default=77_000_000)
    ap.add_argument("--mix", type=float, default=0.25, help="share of M20 deals (r29's --mix-share)")
    ap.add_argument("--max-opts", type=int, default=16)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    torch.set_num_threads(1)
    net, table, _ = M.load(a.ckpt, "cpu")
    out = open(a.out, "w")
    games_out = open(a.out.replace(".jsonl", "_games.jsonl"), "w")
    for i in range(a.games):
        seed = a.seed0 + i
        rng = np.random.default_rng(seed)
        set_code = "M20" if rng.random() < a.mix else "M21"
        supply = get_supply("verified", set_code)
        oracle = OracleIndex.for_sets(set_code)
        rec = Recorder(i, supply, oracle, a.max_opts, rng, out, set_code)
        drivers = [NetDriver(net, table, rec, np.random.default_rng(seed * 2 + s)) for s in (0, 1)]
        t0 = time.time()
        res = play_game(seed, drivers, deck_mode="coherent", pool_mode="verified", set_code=set_code)
        g = {"gid": i, "seed": seed, "set": set_code, "outcome": res["outcome"],
             "winner": res["winner"], "turns": res["turns"], "rows": rec.rows,
             "wall_s": round(time.time() - t0, 1), "detect_s": round(rec.t_detect, 1),
             "knowledge": rec.knowledge_events(), "player_kw": dict(rec.kw_names),
             "values": rec.values, "crash": res.get("crash")}
        games_out.write(json.dumps(g) + "\n")
        out.flush()
        games_out.flush()
        print(json.dumps({k: v for k, v in g.items() if k != "values"}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
