"""Round-19c regression tests: the cast-declaration lane (wave 2 fix-b).

Each test pins the FIXED reading of one r19c root cause, and the green
behaviour the batch had to leave byte-unchanged:

1. MULTI-slot designation (Hunter's Edge / Rookie Mistake): several
   exactly-one TARGET selectors designate POSITIONALLY — the i-th entry
   fills the i-th slot — and the effect runtime shadows each atom's own
   designation (per-selector bindings, no cross-slot hijack). Under-supply
   stays loud with the designation-count shape.
2. FORCED auto-designation (Duress / Mind Rot / Peer): a spell designated
   nothing whose every slot has exactly one legal filler — the lone
   opponent TARGET_PLAYER population, or a one-candidate target — takes
   THE answer (CR 601.2c, the 18b trigger-lane convention mirrored). A
   slot that leaves a real choice stays loud.
3. The SELF-CLAUSE lane (Experimental Overload): a TARGET selector whose
   only satisfier is the source spell (IS_SOURCE over a zone the spell is
   not in yet) auto-designates the spell itself and SKIPS population
   validation — trusted by construction (CR 115.4), then relocated by the
   cast step-7 put guard.
4. take_decision lane 1 (Duress / Experimental Overload pools): a pool
   word the demanded site's vocabulary does NOT carry is never consumed —
   the site falls through to the stream/provider lanes, the word stays in
   the pool for the site it was scripted for, and the original raise
   shape survives when no lane can answer.
5. The CHOOSE handle-alias vocabulary (Duress): each singleton candidate
   row's own handle string is a legal token IN ADDITION to the positional
   index; the digest and the index lane are byte-unchanged.
6. Modes BEFORE targets (Return to Nature, CR 601.2b): a multi-slot
   Choose spell declares its mode at cast time (leading decision token or
   mode_choices), the option prunes the slot set, and the runtime Choose
   CONSUMES the declaration instead of re-asking it.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    Choose,
    ControllerRef,
    FAnd,
    FAtom,
    FAtomPred,
    OptionalEffect,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    SpellKind,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor.legality import ctx_for
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
)
from MTG_bot.core.test_executor_binding import UNIV, atom, card_id
from MTG_bot.core.test_executor_stack import ANY_ZONE, BF_ANY, HAND_OPP, StackCase

CREATURE_F = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")
ARTIFACT_F = FAtom(FAtomPred.TYPE_EQ, string_value="Artifact")
ENCHANT_F = FAtom(FAtomPred.TYPE_EQ, string_value="Enchantment")
BF_YOU = Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)


# ------------------------------------------------- 1 positional multi-slot


class PositionalMultiSlotTest(StackCase):
    def double_zap(self, name="DoubleZap"):
        """Slot 1: damage 1 to a creature YOU control. Slot 2: damage 2 to
        any creature. Two different populations — the shared union binding
        could never serve both (the reason multi-slot stayed loud)."""
        return self.give(
            name,
            SpellKind.INSTANT,
            effect=Seq(
                (
                    atom(
                        Verb.DEAL_DAMAGE,
                        target=Selector(
                            QConst(1), SelectorMode.TARGET, CREATURE_F, BF_YOU
                        ),
                        amount=QConst(1),
                    ),
                    atom(
                        Verb.DEAL_DAMAGE,
                        target=Selector(
                            QConst(1), SelectorMode.TARGET, CREATURE_F, BF_ANY
                        ),
                        amount=QConst(2),
                    ),
                )
            ),
        )

    def test_each_atom_reads_its_own_slot(self):
        mine = self.world.add_card(card_id("Mine", "1", "3"), self.p0, ZONE_BATTLEFIELD)
        theirs = self.world.add_card(
            card_id("Theirs", "1", "3"), self.p1, ZONE_BATTLEFIELD
        )
        frame = cast(self.ex, self.p0, self.double_zap(), targets=(mine, theirs))
        self.assertEqual(frame.declared_targets, (mine, theirs))
        # per-atom SHADOW: slot 1 (mine, +you filter) took the 1, slot 2
        # (any creature) took the 2 — one hijacked binding would read
        # (2, 0) or (3, missing), never this split.
        self.assertEqual(self.ex.damage[mine], 1)
        self.assertEqual(self.ex.damage[theirs], 2)

    def test_under_supply_stays_loud(self):
        mine = self.world.add_card(card_id("Mine", "1", "3"), self.p0, ZONE_BATTLEFIELD)
        with self.assertRaises(ValueError) as cm:
            cast(self.ex, self.p0, self.double_zap("DoubleZap2"), targets=(mine,))
        self.assertIn("2 TARGET slots need 2 designations", str(cm.exception))


# ------------------------------------------------- 2 forced auto-designation


class ForcedAutoDesignationTest(StackCase):
    def peer_draw(self, name="PeerDraw"):
        """Mind Rot / Peer shape: TARGET_PLAYER controller, NO TARGET
        selector — only the synthesized opponent-slot exists."""
        return self.give(
            name,
            SpellKind.SORCERY,
            type_line="Sorcery",
            effect=atom(
                Verb.DRAW, controller=ControllerRef.TARGET_PLAYER, amount=QConst(2)
            ),
        )

    def _hand(self, seat):
        return self.world.players[seat].zone(ZONE_HAND).entries

    def test_lone_opponent_target_player_is_forced(self):
        spell = self.peer_draw()
        self.world.add_card(card_id("Lib1", "1", "1"), self.p1, ZONE_LIBRARY)
        self.world.add_card(card_id("Lib2", "1", "1"), self.p1, ZONE_LIBRARY)
        hand1_before = len(self._hand(self.p1))
        hand0_before = len(self._hand(self.p0))
        frame = cast(self.ex, self.p0, spell)  # designated NOTHING
        self.assertEqual(frame.declared_targets, (self.p1,))
        # the forced filler IS the lone opponent: p1 draws, p0 untouched
        # (minus the spell itself, which the cast took out of p0's hand)
        self.assertEqual(len(self._hand(self.p1)), hand1_before + 2)
        self.assertEqual(len(self._hand(self.p0)), hand0_before - 1)

    def test_one_candidate_target_is_forced(self):
        spell = self.give(
            "ZapOnce",
            SpellKind.INSTANT,
            effect=atom(
                Verb.DEAL_DAMAGE,
                target=Selector(QConst(1), SelectorMode.TARGET, CREATURE_F, BF_ANY),
                amount=QConst(0),  # probe: the target must survive
            ),
        )
        victim = self.world.add_card(
            card_id("Only", "1", "3"), self.p1, ZONE_BATTLEFIELD
        )
        frame = cast(self.ex, self.p0, spell)
        self.assertEqual(frame.declared_targets, (victim,))

    def test_a_real_choice_stays_loud(self):
        spell = self.give(
            "ZapLoud",
            SpellKind.INSTANT,
            effect=atom(
                Verb.DEAL_DAMAGE,
                target=Selector(QConst(1), SelectorMode.TARGET, CREATURE_F, BF_ANY),
                amount=QConst(0),
            ),
        )
        self.world.add_card(card_id("C1", "1", "3"), self.p1, ZONE_BATTLEFIELD)
        self.world.add_card(card_id("C2", "1", "3"), self.p1, ZONE_BATTLEFIELD)
        with self.assertRaises(ValueError) as cm:
            cast(self.ex, self.p0, spell)
        self.assertIn("count_below_min", str(cm.exception))


# --------------------------------------------------------- 3 self-clause


class SelfClauseTest(StackCase):
    def self_finder(self, name="SelfFinder"):
        """Experimental Overload shape: a TARGET selector whose ONLY legal
        designation is the source spell itself — IS_SOURCE over p0's
        graveyard, which cannot enumerate the spell until 601.2h moves
        it (CR 115.4: every legal spell is a legal target of itself)."""
        return self.give(
            name,
            SpellKind.INSTANT,
            effect=atom(
                Verb.EXILE,
                target=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    FAnd((FAtom(FAtomPred.IS_SOURCE),)),
                    Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                ),
            ),
        )

    def test_source_self_designation_skips_population(self):
        # real graveyard content proves the filter (not the emptiness)
        # is what closes the population to zero candidates
        dummy = self.world.add_card(
            card_id("GraveInstant", type_line="Instant"),
            self.p0,
            ZONE_GRAVEYARD,
        )
        spell = self.self_finder()
        cast(self.ex, self.p0, spell)  # designated NOTHING
        self.assertEqual(self.world.zone_of(spell).kind, ZONE_EXILE)
        self.assertEqual(self.world.zone_of(dummy).kind, ZONE_GRAVEYARD)


# ------------------------------------------------- 4 decision lane 1


class DecisionLaneTest(StackCase):
    def test_mismatched_word_is_never_consumed(self):
        spell = self.give("LaneSpell", SpellKind.INSTANT)
        ctx = ctx_for(self.ex, source=spell, controller=self.p0)
        ctx.decisions = ("prey",)
        ctx.stream = None
        with self.assertRaises(ValueError) as cm:
            ctx.take_decision(("fire", "skip"), "may")
        # the ORIGINAL raise shape (test_executor_games pins this text)
        self.assertIn("may decision 'prey' not in", str(cm.exception))
        self.assertEqual(ctx.decision_idx, 0)  # the word was NOT eaten
        # ... and it is still there for the site it was scripted for
        self.assertEqual(ctx.take_decision(("prey", "sheep"), "choose:x"), "prey")

    def test_provider_answers_the_mismatched_site(self):
        spell = self.give("LaneSpell2", SpellKind.INSTANT)
        ctx = ctx_for(self.ex, source=spell, controller=self.p0)
        ctx.decisions = ("prey",)
        ctx.stream = self.ex.decisions
        ctx.stream.provider = lambda vocab, what: "skip"
        # lane 1 cannot serve "may" — falls through to the provider...
        self.assertEqual(ctx.take_decision(("fire", "skip"), "may"), "skip")
        # ...the pool word survived the fall
        self.assertEqual(ctx.take_decision(("prey", "sheep"), "choose:x"), "prey")

    def test_pool_word_flows_to_its_own_site(self):
        # Duress interaction end-to-end: a may-offer asked FIRST must not
        # eat the card-name token scripted for the LATER Choose site.
        pool = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, HAND_OPP)
        result = Selector(
            QConst(1), SelectorMode.CHOOSE, UNIV, ANY_ZONE, referent="result"
        )
        spell = self.give(
            "MayDuress",
            SpellKind.SORCERY,
            type_line="Sorcery",
            effect=Seq(
                (
                    OptionalEffect(
                        atom(
                            Verb.DEAL_DAMAGE,
                            target=Selector(
                                QConst(1), SelectorMode.TARGET, CREATURE_F, BF_ANY
                            ),
                            amount=QConst(1),
                        )
                    ),
                    atom(Verb.CHOOSE, target=pool, count=QConst(1)),
                    atom(
                        Verb.DISCARD,
                        controller=ControllerRef.TARGET_PLAYER,
                        cards=result,
                    ),
                )
            ),
        )
        # ONE creature -> the may-slot's one candidate auto-fills alongside
        # the lone-opponent TARGET_PLAYER slot (both forced, positional);
        # the pool carries only the CHOOSE site's handle token.
        scout = self.world.add_card(
            card_id("Scout", "1", "3"), self.p1, ZONE_BATTLEFIELD
        )
        prey = self.world.add_card(card_id("Prey", "1", "1"), self.p1, ZONE_HAND)
        self.ex.decisions.provider = lambda vocab, what: "skip"
        cast(self.ex, self.p0, spell, decisions=(str(prey),))
        self.assertEqual(self.ex.damage.get(scout, 0), 0)  # the may was SKIPPED
        self.assertEqual(self.world.zone_of(prey).kind, ZONE_GRAVEYARD)  # name honoured


# ---------------------------------------------------- 5 choose alias vocab


class ChooseAliasTest(StackCase):
    def duress(self, name):
        pool = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, HAND_OPP)
        result = Selector(
            QConst(1), SelectorMode.CHOOSE, UNIV, ANY_ZONE, referent="result"
        )
        effect = Seq(
            (
                atom(Verb.CHOOSE, target=pool, count=QConst(1)),
                atom(
                    Verb.DISCARD, controller=ControllerRef.TARGET_PLAYER, cards=result
                ),
            )
        )
        return self.give(name, SpellKind.SORCERY, type_line="Sorcery", effect=effect)

    def test_handle_token_picks_its_row(self):
        spell = self.duress("AliasDuress")
        h1 = self.world.add_card(card_id("HandOne", "1", "1"), self.p1, ZONE_HAND)
        h2 = self.world.add_card(card_id("HandTwo", "1", "1"), self.p1, ZONE_HAND)
        first, second = sorted([h1, h2])
        # a HANDLE string is a legal token (the provider's resolution lane)
        cast(self.ex, self.p0, spell, targets=(self.p1,), decisions=(str(first),))
        self.assertEqual(self.world.zone_of(first).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(second).kind, ZONE_HAND)

    def test_index_lane_byte_unchanged(self):
        spell = self.duress("IndexDuress")
        h1 = self.world.add_card(card_id("HandOne", "1", "1"), self.p1, ZONE_HAND)
        h2 = self.world.add_card(card_id("HandTwo", "1", "1"), self.p1, ZONE_HAND)
        first, second = sorted([h1, h2])
        cast(self.ex, self.p0, spell, targets=(self.p1,), decisions=("1",))
        self.assertEqual(self.world.zone_of(second).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(first).kind, ZONE_HAND)

    def test_word_not_in_any_lane_stays_loud(self):
        spell = self.duress("LoudDuress")
        self.world.add_card(card_id("HandOne", "1", "1"), self.p1, ZONE_HAND)
        with self.assertRaises(ValueError) as cm:
            cast(self.ex, self.p0, spell, targets=(self.p1,), decisions=("nonsense",))
        self.assertIn("not in", str(cm.exception))


# ------------------------------------------------- 6 modes before targets


class PrechosenModesTest(StackCase):
    def rtn(self, name="Returnish"):
        """Return to Nature shape: Choose{ destroy artifact | destroy
        enchantment }, one exactly-one TARGET slot per option."""
        return self.give(
            name,
            SpellKind.INSTANT,
            effect=Choose(
                QConst(1),
                (
                    atom(
                        Verb.DESTROY,
                        target=Selector(
                            QConst(1), SelectorMode.TARGET, ARTIFACT_F, BF_ANY
                        ),
                    ),
                    atom(
                        Verb.DESTROY,
                        target=Selector(
                            QConst(1), SelectorMode.TARGET, ENCHANT_F, BF_ANY
                        ),
                    ),
                ),
            ),
        )

    def _board(self):
        orb = self.world.add_card(
            card_id("Dummy Orb", "1", "1", type_line="Artifact"),
            self.p1,
            ZONE_BATTLEFIELD,
        )
        aura = self.world.add_card(
            card_id("Aura Thing", type_line="Enchantment"),
            self.p1,
            ZONE_BATTLEFIELD,
        )
        return orb, aura

    def test_declared_mode_prunes_and_is_not_rebilled(self):
        orb, aura = self._board()
        # a pool word the may-lane cannot answer pins "no re-ask": if the
        # runtime Choose demanded its token AGAIN, the exhausted pool
        # would raise and the cast would fail.
        self.ex.decisions.provider = None
        cast(self.ex, self.p0, self.rtn(), targets=(orb,), decisions=("0",))
        self.assertEqual(self.world.zone_of(orb).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(aura).kind, ZONE_BATTLEFIELD)

    def test_mode_choices_kwarg_lane(self):
        orb, aura = self._board()
        cast(
            self.ex,
            self.p0,
            self.rtn("Returnish2"),
            mode_choices=(0,),
            targets=(orb,),
        )
        self.assertEqual(self.world.zone_of(orb).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(aura).kind, ZONE_BATTLEFIELD)

    def test_second_option_lane(self):
        orb, aura = self._board()
        cast(
            self.ex, self.p0, self.rtn("Returnish3"), targets=(aura,), decisions=("1",)
        )
        self.assertEqual(self.world.zone_of(aura).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(orb).kind, ZONE_BATTLEFIELD)

    def test_undeclared_mode_stays_loud(self):
        orb, _ = self._board()
        with self.assertRaises(ValueError) as cm:
            cast(self.ex, self.p0, self.rtn("Returnish4"), targets=(orb,))
        self.assertIn("must declare its mode", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
