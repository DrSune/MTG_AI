"""Every differing replay game in one cause bucket, checked from the journals and decisions:

  same play            the journals are identical; only the division asks differ (order/trample
                       asks on main, divide asks on the branch)
  division             first differing row is combat damage from an attacker blocked by two or
                       more creatures (CR 510.1c: the attacker now divides freely)
  trample over         first differing row is combat damage from an attacker blocked by one
                       creature, main having asked trample:... (main's heuristic kept all of it on
                       the blocker; the branch assigns lethal and tramples the rest over, 702.19b)
  Leafkin Druid        the branch taps a Leafkin Druid for mana in the phase the journals part
  107.1b               a LIFE_LOST row from a GAIN_LIFE on main, absent on the branch
  unexplained          anything else

with the winner per side; then each game's first differing journal row on each side (card names
in brackets), or for a "same play" game its first differing division ask.

    classify3.py <main dir> <branch dir>
"""
import ast
import collections
import re
import sys
from pathlib import Path


def load(path):
    lines = path.read_text().splitlines()
    names = {}
    for line in lines:
        if line.startswith("NAMES "):
            names = dict(ast.literal_eval(line[6:]))
    j = [ast.literal_eval(line[2:]) for line in lines if line.startswith("J ")]
    a = [line[2:] for line in lines if line.startswith("A ")]
    winner = lines[0].split()[3]
    return winner, j, a, names


def first(xs, ys):
    i = next((k for k, (x, y) in enumerate(zip(xs, ys)) if x != y), None)
    if i is None:
        return None if len(xs) == len(ys) else min(len(xs), len(ys))
    return i


def blockers_of(rows, start, end, dealer):
    out = []
    for r in rows[start:end]:
        if r[1] == "DECLARE_BLOCKERS":
            blocked = r[5].split("index=")[1].split(")")[0]
            if f"card:{blocked}" == dealer:
                out.append(r[2])
    return out


def named(row, names):
    if row is None:
        return "(end)"
    text = f"{row[1]} {row[2]} by {row[3]} ({row[4]}) {row[5]}"
    text = re.sub(r"Handle\(namespace='(\w+)', index=(\d+)\)", r"\1:\2", text)
    return re.sub(r"card:\d+", lambda m: f"{m.group(0)}[{names.get(m.group(0), '?')}]", text)[:200]


main_dir, branch_dir = Path(sys.argv[1]), Path(sys.argv[2])
buckets = collections.defaultdict(list)
flips = []
lines = []
for path in sorted(main_dir.iterdir(), key=lambda p: (p.stem.split("_")[0], int(p.stem.split("_")[1]))):
    wa, ja, aa, names = load(path)
    wb, jb, ab, names_b = load(branch_dir / path.name)
    names = {**names_b, **names}
    jd = first(ja, jb)
    if jd is None:
        same_other = [x for x in aa if x.split(":")[0] not in ("order", "trample", "divide")] == \
                     [x for x in ab if x.split(":")[0] not in ("order", "trample", "divide")]
        kind = "same play" if same_other else "unexplained"
    else:
        ra, rb = ja[jd], jb[jd]
        start = max(k for k, r in enumerate(ja[:jd]) if r[1] == "TURN_PHASE")
        in_combat = "COMBAT" in ja[start][5]
        end_b = next((k for k in range(jd, len(jb)) if jb[k][1] == "TURN_PHASE"), len(jb))
        if ra[1] == rb[1] == "DAMAGE" and ra[3] == rb[3] and in_combat:
            n = len(blockers_of(ja, start, jd, ra[3]))
            turn_asks = [x for x in aa if x.startswith(f"trample:{ra[3]}:")]
            tramples_b = any(r[1] == "DAMAGE" and r[3] == ra[3] and r[2].startswith("player:")
                             for r in jb[start:end_b])
            if n >= 2:
                kind = "division"
            elif n == 1 and turn_asks and tramples_b:
                kind = "trample over"
            else:
                kind = "unexplained"
        elif any(r[1] == "TAP_STATE" and names.get(r[2]) == "Leafkin Druid" and r[4] == "TAP"
                 for r in jb[max(0, jd - 1):end_b]):
            kind = "Leafkin Druid"
        elif ra[1] == "LIFE_LOST" and ra[4] == "GAIN_LIFE":
            kind = "107.1b"
        else:
            kind = "unexplained"
    buckets[kind].append(path.stem)
    if wa != wb:
        flips.append(f"{path.stem} ({kind}): winner {wa} -> {wb}")
    if jd is None:
        k = first(aa, ab)
        lines.append(f"{path.stem} [{kind}] ask main: {aa[k] if k is not None and k < len(aa) else '(end)'}"
                     f" | branch: {ab[k] if k is not None and k < len(ab) else '(end)'}")
    else:
        lines.append(f"{path.stem} [{kind}] row {jd} main: {named(ja[jd] if jd < len(ja) else None, names)}"
                     f" | branch: {named(jb[jd] if jd < len(jb) else None, names)}")
for kind, games in sorted(buckets.items(), key=lambda kv: -len(kv[1])):
    by_set = collections.Counter(g.split("_")[0] for g in games)
    print(f"{len(games):4} {kind:14} {dict(by_set)}")
print("total", sum(len(g) for g in buckets.values()))
print("winner changed:", len(flips))
for line in flips:
    print("  ", line)
if buckets.get("unexplained"):
    print("UNEXPLAINED", buckets["unexplained"])
print("\nEach game's first difference:")
for line in lines:
    print(" ", line)
