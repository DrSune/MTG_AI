"""Round-21b regression tests: the wave-4 silent-semantic fixes.

Each class pins one 21b root cause plus the green behaviour it had to
leave untouched (promoted packs epitaph_golem_bottom / garruk_minus_two /
basri_ket_minus_two / caged_zombie_died_condition / tormods_crypt carry
the end-to-end readings; these are the UNIT fences under them):

1. The ACTIVATION-LANE cost fold (Sanctum of Tranquil Light): a
   CostModifier with an exactly-IS_SOURCE filter folds when the JUDGE is
   an activation source, so "activated abilities you control cost {5}
   less to activate" stops silently charging the printed cost. The lane
   is pinned to the IS_SOURCE shape — a universal filter does NOT fold
   there — and a caller that passes no activation is byte-identical to
   the pre-21b plan (the cast-lane five and the bare PAY atoms).
2. CONTROLLER_COUNT_GT (Garruk, Unleashed's -2): the dual-filter
   battlefield census — each side's count is its OWN filter (the
   compiled atom carries CONTROLLER_IS atoms inside), TRUE iff the
   inner (opponent) side strictly beats the right_inner (you) side.
3. THAT_MANY_COUNT's trigger-antecedent register (Basri Ket's -2): the
   14e ``result`` register keeps strict precedence; the 21b
   ``declare_attackers`` register answers ONLY when result is absent;
   both absent still RAISES (flag, never guess).
4. DIED_THIS_TURN's battlefield narrowing (Caged Zombie): a creature-
   typed handle SITTING ON THE BATTLEFIELD can never be the dead
   creature, so its gate is the existential reading (a dies row anywhere
   answers True); off-battlefield creature-typed handles keep the
   strict per-handle census (Gadrak), and the dead subject itself is
   still True.
5. The graveyard-sweep exemption in role_handles (Tormod's Crypt): the
   five-condition corpus pin (ALL + EXILE + universal empty-FAnd +
   GRAVEYARD + TARGET_PLAYER) makes the bound target a PLAYER
   designation and sweeps the whole graveyard; every other binding
   keeps binding-first semantics.
"""

import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    CostDeltaReduceGeneric,
    CostManaGeneric,
    CostModifier,
    FAnd,
    FAtom,
    FAtomPred,
    QConst,
    QProp,
    QPropField,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor.events import KIND_CREATURE_DIES
from MTG_bot.core.executor.legality import build_payment_plan, ctx_for, pay_costs
from MTG_bot.core.executor.quantity import _eval_atom, resolve
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
)
from MTG_bot.core.test_executor_binding import (
    GY_ANY,
    BindingCase,
    atom,
    card_id,
    enter,
)
from MTG_bot.core.test_executor_legality import (
    LegalityCase,
    ability,
    cost,
)

CREATURE = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")


def _controlled_by(who: ControllerRef) -> FAtom:
    return FAtom(FAtomPred.CONTROLLER_IS, who=who)


def gt(inner: FAnd, right: FAnd) -> FAtom:
    return FAtom(
        FAtomPred.CONTROLLER_COUNT_GT,
        inner_filter=inner,
        right_inner_filter=right,
    )


class ActivationFoldTest(LegalityCase):
    """Fix 1: the IS_SOURCE CostModifier folds on the activation lane."""

    HOST = CostManaGeneric(QConst(5))

    def sanctum(self, filter_ir=None, host=None):
        """Attach a {5}-activation plus a CostModifier discounting ITS
        OWN source by {5} — the compiled Sanctum shape (the hand-built IR
        stands in for the compiler's NAME_EQ defect, which is a separate
        STOP witness in tools/audit/suspects/)."""
        mod = CostModifier(
            filter=FAtom(FAtomPred.IS_SOURCE) if filter_ir is None else filter_ir,
            controller_ref=ControllerRef.YOU,
            delta=CostDeltaReduceGeneric(QConst(5)),
        )
        self.attach([ability(cost(self.HOST)), mod], handle=host)

    def plan_for(self, activation=None):
        ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0)
        return build_payment_plan(
            self.world, ctx, cost(self.HOST), activation=activation
        )

    def test_activation_lane_folds_the_is_source_discount(self):
        self.sanctum()
        self.pool(self.p0, W=1)
        # printed cost {5} with only {W} in pool: legal ONLY via the fold
        plan, reason = self.plan_for(activation=self.alpha)
        self.assertIsNone(reason)
        assert plan is not None
        # the discount paid everything — the plan consumes ZERO mana
        pay_costs(self.ex, plan, source=self.alpha, controller=self.p0)
        self.assertEqual(self.world.players[self.p0].mana_pool, {"W": 1})

    def test_universal_filter_does_not_fold_on_activation(self):
        # the lane gate: a blanket aura-style modifier stays cast-lane only
        self.sanctum(filter_ir=FAnd(()))
        self.pool(self.p0, W=1)
        plan, reason = self.plan_for(activation=self.alpha)
        self.assertIsNone(plan)
        self.assertEqual(reason, "cost:mana_generic:1<5")

    def test_legacy_caller_is_byte_identical(self):
        # no activation kwarg at all (the bare PAY-atom / query shape):
        # the fold stays dead exactly as before 21b
        self.sanctum()
        self.pool(self.p0, W=1)
        plan, reason = self.plan_for()
        self.assertIsNone(plan)
        self.assertEqual(reason, "cost:mana_generic:1<5")

    def test_foreign_source_is_not_discounted(self):
        # IS_SOURCE reads the JUDGE: an opponent permanent with the same
        # modifier does not discount my activation (host-beta shape: my
        # alpha activates, the IS_SOURCE filter fails against its seat)
        self.attach([ability(cost(self.HOST))])
        mod = CostModifier(
            filter=FAtom(FAtomPred.IS_SOURCE),
            controller_ref=ControllerRef.ANY,
            delta=CostDeltaReduceGeneric(QConst(5)),
        )
        self.ex.attach_card(
            self.beta,
            self.record_for_beta([mod]),
        )
        self.pool(self.p0, W=1)
        plan, reason = self.plan_for(activation=self.alpha)
        self.assertIsNone(plan)
        self.assertEqual(reason, "cost:mana_generic:1<5")

    def record_for_beta(self, abilities):
        from MTG_bot.core.test_executor_binding import record_of

        return record_of(
            abilities,
            name="BetaRec",
            oid=self.world.cards[self.beta].identity.oracle_id,
        )


class ControllerCountGtTest(LegalityCase):
    """Fix 2: the dual-filter population comparison (Garruk -2)."""

    def ctx(self):
        return self.ex._ctx(
            source=self.alpha, controller=self.p0, bindings={}, decisions=()
        )

    def eval_gt(self):
        return _eval_atom(
            gt(
                FAnd((CREATURE, _controlled_by(ControllerRef.OPPONENT))),
                FAnd((CREATURE, _controlled_by(ControllerRef.YOU))),
            ),
            self.p0,
            self.ctx(),
        )

    def test_tie_is_false(self):
        # Alpha (you) vs Beta (opponent): 1 == 1, strict > fails
        self.assertFalse(self.eval_gt())

    def test_opponent_majority_is_true(self):
        self.world.add_card(card_id("Thrull2", "1", "1"), self.p1, ZONE_BATTLEFIELD)
        self.assertTrue(self.eval_gt())

    def test_filters_are_per_side(self):
        # inner names GOBLIN (0 match), right_inner CREATURE (1 match):
        # 0 > 1 is False even though the raw populations tie at 1/1
        self.assertFalse(
            _eval_atom(
                gt(
                    FAnd(
                        (
                            FAtom(FAtomPred.TYPE_EQ, string_value="Goblin"),
                            _controlled_by(ControllerRef.OPPONENT),
                        )
                    ),
                    FAnd((CREATURE, _controlled_by(ControllerRef.YOU))),
                ),
                self.p0,
                self.ctx(),
            )
        )

    def test_loyalty_gate_end_to_end(self):
        # the Garruk shape through ability_playable's condition gate
        self.attach(
            [
                ability(
                    cost(),
                    condition=gt(
                        FAnd((CREATURE, _controlled_by(ControllerRef.OPPONENT))),
                        FAnd((CREATURE, _controlled_by(ControllerRef.YOU))),
                    ),
                )
            ]
        )
        from MTG_bot.core.executor.legality import ability_playable

        self.assertEqual(
            ability_playable(self.world, self.ex, self.alpha, 0, seat=self.p0),
            "condition:false",
        )
        self.world.add_card(card_id("Thrull3", "1", "1"), self.p1, ZONE_BATTLEFIELD)
        self.assertIsNone(
            ability_playable(self.world, self.ex, self.alpha, 0, seat=self.p0)
        )


class ThatManyRegisterTest(LegalityCase):
    """Fix 3: ``result`` precedence over the 21b ``declare_attackers``
    fallback, and the double-absence raise."""

    THAT = QProp("event", QPropField.THAT_MANY_COUNT)

    def resolve_with(self, **bindings):
        # the trigger firing always carries the event subject (12b) —
        # THAT_MANY lives behind that referent read, registers underneath
        ctx = ctx_for(
            self.ex,
            source=self.alpha,
            controller=self.p0,
            bindings={"event": self.alpha, **bindings},
        )
        return resolve(self.THAT, ctx)

    def test_result_register_keeps_precedence(self):
        # Kinetic Augur's producer path: result wins even when the
        # declaration register is also present
        self.assertEqual(
            self.resolve_with(
                result=[self.alpha, self.beta],
                declare_attackers=[self.alpha, self.beta, self.alpha],
            ),
            2,
        )

    def test_declaration_fallback_answers_when_result_absent(self):
        # Basri's -2: the TRIGGER is the antecedent; the group rides in
        # on the 21b register
        self.assertEqual(
            self.resolve_with(declare_attackers=[self.alpha, self.beta]), 2
        )

    def test_single_handle_binding_counts_one(self):
        self.assertEqual(self.resolve_with(declare_attackers=self.alpha), 1)

    def test_both_absent_raises(self):
        with self.assertRaises(NotImplementedError):
            self.resolve_with()


class DiedBattlefieldTest(BindingCase):
    """Fix 4: creature-typed handles ON the battlefield read
    existentially; off-battlefield handles keep the strict census."""

    def ctx(self, source):
        return self.ex._ctx(
            source=source, controller=self.p0, bindings={}, decisions=()
        )

    def kill_watch(self):
        self.ex.execute(
            enter(GY_ANY),
            source=self.watch,
            controller=self.p0,
            bindings={"cards": self.watch},
        )

    def test_dies_row_actually_journaled(self):
        self.kill_watch()
        kinds = [row[1] for row in self.ex.journal.dump()]
        self.assertIn(KIND_CREATURE_DIES, kinds)

    def test_battlefield_creature_reads_existentially(self):
        # Caged Zombie / Sabertooth Mauler: the activation SOURCE is a
        # battlefield creature — it can never itself be the dead one, so
        # "if a creature died this turn" is the only coherent reading
        bystander = self.world.add_card(
            card_id("Caged", "0", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.assertFalse(
            _eval_atom(FAtom(FAtomPred.DIED_THIS_TURN), bystander, self.ctx(bystander))
        )
        self.kill_watch()
        self.assertTrue(
            _eval_atom(FAtom(FAtomPred.DIED_THIS_TURN), bystander, self.ctx(bystander))
        )

    def test_off_battlefield_creature_keeps_strict_census(self):
        # Gadrak / Standard Bearer: graveyard creature-typed handles that
        # did not die still answer False after the narrowing
        bystander = self.world.add_card(
            card_id("Bearer", "2", "2"),
            self.p0,
            ZONE_GRAVEYARD,
        )
        self.kill_watch()
        self.assertFalse(
            _eval_atom(FAtom(FAtomPred.DIED_THIS_TURN), bystander, self.ctx(bystander))
        )
        self.assertTrue(
            _eval_atom(
                FAtom(FAtomPred.DIED_THIS_TURN), self.watch, self.ctx(self.watch)
            )
        )


class GraveyardSweepTest(BindingCase):
    """Fix 5: the Tormod exemption sweeps the target's WHOLE graveyard;
    every other binding-first shape is untouched."""

    def tormod(self, mode=SelectorMode.ALL):
        return atom(
            Verb.EXILE,
            target=Selector(
                QConst(9),
                mode,
                FAnd(()),
                Zone(ZoneKind.GRAVEYARD, ControllerRef.TARGET_PLAYER),
            ),
        )

    def fill_graveyard(self):
        return [
            self.world.add_card(card_id(f"Grav{i}"), self.p1, ZONE_GRAVEYARD)
            for i in (1, 2)
        ]

    def test_all_exile_sweeps_the_bound_players_graveyard(self):
        gy = self.fill_graveyard()
        self.ex.execute(
            self.tormod(),
            source=self.watch,
            controller=self.p0,
            bindings={"target": gy[0]},
        )
        for card in gy:
            self.assertEqual(self.world.zone_of(card).kind, ZONE_EXILE)

    def test_non_all_mode_keeps_binding_first(self):
        # the exemption is ALL-mode only: a CHOOSE designation exiles
        # just the bound card
        gy = self.fill_graveyard()
        self.ex.execute(
            self.tormod(mode=SelectorMode.CHOOSE),
            source=self.watch,
            controller=self.p0,
            bindings={"target": gy[0]},
        )
        self.assertEqual(self.world.zone_of(gy[0]).kind, ZONE_EXILE)
        self.assertEqual(self.world.zone_of(gy[1]).kind, ZONE_GRAVEYARD)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
