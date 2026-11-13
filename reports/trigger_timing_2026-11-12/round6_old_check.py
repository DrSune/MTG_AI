"""Gate round 6, M2 and M3: the trigger-timing check of 989707d7 (before the round's fixes) on
the reverse fixtures of test_trigger_timing_scan_has_teeth. Each comes back clean there, and it
has no qualifier-slot check. Run it from a git-archive copy of 989707d7, so that it imports that
code:

    cd <copy of 989707d7> && .venv/bin/python <this file>
"""
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
import MTG_bot

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from MTG_bot.core import ability_tree as at
from tools.audit import ontology_conformance as oc

draw = at.CardDrawnEvent(actor=at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU))
tap = at.Atom(verb=at.Verb.TAP, args=at.AtomArgs(pairs=(("target", at.Selector(
    at.QConst(1), at.SelectorMode.TARGET, at.FAtom(pred=at.FAtomPred.TYPE_EQ, string_value="Creature"),
    zones=(at.Zone(kind=at.ZoneKind.BATTLEFIELD, controller=at.ControllerRef.ANY),))),)))
pay = at.OptionalEffect(inner=at.Atom(verb=at.Verb.PAY, args=at.AtomArgs(pairs=(
    ("cost", at.Cost(parts=(at.CostManaGeneric(at.QConst(1)),))),))))
gate = at.Conditional(pred=at.FAtom(pred=at.FAtomPred.MAY_DONE), then_effect=at.DelayedTrigger(
    duration=None, event=None, condition=None, effect=tap))
new = at.TriggeredAbility(event=draw, condition=None, effect=at.Seq(steps=(pay, gate)))
if_do = ("Whenever you draw a card, you may pay {1}.", "If you do, tap target creature.")
print("reflexive node, no reflexive wording:", oc.trigger_timing_faults(if_do, if_do, (new,)))
for worded in ("Each opponent may discard a card. When they do, tap target creature.",
               "When a creature is put onto the battlefield this way, it deals 2 damage to any target."):
    print(repr(worded[:40]), "with no reflexive node:", oc.trigger_timing_faults((worded,), (worded,), ()))
two = at.FAtom(pred=at.FAtomPred.CONTROLLER_COUNT_GE, count=at.QConst(2),
               inner_filter=at.FAtom(pred=at.FAtomPred.IS_ATTACKING))
read_once = at.TriggeredAbility(event=at.DeclareAttackersEvent(filter=at.FAnd(children=(
    at.FAtom(pred=at.FAtomPred.TYPE_EQ, string_value="Creature"), two))), condition=None, effect=tap,
    once_per_event=True)
raid = ("Raid — Whenever you attack, if you attacked with two or more creatures, tap target creature.",)
print("an intervening if in the event filter:", oc.trigger_timing_faults(raid, raid, (read_once,)))
print("has a qualifier-slot check:", hasattr(oc, "misplaced_qualifiers"))
