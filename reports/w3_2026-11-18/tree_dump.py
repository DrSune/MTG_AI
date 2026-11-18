"""Per checkout: every card of the 19 sets with its compiler tree sha, its tree with card records
applied (verified or not), whether that tree is the verified one, and the facts gate round W3's
engine changes read (DESIGN_ATOM_ONTOLOGY §19). Run from each checkout; diff the two JSON files
with tree_diff.py (round B3's, unchanged).

    tree_dump.py <checkout> <out.json>

Facts (read on a card's tree with records applied):
- state: a state trigger, StateTrigger (here) or the counter-placed form it replaces (main);
- extra-trigger: TRIGGER_ADDITIONAL (a static here, a trigger's effect on main);
- reveal / look / scry: REVEAL, LOOK_AT, SCRY (their event-log rows changed: verbs._look, _v_scry);
- trigger: any triggered ability (binding._queue now counts the extra-trigger statics).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__

from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.compiler import card_records  # noqa: E402
from MTG_bot.core.compiler.compiler import compile_pool  # noqa: E402
from MTG_bot.core.compiler.coverage import build_full_registry  # noqa: E402
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402
from MTG_bot.core.errors import StateCorruptionError  # noqa: E402

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
STATE = getattr(at, "StateTrigger", None)


def facts(card) -> list[str]:
    out = set()
    for n in at.walk(card):
        if isinstance(n, at.TriggeredAbility):
            out.add("trigger")
            ev = n.event
            if (STATE is not None and isinstance(ev, STATE)) or (
                isinstance(ev, at.CounterPlacedEvent)
                and any(isinstance(m, at.FAtom) and m.pred is at.FAtomPred.HAS_COUNTER
                        for m in at.walk(ev.filter))
            ):
                out.add("state")
        if isinstance(n, at.Atom):
            if n.verb is at.Verb.TRIGGER_ADDITIONAL:
                out.add("extra-trigger")
            elif n.verb is at.Verb.REVEAL:
                out.add("reveal")
            elif n.verb is at.Verb.LOOK_AT:
                out.add("look")
            elif n.verb is at.Verb.SCRY:
                out.add("scry")
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
