"""Phasing (CR 702.26) at the executor level, 2026-10-29.

The scenario packs (tools/scenarios/teferi_*phase*, aven_gagglemaster_*,
feline_sovereign_*) cover the printed cards end to end. These cases pin what
a pack cannot see: phasing is a status and never a zone change (702.26d), the
status is replayed state, tokens and counters stay, the permanent leaves
combat (506.4), its own abilities stop (702.26b) while effects that already
apply to it go on, and it is not summoning-sick when it phases in.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    DamageDealtEvent,
    FAnd,
    FAtom,
    FAtomPred,
    QConst,
    QUnbounded,
    ReplacementAbility,
    Selector,
    SelectorMode,
    TokenSpec,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.legality import legal_attackers
from MTG_bot.core.executor.query import legal_targets
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND, GameWorld
from MTG_bot.core.test_executor_binding import atom, card_id, gain, record_of

BF_ANY = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)
CREATURE = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")


def target_creature() -> Selector:
    return Selector(QConst(1), SelectorMode.TARGET, CREATURE, zones=(BF_ANY,))


def phase_out_target() -> object:
    return atom(Verb.PHASE_OUT, target=target_creature())


class PhasingCase(unittest.TestCase):
    def setUp(self) -> None:
        self.world = GameWorld(num_players=2, start_life=20, master_seed=26)
        self.p0, self.p1 = self.world.player_order
        self.ex = Executor(self.world)

    def creature(self, name: str, seat, abilities=()):
        cid = card_id(name, "2", "2")
        handle = self.world.add_card(cid, seat, ZONE_BATTLEFIELD)
        self.ex.attach_card(handle, record_of(list(abilities), name=name, oid=cid.oracle_id))
        return handle

    def phase_out(self, card, controller=None) -> None:
        self.ex.execute(
            phase_out_target(),
            source=card,
            controller=controller or self.p0,
            bindings={"target": [card]},
        )


class TestStatusNotZone(PhasingCase):
    def test_no_zone_change_and_the_status_is_replayed_state(self) -> None:
        bear = self.creature("Bear", self.p1)
        self.ex.begin_turn(self.p0)
        before_rows = len(self.ex.journal.events)
        before_fp = self.ex.state_fingerprint()
        self.phase_out(bear)
        self.assertEqual(self.ex.phased_out, {bear: (self.p1, None)})
        self.assertEqual(self.world.zone_of(bear).kind, ZONE_BATTLEFIELD)
        new_rows = self.ex.journal.events[before_rows:]
        self.assertFalse([r for r in new_rows if r.kind == "ZONE_CHANGE"])  # 702.26d
        self.assertNotEqual(self.ex.state_fingerprint(), before_fp)

    def test_a_token_and_its_counters_stay_through_phasing(self) -> None:
        self.ex.begin_turn(self.p0)
        self.ex.execute(
            atom(
                Verb.CREATE_TOKEN,
                tokens=TokenSpec(
                    name="Soldier",
                    type_line="Creature — Soldier",
                    types=("Creature",),
                    subtypes=("Soldier",),
                    power=QConst(1),
                    toughness=QConst(1),
                    keywords=(),
                    abilities=(),
                ),
                count=QConst(1),
            ),
            source=self.p1,
            controller=self.p1,
        )
        token = next(h for h, c in self.world.cards.items() if c.identity.is_token)
        self.world.cards[token].counters["PLUS_1_PLUS_1"] = 2
        self.phase_out(token)
        self.ex.advance_turn()  # p1's untap step: it phases in (CR 502.1)
        self.assertNotIn(token, self.ex.phased_out)
        self.assertIn(token, self.world.cards)  # 702.26d: tokens stay
        self.assertEqual(self.world.zone_of(token).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.world.cards[token].counters, {"PLUS_1_PLUS_1": 2})

    def test_it_is_not_summoning_sick_when_it_phases_in(self) -> None:
        # 702.26d: its history does not treat phasing as entering, so it has
        # been under its controller's control continuously (CR 302.6).
        bear = self.creature("Bear", self.p1)
        self.ex.begin_turn(self.p0)
        self.phase_out(bear)
        self.ex.advance_turn()
        self.assertIn(bear, legal_attackers(self.ex, self.p1))


class TestExistence(PhasingCase):
    def test_it_is_not_a_legal_target(self) -> None:
        bear = self.creature("Bear", self.p1)
        self.ex.begin_turn(self.p0)
        self.phase_out(bear)
        slot = legal_targets(
            self.world, self.ex, target_creature(), source=self.p0, controller=self.p0
        )
        self.assertNotIn(bear, slot.candidates)

    def test_its_triggered_abilities_do_not_trigger(self) -> None:
        enters = ZoneChangeEvent(
            from_zone=Zone(ZoneKind.HAND, ControllerRef.ANY),
            to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
            subject=FAnd((CREATURE, FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU))),
        )
        watcher = self.creature(
            "Watcher", self.p0, [TriggeredAbility(event=enters, condition=None, effect=gain(1))]
        )
        newcomer = self.world.add_card(card_id("Newcomer", "1", "1"), self.p0, ZONE_HAND)
        self.ex.begin_turn(self.p0)
        self.phase_out(watcher)
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    FAnd(()),
                    zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),),
                ),
                destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            ),
            source=newcomer,
            controller=self.p0,
            bindings={"cards": [newcomer]},
        )
        self.assertEqual(self.world.players[self.p0].life, 20)

    def test_its_replacement_effects_do_not_apply(self) -> None:
        # A Nine Lives-shaped replacement: "If a source would deal damage to
        # you, prevent that damage" while its permanent exists.
        ward = self.creature(
            "Ward",
            self.p0,
            [
                ReplacementAbility(
                    event=DamageDealtEvent(
                        amount=QUnbounded(),
                        filter=FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                    ),
                    condition=None,
                    action=gain(0),
                )
            ],
        )
        burn = atom(
            Verb.DEAL_DAMAGE,
            amount=QConst(3),
            target=Selector(
                QConst(1),
                SelectorMode.TARGET,
                FAnd(()),
                zones=(Zone(ZoneKind.PLAYER, ControllerRef.ANY),),
            ),
        )
        self.ex.begin_turn(self.p0)
        self.ex.execute(burn, source=self.p1, controller=self.p1, bindings={"target": [self.p0]})
        self.assertEqual(self.world.players[self.p0].life, 20)  # replaced
        self.phase_out(ward)
        self.ex.execute(burn, source=self.p1, controller=self.p1, bindings={"target": [self.p0]})
        self.assertEqual(self.world.players[self.p0].life, 17)  # 702.26b


class TestCombat(PhasingCase):
    def test_a_phased_out_blocker_leaves_the_attacker_blocked(self) -> None:
        # CR 506.4 + 509.1h: removed from combat; the attacker stays blocked
        # and, without trample, assigns no combat damage (CR 510.1c).
        attacker = self.creature("Raider", self.p0)
        blocker = self.creature("Wall", self.p1)
        self.ex.begin_turn(self.p0)
        self.ex.defending_player = self.p1
        self.ex.attackers = [attacker]
        self.ex.attacked = {attacker: self.p1}
        self.ex.blocked_by = {attacker: [blocker]}
        self.ex.phase_out([blocker])
        self.assertEqual(self.ex.blocked_by, {attacker: []})
        self.assertEqual(self.ex.attackers, [attacker])
        self.assertEqual(self.ex._assign_damage(attacker, 2, self.p0), ())

    def test_a_phased_out_attacker_leaves_combat(self) -> None:
        attacker = self.creature("Raider", self.p0)
        self.ex.begin_turn(self.p0)
        self.ex.attackers = [attacker]
        self.ex.attacked = {attacker: self.p1}
        self.ex.phase_out([attacker])
        self.assertEqual(self.ex.attackers, [])
        self.assertEqual(self.ex.attacked, {})


if __name__ == "__main__":
    unittest.main()
