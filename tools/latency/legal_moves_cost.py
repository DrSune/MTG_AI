"""How expensive is the legality oracle itself on a big combat board?

Sequential model calls are the headline threat (see `decisions.py`), but the *mask
builder* is on the critical path of every one of them. `engine.get_legal_moves()` at the
declare-blockers step is O(A x B x R): for each (blocker, attacker) pair it linearly
scans `graph.relationships` (`engine.py:147`). So the engine's own per-decision cost also
grows as a product of board dimensions, independently of the model.

This matters beyond the current implementation. CR 509.1c requires that a block
declaration obey the *maximum possible* number of blocking requirements, which is a
constrained maximisation the engine must solve to answer "is this block legal". An
opponent who plays requirement-creating cards (Nemesis Mask, menace, "blocks if able")
is attacking the mask builder, not the network.

Reported: wall-clock of one get_legal_moves() call, and the menu width, as a function of
(attackers, blockers).
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", default="1,4,8,12,16,20,30")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()

    from tools.latency.decisions import _plant_board

    rows = []
    for n in [int(x) for x in a.sizes.split(",")]:
        graph, engine = _plant_board(n, n, seed=7)
        ts = []
        for _ in range(a.reps):
            t0 = time.perf_counter()
            moves = engine.get_legal_moves()
            ts.append((time.perf_counter() - t0) * 1000)
        rows.append({
            "attackers": n, "blockers": n,
            "menu_width": len(moves),
            "get_legal_moves_ms_median": round(statistics.median(ts), 3),
            "get_legal_moves_ms_max": round(max(ts), 3),
            "entities": len(graph.entities),
            "relationships": len(graph.relationships),
        })
        print(json.dumps(rows[-1]))

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
