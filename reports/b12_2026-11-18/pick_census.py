"""Gate round B12's MINOR 3, its reach: every resolution-time pick (a CHOOSE or ONE_OF `cards`
selector, no referent, not TARGET) that moves cards from a graveyard or library onto the
battlefield, in the 19 sets' trees with card records applied. Prints the card, verb, mode,
count, zones, whether the filter names a creature or permanent card ("creature?": the picks
Grafdigger's Cage can narrow; a self-return names its source instead, and the Cage keeps it
where it is unasked as before), whether a REST sibling shares the effect, and whether the card
is verified. Run from the checkout: pick_census.py > pick_census.txt"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(".").resolve()
sys.path.insert(0, str(ROOT))
from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.compiler import card_records  # noqa: E402
from MTG_bot.core.compiler.compiler import compile_pool  # noqa: E402
from MTG_bot.core.compiler.coverage import build_full_registry  # noqa: E402
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402
from MTG_bot.core.errors import StateCorruptionError  # noqa: E402

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
PICKS = (at.SelectorMode.CHOOSE, at.SelectorMode.ONE_OF)
HIDDEN = (at.ZoneKind.GRAVEYARD, at.ZoneKind.LIBRARY)

registry = build_full_registry()
for code in SETS:
    raw = ingest_pool(ROOT / "MTG_bot" / "data" / f"{code}.json")
    records = card_records.load_records(code)
    for oid, rc in sorted(raw.items(), key=lambda kv: kv[1].identity.name):
        if rc.is_token or rc.is_emblem:
            continue
        try:
            res = compile_pool({oid: rc}, registry, records=records,
                               require_verified=False).results[oid]
        except (StateCorruptionError, ValueError):
            continue
        nodes = list(at.walk(res.card))
        rest = any(isinstance(n, at.Selector) and n.mode is at.SelectorMode.REST for n in nodes)
        for n in nodes:
            if not isinstance(n, at.Atom) or n.verb not in (at.Verb.MOVE_ZONE, at.Verb.SEARCH):
                continue
            dest = n.args.get("destination")
            sel = n.args.get("cards")
            if not (isinstance(dest, at.Zone) and dest.kind is at.ZoneKind.BATTLEFIELD):
                continue
            if not isinstance(sel, at.Selector) or sel.mode not in PICKS or sel.referent:
                continue
            if not any(z.kind in HIDDEN for z in sel.zones):
                continue
            text = repr(sel.filter)
            creature = "Creature" in text or "Permanent" in text or "PERMANENT" in text
            print(code, rc.identity.name, n.verb.name, sel.mode.name, repr(sel.count),
                  [z.kind.name for z in sel.zones], "creature?" if creature else "-",
                  "REST" if rest else "", "verified" if card_records.is_verified(
                      res, records.get(oid)) else "")
