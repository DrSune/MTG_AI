"""Ontology R5-1 (2026-10-29): MOVE_ZONE's ``duration`` role and the executor's return registry.

CR 610.3: a one-shot effect that moves an object "until" an event creates a second one-shot effect
immediately after that event, which returns the object to its previous zone. 610.3a/b: if the event
already happened after the ability triggered or the spell was cast, the object doesn't move.
610.3c: onto the battlefield under its owner's control. 610.3d: returns caused by simultaneous
events are simultaneous. CR 400.7: an object that left that zone meanwhile is a new object.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    DurationEot,
    DurationPermanent,
    DurationUntilLeaves,
    DurationUntilNextStep,
    DurationUntilNextTurn,
    DurationWhileCondition,
    FAnd,
    FAtom,
    FAtomPred,
    QConst,
    Selector,
    SelectorMode,
    Step,
    TokenSpec,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.events import KIND_ZONE_CHANGE, GameEvent
from MTG_bot.core.executor.games import get_supply, identity_of
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_HAND,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import card_id

_ANY = Selector(QConst(1), SelectorMode.TARGET, FAnd(()), zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),))


def _move(destination: ZoneKind, duration=None, role: str = "cards") -> Atom:
    pairs: list[tuple[str, object]] = [(role, _ANY), ("destination", Zone(destination, ControllerRef.OWNER))]
    if duration is not None:
        pairs.append(("duration", duration))
    return Atom(verb=Verb.MOVE_ZONE, args=AtomArgs(pairs=tuple(pairs)))


class MoveZoneDurationConstructionTest(unittest.TestCase):
    def test_the_three_event_ending_durations_construct(self) -> None:
        for duration in (DurationUntilLeaves(), DurationEot(), DurationUntilNextTurn()):
            atom = _move(ZoneKind.EXILE, duration)
            self.assertEqual(atom.args.get("duration"), duration)

    def test_every_other_duration_is_refused(self) -> None:
        for duration in (
            DurationPermanent(),  # the same as leaving the role out
            DurationWhileCondition(filter=FAtom(pred=FAtomPred.IS_SOURCE)),  # could start again
            DurationUntilNextStep(step=Step.UNTAP),
        ):
            with self.assertRaisesRegex(ValueError, "MOVE_ZONE duration must be one of"):
                _move(ZoneKind.EXILE, duration)

    def test_a_tree_without_the_role_keeps_its_bytes(self) -> None:
        from MTG_bot.core.ability_tree import canonical_json

        self.assertNotIn("duration", canonical_json(_move(ZoneKind.EXILE)))


class ReturnRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.world = GameWorld(num_players=2, start_life=20, master_seed=5)
        self.ex = Executor(self.world)
        self.p0, self.p1 = self.world.player_order
        self.ex.begin_turn(self.p0)
        self.anchor = self.world.add_card(card_id("Anchor", "1", "1"), self.p0, ZONE_BATTLEFIELD)

    def _exile_until(self, card: Handle, duration=None, *, role: str = "cards", source=None) -> None:
        self.ex.execute(
            _move(ZoneKind.EXILE, duration or DurationUntilLeaves(), role),
            source=source or self.anchor,
            controller=self.p0,
            bindings={role: card},
        )

    def _leave(self, card: Handle, to: ZoneKind = ZoneKind.GRAVEYARD) -> None:
        self.ex.execute(_move(to), source=card, controller=self.p0, bindings={"cards": card})

    def test_until_leaves_round_trip_to_the_owners_hand(self) -> None:
        zap = self.world.add_card(card_id("Zap", type_line="Instant"), self.p1, ZONE_HAND)
        self._exile_until(zap, role="target")
        self.assertEqual(self.world.zone_of(zap).kind, ZONE_EXILE)
        (row,) = self.ex.returns.rows
        self.assertEqual((row.card, row.previous_zone, row.owner, row.anchor), (zap, ZONE_HAND, self.p1, self.anchor))
        self._leave(self.anchor)
        self.assertEqual(self.world.zone_of(zap).kind, ZONE_HAND)
        self.assertEqual(self.world.zone_of(zap).controller, self.p1)
        self.assertEqual(self.ex.returns.rows, [])

    def test_the_registry_is_folded_into_the_fingerprint(self) -> None:
        zap = self.world.add_card(card_id("Zap", type_line="Instant"), self.p1, ZONE_HAND)
        self._exile_until(zap)
        with_row = self.ex.state_fingerprint()
        rows, self.ex.returns.rows = self.ex.returns.rows, []
        try:
            self.assertNotEqual(with_row, self.ex.state_fingerprint())
        finally:
            self.ex.returns.rows = rows

    def test_a_card_that_left_exile_and_came_back_is_a_new_object(self) -> None:
        # CR 400.7: Handles survive zone moves, the object does not.
        zap = self.world.add_card(card_id("Zap", type_line="Instant"), self.p1, ZONE_HAND)
        salve = self.world.add_card(card_id("Salve", type_line="Sorcery"), self.p1, ZONE_HAND)
        self._exile_until(zap)
        self._exile_until(salve)
        self._leave(zap, ZoneKind.HAND)
        self._leave(zap, ZoneKind.EXILE)
        self._leave(self.anchor)
        self.assertEqual(self.world.zone_of(zap).kind, ZONE_EXILE)
        self.assertEqual(self.world.zone_of(salve).kind, ZONE_HAND)

    def test_a_returning_permanent_comes_back_under_its_owner(self) -> None:
        # CR 610.3c: the opponent's creature, stolen by seat 0, returns under seat 1.
        ogre = self.world.add_card(card_id("Ogre", "3", "3"), self.p1, ZONE_BATTLEFIELD)
        self.ex.gain_control(ogre, self.p0, "Permanent", None)
        self.assertEqual(self.ex.controller_of(ogre), self.p0)
        self._exile_until(ogre, role="target")
        self._leave(self.anchor)
        self.assertEqual(self.world.zone_of(ogre).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.ex.controller_of(ogre), self.p1)

    def test_a_token_does_not_return(self) -> None:
        # CR 704.5d: a token that left the battlefield has ceased to exist.
        spec = TokenSpec(
            name="Soldier", type_line="Creature — Soldier", types=("Creature",), subtypes=("Soldier",),
            power=QConst(1), toughness=QConst(1), keywords=(), abilities=(),
        )
        make = Atom(verb=Verb.CREATE_TOKEN, args=AtomArgs(pairs=(("tokens", spec), ("count", QConst(1)))))
        before = set(self.world.cards)
        self.ex.execute(make, source=self.anchor, controller=self.p1)
        (token,) = set(self.world.cards) - before
        self._exile_until(token, role="target")
        self._leave(self.anchor)
        self.assertFalse(
            token in self.world.cards and self.world.zone_of(token).kind == ZONE_BATTLEFIELD
        )

    def test_simultaneous_departures_return_in_one_batch(self) -> None:
        # CR 610.3d: two anchors leave in one event; both objects return in one move.
        other = self.world.add_card(card_id("Other", "1", "1"), self.p0, ZONE_BATTLEFIELD)
        ogre = self.world.add_card(card_id("Ogre", "3", "3"), self.p1, ZONE_BATTLEFIELD)
        bear = self.world.add_card(card_id("Bear", "2", "2"), self.p1, ZONE_BATTLEFIELD)
        self._exile_until(ogre, role="target")
        self._exile_until(bear, role="target", source=other)
        boundaries: list[list[GameEvent]] = []
        real = self.ex.journal.record_atom

        def spy(*args, **kwargs):
            out = real(*args, **kwargs)
            boundaries.append(list(out))
            return out

        self.ex.journal.record_atom = spy  # type: ignore[method-assign]
        both = Atom(
            verb=Verb.MOVE_ZONE,
            args=AtomArgs(
                pairs=(
                    ("cards", Selector(QConst(2), SelectorMode.TARGET, FAnd(()), zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),))),
                    ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.OWNER)),
                )
            ),
        )
        self.ex.execute(both, source=self.anchor, controller=self.p0, bindings={"cards": [self.anchor, other]})
        returns = [
            b for b in boundaries
            if any(e.kind == KIND_ZONE_CHANGE and e.subject in (ogre, bear) for e in b)
        ]
        self.assertEqual(len(returns), 1)
        moved = {e.subject for e in returns[0] if e.kind == KIND_ZONE_CHANGE}
        self.assertEqual(moved, {ogre, bear})
        self.assertEqual(self.world.zone_of(ogre).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.world.zone_of(bear).kind, ZONE_BATTLEFIELD)

    def test_the_anchor_left_after_the_trigger_so_nothing_moves(self) -> None:
        # CR 610.3b: the trigger's event clock is when it triggered; the anchor left after it.
        zap = self.world.add_card(card_id("Zap", type_line="Instant"), self.p1, ZONE_HAND)
        triggered = self.ex.journal.events[-1]
        self._leave(self.anchor, ZoneKind.HAND)
        self.ex.execute(_move(ZoneKind.BATTLEFIELD), source=self.anchor, controller=self.p0, bindings={"cards": self.anchor})
        ctx = self.ex._ctx(source=self.anchor, controller=self.p0, bindings={"target": zap}, decisions=())
        ctx.event = triggered
        self.ex._run_effect(_move(ZoneKind.EXILE, DurationUntilLeaves(), role="target"), ctx)
        self.assertEqual(self.world.zone_of(zap).kind, ZONE_HAND)
        self.assertEqual(self.ex.returns.rows, [])
        self.assertIn("MOVE_UNTIL_ENDED", [e[1] for e in self.ex.events])

    def test_phasing_out_does_not_end_it(self) -> None:
        # CR 702.26d: phasing is not leaving the battlefield.
        zap = self.world.add_card(card_id("Zap", type_line="Instant"), self.p1, ZONE_HAND)
        self._exile_until(zap)
        self.ex.phase_out([self.anchor])
        self.assertEqual(self.world.zone_of(zap).kind, ZONE_EXILE)
        self.assertEqual(len(self.ex.returns.rows), 1)

    def test_until_end_of_turn_returns_in_the_cleanup_step(self) -> None:
        ogre = self.world.add_card(card_id("Ogre", "3", "3"), self.p1, ZONE_BATTLEFIELD)
        self._exile_until(ogre, DurationEot(), role="target")
        self.assertEqual(self.world.zone_of(ogre).kind, ZONE_EXILE)
        self.ex.end_turn()
        self.assertEqual(self.world.zone_of(ogre).kind, ZONE_BATTLEFIELD)
        self.assertEqual(self.world.zone_of(ogre).controller, self.p1)

    def test_until_your_next_turn_returns_as_that_turn_begins(self) -> None:
        ogre = self.world.add_card(card_id("Ogre", "3", "3"), self.p1, ZONE_BATTLEFIELD)
        self._exile_until(ogre, DurationUntilNextTurn(), role="target")
        self.ex.advance_turn()  # seat 1's turn: not yet
        self.assertEqual(self.world.zone_of(ogre).kind, ZONE_EXILE)
        self.ex.advance_turn()  # seat 0's next turn
        self.assertEqual(self.world.zone_of(ogre).kind, ZONE_BATTLEFIELD)

    def test_a_phased_out_permanent_is_not_a_host_for_an_entering_aura(self) -> None:
        # CR 702.26b + 303.4f: the V32 host menu leaves out what is treated as nonexistent.
        from MTG_bot.core.executor.aura_entry import aura_entry_hosts

        aura = self.world.add_card(
            card_id("Shackle", type_line="Enchantment — Aura"), self.p1, ZONE_EXILE
        )
        gone = self.world.add_card(card_id("Gone", "2", "2"), self.p1, ZONE_BATTLEFIELD)
        self.ex.phase_out([gone])
        self.assertEqual(aura_entry_hosts(self.ex, aura, self.p1), [self.anchor])

    def test_a_move_out_of_a_library_is_refused(self) -> None:
        top = self.world.add_card(card_id("Top", "1", "1"), self.p0, ZONE_LIBRARY)
        with self.assertRaisesRegex(NotImplementedError, "no position rule"):
            self._exile_until(top)

    def test_the_seat_view_shows_where_and_when_it_returns(self) -> None:
        from MTG_bot.bench.view import OracleIndex, SeatLens, render_view

        zap = self.world.add_card(card_id("Zap", type_line="Instant"), self.p1, ZONE_HAND)
        self._exile_until(zap)
        lens = SeatLens(0, OracleIndex.for_sets("M21"))
        view = lens.view(self.ex)
        (card,) = view.players[1].exile
        self.assertEqual(card.returns_to, ZONE_HAND)
        anchor_oid = lens.oid(self.anchor)
        self.assertEqual(card.returns_when, f"{anchor_oid} Anchor (1/1) leaves the battlefield")
        self.assertIn(f"returns to its owner's hand when {anchor_oid} Anchor (1/1) leaves the battlefield", render_view(view))


class ReturnThroughReplacementsTest(unittest.TestCase):
    """CR 614: the return is an ordinary zone change, so replacement effects apply to it."""

    def test_containment_priest_exiles_a_returning_creature(self) -> None:
        cage_supply = get_supply("all", "M19")
        priest_supply = get_supply("all", "M21")

        def record(supply, name):
            return next(supply.pool.results[o].card for o, m in supply.metas.items() if m.name == name)

        world = GameWorld(num_players=2, start_life=20, master_seed=9)
        ex = Executor(world)
        p0, p1 = world.player_order
        cage = world.add_card(identity_of(record(cage_supply, "Hieromancer's Cage")), p0, ZONE_HAND)
        priest = world.add_card(identity_of(record(priest_supply, "Containment Priest")), p0, ZONE_BATTLEFIELD)
        ogre = world.add_card(card_id("Ogre", "3", "3"), p1, ZONE_BATTLEFIELD)
        ex.attach_pool(cage_supply.pool)
        ex.attach_pool(priest_supply.pool)
        ex.begin_turn(p0)
        ex.execute(_move(ZoneKind.BATTLEFIELD), source=cage, controller=p0, bindings={"cards": cage})
        self.assertEqual(world.zone_of(ogre).kind, ZONE_EXILE)  # the Cage's enters trigger
        ex.execute(_move(ZoneKind.GRAVEYARD), source=cage, controller=p0, bindings={"cards": cage})
        # The Ogre would return to the battlefield; it was not cast, so the Priest exiles it.
        self.assertEqual(world.zone_of(ogre).kind, ZONE_EXILE)
        self.assertIn(("ZONE_REPLACED", str(ogre), str(priest)), [e[1:4] for e in ex.events])
        self.assertEqual(ex.returns.rows, [])
        self.assertEqual(world.zone_of(cage).kind, ZONE_GRAVEYARD)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
