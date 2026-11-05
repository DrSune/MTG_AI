"""V20 (2026-10-29, B-66): a spell's own "you can't choose ... as this spell's target as you cast
it" restricts its target choice (CR 113.6e; Enthralling Hold: "You can't choose an untapped creature
as this spell's target as you cast it")."""

from __future__ import annotations

import unittest

from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import get_supply, identity_of
from MTG_bot.core.executor.query import aura_enchant_slot, legal_casts
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND, GameWorld
from MTG_bot.core.test_executor_binding import card_id


class OwnTargetRestrictionTest(unittest.TestCase):
    def setUp(self) -> None:
        supply = get_supply("all")
        self.world = GameWorld(num_players=2, start_life=20, master_seed=9)
        self.ex = Executor(self.world)
        self.ex.attach_pool(supply.pool)
        self.p0, self.p1 = self.world.player_order
        record = next(
            supply.pool.results[oid].card for oid, m in supply.metas.items() if m.name == "Enthralling Hold"
        )
        self.hold = self.world.add_card(identity_of(record), self.p0, ZONE_HAND)
        self.untapped = self.world.add_card(card_id("Untapped", "2", "2"), self.p1, ZONE_BATTLEFIELD)
        self.tapped = self.world.add_card(card_id("Tapped", "3", "3"), self.p1, ZONE_BATTLEFIELD)
        self.world.cards[self.tapped].tapped = True
        self.ex.begin_turn(self.p0)
        self.world.players[self.p0].mana_pool.update({"U": 5})

    def slot(self):
        node = next(r.node for r in legal_casts(self.world, self.ex, self.p0) if r.handle == self.hold)
        return aura_enchant_slot(self.ex, node, spell_handle=self.hold, seat=self.p0)

    def test_untapped_creatures_are_not_offered(self) -> None:
        self.assertEqual(self.slot().candidates, (self.tapped,))

    def test_casting_onto_an_untapped_creature_is_refused(self) -> None:
        with self.assertRaises(ValueError) as caught:
            cast(self.ex, self.p0, self.hold, targets=(self.untapped,))
        self.assertIn("illegal", str(caught.exception))
        self.assertEqual(self.world.zone_of(self.hold).kind, ZONE_HAND)

    def test_a_tapped_creature_is_enchanted_and_stolen(self) -> None:
        cast(self.ex, self.p0, self.hold, targets=(self.tapped,))
        self.assertEqual(self.ex.attachments.get(self.hold), self.tapped)
        self.assertEqual(self.ex.controller_of(self.tapped), self.p0)

    def test_the_restriction_is_about_the_cast_only(self) -> None:
        # On the battlefield the ability no longer restricts anything: the Aura's own targets are
        # chosen as it is cast (CR 113.6e), and the enchanted creature untapping changes nothing.
        cast(self.ex, self.p0, self.hold, targets=(self.tapped,))
        self.world.cards[self.tapped].tapped = False
        self.ex._settle()
        self.assertEqual(self.ex.attachments.get(self.hold), self.tapped)
        self.assertEqual(self.ex.controller_of(self.tapped), self.p0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
