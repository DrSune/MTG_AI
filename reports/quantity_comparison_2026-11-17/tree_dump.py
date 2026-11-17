"""Per checkout: every card of the 19 sets with its compiler tree sha, its tree with card records
applied (verified or not), whether that tree is the verified one (and whether by a reprint stamp),
and the facts ontology round R12 changes the reading of. Run from each checkout; diff the two
JSON files with tree_diff.py.

    tree_dump.py <checkout> <out.json>

Facts (read on a card's tree with records applied): "comparison" (the one quantity comparison or
an old threshold predicate), "targets" (TARGETS, or the old TARGETS_SOURCE), "distinct" (QDistinct
or the old QDistinctColorCount).
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
COMPARISON = {"QTY_GE", "POWER_GE", "POWER_LE", "CMC_GE", "CMC_LE", "PT_GE", "PT_LE", "COLOR_COUNT_GE",
              "CONTROLLER_COUNT_GE", "CONTROLLER_COUNT_GT", "CONTROLLER_COUNT_LE", "ZONE_COUNT_GE",
              "LIFE_TOTAL_GE", "LIFE_LEAD_OVER_START_GE", "NAME_PARTITION_COUNT_GE"}


def facts(card) -> list[str]:
    out = set()
    for n in at.walk(card):
        if isinstance(n, at.FAtom):
            if n.pred.name in COMPARISON:
                out.add("comparison")
            elif n.pred.name in ("TARGETS", "TARGETS_SOURCE"):
                out.add("targets")
        if type(n).__name__ in ("QDistinct", "QDistinctColorCount"):
            out.add("distinct")
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
            row["reprint"] = bool(((records.get(oid) or {}).get("verified") or {}).get("reprint_of"))
            row["facts"] = facts(rec.card)
            row["unparsed"] = len(rec.unparsed) + len(rec.back_face_unparsed)
            row["needs_atom"] = bool(records.get(oid, {}).get("needs_atom"))
        else:
            row["tree"] = rec
        rows[oid] = row
    dump[code] = rows
    print(code, len(rows), file=sys.stderr)
Path(sys.argv[2]).write_text(json.dumps(dump, indent=0, sort_keys=True))
