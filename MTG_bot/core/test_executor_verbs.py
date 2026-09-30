"""Tests for the round-12a state-visible executor (/06 §12a).

Pins the executor contract: every supported verb mutates the GameWorld
exactly as the rules say; every unsupported verb/effect/quantity/pred
RAISES (flag-don't-degrade); multi-object effects are Handle-sorted;
decisions are consumed strictly in order; the replay fingerprint is a
function of the atom sequence alone (P12).
"""

import itertools
import unittest

from MTG_bot.core.ability_tree import (
    QX,
    Atom,
    AtomArgs,
    Choose,
    Conditional,
    ControllerRef,
    CounterKind,
    EachPlayer,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    OptionalEffect,
    PtDelta,
    PtDirection,
    QAgg,
    QAtMost,
    QBin,
    QBinOp,
    QConst,
    QProp,
    QPropField,
    Repeat,
    Selector,
    SelectorMode,
    Seq,
    TokenSpec,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import SUPPORTED_VERBS_V1, Executor
from MTG_bot.core.executor.verbs import token_oracle_id
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)

_ORACLE_SEQ = itertools.count(1)


def reset_oracle_ids():
    """Restart the oracle-id sequence so two worlds built the same way get
    identical identities (required for replay-fingerprint comparisons)."""
    global _ORACLE_SEQ
    _ORACLE_SEQ = itertools.count(1)


def card_id(name, power=None, toughness=None, type_line="Creature", cmc=2):
    n = next(_ORACLE_SEQ)
    return CardIdentity(
        oracle_id=f"{n:08x}-1111-2222-3333-444444444444",
        name=name,
        type_line=type_line,
        power=power,
        toughness=toughness,
        cmc=cmc,
    )


def atom(verb, **roles):
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


BF_ANY = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)
LIB_YOU = Zone(ZoneKind.LIBRARY, ControllerRef.YOU)
HAND_YOU = Zone(ZoneKind.HAND, ControllerRef.YOU)
CREATURE = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")
UNIV = FAnd(())


def target_sel(filter_: Filter = CREATURE, zone: Zone = BF_ANY) -> Selector:
    return Selector(QConst(1), SelectorMode.TARGET, filter_, zone)


class ExecutorCase(unittest.TestCase):
    """Shared fixture: p0 controls Alpha (2/2) and Gamma (3/3) on the
    battlefield, p1 controls Beta (1/1); p0 has a 4-card library (L1..L4,
    L4 top) and H1 in hand; p1 has one library card."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=7)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.alpha = self.world.add_card(
            card_id("Alpha", "2", "2"), self.p0, ZONE_BATTLEFIELD
        )
        self.beta = self.world.add_card(
            card_id("Beta", "1", "1"), self.p1, ZONE_BATTLEFIELD
        )
        self.gamma = self.world.add_card(
            card_id("Gamma", "3", "3"), self.p0, ZONE_BATTLEFIELD
        )
        self.libs = [
            self.world.add_card(card_id(f"L{i}"), self.p0) for i in (1, 2, 3, 4)
        ]
        self.h1 = self.world.add_card(card_id("H1"), self.p0, ZONE_HAND)
        self.p1_lib = self.world.add_card(card_id("L9"), self.p1)
        self.ex = Executor(self.world)


class TestZoneVerbs(ExecutorCase):
    def test_destroy_and_sacrifice_go_to_graveyard(self):
        self.ex.execute(
            atom(Verb.DESTROY, target=target_sel()),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.ex.execute(
            atom(Verb.SACRIFICE, target=target_sel()),
            source=self.alpha,
            controller=self.p1,
            bindings={"target": self.beta},
        )
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(self.beta).kind, ZONE_GRAVEYARD)

    def test_exile(self):
        self.ex.execute(
            atom(Verb.EXILE, target=target_sel()),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.gamma},
        )
        self.assertEqual(self.world.zone_of(self.gamma).kind, ZONE_EXILE)

    def test_move_zone_hand_to_battlefield_tapped(self):
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=target_sel(UNIV, HAND_YOU),
                destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                tapped_on_enter=True,
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"cards": [self.h1]},
        )
        self.assertEqual(self.world.zone_of(self.h1).kind, ZONE_BATTLEFIELD)
        self.assertTrue(self.world.cards[self.h1].tapped)

    def test_draw_idiom_top_n_library_to_hand(self):
        fp_before = self.world.fingerprint()
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=Selector(QConst(2), SelectorMode.ALL, UNIV, LIB_YOU),
                destination=Zone(ZoneKind.HAND, ControllerRef.YOU),
            ),
            source=self.alpha,
            controller=self.p0,
        )
        lib = self.world.players[self.p0].zone(ZONE_LIBRARY).entries
        hand = self.world.players[self.p0].zone(ZONE_HAND).entries
        self.assertEqual(lib, self.libs[:2])  # L1, L2 remain
        self.assertEqual(hand, [self.h1, self.libs[3], self.libs[2]])  # top first
        self.assertNotEqual(self.world.fingerprint(), fp_before)


class TestLifeAndDamage(ExecutorCase):
    def test_gain_and_lose_life_with_clamp(self):
        self.ex.execute(
            atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(3)),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual(self.world.players[self.p0].life, 23)
        self.ex.execute(
            atom(Verb.LOSE_LIFE, controller=ControllerRef.YOU, amount=QConst(30)),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual(self.world.players[self.p0].life, 0)  # clamps at 0

    def test_deal_damage_to_player_clamps(self):
        self.ex.execute(
            atom(
                Verb.DEAL_DAMAGE,
                target=target_sel(UNIV, Zone(ZoneKind.PLAYER, ControllerRef.ANY)),
                amount=QConst(25),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.p1},
        )
        self.assertEqual(self.world.players[self.p1].life, 0)

    def test_lethal_damage_uses_ledger_pt(self):
        self.ex.execute(
            atom(
                Verb.MODIFY_PT,
                target=target_sel(),
                power=PtDelta(PtDirection.DECREASE, QConst(1)),
                toughness=PtDelta(PtDirection.DECREASE, QConst(1)),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )  # Alpha is now 1/1 in the ledger
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(), amount=QConst(1)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_GRAVEYARD)

    def test_nonlethal_damage_keeps_card(self):
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=target_sel(), amount=QConst(1)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_BATTLEFIELD)

    def test_dealer_role_raises(self):
        with self.assertRaises(NotImplementedError):
            self.ex.execute(
                atom(
                    Verb.DEAL_DAMAGE,
                    target=target_sel(),
                    amount=QConst(1),
                    dealer=ControllerRef.YOU,
                ),
                source=self.alpha,
                controller=self.p0,
                bindings={"target": self.beta},
            )


class TestTapsAndCounters(ExecutorCase):
    def test_tap_and_untap(self):
        self.ex.execute(
            atom(Verb.TAP, target=target_sel()),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.assertTrue(self.world.cards[self.alpha].tapped)
        self.ex.execute(
            atom(Verb.UNTAP, target=target_sel()),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.assertFalse(self.world.cards[self.alpha].tapped)

    def test_put_and_remove_counter_clamps(self):
        self.ex.execute(
            atom(
                Verb.PUT_COUNTER,
                target=target_sel(),
                counter_kind=CounterKind.PLUS_1_PLUS_1,
                count=QConst(2),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.assertEqual(self.world.cards[self.alpha].counters["PLUS_1_PLUS_1"], 2)
        self.ex.execute(
            atom(
                Verb.REMOVE_COUNTER,
                target=target_sel(),
                counter_kind=CounterKind.PLUS_1_PLUS_1,
                count=QConst(3),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )  # removal clamps at 0 and drops the key
        self.assertNotIn("PLUS_1_PLUS_1", self.world.cards[self.alpha].counters)

    def test_tap_with_duration_raises(self):
        from MTG_bot.core.ability_tree import DurationEot

        with self.assertRaises(NotImplementedError):
            self.ex.execute(
                atom(Verb.TAP, target=target_sel(), duration=DurationEot()),
                source=self.alpha,
                controller=self.p0,
                bindings={"target": self.alpha},
            )


class TestPtLedger(ExecutorCase):
    def test_modify_pt_delta_and_was_snapshot(self):
        events = self.ex.execute(
            atom(
                Verb.MODIFY_PT,
                target=target_sel(),
                power=PtDelta(PtDirection.INCREASE, QConst(2)),
                toughness=PtDelta(PtDirection.INCREASE, QConst(2)),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.assertEqual(
            self.ex.ledger.effective_pt(
                self.world.cards[self.alpha].identity, self.alpha
            ),
            (4, 4),
        )
        self.assertEqual(events[-1][4], 2)  # C18 was_power snapshot

    def test_set_pt_absolute(self):
        self.ex.execute(
            atom(Verb.SET_PT, target=target_sel(), power=QConst(5)),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.assertEqual(
            self.ex.ledger.effective_pt(
                self.world.cards[self.alpha].identity, self.alpha
            ),
            (5, 2),
        )

    def test_eot_sweep_reverts_eot_keeps_permanent(self):
        from MTG_bot.core.ability_tree import DurationEot

        self.ex.execute(
            atom(
                Verb.MODIFY_PT,
                target=target_sel(),
                power=PtDelta(PtDirection.INCREASE, QConst(1)),
                duration=DurationEot(),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.ex.execute(
            atom(
                Verb.MODIFY_PT,
                target=target_sel(),
                toughness=PtDelta(PtDirection.INCREASE, QConst(1)),
            ),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": self.alpha},
        )
        self.assertEqual(
            self.ex.ledger.effective_pt(
                self.world.cards[self.alpha].identity, self.alpha
            ),
            (3, 3),
        )
        expired = self.ex.ledger.sweep_at_eot()
        self.assertEqual(expired, 1)
        self.assertEqual(
            self.ex.ledger.effective_pt(
                self.world.cards[self.alpha].identity, self.alpha
            ),
            (2, 3),
        )

    def test_set_pt_with_ptdelta_raises(self):
        with self.assertRaises(NotImplementedError):
            self.ex.execute(
                atom(
                    Verb.SET_PT,
                    target=target_sel(),
                    power=PtDelta(PtDirection.INCREASE, QConst(1)),
                ),
                source=self.alpha,
                controller=self.p0,
                bindings={"target": self.alpha},
            )


class TestTokens(ExecutorCase):
    TREASURE = TokenSpec(
        name="Treasure",
        type_line="Token — Treasure",
        types=("Artifact",),
        subtypes=("Treasure",),
        power=None,
        toughness=None,
        keywords=(),
        abilities=(),
    )

    def test_create_token_landson_battlefield_flagged(self):
        events = self.ex.execute(
            atom(Verb.CREATE_TOKEN, tokens=self.TREASURE, count=QConst(2)),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual(len(events), 2)
        tokens = [
            h
            for h in self.world.players[self.p0].zone(ZONE_BATTLEFIELD).entries
            if self.world.cards[h].identity.is_token
        ]
        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0], self.world.cards[tokens[0]].handle)
        self.assertTrue(str(events[0][3]).endswith(":0"))
        self.assertTrue(str(events[1][3]).endswith(":1"))

    def test_create_tapped_creature_token(self):
        soldier = TokenSpec(
            name="Soldier",
            type_line="Token — Creature — Soldier",
            types=("Creature",),
            subtypes=("Soldier",),
            power=QConst(1),
            toughness=QConst(1),
            keywords=(),
            abilities=(),
            color="W",
            enters_tapped=True,
        )
        self.ex.execute(
            atom(Verb.CREATE_TOKEN, tokens=soldier, count=QConst(1)),
            source=self.alpha,
            controller=self.p0,
        )
        tokens = [
            h
            for h in self.world.players[self.p0].zone(ZONE_BATTLEFIELD).entries
            if self.world.cards[h].identity.is_token
        ]
        self.assertEqual(len(tokens), 1)
        self.assertTrue(self.world.cards[tokens[0]].tapped)
        self.assertEqual(
            self.ex.ledger.effective_pt(
                self.world.cards[tokens[0]].identity, tokens[0]
            ),
            (1, 1),
        )

    def test_token_oracle_id_shape_and_distinct(self):
        a, b = token_oracle_id("Treasure"), token_oracle_id("Goblin")
        self.assertRegex(a, r"^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$")
        self.assertNotEqual(a, b)
        self.assertEqual(a, token_oracle_id("Treasure"))  # stable across calls


class TestManaScryShuffleLook(ExecutorCase):
    def test_add_mana_colored(self):
        self.ex.execute(
            atom(
                Verb.ADD_MANA,
                controller=ControllerRef.YOU,
                amount=QConst(2),
                color="R",
            ),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual(self.world.players[self.p0].mana_pool.get("R"), 2)

    def test_add_mana_any_uses_decision(self):
        with self.assertRaises(ValueError):  # decision missing -> RAISE
            self.ex.execute(
                atom(Verb.ADD_MANA, controller=ControllerRef.YOU, amount=QConst(1)),
                source=self.alpha,
                controller=self.p0,
            )
        self.ex.execute(
            atom(Verb.ADD_MANA, controller=ControllerRef.YOU, amount=QConst(1)),
            source=self.alpha,
            controller=self.p0,
            decisions=("U",),
        )
        self.assertEqual(self.world.players[self.p0].mana_pool.get("U"), 1)

    def test_scry_consumes_decisions_top_first(self):
        # Library L1..L4 (L4 top). scry 2, decisions: top card to bottom,
        # second card stays on top.
        self.ex.execute(
            atom(Verb.SCRY, controller=ControllerRef.YOU, count=QConst(2)),
            source=self.alpha,
            controller=self.p0,
            decisions=("bottom", "top"),
        )
        lib = self.world.players[self.p0].zone(ZONE_LIBRARY).entries
        self.assertEqual(lib, self.libs[:2] + [self.libs[3], self.libs[2]])

    def test_scry_clamps_and_requires_decisions(self):
        with self.assertRaises(ValueError):
            self.ex.execute(
                atom(Verb.SCRY, controller=ControllerRef.YOU, count=QConst(2)),
                source=self.alpha,
                controller=self.p0,
            )
        self.ex.execute(  # scry 9 on a 4-card library clamps to 4
            atom(Verb.SCRY, controller=ControllerRef.YOU, count=QConst(9)),
            source=self.alpha,
            controller=self.p0,
            decisions=("top", "top", "top", "top"),
        )
        self.assertEqual(
            self.world.players[self.p0].zone(ZONE_LIBRARY).entries, self.libs
        )

    def test_shuffle_replay_identical_same_seed(self):
        def run(seed):
            w = GameWorld(num_players=2, start_life=20, master_seed=seed)
            p0 = w.player_order[0]
            for i in range(8):
                w.add_card(card_id(f"S{i}"), p0)
            ex = Executor(w)
            ex.execute(
                atom(
                    Verb.SHUFFLE,
                    zone=Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
                ),
                source=p0,
                controller=p0,
            )
            return tuple(w.players[p0].zone(ZONE_LIBRARY).entries)

        self.assertEqual(run(11), run(11))
        self.assertEqual(set(run(11)), set(run(99)))  # a permutation, always
        self.assertNotEqual(run(11), run(99))  # seeds diverge (deterministic)

    def test_look_at_and_reveal_record_without_touching_state(self):
        fp = self.world.fingerprint()
        ev1 = self.ex.execute(
            atom(Verb.LOOK_AT, controller=ControllerRef.YOU, count=QConst(2)),
            source=self.alpha,
            controller=self.p0,
        )
        ev2 = self.ex.execute(
            atom(Verb.REVEAL, controller=ControllerRef.YOU, count=QConst(1)),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual(ev1[0][1], "LOOK_AT")
        self.assertEqual(ev2[0][1], "REVEAL")
        self.assertEqual(ev1[0][3], (str(self.libs[3]), str(self.libs[2])))
        self.assertEqual(self.world.fingerprint(), fp)  # no state touched


class TestSelectors(ExecutorCase):
    def test_handle_sorting_is_canonical(self):
        events = self.ex.execute(
            atom(Verb.DESTROY, target=target_sel()),
            source=self.alpha,
            controller=self.p0,
            bindings={"target": [self.gamma, self.alpha, self.beta]},
        )
        moved = [str(e[2]) for e in events]
        self.assertEqual(moved, sorted(moved))

    def test_all_mode_destroy_without_binding(self):
        self.ex.execute(
            atom(
                Verb.DESTROY,
                target=Selector(QConst(1), SelectorMode.ALL, CREATURE, BF_ANY),
            ),
            source=self.alpha,
            controller=self.p0,
        )
        for c in (self.alpha, self.beta, self.gamma):
            self.assertEqual(self.world.zone_of(c).kind, ZONE_GRAVEYARD)

    def test_choose_mode_c17_clamp(self):
        # "discard up to two" with one card in hand: legal designation
        # 1..2, executor clamps to the 1 handle actually available.
        self.ex.execute(
            atom(
                Verb.DISCARD,
                controller=ControllerRef.YOU,
                cards=Selector(QAtMost(2), SelectorMode.CHOOSE, UNIV, HAND_YOU),
            ),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual(self.world.zone_of(self.h1).kind, ZONE_GRAVEYARD)

    def test_target_mode_without_binding_raises(self):
        with self.assertRaises(ValueError):
            self.ex.execute(
                atom(Verb.DESTROY, target=target_sel()),
                source=self.alpha,
                controller=self.p0,
            )

    def test_unsupported_modes_and_referents_raise(self):
        # AMENDED 14c (B-13): ONE_OF is no longer "unsupported" — it asks
        # the vocabulary-addressed channel, and an ask NO lane can answer
        # raises ValueError (never a default). The closed referents
        # outside a firing stay NotImplementedError.
        one_of = atom(
            Verb.DESTROY,
            target=Selector(QConst(1), SelectorMode.ONE_OF, CREATURE, BF_ANY),
        )
        with self.assertRaises(ValueError):
            self.ex.execute(one_of, source=self.alpha, controller=self.p0)
        result_ref = atom(
            Verb.DESTROY,
            target=Selector(
                QConst(1),
                SelectorMode.CHOOSE,
                UNIV,
                Zone(ZoneKind.ANY, ControllerRef.ANY),
                referent="result",
            ),
        )
        with self.assertRaises(NotImplementedError):
            self.ex.execute(result_ref, source=self.alpha, controller=self.p0)

    def test_random_mode_seeded_replay(self):
        def run(seed):
            w = GameWorld(num_players=2, start_life=20, master_seed=seed)
            p0, _p1 = w.player_order[0], w.player_order[1]
            cards = [
                w.add_card(card_id(f"R{i}", "1", "1"), p0, ZONE_BATTLEFIELD)
                for i in range(4)
            ]
            ex = Executor(w)
            ex.execute(
                atom(
                    Verb.DESTROY,
                    target=Selector(QConst(1), SelectorMode.RANDOM, CREATURE, BF_ANY),
                ),
                source=p0,
                controller=p0,
            )
            gy = w.players[p0].zone(ZONE_GRAVEYARD).entries
            return cards, tuple(gy)

        cards_a, gy_a = run(5)
        _cards_b, gy_b = run(5)
        self.assertEqual(gy_a, gy_b)
        self.assertEqual(len(gy_a), 1)
        self.assertTrue(set(gy_a) <= set(cards_a))


class TestQuantityAndFilters(ExecutorCase):
    def test_qbin_arithmetic_mills(self):
        self.ex.execute(
            atom(
                Verb.MILL,
                controller=ControllerRef.YOU,
                amount=QBin(QBinOp.ADD, QConst(2), QConst(1)),
            ),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual(
            self.world.players[self.p0].zone(ZONE_GRAVEYARD).entries,
            [self.libs[3], self.libs[2], self.libs[1]],
        )

    def test_qprop_power_sum_flows_into_mill(self):
        # p0 controls Alpha (2) and Gamma (3): "mill damage equal to total
        # power of creatures you control" shape -> mill 5 (clamps to 4).
        power_sum = QProp(
            referent=Selector(
                QConst(1),
                SelectorMode.ALL,
                CREATURE,
                Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            ),
            field=QPropField.POWER,
            agg=QAgg.SUM,
        )
        self.ex.execute(
            atom(Verb.MILL, controller=ControllerRef.YOU, amount=power_sum),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual(
            self.world.players[self.p0].zone(ZONE_GRAVEYARD).entries,
            list(reversed(self.libs)),
        )

    def test_filter_or_and_not(self):
        self.ex.execute(
            atom(
                Verb.EXILE,
                target=Selector(
                    QConst(2),
                    SelectorMode.CHOOSE,
                    FOr(
                        (
                            FAtom(FAtomPred.NAME_EQ, string_value="Alpha"),
                            FAtom(FAtomPred.NAME_EQ, string_value="Beta"),
                        )
                    ),
                    BF_ANY,
                ),
            ),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_EXILE)
        self.assertEqual(self.world.zone_of(self.beta).kind, ZONE_EXILE)
        self.assertEqual(self.world.zone_of(self.gamma).kind, ZONE_BATTLEFIELD)

    def test_filter_not_complements(self):
        self.ex.execute(
            atom(
                Verb.EXILE,
                target=Selector(
                    QConst(2),
                    SelectorMode.CHOOSE,
                    FNot(FAtom(FAtomPred.NAME_EQ, string_value="Alpha")),
                    BF_ANY,
                ),
            ),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.world.zone_of(self.beta).kind, ZONE_EXILE)
        self.assertEqual(self.world.zone_of(self.gamma).kind, ZONE_EXILE)

    def test_color_preds_evaluate_now(self):
        # AMENDED (round 13b): COLOR_HAS/COLOR_IN left the unsupported-pred
        # list — the cast-trigger feed (Quirion Dryad's compiled "coloured
        # spell" filter) needs them, and they are plain identity reads.
        # COLOR_HAS = membership; COLOR_IN = NON-EMPTY SUBSET (grammar
        # reading). NAME_CHOSEN is also live (executor_stack suite), and
        # genuinely unsupported preds still raise (test below stays).
        white = self.world.add_card(
            CardIdentity(
                oracle_id="0f000001-1111-2222-3333-444444444444",
                name="White",
                type_line="Creature",
                power="1",
                toughness="1",
                cmc=1,
                colors=("W",),
            ),
            self.p0,
            ZONE_BATTLEFIELD,
        )
        red = self.world.add_card(
            CardIdentity(
                oracle_id="0f000002-1111-2222-3333-444444444444",
                name="Red",
                type_line="Creature",
                power="1",
                toughness="1",
                cmc=1,
                colors=("R",),
            ),
            self.p0,
            ZONE_BATTLEFIELD,
        )
        color_has = atom(
            Verb.DESTROY,
            target=Selector(
                QConst(1),
                SelectorMode.ALL,
                FAtom(FAtomPred.COLOR_HAS, color="W"),
                BF_ANY,
            ),
        )
        self.ex.execute(color_has, source=self.alpha, controller=self.p0)
        self.assertEqual(self.world.zone_of(white).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(red).kind, ZONE_BATTLEFIELD)
        # COLOR_IN: subset reading — {"R"} is inside (R, G), white is not.
        color_in = atom(
            Verb.DESTROY,
            target=Selector(
                QConst(1),
                SelectorMode.ALL,
                FAtom(FAtomPred.COLOR_IN, colors=("R", "G")),
                BF_ANY,
            ),
        )
        self.ex.execute(color_in, source=self.alpha, controller=self.p0)
        self.assertEqual(self.world.zone_of(red).kind, ZONE_GRAVEYARD)

    def test_unsupported_pred_still_raises(self):
        # the flag side stays: a pred the executor truly cannot read still
        # raises at dispatch (NAME_CHOSEN without a CHOOSE_NAME record is
        # the same convention, pinned in test_executor_stack.py).
        # AMENDED (round 16b): IS_ATTACKING is NO LONGER in this class —
        # the COMBAT skeleton answers it from the attack record (pinned
        # below and in test_executor_combat.py).
        # AMENDED 2026-10-02 (round 16c): IS_BLOCKING LEFT this class too —
        # the block record is live and the pred answers False outside
        # combat (the attack sibling's pattern); PT_GE takes the flag
        # torch as a remaining unreadable pred (arity-legal bare FAtom).
        answers_attacking = atom(
            Verb.DESTROY,
            target=Selector(
                QConst(1),
                SelectorMode.ALL,
                FAtom(FAtomPred.IS_ATTACKING),
                BF_ANY,
            ),
        )
        # outside combat nothing is attacking: the pred READS False, the
        # ALL-selector resolves empty, DESTROY finds no target (empty
        # target sets are a legal no-op row — no raise anywhere).
        self.ex.execute(answers_attacking, source=self.alpha, controller=self.p0)
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_BATTLEFIELD)
        answers_blocking = atom(
            Verb.DESTROY,
            target=Selector(
                QConst(1),
                SelectorMode.ALL,
                FAtom(FAtomPred.IS_BLOCKING),
                BF_ANY,
            ),
        )
        # outside combat nothing is blocking: the pred READS False, the
        # ALL-selector resolves empty, DESTROY no-ops (same as above).
        self.ex.execute(answers_blocking, source=self.alpha, controller=self.p0)
        self.assertEqual(self.world.zone_of(self.alpha).kind, ZONE_BATTLEFIELD)
        unreachable = atom(
            Verb.DESTROY,
            target=Selector(
                QConst(1),
                SelectorMode.ALL,
                FAtom(FAtomPred.PT_GE),
                BF_ANY,
            ),
        )
        with self.assertRaises(NotImplementedError):
            self.ex.execute(unreachable, source=self.alpha, controller=self.p0)

    def test_qx_raises(self):
        with self.assertRaises(NotImplementedError):
            self.ex.execute(
                atom(Verb.MILL, controller=ControllerRef.YOU, amount=QX()),
                source=self.alpha,
                controller=self.p0,
            )


class TestDispatchRaises(ExecutorCase):
    def test_unsupported_verbs_raise_at_dispatch(self):
        # Atom.__post_init__ validates role presence, so each probe carries
        # its verb's required roles — only then does the dispatcher's
        # "not implemented" raise become observable.
        # AMENDED 2026-09-29 (round 12d): GRANT_ABILITY left the raise list
        # — it (with LOSE_ABILITY/PREVENT_EFFECT) is a live layer verb now
        # (test_executor_layers.py covers the behaviour).
        # AMENDED 2026-09-29 (round 13a): DRAW and SEARCH left the raise
        # list too — they gained real handlers, so probing them for a
        # dispatch raise is no longer meaningful (their card-level
        # behaviour is the 13b golden work). SUPPORTED_VERBS_V1 still
        # pins them OUT: V1 is the frozen round-12 contract, V2 the live
        # derived set.
        # AMENDED (round 13b): CAST left the raise list — it is the spell
        # stack's effect-side handler (_v_cast -> stack.cast_card, covered
        # in test_executor_stack.py); PAY/CHOOSE/CHOOSE_NAME/MANA_POLICY
        # joined the same round. COUNTER_SPELL STAYS: v1 has no
        # interaction window — a counter-spell can never legally resolve
        # (the four corpus cards keep their loud dispatch raise, pinned
        # by test_counter_spell_still_raises in test_executor_stack.py).
        # AMENDED 2026-09-30 (round 13c): GET_EMBLEM left the raise list —
        # it is the emblems round's live handler (executor.get_emblem,
        # covered in test_executor_permissions.py); GRANT_TYPE,
        # GRANT_ACTIVATION and ADD_LAND_PLAY join GRANT_ABILITY's 12d
        # precedent as layer verbs that were never probed here.
        # AMENDED 2026-09-30 (round 16a): FIGHT left the raise list — it is
        # the damage-exchange round's live handler (HANDLERS[Verb.FIGHT],
        # covered by the 16a marked-damage/fight tests).
        probes = {
            Verb.PHASE_OUT: {"target": target_sel()},
            Verb.COUNTER_SPELL: {"target": target_sel()},
        }
        for verb, roles in probes.items():  # DRAW deliberately outside v1
            with self.subTest(verb=verb.name):
                with self.assertRaises(NotImplementedError) as cm:
                    self.ex.execute(
                        atom(verb, **roles), source=self.alpha, controller=self.p0
                    )
                self.assertIn(verb.name, str(cm.exception))

    def test_supported_set_is_exactly_the_table(self):
        # AMENDED 2026-09-29 (round 12d): 21 -> 24 — GRANT_ABILITY,
        # LOSE_ABILITY and PREVENT_EFFECT joined the honest capability set
        # with the continuous-layers round.
        self.assertEqual(len(SUPPORTED_VERBS_V1), 24)
        self.assertNotIn(Verb.DRAW, SUPPORTED_VERBS_V1)

    def test_execute_and_world_type_guards(self):
        with self.assertRaises(ValueError):
            self.ex.execute("not an atom", source=self.alpha, controller=self.p0)  # pyright: ignore[reportArgumentType]
        with self.assertRaises(ValueError):
            Executor("not a world")  # pyright: ignore[reportArgumentType]


class TestApplyEffect(ExecutorCase):
    def gain(self, n):
        return atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(n))

    def test_seq_runs_steps_in_order(self):
        events = self.ex.apply_effect(
            Seq((self.gain(1), self.gain(2))),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual([e[1] for e in events], ["GAIN_LIFE", "GAIN_LIFE"])
        self.assertEqual(self.world.players[self.p0].life, 23)

    def test_optional_fire_and_skip(self):
        opt = OptionalEffect(self.gain(5))
        self.ex.apply_effect(
            opt, source=self.alpha, controller=self.p0, decisions=("fire",)
        )
        self.assertEqual(self.world.players[self.p0].life, 25)
        events = self.ex.apply_effect(
            opt, source=self.alpha, controller=self.p0, decisions=("skip",)
        )
        self.assertEqual(events, ())
        self.assertEqual(self.world.players[self.p0].life, 25)

    def test_optional_missing_decision_raises(self):
        with self.assertRaises(ValueError):
            self.ex.apply_effect(
                OptionalEffect(self.gain(1)),
                source=self.alpha,
                controller=self.p0,
            )

    def test_conditional_then_and_else(self):
        then_atom = self.gain(1)
        else_atom = self.gain(10)
        # pred over the source: Alpha IS named "Alpha" -> THEN branch
        cond_true = Conditional(
            FAtom(FAtomPred.NAME_EQ, string_value="Alpha"), then_atom, else_atom
        )
        self.ex.apply_effect(cond_true, source=self.alpha, controller=self.p0)
        self.assertEqual(self.world.players[self.p0].life, 21)
        cond_false = Conditional(
            FAtom(FAtomPred.NAME_EQ, string_value="Nope"), then_atom, else_atom
        )
        self.ex.apply_effect(cond_false, source=self.alpha, controller=self.p0)
        self.assertEqual(self.world.players[self.p0].life, 31)

    def test_nested_decisions_consume_in_tree_order(self):
        mana = atom(
            Verb.ADD_MANA,
            controller=ControllerRef.YOU,
            amount=QConst(1),
            color="W",
        )
        self.ex.apply_effect(
            Seq((OptionalEffect(mana), OptionalEffect(mana))),
            source=self.alpha,
            controller=self.p0,
            decisions=("fire", "skip"),
        )
        self.assertEqual(self.world.players[self.p0].mana_pool, {"W": 1})

    def test_unsupported_effect_nodes_raise(self):
        # AMENDED 2026-09-30 (round 14f): EachPlayer is WIRED — one
        # sub-execution per denoted player with the CONTROLLER rotated
        # (the templates compile the inner effect YOU-relative, so the
        # rotation IS the rebinding; the Goremand/Keral/Whale/Thieves'
        # Guild corpus faces run in Round14fSurfaceTest). Repeat stays
        # unimplemented and loud. (Earlier amendment, 12d: Choose became
        # runtime-consumed — pinned separately below.)
        with self.assertRaises(NotImplementedError):
            self.ex.apply_effect(
                Repeat(QConst(2), self.gain(1)),
                source=self.alpha,
                controller=self.p0,
            )
        self.ex.apply_effect(
            EachPlayer(ControllerRef.ALL_OPPONENTS, self.gain(1)),
            source=self.alpha,
            controller=self.p0,
        )
        self.assertEqual(self.world.players[self.p1].life, 21)  # YOU rotated
        self.assertEqual(self.world.players[self.p0].life, 20)  # never fired

    def test_choose_runtime_consumes_a_decision_12d(self):
        # 12d pin: Choose(QConst(1), (A, B)) consumes str(index) and runs
        # that option subtree — the query.choose_options ORDER contract
        # (size-ascending, index-lex; the full multi-option enumeration is
        # pinned in test_executor_layers.py).
        self.ex.apply_effect(
            Choose(QConst(1), (self.gain(1), self.gain(2))),
            source=self.alpha,
            controller=self.p0,
            decisions=("1",),
        )
        self.assertEqual(self.world.players[self.p0].life, 22)
        with self.assertRaises(ValueError):  # missing decision, C15
            self.ex.apply_effect(
                Choose(QConst(1), (self.gain(1), self.gain(2))),
                source=self.alpha,
                controller=self.p0,
            )


def scripted_run(seed):
    """One fixed 11-op sequence against a freshly built world — the replay
    determinism probe: identical fingerprints iff identical transitions."""
    reset_oracle_ids()
    world = GameWorld(num_players=2, start_life=20, master_seed=seed)
    p0, p1 = world.player_order[0], world.player_order[1]
    alpha = world.add_card(card_id("Alpha", "2", "2"), p0, ZONE_BATTLEFIELD)
    beta = world.add_card(card_id("Beta", "1", "1"), p1, ZONE_BATTLEFIELD)
    for i in range(4):
        world.add_card(card_id(f"L{i}"), p0)
    world.add_card(card_id("L9"), p1)
    ex = Executor(world)
    src = alpha
    ex.execute(
        atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(2)),
        source=src,
        controller=p0,
    )
    ex.execute(
        atom(Verb.TAP, target=target_sel()),
        source=src,
        controller=p0,
        bindings={"target": alpha},
    )
    ex.execute(
        atom(
            Verb.PUT_COUNTER,
            target=target_sel(),
            counter_kind=CounterKind.PLUS_1_PLUS_1,
            count=QConst(1),
        ),
        source=src,
        controller=p0,
        bindings={"target": alpha},
    )
    ex.execute(
        atom(
            Verb.MODIFY_PT,
            target=target_sel(),
            power=PtDelta(PtDirection.INCREASE, QConst(1)),
        ),
        source=src,
        controller=p0,
        bindings={"target": alpha},
    )
    ex.execute(
        atom(Verb.DEAL_DAMAGE, target=target_sel(), amount=QConst(1)),
        source=src,
        controller=p0,
        bindings={"target": beta},
    )
    ex.execute(
        atom(Verb.MILL, controller=ControllerRef.OPPONENT, amount=QConst(1)),
        source=src,
        controller=p0,
    )
    ex.execute(
        atom(Verb.SCRY, controller=ControllerRef.YOU, count=QConst(2)),
        source=src,
        controller=p0,
        decisions=("bottom", "top"),
    )
    ex.execute(
        atom(Verb.SHUFFLE, zone=Zone(ZoneKind.LIBRARY, ControllerRef.YOU)),
        source=src,
        controller=p0,
    )
    ex.execute(
        atom(Verb.CREATE_TOKEN, tokens=TestTokens.TREASURE, count=QConst(1)),
        source=src,
        controller=p0,
    )
    ex.execute(
        atom(Verb.ADD_MANA, controller=ControllerRef.YOU, amount=QConst(1), color="G"),
        source=src,
        controller=p0,
    )
    ex.execute(
        atom(Verb.LOSE_LIFE, controller=ControllerRef.OPPONENT, amount=QConst(3)),
        source=src,
        controller=p0,
    )
    return ex


class TestReplayDeterminism(unittest.TestCase):
    def test_scripted_replay_fingerprints_match(self):
        a, b = scripted_run(7), scripted_run(7)
        self.assertEqual(a.world.fingerprint(), b.world.fingerprint())
        self.assertEqual(a.ledger.dump(), b.ledger.dump())
        self.assertEqual(a.state_fingerprint(), b.state_fingerprint())

    def test_ledger_sweep_changes_fingerprint(self):
        from MTG_bot.core.ability_tree import DurationEot

        ex = scripted_run(7)
        before = ex.state_fingerprint()
        p0 = ex.world.player_order[0]
        alpha = ex.world.players[p0].zone(ZONE_BATTLEFIELD).entries[0]
        ex.execute(
            atom(
                Verb.MODIFY_PT,
                target=target_sel(),
                power=PtDelta(PtDirection.INCREASE, QConst(1)),
                duration=DurationEot(),
            ),
            source=alpha,
            controller=p0,
            bindings={"target": alpha},
        )
        mid = ex.state_fingerprint()
        ex.ledger.sweep_at_eot()
        after = ex.state_fingerprint()
        self.assertNotEqual(before, mid)
        self.assertNotEqual(mid, after)  # the ledger IS replayed state


if __name__ == "__main__":
    unittest.main()
