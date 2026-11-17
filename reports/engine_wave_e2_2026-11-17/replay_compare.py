"""Compare two replay.py outputs (main, branch): per set, games with identical journals, event logs
and decisions; outcomes and crashes on each side; every game that differs.

    replay_compare.py <replay_main.json> <replay_branch.json>
"""
import json
import sys
from pathlib import Path

a = json.loads(Path(sys.argv[1]).read_text())
b = json.loads(Path(sys.argv[2]).read_text())
total = differing = 0
for code in a:
    ga, gb = a[code], b[code]
    same = sum(1 for x, y in zip(ga, gb, strict=True) if (x["journal"], x["events"], x["asks"]) ==
               (y["journal"], y["events"], y["asks"]))
    crashes = (sum(1 for g in ga if g["crash"]), sum(1 for g in gb if g["crash"]))
    winners = sum(1 for x, y in zip(ga, gb, strict=True) if (x["outcome"], x["winner"]) != (y["outcome"], y["winner"]))
    print(f"{code}: games {len(ga)}; identical {same}; outcome or winner changed {winners}; "
          f"crashes {crashes[0]} (main) / {crashes[1]} (branch)")
    for i, (x, y) in enumerate(zip(ga, gb, strict=True)):
        total += 1
        if (x["journal"], x["events"], x["asks"]) != (y["journal"], y["events"], y["asks"]):
            differing += 1
            print(f"  {code} game {i}: main {x['outcome']} w{x['winner']} t{x['turns']} -> "
                  f"branch {y['outcome']} w{y['winner']} t{y['turns']}")
print(f"games whose play differs: {differing} of {total}")
