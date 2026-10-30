"""V19 (2026-10-29, B-51): "You choose a noncreature, nonland card from it" is mandatory. The empty
pick exists only when nothing legal does, and a lone legal card is taken without an ask."""

from __future__ import annotations

import unittest

from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import get_supply, identity_of
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import ZONE_GRAVEYARD, ZONE_HAND, GameWorld
from MTG_bot.core.test_executor_binding import card_id


class MandatoryChooseTest(unittest.TestCase):
    def setUp(self) -> None:
        supply = get_supply("all")
        self.world = GameWorld(num_players=2, start_life=20, master_seed=29)
        self.ex = Executor(self.world)
        self.p0, self.p1 = self.world.player_order
        record = next(supply.pool.results[o].card for o, m in supply.metas.items() if m.name == "Duress")
        self.duress = self.world.add_card(identity_of(record), self.p0, ZONE_HAND)
        self.asks: list[tuple[str, tuple[str, ...]]] = []

    def start(self, answer: str | None = None) -> None:
        self.ex.attach_pool(get_supply("all").pool)
        self.ex.begin_turn(self.p0)
        self.world.players[self.p0].mana_pool.update({"B": 1})

        def provider(vocab: tuple[str, ...], what: str) -> str:
            self.asks.append((what, vocab))
            return answer if answer in vocab else vocab[0]

        self.ex.decisions.provider = provider

    def choose_asks(self) -> list[tuple[str, ...]]:
        return [v for w, v in self.asks if w.startswith("choose:")]

    def test_a_lone_legal_card_is_discarded_without_an_ask(self) -> None:
        trick = self.world.add_card(card_id("Trick", type_line="Instant"), self.p1, ZONE_HAND)
        self.world.add_card(card_id("Elf", "1", "1"), self.p1, ZONE_HAND)
        self.start()
        cast(self.ex, self.p0, self.duress)
        self.assertEqual(self.world.zone_of(trick).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.choose_asks(), [])

    def test_two_legal_cards_are_a_choice_with_no_empty_row(self) -> None:
        first = self.world.add_card(card_id("First", type_line="Instant"), self.p1, ZONE_HAND)
        second = self.world.add_card(card_id("Second", type_line="Sorcery"), self.p1, ZONE_HAND)
        self.start(answer="1")
        cast(self.ex, self.p0, self.duress)
        (vocab,) = self.choose_asks()
        self.assertEqual(vocab[:2], ("0", "1"))  # index tokens: no third, empty row
        self.assertNotIn("2", vocab)
        self.assertEqual(self.world.zone_of(second).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(first).kind, ZONE_HAND)

    def test_nothing_legal_chooses_nothing(self) -> None:
        elf = self.world.add_card(card_id("Elf", "1", "1"), self.p1, ZONE_HAND)
        self.start()
        cast(self.ex, self.p0, self.duress)
        self.assertEqual(self.world.zone_of(elf).kind, ZONE_HAND)
        self.assertEqual(self.choose_asks(), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
