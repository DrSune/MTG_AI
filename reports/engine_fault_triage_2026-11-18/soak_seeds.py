"""The seeds behind soak.sh's detector hits (soak.py's summary keeps the hit, not its game):
replays tools/cards/soak.py's own play_one for seeds 1..N of a pool and prints every hit with
its seed, so each class can be traced in one game (215, F65 / BACKLOG B-73).

    soak_seeds.py <checkout> <SET> <N>
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
for p in (ROOT, ROOT / "tools" / "cards", ROOT / "tools" / "audit"):
    sys.path.insert(0, str(p))
import soak  # noqa: E402

code, n = sys.argv[2], int(sys.argv[3])
for seed in range(1, n + 1):
    res = soak.play_one((code, "verified", False, "stress", seed))
    for h in res["hits"]:
        print(f"{code} seed {seed}: {h['detector']}: {h['detail']}", flush=True)
    if res.get("crash"):
        print(f"{code} seed {seed}: CRASH {res['crash']}", flush=True)
