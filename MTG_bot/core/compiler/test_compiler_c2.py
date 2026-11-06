"""Compiler pins: Fabled Passage's tapped search, and existential "if you control" conditions.

The Fabled Passage SEARCH atom carries the printed "onto the battlefield tapped" as
``tapped_on_enter=True``. "If you control a Basri planeswalker" and "if you control a creature
with power 4 or greater" are existence claims over the controlled population: CONTROLLER_COUNT_GE
count=1 with the per-card test inside the inner filter, never a bare filter judged against the
trigger source, and the printed 4 bound to the POWER filter, not the count.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    Atom,
    Conditional,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    QConst,
    Seq,
    TriggeredAbility,
    Verb,
)
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool

_M21_PATH = Path(__file__).resolve().parents[2] / "data" / "M21.json"

_FABLED = "0c85b8f7-0bd0-4680-9ec5-d4b110460a54"
_ADHERENT = "b5f5400e-f341-40e3-b935-36d9cf983a20"
_ORNERY = "8291bc2e-ef58-4bd4-b261-b587142bbb1c"


def _leaf_atoms(f: Filter) -> list[FAtom]:
    """Flatten a Filter to its FAtom leaves (typed narrowing helper)."""
    if isinstance(f, FAtom):
        return [f]
    if isinstance(f, FAnd):
        return [a for child in f.children for a in _leaf_atoms(child)]
    raise AssertionError(f"unexpected filter node {type(f).__name__}")


class TestC2CompilerPins(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pool = ingest_pool(_M21_PATH)
        cls.reg = build_full_registry()

    def _compile(self, oid: str):
        res = compile_card(self.pool[oid], self.reg)
        self.assertEqual(res.unparsed, ())
        return res

    # ---- Fabled Passage: SEARCH tapped_on_enter ----

    def test_fabled_search_atom_stamps_tapped_on_enter(self) -> None:
        """The printed "put it onto the battlefield tapped" lives in the IR, not
        in an executor-side default."""
        res = self._compile(_FABLED)
        (ability,) = res.card.abilities
        assert isinstance(ability, ActivatedAbility)
        assert isinstance(ability.effect, Seq)
        search = ability.effect.steps[0]
        assert isinstance(search, Atom)
        self.assertIs(search.verb, Verb.SEARCH)
        self.assertIs(search.args.get("tapped_on_enter"), True)

    def test_fabled_conditional_untap_tail_still_falsifiable(self) -> None:
        """The >=4-land branch is a Conditional(CONTROLLER_COUNT_GE Lands>=4,
        UNTAP); the fabled_passage.json pack asserts the untap fires."""
        res = self._compile(_FABLED)
        (ability,) = res.card.abilities
        assert isinstance(ability, ActivatedAbility)
        assert isinstance(ability.effect, Seq)
        tail = ability.effect.steps[2]
        assert isinstance(tail, Conditional)
        assert isinstance(tail.pred, FAtom)
        self.assertIs(tail.pred.pred, FAtomPred.CONTROLLER_COUNT_GE)
        self.assertEqual(tail.pred.count, QConst(4))

    # ---- existential conditions ----

    def test_adherent_condition_is_existential_census(self) -> None:
        """Adherent of Hope: the condition quantifies over controlled
        permanents (COUNT_GE count=1 + inner NAME_CONTAINS/TYPE_EQ/
        CONTROLLER_IS), not a filter judged against the trigger source."""
        res = self._compile(_ADHERENT)
        ability, _carrier = res.card.abilities  # + the effect-less cast carrier
        assert isinstance(ability, TriggeredAbility)
        cond = ability.condition
        assert isinstance(cond, FAtom)  # NOT FAnd: the quantifier leads
        self.assertIs(cond.pred, FAtomPred.CONTROLLER_COUNT_GE)
        self.assertEqual(cond.count, QConst(1))
        inner = cond.inner_filter
        assert isinstance(inner, FAnd)
        preds = [a.pred for a in _leaf_atoms(inner)]
        self.assertIn(FAtomPred.NAME_CONTAINS, preds)
        self.assertIn(FAtomPred.TYPE_EQ, preds)
        self.assertIn(FAtomPred.CONTROLLER_IS, preds)
        name = next(a for a in _leaf_atoms(inner) if a.pred is FAtomPred.NAME_CONTAINS)
        self.assertEqual(name.string_value, "Basri")

    def test_ornery_gate_counts_one_creature_not_four(self) -> None:
        """Ornery Dilophosaur: one controlled creature matching the power
        filter is demanded (count=1); the printed 4 lives only in POWER_GE."""
        res = self._compile(_ORNERY)
        ability, _carrier = res.card.abilities  # + the effect-less cast carrier
        assert isinstance(ability, TriggeredAbility)
        cond = ability.condition
        assert isinstance(cond, FAtom)
        self.assertIs(cond.pred, FAtomPred.CONTROLLER_COUNT_GE)
        self.assertEqual(cond.count, QConst(1))
        assert isinstance(cond.inner_filter, FAnd)
        power = next(
            a for a in _leaf_atoms(cond.inner_filter) if a.pred is FAtomPred.POWER_GE
        )
        self.assertEqual(power.count, QConst(4))

    def test_ornery_row_decouples_count_from_threshold(self) -> None:
        """A synthetic "power 6 or greater ... +1/+1" sentence emits count=1 /
        POWER_GE=6: the number never binds to the count."""
        from MTG_bot.core.compiler import templates_b2b
        from MTG_bot.core.compiler.templates import TemplateRegistry

        reg = TemplateRegistry()
        for template in templates_b2b.TEMPLATES:
            reg.register(template)
        matches = reg.match(
            "Whenever this creature attacks, if you control a creature "
            "with power 6 or greater, this creature gets +1/+1 until "
            "end of turn."
        )
        self.assertEqual(len(matches), 1)
        outcome = matches[0].outcome
        ability = getattr(outcome, "ability", outcome)
        assert isinstance(ability, TriggeredAbility)
        cond = ability.condition
        assert isinstance(cond, FAtom)
        self.assertEqual(cond.count, QConst(1))
        assert isinstance(cond.inner_filter, FAnd)
        power = next(
            a for a in _leaf_atoms(cond.inner_filter) if a.pred is FAtomPred.POWER_GE
        )
        self.assertEqual(power.count, QConst(6))


if __name__ == "__main__":
    unittest.main()
