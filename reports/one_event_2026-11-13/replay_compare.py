"""Compare two replay.py outputs (base, branch): per set, the games, identical replay digests and
journal dumps, crashes, and the engine seconds; then each differing game.

    replay_compare.py <replay_base.json> <replay_branch.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

base = json.loads(Path(sys.argv[1]).read_text())
new = json.loads(Path(sys.argv[2]).read_text())
differ = []
for code in base:
    b, n = base[code], new[code]
    same = sum(1 for x, y in zip(b, n) if x["digest"] == y["digest"])
    journals = sum(1 for x, y in zip(b, n) if x["journal"] == y["journal"])
    crashes = (sum(1 for g in b if g["crash"]), sum(1 for g in n if g["crash"]))
    secs = (sum(g["seconds"] for g in b), sum(g["seconds"] for g in n))
    print(f"{code}: games {len(b)}; identical digests {same}; identical journals {journals}; "
          f"crashes {crashes[0]} (base) / {crashes[1]} (branch); engine seconds "
          f"{secs[0]:.1f} / {secs[1]:.1f} ({100 * (secs[1] / secs[0] - 1):+.1f}%)")
    for i, (x, y) in enumerate(zip(b, n)):
        if x["digest"] != y["digest"] or x["journal"] != y["journal"]:
            differ.append((code, i))
            print(f"  game {i}: digest {'same' if x['digest'] == y['digest'] else 'DIFFERS'}, journal "
                  f"differs; outcome {x['outcome']} -> {y['outcome']}, turns {x['turns']} -> {y['turns']}, "
                  f"rows {x['rows']} -> {y['rows']}, crash {x['crash']} -> {y['crash']}")
print("differing games:", " ".join(f"{c}:{i}" for c, i in differ) or "none")
