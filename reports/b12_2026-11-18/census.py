"""Round B12's forms in the trees of the 19 sets (records applied, verified or not), from a
tree_dump.py output: the cards per fact, and each card holding one.

    census.py <trees.json>
"""
import json
import sys
from collections import defaultdict

dump = json.loads(open(sys.argv[1]).read())
ROUND = ("opening-hand", "prevent-CastSpellEvent", "prevent-ZoneChangeEvent",
         "prevent-LifeGainedEvent", "prevent-GameOutcomeEvent", "lose-game", "win-game")
cards = defaultdict(list)
for code, rows in dump.items():
    for row in rows.values():
        for fact in row.get("facts", []):
            if fact in ROUND:
                kind = "verified" if row.get("verified") else ("record" if row.get("record") else "compiler")
                cards[fact].append(f"{code} {row['name']} ({kind}, {row.get('unparsed')} unparsed)")
for fact in ROUND:
    print(f"{fact}: {len(cards[fact])}")
    for name in sorted(cards[fact]):
        print(f"   {name}")
