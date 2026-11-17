"""Census of the verified pools (M21, M20, FDN) for the cards whose play the A, B, G fixes can
touch: tokens with triggered abilities, triggers whose event can name a token that left the
battlefield, CounterPlaced triggers, EtBState counters, loyalty abilities, IS_ATTACHED_TO_SOURCE.

    census.py <checkout>
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.executor.games import get_supply  # noqa: E402
from MTG_bot.core.executor.legality import is_loyalty_ability  # noqa: E402

rows: dict[str, set] = {}


def add(fact, code, name):
    rows.setdefault(fact, set()).add(f"{code} {name}")


for code in ("M21", "M20", "FDN"):
    sup = get_supply("verified", code)
    for oid in sorted(sup.verified_ids):
        res = sup.pool.results.get(oid)
        if res is None or res.card is None:
            continue
        card = res.card
        name = card.name
        for node in at.walk(card):
            if isinstance(node, at.TokenSpec) and any(
                isinstance(a, at.TriggeredAbility) for a in node.abilities
            ):
                add("token-with-trigger", code, name)
            if isinstance(node, at.TriggeredAbility):
                ev = node.event
                kind = type(ev).__name__
                if isinstance(ev, at.CreatureDiesEvent):
                    add("trigger:CreatureDies", code, name)
                elif isinstance(ev, at.ZoneChangeEvent) and getattr(ev, "from_zone", None) is not None:
                    fz = ev.from_zone
                    if getattr(fz, "kind", None) == at.ZoneKind.BATTLEFIELD:
                        add("trigger:LeavesBattlefield", code, name)
                elif isinstance(ev, at.CounterPlacedEvent):
                    add("trigger:CounterPlaced", code, name)
                elif isinstance(ev, at.SacrificeEvent):
                    add("trigger:Sacrifice", code, name)
                elif isinstance(ev, at.DamageDealtEvent):
                    add("trigger:DamageDealt", code, name)
                if node.condition is not None:
                    add(f"trigger-with-condition:{kind}", code, name)
            if isinstance(node, at.DelayedTrigger) and node.reflexive:
                add("reflexive", code, name)
            if isinstance(node, at.EtBState) and node.initial_counters:
                add("etb-counters", code, name)
            if isinstance(node, at.ActivatedAbility) and is_loyalty_ability(node):
                add("loyalty-ability", code, name)
            if isinstance(node, at.FAtom) and node.pred is at.FAtomPred.IS_ATTACHED_TO_SOURCE:
                add("IS_ATTACHED_TO_SOURCE", code, name)
            if isinstance(node, at.Atom) and node.verb is at.Verb.CREATE_TOKEN:
                add("creates-token", code, name)
for fact in sorted(rows):
    print(f"{fact} ({len(rows[fact])}): {', '.join(sorted(rows[fact]))}")
