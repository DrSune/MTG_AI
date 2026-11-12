"""The trigger binding layer.

Pins: compiled-ability attachment (oracle-id bridge identity-checked,
detach-on-leave / re-register-on-re-enter), the structured event journal
(zone moves, dies was-snapshots, draws with per-turn ordinals,
counters, taps, damage, life, turn-phase markers), the APNAP fire loop with
Handle tie-break, may-offer decisions consumed in fire order, the
DelayedTrigger window with its end-of-turn expiry, the 200-fire loop
tripwire, which event nodes bind and which still raise NotImplementedError —
and the replay fingerprint across a scripted multi-trigger chain.
"""

import itertools
import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    BecomesBlockedEvent,
    CardDrawnEvent,
    Choose,
    CardRecord,
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
    QUnbounded,
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
from MTG_bot.core.executor.decisions import in_trigger_order, site_digest
from MTG_bot.core.executor.events import KIND_CREATURE_DIES, GameEvent
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_verbs import stock_libraries

_ORACLE_SEQ = itertools.count(100)


def reset_oracle_ids():
    global _ORACLE_SEQ
    _ORACLE_SEQ = itertools.count(100)


def card_id(
    name,
    power=None,
    toughness=None,
    type_line="Creature",
    cmc=2,
    oid=None,
    colors=(),
):
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
        colors=tuple(colors),
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
    """The referent selector convention (bound object, never a search)."""
    return Selector(
        QConst(1), SelectorMode.CHOOSE, filter_, zones=(ANY_ANY,), referent=referent
    )


def named_sel(name: str) -> Selector:
    """Deterministic CHOOSE designation by printed name."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(FAtomPred.NAME_EQ, string_value=name),
        zones=(BF_ANY,),
    )


def all_bf() -> Selector:
    return Selector(QConst(1), SelectorMode.ALL, UNIV, zones=(BF_ANY,))


def enter(dest: Zone) -> Atom:
    """MOVE_ZONE with the cards role filled by a placeholder Selector — the
    designated objects ride in via ``bindings={"cards": ...}`` (the
    selector is never resolved when a binding exists)."""
    return atom(
        Verb.MOVE_ZONE,
        cards=Selector(QConst(9), SelectorMode.ALL, UNIV, zones=(ANY_ANY,)),
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
    # The mill shape: MOVE_ZONE with the MILL journal kind.
    return atom(
        Verb.MOVE_ZONE,
        controller=ControllerRef.YOU,
        amount=QConst(1),
        **{
            "destination": Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
            "from": LIB_YOU,
            "journal_kind": "MILL",
            "pop_order": "TOP",
        },
    )


def draw_one() -> Atom:
    # Only a DRAW atom draws (CR 121.1, 121.5); the tests using this helper mean
    # a real draw.
    return atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1))


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
                    TurnPhaseEvent(
                        Phase.UPKEEP,
                        FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                    ),
                    None,
                    gain(1),
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
            atom(
                Verb.MOVE_ZONE,
                target=all_bf(),
                destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER),
            ),
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
            atom(
                Verb.MOVE_ZONE,
                target=all_bf(),
                destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER),
            ),
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
    def test_dies_trigger_with_no_target_does_not_bind_the_dead_creature(self):
        # Cavalier of Flame (M20): "When this creature dies, it deals 1 damage to each
        # creature your opponents control" has no target. The dead creature the dies firing
        # binds for the "that player" anaphora (Massacre Wurm) must not become the ALL
        # selector's ``target``: the damage goes to each opponent's creature.
        opp_creature = self.world.add_card(card_id("Opp Bear", "2", "2"), self.p1, ZONE_BATTLEFIELD)
        each_opp_creature = Selector(
            QUnbounded(),
            SelectorMode.ALL,
            FAnd(
                (
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT),
                    CREATURE,
                )
            ),
            zones=(BF_ANY,),
        )
        self.attach_trigger(
            self.watch,
            CreatureDiesEvent(filter=IS_SOURCE),
            atom(Verb.DEAL_DAMAGE, amount=QConst(1), target=each_opp_creature),
        )
        self.ex.execute(
            atom(Verb.DESTROY, target=all_bf()),
            source=self.watch,
            controller=self.p0,
            bindings={"target": self.watch},
        )
        self.assertEqual(self.world.zone_of(self.watch).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.ex.damage, {opp_creature: 1})

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
        # pays the WAS power (4) — the was-snapshot, not the printed value.
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
        # The row carries the controller and the token flag as of death
        # (CR 603.10a).
        _from, was_owner, was_type, was_p, was_t, was_controller, was_token = dies[0].data
        self.assertEqual((was_p, was_t), (4, 2))
        self.assertEqual(was_type, "Creature")
        self.assertEqual(was_owner, self.p0)
        self.assertEqual((was_controller, was_token), (self.p0, False))

    def test_draw_ordinal_trigger(self):
        self.attach_trigger(  # second card drawn this turn -> +1
            self.watch,
            CardDrawnEvent(
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU), ordinal=2
            ),
            gain(1),
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
        self.attach_trigger(
            self.watch,
            LifeGainedEvent(FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)),
            mill_one(),
        )
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
                    TriggeredAbility(
                        SacrificeEvent(
                            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
                        ),
                        None,
                        gain(1),
                    ),
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
        stock_libraries(self.world, seats=[self.p1])  # p1's turn draws (CR 704.5b)
        self.ex.attach_card(
            self.watch,
            self.record_for(
                self.watch,
                [
                    TriggeredAbility(
                        TurnPhaseEvent(
                            Phase.UPKEEP,
                            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                        ),
                        None,
                        gain(1),
                    ),
                    TriggeredAbility(
                        TurnPhaseEvent(
                            Phase.END_TURN,
                            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                        ),
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
        # Both creatures enter in ONE op (simultaneous). CR 603.3b: the active
        # player (p0) puts its trigger on the stack first and p1's goes on top,
        # so p1's resolves first and p0's LAST — the last SET_PT (1/1) wins the
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
        self.assertEqual((power, toughness), (1, 1))
        self.assertEqual(self.world.triggers, [])  # fully drained

    def test_a_trigger_from_a_resolving_trigger_goes_above_the_waiting_ones(self):
        # CR 405.5 with 603.3: a trigger is put on the stack the next time a player would
        # receive priority, above the ones still waiting. c0 (p0, active) and c1 (p1) enter
        # together; p1's ETB resolves first (CR 603.3b) and makes p1 draw, which triggers p0's
        # Watcher ("whenever an opponent draws a card"). The Watcher's trigger resolves next,
        # before p0's older ETB, so p0's ETB (1/1) is the last SET_PT.
        watcher = self.world.add_card(card_id("Watcher", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        watch = TriggeredAbility(
            event=CardDrawnEvent(
                actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT)
            ),
            condition=None,
            effect=atom(
                Verb.SET_PT,
                target=named_sel("Target"),
                duration=DurationEot(),
                power=QConst(7),
                toughness=QConst(7),
            ),
        )
        self.ex.attach_card(
            watcher, record_of([watch], oid=self.world.cards[watcher].identity.oracle_id)
        )
        self.ex.attach_card(self.c0, self.set_pt_rec(self.c0, 1))
        draw = etb_trigger(
            atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1))
        )
        self.ex.attach_card(
            self.c1, record_of([draw], oid=self.world.cards[self.c1].identity.oracle_id)
        )
        stock_libraries(self.world, seats=[self.p1])
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
        self.assertEqual((power, toughness), (1, 1))
        self.assertEqual(self.world.triggers, [])


class TestModalTrigger(BindingCase):
    """CR 603.3c: a modal triggered ability's mode is chosen as it is put on the stack, and its
    targets are then chosen for that mode only; CR 700.2a: a mode that needs a target with no
    legal choice can't be chosen (Voracious Hydra, Dread Presence: no target is asked for under
    the other mode, and the targeted mode is not on offer with nothing to target)."""

    def setUp(self):
        super().setUp()
        self.asks: list[tuple[tuple[str, ...], str]] = []
        self.answers: dict[str, str] = {}

        def provider(vocab, what):
            self.asks.append((tuple(vocab), what))
            for prefix, answer in self.answers.items():
                if what.startswith(prefix) and answer in vocab:
                    return answer
            return vocab[0]

        self.ex.decisions.provider = provider
        # "When this creature enters, choose one: you gain 2 life; or this creature deals
        # 3 damage to target creature an opponent controls."
        opp_creature = FAnd(
            (FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT), CREATURE)
        )
        burn = atom(
            Verb.DEAL_DAMAGE,
            amount=QConst(3),
            target=Selector(QConst(1), SelectorMode.TARGET, opp_creature, zones=(BF_ANY,)),
        )
        self.hydra = self.world.add_card(card_id("Hydra", "1", "1"), self.p0, ZONE_HAND)
        self.ex.attach_card(
            self.hydra,
            self.record_for(
                self.hydra,
                [etb_trigger(Choose(count=QConst(1), options=(gain(2), burn)))],
            ),
        )

    def enter(self) -> None:
        self.ex.execute(
            enter(BF_OWNER), source=self.hydra, controller=self.p0, bindings={"cards": self.hydra}
        )

    def test_with_no_legal_target_only_the_other_mode_can_be_chosen(self):
        self.enter()
        self.assertEqual(self.life(self.p0), 22)  # the burn mode was not on offer
        self.assertEqual([what for _v, what in self.asks if what.startswith("target")], [])
        self.assertEqual([what for _v, what in self.asks if what.startswith("choose")], [])

    def test_the_target_is_chosen_only_for_the_chosen_mode(self):
        ogre = self.world.add_card(card_id("Ogre", "5", "5"), self.p1, ZONE_BATTLEFIELD)
        self.world.add_card(card_id("Troll", "5", "5"), self.p1, ZONE_BATTLEFIELD)
        self.answers["target"] = str(ogre)
        self.answers["choose"] = "0"  # gain 2 life
        self.enter()
        self.assertEqual(self.life(self.p0), 22)
        self.assertEqual([what for _v, what in self.asks if what.startswith("target")], [])
        self.assertEqual(self.ex.damage, {})
        self.answers["choose"] = "1"
        self.asks.clear()
        self.ex.execute(
            atom(Verb.MOVE_ZONE, cards=all_bf(), destination=Zone(ZoneKind.HAND, ControllerRef.OWNER)),
            source=self.hydra,
            controller=self.p0,
            bindings={"cards": self.hydra},
        )
        self.enter()
        self.assertEqual(self.ex.damage, {ogre: 3})
        self.assertIn("choose", [what.split(":")[0] for _v, what in self.asks])


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
        self.assertEqual(len(self.ex.binder.delayed), 1)  # scheduled
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
        # A StepEvent still raises on bind. The other feeds bind CLEAN
        # (checked below): DeclareAttackersEvent (DECLARE_ATTACKERS rows),
        # combat damage as DamageDealtEvent(combat=True) (DAMAGE rows with
        # is_combat=True), DeclareBlockersEvent / BecomesBlockedEvent
        # (DECLARE_BLOCKERS pair rows) and TargetingEvent (the TARGETING
        # rows journal.emit_targeting writes at every designation;
        # binding.py._match_node subscribes them). CastSpellEvent binds too
        # (CAST rows, binding.py._match_cast; fired in test_executor_stack.py).
        for event in (
            StepEvent(Phase.COMBAT, Step.DECLARE_ATTACKERS, ControllerRef.YOU),
        ):
            with (
                self.subTest(event=type(event).__name__),
                self.assertRaises(NotImplementedError),
            ):
                self.attach_trigger(self.watch, event, gain(1))
        # The combat feeds bind clean.
        self.assertEqual(
            self.attach_trigger(
                self.watch, DeclareAttackersEvent(filter=UNIV), gain(1)
            ),
            1,
        )
        self.assertEqual(
            self.attach_trigger(
                self.watch,
                # Combat damage: DamageDealtEvent with combat=True.
                DamageDealtEvent(
                    amount=QUnbounded(), filter=UNIV, source=FAnd(()), combat=True
                ),
                gain(1),
            ),
            1,
        )
        # The block feed binds clean (the matcher semantics — filter/
        # SUBJECT over the blocker, blocked over the attacker, the anchored
        # BecomesBlockedEvent reading — are pinned in test_executor_blockers).
        self.assertEqual(
            self.attach_trigger(self.watch, DeclareBlockersEvent(filter=UNIV), gain(1)),
            1,
        )
        self.assertEqual(
            self.attach_trigger(self.watch, BecomesBlockedEvent(filter=UNIV), gain(1)),
            1,
        )
        # The designation feed binds clean (the TARGETING row matcher,
        # the player-subject guard and the IS_SOURCE/IS_TARGET semantics
        # are pinned in test_executor_r20b).
        self.assertEqual(
            self.attach_trigger(self.watch, TargetingEvent(filter=UNIV), gain(1)),
            1,
        )

    def test_damage_source_and_combat_scopes_bind(self):
        # The scope fields are CONSUMED by _match_damage (dealer=cause
        # filter, combat flag on the DAMAGE row), so the Harbinger/
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

    def test_once_per_event_binds_only_where_the_binder_groups_an_event(self):
        # CR 603.2c: the binder gathers one event's occurrences for a
        # declaration and a combat damage step. A once-per-event trigger on
        # any other event would trigger per occurrence, so it raises on bind.
        def once(event):
            rec = self.record_for(
                self.watch, [TriggeredAbility(event, None, gain(1), once_per_event=True)]
            )
            return self.ex.attach_card(self.watch, rec)

        self.assertEqual(once(DeclareAttackersEvent(filter=UNIV)), 1)
        self.assertEqual(
            once(DamageDealtEvent(QUnbounded(), UNIV, source=UNIV, combat=True)), 1
        )
        with self.assertRaises(NotImplementedError):
            once(CreatureDiesEvent(filter=UNIV))
        # "Whenever this creature attacks" holds one attacker per declaration: the
        # flag would be a second encoding, so the IR refuses it before any bind.
        with self.assertRaises(ValueError):
            once(DeclareAttackersEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)))

    def test_once_per_event_refused_when_scheduled_and_when_a_never_bound_one_triggers(self):
        # A flagged delayed trigger on an event the binder does not group is
        # refused as it is scheduled; one never bound (a GRANT_ABILITY grant)
        # is refused as it triggers, before it can fire per occurrence.
        dies = CreatureDiesEvent(filter=UNIV)
        with self.assertRaises(NotImplementedError):
            self.ex.binder.schedule_delayed(
                DelayedTrigger(DurationEot(), dies, None, gain(1), True), self.watch, self.p0
            )
        self.assertEqual(self.ex.binder.delayed, [])
        granted = TriggeredAbility(dies, None, gain(1), once_per_event=True)
        row = GameEvent(clock=1, kind=KIND_CREATURE_DIES, subject=self.watch, cause=None,
                        cause_verb="DESTROY")
        with self.assertRaises(NotImplementedError):
            self.ex.binder._queue(self.watch, self.p0, granted, row)
        self.assertEqual(self.world.triggers, [])

    def test_trigger_loop_tripwire_quarantines_the_loop_source(self):
        # The tripwire GUARDS instead of raising: "flag it, never run it"
        # means flag, not kill the game (Chandra's Incinerator can
        # self-retrigger). Looper's own ETB shuffles itself graveyard->
        # battlefield: MAX fires resolve, then the culprit source is
        # QUARANTINED (queued firings dropped, future _queue calls drop),
        # the event is recorded loudly in executor.trigger_loops, and the
        # drain COMPLETES normally.
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
        self.ex.execute(  # NO raise — the guard absorbs the loop
            enter(BF_YOU),
            source=looper,
            controller=self.p0,
            bindings={"cards": looper},
        )
        self.assertGreaterEqual(MAX_TRIGGER_FIRES, 200)
        self.assertEqual(len(self.ex.trigger_loops), 1)
        self.assertIn("Looper", self.ex.trigger_loops[0])
        self.assertIn(looper, self.ex.binder.quarantined)
        # The drain COMPLETED (not aborted): the queue and every firing
        # payload are consumed, and the quarantined source left nothing
        # behind. The _queue gate keeps it out for good.
        self.assertFalse(self.ex.world.triggers)
        self.assertFalse(any(str(s) == str(looper) for s in self.ex.binder.firings))

    def test_the_tripwire_also_guards_the_game_loop(self):
        # Bug hunt 2026-11-12 (KNOWLEDGE 197): the game loop resolves through all_pass, which
        # had no tripwire (only the undriven settle counted), so a self-retriggering loop with
        # both players passing never ended. One resolution path now holds it for both.
        from MTG_bot.core.executor import games as G
        from MTG_bot.core.executor import stack as S

        loop = Seq(
            (
                atom(Verb.MOVE_ZONE, cards=referent_sel("event"), destination=GY_ANY),
                atom(Verb.MOVE_ZONE, cards=referent_sel("event"), destination=BF_ANY),
            )
        )
        for seat in (self.p0, self.p1):
            for i in range(20):
                self.world.add_card(card_id(f"L{i}"), seat, ZONE_LIBRARY)
        looper = self.world.add_card(card_id("Looper", "1", "1"), self.p0, ZONE_HAND)
        self.ex.attach_card(
            looper, self.record_for(looper, [etb_trigger(loop)], name="Looper")
        )
        self.ex.decisions.provider = in_trigger_order
        self.ex.begin_turn(self.p0)
        self.ex.driven = True
        self.ex.execute(enter(BF_YOU), source=looper, controller=self.p0,
                        bindings={"cards": looper})

        class Passer:
            def answer(self, vocab, what):
                return vocab[0]

            def take_priority(self, game, seat):
                return False

        resolve, count = S.resolve_top, [0]

        def counted(executor):  # a regression fails here instead of hanging the suite
            count[0] += 1
            if count[0] > 5 * MAX_TRIGGER_FIRES:
                raise AssertionError("the game loop resolved the trigger loop past its tripwire")
            return resolve(executor)

        S.resolve_top = counted
        try:
            game = G.Game(executor=self.ex, seed=11, pool_mode="test")
            G._play(game, Passer(), self.world.player_order, 3, resumed=True)
        finally:
            S.resolve_top = resolve
        self.assertIn(looper, self.ex.binder.quarantined)
        self.assertEqual(len(self.ex.trigger_loops), 1)


class TestMayAndDeterminism(BindingCase):
    def test_may_offer_consumes_decisions_in_fire_order(self):
        """May-offers answer through the executor's vocabulary-addressed
        stream — the two firings ask under their own source's key, so each
        answers per key, in ask order."""
        first = self.world.add_card(card_id("E1", "1", "1"), self.p0, ZONE_HAND)
        second = self.world.add_card(card_id("E2", "1", "1"), self.p0, ZONE_HAND)
        for e in (first, second):
            self.ex.attach_card(
                e, self.record_for(e, [etb_trigger(OptionalEffect(gain(2)))])
            )
        both = sorted([first, second])
        # The may site tag carries the offer digest, so two may-offers on
        # one source are two keys (a source-only tag would mispair their
        # primings). The digest is value-based, so the
        # structurally identical trigger effect re-digests here.
        offer = OptionalEffect(gain(2))
        self.ex.decisions.provider = in_trigger_order  # E1's trigger resolves first (CR 603.3b)
        self.ex.decisions.push(
            ("fire", "skip"), f"may:{both[0]}:{site_digest(offer)}", "fire"
        )
        self.ex.decisions.push(
            ("fire", "skip"), f"may:{both[1]}:{site_digest(offer)}", "skip"
        )
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
                [
                    TriggeredAbility(
                        CardDrawnEvent(
                            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
                        ),
                        None,
                        mill_one(),
                    )
                ],
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
        # drew again and milled again. begin_turn(p0) is the first turn of a
        # two-player game, and the player who plays first skips its draw
        # step (CR 103.8a): ETB draw + mill, direct draw + mill = 2 in hand,
        # 2 in the graveyard, 1 left in the library.
        self.assertEqual(len(world.players[p0].zone(ZONE_HAND).entries), 2)
        self.assertEqual(len(world.players[p0].zone(ZONE_GRAVEYARD).entries), 2)
        return ex.state_fingerprint()


if __name__ == "__main__":
    unittest.main()
