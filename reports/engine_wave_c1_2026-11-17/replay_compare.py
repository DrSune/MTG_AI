"""Compare two replay.py outputs (base, branch): per set, the decks' pool size, the games, how many
replay digests, journal dumps and raw event logs are identical, the moves a replacement replaced
on each side, and the crashes on each side; every game that differs, listed.

    replay_compare.py <replay_base.json> <replay_branch.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

base = json.loads(Path(sys.argv[1]).read_text())
new = json.loads(Path(sys.argv[2]).read_text())
total = differing = 0
for code in base:
    b, n = base[code]["games"], new[code]["games"]
    same = sum(1 for x, y in zip(b, n, strict=True) if x["digest"] == y["digest"])
    journals = sum(1 for x, y in zip(b, n, strict=True) if x["journal"] == y["journal"])
    events = sum(1 for x, y in zip(b, n, strict=True) if x["events"] == y["events"])
    crashes = (sum(1 for g in b if g["crash"]), sum(1 for g in n if g["crash"]))
    print(f"{code}: deckable {base[code]['deckable']} (base) / {new[code]['deckable']} (branch); "
          f"taken out: {len(base[code]['taken_out'])}; games {len(b)}; identical digests {same}; "
          f"identical journals {journals}; identical event logs {events}; "
          f"replaced moves {sum(x['replaced'] for x in b)} (base) / {sum(y['replaced'] for y in n)} (branch); "
          f"crashes {crashes[0]} (base) / {crashes[1]} (branch)")
    for i, (x, y) in enumerate(zip(b, n, strict=True)):
        total += 1
        if (x["digest"], x["journal"], x["events"]) != (y["digest"], y["journal"], y["events"]):
            differing += 1
            print(f"  game {i}: {x} -> {y}")
print(f"games whose play differs: {differing} of {total}")
