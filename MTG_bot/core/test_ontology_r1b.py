"""R1b cost canonicalization — RED-FIRST battery (BINDING spec
KNOWLEDGE/2026-10-20/136 §2(2), ontology §3 SET-R1b rows + O3 set law).

Cost.parts / SpellAbility.additional_costs / CostManaHybrid.colors /
CostModifier.extra_deltas become SET-ENFORCED: sorted AT CONSTRUCTION
(frozen ``__post_init__`` + ``object.__setattr__``, the AtomArgs.pairs
:2541 precedent). Because ``build_payment_plan`` walks the parts LIST,
construction-sort makes the plan — the failure string, the trace, and the
``sacrifice_options`` ask sequence — a function of the parts MULTISET.

Battery items (spec numbering):
  (i)  two-failing-part precedence: same multiset, permuted construction
       ⇒ identical failure string + identical plan (D11: drift accepted,
       canonical order pinned HERE).
  (ii) hybrid determinism probe ({W/B}+{W/U}, pool W:1 B:1): pins the
       DETERMINISTIC post-sort witness outcome. The greedy payer-choice
       unsoundness is D10 — determinism pinned, semantics deferred to the
       engine lane; population 0 in both pools.
  (iii) {U}{X} + CostDeltaReduceMana {U} (Stormwing Entity lane): the
       per-color Σ-min-clamp is order-invariant — payable + trace
       invariant under parts permutation (already-green determinism leg).
  (iv) constructed TWO-sacrifice-part Cost: ask-sequence determinism
       double-run, replay byte-stability of the ``sacrifice:...:digest``
       keys (tripwire for the A2 one-asked-kind-per-Cost assumption).

Pre-change items (i), (ii), (iv) and the raw sort/eq pins MUST be RED;
(iii) is a determinism pin expected GREEN pre-change (reported as such).
"""

from __future__ import annotations

import dataclasses
import unittest

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    Atom,
    AtomArgs,
    Cost,
    CostDeltaReduceMana,
    CostLife,
    CostManaColor,
    CostManaGeneric,
    CostManaHybrid,
    CostModifier,
    CostSacrifice,
    ControllerRef,
    FAtom,
    FAtomPred,
    QConst,
    QX,
    Selector,
    SelectorMode,
    SpellAbility,
    SpellKind,
    Verb,
    canonical_json,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.legality import (
    build_payment_plan,
    ctx_for,
    pay_costs,
)
from MTG_bot.core.state import ZONE_BATTLEFIELD, GameWorld
from MTG_bot.core.test_executor_binding import (
    BF_YOU,
    IS_SOURCE,
    card_id,
    record_of,
    reset_oracle_ids,
)


class R1bCase(unittest.TestCase):
    """Same harness shape as test_executor_legality.LegalityCase."""

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

    def plan(self, cost: Cost, x_value: int | None = None):
        ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0, x_value=x_value)
        return build_payment_plan(self.world, ctx, cost)

    def pool(self, player, **mana):
        self.world.players[player].mana_pool.update(mana)


# ---------------------------------------------------------------------------
# Raw SET-ENFORCED law: construction sort by canonical_json (O3, :2541 style)
# ---------------------------------------------------------------------------
class TestConstructionSort(R1bCase):
    def test_cost_parts_permuted_construction_is_value_equal(self):
        """R1b canonicalization: the same parts MULTiset lands on one
        encoding regardless of construction order (== and hash and bytes)."""
        mana = CostManaColor("W", QConst(1))
        generic = CostManaGeneric(QConst(1))
        a = Cost(parts=(mana, generic))
        b = Cost(parts=(generic, mana))
        self.assertEqual(a, b)
        self.assertEqual(hash(a), hash(b))
        self.assertEqual(canonical_json(a), canonical_json(b))
        # canonical order: canonical_json(mana) < canonical_json(generic)
        # ('"tag":"QConst"' < '"tag":"QX"' byte order, and value '1' < '2'
        # style digit compares — the sort KEY is the json, pinned here):
        want = sorted((mana, generic), key=canonical_json)
        self.assertEqual(a.parts, tuple(want))

    def test_cost_sort_is_idempotent_under_roundtrip_and_replace(self):
        parts = (
            CostManaGeneric(QConst(2)),
            CostLife(QConst(1)),
            CostManaColor("U", QConst(1)),
        )
        once = Cost(parts=parts)
        again = Cost(parts=once.parts)  # no second-pass refire
        self.assertEqual(canonical_json(again), canonical_json(once))
        self.assertEqual(
            canonical_json(dataclasses.replace(once, parts=once.parts)),
            canonical_json(once),
        )
        back = __import__(
            "MTG_bot.core.ability_tree", fromlist=["from_dict"]
        ).from_dict(
            "Cost",
            __import__("MTG_bot.core.ability_tree", fromlist=["to_dict"]).to_dict(once),
        )
        self.assertEqual(canonical_json(back), canonical_json(once))

    def test_cost_validation_survives_the_sort(self):
        with self.assertRaises(ValueError):
            Cost(parts=(CostLife(QConst(1)), "not a cost part"))
        node = Cost(parts=(CostLife(QConst(1)),))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            node.parts = ()  # the only rewrite channel is __post_init__

    def test_hybrid_colors_are_sorted_at_construction(self):
        h1 = CostManaHybrid(colors=("B", "W"), amount=QConst(1))
        h2 = CostManaHybrid(colors=("W", "B"), amount=QConst(1))
        self.assertEqual(h1.colors, ("B", "W"))
        self.assertEqual(h1, h2)  # R1b canonicalization
        self.assertEqual(canonical_json(h1), canonical_json(h2))
        with self.assertRaises(ValueError):  # validation law untouched
            CostManaHybrid(colors=("W", "W"), amount=QConst(1))
        with self.assertRaises(ValueError):
            CostManaHybrid(colors=("W", "K"), amount=QConst(1))

    def test_modifier_extra_deltas_sorted_at_construction(self):
        # (f) channel: pure += accumulators ⇒ commutative ⇒ SET reclass.
        d_u = CostDeltaReduceMana("U", QConst(1))
        d_g = CostDeltaReduceMana("G", QConst(2))
        m1 = CostModifier(
            filter=IS_SOURCE,
            controller_ref=ControllerRef.YOU,
            delta=CostDeltaReduceMana("R", QConst(1)),
            extra_deltas=(d_g, d_u),
        )
        m2 = CostModifier(
            filter=IS_SOURCE,
            controller_ref=ControllerRef.YOU,
            delta=CostDeltaReduceMana("R", QConst(1)),
            extra_deltas=(d_u, d_g),
        )
        self.assertEqual(canonical_json(m1), canonical_json(m2))  # R1b canonicalization
        want = tuple(sorted((d_g, d_u), key=canonical_json))
        self.assertEqual(m1.extra_deltas, want)
        with self.assertRaises(ValueError):
            CostModifier(
                filter=IS_SOURCE,
                controller_ref=ControllerRef.YOU,
                delta=CostDeltaReduceMana("R", QConst(1)),
                extra_deltas=("not a delta",),
            )

    def test_additional_costs_sorted_at_construction(self):
        tap_cost = Cost(parts=(CostLife(QConst(1)),))
        kicker = Cost(parts=(CostManaColor("R", QConst(2)),))
        s1 = SpellAbility(
            kind=SpellKind.CREATURE, effect=None, additional_costs=(tap_cost, kicker)
        )
        s2 = SpellAbility(
            kind=SpellKind.CREATURE, effect=None, additional_costs=(kicker, tap_cost)
        )
        self.assertEqual(canonical_json(s1), canonical_json(s2))  # R1b canonicalization
        want = tuple(sorted((tap_cost, kicker), key=canonical_json))
        self.assertEqual(s1.additional_costs, want)


# ---------------------------------------------------------------------------
# (i) Two-failing-part precedence: canonical order pins ONE failure string
# ---------------------------------------------------------------------------
class TestTwoFailingParts(R1bCase):
    def test_permuted_construction_lands_on_one_failure_string(self):
        """DEVIATION (truth-over-instructions, reported): the task brief's
        example (CostManaColor + CostManaGeneric) is ORDER-FREE even
        pre-sort — the generic shortfall is a POST-loop aggregate, so both
        constructions already fail on the mana string and the battery leg
        could never be RED. The genuine multi-failing pair is two
        IN-LOOP failures: CostLife (fails at its branch) + CostManaColor
        (fails at its branch) — printed order picks the life string,
        canonical order picks the mana string. Canonical order here:
        canonical_json(CostManaColor(W,1)) starts '"value":1',
        CostLife(25) starts '"value":2 ⇒ mana sorts FIRST ⇒ pinned failure
        is the mana string. D11: the choice is diagnostic-only; production
        consumers are ``is None`` tests (spec §1(a)/A4)."""
        life = CostLife(QConst(25))  # 20 life < 25 — fails in-loop
        mana = CostManaColor("W", QConst(1))  # empty pool — fails in-loop
        printed = Cost(parts=(life, mana))  # printed: life first
        permuted = Cost(parts=(mana, life))
        self.assertEqual(canonical_json(printed), canonical_json(permuted))
        plan_a, reason_a = self.plan(printed)
        plan_b, reason_b = self.plan(permuted)
        self.assertIsNone(plan_a)  # identical plan
        self.assertIsNone(plan_b)
        self.assertEqual(reason_a, reason_b)
        self.assertEqual(reason_a, "cost:mana:W:0<1")  # canonical precedence

    def test_payable_variant_plan_is_identical(self):
        life = CostLife(QConst(5))
        mana = CostManaColor("W", QConst(1))
        self.pool(self.p0, W=1)
        plan_a, reason_a = self.plan(Cost(parts=(life, mana)))
        plan_b, reason_b = self.plan(Cost(parts=(mana, life)))
        self.assertIsNone(reason_a)
        self.assertIsNone(reason_b)
        self.assertEqual(repr(plan_a), repr(plan_b))
        self.assertEqual(plan_a.mana, (("W", 1),))
        self.assertEqual(plan_a.life, 5)


# ---------------------------------------------------------------------------
# (ii) Hybrid determinism probe — D10 pinned, semantics deferred
# ---------------------------------------------------------------------------
class TestHybridDeterminism(R1bCase):
    def test_wb_plus_wu_with_pool_w1_b1_is_deterministic(self):
        """D10 ({W/B}+{W/U}, pool W:1 B:1): the greedy canonical witness
        pays IFF the favorable processing order is taken — CR-UNFAITHFUL,
        population 0, RULED out-of-scope for R1b; a CR-faithful fix is the
        engine-lane bipartite/matching item. R1b pins only that the
        OUTCOME IS DETERMINISTIC under the canonical sorted order:
        colors sort (witness prefers its FIRST slot ⇒ alphabetically-first
        colour), parts sort {W/B} before {W/U} ('B' < 'U'), so the pinned
        witness is {W/B}→B then {W/U}→W — PAYABLE with mana (B:1, W:1),
        whatever the insertion order. Pre-sort this flips with insertion
        order (RED leg of this battery)."""
        wb = CostManaHybrid(colors=("W", "B"), amount=QConst(1))
        wu = CostManaHybrid(colors=("W", "U"), amount=QConst(1))
        self.pool(self.p0, W=1, B=1)
        plan_a, reason_a = self.plan(Cost(parts=(wb, wu)))
        plan_b, reason_b = self.plan(Cost(parts=(wu, wb)))
        self.assertIsNone(reason_a)  # deterministic post-sort witness outcome
        self.assertIsNone(reason_b)
        assert plan_a is not None and plan_b is not None
        self.assertEqual(repr(plan_a), repr(plan_b))
        self.assertEqual(plan_a.mana, (("B", 1), ("W", 1)))
        # the complementary shortfall stays deterministic too:
        self.world.players[self.p0].mana_pool.clear()
        self.pool(self.p0, W=1)
        plan_c, reason_c = self.plan(Cost(parts=(wb, wu)))
        plan_d, reason_d = self.plan(Cost(parts=(wu, wb)))
        self.assertIsNone(plan_c)
        self.assertIsNone(plan_d)
        self.assertEqual(reason_c, reason_d)
        # R1b canonicalization: the diagnostic embeds the CONSTRUCTION-SORTED
        # colour tuple — the printed {W/U} reports as ('U', 'W').
        self.assertEqual(reason_c, "cost:mana_hybrid:('U', 'W'):1 unpayable")


# ---------------------------------------------------------------------------
# (iii) {U}{X} + {U} discount (Stormwing Entity lane): trace invariant
# ---------------------------------------------------------------------------
class TestDiscountTraceInvariance(R1bCase):
    def _attach_discount(self, cost: Cost):
        self.ex.attach_card(
            self.alpha,
            record_of(
                [
                    ActivatedAbility(
                        cost=cost,
                        effect=Atom(
                            verb=Verb.GAIN_LIFE,
                            args=AtomArgs(
                                pairs=(
                                    ("controller", ControllerRef.YOU),
                                    ("amount", QConst(1)),
                                )
                            ),
                        ),
                    ),
                    CostModifier(
                        filter=IS_SOURCE,
                        controller_ref=ControllerRef.YOU,
                        delta=CostDeltaReduceMana("U", QConst(1)),
                    ),
                ],
                oid=self.world.cards[self.alpha].identity.oracle_id,
            ),
        )

    def _plan_folded(self, cost: Cost):
        ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0, x_value=1)
        return build_payment_plan(self.world, ctx, cost, activation=self.alpha)

    def test_payable_and_trace_invariant_under_parts_permutation(self):
        """Already-green determinism leg (spec §1(b): the per-colour
        draw is a Σ-min-clamp — payability ORDER-INVARIANT, only the
        intermediate trace could drift). {U} demand 1 minus discount 1
        ⇒ colour leg free; generic {X}=1 draws the single U mana."""
        printed = Cost(parts=(CostManaColor("U", QConst(1)), CostManaGeneric(QX())))
        permuted = Cost(parts=(CostManaGeneric(QX()), CostManaColor("U", QConst(1))))
        self._attach_discount(printed)
        self.pool(self.p0, U=1)
        plan_a, reason_a = self._plan_folded(printed)
        plan_b, reason_b = self._plan_folded(permuted)
        self.assertIsNone(reason_a)
        self.assertIsNone(reason_b)
        self.assertEqual(repr(plan_a), repr(plan_b))
        self.assertEqual(plan_a.mana, (("U", 1),))
        # failing leg: empty pool — the discount frees the {U}, the
        # GENERIC X payment is what fails; string stable under permutation
        world_b = GameWorld(num_players=2, start_life=20, master_seed=13)
        self.world.players[self.p0].mana_pool.clear()
        plan_c, reason_c = self._plan_folded(printed)
        plan_d, reason_d = self._plan_folded(permuted)
        self.assertIsNone(plan_c)
        self.assertEqual(reason_c, reason_d)
        self.assertEqual(reason_c, "cost:mana_generic:0<1")
        del world_b


# ---------------------------------------------------------------------------
# (iv) Constructed TWO-sacrifice-part Cost — ask-sequence determinism
# ---------------------------------------------------------------------------
def _sac(subtype: str) -> CostSacrifice:
    return CostSacrifice(
        target=Selector(
            QConst(1),
            SelectorMode.CHOOSE,
            FAtom(FAtomPred.SUBTYPE_EQ, string_value=subtype),
            zones=(BF_YOU,),
        )
    )


class TestTwoSacrificeAskSequence(unittest.TestCase):
    """A2 TRIPWIRE: the standing assumption is at most ONE asked-kind part
    per Cost post-fold (multi-sac population 0 in the corpus). This
    CONSTRUCTED two-sac cost is the canary: if the ask sequence ever stops
    being a pure function of the parts multiset, A2 is live and the kicker
    fold lanes need a re-audit. Each site really asks (pool 2 > need 1), so
    the sequence order IS observable — the ``sacrifice:<seat>:<source>:
    <digest>`` tags ride ex.decisions.ask_log byte-identically."""

    def _run(self, cost: Cost):
        reset_oracle_ids()  # identical oid sequence ⇒ cross-run comparable keys
        world = GameWorld(num_players=2, start_life=20, master_seed=13)
        p0 = world.player_order[0]
        source = world.add_card(card_id("Source", "1", "1"), p0, ZONE_BATTLEFIELD)
        cats = [
            world.add_card(
                card_id(f"Cat{i}", "2", "2", type_line="Creature — Cat"),
                p0,
                ZONE_BATTLEFIELD,
            )
            for i in (1, 2)
        ]
        birds = [
            world.add_card(
                card_id(f"Bird{i}", "1", "1", type_line="Creature — Bird"),
                p0,
                ZONE_BATTLEFIELD,
            )
            for i in (1, 2)
        ]
        del cats, birds  # handles ride the plan, not the test
        ex = Executor(world)
        ctx = ctx_for(ex, source=source, controller=p0)
        plan, reason = build_payment_plan(world, ctx, cost)
        assert plan is not None, reason
        ex.decisions.provider = lambda vocab, what: vocab[0]
        try:
            pay_costs(ex, plan, source=source, controller=p0)
        finally:
            ex.decisions.provider = None
        return (
            list(ex.decisions.ask_log),
            repr(plan),
            ex.state_fingerprint(),
        )

    def test_ask_sequence_is_deterministic_and_order_free(self):
        printed = Cost(parts=(_sac("Cat"), _sac("Bird")))
        permuted = Cost(parts=(_sac("Bird"), _sac("Cat")))
        log_p1, plan_p1, fp_p1 = self._run(printed)
        log_p2, plan_p2, fp_p2 = self._run(printed)  # double-run determinism
        log_q1, plan_q1, fp_q1 = self._run(permuted)  # permuted construction
        self.assertEqual(log_p1, log_p2)  # replay byte-stability
        self.assertEqual(fp_p1, fp_p2)
        self.assertEqual(len(log_p1), 2)  # BOTH sites really asked (A2 canary)
        self.assertTrue(all(what.startswith("sacrifice:") for what, _ in log_p1))
        self.assertEqual(log_p1, log_q1)  # multiset, not insertion order
        self.assertEqual(plan_p1, plan_q1)
        self.assertEqual(fp_p1, fp_q1)


if __name__ == "__main__":
    unittest.main()
