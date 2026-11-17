"""Delayed (non-reflexive) triggers of the dealt pools' verified cards, with their events."""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.executor.games import get_supply  # noqa: E402

for code in ("M21", "M20", "FDN"):
    sup = get_supply("verified", code)
    for oid in sorted(sup.verified_ids):
        res = sup.pool.results.get(oid)
        if res is None or res.card is None:
            continue
        for node in at.walk(res.card):
            if isinstance(node, at.DelayedTrigger) and not node.reflexive:
                print(code, res.card.name, "|", repr(node.event)[:300])
