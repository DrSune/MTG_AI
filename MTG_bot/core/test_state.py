"""Tests for the deterministic canonical state model.

These pin down the replay contract: two worlds built the same way with the
same seed must have identical fingerprints, and trigger ordering must be a
function of (controller seat, clock) only — never of set iteration order.
That is the property P12 (byte-identical replay) and loop detection build on.
"""

import unittest

from MTG_bot.core.state import (
    GameWorld,
    ZONE_LIBRARY,
    ZONE_HAND,
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
)
from MTG_bot.core.identity import CardIdentity

# Two distinct stable oracle ids so cards are distinguishable.
ORACLE_A = "11111111-1111-1111-1111-111111111111"
ORACLE_B = "22222222-2222-2222-2222-222222222222"
ORACLE_C = "33333333-3333-3333-3333-333333333333"


def card(oracle: str, name: str) -> CardIdentity:
    return CardIdentity(oracle_id=oracle, name=name)


def build_world(n: int = 2, seed: int = 7) -> GameWorld:
    w = GameWorld(num_players=n, start_life=20, master_seed=seed)
    p0, p1 = w.player_order[0], w.player_order[1]
    w.add_card(card(ORACLE_A, "Card A"), p0)
    w.add_card(card(ORACLE_B, "Card B"), p0)
    w.add_card(card(ORACLE_C, "Card C"), p1)
    return w


class TestHandles(unittest.TestCase):
    def test_players_and_cards_use_separate_namespaces(self):
        w = build_world()
        p = w.player_order[0]
        c = w.add_card(card(ORACLE_A, "A"), p)
        self.assertEqual(p.namespace, "player")
        self.assertEqual(c.namespace, "card")
        # Both could be index 0 and never collide.
        self.assertNotEqual(p, c)

    def test_handles_are_stable_integers(self):
        w = build_world()
        c = w.add_card(card(ORACLE_A, "A"), w.player_order[0])
        self.assertIsInstance(c.index, int)
        self.assertEqual(str(c), f"card:{c.index}")


class TestZones(unittest.TestCase):
    def test_add_card_goes_to_library(self):
        w = build_world()
        p0 = w.player_order[0]
        c = w.add_card(card(ORACLE_A, "A"), p0)
        lib = w.players[p0].zone(ZONE_LIBRARY)
        self.assertIn(c, lib.entries)

    def test_move_card_updates_both_zones(self):
        w = build_world()
        p0 = w.player_order[0]
        c = w.add_card(card(ORACLE_A, "A"), p0)
        w.move_to_zone(c, p0, ZONE_HAND)
        self.assertNotIn(c, w.players[p0].zone(ZONE_LIBRARY).entries)
        self.assertIn(c, w.players[p0].zone(ZONE_HAND).entries)

    def test_zone_order_is_entry_order(self):
        w = GameWorld(num_players=1, master_seed=1)
        p = w.player_order[0]
        a = w.add_card(card(ORACLE_A, "A"), p, ZONE_BATTLEFIELD)
        b = w.add_card(card(ORACLE_B, "B"), p, ZONE_BATTLEFIELD)
        c = w.add_card(card(ORACLE_C, "C"), p, ZONE_BATTLEFIELD)
        self.assertEqual(w.players[p].zone(ZONE_BATTLEFIELD).entries, [a, b, c])

    def test_zone_of_unknown_card_raises(self):
        from MTG_bot.core.identity import Handle

        w = build_world()
        ghost = Handle("card", 999)
        with self.assertRaises(KeyError):
            w.zone_of(ghost)

    def test_controller_of(self):
        w = build_world()
        p1 = w.player_order[1]
        c = w.add_card(card(ORACLE_C, "C"), p1)
        self.assertEqual(w.controller_of(c), p1)


class TestDraw(unittest.TestCase):
    def test_draw_pops_top_of_library_into_hand(self):
        w = GameWorld(num_players=1, master_seed=3)
        p = w.player_order[0]
        a = w.add_card(card(ORACLE_A, "A"), p)
        b = w.add_card(card(ORACLE_B, "B"), p)
        c = w.add_card(card(ORACLE_C, "C"), p)
        # Library order is [a, b, c]; top is c.
        drawn = w.draw(p, 1)
        self.assertEqual(drawn, [c])
        self.assertIn(c, w.players[p].zone(ZONE_HAND).entries)
        self.assertEqual(w.players[p].zone(ZONE_LIBRARY).entries, [a, b])

    def test_draw_empty_library_returns_nothing(self):
        w = GameWorld(num_players=1, master_seed=3)
        p = w.player_order[0]
        self.assertEqual(w.draw(p, 5), [])


class TestTriggerOrdering(unittest.TestCase):
    def test_same_controller_ordered_by_clock(self):
        w = build_world()
        p0 = w.player_order[0]
        c = w.add_card(card(ORACLE_A, "A"), p0)
        t1 = w.queue_trigger(c, p0, "etb")
        t2 = w.queue_trigger(c, p0, "etb")
        self.assertEqual(w.pending_triggers(), [t1, t2])

    def test_different_controllers_ordered_by_seat(self):
        w = build_world()
        p0, p1 = w.player_order[0], w.player_order[1]
        ca = w.add_card(card(ORACLE_A, "A"), p0)
        cb = w.add_card(card(ORACLE_B, "B"), p1)
        # p1's trigger is queued first, but p0 (seat 0) must come first.
        t_p1 = w.queue_trigger(cb, p1, "etb")
        t_p0 = w.queue_trigger(ca, p0, "etb")
        self.assertEqual(w.pending_triggers(), [t_p0, t_p1])

    def test_resolve_next_pops_in_order(self):
        w = build_world()
        p0, p1 = w.player_order[0], w.player_order[1]
        ca = w.add_card(card(ORACLE_A, "A"), p0)
        cb = w.add_card(card(ORACLE_B, "B"), p1)
        t_p1 = w.queue_trigger(cb, p1, "etb")
        t_p0 = w.queue_trigger(ca, p0, "etb")
        self.assertIs(w.resolve_next_trigger(), t_p0)
        self.assertIs(w.resolve_next_trigger(), t_p1)
        self.assertIsNone(w.resolve_next_trigger())


class TestDeterminism(unittest.TestCase):
    def test_identical_builds_give_identical_fingerprint(self):
        w1 = build_world(seed=7)
        w2 = build_world(seed=7)
        self.assertEqual(w1.fingerprint(), w2.fingerprint())

    def test_different_seed_gives_different_fingerprint(self):
        w1 = build_world(seed=7)
        w2 = build_world(seed=8)
        self.assertNotEqual(w1.fingerprint(), w2.fingerprint())

    def test_fingerprint_changes_when_state_changes(self):
        w = build_world()
        before = w.fingerprint()
        p0 = w.player_order[0]
        c = w.add_card(card(ORACLE_A, "A"), p0)
        after_add = w.fingerprint()
        self.assertNotEqual(before, after_add)
        w.move_to_zone(c, p0, ZONE_HAND)
        self.assertNotEqual(after_add, w.fingerprint())

    def test_replay_same_moves_same_fingerprint(self):
        # Two worlds, same seed, same move sequence -> same fingerprint.
        def play(w):
            p0 = w.player_order[0]
            c = w.add_card(card(ORACLE_A, "A"), p0)
            w.move_to_zone(c, p0, ZONE_HAND)
            w.queue_trigger(c, p0, "etb")
            w.draw(p0, 1)
            w.players[p0].life -= 3
            return w.fingerprint()

        self.assertEqual(play(build_world(seed=42)), play(build_world(seed=42)))

    def test_fingerprint_includes_card_instance_state(self):
        w1 = build_world(seed=7)
        w2 = build_world(seed=7)
        c = w1.add_card(card(ORACLE_A, "A"), w1.player_order[0])
        w2.add_card(card(ORACLE_A, "A"), w2.player_order[0])
        self.assertEqual(w1.fingerprint(), w2.fingerprint())
        w1.cards[c].tapped = True
        self.assertNotEqual(w1.fingerprint(), w2.fingerprint())


class TestPlayers(unittest.TestCase):
    def test_commander_format_starts_at_40(self):
        w = GameWorld(num_players=4, start_life=40, master_seed=1)
        self.assertEqual(len(w.player_order), 4)
        for p in w.player_order:
            self.assertEqual(w.players[p].life, 40)

    def test_add_player_appends_seat(self):
        w = GameWorld(num_players=1, master_seed=1)
        new = w.add_player("Extra", life=30)
        self.assertEqual(w.players[new].seat, 1)
        self.assertEqual(w.players[new].life, 30)

    def test_unknown_controller_rejected(self):
        from MTG_bot.core.identity import Handle

        w = build_world()
        ghost = Handle("player", 99)
        with self.assertRaises(KeyError):
            w.add_card(card(ORACLE_A, "A"), ghost)


if __name__ == "__main__":
    unittest.main()
