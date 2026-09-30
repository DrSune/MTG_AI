"""Tests for the round-12b trigger binding layer (/06 §12b).

Pins: compiled-ability attachment (oracle-id bridge identity-checked,
detach-on-leave / re-register-on-re-enter), the structured event journal
(zone moves, C18 dies was-snapshots, draws with per-turn ordinals,
counters, taps, damage, life, turn-phase markers), the APNAP fire loop with
Handle tie-break, may-offer decisions consumed in fire order, the C22
DelayedTrigger window with its end-of-turn expiry, the 200-fire loop
tripwire, honest NotImplementedError on combat/cast/targeting event nodes —
and the P12 replay fingerprint across a scripted multi-trigger chain.
"""

import itertools
import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    BecomesBlockedEvent,
    CardDrawnEvent,
    CardRecord,
    CombatDamageEvent,
    ControllerRef,
    CounterKind,
    CounterPlacedEvent,
    CreatureDiesEvent,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    DelayedTrigger,
    DurationEot,
    DurationUntilNextTurn,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    LifeGainedEvent,
    OptionalEffect,
    Phase,
    PtDelta,
    PtDirection,
    QAgg,
    QAtLeast,
    QConst,
    QProp,
    QPropField,
    SacrificeEvent,
    Selector,
    SelectorMode,
    Seq,
    Step,
    StepEvent,
    TapStateEvent,
    TargetingEvent,
    TriggeredAbility,
    TurnPhaseEvent,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.compiler.compiler import compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.test_compiler import _oid, _raw_card
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.binding import MAX_TRIGGER_FIRES
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)

_ORACLE_SEQ = itertools.count(100)


def reset_oracle_ids():
    global _ORACLE_SEQ
    _ORACLE_SEQ = itertools.count(100)


def card_id(name, power=None, toughness=None, type_line="Creature", cmc=2, oid=None):
    if oid is None:
        n = next(_ORACLE_SEQ)
        oid = f"{n:08x}-1111-2222-3333-444444444444"
    return CardIdentity(
        oracle_id=oid,
        name=name,
        type_line=type_line,
        power=power,
        toughness=toughness,
        cmc=cmc,
    )


def atom(verb, **roles):
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


BF_ANY = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)
BF_YOU = Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)
BF_OWNER = Zone(ZoneKind.BATTLEFIELD, ControllerRef.OWNER)
GY_ANY = Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY)
LIB_YOU = Zone(ZoneKind.LIBRARY, ControllerRef.YOU)
HAND_YOU = Zone(ZoneKind.HAND, ControllerRef.YOU)
ANY_ANY = Zone(ZoneKind.ANY, ControllerRef.ANY)
CREATURE = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")
IS_SOURCE = FAtom(FAtomPred.IS_SOURCE)
UNIV = FAnd(())
ANOTHER_CREATURE = FAnd((FNot(IS_SOURCE), CREATURE))


def referent_sel(referent: str, filter_: Filter = UNIV) -> Selector:
    """The C2 convention referent selector (bound object, never a search)."""
    return Selector(QConst(1), SelectorMode.CHOOSE, filter_, ANY_ANY, referent=referent)


def named_sel(name: str) -> Selector:
    """Deterministic CHOOSE designation by printed name (12a stand-in)."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(FAtomPred.NAME_EQ, string_value=name),
        BF_ANY,
    )


def all_bf() -> Selector:
    return Selector(QConst(1), SelectorMode.ALL, UNIV, BF_ANY)


def enter(dest: Zone) -> Atom:
    """MOVE_ZONE with the cards role filled by a placeholder Selector — the
    designated objects ride in via ``bindings={"cards": ...}`` (12a
    convention; the selector is never resolved when a binding exists)."""
    return atom(
        Verb.MOVE_ZONE,
        cards=Selector(QConst(9), SelectorMode.ALL, UNIV, ANY_ANY),
        destination=dest,
    )


def etb_trigger(effect, subject=IS_SOURCE) -> TriggeredAbility:
    return TriggeredAbility(
        event=ZoneChangeEvent(from_zone=ANY_ANY, to_zone=BF_YOU, subject=subject),
        condition=None,
        effect=effect,
    )


def record_of(abilities, name="Rec", oid=None) -> CardRecord:
    """A minimal valid Creature CardRecord carrying ``abilities``."""
    return CardRecord(
        oracle_id=oid or f"{next(_ORACLE_SEQ):08x}-1111-2222-3333-444444444444",
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


def gain(n, who=ControllerRef.YOU) -> Atom:
    return atom(Verb.GAIN_LIFE, controller=who, amount=QConst(n))


def mill_one() -> Atom:
    return atom(Verb.MILL, controller=ControllerRef.YOU, amount=QConst(1))


def draw_one() -> Atom:
    return atom(
        Verb.MOVE_ZONE,
        cards=Selector(QConst(1), SelectorMode.ALL, UNIV, LIB_YOU),
        destination=HAND_YOU,
    )


class BindingCase(unittest.TestCase):
    """p0: Watchdog (attached-trigger carrier) + 4-card library; p1 plain."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=11)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.watch = self.world.add_card(
            card_id("Watchdog", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.libs = [
            self.world.add_card(card_id(f"L{i}"), self.p0) for i in (1, 2, 3, 4)
        ]
        self.ex = Executor(self.world)

    def life(self, player):
        return self.world.players[player].life

    def zone(self, player, kind):
        return self.world.players[player].zone(kind).entries

    def record_for(self, handle, abilities, name="Rec") -> CardRecord:
        """A record SHARED with the world card — the bridge wants the
        card's own oracle id (identity-checked on attach)."""
        return record_of(
            abilities, name=name, oid=self.world.cards[handle].identity.oracle_id
        )

    def attach_trigger(self, handle, event, effect, condition=None, name="Rec"):
        return self.ex.attach_card(
            handle,
            self.record_for(
                handle, [TriggeredAbility(event, condition, effect)], name=name
            ),
        )


class TestAttachment(BindingCase):
    def test_attach_binds_count_and_identity_bridge_checked(self):
        rec = self.record_for(
            self.watch,
            [
                etb_trigger(gain(1)),
                TriggeredAbility(
                    TurnPhaseEvent(Phase.UPKEEP, ControllerRef.YOU), None, gain(1)
                ),
            ],
        )
        self.assertEqual(self.ex.attach_card(self.watch, rec), 2)
        self.assertEqual(len(self.ex.binder.attached), 2)
        stranger = record_of([etb_trigger(gain(1))])  # fresh oracle id
        with self.assertRaises(ValueError):  # the bridge is CHECKED, not assumed
            self.ex.attach_card(self.watch, stranger)
        ghost = self.world.add_card(card_id("Ghost"), self.p0, ZONE_HAND)
        self.world.cards.pop(ghost)
        with self.assertRaises(ValueError):  # not a world card
            self.ex.attach_card(ghost, stranger)

    def test_detach_on_leave_and_reregister_on_reentry(self):
        # Watchdog: "whenever another creature enters, gain 1 life".
        self.attach_trigger(
            self.watch,
            ZoneChangeEvent(ANY_ANY, BF_YOU, subject=ANOTHER_CREATURE),
            gain(1),
        )
        visitor = self.world.add_card(card_id("Visitor", "1", "1"), self.p0, ZONE_HAND)
        enter_op = enter(BF_OWNER)
        self.ex.execute(
            enter_op, source=visitor, controller=self.p0, bindings={"cards": visitor}
        )
        self.assertEqual(self.life(self.p0), 21)
        # Leave to exile and come back: the re-register fires it again.
        self.ex.execute(
            atom(Verb.EXILE, target=all_bf()),
            source=self.watch,
            controller=self.p0,
            bindings={"target": visitor},
        )
        self.ex.execute(
            enter_op, source=visitor, controller=self.p0, bindings={"cards": visitor}
        )
        self.assertEqual(self.life(self.p0), 22)
        # Watchdog leaves: detached. The visitor's next entry is silent.
        self.ex.execute(
            atom(Verb.EXILE, target=all_bf()),
            source=visitor,
            controller=self.p0,
            bindings={"target": self.watch},
        )
        self.assertEqual(self.ex.binder.attached, {})
        self.ex.execute(
            enter_op, source=visitor, controller=self.p0, bindings={"cards": visitor}
        )
        self.assertEqual(self.life(self.p0), 22)

    def test_compiled_mini_pool_bridge(self):
        # A REAL compile: the b2a Carrion-Grub template row. attach_pool
        # registers by oracle id; the ETB mill runs when the card enters.
        pool = {
            _oid(1): _raw_card(
                "Grubby",
                1,
                types=("Creature",),
                subtypes=("Insect",),
                power_raw="4",
                toughness_raw="4",
                sentences=("When this creature enters, mill four cards.",),
            )
        }
        pc = compile_pool(pool, build_full_registry())
        res = pc.results[_oid(1)]
        self.assertEqual(res.unparsed, ())  # the template landed cleanly
        grub = self.world.add_card(
            card_id("Grubby", "4", "4", type_line="Creature — Insect", oid=_oid(1)),
            self.p0,
            ZONE_HAND,
        )
        self.assertEqual(self.ex.attach_pool(pc), 0)  # nothing on the battlefield yet
        self.ex.execute(
            enter(BF_YOU),
            source=grub,
            controller=self.p0,
            bindings={"cards": grub},
        )
        self.assertEqual(len(self.zone(self.p0, ZONE_LIBRARY)), 0)
        self.assertEqual(len(self.zone(self.p0, ZONE_GRAVEYARD)), 4)


class TestEventKinds(BindingCase):
    def test_dies_carries_c18_was_snapshot_and_event_referent(self):
        amount = QProp(referent="event", field=QPropField.POWER, agg=QAgg.FIRST)
        self.attach_trigger(
            self.watch,
            CreatureDiesEvent(filter=UNIV),
            atom(
                Verb.GAIN_LIFE,
                controller=ControllerRef.YOU,
                amount=amount,
            ),
        )
        # Buff the victim 2/2 -> +2/+0 (ledger), then destroy: the trigger
        # pays the WAS power (4) — the C18 snapshot, not the printed value.
        victim = self.world.add_card(
            card_id("Victim", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex.execute(
            atom(
                Verb.MODIFY_PT,
                target=referent_sel("target"),
                power=PtDelta(PtDirection.INCREASE, QConst(2)),
            ),
            source=self.watch,
            controller=self.p0,
            bindings={"target": victim},
        )
        self.ex.execute(
            atom(Verb.DESTROY, target=all_bf()),
            source=self.watch,
            controller=self.p0,
            bindings={"target": victim},
        )
        self.assertEqual(self.life(self.p0), 24)
        dies = [e for e in self.ex.journal.events if e.kind == "CREATURE_DIES"]
        self.assertEqual(len(dies), 1)
        _from, was_owner, was_type, was_p, was_t = dies[0].dies
        self.assertEqual((was_p, was_t), (4, 2))
        self.assertEqual(was_type, "Creature")
        self.assertEqual(was_owner, self.p0)

    def test_draw_ordinal_trigger(self):
        self.attach_trigger(  # second card drawn this turn -> +1
            self.watch, CardDrawnEvent(ControllerRef.YOU, ordinal=2), gain(1)
        )
        self.ex.execute(draw_one(), source=self.watch, controller=self.p0)
        self.assertEqual(self.life(self.p0), 20)
        self.ex.execute(draw_one(), source=self.watch, controller=self.p0)
        self.assertEqual(self.life(self.p0), 21)

    def test_tap_state_and_counter_triggers(self):
        untapper = self.world.add_card(
            card_id("U", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.ex.attach_card(
            untapper,
            self.record_for(
                untapper,
                [
                    TriggeredAbility(TapStateEvent(False, IS_SOURCE), None, gain(4)),
                ],
            ),
        )
        self.ex.attach_card(
            self.watch,
            self.record_for(
                self.watch,
                [
                    TriggeredAbility(
                        CounterPlacedEvent(
                            CounterKind.PLUS_1_PLUS_1, IS_SOURCE, count=QAtLeast(1)
                        ),
                        None,
                        gain(3),
                    ),
                ],
            ),
        )
        self.ex.execute(
            atom(Verb.TAP, target=all_bf()),
            source=self.watch,
            controller=self.p0,
            bindings={"target": untapper},
        )
        self.assertEqual(self.life(self.p0), 20)  # became tapped: no match
        self.ex.execute(
            atom(Verb.UNTAP, target=all_bf()),
            source=self.watch,
            controller=self.p0,
            bindings={"target": untapper},
        )
        self.assertEqual(self.life(self.p0), 24)  # becomes untapped: fired
        self.ex.execute(
            atom(
                Verb.PUT_COUNTER,
                target=all_bf(),
                counter_kind=CounterKind.PLUS_1_PLUS_1,
                count=QConst(2),
            ),
            source=untapper,
            controller=self.p0,
            bindings={"target": self.watch},
        )
        self.assertEqual(self.life(self.p0), 27)

    def test_life_gained_feed_is_one_way(self):
        # LifeGained's effect mills (a life-gaining effect would re-trigger
        # its own life event — the drain's tripwire would rightly catch it).
        self.attach_trigger(self.watch, LifeGainedEvent(ControllerRef.YOU), mill_one())
        self.ex.execute(gain(2), source=self.watch, controller=self.p0)
        self.assertEqual(self.life(self.p0), 22)
        self.assertEqual(len(self.zone(self.p0, ZONE_LIBRARY)), 3)  # milled once

    def test_damage_and_sacrifice_triggers(self):
        self.ex.attach_card(
            self.watch,
            self.record_for(
                self.watch,
                [
                    TriggeredAbility(
                        DamageDealtEvent(QConst(1), IS_SOURCE), None, gain(2)
                    ),
                    TriggeredAbility(SacrificeEvent(ControllerRef.YOU), None, gain(1)),
                ],
            ),
        )
        victim = self.world.add_card(card_id("V", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.ex.execute(
            atom(Verb.SACRIFICE, target=all_bf()),
            source=self.watch,
            controller=self.p0,
            bindings={"target": victim},
        )
        self.assertEqual(self.life(self.p0), 21)
        self.assertIn(victim, self.zone(self.p0, ZONE_GRAVEYARD))
        self.ex.execute(
            atom(
                Verb.DEAL_DAMAGE,
                target=all_bf(),
                amount=QConst(1),
            ),
            source=victim,
            controller=self.p1,
            bindings={"target": self.watch},
        )
        self.assertEqual(self.life(self.p0), 23)  # 1 to the 2/2: survived, fired

    def test_turn_phase_markers_and_eot_sweep(self):
        self.ex.attach_card(
            self.watch,
            self.record_for(
                self.watch,
                [
                    TriggeredAbility(
                        TurnPhaseEvent(Phase.UPKEEP, ControllerRef.YOU), None, gain(1)
                    ),
                    TriggeredAbility(
                        TurnPhaseEvent(Phase.END_TURN, ControllerRef.YOU),
                        None,
                        atom(
                            Verb.MODIFY_PT,
                            target=referent_sel("source"),
                            power=PtDelta(PtDirection.INCREASE, QConst(9)),
                            duration=DurationEot(),
                        ),
                    ),
                ],
            ),
        )
        self.ex.begin_turn(self.p0)  # my turn: UPKEEP fires
        self.assertEqual(self.life(self.p0), 21)
        self.assertEqual(self.world.turn, 1)  # the first begun turn IS turn 1
        self.ex.begin_turn(self.p1)  # opponent's upkeep: YOU does not match
        self.assertEqual(self.life(self.p0), 21)
        self.assertEqual(self.world.turn, 2)
        # The END_TURN trigger's Eot-tagged +9 delta resolves BEFORE the
        # end-of-turn sweep expires it: effective P/T is back at printed.
        self.ex.end_turn()
        power, _t = self.ex.ledger.effective_pt(
            self.world.cards[self.watch].identity, self.watch
        )
        self.assertEqual(power, 2)


class TestAPNAP(unittest.TestCase):
    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=5)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.target = self.world.add_card(
            card_id("Target", "3", "3"), self.p0, ZONE_BATTLEFIELD
        )
        self.c0 = self.world.add_card(card_id("C0", "1", "1"), self.p0, ZONE_HAND)
        self.c1 = self.world.add_card(card_id("C1", "1", "1"), self.p1, ZONE_HAND)
        self.ex = Executor(self.world)
        self.ex.begin_turn(self.p0)  # active player p0, seat 0

    def set_pt_rec(self, handle, value):
        return record_of(
            [
                etb_trigger(
                    atom(
                        Verb.SET_PT,
                        target=named_sel("Target"),
                        duration=DurationEot(),
                        power=QConst(value),
                        toughness=QConst(value),
                    )
                )
            ],
            oid=self.world.cards[handle].identity.oracle_id,
        )

    def test_simultaneous_etbs_resolve_in_apnap_order(self):
        # Both creatures enter in ONE op (simultaneous). The drain order is
        # the world's APNAP order_key (controller_seat first): p0's trigger
        # resolves first, p1's LAST — and the last SET_PT (5/5) wins the
        # ledger fold.
        self.ex.attach_card(self.c0, self.set_pt_rec(self.c0, 1))
        self.ex.attach_card(self.c1, self.set_pt_rec(self.c1, 5))
        both = sorted([self.c0, self.c1])
        self.ex.execute(
            enter(BF_OWNER),
            source=both[0],
            controller=self.p0,
            bindings={"cards": both},
        )
        power, toughness = self.ex.ledger.effective_pt(
            self.world.cards[self.target].identity, self.target
        )
        self.assertEqual((power, toughness), (5, 5))
        self.assertEqual(self.world.triggers, [])  # fully drained


class TestDelayedTrigger(BindingCase):
    def test_subira_window_fires_and_expires(self):
        put = atom(
            Verb.PUT_COUNTER,
            target=referent_sel("source"),
            counter_kind=CounterKind.PLUS_1_PLUS_1,
            count=QConst(1),
        )
        delayed = DelayedTrigger(
            duration=DurationUntilNextTurn(),  # the turn-window stand-in
            event=ZoneChangeEvent(ANY_ANY, BF_YOU, subject=ANOTHER_CREATURE),
            condition=None,
            effect=put,
        )
        subira = self.world.add_card(card_id("Subira", "1", "1"), self.p0, ZONE_HAND)
        self.ex.attach_card(
            subira, self.record_for(subira, [etb_trigger(delayed)], name="Subira")
        )
        self.ex.execute(
            enter(BF_YOU),
            source=subira,
            controller=self.p0,
            bindings={"cards": subira},
        )
        self.assertEqual(len(self.ex.binder.delayed), 1)  # scheduled (C22)
        a = self.world.add_card(card_id("A", "1", "1"), self.p0, ZONE_HAND)
        self.ex.execute(
            enter(BF_YOU),
            source=a,
            controller=self.p0,
            bindings={"cards": a},
        )
        self.assertEqual(
            self.world.cards[subira].counters.get(CounterKind.PLUS_1_PLUS_1.name), 1
        )
        self.ex.end_turn()  # the window closes with the turn
        self.assertEqual(len(self.ex.binder.delayed), 0)
        b = self.world.add_card(card_id("B", "1", "1"), self.p0, ZONE_HAND)
        self.ex.execute(
            enter(BF_YOU),
            source=b,
            controller=self.p0,
            bindings={"cards": b},
        )
        self.assertEqual(
            self.world.cards[subira].counters.get(CounterKind.PLUS_1_PLUS_1.name), 1
        )  # expired: no second counter


class TestRaises(BindingCase):
    def test_combat_cast_targeting_step_event_nodes_raise_on_bind(self):
        # AMENDED (13b): CastSpellEvent LEFT this list — the spell stack
        # shipped, the journal emits CAST rows (executor.events.emit_cast),
        # and binding.py._match_cast subscribes them (the cast-trigger
        # corpus: Quirion Dryad, Mangara, Double Vision, Ghostly Pilferer,
        # Spellgorger Weird, Riddleform, Rin and Seri — bound and fired in
        # test_executor_stack.py).
        # AMENDED 2026-10-01 (round 16b): DeclareAttackersEvent +
        # CombatDamageEvent LEFT this list too — the COMBAT skeleton ships
        # both feeds (DECLARE_ATTACKERS / COMBAT_DAMAGE journal rows,
        # binder matchers in binding.py) and bind CLEAN (checked below).
        # AMENDED 2026-10-02 (round 16c): DeclareBlockersEvent +
        # BecomesBlockedEvent LEFT this list too — the blocker step ships
        # the feed (DECLARE_BLOCKERS pair rows, binder matchers) and both
        # bind CLEAN (checked below). Targeting/step raises stay.
        for event in (
            TargetingEvent(filter=UNIV),
            StepEvent(Phase.COMBAT, Step.DECLARE_ATTACKERS, ControllerRef.YOU),
        ):
            with (
                self.subTest(event=type(event).__name__),
                self.assertRaises(NotImplementedError),
            ):
                self.attach_trigger(self.watch, event, gain(1))
        # 16b: the two combat feeds that LEFT the table bind clean now.
        self.assertEqual(
            self.attach_trigger(
                self.watch, DeclareAttackersEvent(filter=UNIV), gain(1)
            ),
            1,
        )
        self.assertEqual(
            self.attach_trigger(self.watch, CombatDamageEvent(filter=UNIV), gain(1)),
            1,
        )
        # 16c: the block feed binds clean (the matcher semantics — filter/
        # SUBJECT over the blocker, blocked over the attacker, the anchored
        # BecomesBlockedEvent reading — are pinned in test_executor_blockers).
        self.assertEqual(
            self.attach_trigger(
                self.watch, DeclareBlockersEvent(filter=UNIV), gain(1)
            ),
            1,
        )
        self.assertEqual(
            self.attach_trigger(
                self.watch, BecomesBlockedEvent(filter=UNIV), gain(1)
            ),
            1,
        )

    def test_damage_source_and_combat_scopes_bind(self):
        # AMENDED 2026-10-02 (round 16c): the scope fields are CONSUMED by
        # _match_damage (dealer=cause filter, combat flag on the DAMAGE
        # row), so the pre-16c bind-time raise is retired — Harbinger/
        # Subira/Pyreling/Incinerator shapes bind and scope-filter (the
        # firing semantics are pinned in test_executor_blockers).
        self.assertEqual(
            self.attach_trigger(
                self.watch, DamageDealtEvent(QConst(1), UNIV, source=UNIV), gain(1)
            ),
            1,
        )
        self.assertEqual(
            self.attach_trigger(
                self.watch, DamageDealtEvent(QConst(1), UNIV, combat=True), gain(1)
            ),
            1,
        )
        # The plain scope-less damage event BINDS fine (flag, don't over-flag).
        self.assertEqual(
            self.attach_trigger(self.watch, DamageDealtEvent(QConst(1), UNIV), gain(1)),
            1,
        )

    def test_trigger_loop_tripwire_caps_and_raises(self):
        # Looper's own ETB shuffles itself graveyard->battlefield: an
        # unconditional self-retrigger chain. MAX fires resolve, then the
        # cap RAISES — the loop is a bug to flag, never a bug to run.
        loop = Seq(
            (
                atom(Verb.MOVE_ZONE, cards=referent_sel("event"), destination=GY_ANY),
                atom(Verb.MOVE_ZONE, cards=referent_sel("event"), destination=BF_ANY),
            )
        )
        looper = self.world.add_card(card_id("Looper", "1", "1"), self.p0, ZONE_HAND)
        self.ex.attach_card(
            looper, self.record_for(looper, [etb_trigger(loop)], name="Looper")
        )
        with self.assertRaises(RuntimeError):
            self.ex.execute(
                enter(BF_YOU),
                source=looper,
                controller=self.p0,
                bindings={"cards": looper},
            )
        self.assertGreaterEqual(MAX_TRIGGER_FIRES, 200)


class TestMayAndDeterminism(BindingCase):
    def test_may_offer_consumes_decisions_in_fire_order(self):
        """AMENDED 14b (B-4 rebuild): the positional trigger_decisions
        stream is DELETED; may-offers answer through the executor's
        vocabulary-addressed stream — the two firings ask under their own
        source's key, so each answers per key, in ask order."""
        first = self.world.add_card(card_id("E1", "1", "1"), self.p0, ZONE_HAND)
        second = self.world.add_card(card_id("E2", "1", "1"), self.p0, ZONE_HAND)
        for e in (first, second):
            self.ex.attach_card(
                e, self.record_for(e, [etb_trigger(OptionalEffect(gain(2)))])
            )
        both = sorted([first, second])
        self.ex.decisions.push(("fire", "skip"), f"may:{both[0]}", "fire")
        self.ex.decisions.push(("fire", "skip"), f"may:{both[1]}", "skip")
        self.ex.execute(
            enter(BF_YOU),
            source=both[0],
            controller=self.p0,
            bindings={"cards": both},
        )
        self.assertEqual(self.life(self.p0), 22)

    def test_replay_of_the_trigger_chain_is_fingerprint_identical(self):
        self.assertEqual(self._replay_chain(seed=3), self._replay_chain(seed=3))

    def _replay_chain(self, seed):
        """ETB draws -> the draw trigger mills (life feed would self-loop) —
        a scripted multi-trigger chain replayed twice fingerprints equal."""
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=seed)
        p0 = world.player_order[0]
        watcher = world.add_card(card_id("Watcher", "1", "1"), p0, ZONE_BATTLEFIELD)
        for i in (1, 2, 3, 4, 5):
            world.add_card(card_id(f"L{i}"), p0)
        trigger_card = world.add_card(card_id("Drawsy", "1", "1"), p0, ZONE_HAND)
        ex = Executor(world)

        def rec(handle, abilities):
            return record_of(abilities, oid=world.cards[handle].identity.oracle_id)

        ex.attach_card(
            watcher,
            rec(
                watcher,
                [TriggeredAbility(CardDrawnEvent(ControllerRef.YOU), None, mill_one())],
            ),
        )
        ex.attach_card(trigger_card, rec(trigger_card, [etb_trigger(draw_one())]))
        ex.begin_turn(p0)
        ex.execute(
            enter(BF_YOU),
            source=trigger_card,
            controller=p0,
            bindings={"cards": trigger_card},
        )
        ex.execute(draw_one(), source=watcher, controller=p0)
        ex.end_turn()
        # Chain fired: ETB drew, the draw trigger milled, the direct draw
        # drew again and milled again.
        # AMENDED 14a (2026-09-30): the turn skeleton gained its DRAW step
        # (CR 504.5-c, `Executor._turn_draw`) — begin_turn now draws for the
        # active seat, so the chain runs ONE MORE draw at its head: 3 cards
        # end in hand. The library is 5 deep and the feed is now 3 draws + 3
        # mill attempts, so the third mill finds an empty library (CR 121.2
        # no-op through _v_mill) and the graveyard stays 2 deep. Pre-14a this
        # pinned 2/2 because the skeleton had NO draw step at all (the games
        # harness found it: without a per-turn draw a real game stalls). The
        # chain's SHAPE is unchanged — one extra link at the head.
        self.assertEqual(len(world.players[p0].zone(ZONE_HAND).entries), 3)
        self.assertEqual(len(world.players[p0].zone(ZONE_GRAVEYARD).entries), 2)
        return ex.state_fingerprint()


if __name__ == "__main__":
    unittest.main()
