""""Any number of" is every number from zero to all of them (CR 107.1c), and a card put from a hand
anywhere but a graveyard is no discard.

- An effect's CHOOSE over an unbounded count (QUnbounded) asks its decider pick by pick, each ask
  with a NONE stop, as "up to N" does: M20 Battalion Foot Soldier's search ("any number of cards
  named Battalion Foot Soldier", which may also fail to find, CR 701.23b), Cavalier of Flame's
  "discard any number of cards, then draw that many", M21 Siege Striker's "tap any number of
  untapped creatures you control", Necromentia's search of another player's hand and library (a
  searcher sees every card of a searched zone, CR 701.23a).
- A population read of the same selector (a count, a query, the CAST lane) still takes all of it.
- Cavalier of Gales's "put two cards from your hand on top of your library" is the effect's choice
  (``choose:``), not a discard (``discard:`` is CR 701.9a's, a move to the graveyard).
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    FAnd,
    FAtom,
    FAtomPred,
    QConst,
    QProp,
    QPropField,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    Verb,
    Zone,
    ZoneKind,
    ZonePosition,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.legality import ctx_for
from MTG_bot.core.executor.selectors import resolve_selector
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import BF_ANY, HAND_YOU, LIB_YOU, UNIV, atom, card_id, reset_oracle_ids

GY_YOU = Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)
HAND_TO = Zone(ZoneKind.HAND, ControllerRef.YOU)


def any_number(filter_, *zones) -> Selector:
    return Selector(QUnbounded(), SelectorMode.CHOOSE, filter_, zones=zones)


class AnyNumberCase(unittest.TestCase):
    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=5)
        self.p0, self.p1 = self.world.player_order
        self.source = self.world.add_card(card_id("Source", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        self.ex = Executor(self.world)
        self.asks: list[tuple[str, tuple[str, ...], object]] = []

    def answer(self, *words: str) -> None:
        """Answer the asks in order with ``words``; record (site, vocabulary, deciding seat)."""
        queue = list(words)

        def provider(vocab, what):
            self.asks.append((what, tuple(vocab), self.ex.decisions.asking_seat))
            return queue.pop(0)

        self.ex.decisions.provider = provider

    def zone(self, card) -> str:
        return self.world.zone_of(card).kind


class TestAnyNumberIsAsked(AnyNumberCase):
    def test_a_search_for_any_number_asks_and_may_stop(self) -> None:
        # Battalion Foot Soldier: three copies in the library, the player takes two.
        named = FAtom(FAtomPred.NAME_EQ, string_value="Foot Soldier")
        soldiers = [self.world.add_card(card_id("Foot Soldier", "2", "2"), self.p0, ZONE_LIBRARY)
                    for _ in range(3)]
        other = self.world.add_card(card_id("Other", "1", "1"), self.p0, ZONE_LIBRARY)
        self.answer(str(soldiers[1]), str(soldiers[2]), "NONE")
        self.ex.execute(atom(Verb.SEARCH, cards=any_number(named, LIB_YOU), destination=HAND_TO),
                        source=self.source, controller=self.p0)
        self.assertEqual([self.zone(c) for c in soldiers], [ZONE_LIBRARY, ZONE_HAND, ZONE_HAND])
        self.assertEqual(self.zone(other), ZONE_LIBRARY)
        self.assertEqual([vocab for _, vocab, _ in self.asks], [
            (*map(str, soldiers), "NONE"),
            (str(soldiers[0]), str(soldiers[2]), "NONE"),
            (str(soldiers[0]), "NONE"),
        ])
        self.assertTrue(all(w.startswith(f"choose:{self.source}:") for w, _, _ in self.asks))

    def test_a_search_for_any_number_may_find_none(self) -> None:
        # CR 701.23b: a search for cards with a stated quality may fail to find.
        named = FAtom(FAtomPred.NAME_EQ, string_value="Foot Soldier")
        soldier = self.world.add_card(card_id("Foot Soldier", "2", "2"), self.p0, ZONE_LIBRARY)
        self.answer("NONE")
        self.ex.execute(atom(Verb.SEARCH, cards=any_number(named, LIB_YOU), destination=HAND_TO),
                        source=self.source, controller=self.p0)
        self.assertEqual(self.zone(soldier), ZONE_LIBRARY)
        self.assertEqual(len(self.asks), 1)

    def test_discard_any_number_then_draw_that_many(self) -> None:
        # Cavalier of Flame: of three cards in hand the player discards one, so draws one.
        hand = [self.world.add_card(card_id(f"H{i}", "1", "1"), self.p0, ZONE_HAND) for i in range(3)]
        lib = [self.world.add_card(card_id(f"L{i}", "1", "1"), self.p0, ZONE_LIBRARY) for i in range(3)]
        discard = atom(Verb.MOVE_ZONE, cards=any_number(UNIV, HAND_YOU), controller=ControllerRef.YOU,
                       destination=GY_YOU, **{"from": HAND_YOU})
        draw = atom(Verb.DRAW, controller=ControllerRef.YOU,
                    amount=QProp(referent="event", field=QPropField.THAT_MANY_COUNT))
        self.answer(str(hand[2]), "NONE")
        self.ex.apply_effect(Seq((discard, draw)), source=self.source, controller=self.p0,
                             bindings={"event": [self.source]})
        self.assertEqual([self.zone(c) for c in hand], [ZONE_HAND, ZONE_HAND, ZONE_GRAVEYARD])
        self.assertEqual([self.zone(c) for c in lib], [ZONE_LIBRARY, ZONE_LIBRARY, ZONE_HAND])
        self.assertEqual([vocab for _, vocab, _ in self.asks],
                         [(*map(str, hand), "NONE"), (str(hand[0]), str(hand[1]), "NONE")])
        self.assertTrue(all(w.startswith(f"discard:{self.p0}:") for w, _, _ in self.asks))

    def test_discarding_none_draws_none(self) -> None:
        hand = [self.world.add_card(card_id(f"H{i}", "1", "1"), self.p0, ZONE_HAND) for i in range(2)]
        lib = self.world.add_card(card_id("L0", "1", "1"), self.p0, ZONE_LIBRARY)
        discard = atom(Verb.MOVE_ZONE, cards=any_number(UNIV, HAND_YOU), controller=ControllerRef.YOU,
                       destination=GY_YOU, **{"from": HAND_YOU})
        draw = atom(Verb.DRAW, controller=ControllerRef.YOU,
                    amount=QProp(referent="event", field=QPropField.THAT_MANY_COUNT))
        self.answer("NONE")
        self.ex.apply_effect(Seq((discard, draw)), source=self.source, controller=self.p0,
                             bindings={"event": [self.source]})
        self.assertEqual([self.zone(c) for c in (*hand, lib)], [ZONE_HAND, ZONE_HAND, ZONE_LIBRARY])

    def test_tap_any_number_taps_the_picked_creatures(self) -> None:
        # Siege Striker: "you may tap any number of untapped creatures you control".
        mine = [self.world.add_card(card_id(f"C{i}", "1", "1"), self.p0, ZONE_BATTLEFIELD) for i in range(2)]
        self.world.add_card(card_id("Theirs", "1", "1"), self.p1, ZONE_BATTLEFIELD)
        yours = FAnd((FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU), FAtom(FAtomPred.IS_UNTAPPED),
                      FAtom(FAtomPred.TYPE_EQ, string_value="Creature")))
        self.answer(str(mine[0]), "NONE")
        self.ex.execute(atom(Verb.TAP, target=any_number(yours, BF_ANY)), source=self.source,
                        controller=self.p0)
        tapped = {h for h, c in self.world.cards.items() if c.tapped}
        self.assertEqual(tapped, {mine[0]})
        self.assertEqual(self.asks[0][1], (*map(str, sorted((self.source, *mine))), "NONE"))

    def test_a_search_of_another_players_hidden_zones_asks_the_searcher(self) -> None:
        # Necromentia: "search target opponent's graveyard, hand, and library for any number of
        # cards with that name": the searcher sees those zones (CR 701.23a) and leaves the hand.
        named = FAtom(FAtomPred.NAME_EQ, string_value="Bolt")
        in_hand = self.world.add_card(card_id("Bolt"), self.p1, ZONE_HAND)
        in_library = self.world.add_card(card_id("Bolt"), self.p1, ZONE_LIBRARY)
        zones = (Zone(ZoneKind.HAND, ControllerRef.OPPONENT), Zone(ZoneKind.LIBRARY, ControllerRef.OPPONENT))
        self.answer(str(in_library), "NONE")
        self.ex.execute(atom(Verb.SEARCH, cards=any_number(named, *zones),
                             destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                        source=self.source, controller=self.p0)
        self.assertEqual((self.zone(in_hand), self.zone(in_library)), (ZONE_HAND, ZONE_EXILE))
        self.assertEqual(self.asks[0][2], self.p0)

    def test_a_population_read_still_takes_all(self) -> None:
        # A count or a query reads the whole menu: no ask.
        cards = [self.world.add_card(card_id(f"C{i}", "1", "1"), self.p0, ZONE_BATTLEFIELD) for i in range(2)]
        self.answer()
        ctx = ctx_for(self.ex, source=self.source, controller=self.p0)
        out = resolve_selector(any_number(UNIV, BF_ANY), ctx)
        self.assertEqual(out, sorted((self.source, *cards)))
        self.assertEqual(self.asks, [])


class TestAPutFromHandIsNoDiscard(AnyNumberCase):
    def test_cards_put_on_top_from_a_hand_are_asked_as_a_choice(self) -> None:
        # Cavalier of Gales: three cards in hand, two go on top: the picks are a choice of the
        # effect, then the owner orders them (CR 401.4).
        hand = [self.world.add_card(card_id(f"H{i}", "1", "1"), self.p0, ZONE_HAND) for i in range(3)]
        two = Selector(QConst(2), SelectorMode.CHOOSE, UNIV, zones=(HAND_YOU,))
        move = atom(Verb.MOVE_ZONE, cards=two, controller=ControllerRef.YOU,
                    destination=Zone(ZoneKind.LIBRARY, ControllerRef.YOU, position=ZonePosition.TOP),
                    **{"from": HAND_YOU})
        self.answer(str(hand[2]), str(hand[0]), str(hand[0]))
        self.ex.execute(move, source=self.source, controller=self.p0)
        sites = [w for w, _, _ in self.asks]
        self.assertEqual([w.split(":")[0] for w in sites], ["choose", "choose", "arrange"])
        self.assertTrue(sites[0].startswith(f"choose:{self.source}:1of2:"), sites)
        self.assertEqual(self.world.players[self.p0].zone(ZONE_LIBRARY).entries[-2:], [hand[2], hand[0]])
        self.assertEqual(self.zone(hand[1]), ZONE_HAND)

    def test_a_discard_is_still_asked_as_a_discard(self) -> None:
        hand = [self.world.add_card(card_id(f"H{i}", "1", "1"), self.p0, ZONE_HAND) for i in range(2)]
        one = Selector(QConst(1), SelectorMode.CHOOSE, UNIV, zones=(HAND_YOU,))
        self.answer(str(hand[1]))
        self.ex.execute(atom(Verb.MOVE_ZONE, cards=one, controller=ControllerRef.YOU, destination=GY_YOU,
                             **{"from": HAND_YOU}), source=self.source, controller=self.p0)
        self.assertEqual([w for w, _, _ in self.asks], [self.asks[0][0]])
        self.assertTrue(self.asks[0][0].startswith(f"discard:{self.p0}:{self.source}:"))
        self.assertEqual(self.zone(hand[1]), ZONE_GRAVEYARD)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
