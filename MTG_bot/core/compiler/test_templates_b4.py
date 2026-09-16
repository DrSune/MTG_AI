"""Tests for B4 bucket templates (templates_b4.py).

Covers all 47 shapes in ``/tmp/opencode/phase1_buckets/B4.json``
(63 concrete sentences):
- 18 shapes template-covered (19 concrete sentences; ``You gain N life.``
  carries two) -> 18 templates
- 29 shapes UNCOVERED (44 concrete sentences; no grammar construct)

PC-3: every B4 concrete sentence fullmatches at most one template.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from MTG_bot.core.ability_tree import (
    Atom,
    ControllerRef,
    CounterKind,
    DeclareBlockersEvent,
    DurationEot,
    DurationWhileCondition,
    Effect,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    Filter,
    Keyword,
    KeywordAbility,
    PtDelta,
    PtDirection,
    QAgg,
    QConst,
    QCount,
    QProp,
    QPropField,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    Verb,
    ZoneKind,
    canonical_json,
    fingerprint,
)
from MTG_bot.core.compiler import templates_b4
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    Match,
    SentenceOutcome,
    TemplateRegistry,
)

_B4_PATH = Path("/tmp/opencode/phase1_buckets/B4.json")


def _load_b4() -> dict[str, tuple[tuple[str, str], ...]]:
    raw: dict[str, list[list[str]]] = json.loads(_B4_PATH.read_text())
    return {
        shape_key: tuple((entry[0], entry[1]) for entry in entries)
        for shape_key, entries in raw.items()
    }


def _registry() -> TemplateRegistry:
    reg = TemplateRegistry()
    for template in templates_b4.TEMPLATES:
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
    in _TAG), not on the outcome wrappers.
    """
    if isinstance(outcome, AbilityOutcome):
        return outcome.ability
    if isinstance(outcome, EffectOutcome):
        return outcome.effect
    raise TypeError(f"cannot extract inner node from {type(outcome).__name__}")


def _as_effect(outcome: SentenceOutcome) -> EffectOutcome:
    if not isinstance(outcome, EffectOutcome):
        raise AssertionError(f"expected EffectOutcome, got {type(outcome).__name__}")
    return outcome


def _as_ability(outcome: SentenceOutcome) -> AbilityOutcome:
    if not isinstance(outcome, AbilityOutcome):
        raise AssertionError(f"expected AbilityOutcome, got {type(outcome).__name__}")
    return outcome


def _as_static(ability: Any) -> StaticAbility:
    if not isinstance(ability, StaticAbility):
        raise AssertionError(f"expected StaticAbility, got {type(ability).__name__}")
    return ability


def _effect_of(match: Match) -> Effect:
    """The top-level Effect of either outcome kind (StaticAbility is
    static-only in B4)."""
    outcome = match.outcome
    if isinstance(outcome, AbilityOutcome):
        return _as_static(outcome.ability).effect
    if isinstance(outcome, EffectOutcome):
        return outcome.effect
    raise TypeError(f"cannot extract effect from {type(outcome).__name__}")


def _as_atom(effect: Effect) -> Atom:
    if not isinstance(effect, Atom):
        raise AssertionError(f"expected Atom, got {type(effect).__name__}")
    return effect


def _as_seq(effect: Effect) -> Seq:
    if not isinstance(effect, Seq):
        raise AssertionError(f"expected Seq, got {type(effect).__name__}")
    return effect


def _pairs(atom: Atom) -> dict[str, Any]:
    return dict(atom.args.pairs)


def _selector(atom: Atom, role: str) -> Selector:
    value = atom.args.get(role)
    assert isinstance(value, Selector), (
        f"role {role!r} expected Selector, got {type(value).__name__}"
    )
    return value


def _pt_delta(atom: Atom, role: str) -> PtDelta:
    value = atom.args.get(role)
    assert isinstance(value, PtDelta), (
        f"role {role!r} expected PtDelta, got {type(value).__name__}"
    )
    return value


def _qconst(value: Any) -> QConst:
    assert isinstance(value, QConst), f"expected QConst, got {type(value).__name__}"
    return value


def _keyword_ability(atom: Atom, role: str) -> KeywordAbility:
    value = atom.args.get(role)
    assert isinstance(value, KeywordAbility), (
        f"role {role!r} expected KeywordAbility, got {type(value).__name__}"
    )
    return value


# ``AtomArgs.get`` returns ``object | None`` (and ``_pairs().get`` returns
# ``Any | None``); unittest's assertIsInstance does not narrow for Pyright, so
# each of these uses a builtin isinstance to produce a concrete, non-Optional
# type that the test body can access freely.
def _as_fatom(value: object) -> FAtom:
    if not isinstance(value, FAtom):
        raise AssertionError(f"expected FAtom, got {type(value).__name__}")
    return value


def _as_selector(value: object) -> Selector:
    if not isinstance(value, Selector):
        raise AssertionError(f"expected Selector, got {type(value).__name__}")
    return value


def _as_qprop(value: object) -> QProp:
    if not isinstance(value, QProp):
        raise AssertionError(f"expected QProp, got {type(value).__name__}")
    return value


def _as_qcount(value: object) -> QCount:
    if not isinstance(value, QCount):
        raise AssertionError(f"expected QCount, got {type(value).__name__}")
    return value


def _as_duration_while(value: object) -> DurationWhileCondition:
    if not isinstance(value, DurationWhileCondition):
        raise AssertionError(
            f"expected DurationWhileCondition, got {type(value).__name__}"
        )
    return value


def _as_blockers_event(value: object) -> DeclareBlockersEvent:
    if not isinstance(value, DeclareBlockersEvent):
        raise AssertionError(
            f"expected DeclareBlockersEvent, got {type(value).__name__}"
        )
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


def _find_fnot(f: Filter) -> FNot:
    for child in _and_children(f):
        if isinstance(child, FNot):
            return child
    raise AssertionError("no FNot child inside FAnd")


# ---------------------------------------------------------------------------
# Expected outcome kind per covered concrete sentence
#   sentence -> (tid, "ability" | "effect")
# ---------------------------------------------------------------------------

EXPECTED_KIND: dict[str, tuple[str, str]] = {
    "Creatures you control attack each combat if able.": (
        "B4-mandate-attack-you",
        "ability",
    ),
    "Creatures you control gain trample until end of turn.": (
        "B4-grant-trample-eot-you",
        "effect",
    ),
    "Creatures you control get +2/+0 until end of turn.": (
        "B4-modify-pt-eot-you",
        "effect",
    ),
    "Creatures you control get +1/+1.": ("B4-modify-pt-static-you", "ability"),
    "Creatures you control have trample.": ("B4-grant-kw-static-you", "ability"),
    "Creatures your opponents control get -1/-0.": (
        "B4-modify-pt-static-opponents",
        "effect",
    ),
    "Other Cats you control get +1/+1 and have protection from Dogs.": (
        "B4-modify-pt-protect-other-cats",
        "ability",
    ),
    "Other Dogs you control get +1/+1.": ("B4-modify-pt-other-dogs", "ability"),
    "Other creatures get -1/-1.": ("B4-modify-pt-other-creatures", "ability"),
    "This creature can't block.": ("B4-cant-block", "ability"),
    "This creature gets +2/+2 as long as you control a Garruk planeswalker.": (
        "B4-modify-pt-while-garruk",
        "ability",
    ),
    "This creature gets +X/+0, where X is the greatest power among creature "
    "cards in your graveyard.": ("B4-modify-pt-qprop-graveyard", "ability"),
    "This creature has lifelink as long as it has a +1/+1 counter on it.": (
        "B4-grant-lifelink-while-counter",
        "ability",
    ),
    "You control enchanted creature.": ("B4-gain-control-enchanted", "effect"),
    "You draw two cards and each opponent discards two cards.": (
        "B4-draw-discard-bad-deal",
        "effect",
    ),
    "You gain 4 life.": ("B4-gain-life-n", "effect"),
    "You gain 3 life.": ("B4-gain-life-n", "effect"),
    "You gain life equal to the number of Cats you control.": (
        "B4-gain-life-qcount-cats",
        "ability",
    ),
    "You lose 3 life.": ("B4-lose-life-n", "effect"),
}


# ---------------------------------------------------------------------------
# Test: Template Inventory
# ---------------------------------------------------------------------------


class TestB4Inventory(unittest.TestCase):
    """Verify the B4 template collection is well-formed."""

    def setUp(self) -> None:
        self.data = _load_b4()

    def test_18_templates(self) -> None:
        self.assertEqual(len(templates_b4.TEMPLATES), 18)

    def test_29_uncovered(self) -> None:
        self.assertEqual(len(templates_b4.UNCOVERED), 29)

    def test_unique_tids(self) -> None:
        tids = [t.tid for t in templates_b4.TEMPLATES]
        self.assertEqual(len(tids), len(set(tids)), "duplicate tid found")

    def test_all_bucket_b4(self) -> None:
        for t in templates_b4.TEMPLATES:
            self.assertEqual(t.bucket, "B4", f"{t.tid} has bucket {t.bucket}")

    def test_all_priority_100(self) -> None:
        for t in templates_b4.TEMPLATES:
            self.assertEqual(t.priority, 100, f"{t.tid} has priority {t.priority}")

    def test_registry_accepts_all(self) -> None:
        reg = _registry()
        self.assertEqual(len(reg), 18)

    def test_every_template_matches_some_bucket_sentence(self) -> None:
        sentences = [
            sentence for entries in self.data.values() for _card, sentence in entries
        ]
        for template in templates_b4.TEMPLATES:
            hits = [s for s in sentences if template.pattern.fullmatch(s)]
            self.assertTrue(hits, f"template {template.tid} matches no bucket sentence")


# ---------------------------------------------------------------------------
# Test: Coverage partition
# ---------------------------------------------------------------------------


class TestB4Coverage(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _load_b4()
        self.reg = _registry()

    def test_bucket_file_has_47_shapes_and_63_occurrences(self) -> None:
        self.assertEqual(len(self.data), 47)
        total = sum(len(entries) for entries in self.data.values())
        self.assertEqual(total, 63)

    def test_covered_shape_and_occurrence_counts(self) -> None:
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
        self.assertEqual(covered_shapes, 18)
        self.assertEqual(matched_occurrences, 19)

    def test_uncovered_shapes_are_exactly_the_unmatched_shapes(self) -> None:
        unmatched: set[str] = set()
        for shape_key, entries in self.data.items():
            if not any(self.reg.match(sentence) for _card, sentence in entries):
                unmatched.add(shape_key)
        declared = {shape_key for shape_key, _reason in templates_b4.UNCOVERED}
        self.assertEqual(unmatched, declared)

    def test_uncovered_sentences_do_not_match(self) -> None:
        for shape_key, _reason in templates_b4.UNCOVERED:
            self.assertIn(shape_key, self.data)
            for _card, sentence in self.data[shape_key]:
                self.assertEqual(self.reg.match(sentence), (), sentence)

    def test_expected_kind_table_is_consistent_with_bucket(self) -> None:
        self.assertEqual(len(EXPECTED_KIND), 19)
        for sentence in EXPECTED_KIND:
            for _shape, entries in self.data.items():
                if sentence in [s for _card, s in entries]:
                    break
            else:
                self.fail(f"expected-kind sentence not in bucket: {sentence!r}")
        kinds = {kind for _tid, kind in EXPECTED_KIND.values()}
        self.assertEqual(kinds, {"ability", "effect"})


# ---------------------------------------------------------------------------
# Test: PC-3 Matching
# ---------------------------------------------------------------------------


class TestB4Matching(unittest.TestCase):
    """PC-3: every B4 concrete sentence fullmatches at most one template."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = _registry()
        cls.data = _load_b4()

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
            if expected_kind == "ability":
                self.assertIsInstance(match.outcome, AbilityOutcome, sentence)
            else:
                self.assertIsInstance(match.outcome, EffectOutcome, sentence)

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


class TestB4IrStructure(unittest.TestCase):
    def setUp(self) -> None:
        self.reg = _registry()

    def test_mandate_attack_you(self) -> None:
        atom = _as_atom(
            _effect_of(_single_match(self.reg, "Creatures you control attack each combat if able."))
        )
        self.assertIs(atom.verb, Verb.MANDATE_ATTACK)
        cards = _selector(atom, "cards")
        self.assertIs(cards.mode, SelectorMode.ALL)
        self.assertIsInstance(cards.count, QUnbounded)
        self.assertIs(cards.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(cards.zone.controller, ControllerRef.YOU)
        _find_atom(cards.filter, FAtomPred.TYPE_EQ, string_value="Creature")
        _find_atom(cards.filter, FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
        self.assertIs(_pairs(atom).get("controller"), ControllerRef.YOU)

    def test_grant_trample_eot(self) -> None:
        outcome = _as_effect(
            _single_match(
                self.reg, "Creatures you control gain trample until end of turn."
            ).outcome
        )
        atom = _as_atom(outcome.effect)
        self.assertIs(atom.verb, Verb.GRANT_ABILITY)
        keyword_ability = _keyword_ability(atom, "ability")
        self.assertIs(keyword_ability.keyword, Keyword.TRAMPLE)
        self.assertEqual(keyword_ability.params, ())
        duration = atom.args.get("duration")
        self.assertIsInstance(duration, DurationEot)
        target = _selector(atom, "target")
        self.assertIs(target.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(target.zone.controller, ControllerRef.YOU)

    def test_modify_pt_eot_you(self) -> None:
        outcome = _as_effect(
            _single_match(
                self.reg, "Creatures you control get +2/+0 until end of turn."
            ).outcome
        )
        atom = _as_atom(outcome.effect)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        power = _pt_delta(atom, "power")
        toughness = _pt_delta(atom, "toughness")
        self.assertIs(power.direction, PtDirection.INCREASE)
        self.assertIs(toughness.direction, PtDirection.INCREASE)
        self.assertEqual(_qconst(power.magnitude).value, 2)
        self.assertEqual(_qconst(toughness.magnitude).value, 0)
        duration = atom.args.get("duration")
        self.assertIsInstance(duration, DurationEot)

    def test_modify_pt_static_you(self) -> None:
        outcome = _as_ability(
            _single_match(self.reg, "Creatures you control get +1/+1.").outcome
        )
        atom = _as_atom(_as_static(outcome.ability).effect)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        power = _pt_delta(atom, "power")
        toughness = _pt_delta(atom, "toughness")
        self.assertIs(power.direction, PtDirection.INCREASE)
        self.assertIs(toughness.direction, PtDirection.INCREASE)
        self.assertEqual(_qconst(power.magnitude).value, 1)
        self.assertEqual(_qconst(toughness.magnitude).value, 1)
        self.assertNotIn("duration", _pairs(atom))

    def test_grant_kw_static_you(self) -> None:
        outcome = _as_ability(
            _single_match(self.reg, "Creatures you control have trample.").outcome
        )
        atom = _as_atom(_as_static(outcome.ability).effect)
        self.assertIs(atom.verb, Verb.GRANT_ABILITY)
        keyword_ability = _keyword_ability(atom, "ability")
        self.assertIs(keyword_ability.keyword, Keyword.TRAMPLE)
        self.assertNotIn("duration", _pairs(atom))

    def test_modify_pt_static_opponents(self) -> None:
        outcome = _as_effect(
            _single_match(
                self.reg, "Creatures your opponents control get -1/-0."
            ).outcome
        )
        atom = _as_atom(outcome.effect)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        power = _pt_delta(atom, "power")
        toughness = _pt_delta(atom, "toughness")
        self.assertIs(power.direction, PtDirection.DECREASE)
        self.assertIs(toughness.direction, PtDirection.DECREASE)
        self.assertEqual(_qconst(power.magnitude).value, 1)
        self.assertEqual(_qconst(toughness.magnitude).value, 0)
        target = _selector(atom, "target")
        self.assertIs(target.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(target.zone.controller, ControllerRef.ALL_OPPONENTS)
        _find_atom(target.filter, FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT)
        self.assertNotIn("duration", _pairs(atom))

    def test_modify_pt_protect_other_cats(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg,
                "Other Cats you control get +1/+1 and have protection from Dogs.",
            ).outcome
        )
        seq = _as_seq(_as_static(outcome.ability).effect)
        self.assertEqual(len(seq.steps), 2)
        atom_pt, atom_prot = seq.steps
        assert isinstance(atom_pt, Atom)
        assert isinstance(atom_prot, Atom)
        self.assertIs(atom_pt.verb, Verb.MODIFY_PT)
        target = _selector(atom_pt, "target")
        self.assertIs(target.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(target.zone.controller, ControllerRef.YOU)
        _find_atom(target.filter, FAtomPred.TYPE_EQ, string_value="Creature")
        _find_atom(target.filter, FAtomPred.SUBTYPE_EQ, string_value="Cat")
        _find_atom(target.filter, FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
        fnot = _find_fnot(target.filter)
        inner = fnot.inner
        assert isinstance(inner, FAtom)
        self.assertIs(inner.pred, FAtomPred.IS_SOURCE)
        power = _pt_delta(atom_pt, "power")
        self.assertEqual(_qconst(power.magnitude).value, 1)
        self.assertIs(atom_prot.verb, Verb.GRANT_ABILITY)
        keyword_ability = _keyword_ability(atom_prot, "ability")
        self.assertIs(keyword_ability.keyword, Keyword.PROTECTION)
        self.assertEqual(len(keyword_ability.params), 1)
        param = keyword_ability.params[0]
        assert isinstance(param, FAtom)
        self.assertIs(param.pred, FAtomPred.SUBTYPE_EQ)
        self.assertEqual(param.string_value, "Dog")

    def test_modify_pt_other_dogs(self) -> None:
        outcome = _as_ability(
            _single_match(self.reg, "Other Dogs you control get +1/+1.").outcome
        )
        atom = _as_atom(_as_static(outcome.ability).effect)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        target = _selector(atom, "target")
        _find_atom(target.filter, FAtomPred.SUBTYPE_EQ, string_value="Dog")
        _find_atom(target.filter, FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
        _find_fnot(target.filter)
        self.assertIs(target.zone.controller, ControllerRef.YOU)
        power = _pt_delta(atom, "power")
        self.assertIs(power.direction, PtDirection.INCREASE)
        self.assertEqual(_qconst(power.magnitude).value, 1)

    def test_modify_pt_other_creatures(self) -> None:
        outcome = _as_ability(
            _single_match(self.reg, "Other creatures get -1/-1.").outcome
        )
        atom = _as_atom(_as_static(outcome.ability).effect)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        target = _selector(atom, "target")
        self.assertIs(target.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(target.zone.controller, ControllerRef.ANY)
        _find_atom(target.filter, FAtomPred.TYPE_EQ, string_value="Creature")
        _find_fnot(target.filter)
        power = _pt_delta(atom, "power")
        self.assertIs(power.direction, PtDirection.DECREASE)
        self.assertEqual(_qconst(power.magnitude).value, 1)
        toughness = _pt_delta(atom, "toughness")
        self.assertEqual(_qconst(toughness.magnitude).value, 1)

    def test_cant_block(self) -> None:
        outcome = _as_ability(_single_match(self.reg, "This creature can't block.").outcome)
        atom = _as_atom(_as_static(outcome.ability).effect)
        self.assertIs(atom.verb, Verb.PREVENT_EFFECT)
        condition = _as_fatom(_pairs(atom).get("condition"))
        self.assertIs(condition.pred, FAtomPred.IS_SOURCE)
        event = _as_blockers_event(_pairs(atom).get("event"))
        subject = _as_fatom(event.filter)
        self.assertIs(subject.pred, FAtomPred.IS_SOURCE)

    def test_modify_pt_while_garruk(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg,
                "This creature gets +2/+2 as long as you control a Garruk "
                "planeswalker.",
            ).outcome
        )
        atom = _as_atom(_as_static(outcome.ability).effect)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        target = _selector(atom, "target")
        self.assertIs(target.mode, SelectorMode.CHOOSE)
        self.assertEqual(_qconst(target.count).value, 1)
        target_filter = _as_fatom(target.filter)
        self.assertIs(target_filter.pred, FAtomPred.IS_SOURCE)
        duration = _as_duration_while(atom.args.get("duration"))
        _find_atom(
            duration.filter, FAtomPred.TYPE_EQ, string_value="Planeswalker"
        )
        _find_atom(duration.filter, FAtomPred.SUBTYPE_EQ, string_value="Garruk")
        _find_atom(duration.filter, FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
        power = _pt_delta(atom, "power")
        self.assertEqual(_qconst(power.magnitude).value, 2)

    def test_modify_pt_qprop_graveyard(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg,
                "This creature gets +X/+0, where X is the greatest power among "
                "creature cards in your graveyard.",
            ).outcome
        )
        atom = _as_atom(_as_static(outcome.ability).effect)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        power = _pt_delta(atom, "power")
        self.assertIs(power.direction, PtDirection.INCREASE)
        magnitude = _as_qprop(power.magnitude)
        self.assertIs(magnitude.field, QPropField.POWER)
        self.assertIs(magnitude.agg, QAgg.MAX)
        referent = _as_selector(magnitude.referent)
        self.assertIs(referent.zone.kind, ZoneKind.GRAVEYARD)
        self.assertIs(referent.zone.controller, ControllerRef.YOU)
        referent_filter = _as_fatom(referent.filter)
        self.assertIs(referent_filter.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(referent_filter.string_value, "Creature")
        toughness = _pt_delta(atom, "toughness")
        self.assertEqual(_qconst(toughness.magnitude).value, 0)

    def test_grant_lifelink_while_counter(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg,
                "This creature has lifelink as long as it has a +1/+1 counter "
                "on it.",
            ).outcome
        )
        atom = _as_atom(_as_static(outcome.ability).effect)
        self.assertIs(atom.verb, Verb.GRANT_ABILITY)
        keyword_ability = _keyword_ability(atom, "ability")
        self.assertIs(keyword_ability.keyword, Keyword.LIFELINK)
        target = _selector(atom, "target")
        target_filter = _as_fatom(target.filter)
        self.assertIs(target_filter.pred, FAtomPred.IS_SOURCE)
        duration = _as_duration_while(atom.args.get("duration"))
        condition = _as_fatom(duration.filter)
        self.assertIs(condition.pred, FAtomPred.HAS_COUNTER)
        self.assertIs(condition.counter_kind, CounterKind.PLUS_1_PLUS_1)
        self.assertEqual(_qconst(condition.count).value, 1)

    def test_gain_control_enchanted(self) -> None:
        outcome = _as_effect(
            _single_match(self.reg, "You control enchanted creature.").outcome
        )
        atom = _as_atom(outcome.effect)
        self.assertIs(atom.verb, Verb.GAIN_CONTROL)
        target = _selector(atom, "target")
        self.assertIs(target.mode, SelectorMode.ALL)
        self.assertIsInstance(target.count, QUnbounded)
        self.assertIs(target.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(target.zone.controller, ControllerRef.ANY)
        _find_atom(target.filter, FAtomPred.TYPE_EQ, string_value="Creature")
        _find_atom(target.filter, FAtomPred.IS_ATTACHED_TO_SOURCE)
        self.assertIs(_pairs(atom).get("controller"), ControllerRef.YOU)

    def test_draw_discard_bad_deal(self) -> None:
        outcome = _as_effect(
            _single_match(
                self.reg, "You draw two cards and each opponent discards two cards."
            ).outcome
        )
        seq = _as_seq(outcome.effect)
        self.assertEqual(len(seq.steps), 2)
        first, second = seq.steps
        assert isinstance(first, Atom)
        assert isinstance(second, Atom)
        self.assertIs(first.verb, Verb.DRAW)
        self.assertIs(_pairs(first).get("controller"), ControllerRef.YOU)
        self.assertEqual(_qconst(_pairs(first).get("amount")).value, 2)
        self.assertIs(second.verb, Verb.DISCARD)
        self.assertIs(_pairs(second).get("controller"), ControllerRef.OPPONENT)
        cards = _selector(second, "cards")
        self.assertIs(cards.mode, SelectorMode.CHOOSE)
        self.assertEqual(_qconst(cards.count).value, 2)
        self.assertEqual(cards.filter, FAnd(children=()))
        self.assertIs(cards.zone.kind, ZoneKind.HAND)
        self.assertIs(cards.zone.controller, ControllerRef.ANY)

    def test_gain_life_n(self) -> None:
        for sentence, life in (("You gain 4 life.", 4), ("You gain 3 life.", 3)):
            outcome = _as_effect(_single_match(self.reg, sentence).outcome)
            atom = _as_atom(outcome.effect)
            self.assertIs(atom.verb, Verb.GAIN_LIFE, sentence)
            self.assertIs(_pairs(atom).get("controller"), ControllerRef.YOU)
            self.assertEqual(_qconst(_pairs(atom).get("amount")).value, life, sentence)

    def test_gain_life_qcount_cats(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg, "You gain life equal to the number of Cats you control."
            ).outcome
        )
        atom = _as_atom(_as_static(outcome.ability).effect)
        self.assertIs(atom.verb, Verb.GAIN_LIFE)
        self.assertIs(_pairs(atom).get("controller"), ControllerRef.YOU)
        amount = _as_qcount(_pairs(atom).get("amount"))
        selector = amount.selector
        self.assertIs(selector.mode, SelectorMode.ALL)
        self.assertIsInstance(selector.count, QUnbounded)
        self.assertIs(selector.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(selector.zone.controller, ControllerRef.YOU)
        _find_atom(selector.filter, FAtomPred.TYPE_EQ, string_value="Creature")
        _find_atom(selector.filter, FAtomPred.SUBTYPE_EQ, string_value="Cat")
        _find_atom(selector.filter, FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)

    def test_lose_life_n(self) -> None:
        outcome = _as_effect(_single_match(self.reg, "You lose 3 life.").outcome)
        atom = _as_atom(outcome.effect)
        self.assertIs(atom.verb, Verb.LOSE_LIFE)
        self.assertIs(_pairs(atom).get("controller"), ControllerRef.YOU)
        self.assertEqual(_qconst(_pairs(atom).get("amount")).value, 3)


if __name__ == "__main__":
    unittest.main()
