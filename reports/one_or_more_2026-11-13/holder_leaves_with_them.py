"""Gate round 10's MINOR-2, checked: one DESTROY of the Watchdog, which holds a flagged "whenever one
or more other creatures you control leave the battlefield, you gain that much life", and three
Bears. CR 603.10a looks back: one trigger, counting 3. Run with the checkout as the argument."""
import sys

sys.path.insert(0, sys.argv[1])
from MTG_bot.core import ability_tree as at
from MTG_bot.core.ability_tree import (ControllerRef, FAnd, FAtom, FAtomPred, FNot, QUnbounded,
                                       TriggeredAbility, Verb, Zone, ZoneChangeEvent, ZoneKind)
from MTG_bot.core.executor.events import KIND_LIFE_GAINED
from MTG_bot.core.state import ZONE_BATTLEFIELD
from MTG_bot.core.test_executor_binding import atom, card_id
from MTG_bot.core.test_executor_one_or_more import THAT_MANY, YOU_ARE, TestOneEvent, _gain

CREATURE = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")
case = TestOneEvent()
case.setUp()
leave = ZoneChangeEvent(Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                        Zone(ZoneKind.ANY, ControllerRef.ANY),
                        subject=FAnd((CREATURE, YOU_ARE, FNot(FAtom(FAtomPred.IS_SOURCE)))))
case.ex.attach_card(case.watch, case.record_for(case.watch, [
    TriggeredAbility(leave, None, _gain(THAT_MANY), once_per_event=True)]))
bears = [case.world.add_card(card_id(f"Bear{i}", "2", "2"), case.p0, ZONE_BATTLEFIELD)
         for i in range(3)]
everyone = at.Selector(QUnbounded(), at.SelectorMode.ALL, CREATURE,
                       zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))
case.ex.execute(atom(Verb.DESTROY, target=everyone), source=bears[0], controller=case.p1)
print("watchdog and bears:", [case.world.zone_of(h).kind for h in [case.watch, *bears]])
print("gains (the rules: [3]):", [e.data[0] for e in case.ex.journal.events
                                  if e.kind == KIND_LIFE_GAINED and e.subject == case.p0])
