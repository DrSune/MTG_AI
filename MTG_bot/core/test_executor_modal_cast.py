"""V17 (2026-10-29): a modal spell announces its modes as it is cast (CR 601.2b, 700.2a), and only
the chosen modes' targets exist (CR 601.2c, 700.2c)."""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    Choose,
    ControllerRef,
    FAtom,
    FAtomPred,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    SpellKind,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import get_supply, identity_of
from MTG_bot.core.executor.query import (
    cast_mode_options,
    spell_target_slots,
    with_modes,
)
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND, GameWorld
from MTG_bot.core.test_executor_binding import card_id


def _destroy(type_name: str) -> Atom:
    target = Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value=type_name),
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
    )
    return Atom(verb=Verb.DESTROY, args=AtomArgs(pairs=(("target", target),)))


class ModalCastTest(unittest.TestCase):
    def setUp(self) -> None:
        self.supply = get_supply("all")
        self.world = GameWorld(num_players=2, start_life=20, master_seed=13)
        self.ex = Executor(self.world)
        self.ex.attach_pool(self.supply.pool)
        self.p0, self.p1 = self.world.player_order
        self.ex.begin_turn(self.p0)
        self.asks: list[tuple[str, tuple[str, ...]]] = []
        self.answer = "0"

        def provider(vocab: tuple[str, ...], what: str) -> str:
            self.asks.append((what, vocab))
            return self.answer if self.answer in vocab else vocab[0]

        self.ex.decisions.provider = provider

    def tampering(self) -> Handle:
        record = next(
            self.supply.pool.results[oid].card
            for oid, m in self.supply.metas.items()
            if m.name == "Destructive Tampering"
        )
        self.world.players[self.p0].mana_pool.update({"R": 3})
        return self.world.add_card(identity_of(record), self.p0, ZONE_HAND)

    def test_a_targetless_mode_needs_no_target(self) -> None:
        # No artifact anywhere: mode 1 cannot be chosen (700.2a), so mode 2 is the only legal
        # set, announced without an ask, and the spell is cast with no target.
        spell = self.tampering()
        cast(self.ex, self.p0, spell)
        self.assertEqual(self.world.zone_of(spell).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.asks, [])

    def test_the_mode_is_asked_at_cast_and_never_again(self) -> None:
        relic = self.world.add_card(card_id("Relic", type_line="Artifact"), self.p1, ZONE_BATTLEFIELD)
        spell = self.tampering()
        self.answer = "1"
        cast(self.ex, self.p0, spell)
        self.assertEqual([(w.split(":")[0], v) for w, v in self.asks], [("choose", ("0", "1"))])
        self.assertEqual(self.world.zone_of(relic).kind, ZONE_BATTLEFIELD)  # mode 2: no destroy

    def test_declared_modes_validate_their_own_targets(self) -> None:
        relic = self.world.add_card(card_id("Relic", type_line="Artifact"), self.p1, ZONE_BATTLEFIELD)
        spell = self.tampering()
        with self.assertRaises(ValueError):  # mode 2 takes no target
            cast(self.ex, self.p0, spell, mode_choices=(1,), targets=(relic,))
        cast(self.ex, self.p0, spell, mode_choices=(0,), targets=(relic,))
        self.assertEqual(self.world.zone_of(relic).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.asks, [])

    def test_choose_two_announces_a_set_and_unions_its_targets(self) -> None:
        # "Choose two —" over three modes: the option SETS are the menu (choose_options order),
        # a set is legal only when all its targets can be chosen, and its slots are the union.
        node = SpellAbility(
            kind=SpellKind.SORCERY,
            effect=Choose(count=QConst(2), options=(_destroy("Artifact"), _destroy("Enchantment"), _destroy("Land"))),
        )
        spell = self.world.add_card(card_id("Spell", type_line="Sorcery"), self.p0, ZONE_HAND)
        self.world.add_card(card_id("Relic", type_line="Artifact"), self.p1, ZONE_BATTLEFIELD)
        self.world.add_card(card_id("Charm", type_line="Enchantment"), self.p1, ZONE_BATTLEFIELD)
        legal = cast_mode_options(self.ex, node, spell_handle=spell, seat=self.p0)
        self.assertEqual(legal, [(0, (0, 1))])  # no land: only {artifact, enchantment}
        self.assertIsInstance(with_modes(node, (0, 1)).effect, Seq)
        slots = spell_target_slots(self.ex, node, spell_handle=spell, seat=self.p0, modes=(0, 1))
        self.assertEqual(len(slots), 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
