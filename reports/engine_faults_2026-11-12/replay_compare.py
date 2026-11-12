"""Compare two replay.py runs on the same deals: games identical in play (world, events, journal)
and in the full replay fingerprint, the games that differ, crashes, and wall time.

    .venv/bin/python reports/engine_faults_2026-11-12/replay_compare.py BASE.jsonl HEAD.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load(path: str) -> dict:
    return {row["seed"]: row for row in map(json.loads, Path(path).read_text().splitlines())}


base, head = load(sys.argv[1]), load(sys.argv[2])
assert base.keys() == head.keys(), "different seeds"
play_diff = [s for s in sorted(base) if base[s]["play"] != head[s]["play"]]
fp_diff = [s for s in sorted(base) if base[s]["fingerprint"] != head[s]["fingerprint"]]
outcome_diff = [s for s in sorted(base) if (base[s]["outcome"], base[s]["winner"], base[s]["turns"])
                != (head[s]["outcome"], head[s]["winner"], head[s]["turns"])]
print(json.dumps({
    "games": len(base),
    "identical_play": len(base) - len(play_diff),
    "identical_fingerprint": len(base) - len(fp_diff),
    "play_differs": play_diff,
    "fingerprint_only_differs": [s for s in fp_diff if s not in play_diff],
    "outcome_differs": outcome_diff,
    "crashes_base": [(s, r["crash"]) for s, r in sorted(base.items()) if r["crash"]],
    "crashes_head": [(s, r["crash"]) for s, r in sorted(head.items()) if r["crash"]],
    "wall_s": [round(sum(r["wall_s"] for r in base.values()), 1), round(sum(r["wall_s"] for r in head.values()), 1)],
}, indent=1))
