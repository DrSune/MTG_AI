"""V22 (2026-10-29): the legend rule, CR 704.5j.

"If two or more legendary permanents with the same name are controlled by the same player, that
player chooses one of them, and the rest are put into their owners' graveyards." It is a state-based
action (CR 704.3), so it runs at every settle point, and the choice is an explicit ask of that player
(``legend:<seat>:<digest>``, the live same-name group as the vocabulary).
"""

from __future__ import annotations

import unittest
from dataclasses import replace

from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.events import KIND_CREATURE_DIES
from MTG_bot.core.identity import CardIdentity, Handle
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, GameWorld

LEGEND = "Legendary Creature — Human Monk"


def legend(name: str = "Azusa", *, oid: str = "aaaaaaaa-1111-2222-3333-444444444444", **kw) -> CardIdentity:
    return CardIdentity(
        oracle_id=oid, name=name, type_line=kw.pop("type_line", LEGEND), power="1", toughness="2", cmc=3, **kw
    )


class LegendRuleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.world = GameWorld(num_players=2, start_life=20, master_seed=3)
        self.ex = Executor(self.world)
        self.p0, self.p1 = self.world.player_order
        self.asks: list[tuple[str, tuple[str, ...], Handle | None]] = []
        self.keep: list[Handle] = []

        def provider(vocab: tuple[str, ...], what: str) -> str:
            self.asks.append((what, vocab, self.ex.decisions.asking_seat))
            pick = next((str(h) for h in self.keep if str(h) in vocab), vocab[0])
            return pick

        self.ex.decisions.provider = provider

    def add(self, identity: CardIdentity, seat: Handle) -> Handle:
        return self.world.add_card(identity, seat, ZONE_BATTLEFIELD)

    def settle(self) -> None:
        self.ex._settle()

    def zones(self, *handles: Handle) -> list[str]:
        return [self.world.zone_of(h).kind for h in handles]

    def test_two_copies_ask_the_controller_and_the_rest_go(self) -> None:
        old, new = self.add(legend(), self.p0), self.add(legend(), self.p0)
        self.keep = [new]
        self.settle()
        self.assertEqual(self.zones(old, new), [ZONE_GRAVEYARD, ZONE_BATTLEFIELD])
        self.assertEqual(len(self.asks), 1)
        what, vocab, seat = self.asks[0]
        self.assertTrue(what.startswith(f"legend:{self.p0}:"), what)
        self.assertEqual(vocab, (str(old), str(new)))
        self.assertEqual(seat, self.p0)
        # From the battlefield to a graveyard is dying (CR 700.4): dies triggers see it.
        dies = [r for r in self.ex.journal.dump() if r[1] == KIND_CREATURE_DIES]
        self.assertEqual([r[2] for r in dies], [str(old)])

    def test_three_copies_one_ask_two_go(self) -> None:
        a, b, c = (self.add(legend(), self.p0) for _ in range(3))
        self.keep = [b]
        self.settle()
        self.assertEqual(self.zones(a, b, c), [ZONE_GRAVEYARD, ZONE_BATTLEFIELD, ZONE_GRAVEYARD])
        self.assertEqual([len(v) for _w, v, _s in self.asks], [3])

    def test_planeswalkers_with_the_same_name(self) -> None:
        walker = {"type_line": "Legendary Planeswalker — Liliana", "loyalty": "4"}
        one = self.add(replace(legend("Liliana"), **walker), self.p0)
        two = self.add(replace(legend("Liliana"), **walker), self.p0)
        self.world.cards[two].counters["LOYALTY"] = 4
        self.keep = [one]
        self.settle()
        self.assertEqual(self.zones(one, two), [ZONE_BATTLEFIELD, ZONE_GRAVEYARD])
        self.assertNotIn("LOYALTY", self.world.cards[two].counters)  # a new object if it returns

    def test_different_names_or_controllers_coexist(self) -> None:
        mine = self.add(legend("Azusa"), self.p0)
        other_name = self.add(legend("Radha", oid="bbbbbbbb-1111-2222-3333-444444444444"), self.p0)
        theirs = self.add(legend("Azusa"), self.p1)
        nonlegendary = self.add(legend("Azusa", type_line="Creature — Human Monk"), self.p0)
        self.settle()
        self.assertEqual(self.asks, [])
        self.assertEqual(self.zones(mine, other_name, theirs, nonlegendary), [ZONE_BATTLEFIELD] * 4)

    def test_a_token_copy_is_a_legendary_permanent_too(self) -> None:
        card = self.add(legend(), self.p0)
        token = self.add(replace(legend(), oracle_id="cccccccc-1111-2222-3333-444444444444", is_token=True), self.p0)
        self.keep = [card]
        self.settle()
        # re-pinned 2026-10-30: the merge of cards/integration (V35, CR 704.5d) changes where the
        # token ends: it goes to the graveyard and then ceases to exist, so it is in no zone.
        self.assertEqual(self.zones(card), [ZONE_BATTLEFIELD])
        self.assertNotIn(token, self.world.cards)

    def test_control_is_the_effective_one(self) -> None:
        # Player 1 steals player 0's Azusa while controlling one: player 1 now controls two.
        stolen, theirs = self.add(legend(), self.p0), self.add(legend(), self.p1)
        self.ex.gain_control(stolen, self.p1, "Permanent")
        self.keep = [stolen]
        self.settle()
        self.assertEqual([s for _w, _v, s in self.asks], [self.p1])
        # The one not kept goes to its OWNER's graveyard.
        self.assertEqual(self.zones(stolen, theirs), [ZONE_BATTLEFIELD, ZONE_GRAVEYARD])
        self.assertIn(theirs, self.world.players[self.p1].zone(ZONE_GRAVEYARD).entries)

    def test_both_players_choose_in_apnap_order(self) -> None:
        self.ex.begin_turn(self.p1)
        self.asks.clear()
        mine = [self.add(legend(), self.p0) for _ in range(2)]
        theirs = [self.add(legend(), self.p1) for _ in range(2)]
        self.keep = [mine[1], theirs[1]]
        self.settle()
        self.assertEqual([s for _w, _v, s in self.asks], [self.p1, self.p0])  # active player first
        self.assertEqual(self.zones(*mine, *theirs), [ZONE_GRAVEYARD, ZONE_BATTLEFIELD] * 2)

    def test_a_copy_lethally_damaged_that_is_not_kept_moves_once(self) -> None:
        hurt, fresh = self.add(legend(), self.p0), self.add(legend(), self.p0)
        self.ex.mark_damage(hurt, 2)  # lethal for a 1/2
        self.keep = [fresh]
        self.settle()
        self.assertEqual(self.zones(hurt, fresh), [ZONE_GRAVEYARD, ZONE_BATTLEFIELD])
        dies = [r for r in self.ex.journal.dump() if r[1] == KIND_CREATURE_DIES]
        self.assertEqual([r[2] for r in dies], [str(hurt)])

    def test_unanswered_legend_rule_raises_never_a_silent_pick(self) -> None:
        self.add(legend(), self.p0)
        self.add(legend(), self.p0)
        self.ex.decisions.provider = None
        with self.assertRaises(ValueError):
            self.settle()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
