"""ZNR fuzz wave /111 → /112: the DANGLING-REFERENT cast guard, pinned.

Two live-game crashes (reports/znr_engine_smoke_2026-10-19, seeds 5/23/28)
shared one class: the compiler folded a LATER clause whose anaphora reads a
register (``result``/``target``) while the ANTECEDENT clause stayed
unparsed — so the register has no producer and the raw effect lane hits a
selectors.py referent refusal mid-cast:

* Acquisitions Expert — s1/s2 unparsed (reveal/party-quantity, "you choose
  one"), s3 folded as ``B5b-that-player-discards``: MOVE_ZONE cards =
  referent 'result'. NotImplementedError@selectors (2 fuzz hits).
* Shell Shield — s2 unparsed ("Target creature … gets +0/+3"), the kicker
  arm folded STANDALONE (compiler.py kicker fold, saw_unparsed_base law):
  the arm reads referent 'target' with no designation slot ever offered.
  ValueError@selectors (1 fuzz hit).

Fix law (r23a unparseable-statics pattern): the template fold is the bug
(root-caused + proposed fix in KNOWLEDGE/2026-10-19/112), NOT the engine —
so the raw ``_run_effect`` lane KEEPS raising (every unit contract and the
C15 "unset reads RAISE" law stay byte-identical), while every LIVE-GAME
effect lane — the four spell resolution lanes (cast/cast_card effect +
aura-effect) AND the trigger-firing lane (binding._fire, found by the
60-game rerun) — route through Executor._run_guarded_effect: a
selectors.referent_absent refusal skips the mis-shaped effect, the spell
still resolves / the game still plays, and the refusal is recorded LOUD
and deduped on ``executor.unresolved_effects``. Pinned here:

1. 'result'-dangling creature cast — completes to the battlefield, the
   discard skipped, NO zone move, one loud flag; a second copy dedupes;
2. 'target'-dangling kicked instant — completes to the graveyard, the
   damage arm skipped, ex.damage stays empty, one loud flag; the SAME card
   cast UNKICKED never flags (the skip is reached through the guarded
   branch only — WAS_KICKED really gated it);
3. producer PRESENT — Seq(TAP→MOVE_ZONE referent 'result') still resolves
   end-to-end through the guarded lane (guard never degrades a resolvable
   anaphora), no flag;
 4. every OTHER refusal (e.g. a PLAYER-zone MOVE_ZONE destination) stays
    loud through the guarded lane, sink untouched;
 5. referent_absent = dedicated ReferentAbsentError TYPE + byte-exact site
    message (r24a): typed site errors match, message look-alikes and the
    QProp referent refusal do NOT;
 6. the gate's E2E: an unrelated refusal whose text merely CONTAINS the
    marks PROPAGATES through the guarded cast lane, sink untouched;
 7. quantity's QProp 'target' refusal (mark-#1 look-alike) propagates;
 8. CR 609.7: a dangling MID-step of a top-level Seq skips only ITSELF
    (the tail still executes), the nested-Seq whole-step boundary is
    pinned as documented, and per-key OCCURRENCE counts keep distinct
    same-message atoms visible.
"""

import unittest
from unittest import mock

from MTG_bot.core.ability_tree import (
    Conditional,
    ControllerRef,
    Cost,
    CostManaColor,
    FAtom,
    FAtomPred,
    Filter,
    KickerAbility,
    QConst,
    QProp,
    QPropField,
    Selector,
    SelectorMode,
    Seq,
    SpellKind,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.executor import verbs
from MTG_bot.core.executor.selectors import (
    ReferentAbsentBindingError,
    ReferentAbsentRegisterError,
    referent_absent,
)
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND
from MTG_bot.core.test_executor_binding import (
    ANOTHER_CREATURE,
    ANY_ANY,
    BF_OWNER,
    UNIV,
    BindingCase,
    atom,
    card_id,
    enter,
)
from MTG_bot.core.test_executor_stack import StackCase

ANY_ZONE = Zone(ZoneKind.ANY, ControllerRef.ANY)
BF_YOU = Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)
CREATURE_F = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")


def referent_sel(referent: str, filter_: Filter = UNIV) -> Selector:
    return Selector(
        QConst(1), SelectorMode.CHOOSE, filter_, zones=(ANY_ZONE,), referent=referent
    )


# ------------------------------------------------- 1 dangling 'result'


class ResultDanglingCastTest(StackCase):
    """Acquisitions Expert's folded residue: a cast effect whose MOVE_ZONE
    cards role reads the 'result' register nothing produced."""

    def expert(self, name="AcqClone"):
        return self.give(
            name,
            SpellKind.CREATURE,
            effect=atom(
                Verb.MOVE_ZONE,
                destination=Zone(ZoneKind.GRAVEYARD, ControllerRef.TARGET_PLAYER),
                **{
                    "from": Zone(ZoneKind.HAND, ControllerRef.TARGET_PLAYER),
                },
                controller=ControllerRef.TARGET_PLAYER,
                cards=referent_sel("result"),
            ),
            type_line="Creature",
            types=("Creature",),
            power=1,
            toughness=2,
        )

    def test_cast_completes_effect_skipped_loud(self):
        opp_hand = [
            self.world.add_card(card_id(f"H{i}"), self.p1, ZONE_HAND) for i in range(2)
        ]
        handle = self.expert()
        cast(self.ex, self.p0, handle, targets=(self.p1,))
        # the creature still entered (the spell resolves; only the
        # unresolvable half of it is lost)
        self.assertEqual(self.world.zone_of(handle).kind, ZONE_BATTLEFIELD)
        # the skipped discard moved NOTHING: the opponent's hand is intact
        self.assertEqual(
            list(self.world.players[self.p1].zone(ZONE_HAND).entries), opp_hand
        )
        self.assertEqual(
            list(self.world.players[self.p1].zone(ZONE_GRAVEYARD).entries), []
        )
        # LOUD, once, naming the card and the engine's own refusal
        self.assertEqual(len(self.ex.unresolved_effects), 1)
        self.assertIn("AcqClone", self.ex.unresolved_effects[0])
        self.assertIn("has no register", self.ex.unresolved_effects[0])

    def test_second_cast_dedupes_the_flag(self):
        cast(self.ex, self.p0, self.expert(), targets=(self.p1,))
        cast(self.ex, self.p0, self.expert(), targets=(self.p1,))
        self.assertEqual(len(self.ex.unresolved_effects), 1)
        # r24a MINOR: the deduped key keeps an OCCURRENCES count
        self.assertEqual(
            self.ex.unresolved_effect_counts[self.ex.unresolved_effects[0]], 2
        )


# ------------------------------------------------- 2 dangling 'target'


class TargetDanglingCastTest(StackCase):
    """Shell Shield's folded residue: a kicked arm reading referent
    'target' on a spell whose TARGET-selector clause never compiled."""

    def shield(self, name="ShieldClone"):
        return self.give(
            name,
            SpellKind.INSTANT,
            effect=Conditional(
                pred=FAtom(pred=FAtomPred.WAS_KICKED),
                then_effect=atom(
                    Verb.DEAL_DAMAGE,
                    target=referent_sel("target", CREATURE_F),
                    amount=QConst(1),
                ),
            ),
            extra_abilities=(
                KickerAbility(cost=Cost(parts=(CostManaColor("B", QConst(1)),))),
            ),
        )

    def test_kicked_cast_completes_arm_skipped_loud(self):
        creature = self.world.add_card(
            card_id("Fodder", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.world.players[self.p0].mana_pool.clear()
        self.world.players[self.p0].mana_pool["B"] = 1
        handle = self.shield()
        cast(self.ex, self.p0, handle, kicked=True)
        # the instant resolved to its graveyard…
        self.assertEqual(self.world.zone_of(handle).kind, ZONE_GRAVEYARD)
        # …and the dangling arm dealt NOTHING
        self.assertEqual(dict(self.ex.damage), {})
        self.assertNotIn(creature, self.ex.damage)
        self.assertEqual(len(self.ex.unresolved_effects), 1)
        self.assertIn("ShieldClone", self.ex.unresolved_effects[0])
        self.assertIn("no target binding", self.ex.unresolved_effects[0])

    def test_unkicked_same_card_never_flags(self):
        handle = self.shield()
        cast(self.ex, self.p0, handle)
        self.assertEqual(self.ex.unresolved_effects, [])


# ------------------------------------------------- 2b trigger lane twin


class TriggerLaneGuardTest(BindingCase):
    """The 60-game fuzz follow-up (/111→/112): the SAME Acquisitions-
    Expert-shaped residue reaches the game through the TRIGGER-firing
    lane (binding._fire), not cast. Guarded identically: the mis-shaped
    effect skips loud, the event queue keeps draining."""

    def test_dangling_trigger_effect_skips_loud(self):
        self.attach_trigger(
            self.watch,
            ZoneChangeEvent(ANY_ANY, BF_YOU, subject=ANOTHER_CREATURE),
            atom(
                Verb.MOVE_ZONE,
                destination=Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                cards=referent_sel("result"),
            ),
        )
        visitor = self.world.add_card(card_id("Visitor", "1", "1"), self.p0, ZONE_HAND)
        self.ex.execute(
            enter(BF_OWNER),
            source=visitor,
            controller=self.p0,
            bindings={"cards": visitor},
        )
        # the ETB fired, the dangling discard skipped, the enter STOOD
        self.assertEqual(self.world.zone_of(visitor).kind, ZONE_BATTLEFIELD)
        self.assertEqual(list(self.zone(self.p0, ZONE_GRAVEYARD)), [])
        self.assertEqual(len(self.ex.unresolved_effects), 1)
        self.assertIn("trigger", self.ex.unresolved_effects[0])
        self.assertIn("Watchdog", self.ex.unresolved_effects[0])
        self.assertIn("has no register", self.ex.unresolved_effects[0])


# ------------------------------------------------- 3 producer present


class ProducerStillResolvesTest(StackCase):
    def test_result_anaphora_resolves_through_the_guarded_lane(self):
        first = self.world.add_card(
            card_id("Tapped", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        second = self.world.add_card(
            card_id("Kept", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        handle = self.give(
            "ProducerClone",
            SpellKind.INSTANT,
            effect=Seq(
                (
                    atom(
                        Verb.TAP,
                        target=Selector(
                            QConst(1), SelectorMode.CHOOSE, CREATURE_F, zones=(BF_YOU,)
                        ),
                    ),
                    atom(
                        Verb.MOVE_ZONE,
                        destination=Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                        cards=referent_sel("result", CREATURE_F),
                    ),
                )
            ),
        )
        cast(self.ex, self.p0, handle)
        # the CHOOSE 12a stand-in picked the Handle-first creature, the TAP
        # wrote the 'result' register and the MOVE_ZONE consumed it —
        # exactly one creature in the graveyard, no flag.
        gy = list(self.world.players[self.p0].zone(ZONE_GRAVEYARD).entries)
        self.assertIn(first, gy)
        self.assertNotIn(second, gy)
        self.assertEqual(self.world.zone_of(second).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.ex.unresolved_effects, [])


# ------------------------------------------------- 4 other refusals loud


class OtherRefusalsStayLoudTest(StackCase):
    def test_non_card_zone_destination_still_kills_the_cast(self):
        handle = self.give(
            "PlayerZoneClone",
            SpellKind.INSTANT,
            effect=atom(
                Verb.MOVE_ZONE,
                destination=Zone(ZoneKind.PLAYER, ControllerRef.ANY),
                cards=referent_sel("result"),
            ),
        )
        with self.assertRaises(NotImplementedError) as cm:
            cast(self.ex, self.p0, handle)
        self.assertIn("not a card zone", str(cm.exception))
        self.assertEqual(self.ex.unresolved_effects, [])


# ------------------------------------------------- 5 the typed predicate


class ReferentAbsentPredicateTest(unittest.TestCase):
    """r24a (adversarial gate): the predicate is TYPE + BYTE-EXACT site
    message — not a substring scan (the mark already co-matched
    quantity's QProp refusal, and any error whose text merely CONTAINS
    a mark used to be skippable)."""

    def test_matches_the_typed_site_errors(self):
        self.assertTrue(
            referent_absent(
                ReferentAbsentBindingError(
                    "executor: 'target' referent has no target binding"
                )
            )
        )
        self.assertTrue(referent_absent(ReferentAbsentRegisterError("result")))
        self.assertTrue(referent_absent(ReferentAbsentRegisterError("event")))

    def test_rejects_message_lookalikes_and_other_refusals(self):
        # same TEXTS, wrong TYPE: never skippable (they are not the sites)
        self.assertFalse(
            referent_absent(
                ValueError("executor: 'target' referent has no target binding")
            )
        )
        self.assertFalse(
            referent_absent(
                NotImplementedError(
                    "executor: selector referent 'result' has no register — "
                    "no trigger firing bound one and no producer atom wrote "
                    "one in this execution"
                )
            )
        )
        # right TYPE, wrong MESSAGE: the QProp refusal text wearing the
        # site class is still refused
        self.assertFalse(
            referent_absent(
                ReferentAbsentBindingError(
                    "executor: QProp 'target' referent has no target binding"
                )
            )
        )
        self.assertFalse(
            referent_absent(ValueError("executor: MOVE_ZONE cards role has no binding"))
        )
        self.assertFalse(
            referent_absent(
                NotImplementedError("executor: verb FLY is not dispatchable (12c)")
            )
        )
        self.assertFalse(referent_absent(KeyError("result")))


# --------------------------- 6 embedded-mark look-alike PROPAGATES (gate E2E)


class LookAlikePropagatesTest(StackCase):
    """The gate's executed probe: an UNRELATED refusal whose message
    merely CONTAINS both marks must propagate through the guarded cast
    lane — the bug is NOT silenced into the ledger (r24a BLOCKER 1)."""

    MARK_TEXT = (
        "executor: unrelated 12c refusal — a caller that says referent "
        "has no target binding reads this and 'x' has no register too"
    )

    def test_mark_text_unrelated_error_kills_the_cast_and_never_flags(self):
        handle = self.give(
            "LookAlikeClone",
            SpellKind.INSTANT,
            effect=atom(
                Verb.MOVE_ZONE,
                destination=Zone(ZoneKind.EXILE, ControllerRef.ANY),
                cards=Selector(QConst(1), SelectorMode.CHOOSE, CREATURE_F, zones=(BF_YOU,)),
            ),
        )
        self.world.add_card(card_id("Victim", "1", "1"), self.p0, ZONE_BATTLEFIELD)

        def look_alike(ctx, at):  # plain NotImplementedError, marks inside
            raise NotImplementedError(self.MARK_TEXT)

        with (
            mock.patch.dict(verbs.HANDLERS, {Verb.MOVE_ZONE: look_alike}),
            self.assertRaises(NotImplementedError) as cm,
        ):
            cast(self.ex, self.p0, handle)
        self.assertIn("unrelated 12c refusal", str(cm.exception))
        self.assertEqual(self.ex.unresolved_effects, [])
        self.assertEqual(self.ex.unresolved_effect_counts, {})


# ------------------------------- 7 QProp referent refusal PROPAGATES (gate c)


class QPropRefusalStaysLoudTest(StackCase):
    """quantity._referent_handle's QProp 'target' refusal CONTAINS mark
    #1 but is NOT a resolve_selector site — it must kill the cast
    (skipping it would run damage formulas on a wrong referent)."""

    def test_qprop_target_refusal_propagates(self):
        handle = self.give(
            "QPropClone",
            SpellKind.INSTANT,
            effect=atom(
                Verb.DEAL_DAMAGE,
                target=Selector(QConst(1), SelectorMode.CHOOSE, CREATURE_F, zones=(BF_YOU,)),
                amount=QProp(referent="target", field=QPropField.CMC),
            ),
        )
        self.world.add_card(card_id("Target", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        with self.assertRaises(ValueError) as cm:
            cast(self.ex, self.p0, handle)
        self.assertIn(
            "QProp 'target' referent has no target binding", str(cm.exception)
        )
        self.assertEqual(self.ex.unresolved_effects, [])


# ---------------- 8 CR 609.7: a dangling MID-step loses only ITSELF (gate b)


class SeqMidStepTest(StackCase):
    def tap_first(self, name):
        """Seq(TAP (CHOOSE stand-in), dangling MOVE_ZONE, DAMAGE 1): the
        mid-step's 'target' designation never existed; the TAIL must
        still execute (r24a MAJOR 2)."""
        return Seq(
            (
                atom(
                    Verb.TAP,
                    target=Selector(QConst(1), SelectorMode.CHOOSE, CREATURE_F, zones=(BF_YOU,)),
                ),
                atom(
                    Verb.MOVE_ZONE,
                    destination=Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                    cards=referent_sel("target", CREATURE_F),
                ),
                atom(
                    Verb.DEAL_DAMAGE,
                    target=Selector(QConst(1), SelectorMode.CHOOSE, CREATURE_F, zones=(BF_YOU,)),
                    amount=QConst(1),
                ),
            )
        )

    def test_mid_step_dangling_tail_still_executes(self):
        first = self.world.add_card(
            card_id("First", "1", "4"), self.p0, ZONE_BATTLEFIELD
        )
        handle = self.give(
            "MidStepClone", SpellKind.INSTANT, effect=self.tap_first("x")
        )
        cast(self.ex, self.p0, handle)
        gy = list(self.world.players[self.p0].zone(ZONE_GRAVEYARD).entries)
        # the skipped step moved nothing (only the resolved instant itself
        # is in the graveyard)…
        self.assertEqual(gy, [handle])
        self.assertEqual(
            dict(self.ex.damage), {first: 1}
        )  # …but the TAIL damage still landed
        self.assertEqual(len(self.ex.unresolved_effects), 1)
        self.assertIn("MidStepClone", self.ex.unresolved_effects[0])

    def test_nested_seq_boundary_is_whole_step(self):
        """Documented boundary: granularity is the TOP level only — an
        inner Seq that fails mid-way is skipped whole, its resolvable
        tail-step goes with it. Moot once the compiler-wave fold gates
        land; pinned so the boundary is a fact, not a surprise."""
        self.world.add_card(card_id("Victim", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        handle = self.give(
            "NestedClone",
            SpellKind.INSTANT,
            effect=Seq(
                (
                    Seq(
                        (
                            atom(
                                Verb.MOVE_ZONE,
                                destination=Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                                cards=referent_sel("target", CREATURE_F),
                            ),
                            atom(
                                Verb.DEAL_DAMAGE,
                                target=Selector(
                                    QConst(1),
                                    SelectorMode.CHOOSE,
                                    CREATURE_F,
                                    zones=(BF_YOU,),
                                ),
                                amount=QConst(1),
                            ),
                        )
                    ),
                )
            ),
        )
        cast(self.ex, self.p0, handle)
        self.assertEqual(dict(self.ex.damage), {})  # inner tail lost with it
        self.assertEqual(len(self.ex.unresolved_effects), 1)

    def test_distinct_same_message_atoms_count_per_key(self):
        """MINOR: dedupe keys collapse identical messages (two distinct
        dangling atoms, one message) — the OCCURRENCES count keeps both
        visible instead of hiding the second."""
        handle = self.give(
            "TwinDangler",
            SpellKind.INSTANT,
            effect=Seq(
                (
                    atom(
                        Verb.MOVE_ZONE,
                        destination=Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                        cards=referent_sel("target", CREATURE_F),
                    ),
                    atom(
                        Verb.MOVE_ZONE,
                        destination=Zone(ZoneKind.EXILE, ControllerRef.ANY),
                        cards=referent_sel("target", CREATURE_F),
                    ),
                )
            ),
        )
        cast(self.ex, self.p0, handle)
        self.assertEqual(len(self.ex.unresolved_effects), 1)
        self.assertEqual(
            self.ex.unresolved_effect_counts[self.ex.unresolved_effects[0]], 2
        )


if __name__ == "__main__":
    unittest.main()
