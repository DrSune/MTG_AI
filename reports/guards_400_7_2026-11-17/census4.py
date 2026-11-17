"""Verified cards of the dealt pools that can make an Equipment's host illegal (CR 704.5n):
protection grants, GRANT_TYPE / type-changing, LOSE_ABILITY, and the Equipment holders."""
import sys
from pathlib import Path
ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.executor.games import get_supply  # noqa: E402
for code in ("M21", "M20", "FDN"):
    sup = get_supply("verified", code)
    facts = {}
    for oid in sorted(sup.verified_ids):
        res = sup.pool.results.get(oid)
        if res is None or res.card is None:
            continue
        card = res.card
        for node in at.walk(card):
            if isinstance(node, at.KeywordAbility) and node.keyword is at.Keyword.PROTECTION:
                facts.setdefault("protection", set()).add(card.name)
            if isinstance(node, at.Atom) and node.verb.name in ("GRANT_TYPE", "SET_TYPE", "LOSE_TYPE", "BECOME"):
                facts.setdefault(node.verb.name, set()).add(card.name)
        if "Equipment" in card.subtypes:
            facts.setdefault("equipment", set()).add(card.name)
    for k, v in sorted(facts.items()):
        print(code, k, len(v), sorted(v))
