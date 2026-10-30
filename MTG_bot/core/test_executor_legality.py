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
    plan_mana_taps,
    tap_for_payment,
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
        sel = Selector(QConst(2), SelectorMode.CHOOSE, UNIV, zones=(BF_YOU,))
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
        sel = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(BF_YOU,))
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
        sel = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(HAND_YOU,))
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
        sel = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(BF_YOU,))
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
                CostDiscard(Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(HAND_YOU,))),
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

    def test_any_colour_offers_the_five_colours_only(self):
        # V4 (2026-10-29): "one mana of any color" is W, U, B, R or G (CR 105.1,
        # 106.1a); colorless is not a color.
        self.attach([ability(cost(CostTap()), effect=add_mana("ANY"))])
        seen = []

        def provider(vocab, what):
            seen.append((tuple(vocab), what))
            return vocab[-1]

        self.ex.decisions.provider = provider
        activate(self.ex, self.alpha, 0, seat=self.p0)
        self.assertEqual([v for v, w in seen if w.startswith("mana:")], [("W", "U", "B", "R", "G")])
        self.assertEqual(self.world.players[self.p0].mana_pool, {"G": 1})

    def test_sac_cost_self_sacrifice_moves_the_permanent(self):
        sel = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(BF_YOU,))
        self.attach([ability(cost(CostTap(), CostSacrifice(sel)))])
        activate(self.ex, self.alpha, 0, seat=self.p0)
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_GRAVEYARD)
        self.assertTrue(self.world.cards[self.alpha].tapped)


SICK = "summoning sickness (CR 302.6) without haste"


class TestSummoningSickness(LegalityCase):
    """V1 (2026-10-29): CR 302.6 / 602.5a. A creature's ability with {T} in
    its cost needs the creature under its controller's control since their
    most recent turn began; haste exempts it (CR 702.10). Setup permanents
    (Alpha, Beta) carry no entry rows and read ready."""

    def enter(self, name, type_line="Creature", seat=None):
        """A journalled hand -> battlefield move this turn (what a resolving
        creature spell does), so the sickness clock sees the entry row."""
        seat = self.p0 if seat is None else seat
        handle = self.world.add_card(
            card_id(name, "1", "1", type_line=type_line), seat, ZONE_HAND
        )
        self.ex.execute(
            Atom(
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        (
                            "cards",
                            Selector(
                                QConst(1), SelectorMode.TARGET, UNIV, zones=(HAND_YOU,)
                            ),
                        ),
                        ("destination", BF_YOU),
                    )
                ),
            ),
            source=handle,
            controller=seat,
            bindings={"cards": handle},
        )
        self.assertEqual(self.world.zone_of(handle).kind, ZONE_BATTLEFIELD)
        return handle

    def playable(self, handle, seat=None):
        seat = self.p0 if seat is None else seat
        return ability_playable(self.world, self.ex, handle, 0, seat=seat)

    def test_tap_ability_refused_the_turn_it_enters(self):
        self.ex.begin_turn(self.p0)
        newcomer = self.enter("Newcomer")
        self.attach([ability(cost(CostTap()))], newcomer)
        self.assertEqual(self.playable(newcomer), SICK)
        with self.assertRaises(ValueError) as caught:
            activate(self.ex, newcomer, 0, seat=self.p0)
        self.assertIn("summoning sickness", str(caught.exception))
        self.assertFalse(self.world.cards[newcomer].tapped)  # nothing paid

    def test_mana_ability_refused_and_not_listed(self):
        from MTG_bot.core.executor.query import legal_activations

        self.ex.begin_turn(self.p0)
        newcomer = self.enter("Mana Elf")
        self.attach([ability(cost(CostTap()), effect=add_mana("G"))], newcomer)
        self.attach([ability(cost(CostTap()), effect=add_mana("G"))])  # Alpha
        self.assertEqual(self.playable(newcomer), SICK)
        rows = {o.source for o in legal_activations(self.world, self.ex, self.p0)}
        self.assertEqual(rows, {self.alpha})  # the ready setup creature only

    def test_ability_without_the_tap_symbol_is_not_restricted(self):
        self.ex.begin_turn(self.p0)
        newcomer = self.enter("Newcomer")
        self.attach([ability(cost(CostManaColor("G", QConst(1))))], newcomer)
        self.pool(self.p0, G=1)
        self.assertIsNone(self.playable(newcomer))

    def test_tapping_other_creatures_as_a_cost_is_not_restricted(self):
        # "Tap an untapped creature you control" is not the {T} symbol: a
        # sick source may pay it, and a sick creature may be the one tapped.
        self.ex.begin_turn(self.p0)
        newcomer = self.enter("Newcomer")
        other = Selector(
            QConst(1),
            SelectorMode.CHOOSE,
            FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
            zones=(BF_YOU,),
        )
        self.attach([ability(cost(CostTap(target=other)))], newcomer)
        self.assertIsNone(self.playable(newcomer))

    def test_haste_exempts(self):
        from MTG_bot.core.ability_tree import Keyword, KeywordAbility

        self.ex.begin_turn(self.p0)
        newcomer = self.enter("Hasty")
        self.attach([ability(cost(CostTap()))], newcomer)
        self.assertEqual(self.playable(newcomer), SICK)
        self.ex.execute(
            Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("ability", KeywordAbility(keyword=Keyword.HASTE)),
                        (
                            "target",
                            Selector(
                                QConst(1), SelectorMode.TARGET, UNIV, zones=(BF_YOU,)
                            ),
                        ),
                    )
                ),
            ),
            source=newcomer,
            controller=self.p0,
            bindings={"target": newcomer},
        )
        self.assertIsNone(self.playable(newcomer))

    def test_noncreature_permanent_taps_the_turn_it_enters(self):
        self.ex.begin_turn(self.p0)
        relic = self.enter("Relic", type_line="Artifact")
        self.attach([ability(cost(CostTap()))], relic)
        self.assertIsNone(self.playable(relic))

    def test_sick_through_the_opponents_turn_ready_on_its_controllers_next(self):
        # "their most recent turn began": a creature that entered on p0's
        # turn is still sick for p0 during p1's turn.
        self.ex.begin_turn(self.p0)
        newcomer = self.enter("Newcomer")
        self.attach([ability(cost(CostTap()))], newcomer)
        self.ex.end_turn()
        self.ex.advance_turn()
        self.assertEqual(self.world.active_player, self.p1)
        self.assertEqual(self.playable(newcomer), SICK)
        self.ex.end_turn()
        self.ex.advance_turn()
        self.assertEqual(self.world.active_player, self.p0)
        self.assertIsNone(self.playable(newcomer))

    def test_entered_on_the_opponents_turn_ready_on_its_controllers_turn(self):
        self.ex.begin_turn(self.p1)
        newcomer = self.enter("Flash Bear")  # p0's creature, on p1's turn
        self.attach([ability(cost(CostTap()))], newcomer)
        self.assertEqual(self.playable(newcomer), SICK)
        self.ex.end_turn()
        self.ex.advance_turn()
        self.assertEqual(self.world.active_player, self.p0)
        self.assertIsNone(self.playable(newcomer))


class TestManaEmpties(LegalityCase):
    """V2 (2026-10-29): CR 500.5 / 106.4. Unspent mana empties as each step
    and phase ends; within the main phase it stays for the next act."""

    def empty_rows(self):
        return [e for e in self.ex.events if e[1] == "EMPTY_MANA"]

    def tap_alpha_for_green(self):
        self.attach(
            [
                ability(cost(CostTap()), effect=add_mana("G")),
                ability(cost(CostManaColor("G", QConst(1)))),
            ]
        )
        activate(self.ex, self.alpha, 0, seat=self.p0)
        self.assertEqual(self.world.players[self.p0].mana_pool, {"G": 1})

    def test_mana_stays_for_the_next_act_of_the_same_phase(self):
        self.ex.begin_turn(self.p0)
        self.tap_alpha_for_green()
        self.assertIsNone(ability_playable(self.world, self.ex, self.alpha, 1, seat=self.p0))
        activate(self.ex, self.alpha, 1, seat=self.p0)  # pays the {G} just made
        self.assertEqual(self.world.players[self.p0].mana_pool, {})

    def test_main_phase_mana_is_gone_at_combat(self):
        self.ex.begin_turn(self.p0)
        self.tap_alpha_for_green()
        self.ex.decisions.provider = lambda vocab, what: (
            "DECLINE" if "DECLINE" in vocab else vocab[0]
        )
        self.ex.combat_step(self.p0)
        self.assertEqual(self.world.players[self.p0].mana_pool, {})
        rows = self.empty_rows()
        self.assertEqual(len(rows), 1)  # what was lost reaches the fingerprint
        self.assertEqual(rows[0][2:], (str(self.p0), (("G", 1),)))

    def test_mana_does_not_survive_the_turn_and_its_restriction_goes_with_it(self):
        self.ex.begin_turn(self.p0)
        self.pool(self.p1, U=2)
        self.ex.mana_ledger.add(self.p1, "U", 2, (FAtom(FAtomPred.IS_SOURCE),))
        self.ex.end_turn()
        self.ex.advance_turn()
        self.assertEqual(self.world.players[self.p1].mana_pool, {})
        self.assertFalse(self.ex.mana_ledger.has(self.p1))

    def test_an_empty_pool_leaves_no_row(self):
        self.ex.begin_turn(self.p0)
        self.ex.end_turn()
        self.assertEqual(self.empty_rows(), [])



class TestManaAbilitiesWhilePaying(LegalityCase):
    """B-90 (a), 2026-10-29: CR 601.2g / 605.3a. A payment asked outside the
    act window may tap the payer's untapped mana abilities whose cost is only
    {T}: a minimal set the planner proves sufficient, never all."""

    def land(self, name, effect, type_line="Land"):
        handle = self.world.add_card(card_id(name, type_line=type_line), self.p0, ZONE_BATTLEFIELD)
        self.attach([ability(cost(CostTap()), effect=effect)], handle)
        return handle

    def check(self, cost_ir):
        ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0)
        return lambda: build_payment_plan(self.world, ctx, cost_ir)[1]

    def plan(self, *parts):
        return plan_mana_taps(self.ex, self.p0, self.check(cost(*parts)))

    def test_the_pool_pays_without_taps(self):
        self.land("Forest", add_mana("G"))
        self.pool(self.p0, G=1)
        self.assertEqual(self.plan(CostManaColor("G", QConst(1))), ())

    def test_a_minimal_set_never_all(self):
        f1 = self.land("Forest", add_mana("G"))
        self.land("Island", add_mana("U"))
        self.land("Forest", add_mana("G"))
        taps = self.plan(CostManaColor("G", QConst(1)), CostManaGeneric(QConst(1)))
        self.assertEqual(len(taps), 2)  # {1}{G}: two of the three lands
        self.assertEqual(taps[0].source, f1)
        self.assertEqual(taps[0].production[0], "G")

    def test_two_symbols_of_one_colour_tap_two_lands(self):
        # {U}{U} as two cost parts: after one Island the planner still names
        # "U short", which is progress, not a useless tap.
        i1 = self.land("Island", add_mana("U"))
        i2 = self.land("Island", add_mana("U"))
        self.land("Island", add_mana("U"))
        taps = self.plan(CostManaColor("U", QConst(1)), CostManaColor("U", QConst(1)))
        self.assertEqual([t.source for t in taps], [i1, i2])

    def test_a_coloured_need_taps_the_matching_land_only(self):
        self.land("Forest", add_mana("G"))
        island = self.land("Island", add_mana("U"))
        taps = self.plan(CostManaColor("U", QConst(1)))
        self.assertEqual([t.source for t in taps], [island])

    def test_a_dual_land_chooses_the_needed_colour(self):
        from MTG_bot.core.ability_tree import Choose

        dual = self.land("Swiftwater Cliffs", Choose(count=QConst(1), options=(add_mana("U"), add_mana("R"))))
        (tap,) = self.plan(CostManaColor("R", QConst(1)))
        self.assertEqual((tap.source, tap.production[0]), (dual, "R"))
        tap_for_payment(self.ex, self.p0, (tap,))
        self.assertEqual(self.world.players[self.p0].mana_pool, {"R": 1})
        self.assertTrue(self.world.cards[dual].tapped)

    def test_an_any_colour_source_chooses_the_needed_colour(self):
        rock = self.land("Meteorite", add_mana("ANY"), type_line="Artifact")
        (tap,) = self.plan(CostManaColor("B", QConst(1)))
        self.assertEqual((tap.source, tap.decisions), (rock, ("B",)))
        tap_for_payment(self.ex, self.p0, (tap,))
        self.assertEqual(self.world.players[self.p0].mana_pool, {"B": 1})

    def test_sick_mana_creatures_and_tapped_lands_are_not_used(self):
        self.ex.begin_turn(self.p0)
        elf = self.world.add_card(card_id("Elf", "1", "1"), self.p0, ZONE_HAND)
        self.ex.execute(
            Atom(
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        ("cards", Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(HAND_YOU,))),
                        ("destination", BF_YOU),
                    )
                ),
            ),
            source=elf,
            controller=self.p0,
            bindings={"cards": elf},
        )
        self.attach([ability(cost(CostTap()), effect=add_mana("G"))], elf)  # V1: sick
        forest = self.land("Forest", add_mana("G"))
        self.world.cards[forest].tapped = True
        self.assertIsNone(self.plan(CostManaColor("G", QConst(1))))

    def test_a_pay_inside_a_resolution_taps_in_place_and_journals_once(self):
        # "You may pay {1}": offered because a land can pay it (CR 605.3a);
        # paying taps the land without a nested activation, so the running
        # atom journals exactly one TapState row and settles nothing extra.
        from MTG_bot.core.ability_tree import OptionalEffect
        from MTG_bot.core.executor.query import optional_offer

        forest = self.land("Forest", add_mana("G"))
        effect = OptionalEffect(
            inner=Atom(verb=Verb.PAY, args=AtomArgs(pairs=(("cost", cost(CostManaGeneric(QConst(1)))),)))
        )
        self.assertIn("fire", optional_offer(self.ex, effect, source=self.alpha, controller=self.p0))
        self.ex.apply_effect(effect, source=self.alpha, controller=self.p0, decisions=("fire",))
        self.assertTrue(self.world.cards[forest].tapped)
        self.assertEqual(self.world.players[self.p0].mana_pool, {})
        taps = [e for e in self.ex.journal.events if e.kind == "TAP_STATE" and e.subject == forest]
        self.assertEqual(len(taps), 1)

    def test_a_pay_nothing_can_fund_is_not_offered(self):
        from MTG_bot.core.ability_tree import OptionalEffect
        from MTG_bot.core.executor.query import optional_offer

        self.land("Forest", add_mana("G"))
        effect = OptionalEffect(
            inner=Atom(verb=Verb.PAY, args=AtomArgs(pairs=(("cost", cost(CostManaGeneric(QConst(2)))),)))
        )
        self.assertNotIn("fire", optional_offer(self.ex, effect, source=self.alpha, controller=self.p0))

    def test_no_set_pays_returns_none(self):
        self.land("Forest", add_mana("G"))
        self.assertIsNone(self.plan(CostManaColor("G", QConst(2))))

    def test_planning_leaves_no_trace(self):
        self.land("Forest", add_mana("G"))
        self.land("Island", add_mana("U"))
        self.pool(self.p0, W=1)
        before = (dict(self.world.players[self.p0].mana_pool), len(self.ex.events), len(self.ex.journal.events))
        self.assertIsNotNone(self.plan(CostManaColor("G", QConst(1)), CostManaGeneric(QConst(2))))
        after = (dict(self.world.players[self.p0].mana_pool), len(self.ex.events), len(self.ex.journal.events))
        self.assertEqual(before, after)
        self.assertFalse(any(self.world.cards[h].tapped for h in self.world.cards))



class TestSelflessSaviorAnotherTarget(unittest.TestCase):
    """V5 (2026-10-29): Selfless Savior's "Sacrifice this creature: Another
    target creature you control gains indestructible until end of turn."
    "Another" excludes the Savior itself, so alone it has no legal target and
    its ability is not a free sacrifice outlet (CR 601.2c, 602.2b)."""

    def setUp(self):
        from MTG_bot.core.executor.games import get_supply, identity_of

        supply = get_supply("all", "M21")
        record = next(
            supply.pool.results[o].card
            for o, m in supply.metas.items()
            if m.name == "Selfless Savior"
        )
        self.world = GameWorld(num_players=2, start_life=20, master_seed=13)
        self.p0 = self.world.player_order[0]
        self.savior = self.world.add_card(identity_of(record), self.p0, ZONE_BATTLEFIELD)
        self.ex = Executor(self.world)
        self.ex.attach_card(self.savior, record)
        self.ability = record.abilities[0]

    def candidates(self):
        from MTG_bot.core.executor.query import activation_target_slots

        (slot,) = activation_target_slots(
            self.ex, self.ability.effect, source=self.savior, seat=self.p0
        )
        return slot.candidates

    def test_alone_it_has_no_legal_target(self):
        self.assertEqual(self.candidates(), ())

    def test_another_creature_you_control_is_the_target(self):
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        self.assertEqual(self.candidates(), (bear,))



class TestAnotherTarget(unittest.TestCase):
    """V13 (2026-10-29): "another target creature". Relative to the source
    (Brash Taunter's "This creature fights another target creature") the
    source is not a legal target; relative to another target (Rookie Mistake,
    Garruk's -2) the two targets must differ (CR 115.3)."""

    def test_brash_taunter_cannot_fight_itself(self):
        from MTG_bot.core.ability_tree import ActivatedAbility
        from MTG_bot.core.executor.games import get_supply, identity_of
        from MTG_bot.core.executor.query import activation_target_slots

        supply = get_supply("all", "M21")
        record = next(
            supply.pool.results[o].card for o, m in supply.metas.items() if m.name == "Brash Taunter"
        )
        world = GameWorld(num_players=2, start_life=20, master_seed=13)
        p0, p1 = world.player_order
        taunter = world.add_card(identity_of(record), p0, ZONE_BATTLEFIELD)
        ex = Executor(world)
        ex.attach_card(taunter, record)
        fight = next(a for a in record.abilities if isinstance(a, ActivatedAbility))

        def candidates():
            (slot,) = activation_target_slots(ex, fight.effect, source=taunter, seat=p0)
            return slot.candidates

        self.assertEqual(candidates(), ())
        ogre = world.add_card(card_id("Ogre", "3", "3"), p1, ZONE_BATTLEFIELD)
        self.assertEqual(candidates(), (ogre,))

    def test_the_another_slot_must_differ_from_the_other_slot(self):
        from types import SimpleNamespace

        from MTG_bot.core.ability_tree import FAnd
        from MTG_bot.core.executor.stack import another_target_reason
        from MTG_bot.core.identity import Handle

        creature = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")
        first = SimpleNamespace(selector=Selector(QConst(1), SelectorMode.TARGET, creature, zones=(BF_YOU,)))
        another = SimpleNamespace(
            selector=Selector(
                QConst(1),
                SelectorMode.TARGET,
                FAnd((creature, FAtom(FAtomPred.IS_ANY_TARGET))),
                zones=(BF_YOU,),
            )
        )
        a, b = Handle("card", 1), Handle("card", 2)
        self.assertIsNone(another_target_reason([first, another], (a, b)))
        self.assertIsNotNone(another_target_reason([first, another], (b, b)))
        self.assertIsNone(another_target_reason([first, first], (b, b)))  # two plain "target"s may share


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
