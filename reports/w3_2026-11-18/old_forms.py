"""Do the forms gate round W3 refuses validate on a checkout? Each is built from that checkout's
IR (no new names), so main 0b7f9c22 shows which the refusal tests catch there
(test_ability_tree_w3.py fails to import on main: StateTrigger, reveal_hand and reveal_result do
not exist there).

    old_forms.py <checkout>
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
from MTG_bot.core import ability_tree as at  # noqa: E402


def A(verb, **roles):
    return at.Atom(verb=verb, args=at.AtomArgs(pairs=tuple(roles.items())))


YOU = at.ControllerRef.YOU
SOURCE = at.FAtom(pred=at.FAtomPred.IS_SOURCE)
YOURS = at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=YOU)
NINE = at.FAtom(pred=at.FAtomPred.HAS_COUNTER, counter_kind=at.CounterKind.INCARNATION, count=at.QConst(9))
TOP = at.Zone(at.ZoneKind.LIBRARY, YOU, at.ZonePosition.TOP)
DRAW = A(at.Verb.DRAW, controller=YOU, amount=at.QConst(1))
SHRINES = at.at_least(6, quantity=at.number_you_control(at.FAtom(pred=at.FAtomPred.SUBTYPE_EQ, string_value="Shrine")))

FORMS = {
    "the state as a counter placement (old Nine Lives)": lambda: at.TriggeredAbility(
        event=at.CounterPlacedEvent(counter_kind=at.CounterKind.INCARNATION, filter=at.FAnd(children=(SOURCE, NINE))),
        condition=None, effect=DRAW),
    "the carrier trigger (old Sanctum of All)": lambda: at.TriggeredAbility(
        event=at.AbilityTriggerEvent(filter=at.FAnd(children=(YOURS, SHRINES))), condition=None,
        effect=A(at.Verb.TRIGGER_ADDITIONAL, count=at.QConst(1))),
    "an ability triggering as a delayed trigger's event": lambda: at.DelayedTrigger(
        duration=at.DurationEot(), event=at.AbilityTriggerEvent(filter=YOURS), condition=None, effect=DRAW),
    "an ability triggering as a prevention's event": lambda: A(
        at.Verb.PREVENT_EFFECT, condition=YOURS, event=at.AbilityTriggerEvent(filter=YOURS)),
    "TRIGGER_ADDITIONAL with no event": lambda: A(at.Verb.TRIGGER_ADDITIONAL, count=at.QConst(1)),
    "TRIGGER_ADDITIONAL with count 0": lambda: A(at.Verb.TRIGGER_ADDITIONAL, count=at.QConst(0)),
    "the hand reveal as the whole library (old Duress)": lambda: A(
        at.Verb.REVEAL, controller=at.ControllerRef.TARGET_OPPONENT, count=at.QUnbounded()),
    "a look at the whole library": lambda: A(at.Verb.LOOK_AT, controller=YOU, count=at.QUnbounded()),
    "a top-1 reveal after a look (old pick reveal)": lambda: at.Seq(steps=(
        A(at.Verb.LOOK_AT, controller=YOU, count=at.QConst(4)),
        A(at.Verb.REVEAL, controller=YOU, count=at.QConst(1)),
        A(at.Verb.MOVE_ZONE, cards=at.Selector(at.QConst(1), at.SelectorMode.ONE_OF, at.FAnd(()), zones=(TOP,)),
          destination=at.Zone(at.ZoneKind.HAND, YOU)),
    )),
    "a top-1 reveal after a search (old named tutor's \"reveal it\")": lambda: at.Seq(steps=(
        A(at.Verb.SEARCH, cards=at.Selector(at.QConst(1), at.SelectorMode.CHOOSE, at.FAnd(()),
                                            zones=(at.Zone(at.ZoneKind.GRAVEYARD, YOU),)),
          destination=at.Zone(at.ZoneKind.HAND, YOU)),
        A(at.Verb.REVEAL, controller=YOU, count=at.QConst(1)),
    )),
}
for label, build in FORMS.items():
    try:
        build()
        verdict = "VALIDATES"
    except ValueError as exc:
        verdict = f"refused: {str(exc)[:110]}"
    print(f"{label}: {verdict}")
