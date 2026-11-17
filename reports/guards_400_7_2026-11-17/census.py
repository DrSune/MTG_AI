"""Census for the five open 400.7 cases, over the 19 sets' compiled trees (records applied),
with each card's verified flag.

    census.py <checkout>
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.compiler import card_records  # noqa: E402
from MTG_bot.core.compiler.compiler import compile_pool  # noqa: E402
from MTG_bot.core.compiler.coverage import build_full_registry  # noqa: E402
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402
from MTG_bot.core.errors import StateCorruptionError  # noqa: E402

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
registry = build_full_registry()
rows: dict[str, list[str]] = {}


def add(fact, code, name, verified):
    rows.setdefault(fact, []).append(f"{code} {name}{'' if verified else ' (unverified)'}")


def zone_kinds(sel):
    return {z.kind for z in (getattr(sel, "zones", None) or ())}


for code in SETS:
    raw = ingest_pool(ROOT / "MTG_bot" / "data" / f"{code}.json")
    records = card_records.load_records(code)
    for oid, rc in raw.items():
        if rc.is_token or rc.is_emblem:
            continue
        try:
            res = compile_pool({oid: rc}, registry, records=records, require_verified=False).results[oid]
        except (StateCorruptionError, ValueError):
            continue
        if res.card is None:
            continue
        card = res.card
        name = rc.identity.name
        verified = card_records.is_verified(res, records.get(oid))
        nodes = list(at.walk(card))
        for n in nodes:
            if isinstance(n, at.FAtom) and n.pred is at.FAtomPred.CAST_THIS_TURN_FROM:
                add("CAST_THIS_TURN_FROM", code, name, verified)
            if isinstance(n, at.FAtom) and n.pred is at.FAtomPred.IS_EXILED_WITH_SOURCE:
                add("IS_EXILED_WITH_SOURCE", code, name, verified)
            if isinstance(n, at.TriggeredAbility):
                ev = n.event
                if isinstance(ev, at.CounterPlacedEvent):
                    add("trigger:CounterPlaced", code, name, verified)
                left = None
                if isinstance(ev, at.CreatureDiesEvent):
                    left = ev.filter
                elif isinstance(ev, at.ZoneChangeEvent) and ev.from_zone.kind is at.ZoneKind.BATTLEFIELD:
                    left = ev.subject
                if left is not None and any(
                    isinstance(m, at.FAtom) and m.pred is at.FAtomPred.IS_ATTACHED_TO_SOURCE
                    for m in at.walk(left)
                ):
                    add("leaves-trigger on the attached object", code, name, verified)
            if isinstance(n, at.Atom) and n.verb is at.Verb.MOVE_ZONE:
                dest = n.args.get("destination")
                if isinstance(dest, at.Zone) and dest.kind is at.ZoneKind.BATTLEFIELD:
                    sel = n.args.get("cards") or n.args.get("target")
                    src = zone_kinds(sel) if sel is not None else set()
                    add("put onto the battlefield from " + "/".join(sorted(k.name for k in src)), code, name, verified)
        if rc.identity.loyalty is not None:
            add("planeswalker", code, name, verified)
for fact in sorted(rows):
    print(f"{fact} ({len(rows[fact])}): {', '.join(sorted(rows[fact]))}")
