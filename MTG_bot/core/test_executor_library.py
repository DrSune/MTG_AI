"""Tests for the round-13a library/turn executor arc (KNOWLEDGE 11 §13a).

Pins the new surface: DRAW (incl. the CR 121.2 empty-library no-op), SEARCH
(bindings-first designation, deterministic CHOOSE / seeded RANDOM stand-ins,
the Cultivate e2e), FLIP_COIN determinism + the FLIP_WON conditional across
separate ability rows (Tavern Swindler), END_TURN / EXTRA_TURN / LOSE_GAME
on the executor turn ledger, the loyalty ledger (Chandra, Flame's Catalyst:
seeding, payment, CR 606.3 once-per-turn, the 0-loyalty death, the
sorcery-phase window gate) and ``legal_search``; replay fingerprints stay
a function of the sequence alone (P12).
"""

import dataclasses
import itertools
import json
import unittest
from pathlib import Path

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    ActivationWindow,
    Atom,
    AtomArgs,
    Conditional,
    ControllerRef,
    Cost,
    CostLoyalty,
    CounterKind,
    FAnd,
    FAtom,
    FAtomPred,
    QConst,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
    from_dict,
)
from MTG_bot.core.executor import (
    SUPPORTED_VERBS_V1,
    SUPPORTED_VERBS_V2,
    Executor,
    ability_playable,
    activate,
)
from MTG_bot.core.executor.durations import DurationLedger
from MTG_bot.core.executor.quantity import ExecCtx, eval_filter
from MTG_bot.core.executor.query import legal_search
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import record_of

_GOLDEN_DIR = Path(__file__).parent / "golden" / "M21"
_GOLDENS: dict[str, dict] = {}

_ORACLE_SEQ = itertools.count(1)


def reset_oracle_ids():
    """Restart the oracle-id sequence so two worlds built the same way get
    identical identities (required for replay-fingerprint comparisons)."""
    global _ORACLE_SEQ
    _ORACLE_SEQ = itertools.count(1)


def card_id(
    name,
    power=None,
    toughness=None,
    type_line="Creature",
    cmc=2,
    oid=None,
    loyalty=None,
):
    n = next(_ORACLE_SEQ)
    return CardIdentity(
        oracle_id=oid or f"{n:08x}-1111-2222-3333-444444444444",
        name=name,
        type_line=type_line,
        power=power,
        toughness=toughness,
        cmc=cmc,
        loyalty=loyalty,
    )


def atom(verb, **roles):
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


def golden(name: str) -> dict:
    """The committed golden IR dict for a card name (PC-4 stable file)."""
    if not _GOLDENS:
        for path in _GOLDEN_DIR.glob("*.json"):
            d = json.loads(path.read_text(encoding="utf-8"))
            _GOLDENS[d["name"]] = d
    return _GOLDENS[name]


def record(name: str, oid: str | None = None):
    """The golden's CardRecord, optionally re-keyed to a world card's
    oracle id (the bridge is identity-checked)."""
    rec = from_dict("CardRecord", golden(name))
    return rec if oid is None else dataclasses.replace(rec, oracle_id=oid)


BF_ANY = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)
BF_YOU = Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)
LIB_YOU = Zone(ZoneKind.LIBRARY, ControllerRef.YOU)
HAND_YOU = Zone(ZoneKind.HAND, ControllerRef.YOU)
HAND_ANY = Zone(ZoneKind.HAND, ControllerRef.ANY)
UNIV = FAnd(())
BASIC = FAtom(FAtomPred.SUPERTYPE_EQ, string_value="Basic")
FLIP_WON_YOU = FAtom(FAtomPred.FLIP_WON, who=ControllerRef.YOU)


def search_atom(mode=SelectorMode.CHOOSE, count=2, destination=BF_YOU, **extra):
    return atom(
        Verb.SEARCH,
        cards=Selector(QConst(count), mode, BASIC, LIB_YOU),
        destination=destination,
        **extra,
    )


class LibraryCase(unittest.TestCase):
    """Shared fixture: p0 with a 4-card basic-land library (L1..L4, L4 top)
    and H1 in hand; p1 plain; p0 active, FIRST_MAIN (no turn markers until
    ``begin_turn`` is called per-test)."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=7)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.libs = [
            self.world.add_card(card_id(f"L{i}", type_line="Basic Land"), self.p0)
            for i in (1, 2, 3, 4)
        ]
        self.h1 = self.world.add_card(card_id("H1"), self.p0, ZONE_HAND)
        self.ex = Executor(self.world)

    def zone(self, player, kind):
        return self.world.players[player].zone(kind).entries

    def journal_rows(self, kind):
        return [e for e in self.ex.journal.events if e.kind == kind]

    def _do(self, node, controller=None, source=None, **kw):
        fire = self.ex.execute if isinstance(node, Atom) else self.ex.apply_effect
        return fire(
            node,
            source=source if source is not None else self.p0,
            controller=controller if controller is not None else self.p0,
            **kw,
        )


# ------------------------------------------------------------------- DRAW


class TestDraw(LibraryCase):
    def test_draw_moves_n_and_journals_drawer_ordinals(self):
        self._do(atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(2)))
        # top of library = last entry: L4 then L3
        self.assertEqual(self.zone(self.p0, ZONE_LIBRARY), [self.libs[0], self.libs[1]])
        self.assertEqual(
            self.zone(self.p0, ZONE_HAND)[-2:], [self.libs[3], self.libs[2]]
        )
        rows = self.journal_rows("CARD_DRAWN")
        self.assertEqual(len(rows), 2)
        self.assertEqual([r.subject for r in rows], [self.libs[3], self.libs[2]])
        self.assertEqual([r.data for r in rows], [(self.p0, 1), (self.p0, 2)])

    def test_draw_on_empty_library_is_clean_noop(self):
        # CR 121.2: the draw attempt on an empty library is free; the loss
        # is a state-check, NOT part of the DRAW verb.
        self._do(
            atom(Verb.DRAW, controller=ControllerRef.OPPONENT, amount=QConst(3)),
            controller=self.p0,
        )
        self.assertEqual(self.zone(self.p1, ZONE_HAND), [])
        self.assertEqual(self.journal_rows("CARD_DRAWN"), [])
        self.assertEqual(self.ex.lost_players, [])
        self.assertEqual(self.world.players[self.p1].life, 20)


# ----------------------------------------------------------------- SEARCH


def _random_search_pick(master_seed: int):
    """Cards a RANDOM-count-1 SEARCH (no designation) moves onto the
    battlefield in a freshly-built 4-land world under ``master_seed``."""
    reset_oracle_ids()
    world = GameWorld(num_players=2, start_life=20, master_seed=master_seed)
    p0, _p1 = world.player_order[0], world.player_order[1]
    for i in (1, 2, 3, 4):
        world.add_card(card_id(f"L{i}", type_line="Basic Land"), p0)
    ex = Executor(world)
    ex.execute(
        search_atom(mode=SelectorMode.RANDOM, count=1),
        source=p0,
        controller=p0,
    )
    return list(world.players[p0].zone(ZONE_BATTLEFIELD).entries)


class TestSearchUnit(LibraryCase):
    def test_search_binding_moves_exactly_the_designated_cards(self):
        self._do(
            search_atom(tapped_on_enter=True),
            bindings={"cards": [self.libs[1], self.libs[3]]},
        )
        bf = self.zone(self.p0, ZONE_BATTLEFIELD)
        self.assertEqual(bf, [self.libs[1], self.libs[3]])
        self.assertEqual(self.zone(self.p0, ZONE_LIBRARY), [self.libs[0], self.libs[2]])
        self.assertTrue(self.world.cards[self.libs[1]].tapped)
        self.assertTrue(self.world.cards[self.libs[3]].tapped)
        rows = [e for e in self.ex.events if e[1] == "SEARCH"]
        self.assertEqual(
            [(r[2], r[3]) for r in rows],
            [
                (str(self.libs[1]), "library->battlefield"),
                (str(self.libs[3]), "library->battlefield"),
            ],
        )

    def test_undesignated_choose_is_deterministic_first_n_sorted(self):
        expected = sorted(self.libs)[:2]
        self.assertEqual(expected, self.libs[:2])  # Handle order == attach order
        self._do(search_atom(destination=HAND_YOU))
        self.assertEqual(self.zone(self.p0, ZONE_LIBRARY), self.libs[2:])
        # destination append order follows the sorted selection
        self.assertEqual(self.zone(self.p0, ZONE_HAND), [self.h1] + expected)
        self.assertEqual(self.zone(self.p0, ZONE_BATTLEFIELD), [])

    def test_search_random_is_seeded_replay_identical(self):
        first = _random_search_pick(7)
        self.assertEqual(len(first), 1)
        self.assertEqual(_random_search_pick(7), first)

    def test_search_without_designation_or_selector_raises(self):
        with self.assertRaises(ValueError):
            self._do(atom(Verb.SEARCH, destination=BF_YOU))
        # AMENDED 14c (B-13): ONE_OF SEARCH is no longer an unsupported
        # mode — it asks the decision channel (Handle-sorted candidate
        # vocabulary); with no lane able to answer the ask exhausts to a
        # loud ValueError, never a guessed pick.
        with self.assertRaises(ValueError):
            self._do(search_atom(mode=SelectorMode.ONE_OF, count=1))

    def test_cultivate_e2e_per_step_bindings(self):
        """The golden run PER-STEP: shared bindings across Seq steps would
        cross-contaminate the MOVE_ZONE atoms, so each step re-binds."""
        steps = golden("Cultivate")["abilities"][0]["effect"]["steps"]
        nodes = [from_dict("Atom", s) for s in steps]
        self.assertEqual([n.verb.name for n in nodes[:2]], ["SEARCH", "REVEAL"])
        land_a, land_b = self.libs[0], self.libs[1]
        self._do(nodes[0], bindings={"cards": [land_a, land_b]})  # SEARCH
        self._do(nodes[1])  # REVEAL QUnbounded must not crash
        self._do(nodes[2], bindings={"cards": [land_a]})  # ONE_OF -> BF tapped
        self._do(nodes[3], bindings={"cards": [land_b]})  # REST -> hand
        self._do(nodes[4])  # SHUFFLE
        self.assertIn(land_a, self.zone(self.p0, ZONE_BATTLEFIELD))
        self.assertTrue(self.world.cards[land_a].tapped)
        self.assertIn(land_b, self.zone(self.p0, ZONE_HAND))
        self.assertIn("SHUFFLE", [e[1] for e in self.ex.events])
        self.assertIn("REVEAL", [e[1] for e in self.ex.events])
        self.assertEqual(
            len(self.zone(self.p0, ZONE_LIBRARY)),
            2,  # 4 - 2 searched
        )


# -------------------------------------------------------------- Bad Deal


class TestBadDeal(unittest.TestCase):
    """Bad Deal e2e. Candidate cards ONLY in the opponent's hand, created
    BEFORE the library cards so the Handle-sorted CHOOSE stand-in lands
    there and the drawer's fresh draws are never discarded."""

    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=7)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.d1 = self.world.add_card(card_id("D1"), self.p1, ZONE_HAND)
        self.d2 = self.world.add_card(card_id("D2"), self.p1, ZONE_HAND)
        self.libs = [
            self.world.add_card(card_id(f"L{i}", type_line="Basic Land"), self.p0)
            for i in (1, 2, 3, 4)
        ]
        self.ex = Executor(self.world)

    def zone(self, player, kind):
        return self.world.players[player].zone(kind).entries

    def test_bad_deal_e2e(self):
        inner = golden("Bad Deal")["abilities"][0]["effect"]["steps"]
        seq_inner = [from_dict("Atom", s) for s in inner[0]["steps"]]
        lose_life = from_dict("Atom", inner[1])
        self.assertEqual([a.verb.name for a in seq_inner], ["DRAW", "DISCARD"])
        fire = lambda n: self.ex.execute(n, source=self.p0, controller=self.p0)
        fire(seq_inner[0])  # DRAW 2 (YOU = p0)
        fire(seq_inner[1])  # DISCARD 2 (CHOOSE ANY hand -> stand-in)
        fire(lose_life)  # LOSE_LIFE 2 (ANY)
        self.assertEqual(self.zone(self.p0, ZONE_HAND), [self.libs[3], self.libs[2]])
        self.assertEqual(self.zone(self.p1, ZONE_HAND), [])
        gy = self.zone(self.p1, ZONE_GRAVEYARD)
        self.assertIn(self.d1, gy)
        self.assertIn(self.d2, gy)
        self.assertEqual(self.world.players[self.p0].life, 18)
        self.assertEqual(self.world.players[self.p1].life, 18)


# ------------------------------------------------------------- FLIP_COIN


def _flip_outcome(seed: int):
    """(winner_is_flipper, heads) for a minimal p0-flips world under ``seed``."""
    reset_oracle_ids()
    world = GameWorld(num_players=2, start_life=20, master_seed=seed)
    p0, _p1 = world.player_order[0], world.player_order[1]
    ex = Executor(world)
    events = ex.execute(atom(Verb.FLIP_COIN), source=p0, controller=p0)
    heads = events[0][2] == "HEADS"
    return (ex.last_flip_won_by == p0), heads


class TestFlipCoin(LibraryCase):
    def test_same_seed_same_winner_across_two_executors(self):
        winners = []
        for _ in range(2):
            reset_oracle_ids()
            world = GameWorld(num_players=2, start_life=20, master_seed=7)
            p0 = world.player_order[0]
            ex = Executor(world)
            ex.execute(atom(Verb.FLIP_COIN), source=p0, controller=p0)
            winners.append(ex.last_flip_won_by)
        self.assertEqual(winners[0], winners[1])

    def test_crafted_seeds_yield_opposite_coins(self):
        heads_flipper = tails_flipper = None
        for seed in range(60):
            flipper_won, heads = _flip_outcome(seed)
            if heads and heads_flipper is None:
                heads_flipper = (seed, flipper_won)
            if not heads and tails_flipper is None:
                tails_flipper = (seed, flipper_won)
            if heads_flipper and tails_flipper:
                break
        self.assertIsNotNone(heads_flipper, "no HEADS seed found in 60")
        self.assertIsNotNone(tails_flipper, "no TAILS seed found in 60")
        assert heads_flipper is not None and tails_flipper is not None
        self.assertTrue(heads_flipper[1])  # heads -> the flipper wins
        self.assertFalse(tails_flipper[1])  # tails -> the opponent wins

    def test_flip_won_raises_cleanly_without_a_recorded_flip(self):
        cond = Conditional(
            pred=FLIP_WON_YOU,
            then_effect=atom(
                Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(6)
            ),
            else_effect=None,
        )
        with self.assertRaises(NotImplementedError):
            self._do(cond)  # executor present, no flip recorded yet
        bare = ExecCtx(
            world=self.world,
            ledger=DurationLedger(),
            controller=self.p0,
            source=self.p0,
            bindings={},
            decisions=(),
        )
        self.assertIsNone(bare.executor)
        with self.assertRaises(NotImplementedError):
            eval_filter(FLIP_WON_YOU, self.p0, bare)  # no executor at all

    def test_tavern_swindler_e2e_flip_then_conditional_gain(self):
        """AMENDED 2026-09-30 (round 14e, B-17): the golden is ONE ability
        row now — the activation owns the flip AND its winner-gate tail
        (Seq(FLIP_COIN; IF(FLIP_WON)→GAIN_LIFE)); the 13a two-row split
        (tail parked on a card-level SpellAbility, raising at cast) was the
        ruled miscompile. The whole activation runs in ONE apply_effect; the
        gate is still judged off the executor's flip ledger."""
        rec = golden("Tavern Swindler")["abilities"]
        self.assertEqual(
            [a["tag"] for a in rec], ["ActivatedAbility"]
        )  # the SpellAbility row is GONE (capture)
        whole = from_dict("Seq", rec[0]["effect"])
        cond = whole.steps[1]  # IF(FLIP_WON) → GAIN_LIFE
        seed = next(s for s in range(60) if _flip_outcome(s)[1])  # a HEADS seed
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=seed)
        p0, p1 = world.player_order[0], world.player_order[1]
        ex = Executor(world)
        ex.apply_effect(whole, source=p0, controller=p0)  # heads for this seed
        self.assertIs(ex.last_flip_won_by, p0)
        self.assertEqual(world.players[p0].life, 26)  # +6: YOU won, in-game
        ex.apply_effect(cond, source=p0, controller=p1)
        self.assertEqual(world.players[p1].life, 20)  # YOU(p1) did not win


# ------------------------------------------------------------- END_TURN


class TestEndTurn(LibraryCase):
    def _markers(self):
        return [e.data[0] for e in self.journal_rows("TURN_PHASE")]

    def test_end_turn_atom_closes_turn_once(self):
        self.ex.begin_turn(self.p0)
        self.assertTrue(self.ex.turn_open)
        self._do(atom(Verb.END_TURN))
        self.assertFalse(self.ex.turn_open)
        self.assertEqual(self.ex.phase, "END_TURN")
        self.assertEqual(self._markers().count("END_TURN"), 1)
        self.assertFalse(self.ex.end_turn_requested)  # consumed at the op edge

    def test_advance_turn_after_early_end_turn_no_duplicate_marker(self):
        self.ex.begin_turn(self.p0)
        self._do(atom(Verb.END_TURN))
        self.ex.advance_turn()
        self.assertEqual(self._markers().count("END_TURN"), 1)
        self.assertIs(self.world.active_player, self.p1)
        self.assertEqual(self.ex.phase, "FIRST_MAIN")


# ----------------------------------------------------------- EXTRA_TURN


class TestExtraTurn(LibraryCase):
    def test_extra_turn_queue_drains_before_round_robin(self):
        self.ex.begin_turn(self.p0)  # turn 1: p0
        self._do(atom(Verb.EXTRA_TURN, count=QConst(2)))
        self.assertEqual(self.ex.extra_turn_queue, [self.p0, self.p0])
        self.ex.advance_turn()  # queued extra turn -> p0 again
        self.assertIs(self.world.active_player, self.p0)
        self.ex.advance_turn()  # the second queued extra turn -> still p0
        self.assertIs(self.world.active_player, self.p0)
        self.ex.advance_turn()  # queue drained -> round-robin resumes at p1
        self.assertIs(self.world.active_player, self.p1)
        self.assertEqual(self.ex.extra_turn_queue, [])


# -------------------------------------------------------------- LOSE_GAME


class TestLoseGame(LibraryCase):
    def test_lose_game_records_player_and_journal_row(self):
        self._do(atom(Verb.LOSE_GAME))
        self.assertEqual(self.ex.lost_players, [self.p0])
        rows = [e for e in self.ex.events if e[1] == "LOSE_GAME"]
        self.assertEqual(rows, [(rows[0][0], "LOSE_GAME", str(self.p0))])


# ------------------------------------------------------ LOYALTY (Catalyst)


class TestLoyaltyLedger(LibraryCase):
    def setUp(self):
        super().setUp()
        self.pw = self.world.add_card(
            card_id(
                "Chandra, Flame's Catalyst",
                type_line="Legendary Planeswalker — Chandra",
                cmc=6,
                loyalty="5",
            ),
            self.p0,
            ZONE_BATTLEFIELD,
        )
        self.ex.attach_card(
            self.pw,
            record(
                "Chandra, Flame's Catalyst",
                oid=self.world.cards[self.pw].identity.oracle_id,
            ),
        )
        self.ex.begin_turn(self.p0)

    def playable(self, idx, seat=None):
        return ability_playable(self.world, self.ex, self.pw, idx, seat=seat or self.p0)

    def activate_pw(self, idx, **kw):
        return activate(self.ex, self.pw, idx, seat=self.p0, **kw)

    def loyalty(self):
        return self.world.cards[self.pw].counters.get(CounterKind.LOYALTY.name)

    def test_attach_seeds_the_loyalty_counter(self):
        self.assertEqual(self.loyalty(), 5)

    def test_plus_one_raises_the_ledger_and_journals(self):
        self.activate_pw(0)  # +1: DEAL_DAMAGE 3 to all opponents
        self.assertEqual(self.loyalty(), 6)
        self.assertIs(self.world.active_player, self.p0)
        self.assertEqual(self.world.players[self.p1].life, 17)
        rows = [e for e in self.journal_rows("COUNTER_PLACED") if e.subject == self.pw]
        self.assertEqual([r.data for r in rows], [("LOYALTY", 1)])

    def test_minus_two_pays_and_sets_the_clock(self):
        self.activate_pw(1, decisions=["skip"])  # −2, skip the CAST (13b)
        self.assertEqual(self.loyalty(), 3)
        self.assertEqual(self.loyalty_clock_for_pw(), self.world.turn)

    def loyalty_clock_for_pw(self):
        return self.ex.loyalty_clock.get(self.pw)

    def test_second_loyalty_ability_same_turn_is_gated(self):
        self.activate_pw(1, decisions=["skip"])
        self.assertEqual(self.playable(3), "window:loyalty:once_per_turn")

    def test_next_turn_clears_the_once_per_turn_clock(self):
        self.activate_pw(1, decisions=["skip"])
        self.assertIsNotNone(self.playable(1))
        self.ex.advance_turn()
        self.ex.advance_turn()  # back to p0, world.turn advanced
        self.assertIsNone(self.playable(1))

    def test_minus_eight_legality_tracks_the_ledger(self):
        self.assertEqual(self.playable(3), "cost:loyalty:5<8")
        self.world.cards[self.pw].counters[CounterKind.LOYALTY.name] = 8
        self.assertEqual(self.playable(3), None)

    def test_zero_loyalty_sends_the_pw_to_the_graveyard(self):
        self.world.cards[self.pw].counters[CounterKind.LOYALTY.name] = 8
        self.activate_pw(3)  # −8: DISCARD hand + DRAW 7
        self.assertEqual(self.world.zone_of(self.pw).kind, ZONE_GRAVEYARD)
        dies = [e for e in self.journal_rows("CREATURE_DIES") if e.subject == self.pw]
        self.assertEqual(len(dies), 1)

    def test_non_planeswalker_never_seeds_and_never_pays(self):
        art = self.world.add_card(
            card_id("Urn", type_line="Artifact"), self.p0, ZONE_BATTLEFIELD
        )

        def urn_cost(delta):
            return record_of(
                [
                    ActivatedAbility(
                        cost=Cost((CostLoyalty(delta=delta),)),
                        effect=atom(
                            Verb.GAIN_LIFE,
                            controller=ControllerRef.YOU,
                            amount=QConst(1),
                        ),
                    )
                ],
                name="Urn",
                oid=self.world.cards[art].identity.oracle_id,
            )

        self.ex.attach_card(art, urn_cost(-1))
        self.assertNotIn(CounterKind.LOYALTY.name, self.world.cards[art].counters)
        # AMENDED (round 13b — the flip this pin invited): 13a's guard only
        # fired for delta < 0 and it reported a SHORTAGE ("0<1") on a card
        # with no loyalty identity at all. CR 606.1b gates the SOURCE, not
        # the amount: an artifact with no printed loyalty and no LOYALTY
        # counters cannot pay a loyalty cost of EITHER sign, and the reason
        # names why — not_planeswalker, not a bogus 0<1 shortfall.
        self.assertEqual(
            ability_playable(self.world, self.ex, art, 0, seat=self.p0),
            "cost:loyalty:not_planeswalker",
        )
        # The +1 side (13a's KNOWN MISMATCH, payable and landing a LOYALTY
        # counter on an artifact) is closed by the same symmetric guard.
        self.ex.attach_card(art, urn_cost(+1))
        self.assertEqual(
            ability_playable(self.world, self.ex, art, 0, seat=self.p0),
            "cost:loyalty:not_planeswalker",
        )
        self.assertNotIn("LOYALTY", self.world.cards[art].counters)
        self.assertEqual(self.ex.loyalty_clock, {})  # no loyalty act, no clock entry


# ------------------------------------------------------ SORCERY WINDOW


class TestSorceryPhaseGate(LibraryCase):
    def setUp(self):
        super().setUp()
        self.perm = self.world.add_card(card_id("Permute"), self.p0, ZONE_BATTLEFIELD)
        rec = record_of(
            [
                ActivatedAbility(
                    cost=Cost(()),
                    effect=atom(
                        Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(1)
                    ),
                    timing=ActivationWindow.SORCERY,
                )
            ],
            name="Permute",
            oid=self.world.cards[self.perm].identity.oracle_id,
        )
        self.ex.attach_card(self.perm, rec)

    def playable(self):
        return ability_playable(self.world, self.ex, self.perm, 0, seat=self.p0)

    def test_sorcery_gate_tracks_the_phase_clock(self):
        self.ex.begin_turn(self.p0)  # active p0, clock ends at FIRST_MAIN
        self.assertEqual(self.playable(), None)
        for phase in ("UPKEEP", "END_TURN"):
            self.ex.phase = phase
            self.assertEqual(self.playable(), "window:sorcery:phase")
        self.ex.phase = "FIRST_MAIN"
        self.assertEqual(self.playable(), None)


# ------------------------------------------------------------ QUERY: SEARCH


class TestLegalSearch(LibraryCase):
    def test_legal_search_returns_handle_sorted_candidates(self):
        steps = golden("Cultivate")["abilities"][0]["effect"]["steps"]
        node = from_dict("Atom", steps[0])
        got = legal_search(self.world, self.ex, node, seat=self.p0)
        self.assertEqual(list(got), sorted(self.libs))
        # the Selector directly is accepted too
        got2 = legal_search(self.world, self.ex, node.args.get("cards"), seat=self.p0)
        self.assertEqual(got, got2)


# ---------------------------------------------------------------- REPLAY


class TestReplayDeterminism(unittest.TestCase):
    def test_same_script_equal_fingerprints(self):
        def replay():
            reset_oracle_ids()
            world = GameWorld(num_players=2, start_life=20, master_seed=13)
            p0, _p1 = world.player_order[0], world.player_order[1]
            libs = [
                world.add_card(card_id(f"R{i}", type_line="Basic Land"), p0)
                for i in (1, 2, 3, 4)
            ]
            ex = Executor(world)
            ex.begin_turn(p0)
            ex.execute(
                atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1)),
                source=p0,
                controller=p0,
            )
            ex.execute(atom(Verb.FLIP_COIN), source=p0, controller=p0)
            ex.execute(
                search_atom(destination=HAND_YOU),
                source=p0,
                controller=p0,
                bindings={"cards": [libs[0]]},
            )
            ex.execute(atom(Verb.EXTRA_TURN, count=QConst(1)), source=p0, controller=p0)
            ex.advance_turn()  # the extra turn: p0 again
            ex.execute(atom(Verb.END_TURN), source=p0, controller=p0)
            ex.advance_turn()
            ex.execute(atom(Verb.LOSE_GAME), source=p0, controller=p0)
            return ex.state_fingerprint()

        self.assertEqual(replay(), replay())


# ------------------------------------------------------- capability pins


class TestCapabilitySurface(unittest.TestCase):
    def test_v2_derives_the_growth_set_v1_stays_frozen(self):
        # AMENDED (round 13b): the derivation grew five more — the cast-
        # side flip set (PAY, CAST, CHOOSE, CHOOSE_NAME, MANA_POLICY).
        # V1 stays the frozen round-12 contract (24); COUNTER_SPELL is
        # deliberately NOT in the growth: no interaction window in v1.
        # AMENDED 2026-09-30 (round 13c): four more — the permissions
        # flip set (GET_EMBLEM, GRANT_TYPE, GRANT_ACTIVATION,
        # ADD_LAND_PLAY), 35 -> 39. PHASE_OUT (Teferi's co-verb) stays
        # out: its handler is 13d's, not this round's.
        new = {
            Verb.DRAW,
            Verb.SEARCH,
            Verb.FLIP_COIN,
            Verb.END_TURN,
            Verb.EXTRA_TURN,
            Verb.LOSE_GAME,
            Verb.PAY,
            Verb.CAST,
            Verb.CHOOSE,
            Verb.CHOOSE_NAME,
            Verb.MANA_POLICY,
            Verb.GET_EMBLEM,
            Verb.GRANT_TYPE,
            Verb.GRANT_ACTIVATION,
            Verb.ADD_LAND_PLAY,
        }
        self.assertEqual(SUPPORTED_VERBS_V2 - SUPPORTED_VERBS_V1, new)
        self.assertNotIn(Verb.DRAW, SUPPORTED_VERBS_V1)  # the round-12 freeze
        self.assertEqual(len(SUPPORTED_VERBS_V1), 24)
        self.assertEqual(len(SUPPORTED_VERBS_V2), 39)

    def test_turn_ledger_fields_in_state_fingerprint(self):
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=3)
        p0 = world.player_order[0]
        a = Executor(world)
        fp0 = a.state_fingerprint()
        a.execute(atom(Verb.LOSE_GAME), source=p0, controller=p0)
        self.assertNotEqual(fp0, a.state_fingerprint())


if __name__ == "__main__":
    unittest.main()
