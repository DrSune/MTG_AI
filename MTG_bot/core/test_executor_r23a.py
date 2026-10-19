"""r23a — executor fix batch against the seven crash classes the C4
creature-emission campaign exposed (reports/games_2026-10-02.json, 17
crash games over 100 seeds; every one pinned here or by a promoted pack).

The batch, class by class:

* TARGETS_SOURCE (quantity.py) — the Pursued Whale cost-fold filter
  "spells that target this creature" now reads the judge's designation
  (the mirror of IS_ANY_TARGET). Pinned at the filter level below; the
  end-to-end fold (Titanic Growth costs {3} more targeting the enemy 8/8)
  is the promoted ``targets_source_cost_fold`` pack.
* Event register at designation (binding.py ``_designate``) — the 18b
  TARGET-designation now passes the firing's bindings into
  ``legal_targets``, so a referent-"event" selector (landfall-style
  prompts) enumerates its bound object instead of raising "no register".
* QX→ETB (etb_x ledger), FLASH window, the GAIN_LIFE guarded static, the
  TARGET_PLAYER activation slots and the may-offer CAST gate — the two
  former suspects ``wildwood_scourge`` (cast x=2 lane) and
  ``flash_window_engine_gap`` are promoted packs; the static guard is
  ``rin_seri_static_guard``. The tripwire quarantine is pinned in
  test_executor_binding (amended) and by games seeds 17/50.
* COLOR_COUNT_GE (quantity.py ``_eval_atom``) — the class the TARGETS_SOURCE
  fix EXPOSED (seeds 26/33/95 survived their old crash and died one query
  later): Basri's Lieutenant "protection from multicolored" read by the
  block gate, and Ugin's "-X: each permanent ... that's one or more
  colors". The subject simply has COUNT or more colors, off the same
  identity data as the COLOR_HAS/COLOR_IN twin.
"""

import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    FAtom,
    FAtomPred,
    OptionalEffect,
    QConst,
    Selector,
    SelectorMode,
    SpellAbility,
    SpellKind,
    StaticAbility,
    Verb,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.durations_min import DurationLedger
from MTG_bot.core.executor.quantity import ExecCtx, eval_filter
from MTG_bot.core.executor.query import (
    MAY_VOCAB,
    activation_target_slots,
    legal_targets,
    optional_offer,
)
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_LIBRARY, GameWorld
from MTG_bot.core.test_executor_binding import (
    HAND_YOU,
    LIB_YOU,
    UNIV,
    atom,
    card_id,
    record_of,
    referent_sel,
    reset_oracle_ids,
)


class R23ACase(unittest.TestCase):
    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=23)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.whale = self.world.add_card(
            card_id("Pursued Whale", "8", "8"), self.p1, ZONE_BATTLEFIELD
        )
        self.spell = self.world.add_card(card_id("Titanic Growth"), self.p0)
        self.urn = self.world.add_card(
            card_id("Urn", type_line="Artifact"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)


class TestTargetsSourceFold(R23ACase):
    """The cost-fold predicate, read in the modifier host's coordinates."""

    def _ctx(self, *, source, bindings=None, designation=None) -> ExecCtx:
        return ExecCtx(
            world=self.world,
            ledger=DurationLedger(),
            controller=self.p0,
            source=source,
            bindings=bindings or {},
            decisions=(),
            designation_union=designation,
        )

    def test_bare_ctx_reads_conservative_false(self):
        # Pre-601.2d target declaration there is NO designation — the
        # printed cost shows (the honest +{3} lands at payment, where the
        # fold re-runs with bindings). r23a replaced the 12c raise.
        f = FAtom(FAtomPred.TARGETS_SOURCE)
        self.assertFalse(eval_filter(f, self.spell, self._ctx(source=self.whale)))

    def test_host_among_bound_targets_is_true(self):
        # The payment-time fold: stack.cast journaled bindings["target"] =
        # the designated objects; the host (Whale) is one of them.
        f = FAtom(FAtomPred.TARGETS_SOURCE)
        ctx = self._ctx(source=self.whale, bindings={"target": [self.whale]})
        self.assertTrue(eval_filter(f, self.spell, ctx))

    def test_other_bound_target_is_false(self):
        f = FAtom(FAtomPred.TARGETS_SOURCE)
        ctx = self._ctx(source=self.whale, bindings={"target": [self.urn]})
        self.assertFalse(eval_filter(f, self.spell, ctx))

    def test_designation_union_mirror_wins_over_bindings(self):
        # The 18b designation channel is the authoritative reading when
        # present (same union IS_ANY_TARGET consults).
        f = FAtom(FAtomPred.TARGETS_SOURCE)
        ctx = self._ctx(source=self.whale, designation=(self.whale,))
        self.assertTrue(eval_filter(f, self.spell, ctx))


class TestEventRegisterAtDesignation(R23ACase):
    """18b TARGET-designation feeds the firing's bindings to the oracle."""

    def test_referent_event_selector_enumerates_bound_object(self):
        sel = referent_sel("event", UNIV)
        slot = legal_targets(
            self.world,
            self.ex,
            sel,
            source=self.urn,
            controller=self.p0,
            bindings={"event": self.whale},
        )
        self.assertIn(self.whale, slot.candidates)

    def test_unset_referent_stays_the_loud_flag(self):
        # C15 honesty preserved: WITHOUT bindings there is genuinely no
        # register — an unset referent read raises naming it, never a
        # guessed empty population.
        sel = referent_sel("event", UNIV)
        with self.assertRaises(NotImplementedError):
            legal_targets(self.world, self.ex, sel, source=self.urn, controller=self.p0)


class TestActivationTargetPlayerSlots(R23ACase):
    """Liliana's Steward shape: a TARGET_PLAYER coordinate with NO
    TARGET-mode selector — the games activation lane must still offer the
    opponent-seat slot the spell lane synthesizes."""

    def test_target_player_coordinate_synthesizes_the_opponent_slot(self):
        effect = atom(
            Verb.DISCARD,
            cards=Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(HAND_YOU,)),
            controller=ControllerRef.TARGET_PLAYER,
        )
        slots = activation_target_slots(self.ex, effect, source=self.urn, seat=self.p0)
        self.assertEqual(len(slots), 1)
        slot = slots[0]
        self.assertTrue(slot.synthetic)
        self.assertEqual(slot.candidates, (self.p1,))
        self.assertEqual((slot.min_count, slot.max_count), (1, 1))

    def test_no_target_coordinate_no_slots(self):
        effect = atom(Verb.DRAW, amount=QConst(1), controller=ControllerRef.YOU)
        self.assertEqual(
            activation_target_slots(self.ex, effect, source=self.urn, seat=self.p0),
            [],
        )


class TestMayOfferCastGate(R23ACase):
    """Radha's optional CAST over the library: CR 117.3 narrows the offer
    to skip when the population holds no SpellAbility carrier, and only
    then — a land is a CR 305 special action, not a cast."""

    def _may_cast_library(self) -> OptionalEffect:
        return OptionalEffect(
            inner=atom(
                Verb.CAST,
                source=Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(LIB_YOU,)),
            )
        )

    def test_land_only_library_narrows_the_offer_to_skip(self):
        self.world.add_card(card_id("Island", type_line="Land"), self.p0, ZONE_LIBRARY)
        self.assertEqual(
            optional_offer(
                self.ex, self._may_cast_library(), source=self.urn, controller=self.p0
            ),
            MAY_VOCAB[1:],
        )

    def test_a_spell_carrier_restores_the_full_offer(self):
        # AMENDED /125 (shadow seed 777003 lane): the CHOOSE(1) stand-in
        # casts the sorted-FIRST candidate, so the carrier must be the
        # card the designation lane actually takes. The fixture's
        # Titanic Growth (an instant, card:1) sorts FIRST in the library,
        # so the pre-amendment shape — only Bolt registered — offered
        # fire on a population whose designee was the UNREGISTERED
        # Titanic Growth: the runtime cast_card raises there ('no
        # compiled record'), a phantom fire (no-phantom law /10). The
        # pin's intent stands — a spell carrier the designee lane will
        # actually cast restores the full offer — now carried by the
        # designee itself. Land-first/impossible-designee narrowing is
        # pinned in test_executor_cast_payability.py.
        self.world.add_card(card_id("Island", type_line="Land"), self.p0, ZONE_LIBRARY)
        bolt = self.world.add_card(
            card_id("Lightning Bolt", type_line="Instant"), self.p0, ZONE_LIBRARY
        )
        for card, name in ((self.spell, "Titanic Growth"), (bolt, "Lightning Bolt")):
            oid = self.world.cards[card].identity.oracle_id
            self.ex.binder.records[oid] = record_of(
                [SpellAbility(kind=SpellKind.INSTANT, effect=None)],
                name=name,
                oid=oid,
            )
        self.assertEqual(
            optional_offer(
                self.ex, self._may_cast_library(), source=self.urn, controller=self.p0
            ),
            MAY_VOCAB,
        )

    def test_referent_source_is_never_gated(self):
        # Snoop's "you may cast THAT card": produced mid-effect, nothing
        # enumerable pre-execution — the r18a rule, the gate must not
        # crash on it nor narrow on it.
        may = OptionalEffect(inner=atom(Verb.CAST, source=referent_sel("result", UNIV)))
        self.assertEqual(
            optional_offer(self.ex, may, source=self.urn, controller=self.p0),
            MAY_VOCAB,
        )


class TestGuardedStaticAttach(R23ACase):
    """Rin and Seri's GAIN_LIFE static: LOUD refusal at attach — recorded,
    the permanent still enters, only the parseable lane is skipped."""

    def test_unparseable_static_is_flagged_not_fatal(self):
        handle = self.world.add_card(
            card_id("Rin and Seri", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        rec = record_of(
            [
                StaticAbility(
                    effect=atom(
                        Verb.GAIN_LIFE, amount=QConst(1), controller=ControllerRef.YOU
                    )
                )
            ],
            name="Rin and Seri, Inseparable",
            oid=self.world.cards[handle].identity.oracle_id,
        )
        self.ex.attach_card(handle, rec)  # NO raise (pre-batch: killed the game)
        self.assertEqual(len(self.ex.unparseable_statics), 1)
        self.assertIn("GAIN_LIFE", self.ex.unparseable_statics[0])
        self.assertIn(str(handle), self.ex.unparseable_statics[0])


class TestColorCountGE(R23ACase):
    """COLOR_COUNT_GE — the subject simply has COUNT or more colors, read
    off identity data like the COLOR_HAS/COLOR_IN twin. Basri's Lieutenant's
    "protection from multicolored" (count=2, block gate) and Ugin's "-X:
    exile each permanent ... that's one or more colors" (count=1)."""

    def _f(self, n: int) -> FAtom:
        return FAtom(FAtomPred.COLOR_COUNT_GE, count=QConst(n))

    def test_bicoloured_meets_the_multicoloured_threshold(self):
        gold = self.world.add_card(
            card_id("Foldpair Hero", "2", "2", colors=("W", "G")),
            self.p0,
            ZONE_BATTLEFIELD,
        )
        ctx = ExecCtx(
            world=self.world,
            ledger=DurationLedger(),
            controller=self.p0,
            source=gold,
            bindings={},
            decisions=(),
        )
        self.assertTrue(eval_filter(self._f(2), gold, ctx))

    def test_monocoloured_fails_the_multicoloured_threshold(self):
        # Basri's Lieutenant herself (W) is NOT multicolored — the block
        # gate must let a white creature through the "from multicolored"
        # protection.
        ctx = ExecCtx(
            world=self.world,
            ledger=DurationLedger(),
            controller=self.p0,
            source=self.whale,
            bindings={},
            decisions=(),
        )
        self.assertFalse(eval_filter(self._f(2), self.whale, ctx))

    def test_colourless_fails_the_one_or_more_test(self):
        # Ugin's "-X" exile filter: the colorless Urn is NOT "one or more
        # colors"; the monocoloured Whale (identity colors absent in this
        # fixture's card_id default — pinned explicitly) is.
        ctx = ExecCtx(
            world=self.world,
            ledger=DurationLedger(),
            controller=self.p0,
            source=self.urn,
            bindings={},
            decisions=(),
        )
        self.assertFalse(eval_filter(self._f(1), self.urn, ctx))
        self.assertFalse(eval_filter(self._f(1), self.whale, ctx))  # no colors set

    def test_three_threshold_needs_three_colors(self):
        three = self.world.add_card(
            card_id("Naya Triple", "3", "3", colors=("R", "G", "W")),
            self.p0,
            ZONE_BATTLEFIELD,
        )
        ctx = ExecCtx(
            world=self.world,
            ledger=DurationLedger(),
            controller=self.p0,
            source=three,
            bindings={},
            decisions=(),
        )
        self.assertTrue(eval_filter(self._f(3), three, ctx))
        self.assertFalse(eval_filter(self._f(4), three, ctx))


if __name__ == "__main__":
    unittest.main()
