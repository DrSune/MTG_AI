"""C2 compiler campaign batches 0+1 — falsifiability pins (2026-10-02).

Batch 0 (fabled flag): the Fabled Passage SEARCH atom must carry the
printed "onto the battlefield tapped" as ``tapped_on_enter=True`` (the
wave-21b suspect: the flag was silently DROPPED while the grammar slot and
the ``_v_search`` consumer already existed).

Batch 1 (existential census): "if you control a Basri planeswalker" / "if
you control a creature with power 4 or greater" are EXISTENCE claims over
the controlled population — CONTROLLER_COUNT_GE count=1 with the per-card
test INSIDE the inner filter (r18a turret_ogre idiom). The wave-5a suspect
(Adherent: bare filter judged against the trigger SOURCE only) and the
wave-3b suspect (Ornery: the printed 4 bound to the COUNT instead of the
POWER filter) are the miscompiles these pins falsify.

Goldens moved for all three cards under the C1-form set-evidence audit
(KNOWLEDGE/2026-10-02/04; pre-snapshot /tmp/golden_pre_c2, 302 others
byte-identical).
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

    # ---- batch 0: fabled_passage SEARCH tapped_on_enter stamp ----

    def test_fabled_search_atom_stamps_tapped_on_enter(self) -> None:
        """The printed "put it onto the battlefield tapped" is EMITTED.

        Falsified if the flag is dropped (wave-21b) or if a blanket
        executor-side default replaced the emission (the slot must live in
        the IR, per the suspect's STOP ruling)."""
        res = self._compile(_FABLED)
        (ability,) = res.card.abilities
        assert isinstance(ability, ActivatedAbility)
        assert isinstance(ability.effect, Seq)
        search = ability.effect.steps[0]
        assert isinstance(search, Atom)
        self.assertIs(search.verb, Verb.SEARCH)
        self.assertIs(search.args.get("tapped_on_enter"), True)

    def test_fabled_conditional_untap_tail_still_falsifiable(self) -> None:
        """The >=4-land branch stays a Conditional(CONTROLLER_COUNT_GE
        Lands>=4, UNTAP) — the green fabled_passage.json pack asserts the
        untap fires, so the two branches are independently falsifiable."""
        res = self._compile(_FABLED)
        (ability,) = res.card.abilities
        assert isinstance(ability, ActivatedAbility)
        assert isinstance(ability.effect, Seq)
        tail = ability.effect.steps[2]
        assert isinstance(tail, Conditional)
        assert isinstance(tail.pred, FAtom)
        self.assertIs(tail.pred.pred, FAtomPred.CONTROLLER_COUNT_GE)
        self.assertEqual(tail.pred.count, QConst(4))

    # ---- batch 1: existential census emission ----

    def test_adherent_condition_is_existential_census(self) -> None:
        """Adherent of Hope: the condition QUANTIFIES over controlled
        permanents — COUNT_GE(count=1) + inner NAME_CONTAINS/TYPE_EQ/
        CONTROLLER_IS — not the old bare filter the gate judged against
        the trigger source (wave-5a suspect)."""
        res = self._compile(_ADHERENT)
        (ability,) = res.card.abilities
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
        """Ornery Dilophosaur: EXACTLY ONE controlled creature matching
        the power filter is demanded (count=1); the printed 4 lives only
        in the POWER_GE filter (wave-3b off-by-one)."""
        res = self._compile(_ORNERY)
        (ability,) = res.card.abilities
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
        """The row reads DIFFERENT numbers correctly: a synthetic "power 6
        or greater ... +1/+1" sentence must emit count=1 / POWER_GE=6 — a
        template that rebinds the number to the COUNT fails here."""
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
