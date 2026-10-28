"""Kill test K2 data: choices labelled by the engine itself (owner 2026-10-28; REVIEW_ARCHITECTURE §4).

    MTG_REPO=<tree> .venv/bin/python tools/k2/gen.py --set M21 --games 60 --out FILE.jsonl

The owner's question after K1: does the network that PLAYS know what the components mean, "when to
choose what it can choose, ... how much to sacrifice, what it means to sacrifice"? The existing
teacher cannot answer it. ``gameplay_eval_v2.HeuristicTeacher`` takes the first option at every
target, sacrifice and mode ask. So the engine labels each choice instead:

1. **Base game.** Both seats choose uniformly at random, seeded. Every ask is recorded, in the
   order the bench's ``SeatRouter`` raises it.
2. **Try every option.** At every target, sacrifice, discard, may, choose and one_of ask, each
   option is tried by replay:
   - the same seed and the same earlier answers;
   - then this option;
   - then a do-nothing continuation (the refuse option, else the first);
   - up to the next clean boundary (``games._play(stop_after=...)``).
3. **Record, don't judge.** What is recorded is the 24-number board summary from the asking seat
   (``tools/k1/gen.py`` ``board``), before the ask and after each option. The value function that
   turns those into a label belongs to the trainer (``train.py``), so it can change without
   regenerating anything.

The engine is deterministic given the seed and the answers. A replay that raises anything but the
recorded ask at a recorded position is therefore a bug, and it raises ``ReplayDivergence``.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import signal
import sys
import time
from multiprocessing import Pool
from pathlib import Path
from typing import Any

REPO = Path(os.environ.get("MTG_REPO", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(REPO))

from MTG_bot.bench.router import SeatRouter
from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
from MTG_bot.core.executor.games import _play, _setup_game, deal_decks, get_supply
from MTG_bot.core.identity import Handle
from MTG_bot.utils import rng

# tools/k1/gen.py is also named gen.py, so it is loaded by path: board() is K1's 24-number summary
_K1 = importlib.util.spec_from_file_location(
    "k1_gen", Path(__file__).resolve().parents[1] / "k1" / "gen.py")
assert _K1 is not None and _K1.loader is not None
_k1_gen = importlib.util.module_from_spec(_K1)
_K1.loader.exec_module(_k1_gen)
board = _k1_gen.board

#: The choices whose right answer depends on what the asking card does.
ELIGIBLE = ("target", "sacrifice", "discard", "may", "choose", "one_of")
TURN_CAP = 30  # shorter than the engine's 60: every option replays the game up to its ask
ZONES = ("battlefield", "graveyard", "hand", "exile", "library")


class ReplayDivergence(RuntimeError):
    pass


class GameTimeout(Exception):
    pass


def _alarm(_signum: int, _frame: Any) -> None:
    raise GameTimeout


class Scripted:
    """One driver for both seats.

    - Base game (``at`` is None): uniform random answers, seeded.
    - Replay: answer ``script`` up to position ``at``, answer ``to`` there, and afterwards do
      nothing (the refuse option, else option 0).
    """

    name = "k2-scripted"

    def __init__(self, seed: int, script: list | None = None, at: int | None = None,
                 to: int | None = None, observe: Any = None) -> None:
        self.rng = rng.substream("bench", "k2-base", seed)
        self.script, self.at, self.to, self.observe = script or [], at, to, observe
        self.k = 0
        self.log: list[tuple[str, str, tuple[str, ...], int, int]] = []
        self.deviated = False

    def decide(self, ask: Any, obs: Any) -> int:
        k = self.k
        self.k += 1
        tokens = tuple(o.token for o in ask.options)
        if self.at is None:
            if self.observe is not None:
                self.observe(k, ask, obs)
            idx = self.rng.randrange(len(ask.options))
        elif k < self.at:
            kind, site, recorded, _seat, idx = self.script[k]
            if (kind, site, recorded) != (ask.kind, ask.site, tokens):
                raise ReplayDivergence(f"position {k}: recorded {site} {recorded}, "
                                       f"replay asks {ask.site} {tokens}")
        elif k == self.at:
            assert self.to is not None
            idx, self.deviated = self.to, True
        else:
            idx = ask.refuse if ask.refuse is not None else 0
        self.log.append((ask.kind, ask.site, tokens, ask.seat, idx))
        return idx


def source_handle(site: str) -> Handle | None:
    """The card whose ability asks: the first ``card:N`` in the site tag.

    Engine tags put the deciding player first ("sacrifice:player:0:card:12:<digest>",
    legality.py:1505), so the first handle (``tag_handle``) can be the player. The act window's
    target picks are "pick:card:34:<k>".
    """
    parts = site.split(":")
    for i in range(len(parts) - 1):
        if parts[i] == "card" and parts[i + 1].isdigit():
            return Handle("card", int(parts[i + 1]))
    return None


def _zone_of(executor: Any, handle: Handle) -> str:
    for seat in executor.world.player_order:
        for zone in ZONES:
            if handle in executor.world.players[seat].zone(zone).entries:
                return zone
    return "other"


def facts(executor: Any, token: str, me: Handle) -> dict[str, Any]:
    """What an option is: a card (its oracle id, side, zone, P/T), a player, or a word."""
    namespace, _, index = token.partition(":")
    if namespace == "player" and index.isdigit():
        return {"player": True, "mine": Handle("player", int(index)) == me}
    if namespace == "card" and index.isdigit():
        handle = Handle("card", int(index))
        card = executor.world.cards[handle]
        ident = card.identity
        p = t = None
        if "Creature" in ident.type_line:
            try:
                p, t = executor.ledger.effective_pt(ident, handle, card.counters)
            except Exception:  # noqa: BLE001 - '*' P/T outside the ledger's reach
                p, t = None, None
        try:
            mine = executor.controller_of(handle) == me
        except Exception:  # noqa: BLE001 - off the battlefield a card has an owner, not a controller
            mine = ident.owner == me if hasattr(ident, "owner") else None
        return {"oid": ident.oracle_id, "mine": mine,
                "zone": _zone_of(executor, handle), "types": ident.type_line,
                "pt": [p, t], "tapped": bool(card.tapped), "token": bool(ident.is_token)}
    return {"word": token}


class _Shim:
    def __init__(self, executor: Any) -> None:
        self.executor = executor


def _game(set_code: str, pool: str, seed: int, driver: Scripted) -> tuple[Any, SeatRouter]:
    supply = get_supply(pool, set_code)
    game = _setup_game(seed, supply, deal_decks(seed, 1409, supply))
    lenses = [SeatLens(s, OracleIndex.for_sets(set_code), ViewOptions()) for s in (0, 1)]
    return game, SeatRouter(game, [driver, driver], lenses, supply=supply)


def play(args: tuple) -> list[dict[str, Any]]:
    set_code, pool, seed, timeout = args
    pending: dict[int, dict[str, Any]] = {}

    def observe(k: int, ask: Any, obs: Any) -> None:
        if ask.kind not in ELIGIBLE or len(ask.options) < 2:
            return
        executor = obs.executor
        me = executor.world.player_order[ask.seat]
        source = source_handle(ask.site)
        card = (executor.world.cards[source]
                if source is not None and source.namespace == "card" else None)
        if ask.kind == "choose" and card is not None and "Land" in card.identity.type_line:
            return  # a dual land's mana colour: the board summary cannot tell the options apart
        source_oid = card.identity.oracle_id if card is not None else None
        pending[k] = {"kind": ask.kind, "site": ask.site, "seat": ask.seat, "source": source_oid,
                      "turn": executor.world.turn, "before": board(_Shim(executor), me),
                      "options": [o.token for o in ask.options],
                      "facts": [facts(executor, o.token, me) for o in ask.options],
                      "refuse": ask.refuse}

    signal.signal(signal.SIGALRM, _alarm)
    rows: list[dict[str, Any]] = []
    base = Scripted(seed, observe=observe)
    try:
        signal.alarm(timeout)
        game, router = _game(set_code, pool, seed, base)
        _play(game, router, game.world.player_order, TURN_CAP)
    except GameTimeout:
        return rows
    except Exception:  # noqa: BLE001 - a crashed base game yields nothing
        return rows
    finally:
        signal.alarm(0)
    for k, row in sorted(pending.items()):
        after, ok = [], True
        for j in range(len(row["options"])):
            driver = Scripted(seed, script=base.log, at=k, to=j)
            try:
                signal.alarm(timeout)
                game, router = _game(set_code, pool, seed, driver)
                _play(game, router, game.world.player_order, TURN_CAP,
                      stop_after=lambda _g, _b, d=driver: d.deviated)
                if not driver.deviated:  # the replay ended before reaching the ask
                    ok = False
                    break
                after.append(board(game, game.world.player_order[row["seat"]]))
            except ReplayDivergence:
                raise
            except Exception:  # noqa: BLE001 - an option the engine cannot finish voids the ask
                ok = False
                break
            finally:
                signal.alarm(0)
        if ok:
            rows.append({"set": set_code, "seed": seed, "pos": k, **row, "after": after})
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--set", required=True)
    ap.add_argument("--pool", default="castable")
    ap.add_argument("--games", type=int, default=60)
    ap.add_argument("--first-seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--game-timeout", type=int, default=60)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    rng.seed_all(20261028)
    jobs = [(args.set, args.pool, s, args.game_timeout)
            for s in range(args.first_seed, args.first_seed + args.games)]
    started = time.perf_counter()
    n = 0
    with Pool(args.workers) as pool, open(args.out, "w", encoding="utf-8") as out:
        out.write(json.dumps({"kind": "manifest", "set": args.set, "pool": args.pool,
                              "games": args.games, "first_seed": args.first_seed,
                              "turn_cap": TURN_CAP, "eligible": ELIGIBLE,
                              "repo": str(REPO)}) + "\n")
        for batch in pool.imap_unordered(play, jobs, chunksize=1):
            for row in batch:
                out.write(json.dumps(row) + "\n")
                n += 1
    print(f"{args.set}: {n} decisions from {args.games} games in "
          f"{time.perf_counter() - started:.0f} s -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
