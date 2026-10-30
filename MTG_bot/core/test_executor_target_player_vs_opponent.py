"""V21 (2026-10-29): "target player" (TARGET_PLAYER) may designate any player, the caster included
(CR 115.1); "target opponent" (TARGET_OPPONENT) only an opponent (CR 102.2). They shared one token
before, so "target player" could never be you (B-53)."""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import ControllerRef, SpellAbility
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import get_supply, identity_of
from MTG_bot.core.executor.query import (
    activation_target_slots,
    legal_activations,
    player_target_slot,
    spell_target_slots,
)
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND, GameWorld


class TargetPlayerVsOpponentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.supply = get_supply("all")
        self.world = GameWorld(num_players=2, start_life=20, master_seed=31)
        self.ex = Executor(self.world)
        self.p0, self.p1 = self.world.player_order

    def real(self, name: str, zone: str) -> Handle:
        oid = next(o for o, m in self.supply.metas.items() if m.name == name)
        return self.world.add_card(identity_of(self.supply.pool.results[oid].card), self.p0, zone)

    def spell_slot(self, handle: Handle):
        record = self.supply.pool.results[self.world.cards[handle].identity.oracle_id].card
        node = next(a for a in record.abilities if isinstance(a, SpellAbility))
        (slot,) = [s for s in spell_target_slots(self.ex, node, spell_handle=handle, seat=self.p0) if s.synthetic]
        return slot

    def test_target_player_spells_may_designate_the_caster(self) -> None:
        for name in ("Mind Rot", "Peer into the Abyss"):
            spell = self.real(name, ZONE_HAND)
            self.ex.attach_pool(self.supply.pool)
            slot = self.spell_slot(spell)
            self.assertEqual(slot.candidates, (self.p0, self.p1), name)
            self.assertFalse(slot.forced)

    def test_target_opponent_spells_never_designate_the_caster(self) -> None:
        for name in ("Duress", "Run Afoul"):
            spell = self.real(name, ZONE_HAND)
            self.ex.attach_pool(self.supply.pool)
            slot = self.spell_slot(spell)
            self.assertEqual(slot.candidates, (self.p1,), name)
            self.assertTrue(slot.forced)

    def test_activations_follow_the_same_split(self) -> None:
        crypt = self.real("Tormod's Crypt", ZONE_BATTLEFIELD)
        steward = self.real("Liliana's Steward", ZONE_BATTLEFIELD)
        self.ex.attach_pool(self.supply.pool)
        self.ex.begin_turn(self.p0)
        options = {(o.source, o.ability_idx): o for o in legal_activations(self.world, self.ex, self.p0)}
        crypt_slots = activation_target_slots(self.ex, options[(crypt, 0)].ability.effect, source=crypt, seat=self.p0)
        self.assertEqual([s.candidates for s in crypt_slots if s.synthetic], [(self.p0, self.p1)])
        record = self.supply.pool.results[self.world.cards[steward].identity.oracle_id].card
        steward_slots = activation_target_slots(self.ex, record.abilities[0].effect, source=steward, seat=self.p0)
        self.assertEqual([s.candidates for s in steward_slots if s.synthetic], [(self.p1,)])

    def test_a_target_opponent_read_narrows_the_slot_whatever_else_is_read(self) -> None:
        # Duress: "Target opponent reveals..." (TARGET_OPPONENT) then "That player discards"
        # (an anaphoric TARGET_PLAYER read): the designating word decides.
        both = {ControllerRef.TARGET_PLAYER, ControllerRef.TARGET_OPPONENT}
        self.assertEqual(player_target_slot(self.ex, self.p0, both).candidates, (self.p1,))
        self.assertEqual(
            player_target_slot(self.ex, self.p0, {ControllerRef.TARGET_PLAYER}).candidates,
            (self.p0, self.p1),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
