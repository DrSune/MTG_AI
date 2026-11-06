"""The defending player (2026-11-06): ``ControllerRef.DEFENDING_PLAYER``.

CR 506.2: during the combat phase of a two-player game the nonactive player is the defending
player. CR 508.5: an ability of an attacking creature, or one that names an attacking creature,
that refers to the defending player means the player that creature attacks or the controller of
the planeswalker it attacks. The engine's combat has one defending player, whom every attacker
attacks (it or a planeswalker that player controls), so the ref reads ``Executor.defending_player``.
Outside combat there is no defending player: the ref names no player, so "target creature
defending player controls" has no legal target and "defending player loses 1 life" does nothing.
"""

from __future__ import annotations

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    DeclareAttackersEvent,
    FAnd,
    FAtom,
    FAtomPred,
    QConst,
    Selector,
    SelectorMode,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
    from_dict,
    to_dict,
)
from MTG_bot.core.executor.quantity import ExecCtx
from MTG_bot.core.executor.selectors import controller_matches, players_for_ref
from MTG_bot.core.test_executor_blocker_limit import IS_SOURCE, LimitCase
from MTG_bot.core.test_executor_verbs import stock_libraries

DEFENDING = ControllerRef.DEFENDING_PLAYER
THEIRS = FAtom(FAtomPred.CONTROLLER_IS, who=DEFENDING)
CREATURE = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")


def on_attack(effect) -> TriggeredAbility:
    """"Whenever this creature attacks, <effect>." """
    return TriggeredAbility(event=DeclareAttackersEvent(filter=IS_SOURCE), condition=None, effect=effect)


def loses_life(n: int) -> Atom:
    return Atom(Verb.LOSE_LIFE, AtomArgs(pairs=(("amount", QConst(n)), ("controller", DEFENDING))))


def tap_target(filter_) -> Atom:
    target = Selector(QConst(1), SelectorMode.TARGET, filter_,
                      zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))
    return Atom(Verb.TAP, AtomArgs(pairs=(("target", target),)))


class TestDefendingPlayer(LimitCase):
    def ctx(self) -> ExecCtx:
        return self.ex._ctx(source=self.p0, controller=self.p0, bindings=None, decisions=())

    def test_there_is_none_outside_combat(self) -> None:
        self.begin()
        self.ex.begin_turn(self.p0)
        self.assertEqual(players_for_ref(DEFENDING, self.ctx()), [])
        self.assertFalse(controller_matches(DEFENDING, self.p1, self.ctx()))
        self.assertFalse(controller_matches(DEFENDING, self.p0, self.ctx()))

    def test_an_attack_trigger_makes_the_defending_player_lose_life(self) -> None:
        self.custom("Leech", 1, 1, self.p0, (on_attack(loses_life(1)),))
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        self.assertEqual(self.world.players[self.p1].life, 18)  # 1 from the trigger, 1 combat
        self.assertEqual(self.world.players[self.p0].life, 20)

    def test_the_defending_player_is_the_nonactive_player_on_either_turn(self) -> None:
        self.custom("Leech", 1, 1, self.p1, (on_attack(loses_life(1)),))
        stock_libraries(self.world)  # p1's turn draws (CR 704.5b)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.end_turn()
        self.ex.begin_turn(self.p1)
        self.ex.combat_step(self.p1)
        self.assertEqual(self.world.players[self.p0].life, 18)
        self.assertEqual(self.world.players[self.p1].life, 20)

    def test_the_target_menu_holds_only_the_defending_players_creatures(self) -> None:
        self.custom("Diverter", 2, 2, self.p0, (on_attack(tap_target(FAnd((CREATURE, THEIRS)))),))
        mine = self.synth("Goat", 1, 1, self.p0)
        bear = self.synth("Bear", 2, 2, self.p1)
        ogre = self.synth("Ogre", 3, 3, self.p1)
        self.begin()
        self.answers["attack:" + str(mine)] = "DECLINE"
        self.ex.begin_turn(self.p0)
        self.ex.combat_step(self.p0)
        menus = [set(vocab) for vocab, what in self.seen_asks if str(bear) in vocab]
        self.assertEqual(menus, [{str(bear), str(ogre)}])
        self.assertEqual(sum(self.world.cards[h].tapped for h in (bear, ogre)), 1)
        self.assertFalse(self.world.cards[mine].tapped)

    def test_one_acting_player_outside_combat_is_refused(self) -> None:
        self.begin()
        self.ex.begin_turn(self.p0)
        draw = Atom(Verb.DRAW, AtomArgs(pairs=(("amount", QConst(1)), ("controller", DEFENDING))))
        with self.assertRaisesRegex(NotImplementedError, "denotes none"):
            self.ex.execute(draw, source=self.p0, controller=self.p0)

    def test_a_bare_context_cannot_know_the_combat(self) -> None:
        bare = ExecCtx(world=self.world, ledger=self.ex.ledger, controller=self.p0,
                       source=self.p0, bindings={}, decisions=())
        with self.assertRaises(ValueError):
            players_for_ref(DEFENDING, bare)

    def test_the_ref_is_a_controller_is_slot_and_round_trips(self) -> None:
        self.assertEqual(from_dict("FAtom", to_dict(THEIRS)), THEIRS)
        self.assertEqual(from_dict("Atom", to_dict(loses_life(1))), loses_life(1))
