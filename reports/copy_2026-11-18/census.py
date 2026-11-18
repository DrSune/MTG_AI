"""The copy round's census (DESIGN_ATOM_ONTOLOGY §18) from a tree_dump.py output: per fact the
round adds (a token copy, a copy put onto the stack, permanents becoming copies, QProp ORDINAL,
FNot(IS_RESULT)), the trees of the 19 sets that carry it, records applied, verified or not.

    census.py <trees.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

FACTS = ("copy-token", "copy-stack", "copy-become", "ordinal", "not-result")
dump = json.loads(Path(sys.argv[1]).read_text())
for fact in FACTS:
    rows = sorted(
        (code, row["name"], bool(row.get("verified")), bool(row.get("record")))
        for code, cards in dump.items() for row in cards.values()
        if fact in row.get("facts", ())
    )
    print(f"{fact}: {len(rows)} trees")
    for code, name, verified, record in rows:
        print(f"   {code} {name}{' (record)' if record else ''}{' VERIFIED' if verified else ''}")
