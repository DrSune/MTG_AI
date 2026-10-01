"""Tests for the round-12c activation legality + cost payment layer
(/06 §12c, executor/legality.py).

Pins: the CR 117.3 resource floors (tapped permanent can't tap, candidate
counts, life resources), the CR 119.4 life-payment rule (legal iff
life >= amount — reaching EXACTLY 0 is legal, the mission's "> 1"
question settled; 0-life always payable per 119.4b), the mana fold on the
``_v_add_mana`` pool key convention (colour-specific vs generic vs hybrid),
the C20 sorcery window against the turn skeleton + the explicit
stack_empty param, the honest notimpl flags (CostLoyalty, QX amounts),
pay_costs running through the journalled 12a verbs (TapState/ZONE_CHANGE
events fire from costs), and the folded activate move end to end.
"""

import unittest

from MTG_bot.core.ability_tree import (
    QX,
    ActivatedAbility,
    ActivationWindow,
    Atom,
    AtomArgs,
    ControllerRef,
    Cost,
    CostDiscard,
    CostLife,
    CostLoyalty,
    CostManaColor,
    CostManaGeneric,
    CostManaHybrid,
    CostPutCounter,
    CostSacrifice,
    CostTap,
    CounterKind,
    Effect,
    FAtom,
    FAtomPred,
    QConst,
    Selector,
    SelectorMode,
    Verb,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.legality import (
    ability_playable,
    activate,
    build_payment_plan,
    ctx_for,
    pay_costs,
)
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import (
    BF_YOU,
    HAND_YOU,
    UNIV,
    card_id,
    record_of,
    reset_oracle_ids,
)


def cost(*parts) -> Cost:
    return Cost(parts=parts)


def gain_life(n=1) -> Atom:
    return Atom(
        verb=Verb.GAIN_LIFE,
        args=AtomArgs(pairs=(("controller", ControllerRef.YOU), ("amount", QConst(n)))),
    )


def add_mana(color="G", n=1) -> Atom:
    return Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(
            pairs=(
                ("amount", QConst(n)),
                ("color", color),
                ("controller", ControllerRef.YOU),
            )
        ),
    )


def ability(cost_ir: Cost, effect: Effect | None = None, **kw) -> ActivatedAbility:
    return ActivatedAbility(
        cost=cost_ir, effect=gain_life() if effect is None else effect, **kw
    )


class LegalityCase(unittest.TestCase):
    """p0: one 2/2 'Alpha' permanent; p1: one 1/1 'Beta'."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=13)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.alpha = self.world.add_card(
            card_id("Alpha", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.beta = self.world.add_card(
            card_id("Beta", "1", "1"), self.p1, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)

    def attach(self, abilities, handle=None) -> int:
        target = handle if handle is not None else self.alpha
        return self.ex.attach_card(
            target,
            record_of(abilities, oid=self.world.cards[target].identity.oracle_id),
        )

    def pool(self, player, **mana):
        self.world.players[player].mana_pool.update(mana)


class TestTapCost(LegalityCase):
    def test_untapped_source_legal_tapped_source_illegal(self):
        self.attach([ability(cost(CostTap()))])
        self.assertIsNone(
            ability_playable(self.world, self.ex, self.alpha, 0, seat=self.p0)
        )
        self.world.cards[self.alpha].tapped = True
        self.assertEqual(
            ability_playable(self.world, self.ex, self.alpha, 0, seat=self.p0),
            "cost:tap:source_tapped",
        )

    def test_only_controller_may_activate(self):
        # CR 602.3: the controller of the permanent activates it.
        self.attach([ability(cost(CostTap()))])
        self.assertEqual(
            ability_playable(self.world, self.ex, self.alpha, 0, seat=self.p1),
            f"window:not_controller:{self.p1}",
        )

    def test_selector_tap_cost_counts_untapped_candidates(self):
        # A tap COST over a selection (Siege-Striker-shaped "tap any number"
        # stand-in, count 2): the candidate floor is CR 117.3 resource
        # arithmetic — tapped permanents never count.
        sel = Selector(QConst(2), SelectorMode.CHOOSE, UNIV, BF_YOU)
        self.attach([ability(cost(CostTap(target=sel)))])
        self.assertEqual(
            ability_playable(self.world, self.ex, self.alpha, 0, seat=self.p0),
            "cost:tap:insufficient_candidates:1<2",
        )
        gamma = self.world.add_card(
            card_id("Gamma", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.assertIsNone(
            ability_playable(self.world, self.ex, self.alpha, 0, seat=self.p0)
        )
        self.world.cards[gamma].tapped = True
        reason = ability_playable(self.world, self.ex, self.alpha, 0, seat=self.p0)
        assert reason is not None
        self.assertIn("insufficient_candidates", reason)

    def test_bridge_and_kind_gates(self):
        self.assertEqual(
            ability_playable(self.world, self.ex, self.alpha, 0, seat=self.p0),
            f"bridge:no_record:{self.alpha}",
        )
        self.attach([ability(cost())])
        with self.assertRaises(ValueError):
            ability_playable(self.world, self.ex, self.alpha, 5, seat=self.p0)


class TestManaFold(LegalityCase):
    """The PAYMENT:PTR arithmetic on the _v_add_mana key convention."""

    def plan(self, *parts):
        ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0)
        return build_payment_plan(self.world, ctx, cost(*parts))

    def test_color_specific_pool_key_arithmetic(self):
        self.pool(self.p0, G=1)  # one green mana
        plan, reason = self.plan(CostManaColor("G", QConst(1)))
        assert plan is not None
        self.assertEqual((plan.mana, reason), ((("G", 1),), None))
        plan, reason = self.plan(CostManaColor("R", QConst(1)))
        self.assertIsNone(plan)
        self.assertEqual(reason, "cost:mana:R:0<1")

    def test_generic_draws_any_key_colorless_pays_only_generic(self):
        self.pool(self.p0, G=2)
        plan, reason = self.plan(CostManaGeneric(QConst(2)))
        assert plan is not None
        self.assertEqual((plan.mana, reason), ((("G", 2),), None))
        self.pool(self.p0, C=1)
        plan, reason = self.plan(
            CostManaColor("G", QConst(2)), CostManaGeneric(QConst(1))
        )
        assert plan is not None
        self.assertEqual((plan.mana, reason), ((("C", 1), ("G", 2)), None))
        # a colorless key can NEVER pay a colored demand (CR 118.3a)
        self.world.players[self.p0].mana_pool.clear()
        self.pool(self.p0, C=3)
        plan, reason = self.plan(CostManaColor("G", QConst(1)))
        self.assertIsNone(plan, msg=f"colorless paid a green symbol: {plan}")

    def test_hybrid_canonical_first_colour_preference(self):
        self.pool(self.p0, U=1)
        plan, reason = self.plan(CostManaHybrid(("W", "U"), QConst(1)))
        assert plan is not None
        self.assertEqual((plan.mana, reason), ((("U", 1),), None))
        self.pool(self.p0, W=2)
        plan, reason = self.plan(CostManaHybrid(("W", "U"), QConst(3)))
        assert plan is not None
        self.assertEqual((plan.mana, reason), ((("U", 1), ("W", 2)), None))
        plan, reason = self.plan(CostManaHybrid(("W", "U"), QConst(4)))
        self.assertIsNone(plan, msg=f"4 hybrids from {plan}")
        assert reason is not None
        self.assertIn("mana_hybrid", reason)

    def test_generic_total_shortfall_reason(self):
        self.pool(self.p0, R=1)
        plan, reason = self.plan(CostManaGeneric(QConst(2)))
        self.assertIsNone(plan)
        self.assertEqual(reason, "cost:mana_generic:1<2")

    def test_qx_amount_raises_clean_notimpl(self):
        # The Slate's X_VALUE NUM field (design space §1.3) is a caller
        # declaration the executor has not wired: clean flag, never guess.
        ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0)
        with self.assertRaises(NotImplementedError):
            build_payment_plan(self.world, ctx, cost(CostManaGeneric(QX())))


class TestLifeCost(LegalityCase):
    """CR 119.4: legal iff life >= amount — exactly-0 payment is LEGAL,
    the death is the CR 119.6/704 state check AFTER; 0-life always
    payable (119.4b)."""

    def test_pay_to_exactly_zero_is_legal(self):
        self.world.players[self.p0].life = 2
        self.attach([ability(cost(CostLife(QConst(2))))])
        self.assertIsNone(
            ability_playable(self.world, self.ex, self.alpha, 0, seat=self.p0)
        )

    def test_pay_more_than_alive_is_illegal(self):
        self.world.players[self.p0].life = 1
        self.attach([ability(cost(CostLife(QConst(2))))])
        self.assertEqual(
            ability_playable(self.world, self.ex, self.alpha, 0, seat=self.p0),
            "cost:life:1<2",
        )

    def test_zero_life_payment_always_payable(self):
        self.world.players[self.p0].life = 0
        ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0)
        plan, reason = build_payment_plan(self.world, ctx, cost(CostLife(QConst(0))))
        assert plan is not None
        self.assertEqual((plan.life, reason), (0, None))

    def test_loyalty_cost_requires_loyalty_identity(self):
        # AMENDED (round 13b, quirk fix): 13a pinned "+1 on a non-PW is
        # payable" — that asymmetry was wrong. CR 606.1b ("a loyalty
        # ability can't be activated unless the permanent has loyalty")
        # gates the SOURCE, not the sign: Alpha has no printed loyalty and
        # no LOYALTY counters, so EITHER sign of a loyalty cost now
        # returns the same reason. A seeded LOYALTY counter (or a printed
        # CardIdentity.loyalty) restores the ordinary resource check —
        # that's the token-with-loyalty edge the CR really allows.
        ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0)
        plan, reason = build_payment_plan(self.world, ctx, cost(CostLoyalty(-2)))
        self.assertEqual((plan, reason), (None, "cost:loyalty:not_planeswalker"))
        plan, reason = build_payment_plan(self.world, ctx, cost(CostLoyalty(1)))
        self.assertEqual((plan, reason), (None, "cost:loyalty:not_planeswalker"))
        # the edge: loyalty counters present -> ordinary CR 606.3 fold
        self.world.cards[self.alpha].counters["LOYALTY"] = 3
        plan, reason = build_payment_plan(self.world, ctx, cost(CostLoyalty(-2)))
        assert plan is not None
        self.assertEqual((plan.loyalty, reason), (-2, None))
        plan, reason = build_payment_plan(self.world, ctx, cost(CostLoyalty(-5)))
        self.assertEqual((plan, reason), (None, "cost:loyalty:3<5"))


class TestSelectorCosts(LegalityCase):
    def test_sacrifice_candidate_floor_and_canonical_pick(self):
        # "Sacrifice a creature" (CHOOSE 1 of your creatures): floor = 1
        # candidate; the canonical plan picks the FIRST sorted handle.
        sel = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, BF_YOU)
        self.attach([ability(cost(CostSacrifice(sel)))])
        ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0)
        plan, reason = build_payment_plan(self.world, ctx, cost(CostSacrifice(sel)))
        self.assertEqual(reason, None)
        assert plan is not None
        self.assertEqual(plan.sacrifice, (self.alpha,))  # only Alpha is p0's
        # move Alpha to the graveyard: no candidates left
        self.world.move_to_zone(self.alpha, self.p0, ZONE_GRAVEYARD)
        plan, reason = build_payment_plan(self.world, ctx, cost(CostSacrifice(sel)))
        self.assertIsNone(plan)
        assert reason is not None
        self.assertIn("sacrifice:insufficient_candidates", reason)

    def test_discard_cost_needs_hand_cards(self):
        sel = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, HAND_YOU)
        cost_ir = cost(CostDiscard(sel))
        ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0)
        plan, reason = build_payment_plan(self.world, ctx, cost_ir)
        self.assertIsNone(plan)
        assert reason is not None
        self.assertIn("discard:insufficient_candidates", reason)
        hand = self.world.add_card(card_id("Payoff"), self.p0, ZONE_HAND)
        plan, reason = build_payment_plan(self.world, ctx, cost_ir)
        assert plan is not None
        self.assertEqual((plan.discard, reason), ((hand,), None))

    def test_put_counter_cost(self):
        sel = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, BF_YOU)
        cost_ir = cost(CostPutCounter(CounterKind.PAGE, sel, QConst(2)))
        ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0)
        plan, reason = build_payment_plan(self.world, ctx, cost_ir)
        self.assertEqual(reason, None)
        assert plan is not None
        self.assertEqual(plan.counters[0][1:], ("PAGE", 2))


class TestTimingWindow(LegalityCase):
    """C20: SORCERY = own main phase (skeleton's active seat) + empty
    stack (an explicit pre-casting query param — the executor has no
    stack). Default/INSTANT = any turn."""

    def test_sorcery_window_matrix(self):
        self.attach([ability(cost(), timing=ActivationWindow.SORCERY)])
        probe = lambda: ability_playable(
            self.world, self.ex, self.alpha, 0, seat=self.p0, stack_empty=True
        )
        self.assertEqual(probe(), "window:sorcery:not_own_turn")  # no turn begun
        self.ex.begin_turn(self.p0)
        self.assertIsNone(probe())
        self.ex.begin_turn(self.p1)
        self.assertEqual(probe(), "window:sorcery:not_own_turn")
        self.ex.begin_turn(self.p0)
        self.assertEqual(
            ability_playable(
                self.world, self.ex, self.alpha, 0, seat=self.p0, stack_empty=False
            ),
            "window:sorcery:stack_nonempty",
        )

    def test_instant_default_legal_on_opponent_turn(self):
        self.attach([ability(cost(CostTap()), timing=ActivationWindow.INSTANT)])
        self.ex.begin_turn(self.p1)  # opponent's turn
        self.assertIsNone(
            ability_playable(self.world, self.ex, self.alpha, 0, seat=self.p0)
        )


class TestConditionGate(LegalityCase):
    def test_condition_state_predicate(self):
        self.attach([ability(cost(), condition=FAtom(FAtomPred.IS_TAPPED))])
        self.assertEqual(
            ability_playable(self.world, self.ex, self.alpha, 0, seat=self.p0),
            "condition:false",
        )
        self.world.cards[self.alpha].tapped = True
        self.assertIsNone(
            ability_playable(self.world, self.ex, self.alpha, 0, seat=self.p0)
        )

    def test_unsupported_condition_pred_raises(self):
        # flag, never guess: a pred outside the vocab crashes the probe.
        # AMENDED 2026-09-30 (round 13c): NAME_CONTAINS left this probe —
        # it is in-vocab now (the GRANT_ACTIVATION filter's "a Teferi
        # planeswalker" gate evaluates it over the printed name).
        # AMENDED 2026-09-30 (round 14e): CMC_LE left this probe too — the
        # identity-mana-value read is answered now (Eliminate/Idol/Ugin).
        # AMENDED 2026-10-01 (round 18b): CMC_GE left this probe — its
        # identity read is answered now (Fierce Empath's CMC-6-or-greater
        # search filter, the CMC_LE twin).
        # AMENDED 2026-10-01 (round 20c): LIFE_LEAD_OVER_START_GE left this
        # probe — the R9-2 net-life gate is answered now (Speaker of the
        # Heavens' activation gate: current life minus the executor's
        # starting-life snapshot). AMENDED 2026-10-01 (round 21b):
        # CONTROLLER_COUNT_GT left this probe — the R8-9 dual-filter
        # comparison is answered now (Garruk, Unleashed's -2 "if an
        # opponent controls more creatures than you"). CONTROLLER_COUNT_LE
        # (the family's unimplemented sibling — no corpus card compiles it
        # yet) keeps the probe.
        self.attach(
            [
                ability(
                    cost(),
                    condition=FAtom(
                        FAtomPred.CONTROLLER_COUNT_LE,
                        inner_filter=FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
                        count=QConst(2),
                    ),
                )
            ]
        )
        with self.assertRaises(NotImplementedError):
            ability_playable(self.world, self.ex, self.alpha, 0, seat=self.p0)


class TestPayCosts(LegalityCase):
    def test_payment_fires_journal_events_and_pool_arithmetic(self):
        self.pool(self.p0, G=3)
        self.world.players[self.p0].life = 9
        hand = self.world.add_card(card_id("Payoff"), self.p0, ZONE_HAND)
        ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0)
        plan, _ = build_payment_plan(
            self.world,
            ctx,
            cost(
                CostTap(),
                CostManaColor("G", QConst(2)),
                CostLife(QConst(3)),
                CostDiscard(Selector(QConst(1), SelectorMode.CHOOSE, UNIV, HAND_YOU)),
            ),
        )
        assert plan is not None
        events_before = len(self.ex.events)
        journal_before = len(self.ex.journal.dump())
        pay_costs(self.ex, plan, source=self.alpha, controller=self.p0)
        self.assertEqual(self.world.players[self.p0].mana_pool.get("G", 0), 1)
        self.assertTrue(self.world.cards[self.alpha].tapped)
        self.assertEqual(self.world.players[self.p0].life, 6)
        self.assertEqual(self.world.zone_of(hand).kind, ZONE_GRAVEYARD)
        # the journal SEES the costs: TAP + discard zone-moves are events
        self.assertGreater(len(self.ex.events), events_before)
        self.assertGreater(len(self.ex.journal.dump()), journal_before)
        tags = [row[1] for row in self.ex.events[events_before:]]
        self.assertIn("PAY_MANA", tags)
        self.assertIn("TAP", tags)
        # mana audit row carries the canonical spend tuple
        self.assertEqual(
            next(row for row in self.ex.events if row[1] == "PAY_MANA")[3],
            (("G", 2),),
        )

    def test_pay_costs_refuses_a_stale_plan(self):
        ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0)
        self.pool(self.p0, R=1)
        plan, _ = build_payment_plan(
            self.world, ctx, cost(CostManaColor("R", QConst(1)))
        )
        assert plan is not None
        self.world.players[self.p0].mana_pool.clear()  # world moved under it
        with self.assertRaises(ValueError):
            pay_costs(self.ex, plan, source=self.alpha, controller=self.p0)


class TestActivateFold(LegalityCase):
    def test_forest_end_to_end_second_activation_illegal(self):
        self.attach([ability(cost(CostTap()), effect=add_mana("G"))])
        events = activate(self.ex, self.alpha, 0, seat=self.p0)
        self.assertEqual(self.world.players[self.p0].mana_pool, {"G": 1})
        self.assertTrue(self.world.cards[self.alpha].tapped)
        self.assertTrue(events)
        with self.assertRaises(ValueError) as caught:
            activate(self.ex, self.alpha, 0, seat=self.p0)
        self.assertIn("source_tapped", str(caught.exception))

    def test_sac_cost_self_sacrifice_moves_the_permanent(self):
        sel = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, BF_YOU)
        self.attach([ability(cost(CostTap(), CostSacrifice(sel)))])
        activate(self.ex, self.alpha, 0, seat=self.p0)
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_GRAVEYARD)
        self.assertTrue(self.world.cards[self.alpha].tapped)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
