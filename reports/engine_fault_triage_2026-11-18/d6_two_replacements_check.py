"""Soak's d6 '2 replacement records for one event' in M21 seeds 114 and 297: are they two live copies
of one card's replacement (legal: CR 616.1 applies each in turn), not one card registered twice?
Prints, per seed, the copies of each M21 card with a damage replacement in each dealt deck.

    d6_two_replacements_check.py <checkout>
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
for p in (ROOT, ROOT / "tools" / "cards", ROOT / "tools" / "audit"):
    sys.path.insert(0, str(p))
from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.executor.games import deal_decks  # noqa: E402

import soak  # noqa: E402

sup = soak._supply("M21", "verified", False)
damage_repl = {oid for oid in sup.deckable for n in at.walk(sup.pool.results[oid].card)
               if isinstance(n, at.ReplacementAbility) and isinstance(n.event, at.DamageDealtEvent)}
print("M21 cards with a damage replacement:", sorted(sup.metas[o].name for o in damage_repl))
for seed in (114, 297):
    decks = deal_decks(seed, 1409, sup, "stress")
    for i, deck in enumerate(decks):
        copies = {sup.metas[o].name: deck.count(o) for o in set(deck) if o in damage_repl}
        print(f"seed {seed} deck {i}: {copies}")
