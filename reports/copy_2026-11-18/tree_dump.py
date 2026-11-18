"""Per checkout: every card of the 19 sets with its compiler tree sha, its tree with card records
applied (verified or not), whether that tree is the verified one, and the facts the copy round's
engine changes read (DESIGN_ATOM_ONTOLOGY §18). Run from each checkout; diff the two JSON files
with tree_diff.py (round 13's, unchanged).

    tree_dump.py <checkout> <out.json>

Facts (read on a card's tree with records applied):
- copy-stack / copy-become / copy-token: COPY with no ``cards`` (copies.put_copies), COPY with
  ``cards`` (layer 1), CREATE_TOKEN of a CopyOf (the round's new paths);
- create-token: CREATE_TOKEN of a TokenSpec (verbs._v_create_token, its spec half moved into
  _new_spec_token);
- was-kicked: FAtomPred.WAS_KICKED (a spell copy's lane, quantity._eval_atom);
- counter: COUNTER_SPELL (a countered frame leaves through SpellStack.remove);
- cast-trigger / activation-trigger: a TriggeredAbility on a CastSpellEvent (binding._put reads
  ORDINAL) or an AbilityActivatedEvent;
- ordinal / not-result: QProp ORDINAL and FNot(IS_RESULT), the round's other two IR pieces (the
  census, census.py).
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
COPY_OF = getattr(at, "CopyOf", None)


def facts(card) -> list[str]:
    out = set()
    for n in at.walk(card):
        if isinstance(n, at.Atom):
            if n.verb is at.Verb.COPY:
                out.add("copy-become" if n.args.get("cards") is not None else "copy-stack")
            elif n.verb is at.Verb.CREATE_TOKEN:
                copied = COPY_OF is not None and isinstance(n.args.get("tokens"), COPY_OF)
                out.add("copy-token" if copied else "create-token")
            elif n.verb is at.Verb.COUNTER_SPELL:
                out.add("counter")
        if isinstance(n, at.FAtom) and n.pred is at.FAtomPred.WAS_KICKED:
            out.add("was-kicked")
        if isinstance(n, at.QProp) and n.field is getattr(at.QPropField, "ORDINAL", None):
            out.add("ordinal")
        if isinstance(n, at.FNot) and n.inner == at.FAtom(pred=at.FAtomPred.IS_RESULT):
            out.add("not-result")
        if isinstance(n, at.TriggeredAbility):
            if isinstance(n.event, at.CastSpellEvent):
                out.add("cast-trigger")
            elif isinstance(n.event, at.AbilityActivatedEvent):
                out.add("activation-trigger")
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
