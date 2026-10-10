"""r22b: the three damage/draw/counter replacement consumers (wave5a fixes).

Covers the apply-pipeline lanes the suspect cohort needed:

* Fiery Emancipation — the DamageDealtEvent MODIFY idiom (the action is a
  DEAL_DAMAGE whose quantity rewrites the event's: 1 -> 3), both the
  player lane and the permanent lane, with the CONTROLLER_IS source
  filter polarity (an opponent-sourced hit is NOT tripled), the CR 616.1
  two-records-apply raise, and the player-idiom filter skipping the card
  lane (Nine Lives' "to you" never vetoes creature damage).
* The CONSUME doctrine regression (Nine Lives shape): a non-DEAL_DAMAGE
  action still consumes the event — the damage never applies, the action
  runs in the executor drain.
* Teferi's Ageless Insight — the CardDrawnEvent lane: the draw-step
  FIRST draw is never replaced (NOT_FIRST_DRAW_THIS_STEP reads the
  executor's draw-step register), a main-phase draw IS replaced, and the
  replaced draw never touches the library.
* Conclave Mentor — the CounterPlacedEvent lane: the queued 4-tuple
  carries the receiving card and the event's count, so the action's
  ``ADD(QProp(event, COUNTER_COUNT), 1)`` lands 2 counters; a different
  counter kind passes through untouched.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    QX,
    CardDrawnEvent,
    ControllerRef,
    CounterKind,
    CounterPlacedEvent,
    DamageDealtEvent,
    FAnd,
    FAtom,
    FAtomPred,
    QBin,
    QBinOp,
    QConst,
    QProp,
    QPropField,
    QUnbounded,
    ReplacementAbility,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import record_of
from MTG_bot.core.test_executor_verbs import (
    UNIV,
    atom,
    card_id,
    reset_oracle_ids,
)

ANY_ZONE = Zone(ZoneKind.ANY, ControllerRef.ANY)


def _any_target():
    return Selector(QConst(1), SelectorMode.TARGET, UNIV, ANY_ZONE)


class R22bCase(unittest.TestCase):
    """Shared rig: p0 Brute (2/3), p1 Brute-Two (2/2) and Beast (0/6)."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=11)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.ex = Executor(self.world)
        self.brute = self._card("Brute", "2", "3", self.p0)
        self.brute2 = self._card("Brute-Two", "2", "2", self.p1)
        self.beast = self._card("Beast", "0", "6", self.p1)

    # ------------------------------------------------------------- helpers

    def _card(self, name, p, t, seat):
        return self.world.add_card(card_id(name, p, t), seat, ZONE_BATTLEFIELD)

    def _attach(self, handle, ability):
        self.ex.attach_card(
            handle,
            record_of(
                [ability],
                name=self.world.cards[handle].identity.name,
                oid=self.world.cards[handle].identity.oracle_id,
            ),
        )

    def _damage(self, dealer, victim, amount, controller):
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, amount=QConst(amount), target=_any_target()),
            source=dealer,
            controller=controller,
            bindings={"target": victim},
        )

    def _rows(self, kind):
        return [e for e in self.ex.events if len(e) > 1 and e[1] == kind]

    def _hand(self, seat):
        return sum(
            1
            for h in self.world.cards
            if self.world.zone_of(h).kind == ZONE_HAND
            and self.world.controller_of(h) == seat
        )

    def _library(self, seat):
        return [
            h
            for h in sorted(self.world.cards)
            if self.world.zone_of(h).kind == ZONE_LIBRARY
            and self.world.controller_of(h) == seat
        ]

    def _fiery(self, seat, name="Fiery"):
        """The golden Fiery Emancipation node-for-node: QX amount,
        universal subject filter, CONTROLLER_IS(YOU) over the SOURCE; the
        action DEAL_DAMAGE triples QProp(event, AMOUNT)."""
        handle = self._card(name, None, None, seat)
        self._attach(
            handle,
            ReplacementAbility(
                event=DamageDealtEvent(
                    amount=QX(),
                    filter=FAnd(()),
                    source=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                ),
                condition=None,
                action=atom(
                    Verb.DEAL_DAMAGE,
                    amount=QBin(
                        QBinOp.MUL,
                        QConst(3),
                        QProp("event", QPropField.AMOUNT),
                    ),
                    target=Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        UNIV,
                        ANY_ZONE,
                        referent="event",
                    ),
                ),
            ),
        )
        return handle

    def _teferi(self, seat):
        handle = self._card("Teferi", None, None, seat)
        self._attach(
            handle,
            ReplacementAbility(
                event=CardDrawnEvent(actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)),
                condition=FAtom(
                    pred=FAtomPred.NOT_FIRST_DRAW_THIS_STEP,
                    who=ControllerRef.YOU,
                ),
                action=atom(Verb.DRAW, amount=QConst(2), controller=ControllerRef.YOU),
            ),
        )
        return handle

    def _mentor(self, seat):
        handle = self._card("Mentor", None, None, seat)
        self._attach(
            handle,
            ReplacementAbility(
                event=CounterPlacedEvent(
                    counter_kind=CounterKind.PLUS_1_PLUS_1,
                    filter=FAnd(()),
                ),
                condition=None,
                action=atom(
                    Verb.PUT_COUNTER,
                    counter_kind=CounterKind.PLUS_1_PLUS_1,
                    count=QBin(
                        QBinOp.ADD,
                        QProp("event", QPropField.COUNTER_COUNT),
                        QConst(1),
                    ),
                    target=Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        UNIV,
                        ANY_ZONE,
                        referent="event",
                    ),
                ),
            ),
        )
        return handle


class TestFieryDamageModify(R22bCase):
    def test_player_lane_triples(self):
        self._fiery(self.p0)
        self._damage(self.brute, self.p1, 2, self.p0)
        self.assertEqual(self.world.players[self.p1].life, 14)  # 20 - 6
        rows = self._rows("DAMAGE_MODIFIED")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][4:6], (2, 6))

    def test_card_lane_triples(self):
        self._fiery(self.p0)
        self._damage(self.brute, self.beast, 1, self.p0)
        self.assertEqual(self.ex.damage[self.beast], 3)
        self.assertEqual(len(self._rows("DAMAGE_MODIFIED")), 1)

    def test_opponent_sourced_player_hit_not_tripled(self):
        self._fiery(self.p0)
        self._damage(self.brute2, self.p0, 2, self.p1)
        self.assertEqual(self.world.players[self.p0].life, 18)

    def test_opponent_sourced_card_hit_not_tripled(self):
        self._fiery(self.p0)
        self._damage(self.brute2, self.brute, 2, self.p1)
        self.assertEqual(self.ex.damage[self.brute], 2)
        self.assertEqual(self.world.zone_of(self.brute).kind, ZONE_BATTLEFIELD)

    def test_two_records_raise_cr_616_1(self):
        self._fiery(self.p0, "Fiery")
        self._fiery(self.p0, "Fiery Two")
        with self.assertRaises(NotImplementedError):
            self._damage(self.brute, self.p1, 2, self.p0)
        # loud means LOUD: the event was not applied at all
        self.assertEqual(self.world.players[self.p1].life, 20)

    def test_player_idiom_filter_skips_card_lane(self):
        # A Nine-Lives-shaped 'to you' filter (CONTROLLER_IS over the
        # PLAYER-idiom subject) must never consult into the card lane:
        # creature damage passes through untouched.
        handle = self._card("Lives", None, None, self.p0)
        self._attach(
            handle,
            ReplacementAbility(
                event=DamageDealtEvent(
                    amount=QUnbounded(),
                    filter=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                ),
                condition=None,
                action=atom(
                    Verb.GAIN_LIFE, amount=QConst(1), controller=ControllerRef.YOU
                ),
            ),
        )
        self._damage(self.brute2, self.beast, 2, self.p1)
        self.assertEqual(self.ex.damage[self.beast], 2)
        self.assertEqual(self._rows("DAMAGE_REPLACED"), [])


class TestConsumeDoctrine(R22bCase):
    def test_non_damage_action_consumes_the_event(self):
        # The Nine Lives doctrine keeps working after the r22b rewrite: a
        # record whose action is NOT a DEAL_DAMAGE consumes the damage —
        # the life total never moves, the action runs in the drain.
        handle = self._card("Guardian", None, None, self.p0)
        self._attach(
            handle,
            ReplacementAbility(
                event=DamageDealtEvent(
                    amount=QUnbounded(),
                    filter=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                ),
                condition=None,
                action=atom(
                    Verb.GAIN_LIFE, amount=QConst(1), controller=ControllerRef.YOU
                ),
            ),
        )
        self._damage(self.brute, self.p1, 2, self.p0)  # p1 = record's seat
        # The filter names the record's controller (p0), so only p0's
        # damage is consumed:
        self.assertEqual(self.world.players[self.p1].life, 18)
        self._damage(self.brute, self.p0, 2, self.p0)
        self.assertEqual(self.world.players[self.p0].life, 21)  # 20 - 0 + 1
        self.assertEqual(len(self._rows("DAMAGE_REPLACED")), 1)


class TestTeferiDrawLane(R22bCase):
    def _stock(self):
        for name in ("Lib-A", "Lib-B", "Lib-C"):
            self.world.add_card(card_id(name), self.p0, ZONE_LIBRARY)

    def test_draw_step_first_draw_not_replaced(self):
        self._teferi(self.p0)
        self._stock()
        hand_before = self._hand(self.p0)
        self.ex.begin_turn(self.p0)
        self.assertEqual(self._hand(self.p0), hand_before + 1)
        self.assertEqual(len(self._library(self.p0)), 2)
        self.assertEqual(self._rows("DRAW_REPLACED"), [])

    def test_main_phase_draw_is_replaced(self):
        self._teferi(self.p0)
        self._stock()
        self.ex.begin_turn(self.p0)
        hand_before, lib_before = self._hand(self.p0), len(self._library(self.p0))
        self.ex.execute(
            atom(Verb.DRAW, amount=QConst(1), controller=ControllerRef.YOU),
            source=self.p0,
            controller=self.p0,
        )
        # the one draw became two; the library lost exactly two, the
        # replaced draw itself never pulled a card (CR 614.3a)
        self.assertEqual(self._hand(self.p0), hand_before + 2)
        self.assertEqual(len(self._library(self.p0)), lib_before - 2)
        self.assertEqual(len(self._rows("DRAW_REPLACED")), 1)

    def test_no_replacement_without_teféri(self):
        self._stock()
        self.ex.begin_turn(self.p0)
        lib_before = len(self._library(self.p0))
        self.ex.execute(
            atom(Verb.DRAW, amount=QConst(1), controller=ControllerRef.YOU),
            source=self.p0,
            controller=self.p0,
        )
        self.assertEqual(len(self._library(self.p0)), lib_before - 1)
        self.assertEqual(self._rows("DRAW_REPLACED"), [])


class TestConclaveCounterLane(R22bCase):
    def _place(self, kind, n, target):
        self.ex.execute(
            atom(
                Verb.PUT_COUNTER,
                counter_kind=kind,
                count=QConst(n),
                target=_any_target(),
            ),
            source=self.brute,
            controller=self.p0,
            bindings={"target": target},
        )

    def test_plus_one_becomes_two_through_the_drain(self):
        self._mentor(self.p0)
        wolf = self._card("Alpha", "2", "2", self.p0)
        self._place(CounterKind.PLUS_1_PLUS_1, 1, wolf)
        counters = self.world.cards[wolf].counters
        self.assertEqual(counters.get("PLUS_1_PLUS_1"), 2)
        self.assertEqual(len(self._rows("COUNTER_REPLACED")), 1)

    def test_other_counter_kind_passes_through(self):
        self._mentor(self.p0)
        wolf = self._card("Alpha", "2", "2", self.p0)
        self._place(CounterKind.CHARGE, 1, wolf)
        counters = self.world.cards[wolf].counters
        self.assertEqual(counters.get("CHARGE"), 1)
        self.assertEqual(self._rows("COUNTER_REPLACED"), [])


if __name__ == "__main__":
    unittest.main()
