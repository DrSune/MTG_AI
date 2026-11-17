"""The three ruling lints (tools/cards/lints.py food, two_events, its_controller) over every card of
the 19 sets, card records applied: findings on verified trees (homes and reprints: false
positives) and on the rest (the unmapped printings each ruling covers).

    .venv/bin/python reports/rulings_2026-11-17/lint_census.py > reports/rulings_2026-11-17/lint_census.txt
"""
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO), str(REPO / "tools" / "cards")]
import corpus
import lints

from MTG_bot.core.compiler import card_records

NAMES = ("food", "two_events", "its_controller")
cards, flagged = Counter(), Counter()
for code in corpus.SETS:
    sc = corpus.compile_set(code)
    for oid, res in sorted(sc.results.items()):
        if res is None or sc.raw[oid].is_token or sc.raw[oid].is_emblem:
            continue
        side = "verified" if card_records.is_verified(res, sc.records.get(oid, {})) else "other"
        cards[side] += 1
        for name in NAMES:
            for finding in lints.LINTS[name](sc.raw[oid], res.card):
                flagged[(name, side)] += 1
                print(f"{side}\t{code}\t{res.card.name}\t{name}: {finding[:120]}")
print(f"trees: {dict(cards)}; findings: " + ", ".join(
    f"{name} {flagged[(name, 'verified')]} verified / {flagged[(name, 'other')]} other" for name in NAMES))
