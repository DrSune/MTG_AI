"""F01's activated lane (KNOWLEDGE/2026-11-18/215 §11): which activated abilities of the three
verified deal pools designate a player ("target player", "target opponent": a TARGET selector over
a PLAYER zone, or a TARGET_PLAYER / TARGET_OPPONENT ref in the effect), and, for each, whether the
seat's activation is refused when no player is a legal target (CR 602.2b -> 601.2c).

    f01_activated_lane.py <checkout>
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools" / "audit"))
import fault_shapes as fs  # noqa: E402

from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.executor.games import get_supply  # noqa: E402

REFS = (at.ControllerRef.TARGET_PLAYER, at.ControllerRef.TARGET_OPPONENT)
found = []
for code in ("M21", "M20", "FDN"):
    s = get_supply("verified", code)
    for oid in s.deckable:
        card = s.pool.results[oid].card
        for idx, ab in enumerate(card.abilities):
            if not isinstance(ab, at.ActivatedAbility):
                continue
            player_slot = any(isinstance(n, at.Selector) and n.mode is at.SelectorMode.TARGET
                              and at.ZoneKind.PLAYER in fs.zones_of(n) for _p, n in fs.walk(ab.effect))
            ref = any(f"ControllerRef.{r.name}" in repr(ab.effect) for r in REFS)  # an enum leaf
            if player_slot or ref:
                found.append((code, card.name, idx, "player slot" if player_slot else "designated-player ref"))
for row in found:
    print(*row)
print(f"{len(found)} activated abilities with a target-player designation in the three verified pools")
