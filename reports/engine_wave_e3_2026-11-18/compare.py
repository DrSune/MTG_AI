"""Compare two replay.py outputs (base, branch). Without --rows: per set the identical digests,
journals and event logs, crashes, and the differing games (written as SET:i lines to <list.txt>).
With --rows (two replay.py outputs of the differing games only): each game's first differing
journal row on both sides, the card names of the handles in it, and the rows around it.

    compare.py <base.json> <branch.json> <list.txt>
    compare.py --rows <base_rows.json> <branch_rows.json>
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def label(row: str, names: dict) -> str:
    return re.sub(r"card:(\d+)", lambda m: f"card:{m.group(1)}[{names.get('card:' + m.group(1), '?')}]", row)


if sys.argv[1] == "--rows":
    base = json.loads(Path(sys.argv[2]).read_text())
    new = json.loads(Path(sys.argv[3]).read_text())
    for code in base:
        for b, n in zip(base[code]["games"], new[code]["games"], strict=True):
            names = {**b["names"], **n["names"]}
            br, nr = b["rows"], n["rows"]
            first = next((k for k, (x, y) in enumerate(zip(br, nr)) if x != y), min(len(br), len(nr)))
            print(f"{code}:{b['game']}: first differing row {first} of {len(br)} (base) / {len(nr)} (branch); "
                  f"outcome {b['outcome']} -> {n['outcome']}, turns {b['turns']} -> {n['turns']}")
            for k in range(max(0, first - 3), first):
                print(f"   same:   {label(br[k], names)}")
            for k in range(first, min(first + 3, len(br))):
                print(f"   base:   {label(br[k], names)}")
            for k in range(first, min(first + 3, len(nr))):
                print(f"   branch: {label(nr[k], names)}")
    sys.exit(0)

base = json.loads(Path(sys.argv[1]).read_text())
new = json.loads(Path(sys.argv[2]).read_text())
differing = []
for code in base:
    b, n = base[code]["games"], new[code]["games"]
    same = sum(1 for x, y in zip(b, n, strict=True) if x["digest"] == y["digest"])
    journals = sum(1 for x, y in zip(b, n, strict=True) if x["journal"] == y["journal"])
    events = sum(1 for x, y in zip(b, n, strict=True) if x["events"] == y["events"])
    crashes = (sum(1 for g in b if g["crash"]), sum(1 for g in n if g["crash"]))
    print(f"{code}: deckable {base[code]['deckable']} / {new[code]['deckable']}; taken out "
          f"{len(base[code]['taken_out'])}; games {len(b)}; identical digests {same}, journals {journals}, "
          f"event logs {events}; crashes {crashes[0]} / {crashes[1]}")
    for x, y in zip(b, n, strict=True):
        if (x["digest"], x["journal"], x["events"]) != (y["digest"], y["journal"], y["events"]):
            differing.append(f"{code}:{x['game']}")
            print(f"  {code}:{x['game']}: digest {x['digest'] == y['digest']}, journal "
                  f"{x['journal'] == y['journal']}, events {x['events'] == y['events']}; outcome "
                  f"{x['outcome']} -> {y['outcome']}; crash {x['crash']} -> {y['crash']}")
print(f"games that differ: {len(differing)} of {sum(len(base[c]['games']) for c in base)}")
Path(sys.argv[3]).write_text("\n".join(differing) + "\n")
