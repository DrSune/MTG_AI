"""Engine fixes from the M21 verification campaign, fixer 4 (2026-10-29).

V36  The cleanup step (CR 514). The active player discards down to their maximum
     hand size, seven (CR 514.1, 402.2), choosing the cards through visible asks
     (CR 701.9b); then damage and "until end of turn" effects end (514.2); then
     state-based actions and waiting triggers are handled, and if anything happened
     another cleanup step follows (514.3a).
"""

import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    DurationEot,
    PtDelta,
    PtDirection,
    QConst,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.executor import MAX_HAND_SIZE, Executor
from MTG_bot.core.executor.events import KIND_ZONE_CHANGE
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND, GameWorld
from MTG_bot.core.test_executor_binding import (
    atom,
    card_id,
    gain,
    record_of,
    referent_sel,
    reset_oracle_ids,
)


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


if __name__ == "__main__":
    unittest.main()
