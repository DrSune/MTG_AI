"""Review residuals, over the 19 sets with card records applied (verified or not):
(a) an effect that designates, with a referent-less non-TARGET Selector in an atom's ``target``
    role (role_handles' binding-first lane), split by whether the designation can be empty;
(b) a skippable atom (actor = referent Selector or TARGET_PLAYER/TARGET_OPPONENT) followed in its
    Seq by a ``result`` reader or a Conditional.

    review_residuals.py <checkout>
"""
from __future__ import annotations

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
from MTG_bot.core.executor.query import designates  # noqa: E402

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
FOREIGN = (*at._A_CLASSES, at.TokenSpec, at.DelayedTrigger)
ABILITIES = (at.SpellAbility, at.ActivatedAbility, at.TriggeredAbility, at.DelayedTrigger)


def own(effect):
    return [n for n in at.walk(effect, skip=FOREIGN) if not isinstance(n, FOREIGN)]


def skippable(node) -> bool:
    if not isinstance(node, at.Atom):
        return False
    actor = node.args.get("controller")
    return (isinstance(actor, at.Selector) and actor.referent is not None) or (
        isinstance(actor, at.ControllerRef) and actor in at.DESIGNATED_PLAYER_REFS)


def reads_result(node) -> bool:
    return any(isinstance(n, at.Conditional) or (isinstance(n, at.Selector) and n.referent == "result")
               for n in own(node))


registry = build_full_registry()
hits_a: list[str] = []
hits_b: list[str] = []
for code in SETS:
    raw = ingest_pool(ROOT / "MTG_bot" / "data" / f"{code}.json")
    records = card_records.load_records(code)
    for oid, rc in raw.items():
        if rc.is_token or rc.is_emblem:
            continue
        try:
            res = compile_pool({oid: rc}, registry, records=records, require_verified=False).results[oid]
        except Exception:  # noqa: BLE001 - a refused card runs nothing
            continue
        tag = f"{code} {rc.identity.name}" + (" (verified)" if card_records.is_verified(res, records.get(oid)) else "")
        for top in res.card.abilities:
            for ab in at.walk(top):
                if not isinstance(ab, ABILITIES) or getattr(ab, "effect", None) is None:
                    continue
                nodes = own(ab.effect)
                if designates(ab.effect):
                    slots = [n for n in nodes if isinstance(n, at.Selector) and n.mode is at.SelectorMode.TARGET
                             and n.referent is None]
                    player = any(v in at.DESIGNATED_PLAYER_REFS for n in nodes if not isinstance(n, at.Selector)
                                 for v in at._leaf_values(n))
                    can_be_empty = not player and bool(slots) and all(isinstance(s.count, at.QAtMost) for s in slots)
                    for n in nodes:
                        if isinstance(n, at.Atom):
                            v = n.args.get("target")
                            if (isinstance(v, at.Selector) and v.mode is not at.SelectorMode.TARGET
                                    and v.referent is None):
                                hits_a.append(f"{tag} [{type(ab).__name__}] {n.verb.name} {v.mode.name}"
                                              f" designation-can-be-empty={can_be_empty}")
                for n in nodes:
                    if isinstance(n, at.Seq):
                        for i, step in enumerate(n.steps):
                            if skippable(step) and any(reads_result(later) for later in n.steps[i + 1:]):
                                hits_b.append(f"{tag} [{type(ab).__name__}] {step.verb.name} then a result reader")
print(f"== (a) non-TARGET referent-less Selector in role target, in an effect that designates: {len(set(hits_a))}")
for row in sorted(set(hits_a)):
    print("  ", row)
print(f"== (b) a skippable atom followed by a result reader or Conditional: {len(set(hits_b))}")
for row in sorted(set(hits_b)):
    print("  ", row)
