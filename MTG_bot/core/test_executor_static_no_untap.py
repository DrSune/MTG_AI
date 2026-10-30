"""V16 (2026-10-29): a static "doesn't untap during its controller's untap step" (Capture Sphere's
Aura) keeps its creature tapped (CR 502.3), and stops when the Aura leaves."""

from __future__ import annotations

import unittest

from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import get_supply, identity_of
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND, GameWorld
from MTG_bot.core.test_executor_binding import card_id


class StaticNoUntapTest(unittest.TestCase):
    def setUp(self) -> None:
        supply = get_supply("all")
        self.world = GameWorld(num_players=2, start_life=20, master_seed=23)
        self.ex = Executor(self.world)
        self.p0, self.p1 = self.world.player_order
        record = next(
            supply.pool.results[oid].card for oid, m in supply.metas.items() if m.name == "Capture Sphere"
        )
        self.sphere = self.world.add_card(identity_of(record), self.p0, ZONE_HAND)
        self.held = self.world.add_card(card_id("Held", "2", "2"), self.p1, ZONE_BATTLEFIELD)
        self.free = self.world.add_card(card_id("Free", "3", "3"), self.p1, ZONE_BATTLEFIELD)
        self.world.cards[self.free].tapped = True
        self.ex.attach_pool(supply.pool)
        self.ex.begin_turn(self.p0)
        self.world.players[self.p0].mana_pool.update({"U": 4})
        cast(self.ex, self.p0, self.sphere, targets=(self.held,))

    def test_the_enchanted_creature_stays_tapped(self) -> None:
        self.assertTrue(self.world.cards[self.held].tapped)  # its ETB tapped it
        self.ex.end_turn()
        self.ex.advance_turn()  # player 1's untap step
        self.assertTrue(self.world.cards[self.held].tapped)
        self.assertFalse(self.world.cards[self.free].tapped)

    def test_it_untaps_once_the_aura_is_gone(self) -> None:
        self.world.move_to_zone(self.sphere, self.p0, ZONE_GRAVEYARD)
        self.ex._settle()
        self.ex.end_turn()
        self.ex.advance_turn()
        self.assertFalse(self.world.cards[self.held].tapped)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
