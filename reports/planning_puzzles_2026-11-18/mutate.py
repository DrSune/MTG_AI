"""The solver's tests against naive solvers (KNOWLEDGE/2026-11-18/214 §1): three mutations of
tools/puzzles/solver.py, each must fail tools/puzzles/test_solver.py. The file is restored after
each run (and on any error).

    .venv/bin/python reports/planning_puzzles_2026-11-18/mutate.py

2026-11-18: fusion 2 failed, first 2 failed, no_min 5 failed (of 8); unmutated 8 passed.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "tools" / "puzzles" / "solver.py"
MUTANTS = {
    # every member its own information set: the decider may act on what it cannot see
    "fusion": ("groups.setdefault(leaf.key, []).append((i, leaf))",
               "groups.setdefault((leaf.key, i, id(leaf)), []).append((i, leaf))"),
    # the opponent plays its first option instead of its best reply
    "first": ("stack.extend(reversed(list(node.children.values())))",
              "stack.append(next(iter(node.children.values())))"),
    # the opponent maximises the decider's value
    "no_min": ("start[i] = min(start[i], leaf.value)", "start[i] = max(start[i], leaf.value)"),
}

src = PATH.read_text()
try:
    for name, (old, new) in MUTANTS.items():
        if old not in src:
            sys.exit(f"{name}: the line to mutate is gone: {old}")
        PATH.write_text(src.replace(old, new))
        r = subprocess.run([sys.executable, "-m", "pytest", "tools/puzzles/test_solver.py", "-q"],
                           cwd=ROOT, capture_output=True, text=True, check=False)
        print(name, r.stdout.strip().splitlines()[-1])
finally:
    PATH.write_text(src)
