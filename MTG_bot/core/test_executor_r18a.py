"""Printed semantics that must not be lost without a raise.

1. The if-do gate (CR 611.1, 118.12): "you may X. If you do, Y" runs Y only
   when X was done (Crypt Lurker does not draw after a skipped sacrifice).
   The compiler merges the tail as ``Conditional(MAY_DONE, Y)``, and the
   executor answers MAY_DONE by CONSUMING the logged may-offer outcome — it
   never re-asks the question.
2. The offer gate: ``optional_offer`` narrows a may-offer to ``("skip",)``
   only when a branch has ZERO candidates (CR 117.3). An UNDERSUPPLIED
   exact-count selector (wanted 2, had 1) keeps both branches, since the
   runtime CHOOSE resolves what exists, and a population a SEARCH produces
   MID-effect (a re-search tail, the result register) never gates.
3. A FILTERED library->hand MOVE tail is the search result designation,
   never the blind top-n draw idiom.
4. Turret Ogre / Garruk's Uprising: the "if you control (another) a
   creature with power 4 or greater" gates read the battlefield population.
"""

import unittest

from MTG_bot.core.ability_tree import (
    Conditional,
    ControllerRef,
    FAnd,
    FAtom,
    FAtomPred,
    OptionalEffect,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.query import MAY_VOCAB, optional_offer
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import (
    HAND_YOU,
    LIB_YOU,
    UNIV,
    card_id,
    reset_oracle_ids,
)
from MTG_bot.core.test_executor_query import atom, record


def _gain(n: int):
    return atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(n))


def _this() -> Selector:
    """ "it" / "~": the source on the battlefield (the compiler's self-reference)."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(FAtomPred.IS_SOURCE),
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )


def _exile() -> Zone:
    return Zone(ZoneKind.EXILE, ControllerRef.OWNER)


class IfDoGateTest(unittest.TestCase):
    """Class 1 (CR 611.1): the tail runs iff the may answer was 'fire'."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=18)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.src = self.world.add_card(
            card_id("Lurker", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)
        self.plan = Seq(
            steps=(
                OptionalEffect(inner=_gain(2)),
                Conditional(FAtom(FAtomPred.MAY_DONE), _gain(5)),
            )
        )

    def life(self) -> int:
        return self.world.players[self.p0].life

    def test_fire_runs_the_tail(self):
        self.ex.apply_effect(
            self.plan, source=self.src, controller=self.p0, decisions=("fire",)
        )
        self.assertEqual(self.life(), 20 + 2 + 5)

    def test_skip_gates_the_tail(self):
        # Answering skip must NOT deliver the tail.
        self.ex.apply_effect(
            self.plan, source=self.src, controller=self.p0, decisions=("skip",)
        )
        # skip removes the ACTION (2) AND the gated tail (5): the printed
        # "if you do" never pays out on a skipped optional.
        self.assertEqual(self.life(), 20)

    def test_latest_may_answer_wins(self):
        # Two may-offers at the SAME site (same source): the if-do guard
        # consumes the LATEST logged answer, not the first.
        plan = Seq(
            steps=(
                OptionalEffect(inner=_gain(2)),
                OptionalEffect(inner=_gain(3)),
                Conditional(FAtom(FAtomPred.MAY_DONE), _gain(5)),
            )
        )
        self.ex.apply_effect(
            plan, source=self.src, controller=self.p0, decisions=("skip", "fire")
        )
        # first optional skipped (0), second fired (+3), tail gated on the
        # LATEST answer 'fire' (+5).
        self.assertEqual(self.life(), 20 + 3 + 5)

    def test_a_mandatory_step_that_happened_runs_the_tail(self):
        # CR 118.12: "[Do something]. If you do" asks whether the mandatory step actually
        # happened. Exiling the source changes the game.
        plan = Seq(
            steps=(
                atom(Verb.MOVE_ZONE, target=_this(), destination=_exile()),
                Conditional(FAtom(FAtomPred.MAY_DONE), _gain(4)),
            )
        )
        self.ex.apply_effect(plan, source=self.src, controller=self.p0)
        self.assertEqual(self.world.zone_of(self.src).kind, ZONE_EXILE)
        self.assertEqual(self.life(), 20 + 4)

    def test_a_mandatory_step_that_did_nothing_gates_the_tail(self):
        # The source already left the battlefield (Archfiend's Vessel bounced before its
        # trigger resolved, CR 400.7): "exile it" does nothing, so the tail does not run.
        self.world.move_card(self.src, self.world.players[self.p0].zone(ZONE_HAND))
        plan = Seq(
            steps=(
                atom(Verb.MOVE_ZONE, target=_this(), destination=_exile()),
                Conditional(FAtom(FAtomPred.MAY_DONE), _gain(4)),
            )
        )
        self.ex.apply_effect(plan, source=self.src, controller=self.p0)
        self.assertEqual(self.world.zone_of(self.src).kind, ZONE_HAND)
        self.assertEqual(self.life(), 20)

    def test_may_done_without_an_antecedent_is_loud(self):
        # Unanswered question — flagged, never guessed False (FLIP_WON
        # convention): a MAY_DONE Conditional with no may-offer at its site.
        with self.assertRaises(NotImplementedError):
            self.ex.apply_effect(
                Conditional(FAtom(FAtomPred.MAY_DONE), _gain(5)),
                source=self.src,
                controller=self.p0,
            )

    def test_compiled_lurker_gates_its_draw(self):
        # The REAL compiled row (golden file): the continuation is the
        # gated Conditional, not a free-rider sibling.
        rec = record("Crypt Lurker")
        first = rec.abilities[0]
        assert isinstance(first, TriggeredAbility)
        effect = first.effect
        assert isinstance(effect, Seq)
        tail = effect.steps[-1]
        self.assertIsInstance(tail, Conditional)
        assert isinstance(tail, Conditional)
        assert isinstance(tail.pred, FAtom)
        self.assertIs(tail.pred.pred, FAtomPred.MAY_DONE)
        self.assertIsInstance(effect.steps[0], OptionalEffect)


class OfferGateTest(unittest.TestCase):
    """Class 2 (CR 117.3): only ILLEGAL branches narrow the offer."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=19)
        self.p0, _ = self.world.player_order[0], self.world.player_order[1]
        self.src = self.world.add_card(
            card_id("Hound", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)

    def offer(self, inner) -> tuple:
        return optional_offer(
            self.ex, OptionalEffect(inner=inner), source=self.src, controller=self.p0
        )

    def test_undersupplied_exact_count_keeps_both_branches(self):
        # Alpine Houndmaster's compile: WANT two named, the library holds
        # ONE — the runtime CHOOSE takes the one there is, so the offer
        # must NOT be stolen.
        self.world.add_card(card_id("Watchdog", "2", "2"), self.p0, ZONE_LIBRARY)
        sel = Selector(
            QConst(2),
            SelectorMode.CHOOSE,
            FAtom(FAtomPred.NAME_EQ, string_value="Watchdog"),
            zones=(LIB_YOU,),
        )
        self.assertEqual(
            self.offer(
                atom(
                    Verb.SEARCH,
                    cards=sel,
                    destination=Zone(ZoneKind.HAND, ControllerRef.YOU),
                )
            ),
            MAY_VOCAB,
        )

    def test_zero_candidates_still_narrows(self):
        # CR 117.3 preserved: nothing to discard -> skip-only.
        sel = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(HAND_YOU,))
        self.assertEqual(
            self.offer(atom(Verb.DISCARD, cards=sel, controller=ControllerRef.YOU)),
            ("skip",),
        )

    def test_search_tail_is_not_gated_pre_execution(self):
        # Chandra's Firemaw shape: the MOVE tail's pre-execution population
        # (library top) is empty BECAUSE THE SEARCH produces it — the tail
        # must not erase the branch when the SEARCH itself has a hit.
        self.world.add_card(card_id("Catalyst", "1", "1"), self.p0, ZONE_GRAVEYARD)
        for card in range(3):
            self.world.add_card(card_id(f"L{card}", "1", "1"), self.p0, ZONE_LIBRARY)
        search = atom(
            Verb.SEARCH,
            cards=Selector(
                QConst(1),
                SelectorMode.CHOOSE,
                FAtom(FAtomPred.NAME_EQ, string_value="Catalyst"),
                zones=(LIB_YOU, *(Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),)),
            ),
            destination=Zone(ZoneKind.HAND, ControllerRef.YOU),
        )
        tail = atom(
            Verb.MOVE_ZONE,
            cards=Selector(
                QConst(1),
                SelectorMode.CHOOSE,
                FAtom(FAtomPred.IS_SOURCE),
                zones=(Zone(ZoneKind.LIBRARY, ControllerRef.YOU),),
            ),
            destination=Zone(ZoneKind.HAND, ControllerRef.YOU),
        )
        self.assertEqual(self.offer(Seq(steps=(search, tail))), MAY_VOCAB)
        # ... and the honest no-hit world still narrows (SEARCH gates, 0).
        self.world.players[self.p0].zone(ZONE_GRAVEYARD).entries.clear()
        self.assertEqual(self.offer(Seq(steps=(search, tail))), ("skip",))

    def test_result_referent_tail_is_not_gated_pre_execution(self):
        # Teferi's Wavecaster shape: the tail reads the result register the
        # SEARCH writes mid-execution — no pre-execution candidates exist
        # BY DESIGN (the result register), so the gate must not consume the ask.
        search = atom(
            Verb.SEARCH,
            cards=Selector(
                QConst(1),
                SelectorMode.CHOOSE,
                FAtom(FAtomPred.NAME_EQ, string_value="Tvasa"),
                zones=(LIB_YOU,),
            ),
            destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
        )
        tail = atom(
            Verb.GAIN_LIFE,
            controller=ControllerRef.YOU,
            amount=QConst(1),
        )
        move = atom(  # referent-selector variant (register read; neutral zone)
            Verb.MOVE_ZONE,
            cards=Selector(
                QConst(1),
                SelectorMode.CHOOSE,
                UNIV,
                zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
                referent="result",
            ),
            destination=Zone(ZoneKind.HAND, ControllerRef.YOU),
        )
        self.world.add_card(card_id("Tvasa", "1", "1"), self.p0, ZONE_LIBRARY)
        self.assertEqual(self.offer(Seq(steps=(search, tail, move))), MAY_VOCAB)


class FilteredMoveTailTest(unittest.TestCase):
    """Class 3: a FILTERED library->hand MOVE tail is the search result
    designation, never the blind top-n draw idiom."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=20)
        self.p0, _ = self.world.player_order[0], self.world.player_order[1]
        self.src = self.world.add_card(
            card_id("Steed", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)
        self.top = self.world.add_card(card_id("Top", "1", "1"), self.p0, ZONE_LIBRARY)
        self.bottom = self.world.add_card(
            card_id("Bottom", "1", "1"), self.p0, ZONE_LIBRARY
        )

    def test_filtered_tail_moves_nothing_when_nothing_matches(self):
        lib = self.world.players[self.p0].zone(ZONE_LIBRARY)
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=Selector(
                    QConst(1),
                    SelectorMode.CHOOSE,
                    FAtom(FAtomPred.NAME_EQ, string_value="Nowhere"),
                    zones=(LIB_YOU,),
                ),
                destination=Zone(ZoneKind.HAND, ControllerRef.YOU),
            ),
            source=self.src,
            controller=self.p0,
        )
        # Nothing matches NAME_EQ, so nothing moves (the blind draw idiom
        # would take the top card): the library keeps BOTH cards in
        # insertion order (self.bottom is the top entry).
        self.assertEqual(lib.entries, [self.top, self.bottom])
        self.assertEqual(self.world.players[self.p0].zone(ZONE_HAND).entries, [])

    def test_unfiltered_top_move_still_draws(self):
        # The DRAW idiom (unfiltered, referent-less) takes the top card.
        # Top of library = last inserted = self.bottom.
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(LIB_YOU,)),
                destination=Zone(ZoneKind.HAND, ControllerRef.YOU),
            ),
            source=self.src,
            controller=self.p0,
        )
        self.assertEqual(
            self.world.players[self.p0].zone(ZONE_HAND).entries, [self.bottom]
        )


class CompilerMergeTest(unittest.TestCase):
    """Class 1 compiler half: WHERE the gate is attached."""

    def test_optional_seam_gets_the_gate(self):
        from MTG_bot.core.compiler.compiler import _merge_if_do_continuation

        merged = _merge_if_do_continuation(
            OptionalEffect(inner=_gain(1)), _gain(5), "If you do, gain 5 life."
        )
        assert isinstance(merged, Seq)
        gate = merged.steps[-1]
        self.assertIsInstance(gate, Conditional)
        assert isinstance(gate, Conditional)
        assert isinstance(gate.pred, FAtom)
        self.assertIs(gate.pred.pred, FAtomPred.MAY_DONE)
        self.assertIs(gate.else_effect, None)

    def test_mandatory_seam_is_gated_too(self):
        from MTG_bot.core.compiler.compiler import _merge_if_do_continuation

        merged = _merge_if_do_continuation(
            _gain(1),  # mandatory antecedent (no optional seam)
            _gain(4),
            "If you do, gain 4 life.",
        )
        assert isinstance(merged, Seq)
        # CR 118.12 reads a mandatory "[Do something]. If you do" as it reads the "may" form
        # (did the player do it), so the tail is the same Conditional(MAY_DONE, tail): one
        # meaning, one encoding. A plain sibling would run even when the antecedent could not
        # be done (Archfiend's Vessel's Demon after the Vessel left the battlefield).
        self.assertEqual(len(merged.steps), 2)
        gate = merged.steps[-1]
        assert isinstance(gate, Conditional)
        assert isinstance(gate.pred, FAtom)
        self.assertIs(gate.pred.pred, FAtomPred.MAY_DONE)
        self.assertEqual(gate.then_effect, _gain(4))
        self.assertIs(gate.else_effect, None)

    def test_may_bearing_tail_keeps_its_inner_optional(self):
        from MTG_bot.core.compiler.compiler import _merge_if_do_continuation

        merged = _merge_if_do_continuation(
            OptionalEffect(inner=_gain(1)), _gain(5), "If you do, you may gain 5 life."
        )
        assert isinstance(merged, Seq)
        gate = merged.steps[-1]
        assert isinstance(gate, Conditional)
        self.assertIsInstance(gate.then_effect, OptionalEffect)

    def test_turret_and_uprising_conditions_are_existential(self):
        # Class 4: the "if you control (another) a creature with power
        # N+" gates read the battlefield POPULATION (count 1), not the
        # ability's own source.
        for name in ("Turret Ogre", "Garruk's Uprising"):
            rec = record(name)
            first = rec.abilities[0]
            assert isinstance(first, TriggeredAbility)
            cond = first.condition
            assert isinstance(cond, FAtom)
            self.assertIs(cond.pred, FAtomPred.CONTROLLER_COUNT_GE)
            self.assertEqual(cond.count, QConst(1))
            inner = cond.inner_filter
            self.assertTrue(isinstance(inner, FAnd) and len(inner.children) >= 1)
            power = [
                c
                for c in (inner.children if isinstance(inner, FAnd) else ())
                if isinstance(c, FAtom) and c.pred is FAtomPred.POWER_GE
            ]
            self.assertEqual(power[0].count, QConst(4))


if __name__ == "__main__":
    unittest.main()
