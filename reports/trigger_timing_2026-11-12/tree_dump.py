"""Per checkout: every card of the 19 sets with its compiler tree sha, its tree with card records
applied (verified or not), whether that tree is the verified one, and the facts the engine
changes read. Run from each checkout; diff the two JSON files with tree_diff.py.

    tree_dump.py <checkout> <out.json>
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
FOREIGN = (*at._A_CLASSES, at.TokenSpec, at.DelayedTrigger)


def foreign_designation(card) -> bool:
    """A designation (TARGET selector or designated player) reached only through a foreign
    ability subtree of a spell's, activated or triggered ability's effect (the walkers now skip
    them)."""
    def designations(nodes):
        out = set()
        for n in nodes:
            if isinstance(n, at.Selector) and n.mode is at.SelectorMode.TARGET and n.referent is None:
                out.add(repr(n))
            elif not isinstance(n, at.Selector):
                out |= {v.name for v in at._leaf_values(n)
                        if isinstance(v, at.ControllerRef) and v in at.DESIGNATED_PLAYER_REFS}
        return out

    for top in card.abilities:
        for ab in at.walk(top):
            if isinstance(ab, (at.SpellAbility, at.ActivatedAbility, at.TriggeredAbility)) and \
                    getattr(ab, "effect", None) is not None:
                every = designations(at.walk(ab.effect))
                own = designations(n for n in at.walk(ab.effect, skip=FOREIGN) if not isinstance(n, FOREIGN))
                if every != own:
                    return True
    return False


def facts(card) -> list[str]:
    out = []
    nodes = list(at.walk(card))
    if foreign_designation(card):
        out.append("foreign-designation")
    if any(isinstance(n, at.FAtom) and n.pred is at.FAtomPred.ATTACK_AGAINST_COUNT_GE for n in nodes):
        out.append("attack-against-count")
    if any(isinstance(n, at.DelayedTrigger) for n in nodes):
        out.append("delayed-trigger")
    return out


def compiled(oid, rc, records=None):
    """The card's compile result (records applied when given, verified or not), or why the
    compiler refused it."""
    try:
        return compile_pool({oid: rc}, registry, records=records, require_verified=False).results[oid]
    except (StateCorruptionError, ValueError) as exc:
        return f"refused: {type(exc).__name__}"


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
        if not isinstance(rec, str):
            row["tree"] = card_records.tree_sha(rec.card)
            row["record"] = rec.record is not None
            row["verified"] = card_records.is_verified(rec, records.get(oid))
            row["facts"] = facts(rec.card)
            row["unparsed"] = len(rec.unparsed) + len(rec.back_face_unparsed)
        else:
            row["tree"] = rec
        rows[oid] = row
    dump[code] = rows
    print(code, len(rows), file=sys.stderr)
Path(sys.argv[2]).write_text(json.dumps(dump, indent=0, sort_keys=True))
