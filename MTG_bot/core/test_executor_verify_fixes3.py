"""M21 verification campaign, engine fixer 3 (2026-10-29): one test class per finding.

V31  A planeswalker brought to exactly 0 loyalty is put into its owner's graveyard
     (CR 704.5i) on every path: counter removal, a loyalty cost, damage. Its loyalty
     counters cease to exist when it leaves the battlefield (CR 122.2), so a re-entry
     starts from the printed loyalty (CR 306.5b).
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


if __name__ == "__main__":
    unittest.main()
