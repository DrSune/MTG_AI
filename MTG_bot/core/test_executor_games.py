"""Round-14a test suite: the random-policy full-M21 game harness, and the
repro pin for every crash the first 30 games produced.

Two jobs.

1. The harness must be trustworthy before any PC-7 number written from it
   means anything: one seed must replay to the SAME world fingerprint (the
   mission's "pinned replay test seed S game state fingerprints equal across
   two runs"), the deck builder must obey its own documented composition rules,
   and the policy's decision stream must come from the query surface — which is
   testable by making the query surface NARROW and checking the policy follows
   (:class:`DecisionSurfaceTest`). That is the C15 contract as an assertion, not
   as a comment about it.

2. Every crash class the 14a smoke run produced gets a test here, seed-pinned
   through the real seed -> deck -> policy derivation, asserting the CURRENT
   behaviour, with an ``AMENDED`` marker on the line that flips when the engine
   fixes it. These tests are the executable half of
   ``KNOWLEDGE/2026-09-30/03-game-loop-bugs.md``, which names them per row.

   * B-2 (Zone(STACK) target query) is FIXED here, so its test asserts the
     fixed answer and the marker is a history note, not a TODO.
   * B-4 (the mid-drain trigger decision channel) is OPEN and is why PC-7
     survival is 0%: no query enumerates the triggers an op is about to arm, so
     a positional ``trigger_decisions`` stream cannot be built for them.
   * B-7 (CONTROLLER_COUNT_GE), B-8 (TARGET_PLAYER designation) and B-9 (the
     ``result``/``event`` referents outside a trigger firing) are the other
     measured ceilings. B-8 has a documented CR-rule workaround on the policy
     side, so its test asserts the workaround works AND names the query it
     stands in for.
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
    Effect,
    FAnd,
    FAtom,
    FAtomPred,
    Keyword,
    KeywordAbility,
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
from MTG_bot.core.executor.quantity import ExecCtx, eval_filter
from MTG_bot.core.executor.query import (
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

UNIV = FAnd(())
SMOKE_DECK_PAIRS = 1409  # the CLI default: the tests run the shipped recipe


def _atom(verb: Verb, **roles: object) -> Atom:
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


def _target_sel() -> Selector:
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=UNIV,
        zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
    )


def _spell_effect(record: CardRecord) -> Effect | None:
    for ability in record.abilities:
        if isinstance(ability, SpellAbility):
            return ability.effect
    raise AssertionError(f"{record.name} has no SpellAbility node")


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
        # The honest 12e number, from the SUPPORTED_VERBS_V2-gated pass: an
        # ungated compile stamps every card supported (NUMBERS.md 2026-09-30),
        # so a harness that skipped the second pass would report 305.
        # AMENDED 2026-09-30 (round 16a): 286 -> 288 — FIGHT joined the
        # dispatched set, and the gate picked up exactly its two FIGHT
        # carriers (Brash Taunter, Primal Might), zero losses. Verified by
        # diffing the gated compile with and without Verb.FIGHT.
        # AMENDED (round 16b): 288 -> 291 — MANDATE_ATTACK joined, and the
        # gate picked up exactly its three carriers (Furor of the Bitten,
        # Pursued Whale, the Pirate token — the same with/without diff was
        # re-run, NUMBERS 2026-10-01). The DECKABLE set is unchanged: none
        # of the three is put-into-playable, so the engine decks themselves
        # are untouched by the flip; the "all" pool now CARRIES them.
        # AMENDED 2026-10-02 (round 16c): 291 -> 293 — MANDATE_BLOCK and
        # DAMAGE_ASSIGN_POLICY joined, and the with/without gate diff (run
        # again 16c) picked up exactly their two carriers (Canopy Stalker,
        # Garruk Savage Herald), zero losses, deckable unchanged again.
        # AMENDED 2026-10-02 (round 16e): 293 -> 297 — GAIN_CONTROL and
        # ATTACH joined; the with/without gate diff (run again 16e) picked
        # up EXACTLY the four control/attachment carriers (Traitorous
        # Greed, Enthralling Hold, Short Sword, Malefic Scythe), zero
        # losses. Deckable unchanged: none of the four is a creature, so
        # the engine decks are untouched — the two sorceries ride the
        # castable lane, the equipment the activation lane.
        # AMENDED (RUNG-1 response-window arc): 297 -> 301 — COUNTER_SPELL
        # joined with the stack.cast response window, and the gate picked
        # up EXACTLY its four carriers (Cancel, Miscast, Rewind, Lofty
        # Denial — measure_grammar --with-engine-flags: 301/305), zero
        # losses. Deckable unchanged: all four are instants, the castable
        # lane; the window now answers for them when they are cast.
        self.assertEqual(len(self.supply.engine_ids), 301)


class ReplayDeterminismTest(unittest.TestCase):
    """The mission's replay gate, as a test."""

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
    """C15, tested, 14b shape: the ENGINE asks with the query's own
    vocabulary at the demand site, and the policy answers that
    enumeration — AMENDED (was: the policy walked the effect tree and
    built a positional stream from the queries). The walk was only ever
    possible because the harness mirrored two CR literals and re-derived
    the pending-trigger demand; the ask-time channel deletes the need."""

    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=1)
        self.p0 = self.world.player_order[0]
        self.executor = Executor(self.world)
        self.source = self.world.add_card(card_id("Anchor"), self.p0, ZONE_HAND)
        self.policy = RandomPolicy(0)

    def test_may_offer_narrowing_is_enforced_at_the_ask(self) -> None:
        # "You may pay {2}" with an empty pool: query.py narrows the offer
        # to skip (CR 117.3). 14b: the RUNTIME asks with that narrowed
        # vocabulary, so even a policy that blindly answers 'fire' CANNOT
        # make the illegal decision — it raises out of the decision channel
        # before _v_pay is ever reached. C15's offer enumeration, now
        # enforced at the site that consumes it.
        effect = OptionalEffect(
            _atom(Verb.PAY, cost=Cost(parts=(CostManaGeneric(QConst(2)),)))
        )
        self.assertEqual(
            optional_offer(
                self.executor, effect, source=self.source, controller=self.p0
            ),
            ("skip",),
        )
        self.executor.decisions.provider = lambda vocab, what: "fire"
        with self.assertRaises(ValueError) as cm:
            self.executor.apply_effect(effect, source=self.source, controller=self.p0)
        self.assertIn("not in ('skip',)", str(cm.exception))
        # and the legal answer needs no enumeration by the policy at all:
        self.executor.decisions.provider = self.policy.answer
        self.executor.apply_effect(effect, source=self.source, controller=self.p0)
        self.assertEqual(
            self.executor.decisions.answered(),
            ((f"may:{self.source}", "skip"),),
        )

    def test_choose_ask_vocabulary_is_the_query_enumeration(self) -> None:
        effect = Choose(
            count=QConst(1),
            options=(
                _atom(Verb.TAP, target=_target_sel()),
                _atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1)),
            ),
        )
        asked: list[tuple[tuple[str, ...], str]] = []

        def provider(vocab: tuple[str, ...], what: str) -> str:
            asked.append((vocab, what))
            return self.policy.choose(vocab)

        self.executor.decisions.provider = provider
        self.executor.apply_effect(effect, source=self.source, controller=self.p0)
        # the ask vocabulary equals the query surface's own option-set
        # enumeration (§8.3 query/runtime identity, now delivered AT the ask)
        self.assertEqual(len(asked), 1)
        vocab, what = asked[0]
        self.assertTrue(what.startswith(f"choose:{self.source}:"))
        # Choose + QConst(1) = exactly the n printed options (choose_options)
        self.assertEqual(vocab, ("0", "1"))

    def test_unimplemented_node_raises_from_the_engine(self) -> None:
        # Repeat is real IR and unimplemented (12e). 14b: with the walk
        # deleted the harness reports the engine's OWN raise (it no longer
        # mirrors the gate — it plays into it).
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
        # C15/C16: an empty stream with no pool and no answerer raises —
        # the engine never defaults a decision.
        effect = OptionalEffect(
            _atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1))
        )
        with self.assertRaises(ValueError):
            self.executor.apply_effect(effect, source=self.source, controller=self.p0)


class CrashLedgerTest(unittest.TestCase):
    """One test per crash class the first 30 games produced."""

    def test_b2_stack_zone_targets_are_enumerable(self) -> None:
        """B-2 FIXED 14a. AMENDED (was ``assertRaises(NotImplementedError)``,
        'Zone(STACK) enumeration needs the stack'): that raise was round-12
        truth and 13b made it stale. The M21 consumer is Unsubstantiate's
        BATTLEFIELD + STACK target selector, which made legal_casts call the
        spell castable and spell_target_slots raise on the next question."""
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
                zone=Zone(ZoneKind.STACK, ControllerRef.ANY),
            ),
            source=spell,
            controller=p0,
        )
        self.assertEqual(slot.candidates, (spell,))

    def test_b4_scry_armed_by_the_land_drop_itself_is_answered(self) -> None:
        """B-4 FIXED 14b (was the PC-7 blocker, 22/30 kills). The M21
        check-land cycle — drop the land, ITS OWN ETB scry asks mid-op —
        now answers through the vocabulary-addressed channel: the scry ask
        arrives with ('top','bottom') + the 'scry:<player>:<n>' tag the
        moment the drain reaches it, and the provider answers without the
        caller having enumerated anything. Scripted proof below (direct,
        no policy path), then the seed-pinned game check that the old
        rejection message is gone. Replay fingerprint pinned (the
        decision history rides the seeded stream: two runs agree)."""
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
        # and the seed-pinned game class: the old positional rejection is gone.
        outcome = play_game(0, "all", SMOKE_DECK_PAIRS, turn_cap=8)
        crash = outcome.crash
        if crash is not None:  # other ledger classes may still kill it —
            self.assertNotIn("SCRY decision", crash["message"])

    def test_b7_controller_count_ge_filter_raises_from_the_query(self) -> None:
        """B-7 CONTAINER — FIXED 14d (was: the query raised for an
        engine-supported card). AMENDED 14d (was: assertRaises on the same
        direct path; the row text below kept as history). The world-count
        version of CONTROLLER_COUNT_GE answers at the SAME query entry
        point (ctx_for now carries the journal, and this pred is pure
        world-state): 3 lands < 4 is False, and the 4th land flips it."""
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
        """B-8/B-5 CLOSED 14b. 'target opponent' compiles to a
        ControllerRef.TARGET_PLAYER coordinate with NO Selector — the slot
        query now SYNTHESIZES the designation slot (candidates = the
        opponent seats, the engine's own CR population), so the policy
        designates from the query instead of mirroring the rule, and
        ``stack._validate_spell_targets`` stays the oracle. AMENDED (was:
        the mirrored-rule workaround + the _names_a_player IR probe)."""
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
        """B-9 CLOSED 14e (was: cast-time atoms reading the ``result``
        referent raised — the register existed only inside a trigger firing;
        8/11 of the 14d engine-30 wall, dominant face Feat of Resistance).
        The producer-write design: the register is the ctx's ``result``
        binding slot, written by the object-action verbs (SEARCH/CHOOSE
        since 14c, TAP/UNTAP/PUT_COUNTER/MOVE_ZONE since 14e) INSIDE one
        effect execution, and per-resolution because every ExecCtx carries
        a fresh bindings dict. AMENDED (was: assertRaises on the Seasoned
        Hallowblade cast).

        (a) Feat of Resistance resolves at CAST: PUT_COUNTER writes the
            designated creature, the color Choose asks, GRANT reads it.
        (b) Seasoned Hallowblade's tail is the activation's (B-17 capture):
            paying DISCARD runs Seq(TAP; GRANT) — the blade turns
            indestructible. Casting it now raises the B-1 ``not_a_spell``
            flag (capture moved the crash, per the ruling: the accidental
            SpellAbility node is gone).
        (c) A read with NO producer in its own execution still RAISES
            (flag, never guess) — and the write never leaked out of the
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
        # …and a hand cast no longer trips the B-1 not_a_spell flag: C4
        # gave the creature a cast-lane carrier, so legality now reaches
        # the mana gate and fails there on an empty pool (the raise
        # MOVED, it did not disappear — B-9 still resolves above).
        hand_spell = world.add_card(identity_of(blade_rec), p0, ZONE_HAND)
        world.active_player = p0
        executor.turn_open = True
        executor.phase = "FIRST_MAIN"
        with self.assertRaises(ValueError) as cm:
            cast(executor, p0, hand_spell, targets=(), decisions=())
        self.assertIn("cost:mana", str(cm.exception))

    def test_new_rest_one_of_designation_is_the_12c_gap(self) -> None:
        """AMENDED 14c (B-13 FIXED): the split-selection pair designates
        through the vocabulary-addressed decision channel — the 12c prompt
        the 14b streams finally serve. ONE_OF asks with the Handle-sorted
        candidate list as the EXACT vocabulary (C15: enumerate-then-answer,
        no prose); an answer no lane can give RAISES loudly (never a
        default); REST is the deterministic complement — no ask (query.
        rest_of's runtime twin)."""
        # (a) one candidate: forced, no decision consumed (exactly-one
        #     legal filler auto-fills, /06 §1.4).
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
                zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
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
                        target=Selector(QConst(1), SelectorMode.ONE_OF, UNIV, bf),
                    ),
                    _atom(
                        Verb.UNTAP,
                        target=Selector(QConst(1), SelectorMode.REST, UNIV, bf),
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
        """AMENDED 14c (QX CLOSED at cast): CR 601.2f declares X WITH the
        total cost, so when the caller passes no x the legality fold's
        documented X=0 witness (CR 107.1) is the DECLARATION — the frame's
        x_value and the effect's QX read it (the 13b wiring gap: a QX in
        an effect quantity instead of the cost stayed unbound and died at
        quantity.resolve).
        AMENDED 2026-09-30 (round 16a): FIGHT joined HANDLERS, so Primal
        Might has no unimplemented class left and the X=0 cast RESOLVES
        end to end — the pin flips from "got PAST the QX raise" to the
        full resolution: spell to graveyard, the QX=0 witness deal leaves
        NO damage mark (mark_damage ignores n<=0), the ally survives, and
        the FIGHT's CHOOSE over an empty opponent population fights
        nobody (C17). The unbound raise itself is untouched OUTSIDE a
        cast (ctx.x_value None in any other context still flags — pinned
        by 13b's suite)."""
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
    """Round-14c close-out pins: one green test per crash class the round
    fixed, written against the exact crash shape the ledger row records
    (KNOWLEDGE/2026-09-30/03-game-loop-bugs.md B-15/B-16/B-18 + QX)."""

    def _world(self, seed: int = 7) -> tuple[GameWorld, Executor]:
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=seed)
        return world, Executor(world)

    def test_b15_cards_role_target_designation_flows(self) -> None:
        """B-15 FIXED (Rise Again / Read the Tides): the TARGET-mode
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
        # UNDESIGNATED stays loud (the 12c raise is untouched):
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
                        Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                    ),
                    destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                ),
                source=p0,
                controller=p0,
            )
        self.assertIn("TARGET selector has no designation", str(cm.exception))

    def test_b16_target_binding_does_not_clobber_referent_selector(self) -> None:
        """B-16 FIXED (Necromentia): an ANAPHORIC Selector (referent set)
        resolves itself — the spell-level ``target`` designation (the
        designated OPPONENT) no longer hijacks the role and feeds a player
        handle to controller_of (KeyError 'unknown card player:0'). The
        SEARCH atom also lands its found cards in the ``result`` register
        (the 13b CHOOSE read-back convention Necromentia's EXILE reads)."""
        world, executor = self._world()
        p0, p1 = world.player_order
        card = world.add_card(
            CardIdentity(oracle_id=_oid(88), name="Found", type_line="Creature"),
            p0,
            ZONE_GRAVEYARD,
        )
        executor.apply_effect(
            _atom(
                Verb.EXILE,
                target=Selector(
                    QConst(1),
                    SelectorMode.CHOOSE,
                    UNIV,
                    Zone(ZoneKind.ANY, ControllerRef.ANY),
                    referent="result",
                ),
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
                            Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
                        ),
                        destination=Zone(ZoneKind.EXILE, ControllerRef.YOU),
                    ),
                    _atom(
                        Verb.EXILE,
                        target=Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            UNIV,
                            Zone(ZoneKind.ANY, ControllerRef.ANY),
                            referent="result",
                        ),
                    ),
                )
            ),
            source=p0,
            controller=p0,
        )
        self.assertEqual(world.zone_of(land).kind, ZONE_EXILE)

    def test_b18_discard_scoped_to_the_actors_live_hand(self) -> None:
        """B-18 FIXED (Bad Deal): the DISCARD selection pool is the ACTOR'S
        own hand re-read at take time (CR 701.8a). Bad Deal's compiled
        Zone(HAND, ANY) spans both hands and the Handle-sorted stand-in
        used to grab the CASTER'S low handles — the not-in-hand raise
        ended the game. Caster's hand now stays intact."""
        world, executor = self._world()
        p0, p1 = world.player_order
        # caster's card FIRST (lowest handle — exactly what the old
        # sorted stand-in reached for), then the actor's two.
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
                Verb.DISCARD,
                controller=ControllerRef.OPPONENT,
                cards=Selector(
                    QConst(2),
                    SelectorMode.CHOOSE,
                    UNIV,
                    Zone(ZoneKind.HAND, ControllerRef.ANY),
                ),
            ),
            source=mine,
            controller=p0,
        )
        self.assertEqual(world.zone_of(mine).kind, ZONE_HAND)
        for card in theirs:
            self.assertEqual(world.zone_of(card).kind, ZONE_GRAVEYARD)
        self.assertEqual(world.players[p1].zone(ZONE_HAND).entries, [])

    def test_new_moved_to_zone_this_turn_pred_stays_unimplemented(self) -> None:
        """B-7 FAMILY — FIXED 14d. AMENDED 14d (was: both history preds
        RAISED through the ctx_for path — the dominant games class, 13/22
        crashes). The journal now rides every ExecCtx (query included), so
        the preds ANSWER: with no matching journalled row this turn the
        honest answer is False (the history is a record, and an empty
        record is an answer — unlike FLIP_WON's no-antecedent raise, which
        stands below unchanged). Positive legs live in
        Round14dJournalTest (real moves/casts make the same preds True)."""
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
        self.assertIn("FLIP_WON", str(cm.exception))  # B-17, no flip yet

    def test_b7_history_preds_stay_loud_on_a_bare_ctx(self) -> None:
        """The no-half-preds rule: a context that carries NO journal cannot
        answer a history predicate, and must raise naming the pred (the
        FLIP_WON / NAME_CHOSEN convention). Only the 14d family is answered
        here; the untouched members of the vocab still raise."""
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
        # a vocab member STILL unimplemented (games never demanded it).
        # r19b AMENDMENT: TURN_OF moved out of this role — Discontinuity's
        # cost window made the grammar demand it, and it answers from the
        # active-seat column (no journal), so a bare ctx cannot keep it
        # loud; its regression lives in test_executor_r19b.
        # r23a AMENDMENT: TARGETS_SOURCE moved out of THIS role too — the
        # Pursued Whale cost-fold crash class demanded it, and it now
        # answers as the IS_ANY_TARGET mirror (does the judged object's
        # designation contain the ctx's SOURCE). A bare ctx designates
        # NOTHING, so the documented pre-declaration reading is a
        # conservative False (no designation can hold the source); the
        # True/False fold behaviour is pinned in test_executor_r23a.
        self.assertFalse(eval_filter(FAtom(FAtomPred.TARGETS_SOURCE), card, bare))

    def test_new_zone_stack_runtime_enumeration_raises(self) -> None:
        """B-19 — FIXED 14d. AMENDED 14d (was: an Unsubstantiate-shape
        MOVE_ZONE over Zone(STACK) died with a bare KeyError, B-2's runtime
        twin). Runtime enumeration now reads the parked frames through
        stack.stack_zone (the SAME source legal_targets has read since the
        14a F-2 fix), so the spell returns to its owner's hand."""
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
                    Zone(ZoneKind.STACK, ControllerRef.ANY),
                ),
                destination=Zone(ZoneKind.HAND, ControllerRef.OWNER),
            ),
            source=p0,
            controller=p0,
            bindings={"target": [spell]},
        )
        self.assertEqual(world.zone_of(spell).kind, ZONE_HAND)

    def test_b19_stack_enumeration_owner_scope_stays_loud(self) -> None:
        """The honest half of the B-19 fix: OWNER-scoped STACK enumeration
        keeps the 12b selector raise (every zone carries that flag at
        runtime), and an empty designation over the stack resolves to
        nothing, not a crash."""
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
                        Zone(ZoneKind.STACK, ControllerRef.OWNER),
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
                    Zone(ZoneKind.STACK, ControllerRef.ANY),
                ),
                destination=Zone(ZoneKind.HAND, ControllerRef.OWNER),
            ),
            source=p0,
            controller=p0,
            bindings={"target": []},
        )


class Round14dJournalTest(unittest.TestCase):
    """Round-14d B-7 close-out pins: one POSITIVE green test per
    journal-backed predicate the games actually hit (the ledger's 13/22
    dominant class), driven by REAL journalled atoms — plus the C18-row
    dies test and the cross-turn exile-with persistence. The turn window
    is begin_turn's UPKEEP marker (events.py turn_window)."""

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
                Verb.EXILE,
                target=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    UNIV,
                    Zone(ZoneKind.HAND, ControllerRef.YOU),
                ),
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
        13b CAST row's (caster, from_zone) columns answer the handle-
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
        DIED_THIS_TURN (Gadrak's Treasure count, C18 row): real MOVE_ZONE
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
                    Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
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
        # now let it die (battlefield -> graveyard): the C18 row appears
        executor.apply_effect(
            _atom(
                Verb.MOVE_ZONE,
                cards=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    UNIV,
                    Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
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
        exile — the 12b cause column). Another source says no, and the
        relationship PERSISTS across turns (it is not windowed)."""
        world, executor = self._world()
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
                Verb.EXILE,
                target=Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    UNIV,
                    Zone(ZoneKind.HAND, ControllerRef.YOU),
                ),
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
    """Round 14e: the WORLD-evaluated preds the 14d wall named — POWER_GE
    (Legion's Judgment "power 4 or greater" family) and CMC_LE (Eliminate /
    Idol of Endurance / Ugin's mana-value thresholds). Pure world/identity
    reads, answered at EVERY eval entry point with no journal (the raise
    they replace was 3/11 engine30, 2/11 of the 10-pools)."""

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
        # declared value (14c CR 601.2f); unbound outside a cast it keeps
        # raising naming the quantity — no guessed zero for a filter pred.
        world, executor = self._setup()
        p0 = world.player_order[0]
        anchor = world.add_card(card_id("Anchor"), p0, ZONE_BATTLEFIELD)
        ctx = ctx_for(executor, source=anchor, controller=p0)
        critter = world.add_card(card_id("Critter", cmc=2), p0, ZONE_BATTLEFIELD)
        with self.assertRaises(NotImplementedError):
            eval_filter(FAtom(pred=FAtomPred.CMC_LE, count=QX()), critter, ctx)


class Round14fSurfaceTest(unittest.TestCase):
    """Round 14f: the three surfaces the 14e census named honestly —
    KEYWORD_HAS (the LIVE keyword oracle: printed ∪ granted − lost, the
    same registry combat legality calls), EachPlayer (per-player
    sub-executions with the CONTROLLER rotated — the templates compile the
    inner effect YOU-relative), and the Chandra permission row's
    CROSS-resolution population read (14e's residual: the compiled row
    now emits the IS_EXILED_WITH_SOURCE population, so a LATER activation
    answers from the journal, not the dead per-resolution register)."""

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
                    Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
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
        # The no-half-preds rule (14d convention): a context with no layer
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
        # The REAL compiled node (the 14e castable-pool repro's own tree):
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
        # 14e's residual at the exact seam: a card exiled by the source in
        # an EARLIER resolution is in the permission's population when a
        # FRESH execution (fresh bindings dict, NO result register — the
        # situation a later activation is in) resolves the compiled row's
        # Selector. Before the fidelity fix this raised "no producer atom
        # wrote one in this execution".
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
                Verb.EXILE,
                target=Selector(
                    QConst(1),
                    SelectorMode.CHOOSE,
                    FAnd(()),
                    Zone(ZoneKind.LIBRARY, ControllerRef.YOU, ZonePosition.TOP),
                ),
            ),
            source=chandra,
            controller=p0,
        )
        self.assertEqual(world.zone_of(top).kind, ZONE_EXILE)
        selector = Selector(
            QUnbounded(),
            SelectorMode.CHOOSE,
            FAtom(pred=FAtomPred.IS_EXILED_WITH_SOURCE),
            Zone(ZoneKind.EXILE, ControllerRef.YOU),
        )  # the shape the B4-cast-them row now compiles
        ctx = ctx_for(executor, source=chandra, controller=p0)
        self.assertEqual(resolve_selector(selector, ctx), [top])
        # and the read is CAUSE-scoped: another source's exiles are not it
        other = world.add_card(card_id("Idol of Endurance"), p0, ZONE_BATTLEFIELD)
        rival = world.add_card(card_id("Rival Card"), p0, ZONE_LIBRARY)
        executor.apply_effect(
            _atom(
                Verb.EXILE,
                target=Selector(
                    QConst(1),
                    SelectorMode.CHOOSE,
                    FAnd(()),
                    Zone(ZoneKind.LIBRARY, ControllerRef.YOU, ZonePosition.TOP),
                ),
            ),
            source=other,
            controller=p0,
        )
        self.assertEqual(world.zone_of(rival).kind, ZONE_EXILE)
        self.assertEqual(resolve_selector(selector, ctx), [top])


class Round16eControlTest(unittest.TestCase):
    """Round-16e control-overlay + aura lifecycle pins (the smoke that
    proved the pipeline, now permanent): one-turn steal, enchant-the-
    creature cast ordering (CR 303.4a/608.2a), the no-legal-target cast
    gate (CR 601.2e), the aura-death control return, and the unattached-
    aura state check (CR 704.5q). Ledger: KNOWLEDGE/2026-09-30/15-*.md."""

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
        cast(executor, p0, spell, targets=(victim,), decisions=("C",))
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
                    Zone(ZoneKind.ANY, ControllerRef.ANY),
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
                            Zone(ZoneKind.ANY, ControllerRef.ANY),
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
            orphan_emblems=(),
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
        # Seed 73, full engine pool: the longest decisive corpus game (56
        # turns).  It grinds through many rounds but its world genuinely
        # changes every round, so the stall rule must not fire.  Pinned at
        # HEAD with the stall rule present (baseline reports/games_2026-10-05).
        game = play_game(73, "all", SMOKE_DECK_PAIRS)
        self.assertFalse(game.reason.startswith("STALL"), game.reason)
        self.assertEqual(game.turns, 56)
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


class _LoopDeckPolicy(RandomPolicy):
    """Deterministic policy: each turn, cast exactly one legal spell.

    RandomPolicy's dice would take an expected ~250 turns per candidate
    cast window here, making the stall statistically unreachable inside the
    cap; a fixed single-cast policy exercises the detector squarely.
    """

    def take_acts(self, game: Game, seat: Handle) -> None:
        self.turn = game.world.turn
        self.seat_index = game.world.player_order.index(seat)
        rows = [r for r in legal_casts(game.world, game.executor, seat) if not r.land]
        if rows:
            self.play_cast(game, seat, rows[0])
        game.digest.append(f"T{self.turn}.end")


def _oid(n: int) -> str:
    return f"{n:08x}-1111-2222-3333-444444444444"


if __name__ == "__main__":
    unittest.main()
