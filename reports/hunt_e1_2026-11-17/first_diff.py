"""For each game in two dump_journals.py outputs (base, branch): the first differing journal row on
each side, with the card names of the handles it mentions, and a class for the difference:
- etb-counters: the branch's row is a COUNTER_PLACED row the base lacks (fix G: counters a
  permanent enters with are journalled, CR 122.6), and the base resumes in step one row later;
- other: anything else (to be read by hand).
Also counts, per game, how many extra rows the branch has and whether every extra row is such a
counter row (the base's rows, in order, are the branch's with those rows taken out).

    first_diff.py <base.json> <branch.json>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

base = json.loads(Path(sys.argv[1]).read_text())
new = json.loads(Path(sys.argv[2]).read_text())


def strip_clock(row: str) -> str:
    # the row's clock is its first field: rows after an inserted row are shifted by one
    return re.sub(r"^\((\d+), ", "(", row)


def label(row: str, names: dict) -> str:
    return re.sub(r"card:(\d+)", lambda m: f"card:{m.group(1)}[{names.get('card:' + m.group(1), '?')}]", row)


classes: dict[str, int] = {}
for game in base:
    b, n = base[game]["rows"], new[game]["rows"]
    names = {**base[game]["names"], **new[game]["names"]}
    first = next((k for k, (x, y) in enumerate(zip(b, n)) if x != y), min(len(b), len(n)))
    # the branch's extra rows: walk both, skipping branch rows the base lacks
    i = j = 0
    extra = []
    other = None
    while i < len(b) and j < len(n):
        if strip_clock(b[i]) == strip_clock(n[j]) or b[i] == n[j]:
            i += 1
            j += 1
            continue
        extra.append(n[j])
        j += 1
        if len(extra) > 50:
            other = "too many"
            break
    extra += n[j:]
    leftover_base = len(b) - i
    counter_only = all("COUNTER_PLACED" in r for r in extra) and leftover_base == 0 and other is None
    cls = "etb-counters" if counter_only else "other"
    classes[cls] = classes.get(cls, 0) + 1
    print(f"{game}: {cls}; first differing row {first}; branch +{len(extra)} rows"
          + ("" if counter_only else f"; base rows left unmatched {leftover_base}"))
    print(f"   base:   {label(b[first], names) if first < len(b) else '-'}")
    print(f"   branch: {label(n[first], names) if first < len(n) else '-'}")
    if not counter_only:
        for r in extra[:5]:
            print(f"   extra:  {label(r, names)}")
print(classes)
