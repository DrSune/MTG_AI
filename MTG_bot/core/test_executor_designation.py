"""The trigger-resolution DESIGNATION channel.

A triggered ability whose effect carries a TARGET coordinate gets its
targets at the moment it goes on the stack (CR 603.1, 601.2c) — for the
engine's direct-resolution model that means BEFORE the effect's first verb
runs.

Pinned here:

1. designate-then-apply — candidates from the engine's OWN query
   surface, vocabulary = the Handle-sorted candidate list (the
   ONE_OF ask's shape), site tag ``target:<seat>:<source>:<digest>``
   (the ability's CONTROLLER answers — cross-seat firings ask cross-seat
   keys);
2. the auto-fill (one legal filler, no ask) and the CR 603.3d
   zero-candidate answer: the ability is removed from the stack and does
   nothing; never a crash, never a guess ("up to" may choose zero, and a
   target only one mode needs leaves the other mode choosable);
3. the ``QAtMost`` multi-pick shape: every pick, the first included,
   carries the ``"NONE"`` stop token (CR 601.2c, 115.6);
4. TARGET_PLAYER routing (event-kind driven): DAMAGE → the dealer,
   CREATURE_DIES → the dead creature (Massacre Wurm's "that player"),
   self-origin "target opponent" firings → the opponent seats (Tutelage;
   duel: one seat → forced auto-fill, no ask);
5. a multi-slot trigger keeps the loud raise (never guess-bind the second);
6. Zone(ANY) runtime enumeration == the query lane's population (seat ×
   PLAYER_ZONES, the OMNISCIENT reading: hidden zones included), and the
   universal "any target" legality set includes the seats (CR 109.5);
7. query-lane pred parity: CMC_GE / ZONE_COUNT_GE /
   NAME_PARTITION_COUNT_GE answer through ONE evaluator on both lanes,
   and THAT_MANY_COUNT reads the result register — an unset register
   stays a loud read;
8. CONTROLLER_IS follows the live controller (a GAIN_CONTROL override moves
   it) while the OWNER axis stays positional, and the designation scan reads
   a CONTROLLER_IS TARGET_OPPONENT wrapped in an FAnd.
"""

import unittest

from MTG_bot.core.ability_tree import (
    CardDrawnEvent,
    Choose,
    ControllerRef,
    CounterKind,
    CreatureDiesEvent,
    FAnd,
    FAtom,
    FAtomPred,
    QAtMost,
    QConst,
    QProp,
    QPropField,
    Selector,
    SelectorMode,
    Seq,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.legality import (
    _zone_handles,
    ctx_for,
    enumerate_candidates,
)
from MTG_bot.core.executor.quantity import eval_filter, resolve
from MTG_bot.core.executor.selectors import enumerate_zone, resolve_selector
from MTG_bot.core.state import (
    PLAYER_ZONES,
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import (
    BF_ANY,
    BF_OWNER,
    BF_YOU,
    UNIV,
    atom,
    card_id,
    enter,
    etb_trigger,
    record_of,
    reset_oracle_ids,
)

ANY_ZONE = Zone(ZoneKind.ANY, ControllerRef.ANY)
HAND_YOU = Zone(ZoneKind.HAND, ControllerRef.YOU)
LIB_YOU = Zone(ZoneKind.LIBRARY, ControllerRef.YOU)
CREATURE_ONLY = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")


def any_target(count: QConst | None = None) -> Selector:
    return Selector(count or QConst(1), SelectorMode.TARGET, UNIV, zones=(ANY_ZONE,))


class DesignationCase(unittest.TestCase):
    """Carrier card in hand; the enter-op arms whatever trigger is
    attached. ``answer`` installs a recording provider."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=18)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.ex = Executor(self.world)
        self.asks: list[tuple[tuple[str, ...], str]] = []

    def tearDown(self):
        self.ex.decisions.provider = None

    def answer(self, *words):
        queue = list(words)

        def prov(vocab, what):
            self.asks.append((tuple(vocab), what))
            got = queue.pop(0) if queue else vocab[0]
            return got if got in vocab else vocab[0]

        self.ex.decisions.provider = prov

    def never_ask(self):
        def prov(vocab, what):
            raise AssertionError(f"unexpected ask: {what} {vocab}")

        self.ex.decisions.provider = prov

    def carrier(self, seat, name="Carrier", type_line="Creature"):
        return self.world.add_card(
            card_id(name, "2", "2", type_line=type_line), seat, ZONE_HAND
        )

    def attach(self, handle, trigger, name="Carrier"):
        self.ex.attach_card(
            handle,
            record_of(
                [trigger],
                name=name,
                oid=self.world.cards[handle].identity.oracle_id,
            ),
        )

    def enter(self, handle):
        self.ex.execute(
            enter(BF_OWNER),
            source=handle,
            controller=self.world.controller_of(handle),
            bindings={"cards": handle},
        )


class TestDesignateThenApply(DesignationCase):
    def test_any_target_ask_designates_a_player(self):
        # Skeleton Archer's shape: ETB deals 1 damage to ANY TARGET — the
        # population is the omniscient any-zone union PLUS the seats
        # (CR 109.5). Answering "player:1" lands the damage on p1.
        archer = self.carrier(self.p0, "Skeleton Archer")
        self.attach(
            archer,
            etb_trigger(atom(Verb.DEAL_DAMAGE, amount=QConst(1), target=any_target())),
        )
        self.answer("player:1")
        self.enter(archer)
        self.assertEqual(self.world.players[self.p1].life, 19)
        vocab, what = self.asks[0]
        self.assertIn("player:0", vocab)
        self.assertIn("player:1", vocab)
        # the site tag carries the ABILITY CONTROLLER's seat: attribution.
        self.assertTrue(what.startswith(f"target:{self.p0}:{archer}:"))

    def test_ask_vocabulary_is_the_sorted_candidate_list(self):
        # Vocab = exactly the Handle-sorted candidates (no prose) and the
        # answer is consumed as the designation (the effect's TARGET atom
        # means THAT pick).
        charger = self.carrier(self.p0, "Daybreak Charger")
        dummy = self.world.add_card(
            card_id("Dummy", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.attach(
            charger,
            etb_trigger(
                atom(
                    Verb.MOVE_ZONE,
                    cards=Selector(
                        QConst(1), SelectorMode.TARGET, CREATURE_ONLY, zones=(BF_ANY,)
                    ),
                    destination=HAND_YOU,
                )
            ),
        )
        self.answer(str(dummy))
        self.enter(charger)
        self.assertEqual(self.world.zone_of(dummy).kind, ZONE_HAND)
        vocab, what = self.asks[0]
        self.assertEqual(vocab, tuple(sorted((str(charger), str(dummy)))))
        self.assertTrue(what.startswith(f"target:{self.p0}:{charger}:"))

    def test_forced_single_candidate_never_asks(self):
        # Auto-fill: one legal filler designates silently — asking a
        # question with one legal answer is noise, not a decision.
        mutt = self.carrier(self.p0, "Rambunctious Mutt")
        art = self.world.add_card(
            card_id("Battery", "0", "1", type_line="Artifact"),
            self.p1,
            ZONE_BATTLEFIELD,
        )
        self.attach(
            mutt,
            etb_trigger(
                atom(
                    Verb.MOVE_ZONE,
                    target=Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAtom(FAtomPred.TYPE_EQ, string_value="Artifact"),
                        zones=(BF_ANY,),
                    ),
                    destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER),
                )
            ),
        )
        self.never_ask()
        self.enter(mutt)
        self.assertEqual(self.world.zone_of(art).kind, "exile")
        self.assertEqual(self.asks, [])

    def test_zero_candidates_resolves_doing_nothing(self):
        # CR 603.3d: the ability that cannot designate is REMOVED FROM THE
        # STACK — not a crash, not a guess. Artifact carrier, no creature
        # you control anywhere.
        amulet = self.carrier(self.p0, "Amulet", type_line="Artifact")
        self.attach(
            amulet,
            etb_trigger(
                atom(
                    Verb.PUT_COUNTER,
                    counter_kind=CounterKind.PLUS_1_PLUS_1,
                    count=QConst(1),
                    target=Selector(
                        QConst(1), SelectorMode.TARGET, CREATURE_ONLY, zones=(BF_YOU,)
                    ),
                )
            ),
            name="Amulet",
        )
        self.never_ask()
        self.enter(amulet)  # no raise at the TARGET selector
        self.assertEqual(dict(self.world.cards[amulet].counters), {})

    def _counter_then_gain(self, count):
        """"Put a +1/+1 counter on <count> target creature you control.
        You gain 3 life." — a targeted step plus an untargeted one."""
        return Seq(
            (
                atom(
                    Verb.PUT_COUNTER,
                    counter_kind=CounterKind.PLUS_1_PLUS_1,
                    count=QConst(1),
                    target=Selector(
                        count, SelectorMode.TARGET, CREATURE_ONLY, zones=(BF_YOU,)
                    ),
                ),
                atom(Verb.GAIN_LIFE, amount=QConst(3), controller=ControllerRef.YOU),
            )
        )

    def test_required_target_missing_removes_the_whole_ability(self):
        # CR 603.3d: a trigger whose required target has no legal choice
        # is removed from the stack, so its UNTARGETED step never happens
        # either: no 3 life.
        amulet = self.carrier(self.p0, "Amulet", type_line="Artifact")
        self.attach(amulet, etb_trigger(self._counter_then_gain(QConst(1))), name="Amulet")
        self.never_ask()
        self.enter(amulet)
        self.assertEqual(self.world.players[self.p0].life, 20)

    def test_up_to_target_missing_still_resolves_the_rest(self):
        # Control: "up to one target" may legally choose ZERO targets, so
        # the ability goes on the stack with none and its untargeted step
        # still happens (CR 601.2c, 115.1).
        amulet = self.carrier(self.p0, "Amulet", type_line="Artifact")
        self.attach(amulet, etb_trigger(self._counter_then_gain(QAtMost(1))), name="Amulet")
        self.never_ask()
        self.enter(amulet)
        self.assertEqual(self.world.players[self.p0].life, 23)

    def test_mode_dependent_target_missing_keeps_the_other_mode(self):
        # Control: "Choose one — put a +1/+1 counter on target creature you
        # control; or you gain 3 life." A target that only one mode needs
        # does not remove the ability (CR 700.2a: the other mode is still
        # choosable), so choosing the life mode gains the life.
        amulet = self.carrier(self.p0, "Amulet", type_line="Artifact")
        steps = self._counter_then_gain(QConst(1)).steps
        self.attach(
            amulet,
            etb_trigger(Choose(QConst(1), (steps[0], steps[1]))),
            name="Amulet",
        )
        self.answer("1")  # option set 1 = the life mode
        self.enter(amulet)
        self.assertEqual(self.world.players[self.p0].life, 23)

    def test_up_to_multi_pick_carries_the_none_token(self):
        # The TARGET+QAtMost range is 0..n (CR 601.2c, 115.6), so EVERY
        # pick offers the "NONE" stop token, the first included.
        acolyte = self.carrier(self.p0, "Basri's Acolyte")
        d1 = self.world.add_card(
            card_id("Dummy One", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        d2 = self.world.add_card(
            card_id("Dummy Two", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.attach(
            acolyte,
            etb_trigger(
                atom(
                    Verb.PUT_COUNTER,
                    counter_kind=CounterKind.PLUS_1_PLUS_1,
                    count=QConst(1),
                    target=Selector(
                        QAtMost(2), SelectorMode.TARGET, CREATURE_ONLY, zones=(BF_YOU,)
                    ),
                )
            ),
            name="Basri's Acolyte",
        )
        self.answer(str(d2), "NONE")
        self.enter(acolyte)
        self.assertEqual(dict(self.world.cards[d2].counters), {"PLUS_1_PLUS_1": 1})
        self.assertEqual(dict(self.world.cards[d1].counters), {})
        first_vocab, second_vocab = self.asks[0][0], self.asks[1][0]
        self.assertEqual(first_vocab, (str(acolyte), str(d1), str(d2), "NONE"))
        # pool minus the first pick, stop token appended; the acolyte
        # itself is a legal creature candidate all along.
        self.assertEqual(second_vocab, (str(acolyte), str(d1), "NONE"))


class TestTargetPlayerRouting(DesignationCase):
    def test_dies_binds_the_anaphoric_controller(self):
        # Massacre Wurm's twin: "whenever a creature an opponent controls
        # dies, that player loses 2 life" — TARGET_PLAYER is EVENT-bound
        # to the dead creature (the DAMAGE-dealer routing mirrored): NO
        # ask, the controller folds out of the subject.
        wurm = self.world.add_card(
            card_id("Massacre Wurm", "5", "5"), self.p0, ZONE_BATTLEFIELD
        )
        prey = self.world.add_card(card_id("Prey", "1", "1"), self.p1, ZONE_BATTLEFIELD)
        self.attach(
            wurm,
            TriggeredAbility(
                event=CreatureDiesEvent(
                    FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT)
                ),
                condition=None,
                effect=atom(
                    Verb.LOSE_LIFE,
                    amount=QConst(2),
                    controller=ControllerRef.TARGET_PLAYER,
                ),
            ),
            name="Massacre Wurm",
        )
        self.never_ask()
        self.ex.execute(
            atom(
                Verb.DEAL_DAMAGE,
                amount=QConst(3),
                target=Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(BF_ANY,)),
            ),
            source=wurm,
            controller=self.p0,
            bindings={"target": prey},
        )
        self.assertEqual(self.world.zone_of(prey).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.players[self.p1].life, 18)

    def test_self_fire_designates_the_opponent_seat(self):
        # "Target opponent" is TARGET_OPPONENT (a TARGET_PLAYER names any player, so it
        # would ask over both seats).
        # Tutelage's twin: "whenever YOU draw a card, target opponent mills
        # one" — a self-origin firing has no anaphoric antecedent, so the
        # opponent seat is designated (duel: one seat → auto-fill, no ask).
        dower = self.carrier(self.p0, "Tutelage Carrier")
        lib = self.world.add_card(card_id("Drawme"), self.p0, ZONE_LIBRARY)
        victim = self.world.add_card(card_id("Victim"), self.p1, ZONE_LIBRARY)
        self.attach(
            dower,
            TriggeredAbility(
                event=CardDrawnEvent(actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)),
                condition=None,
                effect=atom(
                    Verb.MOVE_ZONE,
                    amount=QConst(1),
                    controller=ControllerRef.TARGET_OPPONENT,
                    **{
                        "destination": Zone(
                            ZoneKind.GRAVEYARD, ControllerRef.TARGET_OPPONENT
                        ),
                        "from": Zone(ZoneKind.LIBRARY, ControllerRef.TARGET_OPPONENT),
                        "journal_kind": "MILL",
                        "pop_order": "TOP",
                    },
                ),
            ),
            name="Tutelage Carrier",
        )
        self.never_ask()
        self.enter(dower)  # arms the draw trigger
        # Only a DRAW atom draws (CR 121.1, 121.5); a library-to-hand MOVE_ZONE
        # is not a draw. Drawme is the top card, so the draw takes it.
        self.ex.execute(
            atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1)),
            source=dower,
            controller=self.p0,
        )
        self.assertEqual(self.world.zone_of(lib).kind, ZONE_HAND)
        self.assertEqual(self.world.zone_of(victim).kind, ZONE_GRAVEYARD)


class TestZoneAnyEnumeration(DesignationCase):
    def test_runtime_union_equals_query_lane(self):
        # Query/runtime identity: selectors.enumerate_zone(ANY) IS legality
        # ._zone_handles(ANY) — seat × PLAYER_ZONES order, omniscient
        # (libraries and the opponent's hidden hand ride along: the
        # OMNISCIENT policy, a known model gap, never silently hidden).
        for i in range(3):
            self.world.add_card(card_id(f"L{i}"), self.p0, ZONE_LIBRARY)
        self.world.add_card(card_id("H0"), self.p1, ZONE_HAND)
        ctx = ctx_for(self.ex, source=self.p0, controller=self.p0)
        query_lane = _zone_handles(ctx, ANY_ZONE)
        runtime_lane = enumerate_zone(ctx, ANY_ZONE)
        self.assertEqual(query_lane, runtime_lane)
        self.assertEqual(
            len(runtime_lane),
            sum(
                len(self.world.players[p].zone(z).entries)
                for p in self.world.player_order
                for z in PLAYER_ZONES
            ),
        )

    def test_owner_any_stays_flagged(self):
        ctx = ctx_for(self.ex, source=self.p0, controller=self.p0)
        with self.assertRaises(NotImplementedError):
            enumerate_zone(ctx, Zone(ZoneKind.ANY, ControllerRef.OWNER))

    def test_any_universal_legality_includes_the_seats(self):
        # CR 109.5 runtime twin: a designated PLAYER survives the TARGET
        # legality filter for the universal ANY selector — and a
        # NON-universal filter never smuggles a player in.
        card = self.world.add_card(
            card_id("Victim", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        ctx = ctx_for(
            self.ex,
            source=card,
            controller=self.p0,
            bindings={"target": [self.p1]},
        )
        self.assertEqual(resolve_selector(any_target(), ctx), [self.p1])
        creature_only = Selector(
            QConst(1), SelectorMode.TARGET, CREATURE_ONLY, zones=(ANY_ZONE,)
        )
        self.assertEqual(resolve_selector(creature_only, ctx), [])


class TestMultiSlotStaysLoud(DesignationCase):
    def test_two_distinct_targets_raise_never_guess_bind(self):
        # One trigger designation channel cannot serve two DISTINCT TARGET
        # slots — the raise stands.
        twin = self.carrier(self.p0, "Twin Carrier")
        self.attach(
            twin,
            etb_trigger(
                Seq(
                    steps=(
                        atom(
                            Verb.EXILE,
                            target=Selector(
                                QConst(1),
                                SelectorMode.TARGET,
                                FAtom(FAtomPred.TYPE_EQ, string_value="Artifact"),
                                zones=(BF_ANY,),
                            ),
                        ),
                        atom(
                            Verb.TAP,
                            target=Selector(
                                QConst(1),
                                SelectorMode.TARGET,
                                FAtom(FAtomPred.TYPE_EQ, string_value="Land"),
                                zones=(BF_ANY,),
                            ),
                        ),
                    )
                )
            ),
        )
        self.answer("unused")  # any provider: the raise fires BEFORE asks
        with self.assertRaises(NotImplementedError) as cm:
            self.enter(twin)
        self.assertIn("designation slots", str(cm.exception))


class TestQueryLanePredParity(DesignationCase):
    """One evaluator: query context and effect context answer the SAME
    for these preds."""

    def test_cmc_ge_one_evaluator_both_lanes(self):
        cheap = self.world.add_card(card_id("Cheap", "1", "1", cmc=5), self.p0)
        big = self.world.add_card(
            card_id("Big", "6", "6", cmc=6), self.p0, ZONE_LIBRARY
        )
        pred = FAtom(FAtomPred.CMC_GE, count=QConst(6))
        selector = Selector(QAtMost(5), SelectorMode.CHOOSE, FAnd((pred,)), zones=(LIB_YOU,))
        ctx = ctx_for(self.ex, source=self.p0, controller=self.p0)
        # query lane (legal_targets' population):
        self.assertEqual(enumerate_candidates(selector, ctx), [big])
        # runtime lane (the effect's own resolve_selector): identical.
        self.assertEqual(resolve_selector(selector, ctx), [big])
        self.assertTrue(eval_filter(pred, big, ctx))
        self.assertFalse(eval_filter(pred, cheap, ctx))

    def test_zone_count_ge_gate_answers(self):
        # Thieves' Guild Enforcer's gate: "<opponent> has >= n cards in
        # their graveyard" — TRUE iff ANY denoted player reaches n.
        for i in range(2):
            self.world.add_card(
                card_id(f"G{i}", None, None, type_line="Instant"),
                self.p1,
                ZONE_GRAVEYARD,
            )
        anchor = self.world.add_card(
            card_id("Anchor", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        ctx = ctx_for(self.ex, source=anchor, controller=self.p0)

        def gate(n: int):
            return FAtom(
                FAtomPred.ZONE_COUNT_GE,
                who=ControllerRef.OPPONENT,
                zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.OPPONENT),
                inner_filter=FAtom(FAtomPred.TYPE_EQ, string_value="Instant"),
                count=QConst(n),
            )

        self.assertTrue(eval_filter(gate(2), anchor, ctx))
        self.assertFalse(eval_filter(gate(3), anchor, ctx))
        # inner_filter bites: a nonmatching population never counts.
        gy_gate = FAtom(
            FAtomPred.ZONE_COUNT_GE,
            who=ControllerRef.OPPONENT,
            zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.OPPONENT),
            inner_filter=FAtom(FAtomPred.TYPE_EQ, string_value="Sorcery"),
            count=QConst(1),
        )
        self.assertFalse(eval_filter(gy_gate, anchor, ctx))

    def test_name_partition_is_mine_only(self):
        # Chrome Replicator: EXACT-name partitions among the
        # permanents the ABILITY CONTROLLER controls — the opponent's
        # twins never count toward mine.
        a = self.world.add_card(card_id("Twin"), self.p0, ZONE_BATTLEFIELD)
        b = self.world.add_card(card_id("Twin"), self.p0, ZONE_BATTLEFIELD)
        self.world.add_card(card_id("Other"), self.p0, ZONE_BATTLEFIELD)
        self.world.add_card(card_id("Twin"), self.p1, ZONE_BATTLEFIELD)
        pred = FAtom(
            FAtomPred.NAME_PARTITION_COUNT_GE,
            inner_filter=UNIV,
            count=QConst(2),
        )
        self.assertTrue(
            eval_filter(pred, a, ctx_for(self.ex, source=a, controller=self.p0))
        )
        self.assertFalse(
            eval_filter(pred, a, ctx_for(self.ex, source=a, controller=self.p1))
        )
        self.assertIsNotNone(b)

    def test_that_many_reads_the_result_register(self):
        # Kinetic Augur's wiring: DISCARD writes the result register
        # and the continuation counts it — "discard two, gain life equal
        # to the number of cards discarded" answers 2, not a guess.
        augur = self.carrier(self.p0, "Kinetic Augur")
        for i in range(2):
            self.world.add_card(
                card_id(f"Discard{i}", None, None, type_line="Instant"),
                self.p0,
                ZONE_HAND,
            )
        self.attach(
            augur,
            etb_trigger(
                Seq(
                    steps=(
                        atom(
                            Verb.MOVE_ZONE,
                            cards=Selector(
                                QConst(2), SelectorMode.CHOOSE, UNIV, zones=(HAND_YOU,)
                            ),
                            controller=ControllerRef.YOU,
                            **{
                                "destination": Zone(
                                    ZoneKind.GRAVEYARD, ControllerRef.YOU
                                ),
                                "from": HAND_YOU,
                            },
                        ),
                        atom(
                            Verb.GAIN_LIFE,
                            controller=ControllerRef.YOU,
                            amount=QProp(
                                referent="event",
                                field=QPropField.THAT_MANY_COUNT,
                            ),
                        ),
                    )
                )
            ),
            name="Kinetic Augur",
        )
        self.enter(augur)
        self.assertEqual(self.world.players[self.p0].life, 22)

    def test_that_many_unset_stays_a_loud_read(self):
        # THIS_WAY's absence is a benign 0 (a declined may legitimately
        # leaves it unwritten); THAT_MANY has NO zero-reading — the compiler
        # only places it in a mandatory continuation, so a missing
        # antecedent is a missing question: flag, never guess 0.
        anchor = self.world.add_card(
            card_id("Anchor", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        # The grammar pins THAT_MANY to the 'event' referent, so the
        # probe ctx carries an EVENT subject but NO result producer — the
        # register read itself, not the handle read, must stay loud.
        ctx = ctx_for(
            self.ex,
            source=anchor,
            controller=self.p0,
            bindings={"event": anchor},
        )
        with self.assertRaises(NotImplementedError) as cm:
            resolve(
                QProp(referent="event", field=QPropField.THAT_MANY_COUNT),
                ctx,
            )
        self.assertIn("THAT_MANY_COUNT", str(cm.exception))


class TestE1ControllerAxis(DesignationCase):
    """CONTROLLER_IS is the ONE direction axis, judged through the live
    ``controller_of`` read — a GAIN_CONTROL override moves it — while the
    OWNER axis stays purely positional (the zone seat). The folded BF/ANY
    selector shape (seat in the zone dropped, direction as a filter atom)
    must agree."""

    def _stolen(self):
        prey = self.world.add_card(
            card_id("Prey", "1", "1"), self.p1, ZONE_BATTLEFIELD
        )
        anchor = self.world.add_card(
            card_id("Anchor", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.assertTrue(self.ex.gain_control(prey, self.p0, "Anchor", anchor))
        return prey, anchor

    def test_controller_is_follows_the_overlay(self):
        prey, anchor = self._stolen()
        ctx = ctx_for(self.ex, source=anchor, controller=self.p0)
        you = FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
        opp = FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT)
        self.assertTrue(eval_filter(you, prey, ctx))
        self.assertFalse(eval_filter(opp, prey, ctx))

    def test_owner_axis_stays_positional(self):
        prey, anchor = self._stolen()
        # a stolen permanent still sits on its owner's battlefield (CR 400.7e)
        self.assertEqual(self.ex.controller_of(prey), self.p0)
        self.assertEqual(self.world.controller_of(prey), self.p1)
        self.assertEqual(self.world.zone_of(prey).controller, self.p1)

    def test_folded_bf_any_selector_reads_the_overlay(self):
        prey, anchor = self._stolen()
        own = self.world.add_card(
            card_id("Mine", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        sel = Selector(
            QConst(1),
            SelectorMode.ALL,
            FAnd(
                (
                    CREATURE_ONLY,
                    FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                )
            ),
            zones=(BF_ANY,),
        )
        mine_ctx = ctx_for(self.ex, source=anchor, controller=self.p0)
        got = resolve_selector(sel, mine_ctx)
        self.assertIn(prey, got, "the fold routes enumeration through controller_of")
        self.assertIn(own, got)
        theirs_ctx = ctx_for(self.ex, source=prey, controller=self.p1)
        self.assertNotIn(prey, resolve_selector(sel, theirs_ctx))


class TestTargetPlayerNestedFilter(DesignationCase):
    """The designation scan reads CONTROLLER_IS TARGET_OPPONENT THROUGH an
    FAnd bundle (Teferi, Timeless Voyager's shape): the opponent seat is
    designated and the filter-bound selector enumerates through it."""

    def _tp_wrapped(self, mode):
        # "Target opponent" is TARGET_OPPONENT (a TARGET_PLAYER names any player, so it
        # would ask over both seats).
        dower = self.carrier(self.p0)
        theirs = self.world.add_card(
            card_id("Theirs", "1", "1"), self.p1, ZONE_BATTLEFIELD
        )
        mine = self.world.add_card(
            card_id("Mine", "1", "1"), self.p0, ZONE_BATTLEFIELD
        )
        self.attach(
            dower,
            etb_trigger(
                atom(
                    Verb.MOVE_ZONE,
                    amount=QConst(1),
                    **{
                        "destination": Zone(
                            ZoneKind.EXILE, ControllerRef.TARGET_OPPONENT
                        ),
                    },
                    cards=Selector(
                        QConst(1),
                        mode,
                        FAnd(
                            (
                                CREATURE_ONLY,
                                FAtom(
                                    FAtomPred.CONTROLLER_IS,
                                    who=ControllerRef.TARGET_OPPONENT,
                                ),
                            )
                        ),
                        zones=(BF_ANY,),
                    ),
                )
            ),
        )
        return dower, theirs, mine

    def test_wrapped_player_filter_opens_the_lane(self):
        # Teferi TV's (0, True) shape: no TARGET-mode selector, the ONLY
        # target-player touchpoint is the filter wrapped in FAnd.
        dower, theirs, mine = self._tp_wrapped(SelectorMode.CHOOSE)
        self.never_ask()  # duel: one opponent seat -> forced auto-fill
        self.enter(dower)
        self.assertEqual(
            self.world.zone_of(theirs).kind,
            ZONE_EXILE,
            "the wrapped filter bound through the designated seat",
        )
        self.assertEqual(self.world.zone_of(mine).kind, ZONE_BATTLEFIELD)

    def test_target_slot_plus_player_lane_stays_loud(self):
        # A TARGET-mode selector AND a separate target-player read is two
        # slots — never guess-bind the second.
        dower, _theirs, _mine = self._tp_wrapped(SelectorMode.TARGET)
        with self.assertRaises(NotImplementedError):
            self.enter(dower)
