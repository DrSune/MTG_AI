"""GAIN_CONTROL for a player other than "you": control given away (CR 110.2, 613.1b, 800.4a).

GAIN_CONTROL's ``controller`` role names who gains control. "You" is the ability's controller;
FDN Harmless Offering's "Target opponent gains control of target permanent you control" names a
designated player, and FDN Wishclaw Talisman's "An opponent gains control of this artifact" an
opponent: with one opponent that player, with several a choice the engine does not make (B-108),
so it refuses. The permanent's controller is the player the effect names (CR 110.2, layer 2: CR
613.1b), and its owner never changes (CR 108.3). CR 800.4a: when a player leaves the game, the
effects that gave that player control of objects end.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    FAnd,
    FAtom,
    FAtomPred,
    QConst,
    Selector,
    SelectorMode,
    SpellAbility,
    SpellKind,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND, GameWorld
from MTG_bot.core.test_executor_binding import card_id, record_of, reset_oracle_ids
from MTG_bot.core.test_executor_verbs import stock_libraries

_BF = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)


def _give(controller, target: Selector) -> Atom:
    return Atom(verb=Verb.GAIN_CONTROL,
                args=AtomArgs(pairs=(("controller", controller), ("target", target))))


def _target_you_control() -> Selector:
    """"target permanent you control"."""
    return Selector(QConst(1), SelectorMode.TARGET,
                    FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU), zones=(_BF,))


def _this() -> Selector:
    """"this artifact"."""
    return Selector(QConst(1), SelectorMode.CHOOSE, FAtom(FAtomPred.IS_SOURCE), zones=(_BF,))


class GiveControlTest(unittest.TestCase):
    def _world(self, seats: int = 2) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=seats, start_life=20, master_seed=11)
        self.seats = list(self.world.player_order)
        stock_libraries(self.world)
        self.ex = Executor(self.world)
        self.ex.begin_turn(self.seats[0])

    def _permanent(self, seat: int, name: str = "Relic") -> object:
        return self.world.add_card(card_id(name, "2", "2"), self.seats[seat], ZONE_BATTLEFIELD)

    def test_target_opponent_gains_control_of_your_permanent(self) -> None:
        """Harmless Offering: the caster designates an opponent and a permanent they control;
        the opponent controls it from then on (no duration: for the rest of the game), and the
        caster still owns it."""
        self._world()
        p0, p1 = self.seats
        relic = self._permanent(0)
        ident = CardIdentity(oracle_id=card_id("Offering").oracle_id, name="Offering",
                             type_line="Sorcery", cmc=0)
        offering = self.world.add_card(ident, p0, ZONE_HAND)
        self.ex.attach_card(offering, record_of(
            [SpellAbility(kind=SpellKind.SORCERY,
                          effect=_give(ControllerRef.TARGET_OPPONENT, _target_you_control()))],
            name="Offering", oid=ident.oracle_id))
        cast(self.ex, p0, offering, targets=(relic, p1))  # the permanent's slot, then the player's
        self.assertEqual(self.ex.controller_of(relic), p1)
        self.assertEqual(self.world.controller_of(relic), p0)  # its owner's zone (CR 108.3)
        self.ex.end_turn()
        self.ex.advance_turn()
        self.assertEqual(self.ex.controller_of(relic), p1)

    def test_an_opponent_gains_control_of_the_source(self) -> None:
        """Wishclaw Talisman's "An opponent gains control of this artifact": with one opponent,
        that player."""
        self._world()
        p0, p1 = self.seats
        talisman = self._permanent(0, "Talisman")
        self.ex.execute(_give(ControllerRef.OPPONENT, _this()), source=talisman, controller=p0)
        self.assertEqual(self.ex.controller_of(talisman), p1)

    def test_an_opponent_among_several_is_a_choice_the_engine_refuses(self) -> None:
        """With two opponents "an opponent" is one the controller picks; no such ask exists, so
        the move is loud (B-108), never the first seat."""
        self._world(seats=3)
        talisman = self._permanent(0, "Talisman")
        with self.assertRaises(NotImplementedError) as cm:
            self.ex.execute(_give(ControllerRef.OPPONENT, _this()), source=talisman,
                            controller=self.seats[0])
        self.assertIn("B-108", str(cm.exception))
        self.assertEqual(self.ex.controller_of(talisman), self.seats[0])

    def test_control_given_by_an_aura_names_its_controller_only(self) -> None:
        """"You control enchanted creature" (Enthralling Hold) follows the Aura's controller; the
        same entry for another player has no reading here, so it is refused, not guessed."""
        self._world()
        p0, _p1 = self.seats
        aura = self._permanent(0, "Hold")
        enchanted = Selector(QConst(1), SelectorMode.CHOOSE,
                             FAtom(FAtomPred.IS_ATTACHED_TO_SOURCE), zones=(_BF,))
        with self.assertRaises(NotImplementedError):
            self.ex.execute(_give(ControllerRef.OPPONENT, enchanted), source=aura, controller=p0)

    def test_control_ends_when_its_player_leaves_the_game(self) -> None:
        """CR 800.4a: in a game of three, the player who lost leaves it, and the effects that
        gave that player control end: the creature p0 stole goes back to its owner, while the one
        p1 stole stays p1's (both owned by p2, who stays: the leaver's own objects are another
        part of 800.4a, not modelled)."""
        self._world(seats=3)
        p0, p1, p2 = self.seats
        first, second = self._permanent(2, "First"), self._permanent(2, "Second")
        steal = Selector(QConst(1), SelectorMode.TARGET, FAnd(()), zones=(_BF,))
        self.ex.execute(_give(ControllerRef.YOU, steal), source=first, controller=p0,
                        bindings={"target": first})
        self.ex.execute(_give(ControllerRef.YOU, steal), source=second, controller=p1,
                        bindings={"target": second})
        self.assertEqual((self.ex.controller_of(first), self.ex.controller_of(second)), (p0, p1))
        self.world.players[p0].life = 0
        self.ex.fire_triggers()  # a priority check: the state-based actions (CR 704.5a)
        self.assertEqual(self.ex.lost_players, [p0])
        self.assertEqual(self.ex.controller_of(first), p2)
        self.assertEqual(self.ex.controller_of(second), p1)


if __name__ == "__main__":
    unittest.main()
