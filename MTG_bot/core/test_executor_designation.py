"""Round-18b: the trigger-resolution DESIGNATION channel, pinned.

The wave-1b suspects (doc 18) died on one class: a triggered ability whose
effect carries a TARGET coordinate raised "no designation" because only the
CAST lane designated (CR 601.2c). CR 603.1 gives every triggered ability
its targets at the moment it goes on the stack — for the engine's direct-
resolution model that means BEFORE the effect's first verb runs.

Pinned here:

1. designate-then-apply — candidates from the engine's OWN 12c query
   surface (§8.3), vocabulary = the Handle-sorted candidate list (the
   ONE_OF ask's C15 shape), site tag ``target:<seat>:<source>:<digest>``
   (the ability's CONTROLLER answers — cross-seat firings ask cross-seat
   keys);
2. the §1.4 auto-fill (one legal filler, no ask) and the CR 603.4
   zero-candidate answer: bind EMPTY — the ability resolves doing nothing;
   never a crash, never a guess;
3. the C17 multi-pick shape: the first ``QAtMost`` pick mandatory (min 1
   designation), later picks carry the ``"NONE"`` stop token;
4. TARGET_PLAYER routing (event-kind driven): DAMAGE → the dealer (16a),
   CREATURE_DIES → the dead creature (18b, Massacre Wurm's "that player"),
   self-origin firings → the opponent seats (Kitesail/Tutelage; duel: one
   seat → forced auto-fill, no ask);
5. a multi-slot trigger keeps the loud raise (per-slot designation is
   /06 arc 3 — never guess-bind the second);
6. Zone(ANY) runtime enumeration == the query lane's population (seat ×
   PLAYER_ZONES, the OMNISCIENT v1 reading — hidden-info gap documented in
   doc 2026-10-01/20), and the universal "any target" legality set
   includes the seats (CR 109.5);
7. query-lane pred parity: CMC_GE / ZONE_COUNT_GE /
   NAME_PARTITION_COUNT_GE answer through ONE evaluator on both lanes,
   and THAT_MANY_COUNT reads the 14e result register — an unset register
   stays a loud read.
"""

import unittest

from MTG_bot.core.ability_tree import (
    CardDrawnEvent,
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
    return Selector(count or QConst(1), SelectorMode.TARGET, UNIV, ANY_ZONE)


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
        # Vocab = exactly the Handle-sorted candidates (C15/C16, no prose)
        # and the answer is consumed as the designation (C2: the effect's
        # TARGET atom means THAT pick).
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
                        QConst(1), SelectorMode.TARGET, CREATURE_ONLY, BF_ANY
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
        # §1.4 auto-fill: one legal filler designates silently — asking a
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
                        BF_ANY,
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
        # CR 603.4: the ability that cannot designate RESOLVES DOING
        # NOTHING — not the 12c crash, not a guess. Artifact carrier, no
        # creature you control anywhere.
        amulet = self.carrier(self.p0, "Amulet", type_line="Artifact")
        self.attach(
            amulet,
            etb_trigger(
                atom(
                    Verb.PUT_COUNTER,
                    counter_kind=CounterKind.PLUS_1_PLUS_1,
                    count=QConst(1),
                    target=Selector(
                        QConst(1), SelectorMode.TARGET, CREATURE_ONLY, BF_YOU
                    ),
                )
            ),
            name="Amulet",
        )
        self.never_ask()
        self.enter(amulet)  # pre-18b this raised at the TARGET selector
        self.assertEqual(dict(self.world.cards[amulet].counters), {})

    def test_up_to_multi_pick_carries_the_none_token(self):
        # C17 contract (the pinned TARGET+QAtMost range 1..n): the FIRST
        # pick is mandatory, later picks offer the "NONE" stop token.
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
                        QAtMost(2), SelectorMode.TARGET, CREATURE_ONLY, BF_YOU
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
        self.assertNotIn("NONE", first_vocab)
        # pool minus the first pick, stop token appended; the acolyte
        # itself is a legal creature candidate all along.
        self.assertEqual(second_vocab, (str(acolyte), str(d1), "NONE"))


class TestTargetPlayerRouting(DesignationCase):
    def test_dies_binds_the_anaphoric_controller(self):
        # Massacre Wurm's twin: "whenever a creature an opponent controls
        # dies, that player loses 2 life" — TARGET_PLAYER is EVENT-bound
        # to the dead creature (16a's DAMAGE-dealer ruling mirrored): NO
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
                target=Selector(QConst(1), SelectorMode.TARGET, UNIV, BF_ANY),
            ),
            source=wurm,
            controller=self.p0,
            bindings={"target": prey},
        )
        self.assertEqual(self.world.zone_of(prey).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.players[self.p1].life, 18)

    def test_self_fire_designates_the_opponent_seat(self):
        # Tutelage's twin: "whenever YOU draw a card, target opponent mills
        # one" — a self-origin firing has no anaphoric antecedent, so the
        # opponent seat is designated (duel: one seat → auto-fill, no ask).
        dower = self.carrier(self.p0, "Tutelage Carrier")
        lib = self.world.add_card(card_id("Drawme"), self.p0, ZONE_LIBRARY)
        victim = self.world.add_card(card_id("Victim"), self.p1, ZONE_LIBRARY)
        self.attach(
            dower,
            TriggeredAbility(
                event=CardDrawnEvent(ControllerRef.YOU),
                condition=None,
                effect=atom(
                    Verb.MOVE_ZONE,
                    amount=QConst(1),
                    controller=ControllerRef.TARGET_PLAYER,
                    **{
                        "destination": Zone(
                            ZoneKind.GRAVEYARD, ControllerRef.TARGET_PLAYER
                        ),
                        "from": Zone(ZoneKind.LIBRARY, ControllerRef.TARGET_PLAYER),
                        "journal_kind": "MILL",
                        "pop_order": "TOP",
                    },
                ),
            ),
            name="Tutelage Carrier",
        )
        self.never_ask()
        self.enter(dower)  # arms the draw trigger
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=Selector(QConst(1), SelectorMode.CHOOSE, UNIV, LIB_YOU),
                destination=HAND_YOU,
            ),
            source=dower,
            controller=self.p0,
            bindings={"cards": lib},
        )
        self.assertEqual(self.world.zone_of(victim).kind, ZONE_GRAVEYARD)


class TestZoneAnyEnumeration(DesignationCase):
    def test_runtime_union_equals_query_lane(self):
        # §8.3 identity: selectors.enumerate_zone(ANY) IS legality
        # ._zone_handles(ANY) — seat × PLAYER_ZONES order, omniscient
        # (libraries and the opponent's hidden hand ride along: the v1
        # OMNISCIENT policy, model gap documented, never silently hidden).
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
            QConst(1), SelectorMode.TARGET, CREATURE_ONLY, ANY_ZONE
        )
        self.assertEqual(resolve_selector(creature_only, ctx), [])


class TestMultiSlotStaysLoud(DesignationCase):
    def test_two_distinct_targets_raise_never_guess_bind(self):
        # /06 arc 3, parity with the cast lane: one designation channel
        # cannot serve two DISTINCT TARGET slots — the raise stands.
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
                                BF_ANY,
                            ),
                        ),
                        atom(
                            Verb.TAP,
                            target=Selector(
                                QConst(1),
                                SelectorMode.TARGET,
                                FAtom(FAtomPred.TYPE_EQ, string_value="Land"),
                                BF_ANY,
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
    """14d's one-evaluator rule: query context and effect context answer
    the SAME for every pred round 18b wired."""

    def test_cmc_ge_one_evaluator_both_lanes(self):
        cheap = self.world.add_card(card_id("Cheap", "1", "1", cmc=5), self.p0)
        big = self.world.add_card(
            card_id("Big", "6", "6", cmc=6), self.p0, ZONE_LIBRARY
        )
        pred = FAtom(FAtomPred.CMC_GE, count=QConst(6))
        selector = Selector(QAtMost(5), SelectorMode.CHOOSE, FAnd((pred,)), LIB_YOU)
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
        # C26 (Chrome Replicator): EXACT-name partitions among the
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
        # Kinetic Augur's wiring: DISCARD writes the 14e producer register
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
                                QConst(2), SelectorMode.CHOOSE, UNIV, HAND_YOU
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
        # 16b made THIS_WAY's absence a benign 0 (a declined may legitimately
        # leaves it unwritten); THAT_MANY has NO zero-reading — the compiler
        # only places it in a mandatory continuation, so a missing
        # antecedent is a missing question: flag, never guess 0.
        anchor = self.world.add_card(
            card_id("Anchor", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        # The frozen grammar pins THAT_MANY to the 'event' referent, so the
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
