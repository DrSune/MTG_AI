"""Per checkout: every card of the 19 sets with its compiler tree sha, its tree with card records
applied (verified or not), whether that tree is the verified one, and the facts the engine
changes read. Run from each checkout; diff the two JSON files with tree_diff.py.

    tree_dump.py <checkout> <out.json>

Facts (the engine paths ontology round R10 touches, read on a card's tree with records applied):
- gathered-trigger: once_per_event on a DeclareAttackersEvent or ZoneChangeEvent (the binder's
  gathered register: every object of the event; Basri Ket's -2, Tide Skimmer);
- flagged-damage: once_per_event on a DamageDealtEvent (Feline Sovereign; its register keeps the
  one player, unchanged);
- event-selector: a Selector(referent="event") (the selector lane no longer slices it to one);
- that-many: a QProp THAT_MANY_COUNT (its trigger fallback reads the gathered register);
- object-zone-trigger: a per-object zone-change trigger over a subject that is not the source
  (G3 now offers the critical "each occurrence -> once per event" mutant on it).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__

from MTG_bot.core import ability_tree as at
from MTG_bot.core.compiler import card_records
from MTG_bot.core.compiler.compiler import compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.errors import StateCorruptionError

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
TRIGGERS = (at.TriggeredAbility, at.DelayedTrigger)


def _self_subject(subject) -> bool:
    parts = subject.children if isinstance(subject, at.FAnd) else (subject,)
    return any(isinstance(p, at.FAtom) and p.pred in (at.FAtomPred.IS_SOURCE,
                                                       at.FAtomPred.IS_ATTACHED_TO_SOURCE)
               for p in parts)


def facts(card) -> list[str]:
    out = set()
    for n in at.walk(card):
        if isinstance(n, TRIGGERS) and n.event is not None:
            if n.once_per_event and isinstance(n.event, (at.DeclareAttackersEvent, at.ZoneChangeEvent)):
                out.add("gathered-trigger")
            elif n.once_per_event:
                out.add("flagged-damage")
            elif isinstance(n.event, at.ZoneChangeEvent) and (
                    n.event.subject is None or not _self_subject(n.event.subject)):
                out.add("object-zone-trigger")
        if isinstance(n, at.Selector) and n.referent == "event":
            out.add("event-selector")
        if isinstance(n, at.QProp) and n.field is at.QPropField.THAT_MANY_COUNT:
            out.add("that-many")
    return sorted(out)


def compiled(oid, rc, records=None):
    """The card's compile result (records applied when given, verified or not), or why the
    compiler refused it."""
    try:
        return compile_pool({oid: rc}, registry, records=records, require_verified=False).results[oid]
    except (StateCorruptionError, ValueError) as exc:
        return f"refused: {type(exc).__name__}: {str(exc)[:160]}"


registry = build_full_registry()
dump: dict = {}
for code in SETS:
    raw = ingest_pool(ROOT / "MTG_bot" / "data" / f"{code}.json")
    records = card_records.load_records(code)
    rows = {}
    for oid, rc in raw.items():
        if rc.is_token or rc.is_emblem:
            continue
        comp = compiled(oid, rc)
        rec = compiled(oid, rc, records)
        row = {"name": rc.identity.name}
        row["compiler"] = card_records.tree_sha(comp.card) if not isinstance(comp, str) else comp
        if not isinstance(comp, str):
            row["compiler_unparsed"] = len(comp.unparsed) + len(comp.back_face_unparsed)
        if not isinstance(rec, str):
            row["tree"] = card_records.tree_sha(rec.card)
            row["record"] = rec.record is not None
            row["verified"] = card_records.is_verified(rec, records.get(oid))
            row["facts"] = facts(rec.card)
            row["unparsed"] = len(rec.unparsed) + len(rec.back_face_unparsed)
            row["needs_atom"] = bool(records.get(oid, {}).get("needs_atom"))
        else:
            row["tree"] = rec
        rows[oid] = row
    dump[code] = rows
    print(code, len(rows), file=sys.stderr)
Path(sys.argv[2]).write_text(json.dumps(dump, indent=0, sort_keys=True))
