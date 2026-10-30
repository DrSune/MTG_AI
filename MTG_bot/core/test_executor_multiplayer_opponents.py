"""V42 (2026-10-30): the opponent refs with three seats. "Each opponent" acts on every opponent,
"target opponent" may designate any one of them, "an opponent has ..." reads any of them, and a
verb that acts through one player never silently takes the first of several (B-108). Real M21
cards; Commander, the priority format, is multiplayer (CR 800.1)."""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import ControllerRef, Keyword, QConst, SpellAbility, Verb
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import get_supply, identity_of
from MTG_bot.core.executor.query import spell_target_slots
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import atom, card_id


class ThreeSeatOpponentsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.supply = get_supply("all")
        self.world = GameWorld(num_players=3, start_life=20, master_seed=41)
        self.ex = Executor(self.world)
        self.p0, self.p1, self.p2 = self.world.player_order
        for seat in self.world.player_order:
            for i in range(10):
                self.world.add_card(card_id(f"Lib {seat.index}.{i}", "1", "1"), seat, ZONE_LIBRARY)

    def real(self, name: str, seat: Handle, zone: str) -> Handle:
        oid = next(o for o, m in self.supply.metas.items() if m.name == name)
        return self.world.add_card(identity_of(self.supply.pool.results[oid].card), seat, zone)

    def start(self, **mana: int) -> None:
        self.ex.attach_pool(self.supply.pool)
        self.ex.begin_turn(self.p0)
        self.world.players[self.p0].mana_pool.update(mana)
        self.ex.decisions.provider = lambda vocab, what: vocab[0]

    def count(self, zone: str) -> list[int]:
        return [len(self.world.players[p].zone(zone).entries) for p in self.world.player_order]

    def lives(self) -> list[int]:
        return [self.world.players[p].life for p in self.world.player_order]

    def test_each_opponent_discards(self) -> None:
        # Bad Deal: "You draw two cards and each opponent discards two cards. Each player loses
        # 2 life."
        for seat in (self.p1, self.p2):
            for i in range(3):
                self.world.add_card(card_id(f"Hand {seat.index}.{i}", "1", "1"), seat, ZONE_HAND)
        deal = self.real("Bad Deal", self.p0, ZONE_HAND)
        self.start(B=6)
        cast(self.ex, self.p0, deal)
        self.assertEqual(self.count(ZONE_HAND), [3, 1, 1])  # p0: its turn's draw + two
        self.assertEqual(self.lives(), [18, 18, 18])

    def test_target_opponent_offers_every_opponent(self) -> None:
        duress = self.real("Duress", self.p0, ZONE_HAND)
        rot = self.real("Mind Rot", self.p0, ZONE_HAND)
        self.start()
        for spell, expected in ((duress, (self.p1, self.p2)), (rot, (self.p0, self.p1, self.p2))):
            record = self.supply.pool.results[self.world.cards[spell].identity.oracle_id].card
            node = next(a for a in record.abilities if isinstance(a, SpellAbility))
            (slot,) = [s for s in spell_target_slots(self.ex, node, spell_handle=spell, seat=self.p0) if s.synthetic]
            self.assertEqual(slot.candidates, expected)
            self.assertFalse(slot.forced)

    def test_each_opponent_is_dealt_damage(self) -> None:
        # Storm Caller: "When this creature enters, it deals 2 damage to each opponent."
        caller = self.real("Storm Caller", self.p0, ZONE_HAND)
        self.start(R=3)
        cast(self.ex, self.p0, caller)
        self.assertEqual(self.lives(), [20, 18, 18])

    def test_each_opponents_creatures_and_their_controllers(self) -> None:
        # Massacre Wurm: "creatures your opponents control get -2/-2 until end of turn. Whenever a
        # creature an opponent controls dies, that player loses 2 life."
        mine = self.world.add_card(card_id("Mine", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        for seat in (self.p1, self.p2):
            self.world.add_card(card_id(f"Small {seat.index}", "2", "2"), seat, ZONE_BATTLEFIELD)
        wurm = self.real("Massacre Wurm", self.p0, ZONE_HAND)
        self.start(B=6)
        cast(self.ex, self.p0, wurm)
        self.assertEqual(self.count(ZONE_GRAVEYARD), [0, 1, 1])
        self.assertEqual(self.world.zone_of(mine).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.lives(), [20, 18, 18])

    def test_each_opponent_mills(self) -> None:
        # Thieves' Guild Enforcer: "Whenever this creature or another Rogue you control enters,
        # each opponent mills two cards."
        enforcer = self.real("Thieves' Guild Enforcer", self.p0, ZONE_HAND)
        self.start(B=3)
        cast(self.ex, self.p0, enforcer)
        self.assertEqual(self.count(ZONE_GRAVEYARD), [0, 2, 2])

    def test_an_opponent_condition_reads_any_opponent(self) -> None:
        # Thieves' Guild Enforcer: "As long as an opponent has eight or more cards in their
        # graveyard, this creature gets +2/+1 and has deathtouch." Only the second opponent does.
        enforcer = self.real("Thieves' Guild Enforcer", self.p0, ZONE_BATTLEFIELD)
        for i in range(8):
            self.world.add_card(card_id(f"Grave {i}", "1", "1"), self.p2, ZONE_GRAVEYARD)
        self.start()
        state = self.world.cards[enforcer]
        self.assertEqual(self.ex.ledger.effective_pt(state.identity, enforcer, state.counters), (3, 2))
        self.assertTrue(self.ex.layers.keyword_of(enforcer, Keyword.DEATHTOUCH))

    def test_teferis_ageless_insight_across_three_seats(self) -> None:
        # "If you would draw a card except the first one you draw in each of your draw steps, draw
        # two cards instead." Other players' turns leave it alone.
        insight = self.real("Teferi's Ageless Insight", self.p0, ZONE_BATTLEFIELD)
        self.start()
        self.assertEqual(self.count(ZONE_HAND), [1, 0, 0])
        self.ex.apply_effect(
            atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1)), source=insight, controller=self.p0
        )
        self.assertEqual(self.count(ZONE_HAND), [3, 0, 0])
        hands = []
        for _ in range(3):
            self.ex.end_turn()
            self.ex.advance_turn()
            hands.append(self.count(ZONE_HAND))
        self.assertEqual(hands, [[3, 1, 0], [3, 1, 1], [4, 1, 1]])

    def test_one_acting_player_never_stands_for_several(self) -> None:
        self.start()
        scry = atom(Verb.SCRY, controller=ControllerRef.ALL_OPPONENTS, count=QConst(1))
        with self.assertRaises(NotImplementedError) as caught:
            self.ex.apply_effect(scry, source=self.p0, controller=self.p0)
        self.assertIn("B-108", str(caught.exception))

    def test_two_seats_keep_the_lone_opponent(self) -> None:
        world = GameWorld(num_players=2, start_life=20, master_seed=41)
        ex = Executor(world)
        p0, p1 = world.player_order
        for i in range(3):
            world.add_card(card_id(f"Lib {i}", "1", "1"), p1, ZONE_LIBRARY)
        ex.decisions.provider = lambda vocab, what: vocab[0]
        draw = atom(Verb.DRAW, controller=ControllerRef.ALL_OPPONENTS, amount=QConst(1))
        ex.apply_effect(draw, source=p0, controller=p0)
        self.assertEqual(len(world.players[p1].zone(ZONE_HAND).entries), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
