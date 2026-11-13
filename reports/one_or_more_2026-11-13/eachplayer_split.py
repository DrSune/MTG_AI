"""Gate round 10's MINOR-1, checked: "each player sacrifices a Bear" against a flagged "whenever
one or more other creatures leave the battlefield, you gain that much life". Run with the checkout
as the argument."""
import sys

sys.path.insert(0, sys.argv[1])
from MTG_bot.core import ability_tree as at
from MTG_bot.core.ability_tree import (ControllerRef, FAnd, FAtom, FAtomPred, FNot, QConst,
                                       TriggeredAbility, Verb, Zone, ZoneChangeEvent, ZoneKind)
from MTG_bot.core.executor.events import KIND_LIFE_GAINED
from MTG_bot.core.state import ZONE_BATTLEFIELD
from MTG_bot.core.test_executor_binding import atom, card_id
from MTG_bot.core.test_executor_one_or_more import THAT_MANY, TestOneEvent, _gain

CREATURE = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")
case = TestOneEvent()
case.setUp()
leave = ZoneChangeEvent(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
                        Zone(ZoneKind.ANY, ControllerRef.ANY),
                        subject=FAnd((CREATURE, FNot(FAtom(FAtomPred.IS_SOURCE)))))
case.ex.attach_card(case.watch, case.record_for(case.watch, [
    TriggeredAbility(leave, None, _gain(THAT_MANY), once_per_event=True)]))
bears = [case.world.add_card(card_id(f"Bear{p}", "2", "2"), p, ZONE_BATTLEFIELD)
         for p in (case.p0, case.p1)]
a_bear = at.Selector(QConst(1), at.SelectorMode.CHOOSE,
                     FAtom(FAtomPred.NAME_CONTAINS, string_value="Bear"),
                     zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),))
each = at.EachPlayer(ControllerRef.ANY, atom(Verb.SACRIFICE, target=a_bear))
from MTG_bot.core.executor.decisions import in_trigger_order
case.ex.decisions.provider = in_trigger_order  # two triggers wait: the split itself
case.ex.apply_effect(each, source=case.watch, controller=case.p0)
print("bears:", [case.world.zone_of(b).kind for b in bears])
print("gains (the rules, CR 101.4: [2]):", [e.data[0] for e in case.ex.journal.events
                 if e.kind == KIND_LIFE_GAINED and e.subject == case.p0])
