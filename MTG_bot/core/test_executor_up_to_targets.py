"""V15 (2026-10-29): "up to N target ..." may choose zero (CR 601.2c, 115.6); a spell or ability
with zero targets chosen is not targeted. Real M21 cards."""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import Keyword
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.events import KIND_TARGETING
from MTG_bot.core.executor.games import get_supply, identity_of
from MTG_bot.core.executor.legality import activate
from MTG_bot.core.executor.query import (
    activation_target_slots,
    legal_activations,
    spell_target_slots,
)
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND, GameWorld
from MTG_bot.core.test_executor_binding import card_id


class UpToTargetsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.supply = get_supply("all")
        self.world = GameWorld(num_players=2, start_life=20, master_seed=17)
        self.ex = Executor(self.world)
        self.p0, self.p1 = self.world.player_order
        self.asks: list[tuple[str, tuple[str, ...]]] = []
        self.answers: list[str] = []

    def real(self, name: str, seat: Handle, zone: str) -> Handle:
        oid = next(o for o, m in self.supply.metas.items() if m.name == name)
        return self.world.add_card(identity_of(self.supply.pool.results[oid].card), seat, zone)

    def start(self) -> None:
        self.ex.attach_pool(self.supply.pool)
        self.ex.begin_turn(self.p0)

        def provider(vocab: tuple[str, ...], what: str) -> str:
            self.asks.append((what, vocab))
            return self.answers.pop(0) if self.answers and self.answers[0] in vocab else vocab[0]

        self.ex.decisions.provider = provider

    def targeting_rows(self) -> list:
        return [r for r in self.ex.journal.dump() if r[1] == KIND_TARGETING]

    def test_up_to_one_with_no_candidate_is_activatable(self) -> None:
        # Liliana, Death Mage +1 with no creature card in the graveyard.
        lm = self.real("Liliana, Death Mage", self.p0, ZONE_BATTLEFIELD)
        sorcery = self.world.add_card(card_id("Spent", type_line="Sorcery"), self.p0, ZONE_GRAVEYARD)
        self.start()
        self.assertIn((lm, 0), {(o.source, o.ability_idx) for o in legal_activations(self.world, self.ex, self.p0)})
        option = next(o for o in legal_activations(self.world, self.ex, self.p0) if (o.source, o.ability_idx) == (lm, 0))
        (slot,) = activation_target_slots(self.ex, option.ability.effect, source=lm, seat=self.p0)
        self.assertEqual((slot.min_count, slot.max_count, slot.candidates), (0, 0, ()))
        activate(self.ex, lm, 0, seat=self.p0)
        self.assertEqual(self.world.cards[lm].counters.get("LOYALTY"), 5)
        self.assertEqual(self.world.zone_of(sorcery).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.targeting_rows(), [])  # CR 115.6: not targeted

    def test_zero_targets_then_its_tail_does_nothing(self) -> None:
        # Basri, Devoted Paladin +1: "Put a +1/+1 counter on up to one target creature. It gains
        # vigilance until end of turn." With zero chosen, nobody gets either.
        basri = self.real("Basri, Devoted Paladin", self.p0, ZONE_BATTLEFIELD)
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        self.start()
        activate(self.ex, basri, 0, seat=self.p0)
        self.assertEqual(self.world.cards[basri].counters.get("LOYALTY"), 5)
        self.assertEqual(self.world.cards[bear].counters, {})
        self.assertFalse(self.ex.layers.keyword_of(bear, Keyword.VIGILANCE))
        self.assertEqual(self.targeting_rows(), [])

    def test_a_trigger_offers_none_from_the_first_pick(self) -> None:
        # Basri's Acolyte: "put a +1/+1 counter on each of up to two other target creatures you
        # control". One candidate is still a choice: it, or none.
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        acolyte = self.real("Basri's Acolyte", self.p0, ZONE_HAND)
        self.start()
        self.world.players[self.p0].mana_pool.update({"W": 4})
        self.answers = ["NONE"]
        cast(self.ex, self.p0, acolyte)
        target_asks = [(w, v) for w, v in self.asks if w.startswith("target:")]
        self.assertEqual(target_asks, [(target_asks[0][0], (str(bear), "NONE"))])
        self.assertEqual(self.world.cards[bear].counters, {})
        self.assertEqual(self.targeting_rows(), [])

    def test_a_spell_with_zero_targets_is_cast_and_resolves(self) -> None:
        # Volcanic Salvo: "deals 6 damage to each of up to two target creatures and/or
        # planeswalkers" — castable with no target at all.
        salvo = self.real("Volcanic Salvo", self.p0, ZONE_HAND)
        self.start()
        self.world.players[self.p0].mana_pool.update({"R": 12})
        node = next(a for a in self.supply.pool.results[self.world.cards[salvo].identity.oracle_id].card.abilities if type(a).__name__ == "SpellAbility")
        (slot,) = spell_target_slots(self.ex, node, spell_handle=salvo, seat=self.p0)
        self.assertEqual(slot.min_count, 0)
        cast(self.ex, self.p0, salvo)
        self.assertEqual(self.world.zone_of(salvo).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.targeting_rows(), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
