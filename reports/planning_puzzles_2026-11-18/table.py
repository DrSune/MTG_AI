"""The readout's tables (KNOWLEDGE/2026-11-18/214 §4) from the runner's output.

    .venv/bin/python reports/planning_puzzles_2026-11-18/table.py \
        reports/planning_puzzles_2026-11-18/readout.json
"""

import json
import sys
from pathlib import Path

CATS = ["A", "B1", "B2", "B3", "C", "D"]


def f(x, fmt="{:.2f}"):
    return "-" if x is None else fmt.format(x)


rep = json.loads(Path(sys.argv[1]).read_text())
print("Per category: twin-consistent pass rate (greedy) / mean probability on the right options /")
print("searched pass rate (8 seeds; '-': not searched). Then the whole suite.")
print("| Checkpoint | " + " | ".join(CATS)
      + " | pairs | single | p right | searched | searched pairs | value order |")
print("|---" * (len(CATS) + 7) + "|")
for r in rep:
    s = r["summary"]
    a = s["all"]
    cells = [f"{f(s[c]['twin_consistent'])} / {f(s[c]['p_right'])} / {f(s[c]['searched_pass'])}"
             for c in CATS]
    print(f"| {Path(r['checkpoint']).stem} | " + " | ".join(cells)
          + f" | {f(a['twin_consistent'])} | {f(a['single_pass'])} | {f(a['p_right'])}"
          + f" | {f(a['searched_pass'])} | {f(a['searched_twin_consistent'])} | {f(a['value_order'])} |")
print()
print("Per puzzle: greedy right (Y/n), probability on the right options, searched pass rate")
names = [x["puzzle"] for x in rep[0]["rows"]]
print("| Puzzle | " + " | ".join(Path(r["checkpoint"]).stem for r in rep) + " |")
print("|---" * (len(rep) + 1) + "|")
for i, n in enumerate(names):
    cells = []
    for r in rep:
        x = r["rows"][i]
        sp = "" if "searched_pass" not in x else f" s{x['searched_pass']:.2f}"
        cells.append(f"{'Y' if x['pass'] else 'n'} {x['p_right']:.2f}{sp}")
    print(f"| {n} | " + " | ".join(cells) + " |")
print()
print("Value head (v + 1) / 2 at the root, beside the solver's value")
print("| Puzzle | solver | " + " | ".join(Path(r["checkpoint"]).stem for r in rep) + " |")
print("|---" * (len(rep) + 2) + "|")
for i, n in enumerate(names):
    print(f"| {n} | {rep[0]['rows'][i]['solver_value']:.3f} | "
          + " | ".join(f"{r['rows'][i]['value']:.2f}" for r in rep) + " |")
