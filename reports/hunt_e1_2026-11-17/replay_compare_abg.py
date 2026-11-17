"""Compare two replay_abg.py outputs (base, branch): per set, how many games have identical replay
digests, journals and raw event logs, the crashes on each side, and for every game that differs
the index of its first differing journal row.

    replay_compare_abg.py <base.json> <branch.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

base = json.loads(Path(sys.argv[1]).read_text())
new = json.loads(Path(sys.argv[2]).read_text())
total = differing = 0
for code in base:
    b, n = base[code], new[code]
    same = sum(1 for x, y in zip(b, n, strict=True) if x["digest"] == y["digest"])
    journals = sum(1 for x, y in zip(b, n, strict=True) if x["journal"] == y["journal"])
    events = sum(1 for x, y in zip(b, n, strict=True) if x["events"] == y["events"])
    crashes = (sum(1 for g in b if g["crash"]), sum(1 for g in n if g["crash"]))
    print(f"{code}: games {len(b)}; identical digests {same}; identical journals {journals}; "
          f"identical event logs {events}; crashes {crashes[0]} (base) / {crashes[1]} (branch)")
    for x, y in zip(b, n, strict=True):
        total += 1
        if (x["digest"], x["journal"], x["events"]) == (y["digest"], y["journal"], y["events"]):
            continue
        differing += 1
        first = next((k for k, (r, s) in enumerate(zip(x["rows"], y["rows"])) if r != s),
                     min(len(x["rows"]), len(y["rows"])))
        same_outcome = (x["outcome"], x["winner"], x["turns"], x["lives"]) == (
            y["outcome"], y["winner"], y["turns"], y["lives"])
        print(f"  {code}:{x['seed']}: first differing journal row {first} "
              f"(of {len(x['rows'])} / {len(y['rows'])}); digest {'same' if x['digest'] == y['digest'] else 'differs'}; "
              f"outcome {'same' if same_outcome else 'differs'}: "
              f"{x['outcome']} {x['winner']} t{x['turns']} {x['lives']} -> "
              f"{y['outcome']} {y['winner']} t{y['turns']} {y['lives']}"
              + (f"; crash {x['crash']} -> {y['crash']}" if x["crash"] or y["crash"] else ""))
print(f"games whose journal or play differs: {differing} of {total}")
