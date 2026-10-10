"""Tests for B4 bucket templates (templates_b4.py).

Covers all 47 shapes in ``/tmp/opencode/phase1_buckets/B4.json``
(63 concrete sentences):
- 43 shapes template-covered (59 concrete sentences; ``This land enters
  tapped.`` carries 15) -> 43 templates
- 4 shapes UNCOVERED (5 concrete sentences; no grammar construct)

PC-3: every B4 concrete sentence fullmatches at most one template.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any

from MTG_bot.core.ability_tree import (
    QX,
    ActivatedAbility,
    ActivationWindow,
    Atom,
    ControllerRef,
    Cost,
    CostDeltaIncreaseGeneric,
    CostDeltaIncreaseLife,
    CostDeltaReduceGeneric,
    CostDeltaReduceMana,
    CostDiscard,
    CostLife,
    CostModifier,
    CounterKind,
    DeclareBlockersEvent,
    DurationEot,
    DurationWhileCondition,
    Effect,
    EtBState,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    Keyword,
    KeywordAbility,
    OptionalEffect,
    PtDelta,
    PtDirection,
    QAgg,
    QBin,
    QConst,
    QCount,
    QProp,
    QPropField,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    TargetingEvent,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    ZonePosition,
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


def _as_cost_modifier(value: object) -> CostModifier:
    if not isinstance(value, CostModifier):
        raise AssertionError(f"expected CostModifier, got {type(value).__name__}")
    return value


def _as_etb_state(value: object) -> EtBState:
    if not isinstance(value, EtBState):
        raise AssertionError(f"expected EtBState, got {type(value).__name__}")
    return value


def _as_activated(value: object) -> ActivatedAbility:
    if not isinstance(value, ActivatedAbility):
        raise AssertionError(f"expected ActivatedAbility, got {type(value).__name__}")
    return value


def _as_optional(value: object) -> OptionalEffect:
    if not isinstance(value, OptionalEffect):
        raise AssertionError(f"expected OptionalEffect, got {type(value).__name__}")
    return value


def _as_cost(value: object) -> Cost:
    if not isinstance(value, Cost):
        raise AssertionError(f"expected Cost, got {type(value).__name__}")
    return value


def _as_cost_delta(value: object) -> CostDeltaReduceGeneric:
    if not isinstance(value, CostDeltaReduceGeneric):
        raise AssertionError(
            f"expected CostDeltaReduceGeneric, got {type(value).__name__}"
        )
    return value


def _and_children(f: Filter) -> tuple[Filter, ...]:
    assert isinstance(f, FAnd), f"expected FAnd filter, got {type(f).__name__}"
    return f.children


def _find_atom(f: Filter, pred: FAtomPred, **slots: Any) -> FAtom:
    """Find an FAtom child of an FAnd with the given pred and slot values."""
    for child in _and_children(f):
        if (
            isinstance(child, FAtom)
            and child.pred is pred
            and all(getattr(child, key) == value for key, value in slots.items())
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
    "You may spend mana as though it were mana of any color.": (
        "B4-spend-any-color",
        "ability",
    ),
    "You may activate loyalty abilities of Teferi on any player's turn "
    "any time you could cast an instant.": (
        "B4-teferi-grant-activation",
        "ability",
    ),
    "You can't choose an untapped creature as this spell's target as you cast it.": (
        "B4-enthralling-target-choice",
        "ability",
    ),
    "You may cast them this turn.": (
        "B4-cast-them-this-turn",
        "ability",
    ),
    "You may look at the top card of your library any time, and you may "
    "play lands from the top of your library.": (
        "B4-look-play-top-of-library",
        "ability",
    ),
    "You may play that card until you exile another card with this enchantment.": (
        "B4-play-that-card-until",
        "ability",
    ),
    "You may play two additional lands on each of your turns.": (
        "B4-azusa-extra-land-plays",
        "ability",
    ),
    "This spell costs {X} less to cast, where X is the total amount of "
    "noncombat damage dealt to your opponents this turn.": (
        "B4-noncombat-damage-cost-modifier",
        "ability",
    ),
    "Creatures you control attack each combat if able.": (
        "B4-mandate-attack-you",
        "ability",
    ),
    "You choose a noncreature, nonland card from it.": (
        "B4-you-choose-from-it",
        "effect",
    ),
    "You have protection from the chosen card name.": (
        "B4-protection-chosen-name",
        "ability",
    ),
    "This creature gets +1/+1 until end of turn for each creature tapped this way.": (
        "B4-per-tapped-this-way",
        "effect",
    ),
    "You may reveal a creature card or Garruk planeswalker card from among them and put it into your hand.": (
        "B4-reveal-one-from-among",
        "effect",
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
    # AMENDED 2026-09-30 (round 14f): the static row joins its five sibling
    # statics as an ABILITY (raw EffectOutcome was the family's outlier;
    # on a creature it folded into the SpellAbility and ran once at cast).
    "Creatures your opponents control get -1/-0.": (
        "B4-modify-pt-static-opponents",
        "ability",
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
    "Creature spells with flying you cast cost {1} less to cast.": (
        "B4-cost-modifier-watcher",
        "ability",
    ),
    "This spell costs {X} less to cast, where X is the total power of "
    "creatures you control.": ("B4-cost-modifier-total-power", "ability"),
    "This spell costs {3} less to cast if you've gained 3 or more life this turn.": (
        "B4-cost-modifier-conditional-life",
        "ability",
    ),
    "This creature enters tapped.": ("B4-enters-tapped-creature", "ability"),
    "This land enters tapped.": ("B4-enters-tapped-land", "ability"),
    "You may cast Goblin spells from the top of your library.": (
        "B4-cast-goblin-top-library",
        "ability",
    ),
    "You may cast this card from your graveyard by paying 3 life and "
    "discarding a card in addition to paying its other costs.": (
        "B4-cast-graveyard-recost",
        "ability",
    ),
    "You may search your library and/or graveyard for a card named "
    "Basri, Devoted Paladin, reveal it, and put it into your hand.": (
        "B4-tutor-basri",
        "ability",
    ),
    "You may search your library and/or graveyard for a card named "
    "Liliana, Death Mage, reveal it, and put it into your hand.": (
        "B4-tutor-liliana",
        "ability",
    ),
    "This spell costs {2}{U} less to cast if you've cast an instant or "
    "sorcery spell this turn.": ("B4-stormwing-cost", "ability"),
    "Spells your opponents cast that target this creature cost an "
    "additional 3 life to cast.": ("B4-opponent-spell-cost-life", "ability"),
    "Spells your opponents cast that target this creature cost {3} more to cast.": (
        "B4-opponent-spell-cost-mana",
        "ability",
    ),
    "This creature can't be blocked as long as you've drawn two or more "
    "cards this turn.": ("B4-cant-be-blocked-aslong-drawn", "ability"),
    "This creature must be blocked if able.": ("B4-must-block", "ability"),
    "This creature can block only creatures with flying.": (
        "B4-block-only-flying",
        "ability",
    ),
    "This creature enters with X +1/+1 counters on it.": (
        "B4-enters-with-x-counters",
        "ability",
    ),
}


# ---------------------------------------------------------------------------
# Test: Template Inventory
# ---------------------------------------------------------------------------


class TestB4Inventory(unittest.TestCase):
    """Verify the B4 template collection is well-formed."""

    def setUp(self) -> None:
        self.data = _load_b4()

    def test_46_templates(self) -> None:
        self.assertEqual(len(templates_b4.TEMPLATES), 46)

    def test_1_uncovered(self) -> None:
        self.assertEqual(len(templates_b4.UNCOVERED), 1)

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
        self.assertEqual(len(reg), 46)

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
        self.assertEqual(covered_shapes, 46)
        self.assertEqual(matched_occurrences, 62)

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
        self.assertEqual(len(EXPECTED_KIND), 47)
        for sentence in EXPECTED_KIND:
            for entries in self.data.values():
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
                    f"fingerprint unstable for {card!r} / {shape_key!r}: {sentence!r}",
                )


# ---------------------------------------------------------------------------
# Test: IR structure — one test per template
# ---------------------------------------------------------------------------


class TestB4IrStructure(unittest.TestCase):
    def setUp(self) -> None:
        self.reg = _registry()

    def test_mandate_attack_you(self) -> None:
        atom = _as_atom(
            _effect_of(
                _single_match(
                    self.reg, "Creatures you control attack each combat if able."
                )
            )
        )
        self.assertIs(atom.verb, Verb.MANDATE_ATTACK)
        cards = _selector(atom, "cards")
        self.assertIs(cards.mode, SelectorMode.ALL)
        self.assertIsInstance(cards.count, QUnbounded)
        self.assertIs(cards.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(cards.zone.controller, ControllerRef.ANY)
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
        self.assertIs(target.zone.controller, ControllerRef.ANY)

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
        # AMENDED 2026-09-30 (round 14f): this row was the family's lone
        # outlier emitting a raw EffectOutcome, which the assembly folded
        # into the CREATURE's SpellAbility to run ONCE at cast (Waker of
        # Waves, B-11-family static miscompile). The family shape is
        # StaticAbility (all five sibling rows); the atom is unchanged.
        outcome = _as_ability(
            _single_match(
                self.reg, "Creatures your opponents control get -1/-0."
            ).outcome
        )
        atom = _as_atom(_as_static(outcome.ability).effect)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        power = _pt_delta(atom, "power")
        toughness = _pt_delta(atom, "toughness")
        self.assertIs(power.direction, PtDirection.DECREASE)
        self.assertIs(toughness.direction, PtDirection.DECREASE)
        self.assertEqual(_qconst(power.magnitude).value, 1)
        self.assertEqual(_qconst(toughness.magnitude).value, 0)
        target = _selector(atom, "target")
        self.assertIs(target.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(target.zone.controller, ControllerRef.ANY)
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
        self.assertIs(target.zone.controller, ControllerRef.ANY)
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
        self.assertIs(target.zone.controller, ControllerRef.ANY)
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
        outcome = _as_ability(
            _single_match(self.reg, "This creature can't block.").outcome
        )
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
        _find_atom(duration.filter, FAtomPred.TYPE_EQ, string_value="Planeswalker")
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
                "This creature has lifelink as long as it has a +1/+1 counter on it.",
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
        # T4 P1a: the discard shape is the merged MOVE_ZONE atom — the
        # discarding opponent's own hand and graveyard.
        self.assertIs(second.verb, Verb.MOVE_ZONE)
        self.assertIs(_pairs(second).get("controller"), ControllerRef.OPPONENT)
        self.assertEqual(
            _pairs(second).get("destination"),
            Zone(ZoneKind.GRAVEYARD, ControllerRef.OPPONENT),
        )
        self.assertEqual(
            _pairs(second).get("from"), Zone(ZoneKind.HAND, ControllerRef.OPPONENT)
        )
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
        self.assertIs(selector.zone.controller, ControllerRef.ANY)
        _find_atom(selector.filter, FAtomPred.TYPE_EQ, string_value="Creature")
        _find_atom(selector.filter, FAtomPred.SUBTYPE_EQ, string_value="Cat")
        _find_atom(selector.filter, FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)

    def test_lose_life_n(self) -> None:
        outcome = _as_effect(_single_match(self.reg, "You lose 3 life.").outcome)
        atom = _as_atom(outcome.effect)
        self.assertIs(atom.verb, Verb.LOSE_LIFE)
        self.assertIs(_pairs(atom).get("controller"), ControllerRef.YOU)
        self.assertEqual(_qconst(_pairs(atom).get("amount")).value, 3)

    # ------------------------------------------------------------------
    # Cost modifiers
    # ------------------------------------------------------------------

    def test_cost_modifier_watcher(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg,
                "Creature spells with flying you cast cost {1} less to cast.",
            ).outcome
        )
        modifier = _as_cost_modifier(outcome.ability)
        self.assertIs(modifier.controller_ref, ControllerRef.YOU)
        delta = _as_cost_delta(modifier.delta)
        self.assertIsInstance(delta, CostDeltaReduceGeneric)
        self.assertEqual(_qconst(delta.amount).value, 1)
        _find_atom(modifier.filter, FAtomPred.TYPE_EQ, string_value="Creature")
        kw = _find_atom(modifier.filter, FAtomPred.KEYWORD_HAS)
        self.assertIs(kw.keyword, Keyword.FLYING)

    def test_cost_modifier_total_power(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg,
                "This spell costs {X} less to cast, where X is the total "
                "power of creatures you control.",
            ).outcome
        )
        modifier = _as_cost_modifier(outcome.ability)
        self.assertIs(modifier.controller_ref, ControllerRef.YOU)
        delta = _as_cost_delta(modifier.delta)
        self.assertIsInstance(delta, CostDeltaReduceGeneric)
        qprop = _as_qprop(delta.amount)
        self.assertIs(qprop.field, QPropField.POWER)
        self.assertIs(qprop.agg, QAgg.SUM)
        referent = _as_selector(qprop.referent)
        self.assertIs(referent.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(referent.zone.controller, ControllerRef.ANY)
        _find_atom(referent.filter, FAtomPred.TYPE_EQ, string_value="Creature")
        _find_atom(referent.filter, FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
        # filter is IS_SOURCE
        filter_atom = _as_fatom(modifier.filter)
        self.assertIs(filter_atom.pred, FAtomPred.IS_SOURCE)

    def test_cost_modifier_conditional_life(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg,
                "This spell costs {3} less to cast if you've gained 3 or "
                "more life this turn.",
            ).outcome
        )
        modifier = _as_cost_modifier(outcome.ability)
        self.assertIs(modifier.controller_ref, ControllerRef.YOU)
        delta = _as_cost_delta(modifier.delta)
        self.assertIsInstance(delta, CostDeltaReduceGeneric)
        self.assertEqual(_qconst(delta.amount).value, 3)
        condition = _as_fatom(modifier.condition)
        self.assertIs(condition.pred, FAtomPred.LIFE_GAINED_THIS_TURN_GE)
        self.assertEqual(_qconst(condition.count).value, 3)
        self.assertIs(condition.who, ControllerRef.YOU)
        filter_atom = _as_fatom(modifier.filter)
        self.assertIs(filter_atom.pred, FAtomPred.IS_SOURCE)

    def test_cost_modifier_stormwing_compound(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg,
                "This spell costs {2}{U} less to cast if you've cast an "
                "instant or sorcery spell this turn.",
            ).outcome
        )
        modifier = _as_cost_modifier(outcome.ability)
        self.assertIs(modifier.controller_ref, ControllerRef.YOU)
        delta = _as_cost_delta(modifier.delta)
        self.assertIsInstance(delta, CostDeltaReduceGeneric)
        self.assertEqual(_qconst(delta.amount).value, 2)
        self.assertEqual(
            modifier.extra_deltas,
            (CostDeltaReduceMana(color="U", amount=QConst(1)),),
        )
        condition = _as_fatom(modifier.condition)
        self.assertIs(condition.pred, FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN)
        self.assertIs(condition.who, ControllerRef.YOU)
        filter_atom = _as_fatom(modifier.filter)
        self.assertIs(filter_atom.pred, FAtomPred.IS_SOURCE)

    def test_cost_modifier_opponent_life(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg,
                "Spells your opponents cast that target this creature "
                "cost an additional 3 life to cast.",
            ).outcome
        )
        modifier = _as_cost_modifier(outcome.ability)
        self.assertIs(modifier.controller_ref, ControllerRef.OPPONENT)
        delta = modifier.delta
        if not isinstance(delta, CostDeltaIncreaseLife):
            self.fail(f"expected CostDeltaIncreaseLife, got {type(delta).__name__}")
        self.assertEqual(_qconst(delta.amount).value, 3)
        self.assertIsNone(modifier.condition)
        filter_atom = _as_fatom(modifier.filter)
        self.assertIs(filter_atom.pred, FAtomPred.TARGETS_SOURCE)

    def test_cost_modifier_opponent_generic(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg,
                "Spells your opponents cast that target this creature "
                "cost {3} more to cast.",
            ).outcome
        )
        modifier = _as_cost_modifier(outcome.ability)
        self.assertIs(modifier.controller_ref, ControllerRef.OPPONENT)
        delta = modifier.delta
        if not isinstance(delta, CostDeltaIncreaseGeneric):
            self.fail(f"expected CostDeltaIncreaseGeneric, got {type(delta).__name__}")
        self.assertEqual(_qconst(delta.amount).value, 3)
        self.assertIsNone(modifier.condition)
        filter_atom = _as_fatom(modifier.filter)
        self.assertIs(filter_atom.pred, FAtomPred.TARGETS_SOURCE)

    # ------------------------------------------------------------------
    # ETB state
    # ------------------------------------------------------------------

    def test_enters_tapped_creature(self) -> None:
        outcome = _as_ability(
            _single_match(self.reg, "This creature enters tapped.").outcome
        )
        etb = _as_etb_state(outcome.ability)
        self.assertTrue(etb.tapped)
        self.assertEqual(etb.initial_counters, ())

    def test_enters_tapped_land(self) -> None:
        outcome = _as_ability(
            _single_match(self.reg, "This land enters tapped.").outcome
        )
        etb = _as_etb_state(outcome.ability)
        self.assertTrue(etb.tapped)
        self.assertEqual(etb.initial_counters, ())

    # ------------------------------------------------------------------
    # Activated abilities — cast from zone
    # ------------------------------------------------------------------

    def test_cast_goblin_top_library(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg, "You may cast Goblin spells from the top of your library."
            ).outcome
        )
        ability = _as_activated(outcome.ability)
        self.assertEqual(ability.cost.parts, ())
        optional = _as_optional(ability.effect)
        atom = _as_atom(optional.inner)
        self.assertIs(atom.verb, Verb.CAST)
        source = _selector(atom, "source")
        self.assertIs(source.zone.kind, ZoneKind.LIBRARY)
        self.assertIs(source.zone.controller, ControllerRef.YOU)
        self.assertIs(source.zone.position, ZonePosition.TOP)
        self.assertIsInstance(source.count, QUnbounded)
        self.assertIs(source.mode, SelectorMode.CHOOSE)
        _find_atom(source.filter, FAtomPred.TYPE_EQ, string_value="Creature")
        _find_atom(source.filter, FAtomPred.SUBTYPE_EQ, string_value="Goblin")

    def test_cast_graveyard_recost(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg,
                "You may cast this card from your graveyard by paying 3 life "
                "and discarding a card in addition to paying its other costs.",
            ).outcome
        )
        ability = _as_activated(outcome.ability)
        cost = ability.cost
        self.assertEqual(len(cost.parts), 2)
        life_part = cost.parts[0]
        assert isinstance(life_part, CostLife)
        self.assertEqual(_qconst(life_part.amount).value, 3)
        discard_part = cost.parts[1]
        assert isinstance(discard_part, CostDiscard)
        discard_target = discard_part.target
        self.assertIs(discard_target.zone.kind, ZoneKind.HAND)
        self.assertIs(discard_target.zone.controller, ControllerRef.YOU)
        self.assertEqual(_qconst(discard_target.count).value, 1)
        self.assertEqual(discard_target.filter, FAnd(children=()))
        optional = _as_optional(ability.effect)
        atom = _as_atom(optional.inner)
        self.assertIs(atom.verb, Verb.CAST)
        source = _selector(atom, "source")
        self.assertIs(source.zone.kind, ZoneKind.GRAVEYARD)
        self.assertIs(source.zone.controller, ControllerRef.YOU)
        self.assertEqual(_qconst(source.count).value, 1)
        source_filter = _as_fatom(source.filter)
        self.assertIs(source_filter.pred, FAtomPred.IS_SOURCE)

    # ------------------------------------------------------------------
    # Tutor (name-specific search)
    # ------------------------------------------------------------------

    def test_tutor_basri(self) -> None:
        self._assert_tutor_structure(
            "You may search your library and/or graveyard for a card named "
            "Basri, Devoted Paladin, reveal it, and put it into your hand.",
            "Basri, Devoted Paladin",
        )

    def test_tutor_liliana(self) -> None:
        self._assert_tutor_structure(
            "You may search your library and/or graveyard for a card named "
            "Liliana, Death Mage, reveal it, and put it into your hand.",
            "Liliana, Death Mage",
        )

    def _assert_tutor_structure(self, sentence: str, card_name: str) -> None:
        outcome = _as_ability(_single_match(self.reg, sentence).outcome)
        ability = _as_activated(outcome.ability)
        self.assertEqual(ability.cost.parts, ())
        optional = _as_optional(ability.effect)
        seq = _as_seq(optional.inner)
        self.assertEqual(len(seq.steps), 3)
        search_atom, reveal_atom, move_atom = seq.steps
        assert isinstance(search_atom, Atom)
        assert isinstance(reveal_atom, Atom)
        assert isinstance(move_atom, Atom)
        # SEARCH
        self.assertIs(search_atom.verb, Verb.SEARCH)
        cards = _selector(search_atom, "cards")
        self.assertEqual(_qconst(cards.count).value, 1)
        self.assertIs(cards.mode, SelectorMode.CHOOSE)
        name_atom = _as_fatom(cards.filter)
        self.assertIs(name_atom.pred, FAtomPred.NAME_EQ)
        self.assertEqual(name_atom.string_value, card_name)
        self.assertIs(cards.zone.kind, ZoneKind.LIBRARY)
        self.assertIs(cards.zone.controller, ControllerRef.YOU)
        self.assertEqual(len(cards.zones), 1)
        self.assertIs(cards.zones[0].kind, ZoneKind.GRAVEYARD)
        self.assertIs(cards.zones[0].controller, ControllerRef.YOU)
        dest = search_atom.args.get("destination")
        assert isinstance(dest, Zone)
        self.assertIs(dest.kind, ZoneKind.HAND)
        self.assertIs(dest.controller, ControllerRef.YOU)
        # REVEAL
        self.assertIs(reveal_atom.verb, Verb.REVEAL)
        self.assertIs(_pairs(reveal_atom).get("controller"), ControllerRef.YOU)
        self.assertEqual(_qconst(_pairs(reveal_atom).get("count")).value, 1)
        # MOVE_ZONE
        self.assertIs(move_atom.verb, Verb.MOVE_ZONE)
        move_dest = move_atom.args.get("destination")
        assert isinstance(move_dest, Zone)
        self.assertIs(move_dest.kind, ZoneKind.HAND)
        self.assertIs(move_dest.controller, ControllerRef.YOU)

    # ------------------------------------------------------------------
    # Round-6 batch: blocked-side restrictions, MANDATE_BLOCK, ETB X-counters
    # ------------------------------------------------------------------

    def test_cant_be_blocked_aslong_drawn(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg,
                "This creature can't be blocked as long as you've drawn "
                "two or more cards this turn.",
            ).outcome
        )
        static = _as_static(outcome.ability)
        # C9: the turn-scoped condition is StaticAbility.condition.
        drawn = _as_fatom(static.condition)
        self.assertIs(drawn.pred, FAtomPred.CARDS_DRAWN_THIS_TURN_GE)
        self.assertEqual(_qconst(drawn.count).value, 2)
        self.assertIs(drawn.who, ControllerRef.YOU)
        atom = _as_atom(static.effect)
        self.assertIs(atom.verb, Verb.PREVENT_EFFECT)
        condition = _as_fatom(atom.args.get("condition"))
        self.assertIs(condition.pred, FAtomPred.IS_SOURCE)
        event = _as_blockers_event(atom.args.get("event"))
        self.assertIsNone(event.subject)
        self.assertEqual(event.filter, FAnd(children=()))
        blocked = _as_fatom(event.blocked)
        self.assertIs(blocked.pred, FAtomPred.IS_SOURCE)
        self.assertNotIn("duration", _pairs(atom))

    def test_must_block(self) -> None:
        outcome = _as_ability(
            _single_match(self.reg, "This creature must be blocked if able.").outcome
        )
        atom = _as_atom(_as_static(outcome.ability).effect)
        self.assertIs(atom.verb, Verb.MANDATE_BLOCK)
        cards = _selector(atom, "cards")
        self.assertIs(cards.mode, SelectorMode.CHOOSE)
        self.assertEqual(_qconst(cards.count).value, 1)
        self.assertIs(cards.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(cards.zone.controller, ControllerRef.ANY)
        self.assertIs(_as_fatom(cards.filter).pred, FAtomPred.IS_SOURCE)
        self.assertNotIn("controller", _pairs(atom))

    def test_block_only_flying(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg, "This creature can block only creatures with flying."
            ).outcome
        )
        static = _as_static(outcome.ability)
        self.assertIsNone(static.condition)
        atom = _as_atom(static.effect)
        self.assertIs(atom.verb, Verb.PREVENT_EFFECT)
        condition = _as_fatom(atom.args.get("condition"))
        self.assertIs(condition.pred, FAtomPred.IS_SOURCE)
        event = _as_blockers_event(atom.args.get("event"))
        self.assertEqual(event.filter, FAnd(children=()))
        subject = _as_fatom(event.subject)
        self.assertIs(subject.pred, FAtomPred.IS_SOURCE)
        blocked_filter = event.blocked
        assert isinstance(blocked_filter, FNot), (
            f"expected FNot blocked filter, got {type(blocked_filter).__name__}"
        )
        inner = blocked_filter.inner
        assert isinstance(inner, FAtom)
        self.assertIs(inner.pred, FAtomPred.KEYWORD_HAS)
        self.assertIs(inner.keyword, Keyword.FLYING)

    def test_enters_with_x_counters(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg, "This creature enters with X +1/+1 counters on it."
            ).outcome
        )
        ability = outcome.ability
        assert isinstance(ability, TriggeredAbility), (
            f"expected TriggeredAbility, got {type(ability).__name__}"
        )
        self.assertIsNone(ability.condition)
        event = ability.event
        assert isinstance(event, ZoneChangeEvent), (
            f"expected ZoneChangeEvent, got {type(event).__name__}"
        )
        self.assertIs(event.from_zone.kind, ZoneKind.ANY)
        self.assertIs(event.to_zone.kind, ZoneKind.BATTLEFIELD)
        assert event.subject is not None
        self.assertIs(_as_fatom(event.subject).pred, FAtomPred.IS_SOURCE)
        atom = _as_atom(ability.effect)
        self.assertIs(atom.verb, Verb.PUT_COUNTER)
        target = _selector(atom, "target")
        # Convention C2: referent selector — CHOOSE + QConst(1) + neutral zone.
        self.assertEqual(target.referent, "event")
        self.assertIs(target.mode, SelectorMode.CHOOSE)
        self.assertEqual(_qconst(target.count).value, 1)
        self.assertIs(target.zone.kind, ZoneKind.ANY)
        self.assertEqual(target.filter, FAnd(children=()))
        self.assertIs(_pairs(atom).get("counter_kind"), CounterKind.PLUS_1_PLUS_1)
        self.assertIsInstance(_pairs(atom).get("count"), QX)


class TestB4Round7AnaphoraIr(unittest.TestCase):
    """Round-7 batch decision-surface assertions (doc 2026-09-28/03 §3)."""

    def setUp(self) -> None:
        self.reg = _registry()

    def test_you_choose_from_it(self) -> None:
        outcome = _as_effect(
            _single_match(
                self.reg, "You choose a noncreature, nonland card from it."
            ).outcome
        )
        atom = _as_atom(outcome.effect)
        self.assertIs(atom.verb, Verb.CHOOSE)
        pool = _selector(atom, "target")
        self.assertIs(pool.mode, SelectorMode.ALL)
        self.assertIsInstance(pool.count, QUnbounded)
        self.assertIs(pool.zone.kind, ZoneKind.HAND)
        self.assertIs(pool.zone.controller, ControllerRef.TARGET_PLAYER)
        self.assertEqual(_pairs(atom).get("count"), QConst(1))
        assert isinstance(pool.filter, FAnd)
        negs = [child for child in pool.filter.children if isinstance(child, FNot)]
        self.assertEqual(len(negs), 2)

    def test_protection_chosen_name(self) -> None:
        outcome = _as_ability(
            _single_match(
                self.reg, "You have protection from the chosen card name."
            ).outcome
        )
        static = _as_static(outcome.ability)
        atom = _as_atom(static.effect)
        self.assertIs(atom.verb, Verb.GRANT_ABILITY)
        ka = _keyword_ability(atom, "ability")
        self.assertIs(ka.keyword, Keyword.PROTECTION)
        (param,) = ka.params
        assert isinstance(param, FAtom)
        self.assertIs(param.pred, FAtomPred.NAME_CHOSEN)
        target = _selector(atom, "target")
        self.assertIs(target.zone.kind, ZoneKind.PLAYER)

    def test_per_tapped_this_way(self) -> None:
        outcome = _as_effect(
            _single_match(
                self.reg,
                "This creature gets +1/+1 until end of turn for each "
                "creature tapped this way.",
            ).outcome
        )
        atom = _as_atom(outcome.effect)
        power = _pt_delta(atom, "power")
        assert isinstance(power.magnitude, QBin)
        prop = power.magnitude.right
        assert isinstance(prop, QProp)
        self.assertIs(prop.field, QPropField.THIS_WAY_COUNT)
        self.assertEqual(prop.referent, "event")
        self.assertIsInstance(atom.args.get("duration"), DurationEot)

    def test_reveal_one_from_among(self) -> None:
        outcome = _as_effect(
            _single_match(
                self.reg,
                "You may reveal a creature card or Garruk planeswalker card "
                "from among them and put it into your hand.",
            ).outcome
        )
        opt = outcome.effect
        assert isinstance(opt, OptionalEffect)
        seq = _as_seq(opt.inner)
        reveal = _as_atom(seq.steps[0])
        self.assertIs(reveal.verb, Verb.REVEAL)
        move = _as_atom(seq.steps[1])
        self.assertIs(move.verb, Verb.MOVE_ZONE)
        cards = _selector(move, "cards")
        self.assertIs(cards.mode, SelectorMode.ONE_OF)
        self.assertIsInstance(cards.count, QConst)
        self.assertIs(cards.zone.kind, ZoneKind.LIBRARY)
        self.assertIs(cards.zone.position, ZonePosition.TOP)


class TestB4Round9B(unittest.TestCase):
    """Round 9-B (doc 2026-09-28/11 §9-B rows 7-9): MANA_POLICY flooding,
    GRANT_ACTIVATION Teferi window, Enthralling targeting legality."""

    def setUp(self) -> None:
        self.reg = _registry()

    def test_spend_any_color(self) -> None:
        """MANA_POLICY scope "ALL_YOURS" closed string (C21), under an
        OptionalEffect (C15 may) inside a StaticAbility (permanent by
        construction — MANA_POLICY has no duration role)."""
        outcome = _single_match(
            self.reg,
            "You may spend mana as though it were mana of any color.",
        ).outcome
        static = _as_static(_as_ability(outcome).ability)
        opt = _as_optional(static.effect)
        atom = _as_atom(opt.inner)
        self.assertIs(atom.verb, Verb.MANA_POLICY)
        self.assertEqual(_pairs(atom), {"scope": "ALL_YOURS"})

    def test_tefei_grant_activation(self) -> None:
        """GRANT_ACTIVATION (R9-7): holder gate FAnd(Planeswalker,
        NAME_CONTAINS Teferi); window = INSTANT verbatim from "any time you
        could cast an instant" (NOT the r10 fixture's SORCERY example)."""
        outcome = _single_match(
            self.reg,
            "You may activate loyalty abilities of Teferi on any player's "
            "turn any time you could cast an instant.",
        ).outcome
        static = _as_static(_as_ability(outcome).ability)
        opt = _as_optional(static.effect)
        atom = _as_atom(opt.inner)
        self.assertIs(atom.verb, Verb.GRANT_ACTIVATION)
        holder = atom.args.get("filter")
        assert isinstance(holder, FAnd)
        type_a, name_a = holder.children
        assert isinstance(type_a, FAtom) and isinstance(name_a, FAtom)
        self.assertIs(type_a.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(type_a.string_value, "Planeswalker")
        self.assertIs(name_a.pred, FAtomPred.NAME_CONTAINS)
        self.assertEqual(name_a.string_value, "Teferi")
        self.assertIs(atom.args.get("window"), ActivationWindow.INSTANT)

    def test_enthralling_target_choice(self) -> None:
        """PREVENT_EFFECT (C11-class): condition IS_ANY_TARGET spell-scope
        (b3/Subira idiom), event TargetingEvent over FAnd(Creature,
        IS_UNTAPPED)."""
        outcome = _single_match(
            self.reg,
            "You can't choose an untapped creature as this spell's target "
            "as you cast it.",
        ).outcome
        static = _as_static(_as_ability(outcome).ability)
        atom = _as_atom(static.effect)
        self.assertIs(atom.verb, Verb.PREVENT_EFFECT)
        cond = atom.args.get("condition")
        assert isinstance(cond, FAtom)
        self.assertIs(cond.pred, FAtomPred.IS_ANY_TARGET)
        event = atom.args.get("event")
        assert isinstance(event, TargetingEvent)
        filt = event.filter
        assert isinstance(filt, FAnd)
        type_a, untapped = filt.children
        assert isinstance(type_a, FAtom) and isinstance(untapped, FAtom)
        self.assertIs(type_a.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(type_a.string_value, "Creature")
        self.assertIs(untapped.pred, FAtomPred.IS_UNTAPPED)


if __name__ == "__main__":
    unittest.main()
