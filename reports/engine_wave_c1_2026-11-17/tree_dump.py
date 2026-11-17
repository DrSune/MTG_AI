"""Per checkout: every card of the 19 sets with its compiler tree sha, its tree with card records
applied (verified or not), whether that tree is the verified one, and the facts the engine wave
C1 changes read. Run from each checkout; diff the two JSON files with tree_diff.py.

    tree_dump.py <checkout> <out.json>

Facts (read on a card's tree with records applied):
- look-conditional: a Conditional run while a look window is open (Executor._run_effect's subject);
- cast-from: CAST_THIS_TURN_FROM (quantity: the object's own cast, CR 400.7);
- trigger-player: a triggered or delayed ability whose effect reads a designated player
  (binding's scan, now query.designated_player_refs);
- gain-control: a GAIN_CONTROL atom (its recipient, CR 800.4a);
- zone-replacement: a ReplacementAbility over a ZoneChangeEvent or a CreatureDiesEvent (now asked
  at every move);
- dies-or-move: a DESTROY, SACRIFICE, SEARCH, COUNTER_SPELL or MOVE_ZONE atom (the verb moves that
  now ask the replacements; read with zone-replacement cards in the same game only).
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
LOOKS = (at.Verb.LOOK_AT, at.Verb.REVEAL)
MOVERS = (at.Verb.DESTROY, at.Verb.SACRIFICE, at.Verb.SEARCH, at.Verb.COUNTER_SPELL, at.Verb.MOVE_ZONE)
DESIGNATED = (at.ControllerRef.TARGET_PLAYER, at.ControllerRef.TARGET_OPPONENT)


def run_order(effect):
    """The effect's atoms and Conditionals in run order (a Conditional before its branches)."""
    if isinstance(effect, at.Atom):
        yield effect
    elif isinstance(effect, at.Seq):
        for step in effect.steps:
            yield from run_order(step)
    elif isinstance(effect, at.OptionalEffect):
        yield from run_order(effect.inner)
    elif isinstance(effect, at.Conditional):
        yield effect
        yield from run_order(effect.then_effect)
        if effect.else_effect is not None:
            yield from run_order(effect.else_effect)
    elif isinstance(effect, (at.EachPlayer,)):
        yield from run_order(effect.effect)
    elif isinstance(effect, at.Repeat):
        yield from run_order(effect.inner)


def reads_designated_player(effect) -> bool:
    """Any TARGET_PLAYER / TARGET_OPPONENT anywhere in the effect (a role, a zone, a filter, an
    EachPlayer ref): the scans that changed read these."""
    text = repr(effect)
    return any(f"ControllerRef.{ref.name}" in text or f"'{ref.value}'" in text for ref in DESIGNATED)


def facts(card) -> list[str]:
    out = set()
    for n in at.walk(card):
        effect = getattr(n, "effect", None)
        if isinstance(n, (at.SpellAbility, at.TriggeredAbility, at.ActivatedAbility,
                          at.DelayedTrigger)) and effect is not None:
            prev = None
            for m in run_order(effect):
                if isinstance(m, at.Conditional) and isinstance(prev, at.Atom) and prev.verb in LOOKS:
                    out.add("look-conditional")
                if isinstance(m, at.Atom):
                    prev = m
        if isinstance(n, (at.TriggeredAbility, at.DelayedTrigger)) and effect is not None:
            if reads_designated_player(effect):
                out.add("trigger-player")
        if isinstance(n, at.FAtom) and n.pred is at.FAtomPred.CAST_THIS_TURN_FROM:
            out.add("cast-from")
        if isinstance(n, at.Atom) and n.verb is at.Verb.GAIN_CONTROL:
            out.add("gain-control")
        if isinstance(n, at.Atom) and n.verb in MOVERS:
            out.add("dies-or-move")
        if isinstance(n, at.ReplacementAbility) and isinstance(n.event, (at.ZoneChangeEvent,
                                                                          at.CreatureDiesEvent)):
            out.add("zone-replacement")
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
