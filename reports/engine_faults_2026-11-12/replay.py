"""Seeded heuristic-vs-heuristic games on a verified pool, one JSON line per game, for comparing
two engines on the same deals: the final replay fingerprint (Executor.state_fingerprint), a play
fingerprint (the world, the event log and the journal: what happened, without the registries'
bookkeeping), the outcome, the turns, and any crash.

Run with the engine under test first on sys.path:
    .venv/bin/python reports/engine_faults_2026-11-12/replay.py ROOT SET FIRST_SEED N OUT.jsonl
ROOT is the checkout whose code plays (the base export or the worktree). Seeds FIRST_SEED ..
FIRST_SEED+N-1; even seeds deal stress decks, odd ones coherent decks (the learner's two modes).
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))

from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
from MTG_bot.core.executor.games import (
    TURN_CAP,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import SelfplayRouter, outcome_of

set_code, first, n, out = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), Path(sys.argv[5])
assert Path(sys.modules["MTG_bot"].__file__).resolve().is_relative_to(root), "wrong engine on the path"
supply = get_supply("verified", set_code)
oracle = OracleIndex.for_sets(set_code)
with out.open("w") as fh:
    for seed in range(first, first + n):
        mode = "stress" if seed % 2 == 0 else "coherent"
        game = _setup_game(seed, supply, deal_decks(seed, 1409, supply, mode))
        router = SelfplayRouter(game, [HeuristicAgent(), HeuristicAgent()],
                                [SeatLens(s, oracle, ViewOptions()) for s in (0, 1)], supply=supply)
        started = time.monotonic()
        crash = None
        try:
            _play(game, router, game.world.player_order, TURN_CAP)
            outcome, winner = outcome_of(game)
        except Exception as error:  # noqa: BLE001 - a crash is recorded, never scored
            outcome, winner, crash = "void-crash", None, f"{type(error).__name__}: {error}"
        ex = game.executor
        play = hashlib.sha256(
            "\n".join([ex.world.fingerprint(), *map(repr, ex.events), *map(repr, ex.journal.dump())]).encode()
        ).hexdigest()
        row = {
            "set": set_code, "seed": seed, "mode": mode, "outcome": outcome, "winner": winner,
            "turns": game.turns, "reason": game.reason, "crash": crash,
            "fingerprint": ex.state_fingerprint(), "play": play,
            "asks": [st["asks"] for st in router.stats],
            "wall_s": round(time.monotonic() - started, 3),
        }
        fh.write(json.dumps(row) + "\n")
        fh.flush()
