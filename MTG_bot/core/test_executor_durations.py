"""Round-12d pins: the full Duration vocabulary on the ledger (plan /06
§12d). Covers: per-vocabulary expiry (Eot / WhileCondition / UntilNextStep
owner+active / UntilLeaves / UntilNextTurn / Permanent), WHILE on-off
cycles driven through journal events, the 12d UNTAP step (untap
journalling, triggers fired from the tick, the Frost Breath compiled
full-card freeze surviving exactly ONE untap tick), the Nine-Lives
compiled replacement chain (prevent + carried action + the HAS_COUNTER-9
exile trigger + detach), the honest PREVENT exposure surface, and the
replay fingerprint over it all.

Canonical rows are COMPILED, not hand-tuned: Frost Breath's two sentences
run through the real b5b/b5c templates, Nine Lives' replacement + exile
trigger through the real b5b/b2a templates — the same template ids that
produced the golden pool rows (see the probe record in
KNOWLEDGE/2026-09-29/09).
"""

from __future__ import annotations

import itertools
import unittest
from typing import cast

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CardRecord,
    ControllerRef,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DurationEot,
    DurationUntilLeaves,
    DurationUntilNextStep,
    DurationUntilNextTurn,
    DurationWhileCondition,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    PtDelta,
    PtDirection,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    SpellKind,
    Step,
    TapStateEvent,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.compiler import compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.test_compiler import _oid, _raw_card
from MTG_bot.core.executor import Executor
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_EXILE, GameWorld

_ORACLE_SEQ = itertools.count(1)


def card_id(name, power=None, toughness=None, type_line="Creature", cmc=2, oid=None):
    return CardIdentity(
        oracle_id=oid or f"00000000-0000-0000-0000-{next(_ORACLE_SEQ):012d}",
        name=name,
        power=power,
        toughness=toughness,
        type_line=type_line,
        cmc=cmc,
    )


def atom(verb, **roles):
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


BF_ANY = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)
UNIV = FAnd(())
CREATURE = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")


def target_sel(filter_=UNIV) -> Selector:
    return Selector(QConst(1), SelectorMode.TARGET, filter_, zones=(BF_ANY,))


def modify_pt(delta_p=0, delta_t=0, duration=None) -> Atom:
    roles: dict = {"target": target_sel()}
    if delta_p:
        roles["power"] = PtDelta(PtDirection.INCREASE, QConst(delta_p))
    if delta_t:
        roles["toughness"] = PtDelta(PtDirection.INCREASE, QConst(delta_t))
    if duration is not None:
        roles["duration"] = duration
    return atom(Verb.MODIFY_PT, **roles)


def gain(n) -> Atom:
    return atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(n))


def record_of(abilities, name, oid):
    """A minimal valid CardRecord carrying ``abilities`` — the same object
    shape attach_card bridges (oracle-id identity-checked)."""
    return CardRecord(
        oracle_id=oid,
        name=name,
        type_line="Creature",
        types=("Creature",),
        subtypes=(),
        supertypes=(),
        colors=(),
        color_identity=frozenset(),
        mana_cost=None,
        mana_value=2,
        power=QConst(2),
        toughness=QConst(2),
        loyalty=None,
        keywords=(),
        abilities=tuple(abilities),
        is_token=False,
    )


class DurationCase(unittest.TestCase):
    """p0 owns Alpha (the condition anchor / effect source), p1 owns Beta
    (the P/T victim). Nothing attached; the ledger is the whole surface."""

    def setUp(self):
        self.world = GameWorld(num_players=2, start_life=20, master_seed=12)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.alpha = self.world.add_card(
            card_id("Alpha", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.beta = self.world.add_card(
            card_id("Beta", "2", "2"), self.p1, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)

    def pt(self, handle):
        return self.ex.ledger.effective_pt(self.world.cards[handle].identity, handle)

    def buff(self, target, duration=None, delta_p=1, delta_t=0):
        self.ex.execute(
            modify_pt(delta_p, delta_t, duration),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": target},
        )

    def statuses(self, handle):
        return [
            self.ex.ledger.status(change.record_id)
            for change in self.ex.ledger.changes_for(handle)
        ]


class TestExpiryVocab(DurationCase):
    def test_eot_sweep_still_marks_rows_and_clears(self):
        self.buff(self.beta, DurationEot())
        self.assertEqual(self.pt(self.beta), (3, 2))
        self.ex.end_turn()
        self.assertEqual(self.pt(self.beta), (2, 2))
        self.assertEqual(self.ex.ledger.sweep_at_eot(), 0)  # already swept

    def test_permanent_buff_survives_the_turn_cycle(self):
        self.buff(self.beta, None)
        self.ex.end_turn()
        self.ex.begin_turn(self.p1)
        self.ex.advance_turn()
        self.assertEqual(self.pt(self.beta), (3, 2))

    def test_until_next_turn_owner_begin_turn_expiry(self):
        # p0 records "until your next turn": it survives p0's end_turn and
        # p1's begin_turn (the RECORDED owner is p0), and dies exactly at
        # p0's next begin_turn — the precise expiry the 12a ledger deferred.
        self.buff(self.beta, DurationUntilNextTurn())
        self.assertEqual(self.pt(self.beta), (3, 2))
        self.ex.end_turn()
        self.ex.begin_turn(self.p1)
        self.assertEqual(self.pt(self.beta), (3, 2))
        self.ex.end_turn()
        self.ex.begin_turn(self.p0)
        self.assertEqual(self.pt(self.beta), (2, 2))
        self.assertIn("expired", self.statuses(self.beta))

    def test_until_next_step_owner_scoped_waits_for_owners_untap(self):
        # "+1/+0 until their controller's next untap step": the victim's
        # controller is p1 — p0's untap ticks do NOT expire it; p1's
        # begin_turn UNTAP step consumes and expires it.
        self.buff(self.beta, DurationUntilNextStep(Step.UNTAP, owner_scoped=True))
        self.assertEqual(self.pt(self.beta), (3, 2))
        self.ex.begin_turn(self.p0)  # p0's untap tick: not p1's step
        self.assertEqual(self.pt(self.beta), (3, 2))
        self.ex.begin_turn(self.p1)  # p1's untap step: consumed and expired
        self.assertEqual(self.pt(self.beta), (2, 2))
        self.assertIn("expired", self.statuses(self.beta))

    def test_until_next_step_unscoped_expires_on_any_untap_tick(self):
        # owner_scoped=False ("until the next untap step" — whoever's): the
        # FIRST untap tick of ANY active player consumes it.
        self.buff(self.beta, DurationUntilNextStep(Step.UNTAP, owner_scoped=False))
        self.ex.begin_turn(self.p0)
        self.assertEqual(self.pt(self.beta), (2, 2))
        self.assertIn("expired", self.statuses(self.beta))

    def test_until_leaves_is_terminal_across_the_zone_cycle(self):
        # "until TARGET leaves the battlefield" (the R7-2 GAIN_CONTROL
        # pairing): the anchor referent is structured — "target" resolves
        # through the same C12 machinery the QProps use.
        self.buff(self.beta, DurationUntilLeaves(source="target"))
        self.assertEqual(self.pt(self.beta), (3, 2))
        self.world.move_to_zone(self.beta, self.p1, ZONE_EXILE)
        # What the executor's journal hook calls on a battlefield-leaving
        # zone change (called directly here: this world-move bypassed the
        # atom boundary on purpose).
        self.ex.ledger.expire_leaves(self.beta)
        self.assertEqual(self.pt(self.beta), (2, 2))
        self.world.move_to_zone(self.beta, self.p1, ZONE_BATTLEFIELD)
        # r5 convention: returning does NOT restore a terminal duration.
        self.assertEqual(self.pt(self.beta), (2, 2))
        self.assertEqual(self.statuses(self.beta), ["expired"])

    def test_until_leaves_via_the_journal_hook(self):
        # The same expiry through the real path: MOVE_ZONE atom exiles the
        # victim and the executor's zone-change hook expires the anchor.
        self.buff(self.beta, DurationUntilLeaves(source="target"))
        self.assertEqual(self.pt(self.beta), (3, 2))
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(),
                destination=Zone(ZoneKind.EXILE, ControllerRef.ANY),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"cards": self.beta},
        )
        self.assertEqual(self.statuses(self.beta), ["expired"])

    def test_while_condition_cycles_with_journal_events(self):
        # "gets +2/+0 as long as [the anchor] is tapped" — the WHILE filter
        # is a state predicate over the recording anchor (the effect
        # source), re-evaluated on the settle tail after EVERY public op.
        cond = DurationWhileCondition(FAtom(FAtomPred.IS_TAPPED))
        self.buff(self.beta, cond, delta_p=2)
        self.assertEqual(self.pt(self.beta), (2, 2))  # anchor untapped: OFF
        self.assertEqual(self.statuses(self.beta), ["while_off"])
        self.ex.execute(  # tapping the anchor flips the condition ON
            atom(Verb.TAP, target=target_sel()),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.assertEqual(self.pt(self.beta), (4, 2))
        self.assertEqual(self.statuses(self.beta), ["live"])
        self.ex.execute(  # and back OFF through the same channel
            atom(Verb.UNTAP, target=target_sel()),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.assertEqual(self.pt(self.beta), (2, 2))
        self.assertEqual(self.statuses(self.beta), ["while_off"])


class TestUntapStep(DurationCase):
    def tap(self, handle):
        self.world.cards[handle].tapped = True

    def test_begin_turn_untaps_active_permanents_with_journal_events(self):
        self.tap(self.alpha)
        self.tap(self.beta)
        self.ex.begin_turn(self.p0)
        self.assertFalse(self.world.cards[self.alpha].tapped)
        self.assertTrue(self.world.cards[self.beta].tapped)  # not p0's
        tap_rows = [
            row
            for row in self.ex.journal.dump()
            if row[1] == "TAP_STATE" and row[4] == "UNTAP_STEP"
        ]
        self.assertEqual(len(tap_rows), 1)  # only Alpha untapped this tick

    def test_untap_triggers_fire_from_the_tick(self):
        # "whenever a creature untaps, you gain 1 life" attached to Alpha:
        # the tick's journalled TapStateEvent arms it; begin_turn settles.
        self.tap(self.alpha)
        self.ex.attach_card(
            self.alpha,
            record_of(
                [
                    TriggeredAbility(
                        event=TapStateEvent(tapped=False, filter=UNIV),
                        condition=None,
                        effect=gain(1),
                    )
                ],
                name="Alpha",
                oid=self.world.cards[self.alpha].identity.oracle_id,
            ),
        )
        fired = self.ex.begin_turn(self.p0)
        self.assertEqual(fired, 1)
        self.assertEqual(self.world.players[self.p0].life, 21)


class TestFrostBreathCompiled(unittest.TestCase):
    """The real M21 row: the b5b tap template + the b5c untap-prevention
    template, folded by the instant assembly into Seq(TAP, PREVENT) — the
    frozen grammar's canonical UntilNextStep(UNTAP, owner-scoped) carrier.
    PREVENT_EFFECT carries NO target role (grammar table): the
    IS_ANY_TARGET anaphora reads the designated set from the bindings the
    TAP atom's designation filled — one shared ctx across the Seq."""

    SENTENCES = (
        "Tap up to two target creatures.",
        "Those creatures don't untap during their controller's next untap step.",
    )

    def setUp(self):
        self.world = GameWorld(num_players=2, start_life=20, master_seed=13)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        pool = {
            _oid(777): _raw_card(
                "Frost Breath",
                777,
                types=("Instant",),
                colors=("U",),
                mana_cost_raw="{1}{U}",
                mana_value=2,
                sentences=self.SENTENCES,
            )
        }
        pc = compile_pool(pool, build_full_registry())
        result = pc.results[_oid(777)]
        self.assertEqual(result.unparsed, ())  # both sentences compiled
        spell = result.card.abilities[0]
        assert isinstance(spell, SpellAbility)
        self.effect = cast(Seq, spell.effect)
        self.cold = self.world.add_card(
            card_id("Frost Breath", type_line="Instant"), self.p0
        )
        self.beta = self.world.add_card(
            card_id("Beta", "2", "2"), self.p1, ZONE_BATTLEFIELD
        )
        self.gamma = self.world.add_card(
            card_id("Gamma", "1", "1"), self.p1, ZONE_BATTLEFIELD
        )
        self.ex = Executor(self.world)

    def cast(self, *targets):
        return self.ex.apply_effect(
            self.effect,
            source=self.cold,
            controller=self.p0,
            bindings={"target": list(targets)},
        )

    def test_seq_shape_is_tap_then_prevent(self):
        steps = cast("tuple[Atom, ...]", self.effect.steps)
        self.assertEqual([step.verb for step in steps], [Verb.TAP, Verb.PREVENT_EFFECT])

    def test_freeze_survives_exactly_one_untap_tick(self):
        self.cast(self.beta)
        self.assertTrue(self.world.cards[self.beta].tapped)
        self.assertEqual(len(self.ex.replacements), 1)
        self.ex.begin_turn(self.p1)  # p1's untap step — FROZEN: stays tapped
        self.assertTrue(self.world.cards[self.beta].tapped)
        self.assertEqual(self.ex.replacements.dump()[0][5], "expired")
        self.ex.end_turn()
        self.ex.begin_turn(self.p0)
        self.ex.end_turn()
        self.ex.begin_turn(self.p1)  # the FOLLOWING untap step: it comes free
        self.assertFalse(self.world.cards[self.beta].tapped)

    def test_up_to_two_targets_both_frozen(self):
        self.cast(self.beta, self.gamma)
        self.assertTrue(self.world.cards[self.beta].tapped)
        self.assertTrue(self.world.cards[self.gamma].tapped)
        self.ex.begin_turn(self.p1)
        self.assertTrue(self.world.cards[self.beta].tapped)
        self.assertTrue(self.world.cards[self.gamma].tapped)

    def test_only_designated_targets_are_frozen(self):
        self.cast(self.beta)
        self.world.cards[self.gamma].tapped = True  # tapped, never designated
        self.ex.begin_turn(self.p1)
        self.assertTrue(self.world.cards[self.beta].tapped)  # frozen
        self.assertFalse(self.world.cards[self.gamma].tapped)  # comes free


class TestNineLivesReplacement(unittest.TestCase):
    """The real b5b row: ReplacementAbility over DamageDealtEvent (subject
    filter "to you"), action PUT_COUNTER(INCARNATION) — "the replacement
    carries its own prevention, no PREVENT atom" — plus the b2a
    HAS_COUNTER-9 exile trigger carrying the printed cap."""

    REPL_SENTENCE = (
        "If a source would deal damage to you, prevent that damage and put "
        "an incarnation counter on this enchantment."
    )
    TRIGGER_SENTENCE = (
        "When there are nine or more incarnation counters on this "
        "enchantment, exile it."
    )

    def setUp(self):
        self.world = GameWorld(num_players=2, start_life=20, master_seed=14)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        pool = {
            _oid(9): _raw_card(
                "Nine Lives",
                9,
                types=("Enchantment",),
                colors=("W",),
                mana_cost_raw="{2}{W}{W}",
                mana_value=4,
                sentences=(self.REPL_SENTENCE, self.TRIGGER_SENTENCE),
            )
        }
        pc = compile_pool(pool, build_full_registry())
        result = pc.results[_oid(9)]
        # B-49 (2026-10-29): + the trailing effect-less SpellAbility cast
        # carrier, so the enchantment is castable; it binds nothing here.
        self.assertEqual(
            [type(ability).__name__ for ability in result.card.abilities],
            ["ReplacementAbility", "TriggeredAbility", "SpellAbility"],
        )
        self.assertEqual(result.card.abilities[2], SpellAbility(kind=SpellKind.ENCHANTMENT))
        self.nine = self.world.add_card(
            card_id("Nine Lives", type_line="Enchantment", oid=result.card.oracle_id),
            self.p0,
            ZONE_BATTLEFIELD,
        )
        self.ex = Executor(self.world)
        self.assertEqual(self.ex.attach_card(self.nine, result.card), 1)

    def hit(self, n=1, victim=None):
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(), amount=QConst(n)),
            source=self.p1,
            controller=self.p1,
            bindings={"target": victim or self.p0},
        )

    def life(self, player=None):
        return self.world.players[player or self.p0].life

    def counters(self):
        return self.world.cards[self.nine].counters.get("INCARNATION", 0)

    def test_damage_to_you_is_consumed_before_the_world_changes(self):
        self.hit(3)
        self.assertEqual(self.life(), 20)  # NO life change at all
        self.assertEqual(self.counters(), 1)  # the carried action ran
        replaced = [event for event in self.ex.events if event[1] == "DAMAGE_REPLACED"]
        self.assertEqual(len(replaced), 1)
        self.assertEqual(self.ex.journal.dump()[-1][1], "COUNTER_PLACED")

    def test_other_damage_lands_and_detach_stops_the_protection(self):
        self.hit(2, victim=self.p1)  # "to you" = the aura's YOU (p0)
        self.assertEqual(self.life(self.p1), 18)
        self.hit(1)  # p0: protected
        self.assertEqual(self.life(), 20)
        self.ex.binder.detach(self.nine)
        self.hit(1)
        self.assertEqual(self.life(), 19)  # replacement left with the aura

    def test_ninth_incarnation_counter_exiles_the_enchantment(self):
        for _ in range(9):
            self.hit(1)
        self.assertEqual(self.counters(), 9)
        self.assertEqual(self.world.zone_of(self.nine).kind, ZONE_EXILE)
        self.hit(1)
        self.assertEqual(self.life(), 19)  # unprotected now: damage lands

    def test_bounded_damage_cap_raises_instead_of_guessing(self):
        # C-4: only "a source would deal damage" (QUnbounded) is matched;
        # "the next N damage" style bounded replacements are NOT guessed.
        from MTG_bot.core.executor.replacements import ReplacementRecord

        self.ex.replacements.replacements.append(
            ReplacementRecord(
                seq=9999,
                source=self.nine,
                controller=self.p0,
                event=DamageDealtEvent(amount=QConst(1), filter=UNIV),
                action=gain(1),
            )
        )
        with self.assertRaises(NotImplementedError):
            self.hit(1, victim=self.p1)  # bypasses Nine's own (YOU-scoped) row


class TestPreventionExposure(DurationCase):
    def test_combat_prevent_registers_and_exposes_without_consumer(self):
        # Faith's Fetters / Capture Sphere shape: a universal "can't
        # attack" veto. Registered, dumped, EXPOSED — no combat phase
        # consumes it pre-12e, and nothing else is affected.
        self.ex.execute(
            atom(
                Verb.PREVENT_EFFECT,
                condition=UNIV,
                event=DeclareAttackersEvent(filter=CREATURE),
            ),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual(len(self.ex.replacements.combat_preventions()), 1)
        self.assertEqual(len(self.ex.replacements.dump()), 1)
        self.assertFalse(self.ex.replacements.prevents_untap(self.beta))

    def test_prevent_without_targets_registers_a_global_family(self):
        # No designation in context: the veto's affected set is empty —
        # a step-wide "creatures don't untap" family (Fetters shape) has
        # no per-card targets; the step/phase consumer is 12e.
        self.ex.execute(
            atom(
                Verb.PREVENT_EFFECT,
                condition=CREATURE,
                event=TapStateEvent(tapped=False, filter=CREATURE),
                step=Step.UNTAP,
                duration=DurationUntilNextTurn(),
            ),
            source=self.alpha,
            controller=self.p0,
        )
        self.world.cards[self.beta].tapped = True
        self.ex.begin_turn(self.p1)
        # re-pinned 2026-10-29: V16 gives the targetless family its consumer
        # (CR 502.3): the record's filter is the affected set, so Beta, a
        # creature, does not untap (it used to: EXPOSED).
        self.assertTrue(self.world.cards[self.beta].tapped)
        self.assertEqual(len(self.ex.replacements.dump()), 1)
        self.assertEqual(self.ex.replacements.dump()[0][5], "live")
        self.ex.end_turn()
        self.ex.begin_turn(self.p0)  # the record's owner's turn begins:
        self.assertEqual(self.ex.replacements.dump()[0][5], "expired")


class TestReplayFingerprint(unittest.TestCase):
    """The 12d machinery — condition cycles, prevents with anaphoric
    designation, the untap tick, step/next-turn expiry — replays
    byte-identical (P12), and a frozen untap differs from a free one."""

    def scripted(self, seed, freeze=True):
        world = GameWorld(num_players=2, start_life=20, master_seed=seed)
        p0, p1 = world.player_order[0], world.player_order[1]
        # Explicit oracle ids: the module's id counter is process-global and
        # would make the SECOND scripted run's identities differ from the
        # first's (the 12a replay helpers reset it per case for the same
        # reason — identities are fingerprint state).
        alpha = world.add_card(
            card_id("Alpha", "2", "2", oid=_oid(1)), p0, ZONE_BATTLEFIELD
        )
        beta = world.add_card(
            card_id("Beta", "2", "2", oid=_oid(2)), p1, ZONE_BATTLEFIELD
        )
        ex = Executor(world)
        cond = DurationWhileCondition(FNot(FAtom(FAtomPred.IS_TAPPED)))
        ex.execute(
            modify_pt(1, 0, cond),
            source=alpha,
            controller=p0,
            bindings={"target": beta},
        )
        if freeze:
            ex.execute(
                atom(
                    Verb.PREVENT_EFFECT,
                    condition=FAtom(FAtomPred.IS_ANY_TARGET),
                    event=TapStateEvent(
                        tapped=False, filter=FAtom(FAtomPred.IS_ANY_TARGET)
                    ),
                    step=Step.UNTAP,
                    duration=DurationUntilNextStep(Step.UNTAP, owner_scoped=True),
                ),
                source=alpha,
                controller=p0,
                bindings={"target": [beta]},
            )
        ex.execute(  # and a tap to freeze (or not)
            atom(Verb.TAP, target=target_sel()),
            source=alpha,
            controller=p0,
            bindings={"target": beta},
        )
        ex.begin_turn(p0)  # while-condition stays ON (alpha untapped)
        ex.begin_turn(p1)  # beta: frozen then record expires / free untap
        ex.end_turn()
        ex.begin_turn(p0)
        ex.end_turn()
        ex.begin_turn(p1)
        ex.end_turn()
        return ex.state_fingerprint()

    def test_two_executors_replay_identically(self):
        self.assertEqual(self.scripted(5), self.scripted(5))

    def test_a_frozen_untap_fingerprints_differently(self):
        self.assertNotEqual(self.scripted(5, freeze=True), self.scripted(5, False))


if __name__ == "__main__":
    unittest.main()
