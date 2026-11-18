"""Gate round W3's census (DESIGN_ATOM_ONTOLOGY §20, §5's rows, NUMBERS.md): over the 19 sets'
cards, card records applied (verified or not), every form the round registers or rewrote, with
the card, its set and whether its tree is the verified one.

    census.py <checkout> > census.txt

Rows (tab-separated): the form, the set, V (verified tree) or -, whole or part (unparsed
sentences left), the card. Forms:
- STATE: a TriggeredAbility whose event is a StateTrigger (CR 603.8);
- EXTRA / EXTRA_CAUSE: a TRIGGER_ADDITIONAL static (CR 603.2d), without or with a `cause`;
- REVEAL_HAND / REVEAL_RESULT / REVEAL_TOP / REVEAL_UNTIL: REVEAL with `cards` over a hand, with
  `cards` the `result` register, the top `count` of a library, or the top down `until` a match;
- LOOK_TOP: LOOK_AT (always the top `count` of a library);
- SCRY.
A last block counts each form's trees and cards. On main (0b7f9c22) the first three forms do not
exist and every REVEAL is a top-`count` one (reports/w3_2026-11-18/old_forms_main.txt).
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(REPO))
from MTG_bot.core import ability_tree as at
from MTG_bot.core.compiler import card_records
from MTG_bot.core.compiler.compiler import compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.errors import StateCorruptionError

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
registry = build_full_registry()


def forms(card: at.CardRecord) -> list[str]:
    out = []
    for n in at.walk(card):
        if isinstance(n, at.TriggeredAbility) and isinstance(n.event, at.StateTrigger):
            out.append("STATE")
        if isinstance(n, at.Atom) and n.verb is at.Verb.TRIGGER_ADDITIONAL:
            out.append("EXTRA_CAUSE" if n.args.get("event").cause is not None else "EXTRA")
        if isinstance(n, at.Atom) and n.verb is at.Verb.REVEAL:
            cards = n.args.get("cards")
            if cards == at.RESULT_REFERENT:
                out.append("REVEAL_RESULT")
            elif cards is not None:
                out.append("REVEAL_HAND")
            elif n.args.get("until") is not None:
                out.append("REVEAL_UNTIL")
            else:
                out.append("REVEAL_TOP")
        if isinstance(n, at.Atom) and n.verb is at.Verb.LOOK_AT:
            out.append("LOOK_TOP")
        if isinstance(n, at.Atom) and n.verb is at.Verb.SCRY:
            out.append("SCRY")
    return out


trees: Counter[str] = Counter()
names: dict[str, set[str]] = {}
for code in SETS:
    raw = ingest_pool(REPO / "MTG_bot" / "data" / f"{code}.json")
    records = card_records.load_records(code)
    for oid, rc in sorted(raw.items(), key=lambda kv: kv[1].identity.name):
        if rc.is_token or rc.is_emblem:
            continue
        try:
            res = compile_pool({oid: rc}, registry, records=records, require_verified=False).results[oid]
        except (StateCorruptionError, ValueError):
            continue
        if res.card is None:
            continue
        ver = "V" if card_records.is_verified(res, records.get(oid)) else "-"
        whole = "whole" if not (res.unparsed or res.back_face_unparsed) else "part"
        for form in forms(res.card):
            print(f"{form}\t{code}\t{ver}\t{whole}\t{rc.identity.name}")
            trees[form] += 1
            names.setdefault(form, set()).add(rc.identity.name)
print()
for form in sorted(trees):
    print(f"# {form}: {trees[form]} atoms or abilities, {len(names[form])} cards")
