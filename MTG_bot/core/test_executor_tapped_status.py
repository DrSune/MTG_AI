"""V43 (2026-10-29): tapped status leaves with the permanent. CR 110.5d: a card that is not on the
battlefield is neither tapped nor untapped; 110.5b: a permanent enters untapped unless a rule or
effect says otherwise; 400.7: a card that changes zones is a new object. One CardState spans every
zone, so a tapped creature that was bounced, killed or exiled came back tapped."""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    QConst,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.events import KIND_TAP_STATE
from MTG_bot.core.executor.games import get_supply, identity_of
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import BF_YOU, UNIV, atom, card_id, enter

EXILE_ANY = Zone(ZoneKind.EXILE, ControllerRef.ANY)
HAND_OWNER = Zone(ZoneKind.HAND, ControllerRef.OWNER)


class TappedStatusTest(unittest.TestCase):
    def setUp(self) -> None:
        self.supply = get_supply("all")
        self.world = GameWorld(num_players=2, start_life=20, master_seed=37)
        self.ex = Executor(self.world)
        self.p0, self.p1 = self.world.player_order
        for i in range(4):
            self.world.add_card(card_id(f"Filler {i}", "1", "1"), self.p0, ZONE_LIBRARY)

    def real(self, name: str, zone: str) -> Handle:
        oid = next(o for o, m in self.supply.metas.items() if m.name == name)
        return self.world.add_card(identity_of(self.supply.pool.results[oid].card), self.p0, zone)

    def start(self) -> None:
        self.ex.attach_pool(self.supply.pool)
        self.ex.begin_turn(self.p0)  # its untap step runs: tap things after it

    def move(self, card: Handle, dest: Zone, **roles) -> None:
        base = enter(dest)
        effect = atom(Verb.MOVE_ZONE, **dict(base.args.pairs), **roles) if roles else base
        self.ex.apply_effect(effect, source=card, controller=self.p0, bindings={"cards": card})

    def tap_rows(self, card: Handle) -> list:
        return [r for r in self.ex.journal.dump() if r[1] == KIND_TAP_STATE and r[2] == str(card)]

    def test_a_bounced_tapped_creature_is_cast_again_untapped(self) -> None:
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        bounce = self.real("Unsubstantiate", ZONE_HAND)
        self.start()
        self.world.cards[bear].tapped = True
        self.world.players[self.p0].mana_pool.update({"U": 2})
        cast(self.ex, self.p0, bounce, targets=(bear,))
        self.assertEqual(self.world.zone_of(bear).kind, ZONE_HAND)
        self.assertFalse(self.world.cards[bear].tapped)  # CR 110.5d
        self.move(bear, BF_YOU)
        self.assertFalse(self.world.cards[bear].tapped)  # CR 110.5b

    def test_exiled_and_returned_untapped(self) -> None:
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        self.start()
        self.world.cards[bear].tapped = True
        self.move(bear, EXILE_ANY)
        self.assertEqual(self.world.zone_of(bear).kind, ZONE_EXILE)
        self.move(bear, BF_YOU)
        self.assertEqual(self.world.zone_of(bear).kind, ZONE_BATTLEFIELD)
        self.assertFalse(self.world.cards[bear].tapped)

    def test_returned_tapped_when_the_effect_says_so(self) -> None:
        # "Return it to the battlefield tapped": the entering stamp lands after the move.
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        self.start()
        self.world.cards[bear].tapped = True
        self.move(bear, EXILE_ANY)
        self.move(bear, BF_YOU, tapped_on_enter=True)
        self.assertTrue(self.world.cards[bear].tapped)

    def test_a_tapped_creature_that_died_is_reanimated_untapped(self) -> None:
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        rise = self.real("Rise Again", ZONE_HAND)
        self.start()
        self.world.cards[bear].tapped = True
        dies = atom(Verb.SACRIFICE, target=Selector(QConst(1), SelectorMode.TARGET, UNIV, zones=(BF_YOU,)))
        self.ex.apply_effect(dies, source=bear, controller=self.p0, bindings={"target": [bear]})
        self.assertEqual(self.world.zone_of(bear).kind, ZONE_GRAVEYARD)
        self.world.players[self.p0].mana_pool.update({"B": 5})
        cast(self.ex, self.p0, rise, targets=(bear,))
        self.assertEqual(self.world.zone_of(bear).kind, ZONE_BATTLEFIELD)
        self.assertFalse(self.world.cards[bear].tapped)

    def test_leaving_the_battlefield_is_not_an_untap_event(self) -> None:
        # Village Rites sacrifices a tapped creature as a cost: the CAST atom's window spans the
        # payment, and the cleared flag must not be journalled as "becomes untapped".
        elf = self.world.add_card(card_id("Elf", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        rites = self.real("Village Rites", ZONE_HAND)
        self.start()
        self.world.cards[elf].tapped = True
        self.world.players[self.p0].mana_pool.update({"B": 1})
        cast(self.ex, self.p0, rites)
        self.assertEqual(self.world.zone_of(elf).kind, ZONE_GRAVEYARD)
        self.assertFalse(self.world.cards[elf].tapped)
        self.assertEqual(self.tap_rows(elf), [])

    def test_a_permanent_that_stays_keeps_its_status(self) -> None:
        stays = self.world.add_card(card_id("Stays", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        leaves = self.world.add_card(card_id("Leaves", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        self.start()
        self.world.cards[stays].tapped = True
        self.world.cards[leaves].tapped = True
        self.move(leaves, HAND_OWNER)
        self.assertTrue(self.world.cards[stays].tapped)
        self.assertFalse(self.world.cards[leaves].tapped)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
