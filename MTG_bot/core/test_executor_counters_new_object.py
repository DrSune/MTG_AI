"""Counters belong to one object (CR 122.2, 400.7).

* Counters cease to exist when a card changes zones, onto the battlefield too: a counter an effect
  put on a card in a graveyard or in exile does not come back with it, and a planeswalker enters
  with its printed loyalty and nothing else (CR 306.5b).
* An effect that names a card in a graveyard or in exile puts counters on it there (an exile "with
  a silver counter on it"); a counter placement whose recipient has become a new object since the
  ability named it does nothing. End to end in the pack
  scavenging_ooze_that_left_the_battlefield_gets_no_counter.
"""

from __future__ import annotations

from MTG_bot.core.ability_tree import (
    ControllerRef,
    CounterKind,
    CreatureDiesEvent,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    LifeGainedEvent,
    QConst,
    Selector,
    SelectorMode,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.executor.events import KIND_COUNTER_PLACED
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_EXILE, ZONE_GRAVEYARD
from MTG_bot.core.test_executor_binding import (
    ANOTHER_CREATURE,
    ANY_ANY,
    BF_ANY,
    BF_YOU,
    IS_SOURCE,
    BindingCase,
    enter,
    gain,
    record_of,
)
from MTG_bot.core.test_executor_verbs import UNIV, atom, card_id, target_sel
from MTG_bot.core.test_executor_verify_fixes3 import FixerCase

_GY = Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY)
_EXILE = Zone(ZoneKind.EXILE, ControllerRef.ANY)
_YOU = FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)


def _counter_on_this(zones=(BF_ANY,)):
    """"put a +1/+1 counter on this creature": the compiler's self-designation."""
    this = Selector(QConst(1), SelectorMode.CHOOSE, IS_SOURCE, zones=zones)
    return atom(Verb.PUT_COUNTER, target=this, counter_kind=CounterKind.PLUS_1_PLUS_1, count=QConst(1))


class CountersStayWithTheirObject(FixerCase):
    def _put_counter(self, card, zone: Zone, kind=CounterKind.PLUS_1_PLUS_1):
        """An effect that names ``card`` in ``zone`` (a target there) and puts a counter on it."""
        self.ex.execute(
            atom(Verb.PUT_COUNTER, target=target_sel(UNIV, zone), counter_kind=kind, count=QConst(1)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [card]},
        )

    def _return(self, card):
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV, Zone(ZoneKind.ANY, ControllerRef.ANY)),
                destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.OWNER),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"cards": [card]},
        )

    def test_a_counter_put_on_a_card_in_a_graveyard_does_not_come_back_with_it(self):
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p0, ZONE_GRAVEYARD)
        self._put_counter(bear, _GY)
        self.assertEqual(dict(self.world.cards[bear].counters), {"PLUS_1_PLUS_1": 1})  # named there
        self._return(bear)
        self.assertEqual(self.world.zone_of(bear).kind, ZONE_BATTLEFIELD)
        self.assertEqual(dict(self.world.cards[bear].counters), {})  # CR 122.2: a new object

    def test_a_walker_back_from_exile_enters_with_its_printed_loyalty_only(self):
        ident = CardIdentity(oracle_id=card_id("Walky").oracle_id, name="Walky",
                             type_line="Legendary Planeswalker — Walky", loyalty="4", cmc=3)
        pw = self.world.add_card(ident, self.p0, ZONE_EXILE)
        self._put_counter(pw, _EXILE)
        self._return(pw)
        self.assertEqual(dict(self.world.cards[pw].counters), {"LOYALTY": 4})

    def test_an_exiled_card_keeps_the_counters_an_effect_put_on_it_there(self):
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p0, ZONE_EXILE)
        self._put_counter(bear, _EXILE)
        self.assertEqual(self.world.zone_of(bear).kind, ZONE_EXILE)
        self.assertEqual(dict(self.world.cards[bear].counters), {"PLUS_1_PLUS_1": 1})
        rows = [e for e in self.ex.journal.events if e.kind == KIND_COUNTER_PLACED and e.subject == bear]
        self.assertEqual(len(rows), 1)

    def test_a_counter_on_a_creature_that_dies_and_returns_is_gone(self):
        self.world.cards[self.alpha].counters["PLUS_1_PLUS_1"] = 2
        self.ex.execute(atom(Verb.DESTROY, target=target_sel()), source=self.beta, controller=self.p1,
                        bindings={"target": [self.alpha]})
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_GRAVEYARD)
        self._return(self.alpha)
        self.assertEqual(dict(self.world.cards[self.alpha].counters), {})


class ATriggersSourceIsTheObjectItWas(BindingCase):
    """The trigger lane's half (``TriggerBinder._source_gone``); the activated lane's is the pack
    scavenging_ooze_that_left_the_battlefield_gets_no_counter."""

    def _creature(self, trigger, zone=ZONE_GRAVEYARD, name="Grower"):
        card = self.world.add_card(card_id(name, "1", "1"), self.p0, zone)
        oid = self.world.cards[card].identity.oracle_id
        self.ex.binder.records[oid] = record_of([trigger], name=name, oid=oid)
        return card

    def _move(self, cards, dest):
        self.ex.execute(enter(dest), source=self.watch, controller=self.p0, bindings={"cards": cards})

    def test_a_source_that_left_and_came_back_while_its_trigger_waited_gets_no_counter(self):
        """"Whenever you gain life, put a +1/+1 counter on this creature": the creature leaves
        and comes back while the trigger waits; the new object gets nothing (CR 113.7a, 400.7)."""
        grower = self._creature(TriggeredAbility(LifeGainedEvent(_YOU), None, _counter_on_this()),
                                zone=ZONE_BATTLEFIELD)
        self.ex.attach_card(grower, self.ex.binder.records[self.world.cards[grower].identity.oracle_id])
        with self.ex.holding_priority():
            self.ex.execute(gain(2), source=self.watch, controller=self.p0)
            self._move(grower, Zone(ZoneKind.EXILE, ControllerRef.OWNER))
            self._move(grower, Zone(ZoneKind.BATTLEFIELD, ControllerRef.OWNER))
        self.ex.fire_triggers()
        self.assertEqual(self.life(self.p0), 22)
        self.assertEqual(self.world.zone_of(grower).kind, ZONE_BATTLEFIELD)
        self.assertEqual(dict(self.world.cards[grower].counters), {})

    def test_a_source_that_entered_with_the_creature_it_triggers_on_gets_its_counter(self):
        """"Whenever another creature you control enters, put a +1/+1 counter on this creature"
        (FDN Skyknight Squire), returned together with a creature whose row comes first: it sees
        that creature enter (CR 603.6a) and is the object it was then."""
        other = self.world.add_card(card_id("Other", "2", "2"), self.p0, ZONE_GRAVEYARD)  # its row first
        squire = self._creature(TriggeredAbility(
            ZoneChangeEvent(from_zone=ANY_ANY, to_zone=BF_YOU, subject=ANOTHER_CREATURE), None,
            _counter_on_this()), name="Squire")
        self._move([other, squire], BF_YOU)
        self.assertEqual(self.world.zone_of(squire).kind, ZONE_BATTLEFIELD)
        self.assertEqual(dict(self.world.cards[squire].counters), {"PLUS_1_PLUS_1": 1})

    def test_a_source_that_died_with_the_creature_it_triggers_on_gets_no_counter(self):
        """"Whenever another creature you control dies, put a +1/+1 counter on this creature",
        its self-designation over every zone: it dies first in the same event, sees the other die
        (CR 603.10a), and the card in the graveyard is a new object."""
        dies = CreatureDiesEvent(filter=FAnd((FNot(IS_SOURCE), FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
                                              _YOU)))
        grower = self._creature(TriggeredAbility(dies, None, _counter_on_this(zones=(ANY_ANY,))),
                                zone=ZONE_BATTLEFIELD)
        self.ex.attach_card(grower, self.ex.binder.records[self.world.cards[grower].identity.oracle_id])
        other = self.world.add_card(card_id("Other", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        self.ex.execute(atom(Verb.DESTROY, target=target_sel()), source=self.watch, controller=self.p1,
                        bindings={"target": [grower, other]})
        self.assertEqual(self.world.zone_of(grower).kind, ZONE_GRAVEYARD)
        self.assertEqual(dict(self.world.cards[grower].counters), {})
