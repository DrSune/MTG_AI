"""Tally the branch-only journal rows of the differing games (journals_base.json vs
journals_branch.json): which rows, on which cards. A branch-only row is one the base lacks once
both journals are aligned on their other rows (difflib on the rows without their clocks)."""
import collections
import difflib
import json
import re
import sys

b_all = json.load(open(sys.argv[1]))
n_all = json.load(open(sys.argv[2]))


def strip(r):
    return re.sub(r"^\((\d+), ", "(", r)


tally = collections.Counter()
base_only = collections.Counter()
per_game = {}
for game in b_all:
    b, n = b_all[game]["rows"], n_all[game]["rows"]
    names = {**b_all[game]["names"], **n_all[game]["names"]}
    sb, sn = [strip(r) for r in b], [strip(r) for r in n]
    sm = difflib.SequenceMatcher(a=sb, b=sn, autojunk=False)
    extra, missing = [], []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op in ("insert", "replace"):
            extra += sn[j1:j2]
        if op in ("delete", "replace"):
            missing += sb[i1:i2]
    kinds = []
    for r in extra:
        parts = eval(r)  # (kind, subject, cause, verb, data) after the clock strip
        name = names.get(parts[1], parts[1])
        kinds.append(f"{parts[0]} {name} {parts[4]}")
    for k in kinds:
        tally[re.sub(r"\('PLUS_1_PLUS_1', \d+\)|\('SOUL', \d+\)", lambda m: m.group(0).split(',')[0] + ")", k)] += 1
    for r in missing:
        parts = eval(r)
        base_only[f"{parts[0]} {names.get(parts[1], parts[1])}"] += 1
    per_game[game] = (len(extra), len(missing))
for k, v in tally.most_common():
    print(f"{v:4d}  branch-only: {k}")
for k, v in base_only.most_common():
    print(f"{v:4d}  base-only: {k}")
print("games with base-only rows:", [g for g, (e, m) in per_game.items() if m])
