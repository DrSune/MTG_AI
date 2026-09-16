"""Tests for B1 bucket templates (templates_b1.py).

Covers all 15 shapes in ``/tmp/opencode/phase1_buckets/B1.json``
(49 concrete sentences):
- 12 keyword shapes -> ``KeywordOutcome`` (10 bare keywords, plus
  ``Hexproof from black`` and ``Protection from planeswalkers`` which
  carry a single ``Filter`` param)
- 3 enchant shapes -> ``MetaOutcome(kind="enchant", filter=...)``
- ``UNCOVERED = ()`` — every B1 shape is template-covered.

PC-3: every B1 concrete sentence fullmatches at most one template
(patterns are pairwise disjoint by construction).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from MTG_bot.core.ability_tree import (
    ControllerRef,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    Keyword,
    KeywordAbility,
    canonical_json,
    fingerprint,
)
from MTG_bot.core.compiler import templates_b1
from MTG_bot.core.compiler.templates import (
    KeywordOutcome,
    Match,
    MetaOutcome,
    SentenceOutcome,
    TemplateRegistry,
)

_B1_PATH = Path("/tmp/opencode/phase1_buckets/B1.json")


def _load_b1() -> dict[str, tuple[tuple[str, str], ...]]:
    raw: dict[str, list[list[str]]] = json.loads(_B1_PATH.read_text())
    return {
        shape_key: tuple((entry[0], entry[1]) for entry in entries)
        for shape_key, entries in raw.items()
    }


def _registry() -> TemplateRegistry:
    reg = TemplateRegistry()
    for template in templates_b1.TEMPLATES:
        reg.register(template)
    return reg


def _single_match(reg: TemplateRegistry, sentence: str) -> Match:
    matches = reg.match(sentence)
    assert len(matches) == 1, (
        f"expected exactly one match for {sentence!r}, got {len(matches)}"
    )
    return matches[0]


# ---------------------------------------------------------------------------
# Narrowing / extraction helpers (Pyright-safe)
# ---------------------------------------------------------------------------


def _inner_node(outcome: SentenceOutcome) -> Any:
    """Extract the serialisable grammar node from a SentenceOutcome.

    canonical_json/fingerprint only work on grammar dataclasses (registered
    in _TAG), not on the outcome wrappers. B1 outcomes are either
    KeywordOutcome (mapped to a KeywordAbility) or MetaOutcome (its
    enchant ``filter`` is the grammar node).
    """
    if isinstance(outcome, KeywordOutcome):
        return KeywordAbility(keyword=outcome.keyword, params=outcome.params)
    if isinstance(outcome, MetaOutcome):
        return outcome.filter
    raise TypeError(f"cannot extract inner node from {type(outcome).__name__}")


def _as_keyword(outcome: SentenceOutcome) -> KeywordOutcome:
    if not isinstance(outcome, KeywordOutcome):
        raise AssertionError(f"expected KeywordOutcome, got {type(outcome).__name__}")
    return outcome


def _as_meta(outcome: SentenceOutcome) -> MetaOutcome:
    if not isinstance(outcome, MetaOutcome):
        raise AssertionError(f"expected MetaOutcome, got {type(outcome).__name__}")
    return outcome


def _as_fatom(value: object) -> FAtom:
    if not isinstance(value, FAtom):
        raise AssertionError(f"expected FAtom, got {type(value).__name__}")
    return value


def _as_fand(value: object) -> FAnd:
    if not isinstance(value, FAnd):
        raise AssertionError(f"expected FAnd, got {type(value).__name__}")
    return value


def _and_children(f: Filter) -> tuple[Filter, ...]:
    assert isinstance(f, FAnd), f"expected FAnd filter, got {type(f).__name__}"
    return f.children


def _find_atom(f: Filter, pred: FAtomPred, **slots: Any) -> FAtom:
    """Find an FAtom child of an FAnd with the given pred and slot values."""
    for child in _and_children(f):
        if isinstance(child, FAtom) and child.pred is pred and all(
            getattr(child, key) == value for key, value in slots.items()
        ):
            return child
    raise AssertionError(f"no FAtom(pred={pred.name}, {slots}) inside FAnd")


# ---------------------------------------------------------------------------
# Expected outcome kind per covered concrete sentence
#   sentence -> (tid, "keyword" | "meta")
# ---------------------------------------------------------------------------

EXPECTED_KIND: dict[str, tuple[str, str]] = {
    "Deathtouch": ("B1-kw-deathtouch", "keyword"),
    "Flash": ("B1-kw-flash", "keyword"),
    "Flying": ("B1-kw-flying", "keyword"),
    "Haste": ("B1-kw-haste", "keyword"),
    "Hexproof": ("B1-kw-hexproof", "keyword"),
    "Hexproof from black": ("B1-kw-hexproof-black", "keyword"),
    "Indestructible": ("B1-kw-indestructible", "keyword"),
    "Lifelink": ("B1-kw-lifelink", "keyword"),
    "Protection from planeswalkers": ("B1-kw-protection-planeswalkers", "keyword"),
    "Reach": ("B1-kw-reach", "keyword"),
    "Trample": ("B1-kw-trample", "keyword"),
    "Vigilance": ("B1-kw-vigilance", "keyword"),
    "Enchant creature": ("B1-enchant-creature", "meta"),
    "Enchant creature you control": ("B1-enchant-creature-you", "meta"),
    "Enchant permanent": ("B1-enchant-permanent", "meta"),
}


# ---------------------------------------------------------------------------
# Test: Template Inventory
# ---------------------------------------------------------------------------


class TestB1Inventory(unittest.TestCase):
    """Verify the B1 template collection is well-formed."""

    def setUp(self) -> None:
        self.data = _load_b1()

    def test_15_templates(self) -> None:
        self.assertEqual(len(templates_b1.TEMPLATES), 15)

    def test_0_uncovered(self) -> None:
        self.assertEqual(len(templates_b1.UNCOVERED), 0)

    def test_unique_tids(self) -> None:
        tids = [t.tid for t in templates_b1.TEMPLATES]
        self.assertEqual(len(tids), len(set(tids)), "duplicate tid found")

    def test_all_bucket_b1(self) -> None:
        for t in templates_b1.TEMPLATES:
            self.assertEqual(t.bucket, "B1", f"{t.tid} has bucket {t.bucket}")

    def test_all_priority_100(self) -> None:
        for t in templates_b1.TEMPLATES:
            self.assertEqual(t.priority, 100, f"{t.tid} has priority {t.priority}")

    def test_registry_accepts_all(self) -> None:
        reg = _registry()
        self.assertEqual(len(reg), 15)

    def test_every_template_matches_some_bucket_sentence(self) -> None:
        sentences = [
            sentence for entries in self.data.values() for _card, sentence in entries
        ]
        for template in templates_b1.TEMPLATES:
            hits = [s for s in sentences if template.pattern.fullmatch(s)]
            self.assertTrue(hits, f"template {template.tid} matches no bucket sentence")


# ---------------------------------------------------------------------------
# Test: Coverage partition
# ---------------------------------------------------------------------------


class TestB1Coverage(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _load_b1()
        self.reg = _registry()

    def test_bucket_file_has_15_shapes_and_49_occurrences(self) -> None:
        self.assertEqual(len(self.data), 15)
        total = sum(len(entries) for entries in self.data.values())
        self.assertEqual(total, 49)

    def test_all_shapes_and_occurrences_covered(self) -> None:
        covered_shapes = 0
        matched_occurrences = 0
        for entries in self.data.values():
            shape_matched = False
            for _card, sentence in entries:
                if self.reg.match(sentence):
                    matched_occurrences += 1
                    shape_matched = True
            if shape_matched:
                covered_shapes += 1
        self.assertEqual(covered_shapes, 15)
        self.assertEqual(matched_occurrences, 49)

    def test_uncovered_is_empty(self) -> None:
        self.assertEqual(templates_b1.UNCOVERED, ())

    def test_every_sentence_matches(self) -> None:
        for _shape, entries in self.data.items():
            for _card, sentence in entries:
                self.assertTrue(self.reg.match(sentence), sentence)

    def test_expected_kind_table_is_consistent_with_bucket(self) -> None:
        self.assertEqual(len(EXPECTED_KIND), 15)
        all_sentences = {
            s for entries in self.data.values() for _card, s in entries
        }
        for sentence in EXPECTED_KIND:
            self.assertIn(sentence, all_sentences, sentence)
        kinds = {kind for _tid, kind in EXPECTED_KIND.values()}
        self.assertEqual(kinds, {"keyword", "meta"})


# ---------------------------------------------------------------------------
# Test: PC-3 Matching
# ---------------------------------------------------------------------------


class TestB1Matching(unittest.TestCase):
    """PC-3: every B1 concrete sentence fullmatches at most one template."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = _registry()
        cls.data = _load_b1()

    def test_pc3_at_most_one_match(self) -> None:
        for shape_key, entries in self.data.items():
            for card, sentence in entries:
                matches = self.reg.match(sentence)
                self.assertLessEqual(
                    len(matches),
                    1,
                    f"PC-3 violated ({len(matches)} matches) for {card!r} "
                    f"/ {shape_key!r}: {sentence!r}",
                )

    def test_covered_sentences_match_expected_tid_and_kind(self) -> None:
        for sentence, (expected_tid, expected_kind) in EXPECTED_KIND.items():
            match = _single_match(self.reg, sentence)
            self.assertEqual(match.template.tid, expected_tid, sentence)
            if expected_kind == "keyword":
                self.assertIsInstance(match.outcome, KeywordOutcome, sentence)
            else:
                self.assertIsInstance(match.outcome, MetaOutcome, sentence)

    def test_pc3_canonical_is_unique(self) -> None:
        for shape_key, entries in self.data.items():
            for card, sentence in entries:
                matches = self.reg.match(sentence)
                if not matches:
                    continue
                canonicals = {
                    canonical_json(_inner_node(match.outcome)) for match in matches
                }
                self.assertEqual(
                    len(canonicals),
                    1,
                    f"PC-3 canonical ambiguity for {card!r} / {shape_key!r}: "
                    f"{sentence!r}",
                )

    def test_fingerprint_is_stable(self) -> None:
        for shape_key, entries in self.data.items():
            for card, sentence in entries:
                matches = self.reg.match(sentence)
                if not matches:
                    continue
                first = fingerprint(_inner_node(matches[0].outcome))
                rematch = self.reg.match(sentence)
                assert rematch, sentence
                second = fingerprint(_inner_node(rematch[0].outcome))
                self.assertEqual(
                    first,
                    second,
                    f"fingerprint unstable for {card!r} / {shape_key!r}: "
                    f"{sentence!r}",
                )


# ---------------------------------------------------------------------------
# Test: IR structure — one test per template
# ---------------------------------------------------------------------------


class TestB1IrStructure(unittest.TestCase):
    def setUp(self) -> None:
        self.reg = _registry()

    # -- keyword templates (bare) -----------------------------------------

    def test_kw_deathtouch(self) -> None:
        self._assert_bare_keyword("Deathtouch", Keyword.DEATHTOUCH)

    def test_kw_flash(self) -> None:
        self._assert_bare_keyword("Flash", Keyword.FLASH)

    def test_kw_flying(self) -> None:
        self._assert_bare_keyword("Flying", Keyword.FLYING)

    def test_kw_haste(self) -> None:
        self._assert_bare_keyword("Haste", Keyword.HASTE)

    def test_kw_hexproof(self) -> None:
        self._assert_bare_keyword("Hexproof", Keyword.HEXPROOF)

    def test_kw_indestructible(self) -> None:
        self._assert_bare_keyword("Indestructible", Keyword.INDESTRUCTIBLE)

    def test_kw_lifelink(self) -> None:
        self._assert_bare_keyword("Lifelink", Keyword.LIFELINK)

    def test_kw_reach(self) -> None:
        self._assert_bare_keyword("Reach", Keyword.REACH)

    def test_kw_trample(self) -> None:
        self._assert_bare_keyword("Trample", Keyword.TRAMPLE)

    def test_kw_vigilance(self) -> None:
        self._assert_bare_keyword("Vigilance", Keyword.VIGILANCE)

    # -- keyword templates (with a Filter param) --------------------------

    def test_kw_hexproof_black(self) -> None:
        kw = _as_keyword(_single_match(self.reg, "Hexproof from black").outcome)
        self.assertIs(kw.keyword, Keyword.HEXPROOF)
        self.assertEqual(len(kw.params), 1)
        param = _as_fatom(kw.params[0])
        self.assertIs(param.pred, FAtomPred.COLOR_HAS)
        self.assertEqual(param.color, "B")

    def test_kw_protection_planeswalkers(self) -> None:
        kw = _as_keyword(
            _single_match(self.reg, "Protection from planeswalkers").outcome
        )
        self.assertIs(kw.keyword, Keyword.PROTECTION)
        self.assertEqual(len(kw.params), 1)
        param = _as_fatom(kw.params[0])
        self.assertIs(param.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(param.string_value, "Planeswalker")

    # -- enchant templates (MetaOutcome) -----------------------------------

    def test_enchant_creature(self) -> None:
        meta = _as_meta(_single_match(self.reg, "Enchant creature").outcome)
        self.assertEqual(meta.kind, "enchant")
        atom = _as_fatom(meta.filter)
        self.assertIs(atom.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(atom.string_value, "Creature")

    def test_enchant_creature_you(self) -> None:
        meta = _as_meta(
            _single_match(self.reg, "Enchant creature you control").outcome
        )
        self.assertEqual(meta.kind, "enchant")
        fand = _as_fand(meta.filter)
        self.assertEqual(len(fand.children), 2)
        _find_atom(fand, FAtomPred.TYPE_EQ, string_value="Creature")
        _find_atom(fand, FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)

    def test_enchant_permanent(self) -> None:
        meta = _as_meta(_single_match(self.reg, "Enchant permanent").outcome)
        self.assertEqual(meta.kind, "enchant")
        atom = _as_fatom(meta.filter)
        self.assertIs(atom.pred, FAtomPred.IS_PERMANENT)

    # -- helpers ----------------------------------------------------------

    def _assert_bare_keyword(self, sentence: str, keyword: Keyword) -> None:
        kw = _as_keyword(_single_match(self.reg, sentence).outcome)
        self.assertIs(kw.keyword, keyword, sentence)
        self.assertEqual(kw.params, (), f"{sentence!r} should carry no params")


if __name__ == "__main__":
    unittest.main()
