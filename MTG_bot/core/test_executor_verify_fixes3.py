"""M21 verification campaign, engine fixer 3 (2026-10-29): one test class per finding.

V31  A planeswalker brought to exactly 0 loyalty is put into its owner's graveyard
     (CR 704.5i) on every path: counter removal, a loyalty cost, damage. Its loyalty
     counters cease to exist when it leaves the battlefield (CR 122.2), so a re-entry
     starts from the printed loyalty (CR 306.5b).
V31b Counters on an object cease to exist when it moves to another zone (CR 122.2).
V24  Ownership never changes (CR 108.3): a moving card lands in its owner's hand,
     library, graveyard or exile whatever player the destination names (CR 400.3),
     and a permanent put onto the battlefield under another player's control is a
     control entry on the owner's zone (CR 110.2a).
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    CounterKind,
    QConst,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    GameWorld,
)
from MTG_bot.core.test_executor_verbs import (
    UNIV,
    atom,
    card_id,
    reset_oracle_ids,
    target_sel,
)


class FixerCase(unittest.TestCase):
    """p0 Alpha (2/2) and p1 Beta (1/1) on the battlefield."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=29)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.alpha = self.world.add_card(
            card_id("Alpha", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.beta = self.world.add_card(
            card_id("Beta", "1", "1"), self.p1, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)

    def walker(self, seat, loyalty="4", name="Walky"):
        ident = CardIdentity(
            oracle_id=card_id(name).oracle_id,
            name=name,
            type_line="Legendary Planeswalker — Walky",
            loyalty=loyalty,
            cmc=3,
        )
        return self.world.add_card(ident, seat, ZONE_BATTLEFIELD)


class TestV31LoyaltyZero(FixerCase):
    def remove_loyalty(self, pw, n):
        self.ex.execute(
            atom(
                Verb.REMOVE_COUNTER,
                target=target_sel(UNIV),
                counter_kind=CounterKind.LOYALTY,
                count=QConst(n),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [pw]},
        )

    def test_counter_removal_to_zero_buries_the_walker(self):
        pw = self.walker(self.p1, "5")
        self.world.cards[pw].counters["LOYALTY"] = 2  # a seeded, used walker
        self.remove_loyalty(pw, 2)
        # CR 704.5i: 0 loyalty puts it into its owner's graveyard; before V31 the
        # zeroed key was deleted and the walker read its printed 5 again.
        self.assertEqual(self.world.zone_of(pw).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.controller_of(pw), self.p1)
        self.assertEqual(dict(self.world.cards[pw].counters), {})

    def test_counter_removal_below_zero_clamps_and_buries(self):
        pw = self.walker(self.p1, "5")
        self.world.cards[pw].counters["LOYALTY"] = 1
        self.remove_loyalty(pw, 2)
        self.assertEqual(self.world.zone_of(pw).kind, ZONE_GRAVEYARD)

    def test_counter_removal_from_an_unseeded_walker_reads_the_printed_loyalty(self):
        pw = self.walker(self.p1, "5")  # the rig never seeds the ledger
        self.remove_loyalty(pw, 2)
        self.assertEqual(dict(self.world.cards[pw].counters), {"LOYALTY": 3})
        self.assertEqual(self.world.zone_of(pw).kind, ZONE_BATTLEFIELD)

    def test_counter_removal_from_a_card_without_loyalty_adds_no_key(self):
        self.remove_loyalty(self.alpha, 1)
        self.assertEqual(dict(self.world.cards[self.alpha].counters), {})
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_BATTLEFIELD)

    def test_other_counter_kinds_still_drop_a_zeroed_key(self):
        self.world.cards[self.alpha].counters["PLUS_1_PLUS_1"] = 1
        self.ex.execute(
            atom(
                Verb.REMOVE_COUNTER,
                target=target_sel(UNIV),
                counter_kind=CounterKind.PLUS_1_PLUS_1,
                count=QConst(1),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [self.alpha]},
        )
        self.assertEqual(dict(self.world.cards[self.alpha].counters), {})

    def test_loyalty_leaves_with_the_walker_and_reentry_reads_printed(self):
        pw = self.walker(self.p0, "4")
        self.world.cards[pw].counters["LOYALTY"] = 1
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV),
                destination=Zone(ZoneKind.HAND, ControllerRef.OWNER),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"cards": [pw]},
        )
        self.assertEqual(self.world.zone_of(pw).kind, ZONE_HAND)
        # CR 122.2: the counters ceased to exist; CR 306.5b: it enters again with
        # its printed loyalty (the binder seeds an absent key).
        self.assertEqual(dict(self.world.cards[pw].counters), {})
        from MTG_bot.core.executor.legality import _loyalty_of

        self.assertEqual(_loyalty_of(self.world, pw), 4)

    def test_counter_removal_on_a_walker_card_off_the_battlefield_adds_no_key(self):
        pw = self.walker(self.p0, "4")
        self.world.move_to_zone(pw, self.p0, ZONE_HAND)
        self.remove_loyalty(pw, 1)
        self.assertEqual(dict(self.world.cards[pw].counters), {})

    def test_loyalty_cost_paid_down_to_zero_buries_the_walker(self):
        from MTG_bot.core.ability_tree import Cost, CostLoyalty
        from MTG_bot.core.executor.legality import (
            build_payment_plan,
            ctx_for,
            pay_costs,
        )

        pw = self.walker(self.p0, "4")
        self.world.cards[pw].counters["LOYALTY"] = 3
        cost = Cost((CostLoyalty(delta=-3),))
        ctx = ctx_for(self.ex, source=pw, controller=self.p0)
        plan, why = build_payment_plan(self.world, ctx, cost)
        self.assertIsNone(why)
        pay_costs(self.ex, plan, source=pw, controller=self.p0)
        # CR 606.6: exactly its loyalty may be paid; CR 704.5i: then it dies.
        self.assertEqual(self.world.zone_of(pw).kind, ZONE_GRAVEYARD)
        self.assertEqual(dict(self.world.cards[pw].counters), {})


class TestV31bCountersCeaseOnZoneChange(FixerCase):
    def bounce(self, card):
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV),
                destination=Zone(ZoneKind.HAND, ControllerRef.OWNER),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"cards": [card]},
        )

    def test_a_bounced_creature_loses_its_counters(self):
        self.world.cards[self.alpha].counters["PLUS_1_PLUS_1"] = 2
        self.bounce(self.alpha)
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_HAND)
        self.assertEqual(dict(self.world.cards[self.alpha].counters), {})

    def test_the_dies_row_still_folds_the_counters(self):
        from MTG_bot.core.executor.events import KIND_CREATURE_DIES

        self.world.cards[self.beta].counters["PLUS_1_PLUS_1"] = 1  # a 2/2 now
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(UNIV), amount=QConst(2)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [self.beta]},
        )
        self.assertEqual(self.world.zone_of(self.beta).kind, ZONE_GRAVEYARD)
        self.assertEqual(dict(self.world.cards[self.beta].counters), {})
        dies = [e for e in self.ex.journal.events if e.kind == KIND_CREATURE_DIES]
        self.assertEqual(len(dies), 1)
        # (from, owner, type line, was power, was toughness): it died a 2/2.
        self.assertEqual(dies[0].dies[3:], (2, 2))

    def test_counters_on_a_card_entering_the_battlefield_are_kept(self):
        card = self.world.add_card(card_id("Ent", "1", "1"), self.p0, ZONE_HAND)
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV),
                destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            ),
            source=card,
            controller=self.p0,
            bindings={"cards": [card]},
        )
        self.world.cards[card].counters["PLUS_1_PLUS_1"] = 1
        self.assertEqual(self.world.zone_of(card).kind, ZONE_BATTLEFIELD)
        self.assertEqual(dict(self.world.cards[card].counters), {"PLUS_1_PLUS_1": 1})


class TestV24OwnershipNeverChanges(FixerCase):
    def setUp(self):
        super().setUp()
        self.corpse = self.world.add_card(
            card_id("Corpse", "2", "2"), self.p1, ZONE_GRAVEYARD
        )

    def move(self, card, dest, controller, zone=None):
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV, zone or Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)),
                destination=dest,
            ),
            source=self.alpha,
            controller=controller,
            bindings={"cards": [card]},
        )

    def test_owners_hand_written_as_any_is_the_owners_hand(self):
        # B-43 (Barrin, Niambi, Roaming Ghostlight): Zone(HAND, ANY) went to seat 0.
        self.move(self.beta, Zone(ZoneKind.HAND, ControllerRef.ANY), self.p0)
        self.assertEqual(self.world.zone_of(self.beta).kind, ZONE_HAND)
        self.assertEqual(self.world.controller_of(self.beta), self.p1)

    def test_seat_one_bouncing_its_own_creature_keeps_it(self):
        self.move(self.beta, Zone(ZoneKind.HAND, ControllerRef.ANY), self.p1)
        self.assertEqual(self.world.controller_of(self.beta), self.p1)

    def test_a_hand_named_as_yours_is_still_the_owners_hand(self):
        # CR 400.3: an object that would go to a hand other than its owner's goes to
        # its owner's.
        self.move(self.beta, Zone(ZoneKind.HAND, ControllerRef.YOU), self.p0)
        self.assertEqual(self.world.controller_of(self.beta), self.p1)

    def test_under_your_control_is_a_control_entry_and_death_returns_it_home(self):
        self.move(
            self.corpse,
            Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            self.p0,
            zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY),
        )
        self.assertEqual(self.world.zone_of(self.corpse).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.world.controller_of(self.corpse), self.p1)  # owner
        self.assertEqual(self.ex.controller_of(self.corpse), self.p0)  # controller
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(UNIV), amount=QConst(2)),
            source=self.beta,
            controller=self.p1,
            bindings={"target": [self.corpse]},
        )
        # It dies into its OWNER's graveyard and the control entry ends with it.
        self.assertEqual(self.world.zone_of(self.corpse).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.controller_of(self.corpse), self.p1)
        self.assertEqual(self.ex.control_entries, [])

    def test_return_to_the_battlefield_without_a_controller_is_the_instructed_player(self):
        # CR 110.2a: Zone(BATTLEFIELD, ANY) ("return ... to the battlefield") puts it
        # under the effect's controller; it used to land on seat 0's battlefield.
        self.move(
            self.corpse,
            Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
            self.p1,
            zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY),
        )
        self.assertEqual(self.world.controller_of(self.corpse), self.p1)
        self.assertEqual(self.ex.controller_of(self.corpse), self.p1)
        self.assertEqual(self.ex.control_entries, [])

    def test_owner_destination_on_the_battlefield_needs_no_entry(self):
        self.move(
            self.corpse,
            Zone(ZoneKind.BATTLEFIELD, ControllerRef.OWNER),
            self.p0,
            zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY),
        )
        self.assertEqual(self.ex.controller_of(self.corpse), self.p1)
        self.assertEqual(self.ex.control_entries, [])


class TestV24CastRefusesAnotherPlayersCard(unittest.TestCase):
    def test_cast_card_refuses_a_card_the_caster_does_not_own(self):
        from MTG_bot.core.ability_tree import Cost, SpellKind
        from MTG_bot.core.executor.stack import cast_card
        from MTG_bot.core.state import ZONE_EXILE
        from MTG_bot.core.test_executor_stack import StackCase

        case = StackCase()
        case.setUp()
        theirs = case.give("Theirs", SpellKind.SORCERY, seat=case.p1, zone=ZONE_EXILE)
        with self.assertRaises(NotImplementedError):
            cast_card(case.ex, case.p0, theirs, cost_override=Cost(()))
        self.assertEqual(case.world.zone_of(theirs).kind, ZONE_EXILE)
        self.assertEqual(case.world.controller_of(theirs), case.p1)


if __name__ == "__main__":
    unittest.main()
