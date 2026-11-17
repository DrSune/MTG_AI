"""For the division and trample-over games of classify3.py: the dealer's whole combat damage plan
(its COMBAT_DAMAGE row) at the first difference, each side, and whether the totals agree.

    totals.py <main dir> <branch dir>
"""
import ast
import re
import sys
from pathlib import Path

sys.argv += []
main_dir, branch_dir = Path(sys.argv[1]), Path(sys.argv[2])


def load(path):
    lines = path.read_text().splitlines()
    return [ast.literal_eval(line[2:]) for line in lines if line.startswith("J ")]


def plan(rows, start, dealer):
    for r in rows[start:]:
        if r[1] == "COMBAT_DAMAGE" and r[2] == dealer:
            return [(int(a), f"{ns}:{ix}") for a, ns, ix in
                    re.findall(r"\((\d+), Handle\(namespace='(\w+)', index=(\d+)\)\)", r[5])]
    return None


bad = 0
seen = 0
for path in sorted(main_dir.iterdir()):
    ja, jb = load(path), load(branch_dir / path.name)
    jd = next((k for k, (x, y) in enumerate(zip(ja, jb)) if x != y), None)
    if jd is None or not (ja[jd][1] == jb[jd][1] == "DAMAGE" and ja[jd][3] == jb[jd][3]):
        continue
    start = max(k for k, r in enumerate(ja[:jd]) if r[1] == "TURN_PHASE")
    if "COMBAT" not in ja[start][5]:
        continue
    dealer = ja[jd][3]
    pa, pb = plan(ja, start, dealer), plan(jb, start, dealer)
    seen += 1
    if pa is None or pb is None or sum(a for a, _ in pa) != sum(a for a, _ in pb):
        bad += 1
        print(path.stem, dealer, pa, pb)
print(f"{seen} games: totals differ in {bad}")
