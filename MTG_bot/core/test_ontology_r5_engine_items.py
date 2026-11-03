"""Ontology R5 engine items on existing components (docs/DESIGN_ATOM_ONTOLOGY.md
§10, gate round 3 GO): "choose one or more" is ``Choose(count=QAtLeast(1))``,
and a cast ordinal counts only the casts its trigger describes (Double
Vision's "your first instant or sorcery spell each turn").
"""

from __future__ import annotations

from pathlib import Path

from MTG_bot.core.ability_tree import (
    CastSpellEvent,
    Choose,
    ControllerRef,
    FAtom,
    FAtomPred,
    QAtLeast,
    SpellKind,
    TriggeredAbility,
    Verb,
    walk,
)
from MTG_bot.core.compiler.compiler import compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.executor.query import choose_options
from MTG_bot.core.executor.stack import cast
from MTG_bot.core.state import ZONE_BATTLEFIELD
from MTG_bot.core.test_executor_binding import gain
from MTG_bot.core.test_executor_stack import INSTANT_OR_SORCERY, StackCase, atom

_M21 = Path(__file__).resolve().parents[1] / "data" / "M21.json"


def test_choose_one_or_more_is_at_least_one() -> None:
    raw = ingest_pool(_M21)
    (oid,) = [o for o, r in raw.items() if r.identity.name == "Sublime Epiphany"]
    card = compile_pool({oid: raw[oid]}, build_full_registry()).results[oid].card
    (choose,) = [n for n in walk(card) if isinstance(n, Choose)]
    assert choose.count == QAtLeast(1)
    assert len(choose.options) == 5


class TestChooseOneOrMoreSets(StackCase):
    def test_the_empty_set_is_not_a_choice(self) -> None:
        # CR 700.2: "choose one or more" names at least one mode, each at most
        # once (700.2d); QUnbounded also offered the empty set.
        two = Choose(count=QAtLeast(1), options=(gain(1), gain(2)))
        sets = [o.option_idxs for o in choose_options(self.ex, two, source=self.p0, controller=self.p0)]
        self.assertEqual(sets, [(0,), (1,), (0, 1)])


class TestFirstInstantOrSorceryOrdinal(StackCase):
    """Double Vision's event with a life-gain payload (its COPY has no
    executor handler, so the trigger itself is what is pinned)."""

    def setUp(self) -> None:
        super().setUp()
        self.mana(self.p0, R=9)

    def watcher(self) -> object:
        trigger = TriggeredAbility(
            event=CastSpellEvent(
                filter=INSTANT_OR_SORCERY,
                actor=FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                ordinal=1,
            ),
            condition=None,
            effect=gain(1),
        )
        return self.give(
            "Vision Watcher",
            SpellKind.ENCHANTMENT,
            zone=ZONE_BATTLEFIELD,
            type_line="Enchantment",
            types=("Enchantment",),
            extra_abilities=(trigger,),
        )

    def instant(self, name: str):
        from MTG_bot.core.ability_tree import Cost, CostManaColor, QConst

        return self.give(
            name,
            SpellKind.INSTANT,
            cost=Cost((CostManaColor("R", QConst(1)),)),
            effect=atom(Verb.GAIN_LIFE, controller=ControllerRef.OPPONENT, amount=QConst(1)),
        )

    def creature(self, name: str):
        from MTG_bot.core.ability_tree import Cost, CostManaColor, QConst

        return self.give(
            name,
            SpellKind.CREATURE,
            cost=Cost((CostManaColor("R", QConst(1)),)),
            type_line="Creature — Bear",
            types=("Creature",),
            power="2",
            toughness="2",
        )

    def life(self) -> int:
        return self.world.players[self.p0].life

    def test_a_creature_first_does_not_use_up_the_first_instant(self) -> None:
        self.watcher()
        cast(self.ex, self.p0, self.creature("Bear"))
        self.assertEqual(self.life(), 20)
        cast(self.ex, self.p0, self.instant("Spark"))  # the first instant: trigger
        self.assertEqual(self.life(), 21)
        cast(self.ex, self.p0, self.instant("Spark Two"))  # the second: no trigger
        self.assertEqual(self.life(), 21)

    def test_an_instant_cast_before_the_watcher_arrived_counts(self) -> None:
        cast(self.ex, self.p0, self.instant("Early Spark"))
        self.watcher()
        cast(self.ex, self.p0, self.instant("Late Spark"))  # second this turn
        self.assertEqual(self.life(), 20)

    def test_the_count_is_per_caster_and_per_turn(self) -> None:
        self.watcher()
        cast(self.ex, self.p0, self.instant("Spark"))
        self.assertEqual(self.life(), 21)
        self.ex.end_turn()
        self.ex.begin_turn(self.p1)
        self.ex.end_turn()
        self.ex.begin_turn(self.p0)
        self.mana(self.p0, R=1)
        cast(self.ex, self.p0, self.instant("Next Turn Spark"))  # first of the new turn
        self.assertEqual(self.life(), 22)
