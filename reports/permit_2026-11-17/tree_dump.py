"""Per checkout: every card of the 19 sets with its compiler tree sha, its tree with card records
applied (verified or not), whether that tree is the verified one, and the facts the round's engine
changes read. Run from each checkout; diff the two JSON files with tree_diff.py.

    tree_dump.py <checkout> <out.json>

Facts (ontology round R13, read on a card's tree with records applied):
- permit / cast: a PERMIT atom (the new verb), a CAST atom (stack.cast_card, rewritten: targets,
  X, the cost roles, the rider);
- rider: a cast verb's `replace` role (stack.exit_zone);
- counter: a COUNTER_SPELL (the countered spell leaves through stack.exit_zone);
- pop-lane: a MOVE_ZONE with pop_order TOP (the lane now writes the `result` register);
- exile-top-selector: a MOVE_ZONE whose target or cards selector is over the top of a library (the
  other form of "exile the top card", divergence D31);
- wrapped-permission: an OptionalEffect around ADD_LAND_PLAY, GRANT_ACTIVATION or MANA_POLICY (R5-2
  v3 point 8's other permission-like atoms, still wrapped: BACKLOG);
- own-permit: a card's own static permission (flashback, CR 702.34a; Demonic Embrace; Squee).
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
PERMIT = getattr(at.Verb, "PERMIT", None)
WRAPPED = {getattr(at.Verb, n) for n in ("ADD_LAND_PLAY", "GRANT_ACTIVATION", "MANA_POLICY")
           if hasattr(at.Verb, n)}


def _top(sel: object) -> bool:
    return isinstance(sel, at.Selector) and any(
        z.kind is at.ZoneKind.LIBRARY and z.position is at.ZonePosition.TOP for z in sel.zones)


def facts(card) -> list[str]:
    out = set()
    for n in at.walk(card):
        if isinstance(n, at.Atom):
            if PERMIT is not None and n.verb is PERMIT:
                out.add("permit")
            elif n.verb is at.Verb.CAST:
                out.add("cast")
            if n.verb in (at.Verb.CAST, PERMIT) and n.args.get("replace") is not None:
                out.add("rider")
            if n.verb is at.Verb.COUNTER_SPELL:
                out.add("counter")
            if n.verb is at.Verb.MOVE_ZONE:
                if n.args.get("pop_order") == "TOP":
                    out.add("pop-lane")
                if any(_top(n.args.get(r)) for r in ("target", "cards")):
                    out.add("exile-top-selector")
        if isinstance(n, at.OptionalEffect) and isinstance(n.inner, at.Atom) and n.inner.verb in WRAPPED:
            out.add("wrapped-permission")
        if isinstance(n, at.StaticAbility) and any(
            isinstance(s, at.Atom) and s.verb is PERMIT and isinstance(s.args.get("source"), at.Selector)
            and at._filter_names_the_source(s.args.get("source").filter)
            for s in at.walk(n.effect)
        ):
            out.add("own-permit")  # a card's own permission: flashback, Demonic Embrace, Squee
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
