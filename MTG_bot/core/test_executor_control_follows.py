"""A permanent's own abilities read "you" as its controller NOW (CR 109.5, 611.3a).

Its static, keyword and replacement abilities register records when it enters the battlefield:
layer records, prevention and replacement records, and the P/T entries a static materializes.
A control change (GAIN_CONTROL, and the change back when that effect ends) is the one event that
changes a battlefield permanent's controller without a re-entry, so ``Executor._recompute_control``
moves those records to the new controller, keeping their timestamps (CR 613.7). Records a resolved
spell or ability made keep the controller they resolved under (CR 611.2c).

The trees are the compiled ones: the "creatures you control" anthem (template
B4-modify-pt-static-you), M20 Blightbeetle, M21 Conclave Mentor, Azusa and Predatory Wurm.
"""

from __future__ import annotations

from MTG_bot.core.ability_tree import (
    ControllerRef,
    CounterKind,
    CounterPlacedEvent,
    DeclareBlockersEvent,
    DurationEot,
    DurationWhileCondition,
    FAnd,
    FAtom,
    FAtomPred,
    OptionalEffect,
    PtDelta,
    PtDirection,
    QAtLeast,
    QBin,
    QBinOp,
    QConst,
    QProp,
    QPropField,
    QUnbounded,
    ReplacementAbility,
    Selector,
    SelectorMode,
    StaticAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_EXILE
from MTG_bot.core.test_executor_layers import (
    BF_ANY,
    CREATURE,
    LayerCase,
    atom,
    card_id,
    target_sel,
)

OPPONENTS = FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT)
YOURS = FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
PLUS_ONE = PtDelta(PtDirection.INCREASE, QConst(1))
PLUS_TWO = PtDelta(PtDirection.INCREASE, QConst(2))


def anthem() -> StaticAbility:
    """"Creatures you control get +1/+1." as the compiler emits it."""
    yours = Selector(QUnbounded(), SelectorMode.ALL, FAnd((YOURS, CREATURE)), zones=(BF_ANY,))
    return StaticAbility(
        effect=atom(Verb.MODIFY_PT, target=yours, power=PLUS_ONE, toughness=PLUS_ONE)
    )


def blightbeetle_static() -> StaticAbility:
    """M20 Blightbeetle: "Creatures your opponents control can't have +1/+1 counters put on
    them.\""""
    theirs = FAnd((OPPONENTS, CREATURE))
    return StaticAbility(
        effect=atom(
            Verb.PREVENT_EFFECT,
            condition=theirs,
            event=CounterPlacedEvent(counter_kind=CounterKind.PLUS_1_PLUS_1, filter=theirs),
        )
    )


def conclave_mentor_replacement() -> ReplacementAbility:
    """M21 Conclave Mentor: "If one or more +1/+1 counters would be put on a creature you
    control, that many plus one +1/+1 counters are put on that creature instead.\""""
    return ReplacementAbility(
        event=CounterPlacedEvent(
            counter_kind=CounterKind.PLUS_1_PLUS_1,
            filter=FAnd((YOURS, CREATURE)),
            count=QAtLeast(1),
        ),
        condition=None,
        action=atom(
            Verb.PUT_COUNTER,
            count=QBin(QBinOp.ADD, QProp("event", QPropField.COUNTER_COUNT), QConst(1)),
            counter_kind=CounterKind.PLUS_1_PLUS_1,
            target=Selector(
                QConst(1),
                SelectorMode.CHOOSE,
                FAnd(()),
                zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
                referent="event",
            ),
        ),
    )


def predatory_wurm_static() -> StaticAbility:
    """M21 Predatory Wurm: "This creature gets +2/+2 as long as you control a Garruk
    planeswalker." (the WHILE rides the atom, so the ledger entry carries it too)."""
    garruk = FAnd(
        (
            YOURS,
            FAtom(FAtomPred.SUBTYPE_EQ, string_value="Garruk"),
            FAtom(FAtomPred.TYPE_EQ, string_value="Planeswalker"),
        )
    )
    itself = Selector(QConst(1), SelectorMode.CHOOSE, FAtom(FAtomPred.IS_SOURCE), zones=(BF_ANY,))
    return StaticAbility(
        effect=atom(
            Verb.MODIFY_PT,
            duration=DurationWhileCondition(filter=garruk),
            power=PLUS_TWO,
            target=itself,
            toughness=PLUS_TWO,
        )
    )


class ControlCase(LayerCase):
    """Banner (P0's) carries the ability under test; Alpha is P0's creature, Beta P1's."""

    def steal(self, permanent):
        """P1 gains control of ``permanent`` until end of turn (Act of Treason)."""
        self.ex.execute(
            atom(
                Verb.GAIN_CONTROL,
                target=target_sel(),
                controller=ControllerRef.YOU,
                duration=DurationEot(),
            ),
            source=self.beta,
            controller=self.p1,
            bindings={"target": permanent},
        )
        self.assertEqual(self.ex.controller_of(permanent), self.p1)

    def put_counter(self, creature):
        self.ex.execute(
            atom(
                Verb.PUT_COUNTER,
                target=target_sel(),
                counter_kind=CounterKind.PLUS_1_PLUS_1,
                count=QConst(1),
            ),
            source=self.beta,
            controller=self.p1,
            bindings={"target": creature},
        )
        return self.world.cards[creature].counters.get("PLUS_1_PLUS_1", 0)

    def garruk(self, seat):
        return self.world.add_card(
            card_id("Garruk", type_line="Legendary Planeswalker — Garruk"), seat, ZONE_BATTLEFIELD
        )


class TestStolenStatics(ControlCase):
    def test_a_stolen_anthem_pumps_its_new_controllers_creatures(self):
        self.attach(self.banner, [anthem()])
        self.assertEqual((self.pt(self.alpha), self.pt(self.beta)), ((3, 3), (2, 2)))
        self.steal(self.banner)
        self.assertEqual(self.pt(self.alpha), (2, 2))  # its owner's creature is not "yours" now
        self.assertEqual((self.pt(self.beta), self.pt(self.banner)), ((3, 3), (3, 3)))
        self.ex.end_turn()  # control returns (DurationEot), and the anthem with it
        self.assertEqual(self.ex.controller_of(self.banner), self.p0)
        self.assertEqual((self.pt(self.alpha), self.pt(self.beta)), ((3, 3), (2, 2)))

    def test_a_stolen_counter_prevention_bars_the_new_opponents_creatures(self):
        # M20 Blightbeetle: the red pack B11 of verification wave 1's G3 pass.
        self.attach(self.banner, [blightbeetle_static()])
        self.steal(self.banner)
        self.assertEqual(self.put_counter(self.beta), 1)  # the thief's own creature
        self.assertEqual(self.put_counter(self.alpha), 0)  # a creature of the thief's opponent

    def test_a_stolen_replacement_reads_its_new_controller(self):
        # Conclave Mentor: the extra counter goes to its controller's creatures.
        self.attach(self.banner, [conclave_mentor_replacement()])
        self.steal(self.banner)
        self.assertEqual(self.put_counter(self.beta), 2)
        self.assertEqual(self.put_counter(self.alpha), 1)

    def test_a_stolen_land_permission_is_the_thiefs(self):
        # Azusa, Lost but Seeking: "You may play two additional lands on each of your turns."
        self.attach(
            self.banner,
            [StaticAbility(effect=OptionalEffect(atom(Verb.ADD_LAND_PLAY, count=QConst(2))))],
        )
        self.steal(self.banner)
        self.assertEqual(self.ex.layers.land_play_bonus(self.p1), 2)
        self.assertEqual(self.ex.layers.land_play_bonus(self.p0), 0)

    def test_a_stolen_while_static_reads_the_thiefs_board(self):
        # Predatory Wurm: its owner controls a Garruk, the thief does not.
        self.garruk(self.p0)
        self.attach(self.banner, [predatory_wurm_static()])
        self.assertEqual(self.pt(self.banner), (4, 4))
        self.steal(self.banner)
        self.assertEqual(self.pt(self.banner), (2, 2))

    def test_a_materialized_while_entry_follows_too(self):
        # Both players control a Garruk, so the Wurm keeps +2/+2 through the steal on the entry
        # materialized under P0. Then P0's Garruk leaves: the Wurm's controller, P1, still
        # controls one, so it keeps the bonus (the entry's WHILE is judged as P1's).
        mine = self.garruk(self.p0)
        self.garruk(self.p1)
        self.attach(self.banner, [predatory_wurm_static()])
        self.steal(self.banner)
        self.settle()
        self.assertEqual(self.pt(self.banner), (4, 4))
        self.world.move_to_zone(mine, self.p0, ZONE_EXILE)
        self.settle()
        self.assertEqual(self.pt(self.banner), (4, 4))


class TestAuraControl(ControlCase):
    """M21 Enthralling Hold's "You control enchanted creature." is the Aura's own static ability,
    compiled onto its spell as a control entry anchored to the Aura: its "you" is the Aura's
    controller now (found by the fresh-eyes review of this fix)."""

    def hold_on_beta(self):
        hold = self.world.add_card(
            card_id("Hold", type_line="Enchantment — Aura"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex.attach_aura(hold, self.beta)
        enchanted = Selector(
            QUnbounded(),
            SelectorMode.ALL,
            FAnd((FAtom(FAtomPred.IS_ATTACHED_TO_SOURCE), CREATURE)),
            zones=(BF_ANY,),
        )
        self.ex.execute(
            atom(Verb.GAIN_CONTROL, controller=ControllerRef.YOU, target=enchanted),
            source=hold,
            controller=self.p0,
        )
        self.assertEqual(self.ex.controller_of(self.beta), self.p0)
        return hold

    def test_stealing_the_aura_takes_the_creature_with_it(self):
        hold = self.hold_on_beta()
        self.steal(hold)
        self.assertEqual(self.ex.controller_of(self.beta), self.p1)
        self.ex.end_turn()  # the Aura returns to P0, and the creature with it
        self.assertEqual(self.ex.controller_of(hold), self.p0)
        self.assertEqual(self.ex.controller_of(self.beta), self.p0)

    def test_a_resolved_steal_stays_with_its_controller(self):
        # CR 611.2c: control a resolved ability gave (Sorin, Vampire Lord's granted "{T}: Gain
        # control of target creature") is not the source's ability: it stays when the source is
        # stolen.
        self.ex.execute(
            atom(Verb.GAIN_CONTROL, target=target_sel(), controller=ControllerRef.YOU),
            source=self.banner,
            controller=self.p0,
            bindings={"target": self.beta},
        )
        self.steal(self.banner)
        self.assertEqual(self.ex.controller_of(self.beta), self.p0)


class TestResolvedEffectsKeepTheirController(ControlCase):
    def test_a_resolved_prevention_keeps_the_controller_it_resolved_under(self):
        # CR 611.2c: "Creatures your opponents control can't block this turn", made by an
        # ability of Banner while P0 controlled it, still means P0's opponents after P1 takes
        # Banner.
        theirs = FAnd((OPPONENTS, CREATURE))
        cant_block = atom(
            Verb.PREVENT_EFFECT,
            condition=theirs,
            event=DeclareBlockersEvent(filter=theirs),
            duration=DurationEot(),
        )
        self.ex.execute(cant_block, source=self.banner, controller=self.p0)
        resolved = [r for r in self.ex.replacements.preventions if r.resolved]
        self.steal(self.banner)
        self.assertEqual([r.controller for r in resolved], [self.p0])
        self.assertTrue(self.ex.replacements.prevents_block_declaration(self.beta, self.alpha))


if __name__ == "__main__":  # pragma: no cover
    import unittest

    unittest.main()
