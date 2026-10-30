"""Engine fixes from the M21 verification campaign, fixer 4 (2026-10-29).

V36  The cleanup step (CR 514). The active player discards down to their maximum
     hand size, seven (CR 514.1, 402.2), choosing the cards through visible asks
     (CR 701.9b); then damage and "until end of turn" effects end (514.2); then
     state-based actions and waiting triggers are handled, and if anything happened
     another cleanup step follows (514.3a).
V37  "End the turn" (CR 724.1). Triggers that triggered before the process cease to exist
     (724.1a); the stack is exiled (724.1b); state-based actions are checked with no trigger
     put on the stack (724.1c); the end step is skipped, so "at the beginning of the end
     step" abilities do not trigger (724.1d-e); the turn goes straight to its cleanup step,
     where the triggers from the process resolve before another cleanup step (724.1f). Nothing
     acts after the turn has ended: Executor.end_turn and the act windows do nothing.
V39  Quirion Dryad: a spell "that's white, blue, black, or red" is a spell with at least one of
     those colors (CR 105.2, 105.2b), so a green-blue spell counts. The compiler wrote a subset
     test (COLOR_IN); it now writes the canonical FOr of COLOR_HAS.
"""

import unittest
from unittest import mock

from MTG_bot.bench.router import SeatRouter
from MTG_bot.bench.view import OracleIndex, SeatLens
from MTG_bot.core.ability_tree import (
    ControllerRef,
    Cost,
    CostManaColor,
    CounterKind,
    CreatureDiesEvent,
    DurationEot,
    FAtom,
    FAtomPred,
    LifeGainedEvent,
    Phase,
    PtDelta,
    PtDirection,
    QConst,
    Seq,
    SpellKind,
    TriggeredAbility,
    TurnPhaseEvent,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.executor import MAX_HAND_SIZE, Executor
from MTG_bot.core.executor import games as games_module
from MTG_bot.core.executor.events import KIND_TURN_PHASE, KIND_ZONE_CHANGE
from MTG_bot.core.executor.games import (
    RandomPolicy,
    _setup_game,
    deal_decks,
    get_supply,
)
from MTG_bot.core.executor.quantity import eval_filter
from MTG_bot.core.executor.query import legal_activations
from MTG_bot.core.executor.stack import cast, play_land
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import (
    IS_SOURCE,
    atom,
    card_id,
    gain,
    record_of,
    referent_sel,
    reset_oracle_ids,
)
from MTG_bot.core.test_executor_stack import any_target, spell_rec

YOU = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)


class Case(unittest.TestCase):
    def setUp(self):
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=7)
        self.p0, self.p1 = self.world.player_order
        self.ex = Executor(self.world)
        self.asks: list[tuple[str, tuple[str, ...], object]] = []
        self.script: list[str] = []
        self.ex.decisions.provider = self.provider

    def provider(self, vocab, what):
        self.asks.append((what, tuple(vocab), self.ex.decisions.asking_seat))
        return self.script.pop(0) if self.script else vocab[0]

    def hand(self, seat, n, prefix="H"):
        return [
            self.world.add_card(card_id(f"{prefix}{i}", "1", "1"), seat, ZONE_HAND)
            for i in range(n)
        ]

    def zone(self, card):
        return self.world.zone_of(card).kind

    def attach_new(self, name, *abilities, seat=None):
        """A 2/2 creature on ``seat``'s battlefield carrying ``abilities``."""
        identity = card_id(name, "2", "2")
        handle = self.world.add_card(identity, seat or self.p0, ZONE_BATTLEFIELD)
        self.ex.attach_card(
            handle, record_of(list(abilities), name=name, oid=identity.oracle_id)
        )
        return handle


class CleanupDiscardTest(Case):
    """V36 (CR 514.1, 402.2, 701.9b)."""

    def test_maximum_hand_size_is_seven(self):
        self.assertEqual(MAX_HAND_SIZE, 7)  # CR 402.2: normally seven

    def test_active_player_discards_down_to_seven_choosing_the_cards(self):
        cards = self.hand(self.p0, 9)
        self.ex.begin_turn(self.p0)  # empty library: the draw step draws nothing
        self.script = [str(cards[5]), str(cards[2])]
        self.ex.end_turn()
        discards = [a for a in self.asks if a[0].startswith("discard:")]
        self.assertEqual(len(discards), 2)  # one ask per excess card
        for what, _vocab, seat in discards:
            self.assertTrue(what.startswith(f"discard:{self.p0}:cleanup:"), what)
            self.assertEqual(seat, self.p0)  # the active player decides
        # The first ask offers the whole hand, the second the rest of it.
        self.assertEqual(discards[0][1], tuple(sorted(str(c) for c in cards)))
        self.assertEqual(len(discards[1][1]), 8)
        self.assertNotIn(str(cards[5]), discards[1][1])
        self.assertEqual(self.zone(cards[5]), ZONE_GRAVEYARD)
        self.assertEqual(self.zone(cards[2]), ZONE_GRAVEYARD)
        kept = [c for c in cards if c not in (cards[5], cards[2])]
        self.assertTrue(all(self.zone(c) == ZONE_HAND for c in kept))
        self.assertEqual(len(self.world.players[self.p0].zone(ZONE_HAND).entries), 7)
        # Each discard is one hand -> graveyard zone change in the journal.
        moves = [
            e
            for e in self.ex.journal.events
            if e.kind == KIND_ZONE_CHANGE and e.subject in (cards[5], cards[2])
        ]
        self.assertEqual([m.zone_move[:2] for m in moves], [("hand", "graveyard")] * 2)

    def test_seven_cards_ask_nothing(self):
        self.hand(self.p0, 7)
        self.ex.begin_turn(self.p0)
        self.ex.end_turn()
        self.assertEqual(self.asks, [])
        self.assertEqual(len(self.world.players[self.p0].zone(ZONE_HAND).entries), 7)

    def test_only_the_active_player_discards(self):
        self.hand(self.p1, 9, prefix="O")
        self.ex.begin_turn(self.p0)
        self.ex.end_turn()
        self.assertEqual(self.asks, [])
        self.assertEqual(len(self.world.players[self.p1].zone(ZONE_HAND).entries), 9)

    def test_the_discard_triggers_resolve_in_the_same_cleanup(self):
        # CR 514.3a: a trigger the discard causes resolves during this cleanup
        # step, before the turn ends, not at the start of the next turn.
        self.attach_new(
            "Watcher",
            TriggeredAbility(
                event=ZoneChangeEvent(
                    from_zone=Zone(ZoneKind.HAND, ControllerRef.YOU),
                    to_zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                ),
                condition=None,
                effect=gain(1),
            ),
        )
        self.hand(self.p0, 9)
        self.ex.begin_turn(self.p0)
        self.ex.end_turn()
        self.assertEqual(self.world.players[self.p0].life, 22)  # two discards, two triggers

    def test_state_based_actions_are_checked_in_the_cleanup_step(self):
        # CR 514.3a: a 1/1 with a -1/-1 counter lives on a +0/+1 until end of
        # turn; when that effect ends in the cleanup step it is a 0/0, and the
        # state-based action puts it into the graveyard during the cleanup step.
        self.ex.begin_turn(self.p0)
        frail = self.world.add_card(card_id("Frail", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.world.cards[frail].counters["MINUS_1_MINUS_1"] = 1
        self.ex.execute(
            atom(
                Verb.MODIFY_PT,
                target=referent_sel("source"),
                toughness=PtDelta(PtDirection.INCREASE, QConst(1)),
                duration=DurationEot(),
            ),
            source=frail,
            controller=self.p0,
        )
        self.assertEqual(self.zone(frail), ZONE_BATTLEFIELD)
        self.ex.end_turn()
        self.assertEqual(self.zone(frail), ZONE_GRAVEYARD)

    def test_replays_are_identical(self):
        def run():
            reset_oracle_ids()
            world = GameWorld(num_players=2, start_life=20, master_seed=11)
            p0, _p1 = world.player_order
            cards = [
                world.add_card(card_id(f"H{i}", "1", "1"), p0, ZONE_HAND) for i in range(10)
            ]
            ex = Executor(world)
            ex.decisions.provider = lambda vocab, what: vocab[-1]
            ex.begin_turn(p0)
            ex.end_turn()
            return ex.state_fingerprint(), tuple(
                c for c in cards if world.zone_of(c).kind == ZONE_GRAVEYARD
            )

        first, second = run(), run()
        self.assertEqual(first, second)
        self.assertEqual(len(first[1]), 3)


class EndTheTurnTest(Case):
    """V37 (CR 724.1, all subrules)."""

    def setUp(self):
        super().setUp()
        self.ex.begin_turn(self.p0)

    def spell(self, name, effect):
        """An instant costing {U} in p0's hand, with {U} in p0's pool to cast it."""
        rec = spell_rec(name, SpellKind.INSTANT, cost=Cost((CostManaColor("U", QConst(1)),)), effect=effect)
        handle = self.world.add_card(
            CardIdentity(oracle_id=rec.oracle_id, name=name, type_line="Instant", cmc=1),
            self.p0,
            ZONE_HAND,
        )
        self.ex.attach_card(handle, rec)
        pool = self.world.players[self.p0].mana_pool
        pool["U"] = pool.get("U", 0) + 1
        return handle

    def end_steps(self):
        return [e for e in self.ex.journal.events if e.kind == KIND_TURN_PHASE and e.data[0] == "END_TURN"]

    def test_the_end_step_is_skipped(self):
        # 724.1d-e: "at the beginning of the end step" abilities do not trigger.
        self.attach_new(
            "Assassin",
            TriggeredAbility(event=TurnPhaseEvent(Phase.END_TURN, YOU), condition=None, effect=gain(1)),
        )
        disc = self.spell("Discontinuity", atom(Verb.END_TURN))
        cast(self.ex, self.p0, disc)
        self.assertEqual(self.world.players[self.p0].life, 20)
        self.assertEqual(self.end_steps(), [])
        self.assertFalse(self.ex.turn_open)
        self.assertEqual(self.zone(disc), ZONE_EXILE)  # 724.1b: the resolving spell is exiled
        # The turn is over: a driver's end_turn (the game loop calls it) does nothing.
        self.assertEqual(self.ex.end_turn(), 0)
        self.assertEqual(self.end_steps(), [])
        self.assertEqual(self.world.players[self.p0].life, 20)
        self.ex.advance_turn()
        self.assertIs(self.world.active_player, self.p1)
        self.assertEqual(self.end_steps(), [])

    def test_the_cleanup_step_still_happens(self):
        # 724.1d: straight to the cleanup step: damage wears off, "until end of
        # turn" effects end, and the active player discards down to seven.
        bear = self.attach_new("Bear")
        self.ex.execute(
            atom(
                Verb.MODIFY_PT,
                target=referent_sel("source"),
                power=PtDelta(PtDirection.INCREASE, QConst(3)),
                duration=DurationEot(),
            ),
            source=bear,
            controller=self.p0,
        )
        self.ex.mark_damage(bear, 1)
        cards = self.hand(self.p0, 8)  # eight cards stay in hand once the spell is cast
        disc = self.spell("Discontinuity", atom(Verb.END_TURN))
        self.script = [str(cards[3])]
        cast(self.ex, self.p0, disc)
        power, _toughness = self.ex.ledger.effective_pt(self.world.cards[bear].identity, bear)
        self.assertEqual(power, 2)
        self.assertEqual(self.ex.damage.get(bear, 0), 0)
        discards = [a for a in self.asks if a[0].startswith(f"discard:{self.p0}:cleanup:")]
        self.assertEqual(len(discards), 1)
        self.assertEqual(self.zone(cards[3]), ZONE_GRAVEYARD)
        self.assertEqual(len(self.world.players[self.p0].zone(ZONE_HAND).entries), 7)
        self.assertEqual(self.end_steps(), [])

    def test_triggers_from_before_the_process_cease_to_exist(self):
        # 724.1a: the life gain happens during the resolution, before "end the
        # turn"; the ability it triggered was never put onto the stack, so it
        # ceases to exist.
        pridemate = self.attach_new(
            "Pridemate",
            TriggeredAbility(
                event=LifeGainedEvent(actor=YOU),
                condition=None,
                effect=atom(
                    Verb.PUT_COUNTER,
                    target=referent_sel("source"),
                    counter_kind=CounterKind.PLUS_1_PLUS_1,
                    count=QConst(1),
                ),
            ),
        )
        spell = self.spell("Time Out", Seq((gain(1), atom(Verb.END_TURN))))
        cast(self.ex, self.p0, spell)
        self.assertEqual(self.world.players[self.p0].life, 21)
        self.assertEqual(self.world.cards[pridemate].counters.get("PLUS_1_PLUS_1", 0), 0)
        self.assertFalse(self.ex.turn_open)

    def test_state_based_actions_then_the_process_triggers_in_cleanup(self):
        # 724.1c: the creature the spell dealt lethal damage dies before the
        # cleanup step removes damage; its dies trigger, triggered during the
        # process, resolves in the cleanup step (724.1f).
        victim = self.attach_new(
            "Victim",
            TriggeredAbility(
                event=CreatureDiesEvent(IS_SOURCE), condition=None, effect=gain(3)
            ),
        )
        spell = self.spell(
            "Burn Out",
            Seq((atom(Verb.DEAL_DAMAGE, target=any_target(), amount=QConst(2)), atom(Verb.END_TURN))),
        )
        cast(self.ex, self.p0, spell, targets=(victim,))
        self.assertEqual(self.zone(victim), ZONE_GRAVEYARD)
        self.assertEqual(self.world.players[self.p0].life, 23)
        self.assertEqual(self.end_steps(), [])


class FirstActAgent:
    """Takes the first option that is not PASS whenever there is one."""

    name = "first-act"

    def decide(self, ask, obs):
        return 1 if len(ask.options) > 1 else 0


class ActWindowAfterTheTurnEndedTest(unittest.TestCase):
    """V37: once an effect has ended the turn, no player gets priority in it
    again (CR 724.1f), so the act windows offer nothing."""

    def game_with_a_land(self):
        """The first seeded deal whose opening hand holds a basic land, played: the
        act menu then offers its mana ability."""
        supply = get_supply("castable", "M21")
        basics = ("Plains", "Island", "Swamp", "Mountain", "Forest")
        for seed in range(1, 40):
            game = _setup_game(seed, supply, deal_decks(seed, 1409, supply))
            world = game.world
            p0 = world.player_order[0]
            game.executor.begin_turn(p0)
            hand = world.players[p0].zone(ZONE_HAND).entries
            lands = [h for h in hand if world.cards[h].identity.name in basics]
            if not lands:
                continue
            play_land(game.executor, p0, lands[0])
            self.assertTrue(legal_activations(world, game.executor, p0))
            return game, supply, p0
        self.fail("no seed deals a basic land")

    def end_the_turn(self, game, p0):
        game.executor.execute(atom(Verb.END_TURN), source=p0, controller=p0)
        self.assertFalse(game.executor.turn_open)

    def test_the_engine_policy_takes_no_act(self):
        game, _supply, p0 = self.game_with_a_land()
        policy = RandomPolicy(3)
        game.executor.decisions.provider = policy.answer
        self.end_the_turn(game, p0)
        # A policy that never walks away and always taps mana when it can: with the
        # window still open it would tap the land at once.
        with mock.patch.object(games_module, "PASS_P", 0.0), mock.patch.object(
            games_module, "TAP_MANA_P", 1.0
        ):
            policy.take_acts(game, p0)
        self.assertEqual(game.acts, 0)

    def test_the_bench_router_takes_no_act(self):
        game, supply, p0 = self.game_with_a_land()
        lenses = [SeatLens(0, OracleIndex.for_sets("M21")), SeatLens(1, OracleIndex.for_sets("M21"))]
        router = SeatRouter(game, [FirstActAgent(), FirstActAgent()], lenses, supply=supply)
        game.executor.decisions.provider = router.answer
        self.end_the_turn(game, p0)
        router.take_acts(game, p0)
        self.assertEqual(game.acts, 0)


class QuirionDryadColorTest(unittest.TestCase):
    """V39 (CR 105.2, 105.2b)."""

    def test_the_compiled_trigger_reads_any_of_the_four_colors(self):
        supply = get_supply("all", "M21")
        record = next(r.card for r in supply.pool.results.values() if r.card.name == "Quirion Dryad")
        trigger = next(a for a in record.abilities if isinstance(a, TriggeredAbility))
        reset_oracle_ids()
        world = GameWorld(num_players=2, start_life=20, master_seed=7)
        p0 = world.player_order[0]
        ex = Executor(world)
        ctx = ex._ctx(source=p0, controller=p0, bindings=None, decisions=())
        expected = {
            ("G", "U"): True,  # green AND blue: a spell that's blue
            ("U",): True,
            ("B", "W"): True,
            ("G", "R"): True,
            ("G",): False,
            (): False,  # colorless
        }
        for colors, fires in expected.items():
            spell = world.add_card(
                card_id("Spell" + "".join(colors), type_line="Instant", colors=colors), p0, ZONE_HAND
            )
            self.assertEqual(eval_filter(trigger.event.filter, spell, ctx), fires, colors)


if __name__ == "__main__":
    unittest.main()
