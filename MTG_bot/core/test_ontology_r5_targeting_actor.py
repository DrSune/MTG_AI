"""Ontology R5-6 (2026-10-29): ``TargetingEvent.actor``, a Filter over the controller of the
targeting spell or ability ("becomes the target of a spell or ability an opponent controls").

Warden of the Woods must not trigger on its controller's own spells; it must on an opponent's. The
actor is the single direction encoding (E1) CastSpellEvent, CardDrawnEvent, LifeGainedEvent and
LoyaltyActivatedEvent use, and a TargetingEvent without it keeps its bytes.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    ControllerRef,
    FAtom,
    FAtomPred,
    OptionalEffect,
    QConst,
    TargetingEvent,
    TriggeredAbility,
    Verb,
    canonical_json,
    from_dict,
    to_dict,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND, GameWorld
from MTG_bot.core.test_executor_binding import atom, card_id, record_of

_OPPONENT = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT)


class TargetingEventActorNodeTest(unittest.TestCase):
    def test_actor_is_an_optional_filter(self) -> None:
        self.assertIsNone(TargetingEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)).actor)
        with self.assertRaisesRegex(ValueError, "actor must be a Filter"):
            TargetingEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE), actor=ControllerRef.OPPONENT)  # type: ignore[arg-type]

    def test_absent_actor_keeps_the_bytes_and_present_actor_round_trips(self) -> None:
        bare = TargetingEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE))
        self.assertNotIn("actor", to_dict(bare))
        self.assertNotIn('"actor"', canonical_json(bare))
        scoped = TargetingEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE), actor=_OPPONENT)
        self.assertEqual(from_dict("TargetingEvent", to_dict(scoped)), scoped)


class TargetingActorMatchTest(unittest.TestCase):
    """The binder reads the actor off the TARGETING row (data = (source object, actor))."""

    def setUp(self) -> None:
        self.world = GameWorld(num_players=2, start_life=20, master_seed=3)
        self.ex = Executor(self.world)
        self.p0, self.p1 = self.world.player_order
        self.ex.begin_turn(self.p0)
        self.warden = self.world.add_card(card_id("Warden", "5", "7"), self.p0, ZONE_BATTLEFIELD)
        self.ex.attach_card(
            self.warden,
            record_of(
                [
                    TriggeredAbility(
                        event=TargetingEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE), actor=_OPPONENT),
                        condition=None,
                        effect=OptionalEffect(
                            inner=atom(Verb.DRAW, amount=QConst(2), controller=ControllerRef.YOU)
                        ),
                    )
                ],
                name="Warden",
                oid=self.world.cards[self.warden].identity.oracle_id,
            ),
        )
        self.spell0 = self.world.add_card(card_id("Mine", type_line="Instant"), self.p0, ZONE_HAND)
        self.spell1 = self.world.add_card(card_id("Theirs", type_line="Instant"), self.p1, ZONE_HAND)

    def _queued_after(self, spell, actor) -> int:
        before = len(self.world.triggers)
        self.ex.journal.emit_targeting(spell, actor, [self.warden])
        self.ex.binder.on_events()
        return len(self.world.triggers) - before

    def test_an_opponents_spell_triggers_it(self) -> None:
        self.assertEqual(self._queued_after(self.spell1, self.p1), 1)

    def test_its_controllers_own_spell_does_not(self) -> None:
        self.assertEqual(self._queued_after(self.spell0, self.p0), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
