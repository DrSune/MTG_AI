"""The fork's cost at the planning puzzles' roots (KNOWLEDGE/2026-11-18/214 §1): the mean of 200
forks of each puzzle's world-0 game at its arranged start, in ms.

    CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 nice -n 19 .venv/bin/python \
        reports/planning_puzzles_2026-11-18/fork_cost.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.puzzles import puzzle as P
from tools.search.fork import fork

out = []
for path in sorted(P.SUITE.glob("*.json")):
    pz = P.load(path)
    game, _ = P.build(pz, 0)
    supply = P.supply_of(pz)
    fork(game, supply)  # warm the intern cache
    t = time.perf_counter()
    for _ in range(200):
        fork(game, supply)
    ms = (time.perf_counter() - t) / 200 * 1000
    out.append(ms)
    print(f"{pz['name']:36s} {len(game.world.cards):3d} cards  {ms:.2f} ms")
print(f"mean {sum(out) / len(out):.2f} ms, min {min(out):.2f}, max {max(out):.2f}")
