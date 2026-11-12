"""The random-policy full-M21 game harness, and engine behaviour that dealt games exercise.

1. The harness must be trustworthy before any number written from it means
   anything: one seed replays to the SAME world fingerprint, the deck builder
   obeys its own documented composition rules, and the policy answers the
   engine's asks, whose vocabulary is the query surface's own enumeration —
   testable by making the query surface NARROW and checking the policy follows
   (:class:`DecisionSurfaceTest`).

2. The engine shapes real games reach, each pinned on the real compiled card
   or a minimal world: stack-zone targets, a land's own ETB ask mid-op,
   synthesized player slots, the ``result``/``event`` referents, kicker and
   X-kicker casts, the journal-backed history predicates, control and Aura
   lifecycles, the stall rule, the act windows of both main phases, and dealt
   cards binding their records.
"""

from __future__ import annotations

import unittest
from collections import Counter

from MTG_bot.core.ability_tree import (
    QX,
    ActivatedAbility,
    Atom,
    AtomArgs,
    CardRecord,
    Choose,
    Conditional,
    ControllerRef,
    Cost,
    CostManaGeneric,
    DurationEot,
    EachPlayer,
    FAnd,
    FAtom,
    FAtomPred,
    Keyword,
    KeywordAbility,
    KickerAbility,
    OptionalEffect,
    QConst,
    QUnbounded,
    Repeat,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    SpellKind,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    ZonePosition,
    walk,
)
from MTG_bot.core.compiler.compiler import CompileResult, PoolCompile
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.events import KIND_STALL_BREAK
from MTG_bot.core.executor.games import (
    DECK_SIZE,
    MAX_COPIES,
    MIN_MANA_SOURCES,
    REPEAT_ROUNDS,
    TURN_CAP,
    CardMeta,
    Game,
    RandomPolicy,
    Supply,
    _play,
    _setup_game,
    _stall_fingerprint,
    build_deck,
    deal_decks,
    get_supply,
    identity_of,
    play_game,
    run_games,
)
from MTG_bot.core.executor.legality import activate, ctx_for, spell_castable
from MTG_bot.core.executor.menu import menu, sorcery_timing
from MTG_bot.core.executor.quantity import ExecCtx, eval_filter
from MTG_bot.core.executor.query import (
    activation_target_slots,
    is_aura_spell,
    legal_casts,
    legal_targets,
    optional_offer,
    spell_target_slots,
)
from MTG_bot.core.executor.selectors import resolve_selector
from MTG_bot.core.executor.stack import cast, park, play_land
from MTG_bot.core.identity import CardIdentity, Handle, LegalityFlags
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import card_id, reset_oracle_ids
from MTG_bot.core.test_executor_verbs import stock_libraries

UNIV = FAnd(())
SMOKE_DECK_PAIRS = 1409  # the CLI default: the tests run the shipped recipe


def _atom(verb: Verb, **roles: object) -> Atom:
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


def _target_sel() -> Selector:
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=UNIV,
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )


def _record_named(supply: Supply, name: str) -> CardRecord:
    for oid, meta in supply.metas.items():
        if meta.name == name:
            return supply.pool.results[oid].card
    raise AssertionError(f"{name!r} is not in the compiled pool")


class DeckSupplyTest(unittest.TestCase):
    """The deck builder obeys the composition rules the report cites."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.supply = get_supply("castable")

    def test_deck_is_60_deterministic_and_mana_floored(self) -> None:
        deck = build_deck(11, self.supply)
        self.assertEqual(len(deck), DECK_SIZE)
        self.assertGreaterEqual(
            sum(1 for oid in deck if self.supply.metas[oid].mana_capable),
            MIN_MANA_SOURCES,
            "a deck without a mana base measures the shuffle, not the engine",
        )
        self.assertLessEqual(max(Counter(deck).values()), MAX_COPIES)
        self.assertEqual(build_deck(11, self.supply), deck)
        self.assertNotEqual(build_deck(12, self.supply), deck)

    def test_deck_pairs_derive_from_the_game_seed(self) -> None:
        self.assertEqual(
            deal_decks(9, SMOKE_DECK_PAIRS, self.supply),
            deal_decks(9, SMOKE_DECK_PAIRS, self.supply),
        )

    def test_castable_pool_only_deals_playable_engine_cards(self) -> None:
        for oid in self.supply.deckable:
            meta = self.supply.metas[oid]
            self.assertTrue(meta.engine_supported and meta.playable, meta.name)

    def test_engine_count_is_the_gated_293(self) -> None:
        # The SUPPORTED_VERBS_V2-gated count: an ungated compile stamps every
        # card supported, so a harness that skipped the second pass would
        # report 305. Re-pin it only after diffing the gated compile with and
        # without the change: a change must move exactly the cards it affects.
        self.assertEqual(len(self.supply.engine_ids), 300)


class ShapeGapSupplyExclusionTest(unittest.TestCase):
    """The ZNR supply EXCLUDES the one printed shape the compiler refuses —
    Nighthawk Scavenger, P/T "1+*", whose '*' is "the number of card types
    among cards in your opponents' graveyards" (a derived count the Quantity
    grammar cannot express) — and registers it as a ShapeGap row: loud
    (stderr line + ledger), never silent."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.supply = get_supply("engine", "ZNR")

    def test_znr_engine_supply_builds(self) -> None:
        self.assertTrue(self.supply.deckable)

    def test_nighthawk_excluded_and_registered_not_silent(self) -> None:
        names = {meta.name for meta in self.supply.metas.values()}
        self.assertNotIn("Nighthawk Scavenger", names)
        gap_names = {gap.name for gap in self.supply.shape_gaps}
        self.assertEqual(gap_names, {"Nighthawk Scavenger"})
        [gap] = self.supply.shape_gaps
        self.assertIn("parse_pt", gap.error)
        self.assertIn("1+*", gap.error)

    def test_exclusion_is_the_only_one(self) -> None:
        # Nighthawk is the ONLY non-digit P/T in ZNR; a second
        # gap row means a new shape crash got swallowed — that is a finding.
        self.assertEqual(len(self.supply.shape_gaps), 1)

    def test_m21_supply_untouched_by_the_lane(self) -> None:
        m21 = get_supply("engine")
        self.assertEqual(m21.shape_gaps, ())
        self.assertEqual(len(m21.deckable), 280)


class KickerLaneTest(unittest.TestCase):
    """A KickerAbility is a cast OPTION, not a second spell. The legality
    fold charges printed + kicker cost when ``kicked=True``, rejects the
    flag on non-kickers, and the compiler gives a kicker-only noncreature
    head a SpellAbility carrier (Roost of Drakes has no effect sentence, yet
    it is a spell). X-valued kickers: XKickerLaneTest below."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.supply = get_supply("engine", "ZNR")

    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=3)
        self.executor = Executor(self.world)
        self.executor.attach_pool(self.supply.pool)
        self.p0, _p1 = self.world.player_order
        self.world.active_player = self.p0
        self.executor.turn_open = True
        self.executor.phase = "FIRST_MAIN"

    def _castable(self, name: str, *, kicked: bool, mana: int):
        record = _record_named(self.supply, name)
        handle = self.world.add_card(identity_of(record), self.p0, ZONE_HAND)
        self.world.players[self.p0].mana_pool.clear()
        self.world.players[self.p0].mana_pool["U"] = mana
        return spell_castable(self.executor, self.p0, handle, kicked=kicked)

    def test_kicker_head_gets_a_spell_carrier(self) -> None:
        record = _record_named(self.supply, "Roost of Drakes")
        spell = next(a for a in record.abilities if isinstance(a, SpellAbility))
        self.assertIsNone(spell.effect, "carrier only — no effect sentence")
        self.assertEqual(spell.kind, SpellKind.ENCHANTMENT)
        self.assertTrue(
            any(isinstance(a, KickerAbility) for a in record.abilities),
            "the carrier joins, it does not replace the kicker",
        )

    def test_kicked_cast_folds_the_kicker_cost(self) -> None:
        # printed {U}; kicker {2}{U} -> kicked fold needs 4U, plain 1U
        reason, node, _record, plan = self._castable(
            "Roost of Drakes", kicked=True, mana=4
        )
        self.assertIsNone(reason, str(reason))
        self.assertIsNotNone(node)
        self.assertIsNotNone(plan)
        short = self._castable("Roost of Drakes", kicked=True, mana=3)
        assert short[0] is not None
        self.assertIn("cost:mana", short[0])
        plain = self._castable("Roost of Drakes", kicked=False, mana=1)
        self.assertIsNone(plain[0], str(plain[0]))

    def test_kick_flag_on_a_non_kicker_is_rejected(self) -> None:
        # Find a plain ZNR instant that is castable at all (some instants
        # have no SpellAbility: unparsed effect side), then reject the flag.
        for meta in self.supply.metas.values():
            if "Instant" not in meta.type_line:
                continue
            record = self.supply.pool.results[meta.oracle_id].card
            if any(isinstance(a, KickerAbility) for a in record.abilities):
                continue
            handle = self.world.add_card(identity_of(record), self.p0, ZONE_HAND)
            self.world.players[self.p0].mana_pool.clear()
            self.world.players[self.p0].mana_pool["U"] = 10
            if spell_castable(self.executor, self.p0, handle)[0] is not None:
                continue  # uncastable for another reason (no spell node...)
            reason = spell_castable(self.executor, self.p0, handle, kicked=True)[0]
            assert reason is not None
            self.assertTrue(reason.startswith("cast:not_a_kicker"), reason)
            return
        self.fail("no castable non-kicker instant in the ZNR engine pool")

    def test_legal_casts_enumerates_kicker_both_ways(self) -> None:
        record = _record_named(self.supply, "Roost of Drakes")
        handle = self.world.add_card(identity_of(record), self.p0, ZONE_HAND)
        self.world.players[self.p0].mana_pool.clear()
        self.world.players[self.p0].mana_pool["U"] = 4
        kicks = {
            row.kicked
            for row in legal_casts(self.world, self.executor, self.p0)
            if row.handle == handle
        }
        self.assertEqual(kicks, {True, False}, "CR 601.2b: the choice, both ways")


class XKickerLaneTest(unittest.TestCase):
    """An X-valued kicker: Thieving Skydiver
    ``Kicker {X}. X can't be 0.`` Its printed cost {1}{U} carries no X, so
    the kicker {X} is the spell's ONLY X — CR 107.4a gives ONE declared
    value per object, feeding both the cost fold and the ETB filter. The
    cast's ``x`` IS that single announcement (no separate kicker-X slot).

    The X law is the engine's zero floor (CR 107.1): X=0 is a legal
    declaration, so a kick with X=0 pays {0} and IS a legal kick. The
    printed "X can't be 0." is UNPARSED (the grammar has no X-bound
    atom), so the engine cannot enforce a constraint it cannot
    see — a REGISTERED effect gap, never a silent side-channel check. The
    card stays engine-UNSUPPORTED (its gated ETB control-gain effect is
    unparsed), so it is addressed from the ``all`` supply."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.supply = get_supply("all", "ZNR")

    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=3)
        self.executor = Executor(self.world)
        self.executor.attach_pool(self.supply.pool)
        self.p0, _p1 = self.world.player_order
        self.world.active_player = self.p0
        self.executor.turn_open = True
        self.executor.phase = "FIRST_MAIN"

    def _hand(self, mana: int):
        record = _record_named(self.supply, "Thieving Skydiver")
        handle = self.world.add_card(identity_of(record), self.p0, ZONE_HAND)
        self.world.players[self.p0].mana_pool.clear()
        self.world.players[self.p0].mana_pool["U"] = mana
        return handle

    def test_x_kicker_fold_prices_the_announced_x(self) -> None:
        # {1}{U} + {X}: X=2 -> 3 generic + 1 colored = 4 from the U pool.
        handle = self._hand(6)
        reason, _node, _rec, plan = spell_castable(
            self.executor, self.p0, handle, x=2, kicked=True
        )
        self.assertIsNone(reason, str(reason))
        assert plan is not None
        self.assertEqual(plan.mana, (("U", 4),), plan.mana)

    def test_x_kicker_zero_floor_is_a_legal_kick(self) -> None:
        # CR 107.1: X=0 pays {0} yet still marks the cast
        # kicked — {1}{U}{0} = 2 total, same as the un-kicked base.
        handle = self._hand(6)
        reason, _node, _rec, plan = spell_castable(
            self.executor, self.p0, handle, x=0, kicked=True
        )
        self.assertIsNone(reason, str(reason))
        assert plan is not None
        self.assertEqual(plan.mana, (("U", 2),), plan.mana)

    def test_x_kicker_too_big_x_is_a_shortage_not_a_raise(self) -> None:
        handle = self._hand(2)  # only 2 mana available
        reason = spell_castable(self.executor, self.p0, handle, x=5, kicked=True)[0]
        assert reason is not None
        self.assertIn("cost:mana", reason)

    def test_legal_casts_prices_the_x_kicker_both_ways(self) -> None:
        # base {1}{U} and the X=0 kick witness share a cost, so BOTH rows
        # ride the surface even on a base-priced pool; a caller asking X=3
        # on a 2-mana pool keeps only the base row (an honest shortage).
        handle = self._hand(2)
        both = {
            row.kicked
            for row in legal_casts(self.world, self.executor, self.p0)
            if row.handle == handle
        }
        self.assertEqual(both, {True, False}, "CR 601.2b: both, at the X=0 floor")
        big = {
            row.kicked
            for row in legal_casts(self.world, self.executor, self.p0, x=3)
            if row.handle == handle
        }
        self.assertEqual(big, {False}, "an unaffordable X-kick disappears")

    def test_was_kicked_window_sees_the_x_kicked_cast(self) -> None:
        handle = self._hand(6)
        frame = cast(self.executor, self.p0, handle, x=2, kicked=True)
        self.assertEqual(frame.x_value, 2)
        self.assertTrue(frame.kicked)
        [row] = [
            e
            for e in self.executor.journal.events
            if e.kind == "CAST" and e.subject == handle
        ]
        self.assertEqual(row.cast[4], 2, "journalled declared X")
        self.assertTrue(row.kicked, "journalled paid-kick flag")
        ctx = ctx_for(self.executor, source=handle, controller=self.p0)
        self.assertTrue(
            eval_filter(FAtom(FAtomPred.WAS_KICKED), handle, ctx),
            "the window read must see the X-kicked cast",
        )


class PermanentKickerBlinkTest(unittest.TestCase):
    """WAS_KICKED for a handle ON the battlefield is ENTRY-BOUND, not
    window-bound. A kicked permanent that leaves and re-enters is a NEW
    object that was never cast (CR 400.7), so its gated EtBState must not
    re-apply (CR 614.1c)
    and "if it was kicked" follows the ENTRY's provenance (the entry
    ZONE_CHANGE row's from_state), not the stale CAST row. Exercised with
    the engine's REAL out-and-back primitives (MOVE_ZONE exile lane +
    MOVE_ZONE battlefield-put lane, the runner's `enter` op twin) on the
    real compiled Cragplate Baloth."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.supply = get_supply("all", "ZNR")

    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=3)
        self.executor = Executor(self.world)
        self.executor.attach_pool(self.supply.pool)
        self.p0, _p1 = self.world.player_order
        self.world.active_player = self.p0
        self.executor.turn_open = True
        self.executor.phase = "FIRST_MAIN"
        record = _record_named(self.supply, "Cragplate Baloth")
        self.handle = self.world.add_card(identity_of(record), self.p0, ZONE_HAND)
        self.world.players[self.p0].mana_pool.clear()
        self.world.players[self.p0].mana_pool["G"] = 30

    def _move(self, dest: ZoneKind) -> None:
        # The runner's `enter` op shape, generalized: bindings carry the
        # handle straight to the MOVE_ZONE move (the Selector is the atom's
        # required cards role; the binding short-circuits resolution).
        handle = self.handle
        self.executor.execute(
            _atom(
                Verb.MOVE_ZONE,
                cards=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    UNIV,
                    zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),),
                ),
                destination=Zone(dest, ControllerRef.YOU),
            ),
            source=handle,
            controller=self.p0,
            bindings={"cards": handle},
        )

    def _was_kicked(self) -> bool:
        ctx = ctx_for(self.executor, source=self.handle, controller=self.p0)
        return eval_filter(FAtom(FAtomPred.WAS_KICKED), self.handle, ctx)

    def test_cast_kicked_permanent_lane_true_and_counters_applied(self) -> None:
        # CONTROL: no blink — the entry IS the cast's resolution, so the
        # entry-bound read sees the cast's kick and the gate applies once.
        cast(self.executor, self.p0, self.handle, kicked=True)
        self.assertEqual(self.world.zone_of(self.handle).kind, ZONE_BATTLEFIELD)
        self.assertTrue(self._was_kicked(), "kicked cast, entry from stack")
        self.assertEqual(self.world.cards[self.handle].counters.get("PLUS_1_PLUS_1"), 4)

    def test_un_kicked_second_cast_in_same_world_reads_false(self) -> None:
        # Falsifier for the pairing term: a KICKED cast earlier in the same
        # window/journal must not leak into the second, un-kicked cast's
        # entry — the entry-bound read must carry THIS cast's False.
        other_rec = _record_named(self.supply, "Cragplate Baloth")
        other = self.world.add_card(identity_of(other_rec), self.p0, ZONE_HAND)
        cast(self.executor, self.p0, self.handle, kicked=True)
        cast(self.executor, self.p0, other, kicked=False)
        ctx = ctx_for(self.executor, source=other, controller=self.p0)
        self.assertFalse(
            eval_filter(FAtom(FAtomPred.WAS_KICKED), other, ctx),
            "the un-kicked entry carries its own provenance, not the sibling's",
        )
        self.assertEqual(self.world.cards[other].counters, {})
        self.assertEqual(self.world.cards[self.handle].counters.get("PLUS_1_PLUS_1"), 4)

    def test_blink_return_is_not_kicked_and_does_not_reapply_counters(self) -> None:
        cast(self.executor, self.p0, self.handle, kicked=True)
        self.assertEqual(self.world.cards[self.handle].counters.get("PLUS_1_PLUS_1"), 4)
        self._move(ZoneKind.EXILE)
        self.assertEqual(self.world.zone_of(self.handle).kind, ZONE_EXILE)
        counters_before = dict(self.world.cards[self.handle].counters)
        self._move(ZoneKind.BATTLEFIELD)  # the return: EtBState hook re-runs
        self.assertEqual(self.world.zone_of(self.handle).kind, ZONE_BATTLEFIELD)
        self.assertFalse(
            self._was_kicked(),
            "CR 400.7: the returning object was never cast — stale CAST row forbidden",
        )
        self.assertEqual(
            dict(self.world.cards[self.handle].counters),
            counters_before,
            "CR 614.1c: the gated entering state must NOT re-apply on a return "
            "(an 8-counter permanent here would be the window-heuristic bug)",
        )

    def test_put_enter_from_hand_never_kicked_never_phantom_counters(self) -> None:
        # Falsifier for a phantom gate: a card that was never cast at all
        # enters via the MOVE_ZONE battlefield-put lane (runner `enter` op)
        # — gate False, zero counters.
        self._move(ZoneKind.BATTLEFIELD)
        self.assertEqual(self.world.zone_of(self.handle).kind, ZONE_BATTLEFIELD)
        self.assertFalse(self._was_kicked())
        self.assertEqual(self.world.cards[self.handle].counters, {})

    def test_kicked_permanent_lane_survives_the_turn_boundary(self) -> None:
        # Entry-bound (whole journal), not window-bound: a kicked permanent
        # that is STILL the same object next turn was still kicked
        # (CR 702.27a — the property does not expire with the window).
        cast(self.executor, self.p0, self.handle, kicked=True)
        self.executor.end_turn()
        self.executor.advance_turn()
        self.assertEqual(self.world.zone_of(self.handle).kind, ZONE_BATTLEFIELD)
        self.assertTrue(self._was_kicked(), "entry provenance is object permanence")


class ReplayDeterminismTest(unittest.TestCase):
    """One seed replays to the same fingerprint; different seeds diverge."""

    def test_one_seed_two_runs_identical_fingerprint(self) -> None:
        first = play_game(3, "castable", SMOKE_DECK_PAIRS, turn_cap=8)
        second = play_game(3, "castable", SMOKE_DECK_PAIRS, turn_cap=8)
        self.assertTrue(first.fingerprint)
        self.assertEqual(first.fingerprint, second.fingerprint)
        self.assertEqual(first.digest, second.digest)
        self.assertEqual((first.turns, first.acts), (second.turns, second.acts))
        self.assertEqual(first.fired_names, second.fired_names)
        self.assertEqual(first.reason, second.reason)

    def test_different_seeds_diverge(self) -> None:
        self.assertNotEqual(
            play_game(3, "castable", SMOKE_DECK_PAIRS, turn_cap=8).fingerprint,
            play_game(4, "castable", SMOKE_DECK_PAIRS, turn_cap=8).fingerprint,
        )


class DecisionSurfaceTest(unittest.TestCase):
    """The ENGINE asks with the query's own vocabulary at the demand site,
    and the policy answers that enumeration."""

    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=1)
        self.p0 = self.world.player_order[0]
        self.executor = Executor(self.world)
        self.source = self.world.add_card(card_id("Anchor"), self.p0, ZONE_HAND)
        self.policy = RandomPolicy(0)

    def test_may_offer_narrowing_autopicks_the_forced_answer(self) -> None:
        # "You may pay {2}" with an empty pool: query.py narrows the offer
        # to skip (CR 117.3). A skip-only surface is NOT an ask — the
        # shared phantom gate (offers.offer_or_autopick) consumes it
        # silently, so a blind "fire" provider is never consulted and
        # the illegal decision CANNOT be made: nothing is offered at all.
        # The consumption is journalled, not asked: answered() — the
        # public ask lane — stays empty.
        effect = OptionalEffect(
            _atom(Verb.PAY, cost=Cost(parts=(CostManaGeneric(QConst(2)),)))
        )
        self.assertEqual(
            optional_offer(
                self.executor, effect, source=self.source, controller=self.p0
            ),
            ("skip",),
        )
        consulted: list[tuple[tuple[str, ...], str]] = []

        def blind(vocab, what):
            consulted.append((tuple(vocab), what))
            return "fire"

        self.executor.decisions.provider = blind
        self.executor.apply_effect(effect, source=self.source, controller=self.p0)
        self.assertEqual(consulted, [], "forced surface was presented")
        self.assertEqual(self.executor.decisions.answered(), ())
        site = f"may:{self.source}"
        self.assertTrue(
            any(
                w == site or w.startswith(f"{site}:")
                for w, a in self.executor.decisions.journal
            ),
            "the forced skip was not journalled",
        )

    def test_choose_ask_vocabulary_is_the_query_enumeration(self) -> None:
        effect = Choose(
            count=QConst(1),
            options=(
                _atom(Verb.TAP, target=_target_sel()),
                _atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1)),
            ),
        )
        stock_libraries(self.world)  # the DRAW option draws (CR 704.5b)
        asked: list[tuple[tuple[str, ...], str]] = []

        def provider(vocab: tuple[str, ...], what: str) -> str:
            asked.append((vocab, what))
            return self.policy.choose(vocab)

        self.executor.decisions.provider = provider
        self.executor.apply_effect(effect, source=self.source, controller=self.p0)
        # the ask vocabulary equals the query surface's own option-set
        # enumeration (query/runtime identity, delivered AT the ask)
        self.assertEqual(len(asked), 1)
        vocab, what = asked[0]
        self.assertTrue(what.startswith(f"choose:{self.source}:"))
        # Choose + QConst(1) = exactly the n printed options (choose_options)
        self.assertEqual(vocab, ("0", "1"))

    def test_unimplemented_node_raises_from_the_engine(self) -> None:
        # Repeat is real IR and unimplemented: the harness reports the
        # engine's OWN raise (it does not mirror the gate — it plays into it).
        with self.assertRaises(NotImplementedError):
            self.executor.apply_effect(
                Repeat(
                    count=QConst(2),
                    inner=_atom(
                        Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1)
                    ),
                ),
                source=self.source,
                controller=self.p0,
            )

    def test_loud_exhaustion_no_default(self) -> None:
        # An empty stream with no pool and no answerer raises —
        # the engine never defaults a decision.
        effect = OptionalEffect(
            _atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1))
        )
        with self.assertRaises(ValueError):
            self.executor.apply_effect(effect, source=self.source, controller=self.p0)


class CrashLedgerTest(unittest.TestCase):
    """Stack-zone targets, a land's own ETB ask, the world-count gate, the synthesized
    opponent slot, the result register, ONE_OF/REST designation and the undeclared X."""

    def test_b2_stack_zone_targets_are_enumerable(self) -> None:
        """Zone(STACK) targets enumerate the parked spells. The M21 consumer
        is Unsubstantiate's BATTLEFIELD + STACK target selector."""
        reset_oracle_ids()
        world = GameWorld(num_players=2, master_seed=2)
        p0 = world.player_order[0]
        executor = Executor(world)
        spell = world.add_card(
            CardIdentity(
                oracle_id=_oid(201), name="Unsubstantiate", type_line="Instant"
            ),
            p0,
            ZONE_HAND,
        )
        park(executor, p0, spell)
        slot = legal_targets(
            world,
            executor,
            Selector(
                count=QConst(1),
                mode=SelectorMode.TARGET,
                filter=UNIV,
                zones=(Zone(ZoneKind.STACK, ControllerRef.ANY),),
            ),
            source=spell,
            controller=p0,
        )
        self.assertEqual(slot.candidates, (spell,))

    def test_b4_scry_armed_by_the_land_drop_itself_is_answered(self) -> None:
        """The M21 check-land cycle — drop the land, ITS OWN ETB scry asks
        mid-op — answers through the vocabulary-addressed channel: the scry
        ask arrives with ('top','bottom') + the 'scry:<player>:<n>' tag the
        moment the drain reaches it, and the provider answers without the
        caller having enumerated anything. Scripted proof below (direct,
        no policy path). Replay fingerprint pinned (the decision history
        rides the seeded stream: two runs agree)."""
        supply = get_supply("all")
        record = _record_named(supply, "Temple of Epiphany")
        answers: list[tuple[tuple[str, ...], str]] = []

        def play_once(seed: int) -> tuple[str, int]:
            reset_oracle_ids()
            world = GameWorld(num_players=2, start_life=20, master_seed=seed)
            p0 = world.player_order[0]
            executor = Executor(world)
            executor.attach_pool(supply.pool)
            land = world.add_card(identity_of(record), p0, ZONE_HAND)
            world.add_card(
                CardIdentity(oracle_id=_oid(203), name="TopDeck", type_line="Instant"),
                p0,
                ZONE_LIBRARY,
            )
            top_before = list(world.players[p0].zone(ZONE_LIBRARY).entries)
            world.active_player = p0
            executor.turn_open = True
            executor.phase = "FIRST_MAIN"

            def answer(vocab: tuple[str, ...], what: str) -> str:
                answers.append((vocab, what))
                return "bottom" if len(answers) % 2 else "top"

            executor.decisions.provider = answer
            play_land(executor, p0, land)
            lib = world.players[p0].zone(ZONE_LIBRARY).entries
            # the scry DID happen: the ETB fired inside the drop's own
            # settle, asked, was answered, and the library moved.
            self.assertEqual(len(answers), 1)
            vocab, what = answers[0]
            self.assertEqual(vocab, ("top", "bottom"))
            self.assertTrue(what.startswith(f"scry:{p0}:1"))
            self.assertEqual(list(lib), list(top_before))  # scry 1 -> bottom, same
            return executor.state_fingerprint(), world.turn

        fp_a, _ = play_once(41)
        answers.clear()
        fp_b, _ = play_once(41)
        answers.clear()
        self.assertEqual(fp_a, fp_b)

    def test_b7_controller_count_ge_filter_raises_from_the_query(self) -> None:
        """The world-count CONTROLLER_COUNT_GE (Fabled Passage) answers at
        the query entry point (ctx_for carries the journal, and this pred
        is pure world-state): 3 lands < 4 is False, and the 4th land flips
        it."""
        supply = get_supply("all")
        record = _record_named(supply, "Fabled Passage")
        pred = next(
            node.pred
            for ability in record.abilities
            if isinstance(ability, (ActivatedAbility, TriggeredAbility))
            and ability.effect is not None
            for node in walk(ability.effect)
            if isinstance(node, Conditional)
            and isinstance(node.pred, FAtom)
            and node.pred.pred is FAtomPred.CONTROLLER_COUNT_GE
        )
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=3)
        p0 = world.player_order[0]
        executor = Executor(world)
        executor.attach_pool(supply.pool)
        permanent = world.add_card(identity_of(record), p0, ZONE_BATTLEFIELD)
        ctx = ctx_for(executor, source=permanent, controller=p0)
        self.assertFalse(eval_filter(pred, permanent, ctx))  # 1 land (itself)
        for i in range(2):
            world.add_card(
                CardIdentity(
                    oracle_id=_oid(400 + i), name=f"Plot {i}", type_line="Land"
                ),
                p0,
                ZONE_BATTLEFIELD,
            )
        self.assertFalse(eval_filter(pred, permanent, ctx))  # 3 lands < 4
        world.add_card(
            CardIdentity(oracle_id=_oid(403), name="Plot 4", type_line="Land"),
            p0,
            ZONE_BATTLEFIELD,
        )
        self.assertTrue(eval_filter(pred, permanent, ctx))  # 4 lands >= 4

    def test_b8_target_player_coordinate_rides_the_synthesized_slot(self) -> None:
        """'target opponent' compiles to a ControllerRef.TARGET_OPPONENT
        coordinate with NO Selector — the slot query SYNTHESIZES the
        designation slot (candidates = the opponent seats, the engine's own
        CR population), so the policy designates from the query instead of
        mirroring the rule, and ``stack._validate_spell_targets`` stays the
        oracle."""
        supply = get_supply("all")
        record = _record_named(supply, "Duress")
        node = next(a for a in record.abilities if isinstance(a, SpellAbility))
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=3)
        p0, p1 = world.player_order
        executor = Executor(world)
        executor.attach_pool(supply.pool)
        spell = world.add_card(identity_of(record), p0, ZONE_HAND)
        # Duress keeps creatures OUT of the choice pool, so the victim has to be
        # a noncreature nonland card or the CHOOSE pool is empty and the test
        # measures nothing.
        world.add_card(
            CardIdentity(
                oracle_id=_oid(202), name="Victim", type_line="Artifact", cmc=1
            ),
            p1,
            ZONE_HAND,
        )
        slots = spell_target_slots(executor, node, spell_handle=spell, seat=p0)
        self.assertEqual(len(slots), 1)
        self.assertTrue(slots[0].synthetic)  # the coordinate's slot
        self.assertEqual(slots[0].candidates, (p1,))  # engine CR population
        for key in ("U", "B"):
            world.players[p0].mana_pool[key] = 1
        world.active_player = p0  # the window gate reads the world, not the op
        executor.turn_open = True
        executor.phase = "FIRST_MAIN"
        cast(
            executor,
            p0,
            spell,
            targets=(p1,),  # designated FROM the slot
            decisions=("0",),  # the CHOOSE atom's pick, index into the row order
        )
        self.assertEqual(
            len(world.players[p1].zone(ZONE_HAND).entries),
            0,
            "the designated opponent is the one that discarded",
        )

    def test_b9_result_referent_resolves_from_resolution_producers(self) -> None:
        """The ``result`` register is the ctx's ``result`` binding slot,
        written by the object-action verbs (SEARCH, CHOOSE, TAP, UNTAP,
        PUT_COUNTER, MOVE_ZONE) INSIDE one effect execution, and
        per-resolution because every ExecCtx carries a fresh bindings dict.

        (a) Feat of Resistance resolves at CAST: PUT_COUNTER writes the
            designated creature, the color Choose asks, GRANT reads it.
        (b) Seasoned Hallowblade's tail is the activation's: paying DISCARD
            runs Seq(TAP; GRANT) — the blade turns indestructible.
        (c) A read with NO producer in its own execution RAISES (flag,
            never guess) — and the write never leaked out of the
            activation that made it (per-resolution, not card-global)."""
        supply = get_supply("all")
        # (a) the cast-resolution face
        record = _record_named(supply, "Feat of Resistance")
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=3)
        p0, _p1 = world.player_order
        executor = Executor(world)
        executor.attach_pool(supply.pool)
        spell = world.add_card(identity_of(record), p0, ZONE_HAND)
        critter = world.add_card(card_id("Feat Target"), p0, ZONE_BATTLEFIELD)
        world.players[p0].mana_pool["W"] = 1
        world.players[p0].mana_pool["C"] = 1
        world.active_player = p0
        executor.turn_open = True
        executor.phase = "FIRST_MAIN"
        cast(executor, p0, spell, targets=(critter,), decisions=("0",))
        self.assertEqual(world.cards[critter].counters.get("PLUS_1_PLUS_1"), 1)
        self.assertTrue(
            executor.layers.keyword_of(critter, Keyword.PROTECTION),
            "the GRANT read the PUT_COUNTER target from the result register",
        )
        # (b) the captured activation tail
        blade_rec = _record_named(supply, "Seasoned Hallowblade")
        blade = world.add_card(identity_of(blade_rec), p0, ZONE_BATTLEFIELD)
        executor.binder.attach_card(blade, blade_rec)
        world.add_card(card_id("Blade Bait"), p0, ZONE_HAND)
        activate(executor, blade, 0, seat=p0)
        self.assertTrue(world.cards[blade].tapped)
        self.assertTrue(
            executor.layers.keyword_of(blade, Keyword.INDESTRUCTIBLE),
            "TAP wrote the register; the tail's GRANT read the blade itself",
        )
        # (c) the same GRANT step in a FRESH execution raises: no producer
        # ran there — per-resolution scope, and the flag convention intact.
        tail = blade_rec.abilities[0]
        assert isinstance(tail, ActivatedAbility) and isinstance(tail.effect, Seq)
        grant = tail.effect.steps[1]
        with self.assertRaises(NotImplementedError) as cm:
            executor.apply_effect(grant, source=blade, controller=p0)
        self.assertIn("producer", str(cm.exception))
        # …and the blade in hand is a spell (the creature has a cast-lane
        # carrier): legality reaches the mana gate and fails there on an
        # empty pool.
        hand_spell = world.add_card(identity_of(blade_rec), p0, ZONE_HAND)
        world.active_player = p0
        executor.turn_open = True
        executor.phase = "FIRST_MAIN"
        with self.assertRaises(ValueError) as cm:
            cast(executor, p0, hand_spell, targets=(), decisions=())
        self.assertIn("cost:mana", str(cm.exception))

    def test_new_rest_one_of_designation_is_the_12c_gap(self) -> None:
        """The split-selection pair designates through the
        vocabulary-addressed decision channel. ONE_OF asks with the
        Handle-sorted candidate list as the EXACT vocabulary
        (enumerate-then-answer, no prose); an answer no lane can give
        RAISES loudly (never a default); REST is the deterministic
        complement — no ask (query.rest_of's runtime twin)."""
        # (a) one candidate: forced, no decision consumed (exactly-one
        #     legal filler auto-fills).
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=7)
        p0 = world.player_order[0]
        executor = Executor(world)
        host = world.add_card(
            CardIdentity(oracle_id=_oid(204), name="Host", type_line="Creature"),
            p0,
            ZONE_BATTLEFIELD,
        )
        asked: list[tuple[tuple[str, ...], str]] = []
        executor.decisions.provider = lambda vocab, what: (
            asked.append((vocab, what)) or vocab[0]
        )
        tap_one_of = _atom(
            Verb.TAP,
            target=Selector(
                count=QConst(1),
                mode=SelectorMode.ONE_OF,
                filter=UNIV,
                zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
            ),
        )
        executor.apply_effect(tap_one_of, source=host, controller=p0)
        self.assertEqual(asked, [])  # forced — no ask happened
        self.assertTrue(world.cards[host].tapped)
        # (b) two candidates: the ask vocabulary is the Handle-sorted
        #     candidate list, and the answered handle alone gets tapped.
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=7)
        p0 = world.player_order[0]
        executor = Executor(world)
        first = world.add_card(
            CardIdentity(oracle_id=_oid(204), name="First", type_line="Creature"),
            p0,
            ZONE_BATTLEFIELD,
        )
        second = world.add_card(
            CardIdentity(oracle_id=_oid(205), name="Second", type_line="Creature"),
            p0,
            ZONE_BATTLEFIELD,
        )
        asked = []
        executor.decisions.provider = lambda vocab, what: (
            asked.append((vocab, what)) or vocab[-1]  # pick the LAST one
        )
        executor.apply_effect(tap_one_of, source=first, controller=p0)
        self.assertEqual(len(asked), 1)
        self.assertEqual(asked[0][0], tuple(sorted(str(h) for h in (first, second))))
        self.assertTrue(world.cards[second].tapped)
        self.assertFalse(world.cards[first].tapped)
        # (c) REST: the complement of this resolution's ONE_OF pick —
        # paired inside ONE Seq (the Cultivate shape; the pairing is
        # ctx-scoped). TAP asks (provider picks the LAST candidate), then
        # UNTAP-REST must leave the PICKED card alone: if the complement
        # failed, the picked card would come back untapped.
        bf = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=7)
        p0 = world.player_order[0]
        executor = Executor(world)
        for i in (204, 205, 206):
            world.add_card(
                CardIdentity(oracle_id=_oid(i), name=f"C{i}", type_line="Creature"),
                p0,
                ZONE_BATTLEFIELD,
            )
        asked = []
        executor.decisions.provider = lambda vocab, what: (
            asked.append((vocab, what)) or vocab[-1]
        )
        executor.apply_effect(
            Seq(
                steps=(
                    _atom(
                        Verb.TAP,
                        target=Selector(
                            QConst(1), SelectorMode.ONE_OF, UNIV, zones=(bf,)
                        ),
                    ),
                    _atom(
                        Verb.UNTAP,
                        target=Selector(
                            QConst(1), SelectorMode.REST, UNIV, zones=(bf,)
                        ),
                    ),
                )
            ),
            source=world.players[p0].zone(ZONE_BATTLEFIELD).entries[0],
            controller=p0,
        )
        self.assertEqual(len(asked), 1)  # REST never asks (forced complement)
        entries = world.players[p0].zone(ZONE_BATTLEFIELD).entries
        picked = max(entries)  # vocab[-1] = Handle-last
        # The TAP tapped ONLY the pick; the UNTAP-REST tapped nothing else
        # (they started untapped, a no-op) AND MUST HAVE LEFT THE PICK
        # ALONE — if the complement failed, the pick would sit untapped.
        self.assertTrue(world.cards[picked].tapped)
        self.assertFalse(any(world.cards[h].tapped for h in entries if h != picked))
        # (d) exhaustion stays loud: ONE_OF with a real choice and no lane.
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=7)
        p0 = world.player_order[0]
        executor = Executor(world)
        a = world.add_card(
            CardIdentity(oracle_id=_oid(204), name="A", type_line="Creature"),
            p0,
            ZONE_BATTLEFIELD,
        )
        world.add_card(
            CardIdentity(oracle_id=_oid(205), name="B", type_line="Creature"),
            p0,
            ZONE_BATTLEFIELD,
        )
        with self.assertRaises(ValueError) as cm:
            executor.apply_effect(tap_one_of, source=a, controller=p0)
        self.assertIn("needs a decision", str(cm.exception))

    def test_qx_undeclared_x_resolves_the_whole_cast(self) -> None:
        """CR 601.2f declares X WITH the total cost, so when the caller
        passes no x the legality fold's documented X=0 witness (CR 107.1)
        is the DECLARATION — the frame's x_value and the effect's QX (a QX
        in an effect quantity, not the cost) read it. Primal Might's X=0
        cast RESOLVES end to end: spell to graveyard, the QX=0 witness deal
        leaves NO damage mark (mark_damage ignores n<=0), the ally
        survives, and the FIGHT's CHOOSE over an empty opponent population
        fights nobody. Outside a cast an unbound QX (ctx.x_value None)
        still raises."""
        supply = get_supply("all")
        record = _record_named(supply, "Primal Might")
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=5)
        p0 = world.player_order[0]
        executor = Executor(world)
        executor.attach_pool(supply.pool)
        spell = world.add_card(identity_of(record), p0, ZONE_HAND)
        creature = world.add_card(
            CardIdentity(oracle_id=_oid(210), name="Ally", type_line="Creature"),
            p0,
            ZONE_BATTLEFIELD,
        )
        world.players[p0].mana_pool["G"] = 3
        world.active_player = p0
        executor.turn_open = True
        executor.phase = "FIRST_MAIN"
        cast(executor, p0, spell, targets=(creature,), decisions=())  # no raise
        self.assertEqual(world.zone_of(spell).kind, ZONE_GRAVEYARD)
        self.assertEqual(world.zone_of(creature).kind, ZONE_BATTLEFIELD)
        self.assertEqual(executor.damage, {})  # QX witness X=0 deals nothing

    def test_stats_report_shape(self) -> None:
        stats = run_games(2, "castable", SMOKE_DECK_PAIRS, turn_cap=4)
        for key in (
            "survival_pct",
            "mean_turns",
            "coverage_fired",
            "coverage_fired_of_engine_pct",
            "crashes",
            "rows",
            "engine_supported",
            "player_target_designations",
        ):
            self.assertIn(key, stats)
        self.assertEqual(stats["n_games"], 2)
        for crash in stats["crashes"]:
            self.assertTrue({"exc", "frame", "seeds", "repro"} <= set(crash))


class Round14cFixTest(unittest.TestCase):
    """Designation through non-target roles, anaphoric selectors, the
    actor's own hand for DISCARD, history predicates and stack
    enumeration."""

    def _world(self, seed: int = 7) -> tuple[GameWorld, Executor]:
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=seed)
        return world, Executor(world)

    def test_b15_cards_role_target_designation_flows(self) -> None:
        """Rise Again / Read the Tides: the TARGET-mode
        Selector riding in a non-``target`` ROLE resolves through the
        spell's designation (CR 601.2c — one designation, every "target"
        means it); UNdesignated keeps the loud raise."""
        supply = get_supply("all")
        record = _record_named(supply, "Rise Again")
        world, executor = self._world()
        executor.attach_pool(supply.pool)
        spell = world.add_card(identity_of(record), world.player_order[0], ZONE_HAND)
        p0, _p1 = world.player_order
        recruit = world.add_card(
            CardIdentity(oracle_id=_oid(77), name="Recruit", type_line="Creature"),
            p0,
            ZONE_GRAVEYARD,
        )
        for key in ("W", "U", "B", "R", "G", "C"):
            world.players[p0].mana_pool[key] = 20
        world.active_player = p0
        executor.turn_open = True
        executor.phase = "FIRST_MAIN"
        cast(executor, p0, spell, targets=(recruit,))
        self.assertEqual(world.zone_of(recruit).kind, ZONE_BATTLEFIELD)
        # UNDESIGNATED stays loud:
        _world2, executor2 = self._world(8)
        executor2.attach_pool(supply.pool)
        with self.assertRaises(ValueError) as cm:
            executor2.apply_effect(
                _atom(
                    Verb.MOVE_ZONE,
                    cards=Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAtom(FAtomPred.TYPE_EQ, string_value="Creature"),
                        zones=(Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),),
                    ),
                    destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                ),
                source=p0,
                controller=p0,
            )
        self.assertIn("TARGET selector has no designation", str(cm.exception))

    def test_b16_target_binding_does_not_clobber_referent_selector(self) -> None:
        """Necromentia: an ANAPHORIC Selector (referent set) resolves
        itself — the spell-level ``target`` designation (the designated
        OPPONENT) does not hijack the role (a player handle must never reach
        controller_of). The SEARCH atom also lands its found cards in the
        ``result`` register (the CHOOSE read-back convention Necromentia's
        EXILE reads)."""
        world, executor = self._world()
        p0, p1 = world.player_order
        card = world.add_card(
            CardIdentity(oracle_id=_oid(88), name="Found", type_line="Creature"),
            p0,
            ZONE_GRAVEYARD,
        )
        executor.apply_effect(
            _atom(
                Verb.MOVE_ZONE,
                target=Selector(
                    QConst(1),
                    SelectorMode.CHOOSE,
                    UNIV,
                    zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
                    referent="result",
                ),
                destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER),
            ),
            source=p0,
            controller=p0,
            bindings={"target": [p1], "result": [card]},
        )
        self.assertEqual(world.zone_of(card).kind, ZONE_EXILE)
        # SEARCH writes the register: search-then-referent in one Seq, no
        # binding for 'cards' (the Necromentia compile idiom).
        world, executor = self._world(9)
        p0 = world.player_order[0]
        land = world.add_card(
            CardIdentity(oracle_id=_oid(89), name="Swamp", type_line="Basic Land"),
            p0,
            ZONE_LIBRARY,
        )
        executor.apply_effect(
            Seq(
                steps=(
                    _atom(
                        Verb.SEARCH,
                        cards=Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            UNIV,
                            zones=(Zone(ZoneKind.LIBRARY, ControllerRef.YOU),),
                        ),
                        destination=Zone(ZoneKind.EXILE, ControllerRef.YOU),
                    ),
                    _atom(
                        Verb.MOVE_ZONE,
                        target=Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            UNIV,
                            zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
                            referent="result",
                        ),
                        destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER),
                    ),
                )
            ),
            source=p0,
            controller=p0,
        )
        self.assertEqual(world.zone_of(land).kind, ZONE_EXILE)

    def test_b18_discard_scoped_to_the_actors_live_hand(self) -> None:
        """Bad Deal: the DISCARD selection pool is the ACTOR'S own hand
        re-read at take time (CR 701.8a). Bad Deal's compiled Zone(HAND,
        ANY) spans both hands; the Handle-sorted stand-in must not grab the
        CASTER'S low handles. The caster's hand stays intact."""
        world, executor = self._world()
        p0, p1 = world.player_order
        # caster's card FIRST (lowest handle — what a sorted pick over both
        # hands would reach for), then the actor's two.
        mine = world.add_card(
            CardIdentity(oracle_id=_oid(90), name="Mine", type_line="Creature"),
            p0,
            ZONE_HAND,
        )
        theirs = [
            world.add_card(
                CardIdentity(
                    oracle_id=_oid(91 + i), name=f"Theirs{i}", type_line="Creature"
                ),
                p1,
                ZONE_HAND,
            )
            for i in range(2)
        ]
        executor.execute(
            _atom(
                Verb.MOVE_ZONE,
                controller=ControllerRef.OPPONENT,
                cards=Selector(
                    QConst(2),
                    SelectorMode.CHOOSE,
                    UNIV,
                    zones=(Zone(ZoneKind.HAND, ControllerRef.ANY),),
                ),
                **{
                    "destination": Zone(ZoneKind.GRAVEYARD, ControllerRef.OPPONENT),
                    "from": Zone(ZoneKind.HAND, ControllerRef.OPPONENT),
                },
            ),
            source=mine,
            controller=p0,
        )
        self.assertEqual(world.zone_of(mine).kind, ZONE_HAND)
        for card in theirs:
            self.assertEqual(world.zone_of(card).kind, ZONE_GRAVEYARD)
        self.assertEqual(world.players[p1].zone(ZONE_HAND).entries, [])

    def test_new_moved_to_zone_this_turn_pred_stays_unimplemented(self) -> None:
        """The journal rides every ExecCtx (query included), so the history
        preds ANSWER: with no matching journalled row this turn the honest
        answer is False (the history is a record, and an empty record is an
        answer — unlike FLIP_WON's no-antecedent raise, below). Positive
        legs live in Round14dJournalTest (real moves/casts make the same
        preds True)."""
        world, executor = self._world()
        p0 = world.player_order[0]
        card = world.add_card(
            CardIdentity(oracle_id=_oid(95), name="Ledger", type_line="Creature"),
            p0,
            ZONE_EXILE,
        )
        ctx = ctx_for(executor, source=p0, controller=p0)
        cases = (
            (
                FAtomPred.MOVED_TO_ZONE_THIS_TURN,
                FAtom(
                    FAtomPred.MOVED_TO_ZONE_THIS_TURN,
                    who=ControllerRef.YOU,
                    from_zone=Zone(ZoneKind.HAND, ControllerRef.YOU),
                    to_zone=Zone(ZoneKind.EXILE, ControllerRef.YOU),
                ),
            ),
            (
                FAtomPred.CAST_THIS_TURN_FROM,
                FAtom(
                    FAtomPred.CAST_THIS_TURN_FROM,
                    who=ControllerRef.YOU,
                    zone=Zone(ZoneKind.HAND, ControllerRef.YOU),
                ),
            ),
        )
        for pred, filt in cases:
            self.assertFalse(eval_filter(filt, card, ctx))  # no row = no move
        with self.assertRaises(NotImplementedError) as cm:
            eval_filter(FAtom(FAtomPred.FLIP_WON, who=ControllerRef.YOU), card, ctx)
        self.assertIn("FLIP_WON", str(cm.exception))  # no flip yet

    def test_b7_history_preds_stay_loud_on_a_bare_ctx(self) -> None:
        """The no-half-preds rule: a context that carries NO journal cannot
        answer a history predicate, and must raise naming the pred (the
        FLIP_WON / NAME_CHOSEN convention)."""
        world, executor = self._world()
        p0 = world.player_order[0]
        card = world.add_card(
            CardIdentity(oracle_id=_oid(96), name="Bare", type_line="Creature"),
            p0,
            ZONE_EXILE,
        )
        bare = ExecCtx(
            world=world,
            ledger=executor.ledger,
            controller=p0,
            source=p0,
            bindings={},
            decisions=(),
        )
        self.assertIsNone(bare.journal)
        for filt in (
            FAtom(FAtomPred.DIED_THIS_TURN),
            FAtom(
                FAtomPred.MOVED_TO_ZONE_THIS_TURN,
                who=ControllerRef.YOU,
                from_zone=Zone(ZoneKind.HAND, ControllerRef.YOU),
                to_zone=Zone(ZoneKind.EXILE, ControllerRef.YOU),
            ),
            FAtom(
                FAtomPred.CAST_THIS_TURN_FROM,
                who=ControllerRef.YOU,
                zone=Zone(ZoneKind.HAND, ControllerRef.YOU),
            ),
            FAtom(
                FAtomPred.ENTERED_THIS_TURN_FROM,
                zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
            ),
            FAtom(FAtomPred.IS_EXILED_WITH_SOURCE),
        ):
            with self.assertRaises(NotImplementedError) as cm:
                eval_filter(filt, card, bare)
            self.assertIn(filt.pred.name, str(cm.exception))
        # TARGETS_SOURCE needs no journal: it is the IS_ANY_TARGET mirror
        # (does the judged object's designation contain the ctx's SOURCE).
        # A bare ctx designates NOTHING, so the pre-declaration reading is a
        # conservative False; the fold behaviour is pinned in
        # test_executor_r23a.
        self.assertFalse(eval_filter(FAtom(FAtomPred.TARGETS_SOURCE), card, bare))

    def test_new_zone_stack_runtime_enumeration_raises(self) -> None:
        """Runtime enumeration of Zone(STACK) reads the parked frames
        through stack.stack_zone (the SAME source legal_targets reads), so
        an Unsubstantiate-shape MOVE_ZONE returns the spell to its owner's
        hand."""
        world, executor = self._world()
        p0 = world.player_order[0]
        spell = world.add_card(
            CardIdentity(oracle_id=_oid(97), name="Counterspell", type_line="Instant"),
            p0,
            ZONE_HAND,
        )
        park(executor, p0, spell)
        self.assertEqual(world.zone_of(spell).kind, "stack")
        executor.apply_effect(
            _atom(
                Verb.MOVE_ZONE,
                cards=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    UNIV,
                    zones=(Zone(ZoneKind.STACK, ControllerRef.ANY),),
                ),
                destination=Zone(ZoneKind.HAND, ControllerRef.OWNER),
            ),
            source=p0,
            controller=p0,
            bindings={"target": [spell]},
        )
        self.assertEqual(world.zone_of(spell).kind, ZONE_HAND)

    def test_b19_stack_enumeration_owner_scope_stays_loud(self) -> None:
        """OWNER-scoped STACK enumeration keeps the selector raise (every
        zone carries that flag at runtime), and an empty designation over
        the stack resolves to nothing, not a crash."""
        world, executor = self._world()
        p0 = world.player_order[0]
        with self.assertRaises(NotImplementedError) as cm:
            executor.apply_effect(
                _atom(
                    Verb.MOVE_ZONE,
                    cards=Selector(
                        QConst(1),
                        SelectorMode.ALL,
                        UNIV,
                        zones=(Zone(ZoneKind.STACK, ControllerRef.OWNER),),
                    ),
                    destination=Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                ),
                source=p0,
                controller=p0,
            )
        self.assertIn("OWNER in selector enumeration", str(cm.exception))
        executor.apply_effect(  # empty designation: no-op, never a KeyError
            _atom(
                Verb.MOVE_ZONE,
                cards=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    UNIV,
                    zones=(Zone(ZoneKind.STACK, ControllerRef.ANY),),
                ),
                destination=Zone(ZoneKind.HAND, ControllerRef.OWNER),
            ),
            source=p0,
            controller=p0,
            bindings={"target": []},
        )


class Round14dJournalTest(unittest.TestCase):
    """One POSITIVE test per journal-backed predicate the games hit, driven
    by REAL journalled atoms — plus the dies-row test and the cross-turn
    exile-with persistence. The turn window is begin_turn's UPKEEP marker
    (events.py turn_window)."""

    def _world(self, seed: int = 7) -> tuple[GameWorld, Executor]:
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=seed)
        return world, Executor(world)

    def test_moved_to_zone_handle_and_gate_readings(self) -> None:
        """MOVED_TO_ZONE_THIS_TURN (Necromentia's count + Barrin's gate):
        a real hand->exile atom makes the CANDIDATE leg true for the card
        that moved (a second exiled card is not), the gate leg existential
        for a battlefield anchor, and both legs false once the turn
        window turns over (advance_turn)."""
        world, executor = self._world()
        stock_libraries(world)  # turns advance: no deck-out (CR 704.5b)
        p0 = world.player_order[0]
        executor.begin_turn(p0)
        mover = world.add_card(
            CardIdentity(oracle_id=_oid(90), name="Purged", type_line="Creature"),
            p0,
            ZONE_HAND,
        )
        other = world.add_card(
            CardIdentity(oracle_id=_oid(91), name="Already", type_line="Creature"),
            p0,
            ZONE_EXILE,
        )
        anchor = world.add_card(
            CardIdentity(oracle_id=_oid(92), name="Barrin", type_line="Creature"),
            p0,
            ZONE_BATTLEFIELD,
        )
        executor.apply_effect(
            _atom(
                Verb.MOVE_ZONE,
                target=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    UNIV,
                    zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),),
                ),
                destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER),
            ),
            source=p0,
            controller=p0,
            bindings={"target": mover},
        )
        self.assertEqual(world.zone_of(mover).kind, ZONE_EXILE)
        pred = FAtom(
            FAtomPred.MOVED_TO_ZONE_THIS_TURN,
            who=ControllerRef.YOU,
            from_zone=Zone(ZoneKind.HAND, ControllerRef.YOU),
            to_zone=Zone(ZoneKind.EXILE, ControllerRef.YOU),
        )
        ctx = ctx_for(executor, source=p0, controller=p0)
        self.assertTrue(eval_filter(pred, mover, ctx))  # handle leg: it moved
        self.assertFalse(eval_filter(pred, other, ctx))  # exiled, but not so
        self.assertTrue(eval_filter(pred, anchor, ctx))  # gate: A move happened
        executor.advance_turn()  # the window turns over with the UPKEEP marker
        self.assertFalse(eval_filter(pred, mover, ctx))
        self.assertFalse(eval_filter(pred, anchor, ctx))

    def test_cast_this_turn_from_reads_the_cast_row(self) -> None:
        """CAST_THIS_TURN_FROM (See the Truth / Archfiend's Vessel): the
        CAST row's (caster, from_zone) columns answer the handle-
        scoped pred — from HAND yes, from the GRAVEYARD no, and the same
        row makes See-the-Truth's FNot(HAND) shape read False."""
        world, executor = self._world()
        p0, p1 = world.player_order
        executor.begin_turn(p0)
        spell = world.add_card(
            CardIdentity(oracle_id=_oid(93), name="Truthish", type_line="Sorcery"),
            p0,
            ZONE_HAND,
        )
        # the cast feed's own emitter — the same row stack.cast writes at
        # 601.2h (unit-scoped to the predicate, pipeline-shaped data).
        world.move_card(spell, world.players[p0].zone(ZONE_GRAVEYARD))
        executor.journal.emit_cast(spell, p0, "sorcery", ZONE_HAND, None)
        ctx = ctx_for(executor, source=spell, controller=p0)
        from_hand = FAtom(
            FAtomPred.CAST_THIS_TURN_FROM,
            who=ControllerRef.YOU,
            zone=Zone(ZoneKind.HAND, ControllerRef.YOU),
        )
        from_graveyard = FAtom(
            FAtomPred.CAST_THIS_TURN_FROM,
            who=ControllerRef.YOU,
            zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
        )
        self.assertTrue(eval_filter(from_hand, spell, ctx))
        self.assertFalse(eval_filter(from_graveyard, spell, ctx))
        self.assertFalse(
            eval_filter(
                from_hand, spell, ctx_for(executor, source=spell, controller=p1)
            )
        )  # not YOUR cast

    def test_entered_and_died_this_turn_handle_scoped(self) -> None:
        """ENTERED_THIS_TURN_FROM (Archfiend's Vessel's FOr twin) and
        DIED_THIS_TURN (Gadrak's Treasure count, the dies row): real MOVE_ZONE
        atoms journalled by the executor make each pred true for the
        card that moved/died and false for a card that merely sits in the
        same zone."""
        world, executor = self._world()
        p0 = world.player_order[0]
        executor.begin_turn(p0)
        risen = world.add_card(
            CardIdentity(oracle_id=_oid(94), name="Risen", type_line="Creature"),
            p0,
            ZONE_GRAVEYARD,
        )
        sitter = world.add_card(
            CardIdentity(oracle_id=_oid(95), name="Sitter", type_line="Creature"),
            p0,
            ZONE_GRAVEYARD,
        )
        executor.apply_effect(
            _atom(
                Verb.MOVE_ZONE,
                cards=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    UNIV,
                    zones=(Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),),
                ),
                destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            ),
            source=p0,
            controller=p0,
            bindings={"target": [risen]},
        )
        entered = FAtom(
            FAtomPred.ENTERED_THIS_TURN_FROM,
            zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
        )
        died = FAtom(FAtomPred.DIED_THIS_TURN)
        ctx = ctx_for(executor, source=p0, controller=p0)
        self.assertTrue(eval_filter(entered, risen, ctx))
        self.assertFalse(eval_filter(entered, sitter, ctx))
        self.assertFalse(eval_filter(died, risen, ctx))
        # now let it die (battlefield -> graveyard): the dies row appears
        executor.apply_effect(
            _atom(
                Verb.MOVE_ZONE,
                cards=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    UNIV,
                    zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),),
                ),
                destination=Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
            ),
            source=p0,
            controller=p0,
            bindings={"target": [risen]},
        )
        self.assertTrue(eval_filter(died, risen, ctx))
        self.assertFalse(eval_filter(died, sitter, ctx))

    def test_is_exiled_with_source_scoped_to_the_cause(self) -> None:
        """IS_EXILED_WITH_SOURCE (Idol of Endurance / Chandra, Heart of
        Fire; Necromentia's name-exile station's sibling): the WORLD half
        (in exile now) plus the HISTORY half (the SOURCE caused the
        exile — the journal's cause column). Another source says no, and the
        relationship PERSISTS across turns (it is not windowed)."""
        world, executor = self._world()
        stock_libraries(world)  # turns advance: no deck-out (CR 704.5b)
        p0 = world.player_order[0]
        executor.begin_turn(p0)
        idol = world.add_card(
            CardIdentity(oracle_id=_oid(96), name="Idol", type_line="Artifact"),
            p0,
            ZONE_BATTLEFIELD,
        )
        rival = world.add_card(
            CardIdentity(oracle_id=_oid(97), name="Rival", type_line="Artifact"),
            p0,
            ZONE_BATTLEFIELD,
        )
        purged = world.add_card(
            CardIdentity(oracle_id=_oid(98), name="Purged", type_line="Creature"),
            p0,
            ZONE_HAND,
        )
        executor.apply_effect(
            _atom(
                Verb.MOVE_ZONE,
                target=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    UNIV,
                    zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),),
                ),
                destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER),
            ),
            source=idol,
            controller=p0,
            bindings={"target": purged},
        )
        pred = FAtom(FAtomPred.IS_EXILED_WITH_SOURCE)
        self.assertTrue(
            eval_filter(pred, purged, ctx_for(executor, source=idol, controller=p0))
        )
        self.assertFalse(
            eval_filter(pred, purged, ctx_for(executor, source=rival, controller=p0))
        )
        executor.advance_turn()  # exile-with persists across turns
        self.assertTrue(
            eval_filter(pred, purged, ctx_for(executor, source=idol, controller=p0))
        )


class Round14eWorldPredTest(unittest.TestCase):
    """The WORLD-evaluated preds POWER_GE (Legion's Judgment "power 4 or
    greater" family) and CMC_LE (Eliminate / Idol of Endurance / Ugin's
    mana-value thresholds): pure world/identity reads, answered at EVERY
    eval entry point with no journal."""

    def _setup(self) -> tuple[GameWorld, Executor]:
        supply = get_supply("all")
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=3)
        executor = Executor(world)
        executor.attach_pool(supply.pool)
        return world, executor

    def test_power_ge_reads_live_power(self) -> None:
        world, executor = self._setup()
        p0 = world.player_order[0]
        anchor = world.add_card(card_id("Judge"), p0, ZONE_BATTLEFIELD)
        ctx = ctx_for(executor, source=anchor, controller=p0)
        pred = FAtom(pred=FAtomPred.POWER_GE, count=QConst(4))
        giant = world.add_card(
            card_id("Giant", power="4", toughness="4"), p0, ZONE_BATTLEFIELD
        )
        cat = world.add_card(
            card_id("Cat", power="1", toughness="1"), p0, ZONE_BATTLEFIELD
        )
        plot = world.add_card(card_id("Plot", type_line="Land"), p0, ZONE_BATTLEFIELD)
        self.assertTrue(eval_filter(pred, giant, ctx))  # 4 >= 4
        self.assertFalse(eval_filter(pred, cat, ctx))  # 1 < 4
        # no power is not "power 4 or greater" — the POWER_LE convention.
        self.assertFalse(eval_filter(pred, plot, ctx))

    def test_cmc_le_reads_identity_mana_value(self) -> None:
        world, executor = self._setup()
        p0 = world.player_order[0]
        anchor = world.add_card(card_id("Eliminator"), p0, ZONE_BATTLEFIELD)
        ctx = ctx_for(executor, source=anchor, controller=p0)
        pred = FAtom(pred=FAtomPred.CMC_LE, count=QConst(3))
        cheap = world.add_card(card_id("Cheap", cmc=3), p0, ZONE_BATTLEFIELD)
        big = world.add_card(card_id("Big", cmc=6), p0, ZONE_BATTLEFIELD)
        # A synthetic token identity carries no cmc: mana value 0, the
        # quantity._prop_value convention the QProp CMC field already uses.
        token = world.add_card(
            CardIdentity(oracle_id=_oid(501), name="Sparkie", type_line="Creature"),
            p0,
            ZONE_BATTLEFIELD,
        )
        self.assertTrue(eval_filter(pred, cheap, ctx))  # 3 <= 3
        self.assertFalse(eval_filter(pred, big, ctx))  # 6 > 3
        self.assertTrue(eval_filter(pred, token, ctx))  # cmc None == 0 <= 3
        self.assertFalse(
            eval_filter(pred, world.player_order[1], ctx)
        )  # non-card handle: no mana value

    def test_cmc_le_qx_outside_a_cast_stays_loud(self) -> None:
        # Ugin/Idol compile the threshold with {X}: QX rides the CAST's
        # declared value (CR 601.2f); unbound outside a cast it keeps
        # raising naming the quantity — no guessed zero for a filter pred.
        world, executor = self._setup()
        p0 = world.player_order[0]
        anchor = world.add_card(card_id("Anchor"), p0, ZONE_BATTLEFIELD)
        ctx = ctx_for(executor, source=anchor, controller=p0)
        critter = world.add_card(card_id("Critter", cmc=2), p0, ZONE_BATTLEFIELD)
        with self.assertRaises(NotImplementedError):
            eval_filter(FAtom(pred=FAtomPred.CMC_LE, count=QX()), critter, ctx)


class Round14fSurfaceTest(unittest.TestCase):
    """KEYWORD_HAS (the LIVE keyword oracle: printed ∪ granted − lost, the
    same registry combat legality calls), EachPlayer (per-player
    sub-executions with the CONTROLLER rotated — the templates compile the
    inner effect YOU-relative), and the Chandra permission row's
    CROSS-resolution population read (the compiled row emits the
    IS_EXILED_WITH_SOURCE population, so a LATER activation answers from
    the journal, not a per-resolution register)."""

    def _world(self) -> tuple[GameWorld, Executor]:
        supply = get_supply("all")
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=5)
        executor = Executor(world)
        executor.attach_pool(supply.pool)
        return world, executor

    # ------------------------------------------------------------- KEYWORD_HAS

    def test_keyword_has_filter_uses_the_live_oracle(self) -> None:
        world, executor = self._world()
        p0, p1 = world.player_order
        anchor = world.add_card(card_id("Afoul Anchor"), p0, ZONE_BATTLEFIELD)
        ctx = ctx_for(executor, source=anchor, controller=p0)
        pred = FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING)
        angel = world.add_card(
            CardIdentity(
                oracle_id=_oid(601),
                name="Printed Angel",
                type_line="Creature",
                keywords=("FLYING",),
            ),
            p0,
            ZONE_BATTLEFIELD,
        )
        bat = world.add_card(card_id("Grounded Bat"), p0, ZONE_BATTLEFIELD)
        # Registry projections rebuild at op boundaries (the settle point);
        # this test seeds the world outside ops, so fold once — the same
        # recompute verbs.py's live-permission refresh performs.
        executor.layers.recompute()
        self.assertTrue(eval_filter(pred, angel, ctx))  # printed
        self.assertFalse(eval_filter(pred, bat, ctx))  # absent characteristic
        # a player seat has no keywords (Run Afoul's CHOOSE pool over
        # BATTLEFIELD never admits one)
        self.assertFalse(eval_filter(pred, p1, ctx))
        # LIVE reading: a granted keyword flips membership — a printed-only
        # guess would be silently wrong here.
        executor.apply_effect(
            _atom(
                Verb.GRANT_ABILITY,
                target=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    FAnd(()),
                    zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
                ),
                ability=KeywordAbility(keyword=Keyword.FLYING),
                duration=DurationEot(),
            ),
            source=anchor,
            controller=p0,
            bindings={"target": [bat]},
        )
        self.assertTrue(eval_filter(pred, bat, ctx))

    def test_keyword_has_bare_ctx_stays_loud(self) -> None:
        # The no-half-preds rule: a context with no layer
        # registry raises naming the pred — never a printed-only guess.
        world, executor = self._world()
        p0 = world.player_order[0]
        creature = world.add_card(card_id("Bare Bat"), p0, ZONE_BATTLEFIELD)
        bare = ExecCtx(
            world=world,
            ledger=executor.ledger,
            controller=p0,
            source=p0,
            bindings={},
            decisions=(),
        )
        self.assertIsNone(bare.layers)
        with self.assertRaises(NotImplementedError) as cm:
            eval_filter(
                FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING),
                creature,
                bare,
            )
        self.assertIn("KEYWORD_HAS", str(cm.exception))

    # ------------------------------------------------------------ EachPlayer

    def test_each_player_rotates_the_controller(self) -> None:
        # YOU-relative inner effect: the ROTATION is the rebinding. The
        # opponent draws, the controller does not.
        world, executor = self._world()
        p0, p1 = world.player_order
        anchor = world.add_card(card_id("Goremand Anchor"), p0, ZONE_BATTLEFIELD)
        # Both seats hold library cards: a draw is only countable if a
        # BROKEN rotation drawing to the controller would also be visible.
        world.add_card(card_id("P0 Top"), p0, ZONE_LIBRARY)
        world.add_card(card_id("P1 Top"), p1, ZONE_LIBRARY)
        hands = (
            len(world.players[p0].zone(ZONE_HAND).entries),
            len(world.players[p1].zone(ZONE_HAND).entries),
        )
        executor.apply_effect(
            EachPlayer(
                ref=ControllerRef.ALL_OPPONENTS,
                effect=_atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1)),
            ),
            source=anchor,
            controller=p0,
        )
        self.assertEqual(
            len(world.players[p0].zone(ZONE_HAND).entries), hands[0]
        )  # YOU was NOT the controller here
        self.assertEqual(len(world.players[p1].zone(ZONE_HAND).entries), hands[1] + 1)

    def test_each_player_forwards_the_decision_pool(self) -> None:
        # The per-op positional supply rides across the sub-contexts:
        # ref=ANY asks once per seat (seat order), one pool answers every
        # station in ask order — byte-identical to single-context
        # consumption, and the cursor write-back keeps later asks aligned.
        world, executor = self._world()
        p0, p1 = world.player_order
        anchor = world.add_card(card_id("Guildgate Anchor"), p0, ZONE_BATTLEFIELD)
        executor.apply_effect(
            EachPlayer(
                ref=ControllerRef.ANY,
                effect=OptionalEffect(
                    _atom(
                        Verb.GAIN_LIFE,
                        controller=ControllerRef.YOU,
                        amount=QConst(1),
                    )
                ),
            ),
            source=anchor,
            controller=p0,
            decisions=("fire", "fire"),
        )
        self.assertEqual(world.players[p0].life, 21)
        self.assertEqual(world.players[p1].life, 21)

    def test_goremand_face_each_opponent_sacrifices_theirs(self) -> None:
        # The REAL compiled node (Goremand's own tree):
        # each opponent's creature dies, the controller's survives.
        supply = get_supply("all")
        record = _record_named(supply, "Goremand")
        each = None
        for ability in record.abilities:
            if isinstance(ability, TriggeredAbility) and isinstance(
                ability.effect, EachPlayer
            ):
                each = ability.effect
        self.assertIsNotNone(each, "Goremand's ETB must compile an EachPlayer")
        assert each is not None  # pyright narrowing for the live run below
        world, executor = self._world()
        p0, p1 = world.player_order
        mine = world.add_card(card_id("My Cat"), p0, ZONE_BATTLEFIELD)
        theirs = world.add_card(card_id("Their Wolf"), p1, ZONE_BATTLEFIELD)
        anchor = world.add_card(card_id("Goremand ETB"), p0, ZONE_BATTLEFIELD)
        executor.apply_effect(each, source=anchor, controller=p0)
        self.assertEqual(world.zone_of(theirs).kind, ZONE_GRAVEYARD)
        self.assertEqual(world.zone_of(mine).kind, ZONE_BATTLEFIELD)

    # ---------------------------------------- Chandra cross-resolution read

    def test_chandra_permission_population_answers_from_the_journal(self) -> None:
        # A card exiled by the source in an EARLIER resolution is in the
        # permission's population when a FRESH execution (fresh bindings
        # dict, NO result register — the situation a later activation is
        # in) resolves the compiled row's Selector.
        world, executor = self._world()
        p0, _p1 = world.player_order
        chandra = world.add_card(
            card_id("Chandra, Heart of Fire"), p0, ZONE_BATTLEFIELD
        )
        exiled = world.add_card(card_id("Kiln Spawn"), p0, ZONE_LIBRARY)
        top = world.players[p0].zone(ZONE_LIBRARY).entries[-1]
        self.assertEqual(top, exiled)
        executor.apply_effect(
            _atom(
                Verb.MOVE_ZONE,
                target=Selector(
                    QConst(1),
                    SelectorMode.CHOOSE,
                    FAnd(()),
                    zones=(
                        Zone(ZoneKind.LIBRARY, ControllerRef.YOU, ZonePosition.TOP),
                    ),
                ),
                destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER),
            ),
            source=chandra,
            controller=p0,
        )
        self.assertEqual(world.zone_of(top).kind, ZONE_EXILE)
        selector = Selector(
            QUnbounded(),
            SelectorMode.CHOOSE,
            FAtom(pred=FAtomPred.IS_EXILED_WITH_SOURCE),
            zones=(Zone(ZoneKind.EXILE, ControllerRef.YOU),),
        )  # the shape the B4-cast-them-this-turn template compiles
        ctx = ctx_for(executor, source=chandra, controller=p0)
        self.assertEqual(resolve_selector(selector, ctx), [top])
        # and the read is CAUSE-scoped: another source's exiles are not it
        other = world.add_card(card_id("Idol of Endurance"), p0, ZONE_BATTLEFIELD)
        rival = world.add_card(card_id("Rival Card"), p0, ZONE_LIBRARY)
        executor.apply_effect(
            _atom(
                Verb.MOVE_ZONE,
                target=Selector(
                    QConst(1),
                    SelectorMode.CHOOSE,
                    FAnd(()),
                    zones=(
                        Zone(ZoneKind.LIBRARY, ControllerRef.YOU, ZonePosition.TOP),
                    ),
                ),
                destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER),
            ),
            source=other,
            controller=p0,
        )
        self.assertEqual(world.zone_of(rival).kind, ZONE_EXILE)
        self.assertEqual(resolve_selector(selector, ctx), [top])


class Round16eControlTest(unittest.TestCase):
    """Control overlay and Aura lifecycle: one-turn steal, enchant-the-
    creature cast ordering (CR 303.4a/608.2a), the no-legal-target cast
    gate (CR 601.2e), the aura-death control return, and the unattached-
    aura state check (CR 704.5q)."""

    def _world(self, seed: int = 7) -> tuple[GameWorld, Executor]:
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=seed)
        return world, Executor(world)

    def _arm(self, world: GameWorld, executor: Executor, p0: Handle) -> None:
        for key in ("W", "U", "B", "R", "G", "C"):
            world.players[p0].mana_pool[key] = 20
        world.active_player = p0
        executor.turn_open = True
        executor.phase = "FIRST_MAIN"

    def test_traitorous_greed_steals_until_end_of_turn(self) -> None:
        # GAIN_CONTROL with DurationEot: the overlay routes control, the
        # EoT expiry hands it back. The real compiled tree's ADD_MANA
        # (color ANY) is the only primed-decision consumer — both CHOOSE
        # atoms auto-force off the single-target designation.
        supply = get_supply("all")
        record = _record_named(supply, "Traitorous Greed")
        world, executor = self._world()
        executor.attach_pool(supply.pool)
        p0, p1 = world.player_order
        victim = world.add_card(
            CardIdentity(oracle_id=_oid(301), name="Victim", type_line="Creature"),
            p1,
            ZONE_BATTLEFIELD,
        )
        spell = world.add_card(identity_of(record), p0, ZONE_HAND)
        self._arm(world, executor, p0)
        # "Add one mana of any color" offers the five colors only (CR 105.1,
        # 106.1a); colorless is not a color.
        cast(executor, p0, spell, targets=(victim,), decisions=("R",))
        self.assertEqual(executor.controller_of(victim), p0)
        executor.end_turn()
        self.assertEqual(executor.controller_of(victim), p1)

    def test_enthralling_hold_gate_attach_and_death_return(self) -> None:
        # The synthesized Enchant slot: no battlefield creature -> the
        # legal_casts row disappears (CR 601.2e); with one -> cast puts
        # the aura onto the battlefield ATTACHED (CR 303.4a) before the
        # effect runs, the GAIN_CONTROL static steals the creature, and
        # killing the aura drops the attachment edge and returns control.
        supply = get_supply("all")
        record = _record_named(supply, "Enthralling Hold")
        world, executor = self._world(9)
        executor.attach_pool(supply.pool)
        p0, p1 = world.player_order
        aura = world.add_card(identity_of(record), p0, ZONE_HAND)
        self._arm(world, executor, p0)
        self.assertTrue(is_aura_spell(world, aura))
        # ENCHANT is an identity keyword and the cast gate is loud:
        reason, *_ = spell_castable(executor, p0, aura)
        self.assertIsNotNone(reason)
        assert reason is not None  # pyright narrowing for the live run below
        self.assertIn("aura_no_legal_target", reason)
        victim = world.add_card(
            CardIdentity(oracle_id=_oid(302), name="Victim", type_line="Creature"),
            p1,
            ZONE_BATTLEFIELD,
        )
        # The Aura's "You can't choose an untapped creature as this spell's
        # target as you cast it" (CR 113.6e): the victim must be tapped to be
        # a legal target.
        world.cards[victim].tapped = True
        cast(executor, p0, aura, targets=(victim,))
        self.assertEqual(world.zone_of(aura).kind, ZONE_BATTLEFIELD)
        self.assertEqual(executor.attachments.get(aura), victim)
        self.assertEqual(executor.controller_of(victim), p0)
        # DESTROY the aura (a placeholder TARGET node fed by bindings —
        # the verb's own death pipeline, not another spell):
        executor.apply_effect(
            _atom(
                Verb.DESTROY,
                target=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    FAnd(()),
                    zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
                ),
            ),
            source=victim,
            controller=p1,
            bindings={"target": [aura]},
        )
        self.assertEqual(world.zone_of(aura).kind, ZONE_GRAVEYARD)
        self.assertIsNone(executor.attachments.get(aura))
        self.assertEqual(executor.controller_of(victim), p1)

    def test_unattached_aura_state_check_graveyard(self) -> None:
        # CR 704.5q: an aura on the battlefield not attached to anything
        # (its host left from under it, or it was somehow put there
        # floating) is put into its owner's graveyard by the next state
        # check batch. Equipment carry EQUIP, not ENCHANT, so they are
        # NOT swept — only is_aura_spell cards are.
        supply = get_supply("all")
        record = _record_named(supply, "Enthralling Hold")
        world, executor = self._world(13)
        executor.attach_pool(supply.pool)
        p0, _p1 = world.player_order
        aura = world.add_card(identity_of(record), p0, ZONE_BATTLEFIELD)
        executor._settle()
        self.assertEqual(world.zone_of(aura).kind, ZONE_GRAVEYARD)


_SNARE_OID = "00000000-1111-2222-3333-666666666666"


class AuraEffectlessLegalityTest(unittest.TestCase):
    """An aura whose SpellAbility carries NO effect (Bubble Snare: its
    gameplay rides entirely on sibling abilities) still gets the synthesized
    ENCHANT designation from :func:`spell_target_slots`, so the cast lane
    never sees a targetless spell. Pins:
      * an effectless aura harvests exactly one REQUIRED (min=1)
        synthetic enchant slot;
      * no legal designee => spell_castable refuses AND a direct cast
        raises before the stack push — designation refusal never casts
        (refusal-consistency law);
      * the policy's ask (select_targets) declines the empty population
        and, with a designee, designates BEFORE resolution and the aura
        resolves ATTACHED."""

    @staticmethod
    def _snare_pool() -> PoolCompile:
        record = CardRecord(
            oracle_id=_SNARE_OID,
            name="Effectless Snare",
            type_line="Enchantment — Aura",
            types=("Enchantment",),
            subtypes=("Aura",),
            supertypes=(),
            colors=("U",),
            color_identity=frozenset({"U"}),
            mana_cost=None,
            mana_value=1,
            power=None,
            toughness=None,
            loyalty=None,
            keywords=(KeywordAbility(keyword=Keyword.ENCHANT, params=()),),
            # THE specimen shape: SpellAbility with NO effect (Bubble
            # Snare's whole rules body compiles to sibling ETB/static
            # abilities; the SpellAbility stays effect=None).
            abilities=(SpellAbility(kind=SpellKind.ENCHANTMENT, effect=None),),
            is_token=False,
        )
        return PoolCompile(
            cards={_SNARE_OID: record},
            emblems={},
            results={
                _SNARE_OID: CompileResult(
                    card=record,
                    legality=LegalityFlags(format_legal=True, engine_supported=True),
                )
            },
            summary={},
        )

    def _armed(self, seed: int = 7):
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=seed)
        executor = Executor(world)
        executor.attach_pool(self._snare_pool())
        p0, _p1 = world.player_order
        for key in ("W", "U", "B", "R", "G", "C"):
            world.players[p0].mana_pool[key] = 20
        world.active_player = p0
        executor.turn_open = True
        executor.phase = "FIRST_MAIN"
        record = executor.binder.records[_SNARE_OID]
        node = next(a for a in record.abilities if isinstance(a, SpellAbility))
        aura = world.add_card(identity_of(record), p0, ZONE_HAND)
        return world, executor, p0, node, aura

    def test_effectless_aura_slot_required_refusal_never_casts(self) -> None:
        world, executor, p0, node, aura = self._armed()
        self.assertTrue(is_aura_spell(world, aura))
        # The harvest pin: zero-effect aura SpellAbility still yields the
        # one REQUIRED enchant slot (min=1).
        slots = spell_target_slots(executor, node, spell_handle=aura, seat=p0)
        self.assertEqual(len(slots), 1)
        self.assertTrue(slots[0].synthetic)
        self.assertEqual((slots[0].min_count, slots[0].max_count), (1, 1))
        self.assertEqual(slots[0].candidates, ())  # empty battlefield
        # Legality refuses the cast (CR 601.2e), the policy's ask declines
        # it (refusal-consistency), and a direct zero-target cast raises
        # BEFORE the stack push — no frame, no floating aura.
        reason, *_ = spell_castable(executor, p0, aura)
        self.assertIsNotNone(reason)
        assert reason is not None  # pyright narrowing
        self.assertIn("aura_no_legal_target", reason)
        self.assertIsNone(RandomPolicy(0).select_targets(slots))
        with self.assertRaises(ValueError) as cm:
            cast(executor, p0, aura)
        self.assertIn("aura_no_legal_target", str(cm.exception))
        self.assertEqual(world.zone_of(aura).kind, ZONE_HAND)
        self.assertEqual(executor.stack.frames, [])

    def test_effectless_aura_designates_before_resolution(self) -> None:
        world, executor, p0, node, aura = self._armed(11)
        host = world.add_card(
            CardIdentity(oracle_id=_oid(311), name="Host", type_line="Land"),
            p0,
            ZONE_BATTLEFIELD,
        )
        # With a designee the slot populates, legality clears, the ASK
        # answers from the slot BEFORE the cast, and resolution attaches
        # (CR 303.4a).
        slots = spell_target_slots(executor, node, spell_handle=aura, seat=p0)
        self.assertEqual(slots[0].candidates, (host,))
        self.assertIsNone(spell_castable(executor, p0, aura)[0])
        picked = RandomPolicy(0).select_targets(slots)
        self.assertEqual(picked, (host,))
        assert picked is not None  # pyright narrowing for the cast below
        cast(executor, p0, aura, targets=picked)
        self.assertEqual(world.zone_of(aura).kind, ZONE_BATTLEFIELD)
        self.assertEqual(executor.attachments.get(aura), host)


class AuraEnchantRestrictionTest(unittest.TestCase):
    """"Enchant creature" limits what an Aura spell can target (CR 303.4a, 702.5a). An
    Aura cast through the effect-less carrier has no effect tree to read the restriction
    from, so the compiled ENCHANT keyword carries the Enchant line's filter and the
    enchant slot reads it: Dub, Capture Sphere or Bubble Snare is never cast onto a land."""

    def _slot_names(self, set_code: str, aura_name: str) -> set[str]:
        supply = get_supply("all", set_code)
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=7)
        executor = Executor(world)
        executor.attach_pool(supply.pool)
        p0, p1 = world.player_order
        by_name = {meta.name: oid for oid, meta in supply.metas.items()}
        board = {"Island": (p0, p1), "Short Sword": (p0, p1)} if set_code == "M21" else {"Island": (p0, p1)}
        for name, seats in board.items():
            for seat in seats:
                world.add_card(identity_of(supply.pool.results[by_name[name]].card), seat, ZONE_BATTLEFIELD)
        for seat, label in ((p0, "Own"), (p1, "Opp")):
            world.add_card(card_id(f"{label} Bear", type_line="Creature — Bear", power="2", toughness="2"),
                           seat, ZONE_BATTLEFIELD)
        record = supply.pool.results[by_name[aura_name]].card
        aura = world.add_card(identity_of(record), p0, ZONE_HAND)
        node = next(a for a in record.abilities if isinstance(a, SpellAbility))
        (slot,) = spell_target_slots(executor, node, spell_handle=aura, seat=p0)
        return {
            f"{'own' if world.controller_of(h) == p0 else 'opp'} {world.cards[h].identity.name}"
            for h in slot.candidates
        }

    def test_every_m21_aura_keyword_carries_its_enchant_filter(self) -> None:
        cards = get_supply("all", "M21").pool.results.values()
        auras = {
            res.card.name: next(ka for ka in res.card.keywords if ka.keyword is Keyword.ENCHANT)
            for res in cards
            if any(ka.keyword is Keyword.ENCHANT for ka in res.card.keywords)
        }
        self.assertEqual(len(auras), 10)
        self.assertTrue(all(len(ka.params) == 1 for ka in auras.values()), auras)
        self.assertEqual(auras["Dub"].params, (FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),))
        self.assertEqual(auras["Faith's Fetters"].params, (FAtom(pred=FAtomPred.IS_PERMANENT),))

    def test_carrier_auras_offer_only_legal_hosts(self) -> None:
        creatures = {"own Own Bear", "opp Opp Bear"}
        for aura in ("Capture Sphere", "Demonic Embrace", "Dub", "Furor of the Bitten",
                     "Infernal Scarring", "Light of Promise", "Rousing Read"):
            self.assertEqual(self._slot_names("M21", aura), creatures, aura)
        # "Enchant creature you control"
        self.assertEqual(self._slot_names("M21", "Setessan Training"), {"own Own Bear"})
        # "Enchant permanent" keeps every permanent
        self.assertEqual(len(self._slot_names("M21", "Faith's Fetters")), 6)

    def test_bubble_snare_is_fixed_by_the_same_change(self) -> None:
        self.assertEqual(self._slot_names("ZNR", "Bubble Snare"), {"own Own Bear", "opp Opp Bear"})


class TormodsCryptTargetPlayerTest(unittest.TestCase):
    """"Exile target player's graveyard" names the player only inside a
    selector's zone, Zone(GRAVEYARD, TARGET_PLAYER). "target player" is a
    target (CR 115.1), so the activation lane's scan reads that zone and
    builds the synthesized player slot, which offers every player, the
    caster included."""

    def _armed(self):
        supply = get_supply("all", "M21")
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=7)
        executor = Executor(world)
        executor.attach_pool(supply.pool)
        p0, p1 = world.player_order
        record = next(r.card for r in supply.pool.results.values() if r.card.name == "Tormod's Crypt")
        crypt = world.add_card(identity_of(record), p0, ZONE_BATTLEFIELD)
        executor.attach_card(crypt, record)
        mine = world.add_card(card_id("Own Dead", power="1", toughness="1"), p0, ZONE_GRAVEYARD)
        theirs = [
            world.add_card(card_id(f"Opp Dead {i}", power="1", toughness="1"), p1, ZONE_GRAVEYARD)
            for i in range(2)
        ]
        world.active_player = p0
        executor.turn_open = True
        executor.phase = "FIRST_MAIN"
        return world, executor, p0, p1, record, crypt, mine, theirs

    def test_the_zone_read_opens_one_required_player_slot(self) -> None:
        _world, executor, p0, p1, record, crypt, _mine, _theirs = self._armed()
        (slot,) = activation_target_slots(executor, record.abilities[0].effect, source=crypt, seat=p0)
        self.assertTrue(slot.synthetic)
        self.assertEqual((slot.min_count, slot.max_count), (1, 1))
        # "target player" is any player (CR 115.1).
        self.assertEqual(slot.candidates, (p0, p1))

    def test_the_designated_activation_exiles_exactly_that_graveyard(self) -> None:
        world, executor, p0, _p1, record, crypt, mine, theirs = self._armed()
        (slot,) = activation_target_slots(executor, record.abilities[0].effect, source=crypt, seat=p0)
        # The slot names both seats; designate the opponent.
        self.assertIn(_p1, slot.candidates)
        activate(executor, crypt, 0, seat=p0, targets=(_p1,))
        self.assertEqual([world.zone_of(h).kind for h in theirs], [ZONE_EXILE, ZONE_EXILE])
        self.assertEqual(world.zone_of(mine).kind, ZONE_GRAVEYARD)
        self.assertEqual(world.zone_of(crypt).kind, ZONE_GRAVEYARD)  # sacrificed as the cost


# ---------------------------------------------------------------------------
# Stall rule (CR 104.4b): a world fingerprint that repeats exactly across
# REPEAT_ROUNDS consecutive per-seat round observations ends the game early
# as a STALL draw.  The synthetic world below is the canonical pathological
# loop: a 0-mana creature whose ETB shuffles itself back into its owner's
# library.  Every action cycle leaves the world exactly as it found it —
# life, battlefield, zone sizes all invariant — except for library *order*,
# which is deliberately excluded from the fingerprint (seeded shuffles
# rewrite order while making zero progress).


_STALL_OID = "00000000-1111-2222-3333-444444444444"


class StallRuleTest(unittest.TestCase):
    """The games/terminal-lane stall detector."""

    @staticmethod
    def _loop_supply() -> Supply:
        etb = TriggeredAbility(
            event=ZoneChangeEvent(
                from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
                to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                subject=FAtom(FAtomPred.IS_SOURCE),
            ),
            condition=None,
            effect=Seq(
                (
                    _atom(
                        Verb.MOVE_ZONE,
                        cards=Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            UNIV,
                            zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
                            referent="event",
                        ),
                        destination=Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
                    ),
                    _atom(Verb.SHUFFLE, zone=Zone(ZoneKind.LIBRARY, ControllerRef.YOU)),
                )
            ),
        )
        record = CardRecord(
            oracle_id=_STALL_OID,
            name="Stall Loop Drake",
            type_line="Creature",
            types=("Creature",),
            subtypes=(),
            supertypes=(),
            colors=(),
            color_identity=frozenset(),
            mana_cost=None,
            mana_value=0,
            power=QConst(1),
            toughness=QConst(1),
            loyalty=None,
            keywords=(),
            abilities=(SpellAbility(kind=SpellKind.CREATURE, effect=None), etb),
            is_token=False,
        )
        pool = PoolCompile(
            cards={_STALL_OID: record},
            emblems={},
            results={
                _STALL_OID: CompileResult(
                    card=record,
                    legality=LegalityFlags(format_legal=True, engine_supported=True),
                )
            },
            summary={},
        )
        metas = {
            _STALL_OID: CardMeta(
                oracle_id=_STALL_OID,
                name="Stall Loop Drake",
                type_line="Creature",
                mana_value=0,
                is_land=False,
                produces_mana=False,
                has_spell_node=True,
                engine_supported=True,
                is_basic=False,
            )
        }
        return Supply(
            mode="stall-synthetic",
            pool=pool,
            metas=metas,
            deckable=(_STALL_OID,),
            engine_ids=frozenset({_STALL_OID}),
            playable_engine_ids=frozenset({_STALL_OID}),
            pool_seconds=0.0,
        )

    @staticmethod
    def _run_loop_game(seed: int = 0) -> Game:
        supply = StallRuleTest._loop_supply()
        deck = (_STALL_OID,) * DECK_SIZE
        game = _setup_game(seed, supply, (deck, deck))
        _play(game, _LoopDeckPolicy(seed), game.world.player_order, TURN_CAP)
        return game

    def test_infinite_loop_stalls_early(self) -> None:
        game = self._run_loop_game()
        self.assertTrue(game.reason.startswith("STALL"), game.reason)
        # Observed: detected on the 5th turn (3rd observation of the active
        # seat).  Bound: an active-seat streak needs REPEAT_ROUNDS of that
        # seat's turns plus the interleaved opponent turns.
        self.assertLessEqual(game.turns, 2 * REPEAT_ROUNDS + 2)
        self.assertLess(game.turns, TURN_CAP)
        life = [game.world.players[s].life for s in game.world.player_order]
        self.assertEqual(life, [20, 20])  # zero-progress: nobody was hurt

    def test_stall_break_row_recorded_in_journal(self) -> None:
        game = self._run_loop_game()
        rows = [r for r in game.executor.journal.dump() if r[1] == KIND_STALL_BREAK]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][4], "STALL")
        self.assertEqual(rows[0][5], f"({REPEAT_ROUNDS},)")

    def test_long_decisive_corpus_game_untouched(self) -> None:
        # Seed 73, full engine pool: a long decisive corpus game. Its world
        # genuinely changes every round, so the stall rule must not fire. Any
        # engine or policy change that shifts the seeded trajectory moves the
        # pinned turn count and loser: re-pin them after a double-run replay
        # check (same fingerprint and digest), never by loosening the stall
        # assertion.
        game = play_game(73, "all", SMOKE_DECK_PAIRS)
        self.assertFalse(game.reason.startswith("STALL"), game.reason)
        # 2026-11-11: 51 -> 59 when the response windows went (DESIGN_PRIORITY
        # §11 5b-1; the random players answered them), then 46 with a new loser
        # when the loop asked at every priority point and the random player
        # stopped tapping mana by hand (5b-2); double-run identical each time.
        self.assertEqual(game.turns, 46)
        self.assertEqual(game.reason, "game over: player:0(life<=0)")

    def test_stall_run_is_deterministic(self) -> None:
        first = self._run_loop_game()
        second = self._run_loop_game()
        self.assertEqual(first.reason, second.reason)
        self.assertEqual(first.turns, second.turns)
        self.assertEqual(
            first.executor.state_fingerprint(), second.executor.state_fingerprint()
        )

    def test_fingerprint_is_pure_and_seat_symmetric(self) -> None:
        # Fresh world: both seats' fingerprints exist, are tuples, and equal
        # fingerprints mean equal lives (sanity on the pure helper).
        supply = self._loop_supply()
        deck = (_STALL_OID,) * DECK_SIZE
        game = _setup_game(0, supply, (deck, deck))
        first = _stall_fingerprint(game.executor)
        self.assertIsInstance(first, tuple)
        self.assertEqual(first, _stall_fingerprint(game.executor))


class ChooseNamePoolTest(unittest.TestCase):
    """A dealt game names a card from the format's pool, every card the deck builder could have
    used, never from the world: the world's names would put the cards of hidden zones (the
    opponent's hand and library) into the menu, and its order and size would reveal them."""

    def vocab(self, opponent_card: str, chooser: str = "Runed Halo") -> tuple[str, ...]:
        supply = get_supply("castable")
        oid = {m.name: o for o, m in supply.metas.items()}
        decks = (
            (oid[chooser],) + (oid["Plains"],) * (DECK_SIZE - 1),
            (oid[opponent_card],) * 4 + (oid["Island"],) * (DECK_SIZE - 4),
        )
        game = _setup_game(7, supply, decks)
        world = game.world
        source = next(h for h, c in world.cards.items() if c.identity.name == chooser)
        choose = next(n for a in supply.pool.results[oid[chooser]].card.abilities for n in walk(a)
                      if isinstance(n, Atom) and n.verb is Verb.CHOOSE_NAME)
        seen: list[tuple[str, ...]] = []
        game.executor.decisions.provider = lambda vocab, what: seen.append(vocab) or vocab[0]
        game.executor.apply_effect(choose, source=source, controller=world.player_order[0])
        return seen[0]

    def test_the_names_are_the_deckable_pool_whatever_is_hidden(self):
        supply = get_supply("castable")
        pool = tuple(sorted({supply.metas[o].name for o in supply.deckable}))
        self.assertEqual(self.vocab("Shock"), pool)
        self.assertEqual(self.vocab("Cancel"), pool)  # the opponent's library changes nothing

    def test_a_name_filter_reads_the_printed_card(self):
        # Necromentia: "Choose a card name other than a basic land card name."
        vocab = self.vocab("Shock", chooser="Necromentia")
        self.assertNotIn("Plains", vocab)
        self.assertNotIn("Island", vocab)
        self.assertIn("Necromentia", vocab)
        self.assertIn("Shock", vocab)


class _PriorityLog:
    """A ``_play`` policy that never acts and logs each priority decision it is asked for as
    (turn, seat, step). An ask takes DECLINE when offered (nobody attacks), else its first word."""

    def __init__(self) -> None:
        self.decisions: list[tuple[int, Handle, str | None]] = []

    def answer(self, vocab: tuple[str, ...], what: str) -> str:
        return "DECLINE" if "DECLINE" in vocab else vocab[0]

    def take_priority(self, game: Game, seat: Handle) -> bool:
        self.decisions.append((game.world.turn, seat, game.executor.phase))
        return False


class PriorityLoopTest(unittest.TestCase):
    """CR 117: the turn loop gives priority in every step but the untap step and a quiet cleanup
    step, to the active player first (117.3a) and then to the other (117.3d); with no attackers
    there are no blockers or damage steps (508.8); and a game stopped at a priority point resumes
    there, never replaying a step (the search resumes its forks so)."""

    @staticmethod
    def _game() -> Game:
        supply = get_supply("castable")
        return _setup_game(5, supply, deal_decks(5, SMOKE_DECK_PAIRS, supply))

    @staticmethod
    def _combats(game: Game) -> int:
        return sum(
            1 for e in game.executor.journal.events
            if e.kind == "TURN_PHASE" and e.phase[0] == "COMBAT"
        )

    def test_every_step_with_priority_asks_the_active_player_first(self) -> None:
        game = self._game()
        log = _PriorityLog()
        _play(game, log, game.world.player_order, turn_cap=2)
        p0, p1 = game.world.player_order
        steps = ("UPKEEP", "DRAW", "FIRST_MAIN", "COMBAT", "DECLARE_ATTACKERS", "END_OF_COMBAT",
                 "SECOND_MAIN", "END_TURN")
        expected = [
            (turn, seat, step)
            for turn, active, other in ((1, p0, p1), (2, p1, p0))
            for step in steps
            if not (turn == 1 and step == "DRAW")  # CR 103.8a: no draw on the first turn
            for seat in (active, other)
        ]
        self.assertEqual(log.decisions, expected)

    def test_a_game_stopped_at_a_priority_point_resumes_there(self) -> None:
        game = self._game()
        p1 = game.world.player_order[1]
        _play(game, _PriorityLog(), game.world.player_order, turn_cap=10,
              stop_after=lambda g, b: b == "priority" and g.world.turn == 2
              and g.executor.phase == "SECOND_MAIN")
        self.assertEqual((game.world.turn, game.executor.phase), (2, "SECOND_MAIN"))
        self.assertEqual(self._combats(game), 2)
        log = _PriorityLog()
        _play(game, log, game.world.player_order, turn_cap=3, resumed=True)
        self.assertEqual(log.decisions[0], (2, p1, "SECOND_MAIN"))  # the same point, asked again
        self.assertEqual(self._combats(game), 3)  # turn 3's combat only
        self.assertEqual(game.turns, 3)


class ForkResumeTest(unittest.TestCase):
    """DESIGN_PRIORITY §4.3: a game's state, the step and priority included, lives in objects a
    deep copy takes whole, so a game stopped at any priority point and copied plays on exactly as
    the original does, and as the same game never stopped."""

    def test_a_copy_at_a_priority_point_plays_on_identically(self) -> None:
        import copy

        supply = get_supply("verified")
        for seed, stop_at in ((3, 57), (4, 211), (5, 150)):
            def deal(seed: int = seed) -> Game:
                return _setup_game(seed, supply, deal_decks(seed, SMOKE_DECK_PAIRS, supply, "coherent"))

            whole = deal()
            _play(whole, RandomPolicy(seed), whole.world.player_order, TURN_CAP)
            game, policy = deal(), RandomPolicy(seed)
            seen = [0]

            def stop(_g, boundary, seen=seen, stop_at=stop_at) -> bool:
                seen[0] += boundary == "priority"
                return boundary == "priority" and seen[0] == stop_at

            _play(game, policy, game.world.player_order, TURN_CAP, stop_after=stop)
            self.assertEqual(seen[0], stop_at, "the game ended before the stop")
            twin, twin_policy = copy.deepcopy((game, policy))
            for g, p in ((game, policy), (twin, twin_policy)):
                _play(g, p, g.world.player_order, TURN_CAP, resumed=True)
            for g in (game, twin):
                self.assertEqual((g.digest, g.reason, g.turns), (whole.digest, whole.reason, whole.turns))
                self.assertEqual(g.executor.state_fingerprint(), whole.executor.state_fingerprint())


class _LoopDeckPolicy(RandomPolicy):
    """Deterministic policy: each turn, cast exactly one legal spell, in the
    first main phase; pass everywhere else.

    RandomPolicy's dice would take an expected ~250 turns per candidate
    cast window here, making the stall statistically unreachable inside the
    cap; a fixed single-cast policy exercises the detector squarely.
    """

    cast_turn = -1

    def take_priority(self, game: Game, seat: Handle) -> bool:
        executor = game.executor
        turn = game.world.turn
        if executor.phase != "FIRST_MAIN" or not sorcery_timing(executor, seat) or self.cast_turn == turn:
            return False
        self.turn = turn
        self.seat_index = game.world.player_order.index(seat)
        rows = [r for r in menu(executor, seat) if r.kind == "cast"]
        if not rows:
            return False
        self.cast_turn = turn
        return self.play_row(game, seat, rows[0])


def _oid(n: int) -> str:
    return f"{n:08x}-1111-2222-3333-444444444444"


if __name__ == "__main__":
    unittest.main()


class EffectEnteredPermanentTest(unittest.TestCase):
    """A dealt card that an effect puts onto the battlefield (a fetched or ramped land, Risen
    Reef's land, a reanimated card never on the battlefield) has its abilities: ``_setup_game``
    attaches the pool before the decks are dealt, so no library card has a bound record, and
    battlefield entry binds by oracle id, as graveyard entry does."""

    def test_a_land_put_onto_the_battlefield_from_the_library_taps_for_mana(self) -> None:
        from MTG_bot.core.executor.legality import _mana_tap_options

        supply = get_supply("verified", "M21")
        oid = {m.name: o for o, m in supply.metas.items()}
        game = _setup_game(7, supply, ((oid["Forest"],) * DECK_SIZE, (oid["Plains"],) * DECK_SIZE))
        world, executor = game.world, game.executor
        p0 = world.player_order[0]
        forest = next(h for h in sorted(world.cards, key=lambda h: h.index)
                      if world.zone_of(h).kind == ZONE_LIBRARY and world.controller_of(h) == p0)
        executor.apply_effect(
            _atom(
                Verb.MOVE_ZONE,
                target=Selector(QConst(1), SelectorMode.CHOOSE, UNIV,
                                zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),), referent="result"),
                destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            ),
            source=p0, controller=p0, bindings={"result": [forest]},
        )
        self.assertEqual(world.zone_of(forest).kind, ZONE_BATTLEFIELD)
        self.assertIn(forest, executor.binder.handle_record)
        sources = {tap.source for options in _mana_tap_options(executor, p0) for tap in options}
        self.assertIn(forest, sources)


class DealtSpellOwnCostModifierTest(unittest.TestCase):
    """Volcanic Salvo ({10}{R}{R}, "This spell costs {X} less to cast, where X is the total power
    of creatures you control") is offered with 13 power and 7 lands. The CR 601.2f fold reads the
    spell's own modifier for a dealt card in hand, which has no per-handle record (``_setup_game``
    attaches the pool before dealing; a card is bound when it is cast, played or put onto the
    battlefield). A pack cannot pin this: the pack runner binds every placed card."""

    def test_volcanic_salvo_in_a_dealt_hand_costs_x_less(self) -> None:
        from MTG_bot.core.executor.legality import plan_mana_taps, tap_for_payment

        supply = get_supply("verified", "M21")
        oid = {m.name: o for o, m in supply.metas.items()}
        field = ("Mountain",) * 7 + ("Colossal Dreadmaw", "Garruk's Gorehorn")  # power 6 + 7
        deck = tuple(oid[n] for n in ("Volcanic Salvo", *field))
        game = _setup_game(
            7, supply, (deck + (oid["Island"],) * (DECK_SIZE - len(deck)), (oid["Island"],) * DECK_SIZE)
        )
        world, executor = game.world, game.executor
        p0 = world.player_order[0]
        mine = sorted((h for h in world.cards if world.controller_of(h) == p0), key=lambda h: h.index)
        salvo = next(h for h in mine if world.cards[h].identity.name == "Volcanic Salvo")
        world.move_to_zone(salvo, p0, ZONE_HAND)  # dealt into the opening hand
        for name in sorted(set(field)):
            for card in [h for h in mine if world.cards[h].identity.name == name]:
                executor.apply_effect(  # each enters as in a game, which binds its record
                    _atom(
                        Verb.MOVE_ZONE,
                        target=Selector(QConst(1), SelectorMode.CHOOSE, UNIV,
                                        zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),), referent="result"),
                        destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                    ),
                    source=p0, controller=p0, bindings={"result": [card]},
                )
        executor.begin_turn(p0)
        self.assertNotIn(salvo, executor.binder.handle_record)  # unbound, as dealt
        taps = plan_mana_taps(executor, p0, lambda: spell_castable(executor, p0, salvo)[0])
        self.assertIsNotNone(taps)  # offered: X = 13 leaves {R}{R}
        self.assertEqual(len(taps), 2)
        tap_for_payment(executor, p0, taps)
        dreadmaw = next(h for h in mine if world.cards[h].identity.name == "Colossal Dreadmaw")
        cast(executor, p0, salvo, targets=(dreadmaw,))
        self.assertEqual(world.zone_of(salvo).kind, ZONE_GRAVEYARD)
        mountains = [h for h in mine if world.cards[h].identity.name == "Mountain"]
        self.assertEqual(sum(world.cards[h].tapped for h in mountains), 2)
