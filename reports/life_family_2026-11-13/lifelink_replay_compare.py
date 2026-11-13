"""Compare two lifelink_replay.py outputs (before the fix, after it): per set, the games, the
identical replay digests and journals, the crashes, and the combat damage steps in which a
lifelink dealer had two or more recipients; then each game that differs.

    lifelink_replay_compare.py <before.json> <after.json> <dump.json> [<before.journals.json>
                               <after.journals.json>]

<dump.json> is written: the {set: [game index, ...]} map of the games that differ, for the
journal runs of lifelink_replay.py on each side. Given those journals, each game's first
differing journal row and the rows after it are printed (a replayed game's journal sha is
checked against the first run's).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

before = json.loads(Path(sys.argv[1]).read_text())
after = json.loads(Path(sys.argv[2]).read_text())
dumped = [json.loads(Path(p).read_text()) for p in sys.argv[4:6]] if len(sys.argv) > 5 else None
differing: dict[str, list[int]] = {}
for code in before:
    b, a = before[code]["games"], after[code]["games"]
    same_digest = sum(x["digest"] == y["digest"] for x, y in zip(b, a))
    same_journal = sum(x["journal"] == y["journal"] for x, y in zip(b, a))
    with_split = [i for i, x in enumerate(b) if x["split_steps"]]
    print(f"{code}: deckable {before[code]['deckable']}; games {len(b)}; identical digests "
          f"{same_digest}; identical journals {same_journal}; crashes "
          f"{sum(bool(g['crash']) for g in b)} before / {sum(bool(g['crash']) for g in a)} after; "
          f"split lifelink steps before {sum(x['split_steps'] for x in b)} in {len(with_split)} "
          f"games, after {sum(y['split_steps'] for y in a)}")
    for i, (x, y) in enumerate(zip(b, a)):
        if x["digest"] == y["digest"] and x["journal"] == y["journal"]:
            continue
        differing.setdefault(code, []).append(i)
        print(f"  game {i}: split steps {x['split_steps']} -> {y['split_steps']}; digest "
              f"{'same' if x['digest'] == y['digest'] else 'differs'}; outcome {x['outcome']} -> "
              f"{y['outcome']}, turns {x['turns']} -> {y['turns']}, lives {x['lives']} -> {y['lives']}")
        if dumped is None or str(i) not in dumped[0].get(code, {}):
            continue
        sides = [dumped[0][code][str(i)], dumped[1][code][str(i)]]
        assert [s["journal"] for s in sides] == [x["journal"], y["journal"]], (code, i)
        rows_b, rows_a = sides[0]["rows"], sides[1]["rows"]
        first = next((k for k, (r, s) in enumerate(zip(rows_b, rows_a)) if r != s),
                     min(len(rows_b), len(rows_a)))
        print(f"    first differing journal row {first} of {len(rows_b)} / {len(rows_a)}:")
        for label, rows in (("before", rows_b), ("after ", rows_a)):
            for row in rows[first:first + 5]:
                print(f"      {label} {row}")
Path(sys.argv[3]).write_text(json.dumps(differing))
