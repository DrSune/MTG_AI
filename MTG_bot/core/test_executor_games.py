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
    ActivatedAbility,
    Atom,
    AtomArgs,
    CardRecord,
    Choose,
    Conditional,
    ControllerRef,
    Cost,
    CostManaGeneric,
    Effect,
    FAnd,
    FAtom,
    FAtomPred,
    OptionalEffect,
    QConst,
    Repeat,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
    walk,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import (
    DECK_SIZE,
    MAX_COPIES,
    MIN_MANA_SOURCES,
    RandomPolicy,
    Supply,
    build_deck,
    deal_decks,
    get_supply,
    identity_of,
    play_game,
    run_games,
)
from MTG_bot.core.executor.legality import ctx_for
from MTG_bot.core.executor.quantity import eval_filter
from MTG_bot.core.executor.query import (
    legal_targets,
    optional_offer,
    spell_target_slots,
)
from MTG_bot.core.executor.stack import cast, park, play_land
from MTG_bot.core.identity import CardIdentity
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

    def test_engine_count_is_the_gated_286(self) -> None:
        # The honest 12e number, from the SUPPORTED_VERBS_V2-gated pass: an
        # ungated compile stamps every card supported (NUMBERS.md 2026-09-30),
        # so a harness that skipped the second pass would report 305.
        self.assertEqual(len(self.supply.engine_ids), 286)


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
        """B-7 OPEN. Fabled Passage's land-swap reads 'if you control more
        lands' — CONTROLLER_COUNT_GE is unimplemented in the predicate
        evaluator, reached through the query/activation path for a card the
        engine flags as supported, so asking the question costs a raise.
        AMENDED 14b (was: seed-pinned through a policy path): pinned DIRECTLY
        on the card's own Conditional predicate — deterministic,
        path-independent, and it raises through the SAME evaluator."""
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
        with self.assertRaises(NotImplementedError) as cm:
            eval_filter(pred, permanent, ctx)
        self.assertIn("CONTROLLER_COUNT_GE", str(cm.exception))

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

    def test_b9_result_referent_only_resolves_inside_a_trigger(self) -> None:
        """B-9 RESIDUAL, still OPEN after the 14b rebuild (unchanged from
        14a): Seasoned Hallowblade has NO trigger — a static-ish effect is
        parked on its SpellAbility and reads the ``result`` referent, which
        resolves only inside a trigger firing, so CASTING the card still
        raises out of resolution with no event register to read."""
        supply = get_supply("all")
        record = _record_named(supply, "Seasoned Hallowblade")
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=3)
        p0 = world.player_order[0]
        executor = Executor(world)
        executor.attach_pool(supply.pool)
        spell = world.add_card(identity_of(record), p0, ZONE_HAND)
        world.players[p0].mana_pool["W"] = 1
        world.players[p0].mana_pool["C"] = 2
        world.active_player = p0
        executor.turn_open = True
        executor.phase = "FIRST_MAIN"
        with self.assertRaises(NotImplementedError) as cm:
            cast(executor, p0, spell, targets=(), decisions=())
        self.assertIn("referent", str(cm.exception))

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

    def test_qx_undeclared_x_raises_loud_on_cast(self) -> None:
        """AMENDED 14c (QX CLOSED at cast): CR 601.2f declares X WITH the
        total cost, so when the caller passes no x the legality fold's
        documented X=0 witness (CR 107.1) is the DECLARATION — the frame's
        x_value and the effect's QX read it (the 13b wiring gap: a QX in
        an effect quantity instead of the cost stayed unbound and died at
        quantity.resolve). Primal Might now gets past the QX raise and
        falls to the NEXT open class: Verb.FIGHT has no handler at all
        (unimplemented-verb ledger family, B-3/B-10 neighbours). The
        unbound raise itself is untouched OUTSIDE a cast (ctx.x_value
        None in any other context still flags — pinned by 13b's suite)."""
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
        with self.assertRaises(NotImplementedError) as cm:
            cast(executor, p0, spell, targets=(creature,), decisions=())
        self.assertIn("FIGHT", str(cm.exception))  # got PAST the QX raise

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
        """NEW class pin (surfaces once B-16 closes): Necromentia's
        CREATE_TOKEN count filters MOVED_TO_ZONE_THIS_TURN, which the
        closed filter vocabulary does not implement — loud, never guessed
        (the B-7 predicate-completeness family). CAST_THIS_TURN_FROM
        (Juggernaut's kin, castable pool) is the same family's next
        member; FLIP_WON with NO recorded flip (B-17, the misplaced
        conditional tail) answers through the SAME raise shape."""
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
            with self.assertRaises(NotImplementedError) as cm:
                eval_filter(filt, card, ctx)
            self.assertIn(pred.name, str(cm.exception))
        with self.assertRaises(NotImplementedError) as cm:
            eval_filter(FAtom(FAtomPred.FLIP_WON, who=ControllerRef.YOU), card, ctx)
        self.assertIn("FLIP_WON", str(cm.exception))  # B-17, no flip yet

    def test_new_zone_stack_runtime_enumeration_raises(self) -> None:
        """NEW class pin (14c, the B-2 runtime twin): B-2 closed the QUERY
        side (legal_targets reads the stack frames), but RUNTIME
        enumeration of Zone(STACK) has no ZONE_KIND_TO_STATE entry, so an
        Unsubstantiate-shape MOVE_ZONE dies with a bare KeyError (not even
        a NotImplementedError). Loud by accident, pinned deliberately —
        the runtime stack enumeration is the next round's small fix."""
        world, executor = self._world()
        p0 = world.player_order[0]
        with self.assertRaises(KeyError) as cm:
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
                bindings={"target": []},
            )
        self.assertIn("STACK", str(cm.exception))


def _oid(n: int) -> str:
    return f"{n:08x}-1111-2222-3333-444444444444"


if __name__ == "__main__":
    unittest.main()
