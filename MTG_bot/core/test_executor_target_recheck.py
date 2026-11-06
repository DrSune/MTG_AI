"""CR 608.2b: as a spell or ability resolves, its targets are checked again.

"If all its targets, for every instance of the word 'target,' are now illegal, the spell or
ability doesn't resolve. It's removed from the stack and, if it's a spell, put into its owner's
graveyard. Otherwise, the spell or ability will resolve normally. Illegal targets, if any, won't
be affected by parts of a resolving spell's effect for which they're illegal."

A spell whose only target is gone does not resolve (it draws no card); a spell with one illegal
and one legal target affects only the legal one. The ability side (Heartfire Immolator sacrificed
to its own ability while targeting itself) is the scenario
tools/scenarios/heartfire_immolator_self_target_does_not_resolve.json.
"""

from __future__ import annotations

from MTG_bot.core.ability_tree import (
    CastSpellEvent,
    ControllerRef,
    Cost,
    CostManaColor,
    DurationEot,
    FAtom,
    FAtomPred,
    PtDelta,
    PtDirection,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    SpellKind,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_GRAVEYARD, ZONE_HAND
from MTG_bot.core.test_executor_binding import card_id, record_of
from MTG_bot.core.test_executor_stack import StackCase
from MTG_bot.core.test_executor_verbs import atom

CREATURE = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")
BF = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)


def target_creatures(n: int) -> Selector:
    return Selector(QConst(n), SelectorMode.TARGET, CREATURE, zones=(BF,))


def named(name: str) -> Selector:
    return Selector(
        QConst(1), SelectorMode.CHOOSE, FAtom(FAtomPred.NAME_EQ, string_value=name), zones=(BF,)
    )


class TestSpellTargetRecheck(StackCase):
    def setUp(self):
        super().setUp()
        self.bear = self.world.add_card(card_id("Bear", "2", "2"), self.p0, ZONE_BATTLEFIELD)
        self.ogre = self.world.add_card(card_id("Ogre", "3", "3"), self.p1, ZONE_BATTLEFIELD)

    def destroy_bear_on_cast(self) -> None:
        """A permanent of p0's whose cast trigger destroys the Bear: it resolves above the
        spell (CR 601.2i, 603.3), so the Bear is gone before the spell resolves."""
        trig = TriggeredAbility(
            event=CastSpellEvent(
                FAtom(FAtomPred.TYPE_EQ, string_value="Instant"),
                actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            ),
            condition=None,
            effect=atom(Verb.DESTROY, target=named("Bear")),
        )
        watcher = self.world.add_card(card_id("Watcher", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        self.ex.attach_card(
            watcher, record_of([trig], oid=self.world.cards[watcher].identity.oracle_id)
        )

    def test_a_spell_whose_only_target_is_gone_does_not_resolve(self):
        # Defiant Strike's shape: "Target creature gets +1/+0 until end of turn. Draw a card."
        strike = self.give(
            "Strike",
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("W", QConst(1)),)),
            effect=Seq(
                steps=(
                    atom(
                        Verb.MODIFY_PT,
                        target=target_creatures(1),
                        power=PtDelta(PtDirection.INCREASE, QConst(1)),
                        duration=DurationEot(),
                    ),
                    atom(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1)),
                )
            ),
        )
        self.destroy_bear_on_cast()
        self.mana(self.p0, W=1)
        hand = len(self.world.players[self.p0].zone(ZONE_HAND).entries)
        cast(self.ex, self.p0, strike, targets=(self.bear,))
        self.assertEqual(self.world.zone_of(self.bear).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.world.zone_of(strike).kind, ZONE_GRAVEYARD)
        # The spell left the hand and drew nothing.
        self.assertEqual(len(self.world.players[self.p0].zone(ZONE_HAND).entries), hand - 1)

    def test_an_illegal_target_is_not_affected_and_the_legal_one_is(self):
        burn = self.give(
            "Twin Bolt",
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("R", QConst(1)),)),
            effect=atom(Verb.DEAL_DAMAGE, target=target_creatures(2), amount=QConst(1)),
        )
        self.destroy_bear_on_cast()
        self.mana(self.p0, R=1)
        cast(self.ex, self.p0, burn, targets=tuple(sorted((self.bear, self.ogre))))
        self.assertEqual(self.world.zone_of(self.bear).kind, ZONE_GRAVEYARD)
        self.assertEqual(self.ex.damage, {self.ogre: 1})
