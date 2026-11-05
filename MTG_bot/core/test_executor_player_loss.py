"""The player-loss state-based actions and the end of the game (2026-11-05).

CR 704.5a: a player with 0 or less life loses. CR 704.5b: a player who attempted to draw
from an empty library since the last check loses. CR 704.3: the check happens whenever a
player would receive priority, and in a two-player game a loss ends the game there (CR
104.2a; both players at once is a draw, 104.4a). The engine raises :class:`GameOver` at that
check, so nothing after it happens: no further act, no combat, no regular damage after a
lethal first strike, no cleanup step after a lethal end step.

Regressions for the 2026-11-05 whole-game audits: a player at -1 life kept acting, attacked,
lifelinked back above 0 and won (41 of 1,000 games; invariant-hunt seed 478); the harness
declared a deck-out loss one draw early, right after a player drew their last card (seed 427
recorded a draw that was a seat-0 win), and a mid-turn draw from an empty library went
unnoticed until the next draw step.
"""

from __future__ import annotations

from MTG_bot.core.ability_tree import (
    ControllerRef,
    Cost,
    CostLife,
    CostSacrifice,
    CreatureDiesEvent,
    DurationEot,
    FAtom,
    FAtomPred,
    Keyword,
    KeywordAbility,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import GameOver
from MTG_bot.core.executor.games import Game, _play
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND, ZONE_LIBRARY
from MTG_bot.core.test_executor_combat import CombatCase
from MTG_bot.core.test_executor_verbs import atom, stock_libraries, target_sel


class LossCase(CombatCase):
    def lost_rows(self):
        return [(e.subject, e.data[0]) for e in self.rows("GAME_LOST")]

    def grant(self, card, keyword) -> None:
        self.ex.execute(
            atom(Verb.GRANT_ABILITY, target=target_sel(), ability=KeywordAbility(keyword=keyword)),
            source=card,
            controller=self.world.controller_of(card),
            bindings={"target": card},
        )


class TestLifeLoss(LossCase):
    def test_zero_life_after_an_act_ends_the_game_at_its_check(self):
        # Grim Tutor: "... You lose 3 life." At 3 life the caster is at 0 when
        # the spell has resolved, and loses at the check that follows.
        tutor = self.real("Grim Tutor", self.p0, ZONE_HAND)
        stock_libraries(self.world, seats=[self.p0])
        self.begin()
        self.ex.begin_turn(self.p0)
        self.world.players[self.p0].life = 3
        self.world.players[self.p0].mana_pool.update({"B": 3})
        with self.assertRaises(GameOver):
            cast(self.ex, self.p0, tutor)
        self.assertEqual(self.ex.lost_players, [self.p0])
        self.assertEqual(self.lost_rows(), [(self.p0, "LIFE")])

    def test_lethal_first_strike_ends_the_game_before_regular_damage(self):
        # p1 at 2: the first striker's 2 kills p1 in the first damage step.
        # The regular step never happens, so p1's lifelink blocker cannot
        # bring p1 back above 0 (it used to: p1 ended at 1 and lived).
        fencer = self.synth("Fencer", 2, 2, self.p0)
        grunt = self.synth("Grunt", 1, 3, self.p0)
        leech = self.synth("Leech", 1, 1, self.p1)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.grant(fencer, Keyword.FIRST_STRIKE)
        self.grant(leech, Keyword.LIFELINK)
        self.world.players[self.p1].life = 2
        self.answers[f"block:{leech}"] = str(grunt)
        with self.assertRaises(GameOver):
            self.ex.combat_step(self.p0)
        self.assertEqual(self.world.players[self.p1].life, 0)
        self.assertEqual(self.ex.lost_players, [self.p1])
        self.assertEqual([e.subject for e in self.rows("COMBAT_DAMAGE")], [fencer])
        self.assertEqual(self.ex.damage, {})  # no regular damage to grunt or leech

    def test_a_loss_in_the_end_step_ends_the_game_before_cleanup(self):
        # Indulging Patrician: "At the beginning of your end step, if you
        # gained 3 or more life this turn, each opponent loses 3 life." p1 at
        # 3 loses at the end step's check; the cleanup step never starts, so
        # p0 is never asked to discard down to seven.
        self.real("Indulging Patrician", self.p0)
        for i in range(8):
            self.synth(f"Card {i}", 1, 1, self.p0, ZONE_HAND)
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.execute(
            atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(3)),
            source=self.p0,
            controller=self.p0,
        )
        self.world.players[self.p1].life = 3
        with self.assertRaises(GameOver):
            self.ex.end_turn()
        self.assertEqual(self.world.players[self.p1].life, 0)
        self.assertEqual(self.ex.lost_players, [self.p1])
        self.assertEqual(self.hand(self.p0), 8)
        self.assertFalse([w for _v, w in self.seen_asks if w.startswith("discard:")])

    def test_both_players_at_zero_at_one_check_is_a_draw(self):
        self.begin()
        self.ex.begin_turn(self.p0)
        for seat in (self.p0, self.p1):
            self.world.players[seat].life = 0
        with self.assertRaises(GameOver):
            self.ex.end_turn()
        self.assertEqual(self.ex.lost_players, [self.p0, self.p1])
        game = Game(executor=self.ex, seed=0, pool_mode="all")
        self.assertEqual(
            game.over_reason(), "draw: player:0(life<=0), player:1(life<=0)"
        )


class TestSimultaneousTriggerOrder(LossCase):
    """CR 603.3b: triggered abilities that triggered since a player last received priority are
    put on the stack in APNAP order, the active player's first, so the non-active player's
    resolve first (the stack resolves from the top, CR 405.5). Both players at 3 life; the
    active player's Pitchburn Devils attacks into the other Devils, both die, and each dies
    trigger ("it deals 3 damage to any target") aims at the opponent. The non-active player's
    trigger resolves first, so the active player is at 0 at the check after it and loses
    (CR 704.5a). The drain used to resolve by seat index, so seat 0 always won the race
    (2 of 2,000 integration games ended in such a drain, rules red-team 2026-11-05)."""

    def _race(self, active: int) -> None:
        ap, nap = self.world.player_order[active], self.world.player_order[1 - active]
        devils_ap = self.real("Pitchburn Devils", ap)
        devils_nap = self.real("Pitchburn Devils", nap)
        stock_libraries(self.world, seats=[self.p0, self.p1])
        self.begin()
        self.ex.begin_turn(self.p0)
        if active == 1:
            self.ex.end_turn()
            self.ex.advance_turn()
        self.assertEqual(self.world.active_player, ap)
        self.world.players[self.p0].life = 3
        self.world.players[self.p1].life = 3
        self.answers[f"block:{devils_nap}"] = str(devils_ap)
        self.answers[f"target:{ap}:{devils_ap}"] = str(nap)
        self.answers[f"target:{nap}:{devils_nap}"] = str(ap)
        with self.assertRaises(GameOver):
            self.ex.combat_step(ap)
        self.assertEqual(self.ex.lost_players, [ap])
        self.assertEqual(self.world.players[nap].life, 3)

    def test_seat_0_active_loses_the_race(self):
        self._race(0)

    def test_seat_1_active_loses_the_race(self):
        self._race(1)


class TestNoCheckInsideAResolution(LossCase):
    """CR 704.3: state-based actions are checked only when a player would receive priority,
    never while a spell or ability resolves, and CR 603.3: a triggered ability waits for
    that moment too. A cost paid by an effect ("you may pay 2 life. If you do, ...") went
    through legality.pay_costs, whose steps are public ops that each settled: the
    player-loss check ran in the middle of the resolution and could end the game there,
    and the triggers the payment caused resolved before the rest of the effect."""

    def test_paying_life_to_zero_then_gaining_it_back_is_no_loss(self):
        self.begin()
        self.ex.begin_turn(self.p0)
        self.world.players[self.p0].life = 2
        pay_then_gain = Seq(
            steps=(
                atom(Verb.PAY, cost=Cost(parts=(CostLife(amount=QConst(2)),))),
                atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(3)),
            )
        )
        source = self.synth("Payer", 1, 1, self.p0)
        self.ex.apply_effect(pay_then_gain, source=source, controller=self.p0)
        self.assertEqual(self.world.players[self.p0].life, 3)
        self.assertEqual(self.ex.lost_players, [])

    def test_a_trigger_the_payment_causes_waits_for_the_resolution(self):
        # The effect sacrifices a creature as a cost, then sets Target to 2/2. A dies
        # trigger sets Target to 5/5; it resolves after the effect, so 5/5 is last.
        target = self.synth("Target", 3, 3, self.p0)
        fodder = self.synth("Fodder", 1, 1, self.p0)
        watcher = self.synth("Watcher", 1, 1, self.p1)
        self.begin()
        self.ex.begin_turn(self.p0)
        named = lambda name: Selector(  # noqa: E731
            QConst(1),
            SelectorMode.CHOOSE,
            FAtom(FAtomPred.NAME_EQ, string_value=name),
            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
        )
        set_pt = lambda n: atom(  # noqa: E731
            Verb.SET_PT, target=named("Target"), duration=DurationEot(),
            power=QConst(n), toughness=QConst(n),
        )
        from MTG_bot.core.test_executor_binding import record_of

        self.ex.attach_card(
            watcher,
            record_of(
                [TriggeredAbility(CreatureDiesEvent(filter=FAtom(FAtomPred.NAME_EQ, string_value="Fodder")), None, set_pt(5))],
                oid=self.world.cards[watcher].identity.oracle_id,
            ),
        )
        sacrifice_then_set = Seq(
            steps=(
                atom(Verb.PAY, cost=Cost(parts=(CostSacrifice(target=named("Fodder")),))),
                set_pt(2),
            )
        )
        self.ex.apply_effect(sacrifice_then_set, source=target, controller=self.p0)
        self.assertEqual(self.world.zone_of(fodder).kind, "graveyard")
        power, toughness = self.ex.ledger.effective_pt(self.world.cards[target].identity, target)
        self.assertEqual((power, toughness), (5, 5))


class TestDrawFromEmptyLibrary(LossCase):
    def test_drawing_the_last_card_is_not_a_loss(self):
        self.synth("Last Card", 1, 1, self.p1, ZONE_LIBRARY)
        stock_libraries(self.world, seats=[self.p0])
        self.begin()
        self.ex.begin_turn(self.p0)
        self.ex.advance_turn()  # p1 draws its last card: no loss yet
        self.assertEqual(self.hand(self.p1), 1)
        self.assertEqual(self.ex.lost_players, [])
        self.ex.advance_turn()
        with self.assertRaises(GameOver):
            self.ex.advance_turn()  # now p1 attempts to draw from an empty library
        self.assertEqual(self.ex.lost_players, [self.p1])
        self.assertEqual(self.lost_rows(), [(self.p1, "EMPTY_LIBRARY")])

    def test_a_mid_turn_draw_from_an_empty_library_loses_at_that_check(self):
        stock_libraries(self.world, seats=[self.p1])
        self.begin()
        self.ex.begin_turn(self.p0)  # p0 has no library; turn 1 draws nothing
        self.assertEqual(self.ex.lost_players, [])
        with self.assertRaises(GameOver):
            self.ex.execute(
                atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1)),
                source=self.p0,
                controller=self.p0,
            )
        self.assertEqual(self.ex.lost_players, [self.p0])
        self.assertEqual(self.lost_rows(), [(self.p0, "EMPTY_LIBRARY")])


class ScriptedPolicy:
    """A ``_play`` policy: ``acts(game, seat)`` runs in each act window; asks
    take ATTACK when offered, else the first word."""

    def __init__(self, acts=None) -> None:
        self.acts = acts
        self.windows: list[tuple[int, object]] = []

    def answer(self, vocab, what):
        return "ATTACK" if "ATTACK" in vocab else vocab[0]

    def take_acts(self, game, seat) -> None:
        self.windows.append((game.world.turn, seat))
        if self.acts is not None:
            self.acts(game, seat)


class TestTheGameEnds(LossCase):
    """Through the game driver ``games._play``."""

    def game(self) -> Game:
        self.ex.attach_pool(self.supply.pool)
        return Game(executor=self.ex, seed=0, pool_mode="all")

    def test_an_act_that_kills_its_caster_ends_the_game_before_combat(self):
        # The audit's dead_combat line: at 3 life with a lifelink attacker,
        # the active player casts Grim Tutor as its last act. It used to
        # attack anyway, lifelink back to 1 and survive.
        vessel = self.real("Archfiend's Vessel", self.p0)  # 1/1 lifelink
        tutor = self.real("Grim Tutor", self.p0, ZONE_HAND)
        stock_libraries(self.world, seats=[self.p0])
        stock_libraries(self.world, seats=[self.p1])
        game = self.game()
        self.world.players[self.p0].life = 3

        def acts(game, seat):
            game.world.players[seat].mana_pool.update({"B": 3})
            cast(game.executor, seat, tutor)

        policy = ScriptedPolicy(acts)
        _play(game, policy, self.world.player_order, turn_cap=1)
        self.assertEqual(game.reason, "game over: player:0(life<=0)")
        self.assertEqual(self.ex.lost_players, [self.p0])
        self.assertEqual(self.world.players[self.p0].life, 0)
        self.assertEqual(self.rows("DECLARE_ATTACKERS"), [])
        self.assertEqual(self.world.zone_of(vessel).kind, ZONE_BATTLEFIELD)

    def test_a_deck_out_loses_at_the_draw_step_not_after_the_last_draw(self):
        self.synth("Last Card", 1, 1, self.p1, ZONE_LIBRARY)
        stock_libraries(self.world, seats=[self.p0])
        game = self.game()
        policy = ScriptedPolicy()
        _play(game, policy, self.world.player_order, turn_cap=10)
        # p1 drew its last card on turn 2 and played on; it loses on turn 4,
        # at the check after its draw step, before any act of that turn.
        self.assertEqual(policy.windows, [(1, self.p0), (2, self.p1), (3, self.p0)])
        self.assertEqual(game.turns, 4)
        self.assertEqual(
            game.reason, "game over: player:1(draw from empty library (CR 704.5b))"
        )
