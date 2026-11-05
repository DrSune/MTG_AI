"""Turn history (2026-11-05): "what happened this turn" as one mechanism.

``FAtomPred.EVENT_THIS_TURN`` asks whether an event happened this turn, ``count`` or more;
``SUBJECT_OF_EVENT_THIS_TURN`` whether the judged object was that event's subject. The event is an
EventSpec, matched against the turn's journal rows by the trigger binder's own matcher, so the
trigger vocabulary and the history vocabulary are one. ``LifeLostEvent`` joins the events (CR
120.3a: damage to a player is life lost; CR 119.4: so is paying life).

Cards that needed this (needs-atom records): Savage Gorger and Stromkirk Bloodthief ("if an
opponent lost life this turn"), Knight of the Ebon Legion ("a player lost 4 or more life"),
Nightpack Ambusher ("if you didn't cast a spell"), Veil of Summer ("an opponent has cast a blue or
black spell"), Ogre Siegebreaker and Fathom Fleet Cutthroat ("creature that was dealt damage this
turn"), and raid ("if you attacked this turn").
"""

from __future__ import annotations

import unittest

import pytest

import MTG_bot.core.ability_tree as at
from MTG_bot.core.ability_tree import (
    AbilityTriggerEvent,
    CastSpellEvent,
    ControllerRef,
    Cost,
    CostManaColor,
    CounteredEvent,
    CounterKind,
    DamageDealtEvent,
    DeclareAttackersEvent,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    LifeLostEvent,
    Phase,
    QConst,
    QProp,
    QPropField,
    QUnbounded,
    Selector,
    SelectorMode,
    SpellKind,
    Step,
    StepEvent,
    TriggeredAbility,
    TurnPhaseEvent,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.quantity import ExecCtx, eval_filter
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND, GameWorld
from MTG_bot.core.test_executor_binding import (
    UNIV,
    atom,
    card_id,
    reset_oracle_ids,
)
from MTG_bot.core.test_executor_stack import spell_rec
from MTG_bot.core.test_executor_verbs import stock_libraries

YOU = FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
OPPONENT = FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT)
ONE = QConst(1)


def happened(event, count=1) -> FAtom:
    return FAtom(FAtomPred.EVENT_THIS_TURN, event=event, count=QConst(count))


def subject_of(event, count=1) -> FAtom:
    return FAtom(FAtomPred.SUBJECT_OF_EVENT_THIS_TURN, event=event, count=QConst(count))


def any_target() -> Selector:
    return Selector(
        QConst(1), SelectorMode.TARGET, UNIV, zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),)
    )


DEALT_DAMAGE = DamageDealtEvent(amount=QUnbounded(), filter=UNIV)
AN_OPPONENT_LOST_LIFE = happened(LifeLostEvent(actor=OPPONENT))
YOU_CAST_A_SPELL = happened(CastSpellEvent(filter=UNIV, actor=YOU))


# ---------------------------------------------------------------------------- IR


def test_rule_rows_take_event_and_count() -> None:
    for pred in (FAtomPred.EVENT_THIS_TURN, FAtomPred.SUBJECT_OF_EVENT_THIS_TURN):
        assert at._FATOM_RULES[pred] == (
            frozenset({"event", "count"}),
            frozenset({"event", "count"}),
        )


@pytest.mark.parametrize(
    ("slots", "message"),
    [
        ({"count": ONE}, "requires slot 'event'"),
        ({"event": LifeLostEvent()}, "requires slot 'count'"),
        ({"event": LifeLostEvent(), "count": QConst(0)}, "count >= 1"),
        ({"event": OPPONENT, "count": ONE}, "event must be an EventSpec"),
        (
            {"event": StepEvent(Phase.END_TURN, Step.UNTAP, ControllerRef.YOU), "count": ONE},
            "no journal history",
        ),
        ({"event": AbilityTriggerEvent(UNIV), "count": ONE}, "no journal history"),
        ({"event": CounteredEvent(UNIV), "count": ONE}, "no journal history"),
    ],
)
def test_history_atoms_validate(slots, message) -> None:
    with pytest.raises(ValueError, match=message):
        FAtom(FAtomPred.EVENT_THIS_TURN, **slots)


def test_other_preds_refuse_the_event_slot() -> None:
    with pytest.raises(ValueError, match="does not take slot 'event'"):
        FAtom(FAtomPred.IS_SOURCE, event=LifeLostEvent())


def test_round_trip_and_earlier_bytes_unchanged() -> None:
    nodes = [
        AN_OPPONENT_LOST_LIFE,
        subject_of(DEALT_DAMAGE),
        happened(LifeLostEvent(), count=4),
        CounteredEvent(filter=FAtom(FAtomPred.IS_SOURCE)),
    ]
    for node in nodes:
        assert at.from_dict(type(node).__name__, at.to_dict(node)) == node
    # the event slot and a None actor are omitted: an earlier FAtom keeps its bytes
    assert "event" not in at.to_dict(FAtom(FAtomPred.IS_SOURCE))
    assert at.to_dict(LifeLostEvent()) == {"tag": "LifeLostEvent"}


# ---------------------------------------------------------------------- executor


class HistoryCase(unittest.TestCase):
    """p0's turn is open; ``judge`` evaluates a filter in p0's coordinates."""

    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=7)
        self.p0, self.p1 = self.world.player_order
        stock_libraries(self.world)
        self.ex = Executor(self.world)
        self.ex.begin_turn(self.p0)
        self.source = self.world.add_card(card_id("Probe", "1", "1"), self.p0, ZONE_BATTLEFIELD)

    def ctx(self, controller=None) -> ExecCtx:
        return self.ex._ctx(
            source=self.source,
            controller=controller or self.p0,
            bindings={},
            decisions=(),
        )

    def judge(self, filter_, handle=None, controller=None) -> bool:
        return eval_filter(filter_, handle or self.source, self.ctx(controller))

    def lose_life(self, player, n) -> None:
        self.ex.execute(
            atom(Verb.LOSE_LIFE, controller=ControllerRef.YOU, amount=QConst(n)),
            source=self.source,
            controller=player,
        )

    def damage(self, target, n) -> None:
        self.ex.execute(
            atom(Verb.DEAL_DAMAGE, target=any_target(), amount=QConst(n)),
            source=self.source,
            controller=self.p0,
            bindings={"target": target},
        )

    def spell(self, name, seat, *, color="R", creature=False):
        """A one-mana spell card in ``seat``'s hand, its mana in the pool: an instant
        (you gain 1 life) or a 1/1 creature."""
        type_line = "Creature" if creature else "Instant"
        pt = "1" if creature else None
        rec = spell_rec(
            name,
            SpellKind.CREATURE if creature else SpellKind.INSTANT,
            cost=Cost((CostManaColor(color, ONE),)),
            effect=None
            if creature
            else atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=ONE),
            type_line=type_line,
            types=(type_line,),
            colors=(color,),
            power=pt,
            toughness=pt,
        )
        handle = self.world.add_card(
            card_id(name, pt, pt, type_line=type_line, oid=rec.oracle_id, colors=(color,)),
            seat,
            ZONE_HAND,
        )
        self.ex.attach_card(handle, rec)
        pool = self.world.players[seat].mana_pool
        pool[color] = pool.get(color, 0) + 1
        return handle


class TestLifeLost(HistoryCase):
    def test_damage_and_life_loss_are_both_life_lost(self) -> None:
        self.assertFalse(self.judge(AN_OPPONENT_LOST_LIFE))
        self.lose_life(self.p0, 2)  # you lost life: not an opponent
        self.assertFalse(self.judge(AN_OPPONENT_LOST_LIFE))
        self.damage(self.p1, 1)  # CR 120.3a: damage to a player is life lost
        self.assertTrue(self.judge(AN_OPPONENT_LOST_LIFE))
        # judged from the opponent's seat, "an opponent" is p0, who lost 2
        self.assertTrue(self.judge(AN_OPPONENT_LOST_LIFE, controller=self.p1))

    def test_paid_life_counts(self) -> None:
        self.lose_life(self.p1, 1)  # LOSE_LIFE is also how a life payment is made
        self.assertTrue(self.judge(AN_OPPONENT_LOST_LIFE))

    def test_a_threshold_is_met_by_one_player(self) -> None:
        a_player_lost_four = happened(LifeLostEvent(), count=4)
        self.lose_life(self.p0, 2)
        self.lose_life(self.p1, 2)
        self.assertFalse(self.judge(a_player_lost_four))  # 2 + 2 over two players
        self.damage(self.p1, 2)  # p1: 2 lost + 2 damage
        self.assertTrue(self.judge(a_player_lost_four))

    def test_damage_to_a_creature_is_not_life_lost(self) -> None:
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p1, ZONE_BATTLEFIELD)
        self.damage(bear, 1)
        self.assertFalse(self.judge(happened(LifeLostEvent())))

    def test_only_this_turn(self) -> None:
        self.damage(self.p1, 3)
        self.assertTrue(self.judge(AN_OPPONENT_LOST_LIFE))
        self.ex.begin_turn(self.p1)
        self.assertFalse(self.judge(AN_OPPONENT_LOST_LIFE))


class TestSpellsCast(HistoryCase):
    def test_a_spell_of_any_type(self) -> None:
        legacy = FAtom(FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN, who=ControllerRef.YOU)
        bear = self.spell("Bear", self.p0, color="G", creature=True)
        self.assertFalse(self.judge(YOU_CAST_A_SPELL))
        cast(self.ex, self.p0, bear)
        self.assertTrue(self.judge(YOU_CAST_A_SPELL))
        self.assertFalse(self.judge(legacy))  # the old pred reads instants and sorceries only
        self.assertFalse(self.judge(FNot(YOU_CAST_A_SPELL)))  # "if you didn't cast a spell"
        self.assertFalse(self.judge(YOU_CAST_A_SPELL, controller=self.p1))

    def test_a_spell_by_color_and_caster(self) -> None:
        blue_or_black = happened(
            CastSpellEvent(
                filter=FOr(
                    (
                        FAtom(FAtomPred.COLOR_HAS, color="U"),
                        FAtom(FAtomPred.COLOR_HAS, color="B"),
                    )
                ),
                actor=OPPONENT,
            )
        )
        self.ex.begin_turn(self.p1)
        red = self.spell("Spark", self.p1, color="R")
        cast(self.ex, self.p1, red)
        self.assertFalse(self.judge(blue_or_black))  # p0 asks: a red spell
        blue = self.spell("Ponder", self.p1, color="U")
        cast(self.ex, self.p1, blue)
        self.assertTrue(self.judge(blue_or_black))
        self.assertFalse(self.judge(blue_or_black, controller=self.p1))  # not p1's opponent


class TestDealtDamage(HistoryCase):
    def test_the_judged_object_was_dealt_damage(self) -> None:
        hit = self.world.add_card(card_id("Hit", "3", "3"), self.p1, ZONE_BATTLEFIELD)
        spared = self.world.add_card(card_id("Spared", "3", "3"), self.p1, ZONE_BATTLEFIELD)
        self.damage(hit, 1)
        was_dealt = FAnd((FAtom(FAtomPred.TYPE_EQ, string_value="Creature"), subject_of(DEALT_DAMAGE)))
        self.assertTrue(self.judge(was_dealt, hit))
        self.assertFalse(self.judge(was_dealt, spared))
        self.assertFalse(self.judge(subject_of(DEALT_DAMAGE, count=2), hit))
        self.damage(hit, 1)
        self.assertTrue(self.judge(subject_of(DEALT_DAMAGE, count=2), hit))  # amounts add
        # existential: some creature was dealt damage, whoever is judged
        self.assertTrue(self.judge(happened(DEALT_DAMAGE), spared))

    def test_a_new_object_has_no_history(self) -> None:
        hit = self.world.add_card(card_id("Hit", "3", "3"), self.p1, ZONE_HAND)
        self.ex.execute(
            atom(
                Verb.MOVE_ZONE,
                cards=Selector(ONE, SelectorMode.TARGET, UNIV, zones=(Zone(ZoneKind.HAND, ControllerRef.YOU),)),
                destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
            ),
            source=hit,
            controller=self.p1,
            bindings={"cards": hit},
        )
        self.damage(hit, 1)
        self.assertTrue(self.judge(subject_of(DEALT_DAMAGE), hit))
        for zone in (ZoneKind.HAND, ZoneKind.BATTLEFIELD):  # bounced, then back (CR 400.7)
            self.ex.execute(
                atom(
                    Verb.MOVE_ZONE,
                    cards=Selector(ONE, SelectorMode.TARGET, UNIV, zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),)),
                    destination=Zone(zone, ControllerRef.OWNER),
                ),
                source=hit,
                controller=self.p1,
                bindings={"cards": hit},
            )
        self.assertEqual(self.world.zone_of(hit).kind, ZONE_BATTLEFIELD)
        self.assertFalse(self.judge(subject_of(DEALT_DAMAGE), hit))

    def test_damage_to_a_player_is_a_damage_event(self) -> None:
        an_opponent_was_dealt_damage = happened(
            DamageDealtEvent(
                amount=QUnbounded(), filter=FAtom(FAtomPred.OPPONENT_OF, who=ControllerRef.YOU)
            )
        )
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p1, ZONE_BATTLEFIELD)
        self.damage(bear, 1)  # an opponent's creature, not an opponent
        self.assertFalse(self.judge(an_opponent_was_dealt_damage))
        self.damage(self.p1, 1)
        self.assertTrue(self.judge(an_opponent_was_dealt_damage))


class TestAttacked(HistoryCase):
    def test_raid_reads_the_declaration(self) -> None:
        # "you attacked this turn": only the active player attacks (CR 508.1), so it is "your
        # turn, and attackers were declared this turn"; the attack record itself is gone after
        # combat, and the creature may have left since.
        you_attacked = FAnd(
            (FAtom(FAtomPred.TURN_OF, who=ControllerRef.YOU), happened(DeclareAttackersEvent(UNIV)))
        )
        self.ex.advance_turn()
        self.ex.advance_turn()  # p0 again, and the Probe is no longer summoning sick

        def answer(vocab, what):
            for word in ("ATTACK", "NONE"):
                if word in vocab:
                    return word
            return vocab[0]

        self.ex.decisions.provider = answer
        self.assertFalse(self.judge(you_attacked))
        self.ex.combat_step(self.p0)
        self.assertEqual(self.ex.attackers, [])  # combat is over; the journal remembers
        self.assertTrue(self.judge(you_attacked))
        self.assertFalse(self.judge(you_attacked, controller=self.p1))
        self.ex.advance_turn()
        self.assertFalse(self.judge(you_attacked, controller=self.p1))  # p1's turn: no attack yet


class TestEveryEntryPoint(HistoryCase):
    def test_a_bare_ctx_flags_the_question(self) -> None:
        bare = ExecCtx(
            world=self.world,
            ledger=self.ex.ledger,
            controller=self.p0,
            source=self.source,
            bindings={},
            decisions=(),
        )
        with self.assertRaises(NotImplementedError) as cm:
            eval_filter(AN_OPPONENT_LOST_LIFE, self.source, bare)
        self.assertIn("EVENT_THIS_TURN", str(cm.exception))

    def test_an_intervening_if_end_step_trigger(self) -> None:
        # Savage Gorger's tree: "At the beginning of your end step, if an opponent lost life
        # this turn, put a +1/+1 counter on this creature." (CR 603.4)
        gorger_rec = spell_rec(
            "Gorger",
            SpellKind.CREATURE,
            type_line="Creature",
            types=("Creature",),
            power="1",
            toughness="1",
            extra_abilities=(
                TriggeredAbility(
                    event=TurnPhaseEvent(Phase.END_TURN, actor=YOU),
                    condition=AN_OPPONENT_LOST_LIFE,
                    effect=atom(
                        Verb.PUT_COUNTER,
                        target=Selector(
                            ONE,
                            SelectorMode.CHOOSE,
                            FAtom(FAtomPred.IS_SOURCE),
                            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
                        ),
                        counter_kind=CounterKind.PLUS_1_PLUS_1,
                        count=ONE,
                    ),
                ),
            ),
        )
        gorger = self.world.add_card(
            card_id("Gorger", "1", "1", oid=gorger_rec.oracle_id), self.p0, ZONE_BATTLEFIELD
        )
        self.ex.attach_card(gorger, gorger_rec)
        self.ex.end_turn()  # nobody lost life
        self.assertEqual(self.world.cards[gorger].counters, {})
        self.ex.begin_turn(self.p1)
        self.ex.end_turn()  # not p0's end step
        self.ex.begin_turn(self.p0)
        self.damage(self.p1, 1)
        self.ex.end_turn()
        self.assertEqual(self.world.cards[gorger].counters, {"PLUS_1_PLUS_1": 1})


class TestTriggerLane(HistoryCase):
    """The two new events are trigger events too: one matcher serves both lanes."""

    def _permanent_with(self, trigger) -> object:
        rec = spell_rec(
            "Watcher",
            SpellKind.CREATURE,
            type_line="Creature",
            types=("Creature",),
            power="1",
            toughness="1",
            extra_abilities=(trigger,),
        )
        handle = self.world.add_card(
            card_id("Watcher", "1", "1", oid=rec.oracle_id), self.p0, ZONE_BATTLEFIELD
        )
        self.ex.attach_card(handle, rec)
        return handle

    def hand(self, seat) -> int:
        return len(self.world.players[seat].zone(ZONE_HAND).entries)

    def test_whenever_you_lose_life_draw_that_many(self) -> None:
        # Vilis, Broker of Blood's "Whenever you lose life, draw that many cards."
        self._permanent_with(
            TriggeredAbility(
                event=LifeLostEvent(actor=YOU),
                condition=None,
                effect=atom(
                    Verb.DRAW,
                    controller=ControllerRef.YOU,
                    amount=QProp(referent="event", field=QPropField.AMOUNT),
                ),
            )
        )
        before = self.hand(self.p0)
        self.damage(self.p0, 2)
        self.ex.fire_triggers()
        self.assertEqual(self.hand(self.p0), before + 2)
        self.lose_life(self.p0, 1)
        self.ex.fire_triggers()
        self.assertEqual(self.hand(self.p0), before + 3)
        self.damage(self.p1, 4)  # an opponent's loss is not yours
        self.ex.fire_triggers()
        self.assertEqual(self.hand(self.p0), before + 3)

    def test_countered_is_a_prevention_event_only(self) -> None:
        # The countered spell has left the stack when the drain would match its COUNTER row,
        # so no "spell" filter could be judged: binding a trigger on it is refused loudly.
        with self.assertRaises(NotImplementedError) as cm:
            self._permanent_with(
                TriggeredAbility(
                    event=CounteredEvent(filter=FAtom(FAtomPred.STACK_KIND_EQ, string_value="SPELL")),
                    condition=None,
                    effect=atom(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QConst(3)),
                )
            )
        self.assertIn("CounteredEvent", str(cm.exception))
