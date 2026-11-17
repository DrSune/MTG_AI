"""What a Conditional right after a look judges, and which cast "this spell was cast from" reads.

M21 See the Truth: "Look at the top three cards of your library. Put one of those cards into your
hand and the rest on the bottom of your library in any order. If this spell was cast from anywhere
other than your hand, put each of those cards into your hand instead." Its "instead" (CR 608.2c)
compiles as Conditional(not cast from your hand, every looked-at card into your hand, else=the
split) right after the look, so the Conditional runs while the look window is open. The window's
card is the subject of a characteristic test about it ("If it's a creature card", Track Down,
Garruk, Savage Herald); a history question about the spell is judged on the spell. The cast it
reads is the spell's own (CR 400.7): the packs see_the_truth_recast_from_your_graveyard_reads_the_
second_cast and archfiends_vessel_cast_from_graveyard_then_from_hand_same_turn pin that end to end.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    Conditional,
    ControllerRef,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    QConst,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    SpellKind,
    Verb,
    Zone,
    ZoneKind,
    ZonePosition,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_HAND, ZONE_LIBRARY, GameWorld
from MTG_bot.core.test_executor_binding import card_id, record_of, reset_oracle_ids

_TOP = Zone(ZoneKind.LIBRARY, ControllerRef.YOU, position=ZonePosition.TOP)
_HAND = Zone(ZoneKind.HAND, ControllerRef.YOU)


def _atom(verb: Verb, **roles) -> Atom:
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


def _look_then(condition, then_effect, else_effect=None) -> Seq:
    """Look at the top three cards, then a Conditional while the window is open."""
    return Seq(
        steps=(
            _atom(Verb.LOOK_AT, controller=ControllerRef.YOU, count=QConst(3)),
            Conditional(pred=condition, then_effect=then_effect, else_effect=else_effect),
        )
    )


def _see_the_truth() -> Seq:
    """See the Truth's tree as the compiler emits it (B5b-cast-elsewhere-instead)."""
    every_looked = Selector(QUnbounded(), SelectorMode.ALL, FAnd(()), zones=(_TOP,))
    one = Selector(QConst(1), SelectorMode.ONE_OF, FAnd(()), zones=(_TOP,))
    rest = Selector(QConst(1), SelectorMode.REST, FAnd(()), zones=(_TOP,))
    bottom = Zone(ZoneKind.LIBRARY, ControllerRef.YOU, position=ZonePosition.BOTTOM)
    return _look_then(
        FNot(FAtom(FAtomPred.CAST_THIS_TURN_FROM, zone=_HAND, who=ControllerRef.YOU)),
        _atom(Verb.MOVE_ZONE, cards=every_looked, destination=_HAND),
        Seq(
            steps=(
                _atom(Verb.MOVE_ZONE, cards=one, destination=_HAND),
                _atom(Verb.MOVE_ZONE, cards=rest, destination=bottom),
            )
        ),
    )


class LookThenConditionTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=11)
        self.p0, self.p1 = self.world.player_order
        for i in range(5):  # the top of the library is the last added
            self.world.add_card(card_id(f"Lib {i}", "1", "1"), self.p0, ZONE_LIBRARY)
        self.ex = Executor(self.world)
        self.ex.begin_turn(self.p0)  # the main phase of p0's turn: a sorcery may be cast
        self.asks: list[str] = []

        def first_word(vocab, what):
            self.asks.append(what.split(":")[0])
            return vocab[0]

        self.ex.decisions.provider = first_word

    def _cast_sorcery(self, effect) -> None:
        ident = CardIdentity(oracle_id=card_id("Truthish").oracle_id, name="Truthish",
                             type_line="Sorcery", cmc=0)
        spell = self.world.add_card(ident, self.p0, ZONE_HAND)
        self.ex.attach_card(spell, record_of([SpellAbility(kind=SpellKind.SORCERY, effect=effect)],
                                             name="Truthish", oid=ident.oracle_id))
        cast(self.ex, self.p0, spell)

    def _hand(self) -> list[str]:
        return sorted(self.world.cards[h].identity.name
                      for h in self.world.players[self.p0].zone(ZONE_HAND).entries)

    def test_a_history_condition_after_a_look_judges_the_spell(self) -> None:
        """Cast from the hand, See the Truth's condition is false: one card is chosen for the
        hand and the rest go to the bottom. Judged on the looked-at card (never cast), the
        condition was true and all three went to the hand."""
        self._cast_sorcery(_see_the_truth())
        self.assertEqual(self._hand(), ["Lib 2"])  # vocab[0]: the Handle-first looked-at card
        self.assertIn("one_of", self.asks)
        library = [self.world.cards[h].identity.name
                   for h in self.world.players[self.p0].zone(ZONE_LIBRARY).entries]
        self.assertEqual(library[2:], ["Lib 0", "Lib 1"])  # the top is the last entry

    def test_a_characteristic_condition_after_a_look_judges_the_card_shown(self) -> None:
        """"If it's a creature card" right after the look reads the top looked-at card (Lib 4, a
        creature) and its Land twin reads it too (false), whatever the spell itself is."""
        draw = _atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1))
        creature = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")
        self._cast_sorcery(Seq(steps=(
            _look_then(creature, draw),
            _look_then(FAtom(FAtomPred.TYPE_EQ, string_value="Land"), draw),
        )))
        self.assertEqual(self._hand(), ["Lib 4"])


if __name__ == "__main__":
    unittest.main()
