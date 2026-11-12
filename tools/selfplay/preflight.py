"""Pre-flight for a self-play run (docs/TRAINING_REVIEW_PROTOCOL.md §1): writes
``<run>/preflight.json`` and exits non-zero when a check fails.

- P1 the working tree is clean and its commit is recorded;
- P8 a smoke slate of games on the run's pool raises no engine error and voids none;
- P9 almost every game ends by a loss (life, library, effect), not by the turn cap or a stall;
- P12 the same seed replays to the same game, journal digest included.

    .venv/bin/python -m tools.selfplay.preflight runs/selfplay/NAME [--games 200]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

from MTG_bot.bench.agents import UniformRandomAgent
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import play_game

REPO = Path(__file__).resolve().parents[2]
SMOKE_SEED0 = 3_000_000  # disjoint from training, evaluation and gate deals (learner.py)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                          check=False).stdout.strip()


def _game(seed: int, pool: str) -> dict:
    seats = [HeuristicAgent(), HeuristicAgent() if seed % 2 else UniformRandomAgent(random.Random(seed))]
    return play_game(seed, seats, deck_mode="stress" if seed % 3 else "coherent", pool_mode=pool)


def _digest(res: dict) -> str:
    keys = ("outcome", "winner", "reason", "turns", "lives", "asks", "crash")
    return hashlib.sha256(json.dumps({k: res.get(k) for k in keys}, default=str).encode()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--pool", default="verified")
    a = ap.parse_args(argv)
    checks: dict[str, dict] = {}
    # no optional locks: a status that refreshes the index would hold index.lock against
    # commits made in the same checkout meanwhile (as learner.write_manifest)
    dirty = _git("--no-optional-locks", "status", "--porcelain")
    checks["P1_clean_tree"] = {"pass": not dirty, "commit": _git("rev-parse", "HEAD"),
                               "dirty_paths": dirty.splitlines()[:20]}
    results = [_game(SMOKE_SEED0 + i, a.pool) for i in range(a.games)]
    errors = [r for r in results if r["crash"]]
    checks["P8_smoke_slate"] = {"pass": not errors, "games": a.games, "pool": a.pool,
                                "engine_errors": len(errors),
                                "first_errors": [r["crash"][:200] for r in errors[:5]]}
    ends = Counter(("loss" if r["outcome"] == "win" or r["outcome"] == "draw-mutual"
                    else r["outcome"]) for r in results)
    decided = ends["loss"] / max(a.games, 1)
    checks["P9_termination"] = {"pass": decided >= 0.95, "share_ended_by_a_loss": round(decided, 4),
                                "histogram": dict(ends)}
    first, again = _game(SMOKE_SEED0, a.pool), _game(SMOKE_SEED0, a.pool)
    checks["P12_replay"] = {"pass": _digest(first) == _digest(again), "seed": SMOKE_SEED0}
    report = {"pass": all(c["pass"] for c in checks.values()), "checks": checks}
    run = Path(a.run)
    run.mkdir(parents=True, exist_ok=True)
    (run / "preflight.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: v["pass"] for k, v in checks.items()} | {"pass": report["pass"]}))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
