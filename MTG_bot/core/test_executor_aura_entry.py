"""V32 (2026-10-29): an Aura put onto the battlefield without being cast enters attached to what the
player it enters under chooses (CR 303.4f, not targeting); with nothing legal it stays put (303.4g)."""

from __future__ import annotations

import unittest
from dataclasses import replace

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    FAnd,
    QConst,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.aura_entry import aura_entry_hosts
from MTG_bot.core.executor.games import get_supply, identity_of
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND, GameWorld
from MTG_bot.core.test_executor_binding import card_id


def _put_onto_battlefield(executor: Executor, card: Handle, controller: Handle) -> None:
    move = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("cards", Selector(QConst(1), SelectorMode.TARGET, FAnd(()), zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),))),
                ("destination", Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)),
            )
        ),
    )
    executor.execute(move, source=card, controller=controller, bindings={"cards": card})


class AuraEntryTest(unittest.TestCase):
    def setUp(self) -> None:
        supply = get_supply("all")
        self.world = GameWorld(num_players=2, start_life=20, master_seed=21)
        self.ex = Executor(self.world)
        self.p0, self.p1 = self.world.player_order
        record = next(
            supply.pool.results[oid].card for oid, m in supply.metas.items() if m.name == "Capture Sphere"
        )
        # added before attach_pool: the binder bridges the cards it saw then (binding.attach_pool)
        self.sphere = self.world.add_card(identity_of(record), self.p0, ZONE_HAND)
        self.ex.attach_pool(supply.pool)
        self.asks: list[tuple[str, tuple[str, ...], Handle | None]] = []
        self.pick: Handle | None = None

        def provider(vocab: tuple[str, ...], what: str) -> str:
            self.asks.append((what, vocab, self.ex.decisions.asking_seat))
            return str(self.pick) if self.pick is not None and str(self.pick) in vocab else vocab[0]

        self.ex.decisions.provider = provider

    def test_the_entering_player_chooses_the_host(self) -> None:
        small = self.world.add_card(card_id("Small", "1", "1"), self.p1, ZONE_BATTLEFIELD)
        big = self.world.add_card(card_id("Big", "5", "5"), self.p1, ZONE_BATTLEFIELD)
        self.pick = big
        _put_onto_battlefield(self.ex, self.sphere, self.p0)
        self.assertEqual(self.ex.attachments.get(self.sphere), big)
        self.assertEqual(self.world.zone_of(self.sphere).kind, ZONE_BATTLEFIELD)
        enchant = [(w, v, s) for w, v, s in self.asks if w.startswith("enchant:")]
        self.assertEqual(enchant, [(enchant[0][0], tuple(str(h) for h in sorted((small, big))), self.p0)])
        self.assertTrue(self.world.cards[big].tapped)  # its ETB taps the enchanted creature

    def test_one_host_is_taken_without_an_ask(self) -> None:
        only = self.world.add_card(card_id("Only", "2", "2"), self.p1, ZONE_BATTLEFIELD)
        _put_onto_battlefield(self.ex, self.sphere, self.p0)
        self.assertEqual(self.ex.attachments.get(self.sphere), only)
        self.assertEqual([w for w, _v, _s in self.asks if w.startswith("enchant:")], [])

    def test_nothing_to_enchant_it_stays_where_it_is(self) -> None:
        self.world.add_card(card_id("Relic", type_line="Artifact"), self.p1, ZONE_BATTLEFIELD)
        _put_onto_battlefield(self.ex, self.sphere, self.p0)
        self.assertEqual(self.world.zone_of(self.sphere).kind, ZONE_HAND)
        self.assertNotIn(self.sphere, self.ex.attachments)

    def test_hexproof_does_not_stop_it_and_it_never_enchants_itself(self) -> None:
        shy = self.world.add_card(replace(card_id("Shy", "2", "2"), keywords=("HEXPROOF",)), self.p1, ZONE_BATTLEFIELD)
        self.ex.layers.recompute()
        hosts = aura_entry_hosts(self.ex, self.sphere, self.p0)
        self.assertEqual(hosts, [shy])
        self.assertNotIn(self.sphere, hosts)

    def test_an_aura_resolving_as_a_spell_is_unchanged(self) -> None:
        # The cast lane targets (CR 303.4a) and attaches itself; no enchant ask.
        from MTG_bot.core.executor.stack import cast

        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p1, ZONE_BATTLEFIELD)
        self.ex.begin_turn(self.p0)
        self.world.players[self.p0].mana_pool.update({"U": 4})
        cast(self.ex, self.p0, self.sphere, targets=(bear,))
        self.assertEqual(self.ex.attachments.get(self.sphere), bear)
        self.assertEqual([w for w, _v, _s in self.asks if w.startswith("enchant:")], [])
        self.assertNotEqual(self.world.zone_of(self.sphere).kind, ZONE_GRAVEYARD)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
