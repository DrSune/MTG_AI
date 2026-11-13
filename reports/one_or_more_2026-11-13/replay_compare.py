"""Compare two replay.py outputs (base, branch): per set, the decks' pool size, the games, how many
replay digests and journal dumps are identical, the games that queued a flagged trigger, and the
crashes on each side.

    replay_compare.py <replay_base.json> <replay_branch.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

base = json.loads(Path(sys.argv[1]).read_text())
new = json.loads(Path(sys.argv[2]).read_text())
for code in base:
    b, n = base[code]["games"], new[code]["games"]
    same = sum(1 for x, y in zip(b, n) if x["digest"] == y["digest"])
    journals = sum(1 for x, y in zip(b, n) if x["journal"] == y["journal"])
    flagged = sum(1 for y in n if y["flagged_queues"])
    crashes = (sum(1 for g in b if g["crash"]), sum(1 for g in n if g["crash"]))
    print(f"{code}: deckable {base[code]['deckable']} (base) / {new[code]['deckable']} (branch); "
          f"taken out: {len(base[code]['taken_out'])}; games {len(b)}; identical digests {same}; "
          f"identical journals {journals}; games queueing a flagged trigger {flagged} "
          f"({sum(y['flagged_queues'] for y in n)} queues); "
          f"crashes {crashes[0]} (base) / {crashes[1]} (branch)")
    for i, (x, y) in enumerate(zip(b, n)):
        if x["digest"] != y["digest"] or x["journal"] != y["journal"]:
            print(f"  game {i}: {x} -> {y}")
