"""Survey of the 19 sets (records applied):
- triggers whose designated-player reads differ between binding's own scan and the query lanes'
  shared predicate (query._designated_player_refs per role + _rotation_player_refs per node); run
  on the base (main 30736aba), where the trigger lane still had its own scan;
- Conditionals reached while a look window is open (the last atom before them a LOOK_AT/REVEAL),
  with their predicate.

    survey_triggers.py <checkout>
"""
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
from MTG_bot.core.executor import query
from MTG_bot.core.executor.binding import TriggerBinder

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
registry = build_full_registry()
LOOKS = (at.Verb.LOOK_AT, at.Verb.REVEAL)


def shared_refs(effect):
    refs = set()
    for inner in at.own_nodes(effect):
        refs |= query._rotation_player_refs(inner)
        if isinstance(inner, at.Atom):
            for _role, value in inner.args.pairs:
                refs |= query._designated_player_refs(value)
    return refs


def linear(effect):
    """The effect's nodes in run order (atoms and Conditionals), descending into Seq, Optional,
    Conditional (then, else) and EachPlayer; a Conditional is yielded before its branches."""
    if isinstance(effect, at.Atom):
        yield effect
    elif isinstance(effect, at.Seq):
        for s in effect.steps:
            yield from linear(s)
    elif isinstance(effect, at.OptionalEffect):
        yield from linear(effect.inner)
    elif isinstance(effect, at.Conditional):
        yield effect
        yield from linear(effect.then_effect)
        if effect.else_effect is not None:
            yield from linear(effect.else_effect)
    elif isinstance(effect, at.EachPlayer):
        yield from linear(effect.effect)
    elif isinstance(effect, at.Repeat):
        yield from linear(effect.inner)


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
        ver = "VERIFIED" if card_records.is_verified(res, records.get(oid)) else "-"
        name = rc.identity.name
        for n in at.walk(res.card):
            if isinstance(n, (at.TriggeredAbility, at.DelayedTrigger)) and n.effect is not None:
                own = TriggerBinder._designated_player_refs(n.effect)
                shared = shared_refs(n.effect)
                if own != shared:
                    print("TRIGGER_REFS_DIFFER", code, "|", name, "|", ver, "| binding:", sorted(r.name for r in own),
                          "| shared:", sorted(r.name for r in shared))
            effect = getattr(n, "effect", None)
            if isinstance(n, (at.SpellAbility, at.TriggeredAbility, at.ActivatedAbility, at.DelayedTrigger)) and effect is not None:
                prev = None
                for m in linear(effect):
                    if isinstance(m, at.Conditional) and isinstance(prev, at.Atom) and prev.verb in LOOKS:
                        print("COND_IN_LOOK_WINDOW", code, "|", name, "|", ver, "| pred:", repr(m.pred)[:140])
                    if isinstance(m, at.Atom):
                        prev = m
