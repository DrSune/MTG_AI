"""H4 Scope C: partition designation journal pins.

ONE_OF and REST choices are not CR target designations, but branch coverage
still needs observable evidence for their chosen-set cardinality. These tests
pin the narrow Scope C contract:

1. real partition applications emit audit TARGETING rows with the selector
   mode as the cause verb;
2. query-like selector resolution leaves the journal clean;
3. the audit rows do not fire TargetingEvent triggers.
"""

from __future__ import annotations

import unittest

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    FAnd,
    QConst,
    Selector,
    SelectorMode,
    TargetingEvent,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
    ZonePosition,
)
from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.events import KIND_TARGETING
from MTG_bot.core.executor.legality import ctx_for
from MTG_bot.core.executor.selectors import resolve_selector
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import (
    ZONE_BATTLEFIELD,
    ZONE_LIBRARY,
    GameWorld,
)
from MTG_bot.core.test_executor_binding import card_id, record_of, reset_oracle_ids

UNIV = FAnd(())


def atom(verb, **roles) -> Atom:
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


class H4PartitionJournalTest(unittest.TestCase):
    def setUp(self) -> None:
        reset_oracle_ids()
        self.world = GameWorld(num_players=2, start_life=20, master_seed=4)
        self.p0, self.p1 = self.world.player_order[0], self.world.player_order[1]
        self.ex = Executor(self.world)
        self.source = self._card("Partition Source", zone=ZONE_BATTLEFIELD)

    def _card(
        self,
        name: str,
        *,
        p: str = "1",
        t: str = "1",
        type_line: str = "Creature",
        zone: str = ZONE_BATTLEFIELD,
    ):
        ident = CardIdentity(
            oracle_id=card_id(name).oracle_id,
            name=name,
            type_line=type_line,
            power=p,
            toughness=t,
            cmc=1,
        )
        return self.world.add_card(ident, self.p0, zone)

    def _targeting_rows(self):
        return [row for row in self.ex.journal.events if row.kind == KIND_TARGETING]

    def _lib_top_zone(self) -> Zone:
        return Zone(ZoneKind.LIBRARY, ControllerRef.YOU, ZonePosition.TOP)

    def _one_of_top(self) -> Selector:
        return Selector(QConst(1), SelectorMode.ONE_OF, UNIV, zones=(self._lib_top_zone(),))

    def _rest_top(self) -> Selector:
        return Selector(QConst(1), SelectorMode.REST, UNIV, zones=(self._lib_top_zone(),))

    def test_one_of_partition_emits_mode_verb_audit_row(self) -> None:
        top = self._card("Top Card", zone=ZONE_LIBRARY)
        self.ex.apply_effect(
            atom(
                Verb.MOVE_ZONE,
                cards=self._one_of_top(),
                destination=Zone(ZoneKind.HAND, ControllerRef.YOU),
            ),
            source=self.source,
            controller=self.p0,
        )

        rows = self._targeting_rows()
        self.assertEqual(
            [(row.subject, row.cause, row.cause_verb) for row in rows],
            [(top, self.source, "ONE_OF")],
        )

    def test_rest_partition_emits_complement_mode_rows(self) -> None:
        cards = [self._card(f"Top {i}", zone=ZONE_LIBRARY) for i in range(4)]
        ctx = ctx_for(self.ex, source=self.source, controller=self.p0)
        ctx.look_window = tuple(sorted(cards))
        ctx.decisions = (str(cards[1]),)

        chosen = resolve_selector(self._one_of_top(), ctx, journal_partition=True)
        rest = resolve_selector(self._rest_top(), ctx, journal_partition=True)

        self.assertEqual(chosen, [cards[1]])
        self.assertEqual(rest, sorted(set(cards) - {cards[1]}))

        rows = self._targeting_rows()
        self.assertEqual(
            [row.cause_verb for row in rows], ["ONE_OF", "REST", "REST", "REST"]
        )

    def test_query_lane_partition_resolution_does_not_journal(self) -> None:
        cards = [self._card(f"Top {i}", zone=ZONE_LIBRARY) for i in range(3)]
        ctx = ctx_for(self.ex, source=self.source, controller=self.p0)
        ctx.look_window = tuple(sorted(cards))
        ctx.decisions = (str(cards[0]),)

        chosen = resolve_selector(self._one_of_top(), ctx)

        self.assertEqual(chosen, [cards[0]])
        self.assertEqual(self._targeting_rows(), [])

    def test_partition_audit_row_does_not_fire_targeting_trigger(self) -> None:
        watcher = self._card("Warden Clone")
        self.ex.attach_card(
            watcher,
            record_of(
                [
                    TriggeredAbility(
                        event=TargetingEvent(filter=UNIV),
                        condition=None,
                        effect=atom(
                            Verb.TAP,
                            target=Selector(
                                QConst(1),
                                SelectorMode.CHOOSE,
                                UNIV,
                                zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
                                referent="source",
                            ),
                        ),
                    )
                ],
                name="Warden Clone",
                oid=self.world.cards[watcher].identity.oracle_id,
            ),
        )
        self._card("Top Card", zone=ZONE_LIBRARY)

        self.ex.apply_effect(
            atom(
                Verb.MOVE_ZONE,
                cards=self._one_of_top(),
                destination=Zone(ZoneKind.HAND, ControllerRef.YOU),
            ),
            source=self.source,
            controller=self.p0,
        )

        self.assertTrue(self._targeting_rows())
        self.assertFalse(self.world.cards[watcher].tapped)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
