"""Round-20c tests: the cast/cost/attach fix batch (wave-3 suspects).

Pins the four executor fixes the scenario packs verified end to end:

* Waker of Waves (legality.py): the printed "Discard this card:" hand
  activation — the window gate opens ONLY for a cost whose HAND-zone
  selector filter demands IS_SOURCE (cycling CR 702.29a family), the
  payment plan's r19b self-exclusion carves back exactly for that IR
  shape (CR 601.2h is a CAST-cost rule), and every other activation from
  the hand stays the loud ``window:not_on_battlefield`` reason.
* Hobblefiend (selectors.py): a CHOOSE-mode selector filtered on
  IS_SOURCE is the effect's OWN self-designation (CR 602.2c) — the
  cost-side TARGET binding sharing the role name must not hijack it.
* Malefic Scythe (binding.py + quantity.py): the leave-detach sweep
  snapshots the departing host's aura set into ``executor.detach_lki``
  BEFORE pruning, and IS_ATTACHED_TO_SOURCE falls back to that LKI
  snapshot (CR 400.7) only once the judged host has LEFT the
  battlefield — on the battlefield the live table is the only word.
* Speaker of the Heavens (quantity.py + __init__.py):
  LIFE_LEAD_OVER_START_GE is a ledger read (current life minus the
  construction-time ``starting_life`` snapshot), not a LIFE_GAINED
  journal sum — a non-damage life loss leaves no journal row.
"""

import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    Cost,
    CostDiscard,
    CostTap,
    CounterKind,
    FAtom,
    FAtomPred,
    QConst,
    Selector,
    SelectorMode,
    Verb,
)
from MTG_bot.core.executor.legality import (
    ability_playable,
    activate,
    build_payment_plan,
    ctx_for,
)
from MTG_bot.core.executor.quantity import eval_filter
from MTG_bot.core.executor.selectors import role_handles
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND
from MTG_bot.core.test_executor_binding import (
    BF_YOU,
    HAND_YOU,
    IS_SOURCE,
    UNIV,
    card_id,
    record_of,
)
from MTG_bot.core.test_executor_legality import LegalityCase, ability, cost

# Fixed oracle ids for the hand-activation cards (the record registry is
# keyed by id; reset_oracle_ids() only rewinds the synthetic sequence).
WAKER_OID = "0c0ffee0-1111-2222-3333-444444444444"
TAP_FROM_HAND_OID = "0badf00d-1111-2222-3333-444444444444"
SCYTHE_OID = "5c0f6ee5-1111-2222-3333-444444444444"


def self_discard_cost() -> Cost:
    """The cycling-shape printed cost: "Discard this card" — a CHOOSE
    selector over the controller's HAND filtered on IS_SOURCE."""
    return cost(
        CostDiscard(Selector(QConst(1), SelectorMode.CHOOSE, IS_SOURCE, HAND_YOU))
    )


class TestHandSelfDiscardWindow(LegalityCase):
    """Waker fix, gate lane: the window opens for the printed hand
    activation and for nothing else."""

    def put_in_hand(self, oid: str, abil, name: str) -> Handle:
        handle = self.world.add_card(
            card_id(name, "2", "2", oid=oid), self.p0, ZONE_HAND
        )
        # A hand card is never ATTACHED (attachment is the battlefield
        # lifecycle) — the oracle-id registry is the IR source the
        # spell_record fallback reads.
        self.ex.binder.records[oid] = record_of([abil], name=name, oid=oid)
        return handle

    def test_self_discard_activation_is_legal_from_hand(self):
        h = self.put_in_hand(WAKER_OID, ability(self_discard_cost()), "Waker")
        self.assertIsNone(ability_playable(self.world, self.ex, h, 0, seat=self.p0))

    def test_self_discard_activate_pays_and_resolves(self):
        h = self.put_in_hand(WAKER_OID, ability(self_discard_cost()), "Waker")
        activate(self.ex, h, 0, seat=self.p0)
        # Cost paid: the card left hand into the graveyard (CR 400.x —
        # discarded, the ability keeps resolving from the stack lane).
        self.assertIn(h, self.world.players[self.p0].zone(ZONE_GRAVEYARD).entries)
        self.assertNotIn(h, self.world.players[self.p0].zone(ZONE_HAND).entries)
        # Effect resolved: the gain_life default fired for the controller.
        self.assertEqual(self.world.players[self.p0].life, 21)

    def test_ordinary_activation_from_hand_stays_refused(self):
        # CR 602.3 stands: no printed self-discard cost -> the loud reason.
        h = self.put_in_hand(TAP_FROM_HAND_OID, ability(cost(CostTap())), "Idle")
        self.assertEqual(
            ability_playable(self.world, self.ex, h, 0, seat=self.p0),
            f"window:not_on_battlefield:{h}",
        )

    def test_unregistered_hand_card_stays_refused(self):
        # No compiled record anywhere for the handle -> the loud
        # not_compiled reason still fires (fallback must not guess).
        h = self.world.add_card(
            card_id("Ghost", "2", "2", oid="ffffffff-1111-2222-3333-444444444444"),
            self.p0,
            ZONE_HAND,
        )
        self.assertIsNotNone(ability_playable(self.world, self.ex, h, 0, seat=self.p0))


class TestDiscardPaymentSelfLane(LegalityCase):
    """Waker fix, payment lane: build_payment_plan's r19b self-exclusion
    (CR 601.2h) carves back exactly for the self-referential IR filter."""

    def test_self_referential_discard_pays_its_own_source(self):
        h = self.world.add_card(card_id("Waker"), self.p0, ZONE_HAND)
        ctx = ctx_for(self.ex, source=h, controller=self.p0)
        plan, reason = build_payment_plan(
            self.world,
            ctx,
            cost(
                CostDiscard(
                    Selector(QConst(1), SelectorMode.CHOOSE, IS_SOURCE, HAND_YOU)
                )
            ),
        )
        assert plan is not None
        self.assertEqual((plan.discard, reason), ((h,), None))

    def test_generic_discard_still_excludes_the_casting_spell(self):
        # r19b Thrill lane regression: "discard a card" (UNIV filter) as a
        # CAST cost may never spend the spell on the stack itself.
        spell = self.world.add_card(card_id("Thriller"), self.p0, ZONE_HAND)
        other = self.world.add_card(card_id("Payoff"), self.p0, ZONE_HAND)
        ctx = ctx_for(self.ex, source=spell, controller=self.p0)
        plan, reason = build_payment_plan(self.world, ctx, self.discard_generic())
        assert plan is not None
        self.assertEqual((plan.discard, reason), ((other,), None))

    def test_generic_discard_with_only_the_spell_fails_loudly(self):
        spell = self.world.add_card(card_id("Lonely"), self.p0, ZONE_HAND)
        ctx = ctx_for(self.ex, source=spell, controller=self.p0)
        plan, reason = build_payment_plan(self.world, ctx, self.discard_generic())
        self.assertIsNone(plan)
        assert reason is not None
        self.assertIn("discard:insufficient_candidates", reason)

    @staticmethod
    def discard_generic() -> Cost:
        return cost(
            CostDiscard(Selector(QConst(1), SelectorMode.CHOOSE, UNIV, HAND_YOU))
        )


class TestSelfRefSelectorRole(LegalityCase):
    """Hobblefiend fix: the effect's IS_SOURCE self-designation is not
    hijacked by the cost TARGET binding sharing the role name."""

    def put_counter_atom(self, sel: Selector) -> Atom:
        return Atom(
            verb=Verb.PUT_COUNTER,
            args=AtomArgs(
                pairs=(
                    ("target", sel),
                    ("counter_kind", CounterKind.PAGE),
                    ("count", QConst(1)),
                )
            ),
        )

    def test_cost_binding_does_not_hijack_self_designation(self):
        ctx = ctx_for(
            self.ex,
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [self.beta]},
        )
        sel = Selector(QConst(1), SelectorMode.CHOOSE, IS_SOURCE, BF_YOU)
        self.assertEqual(
            role_handles(ctx, self.put_counter_atom(sel), "target"), [self.alpha]
        )

    def test_plain_choose_selector_stays_binding_first(self):
        # The 12a designation convention stands for every non-self filter.
        ctx = ctx_for(
            self.ex,
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [self.beta]},
        )
        sel = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, BF_YOU)
        self.assertEqual(
            role_handles(ctx, self.put_counter_atom(sel), "target"), [self.beta]
        )


class TestLeaveDetachLKI(LegalityCase):
    """Malefic Scythe fix: the departure snapshot answers IS_ATTACHED_-
    TO_SOURCE after the live table was pruned — and never while the
    judged host still stands on the battlefield."""

    def setUp(self):
        super().setUp()
        self.scythe = self.world.add_card(
            card_id("Scythe", "0", "3", type_line="Enchantment — Aura", oid=SCYTHE_OID),
            self.p0,
            ZONE_BATTLEFIELD,
        )
        self.ex.attach_aura(self.scythe, self.alpha)

    def ctx(self):
        # The filter's subject is the HOST creature; ctx.source is the aura.
        return ctx_for(self.ex, source=self.scythe, controller=self.p0)

    def test_lki_snapshot_answers_after_host_leaves(self):
        self.world.move_to_zone(self.alpha, self.p0, ZONE_GRAVEYARD)
        self.ex.binder.detach(self.alpha)  # the sweep's leave-detach entry point
        self.assertIn(self.scythe, self.ex.detach_lki[self.alpha])
        self.assertTrue(
            eval_filter(FAtom(FAtomPred.IS_ATTACHED_TO_SOURCE), self.alpha, self.ctx())
        )

    def test_live_table_governs_while_host_is_on_battlefield(self):
        # Artificial prune (host never left): the LKI row exists but must
        # NOT answer for a battlefield object — the live table says no.
        self.ex.binder.detach(self.alpha)
        self.assertIn(self.scythe, self.ex.detach_lki[self.alpha])
        self.assertFalse(
            eval_filter(FAtom(FAtomPred.IS_ATTACHED_TO_SOURCE), self.alpha, self.ctx())
        )

    def test_unrelated_host_still_false_after_snapshot(self):
        self.world.move_to_zone(self.alpha, self.p0, ZONE_GRAVEYARD)
        self.ex.binder.detach(self.alpha)
        self.assertFalse(
            eval_filter(FAtom(FAtomPred.IS_ATTACHED_TO_SOURCE), self.beta, self.ctx())
        )


class TestLifeLeadOverStart(LegalityCase):
    """Speaker fix: the gate reads current-minus-start from the ledger —
    never a LIFE_GAINED journal sum."""

    LEEAD = FAtom(FAtomPred.LIFE_LEAD_OVER_START_GE, count=QConst(7))

    def setUp(self):
        super().setUp()
        self.ctx = ctx_for(self.ex, source=self.alpha, controller=self.p0)

    def test_snapshot_at_construction(self):
        self.assertEqual(self.ex.starting_life, {self.p0: 20, self.p1: 20})

    def test_open_at_start_plus_threshold(self):
        self.world.players[self.p0].life = 27
        self.assertTrue(eval_filter(self.LEEAD, self.alpha, self.ctx))

    def test_closed_one_short(self):
        self.world.players[self.p0].life = 26
        self.assertFalse(eval_filter(self.LEEAD, self.alpha, self.ctx))

    def test_life_paid_down_closes_the_gate(self):
        # A non-damage loss (CR 118.12 payment) leaves NO journal row — a
        # gains-sum reading would still say 27 here. The ledger says 13.
        self.world.players[self.p0].life = 27
        self.assertTrue(eval_filter(self.LEEAD, self.alpha, self.ctx))
        self.world.players[self.p0].life = 13
        self.assertFalse(eval_filter(self.LEEAD, self.alpha, self.ctx))

    def test_opponent_life_is_not_mine(self):
        self.world.players[self.p1].life = 40
        self.world.players[self.p0].life = 20
        self.assertFalse(eval_filter(self.LEEAD, self.alpha, self.ctx))


if __name__ == "__main__":
    unittest.main()
