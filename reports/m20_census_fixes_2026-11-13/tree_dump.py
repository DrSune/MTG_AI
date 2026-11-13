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


ABILITIES = (at.SpellAbility, at.ActivatedAbility, at.TriggeredAbility, at.DelayedTrigger)


def _own(effect):
    return [n for n in at.walk(effect, skip=FOREIGN) if not isinstance(n, FOREIGN)]


def _slots(effect):
    """The designations an ability's own effect makes: TARGET selectors and designated players."""
    sels = {repr(n) for n in _own(effect)
            if isinstance(n, at.Selector) and n.mode is at.SelectorMode.TARGET and n.referent is None}
    player = any(v in at.DESIGNATED_PLAYER_REFS for n in _own(effect) if not isinstance(n, at.Selector)
                 for v in at._leaf_values(n))
    return sels, player


def facts(card) -> list[str]:
    """The engine paths this branch changes that a tree reads (item 1 player hexproof, item 2 the
    absent antecedent, item 3 per-slot designation and the designated player, item 4 the reveal
    until's partition anchors, and the any-target widening through the another-target mark)."""
    out = set()
    nodes = list(at.walk(card))
    for n in nodes:
        if isinstance(n, at.Atom) and n.verb is at.Verb.GRANT_ABILITY:
            tgt = n.args.get("target")
            if isinstance(tgt, at.Selector) and any(z.kind is at.ZoneKind.PLAYER for z in tgt.zones):
                out.add("player-grant")
            ab = n.args.get("ability")
            if isinstance(ab, at.KeywordAbility) and ab.keyword is at.Keyword.HEXPROOF:
                out.add("hexproof-grant")
        if isinstance(n, at.Atom):
            actor = n.args.get("controller")
            if isinstance(actor, at.Selector) and actor.referent is not None:
                out.add("actor-antecedent")
            if n.verb is at.Verb.REVEAL and n.args.get("until") is not None:
                out.add("reveal-until")
        if isinstance(n, at.Selector) and n.mode is at.SelectorMode.TARGET:
            f = n.filter
            if isinstance(f, at.FAnd) and any(isinstance(c, at.FAtom) and c.pred is at.FAtomPred.IS_ANY_TARGET
                                              for c in f.children):
                out.add("another-mark")
    for top in card.abilities:
        for ab in at.walk(top):
            if not isinstance(ab, ABILITIES) or getattr(ab, "effect", None) is None:
                continue
            sels, player = _slots(ab.effect)
            if len(sels) + int(player) > 1:
                out.add("multi-slot" + ("+player" if player else ""))
            if isinstance(ab, (at.SpellAbility, at.ActivatedAbility)) and any(
                    isinstance(n, at.Selector) and n.mode is at.SelectorMode.TARGET
                    and isinstance(n.count, at.QAtMost) for n in _own(ab.effect)):
                out.add("up-to-slot")
    return sorted(out)


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
