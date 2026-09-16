"""Tests for the B3 activated-ability template bucket."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    Atom,
    Choose,
    CostManaColor,
    CostManaGeneric,
    CostPart,
    CostTap,
    ControllerRef,
    CounterKind,
    DurationEot,
    Keyword,
    KeywordAbility,
    PtDelta,
    PtDirection,
    QAgg,
    QConst,
    QCount,
    QProp,
    QPropField,
    Selector,
    SelectorMode,
    Seq,
    TokenSpec,
    Verb,
    ZoneKind,
    canonical_json,
    fingerprint,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    Match,
    TemplateRegistry,
)
from MTG_bot.core.compiler import templates_b3

_B3_PATH = Path("/tmp/opencode/phase1_buckets/B3.json")


def _load_b3() -> dict[str, tuple[tuple[str, str], ...]]:
    raw: dict[str, list[list[str]]] = json.loads(_B3_PATH.read_text())
    return {
        shape_key: tuple((entry[0], entry[1]) for entry in entries)
        for shape_key, entries in raw.items()
    }


def _registry() -> TemplateRegistry:
    reg = TemplateRegistry()
    for template in templates_b3.TEMPLATES:
        reg.register(template)
    return reg


def _single_match(reg: TemplateRegistry, sentence: str) -> Match:
    matches = reg.match(sentence)
    assert len(matches) == 1, (
        f"expected exactly one match for {sentence!r}, got {len(matches)}"
    )
    return matches[0]


def _ability(match: Match) -> ActivatedAbility:
    outcome = match.outcome
    assert isinstance(outcome, AbilityOutcome), (
        f"expected AbilityOutcome, got {type(outcome).__name__}"
    )
    ability = outcome.ability
    assert isinstance(ability, ActivatedAbility), (
        f"expected ActivatedAbility, got {type(ability).__name__}"
    )
    return ability


def _atom(ability: ActivatedAbility) -> Atom:
    effect = ability.effect
    assert isinstance(effect, Atom), f"expected Atom, got {type(effect).__name__}"
    return effect


def _selector(atom: Atom, role: str) -> Selector:
    value = atom.args.get(role)
    assert isinstance(value, Selector), (
        f"role {role!r} expected Selector, got {type(value).__name__}"
    )
    return value


def _qconst(atom: Atom, role: str) -> QConst:
    value = atom.args.get(role)
    assert isinstance(value, QConst), (
        f"role {role!r} expected QConst, got {type(value).__name__}"
    )
    return value


def _keyword_ability(atom: Atom, role: str) -> KeywordAbility:
    value = atom.args.get(role)
    assert isinstance(value, KeywordAbility), (
        f"role {role!r} expected KeywordAbility, got {type(value).__name__}"
    )
    return value


def _cost_parts(ability: ActivatedAbility) -> tuple[CostPart, ...]:
    return ability.cost.parts


class TestB3Coverage(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _load_b3()
        self.reg = _registry()

    def test_bucket_file_has_48_shapes_and_55_occurrences(self) -> None:
        self.assertEqual(len(self.data), 48)
        total = sum(len(entries) for entries in self.data.values())
        self.assertEqual(total, 55)

    def test_public_api_counts(self) -> None:
        self.assertEqual(len(templates_b3.TEMPLATES), 23)
        self.assertEqual(len(templates_b3.UNCOVERED), 7)

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
        self.assertEqual(covered_shapes, 41)
        self.assertEqual(matched_occurrences, 48)

    def test_uncovered_shapes_are_exactly_the_unmatched_shapes(self) -> None:
        unmatched: set[str] = set()
        for shape_key, entries in self.data.items():
            if not any(self.reg.match(sentence) for _card, sentence in entries):
                unmatched.add(shape_key)
        declared = {shape_key for shape_key, _reason in templates_b3.UNCOVERED}
        self.assertEqual(unmatched, declared)

    def test_uncovered_sentences_do_not_match(self) -> None:
        for shape_key, _reason in templates_b3.UNCOVERED:
            self.assertIn(shape_key, self.data)
            for _card, sentence in self.data[shape_key]:
                self.assertEqual(self.reg.match(sentence), (), sentence)

    def test_pc3_ambiguity_is_zero(self) -> None:
        for shape_key, entries in self.data.items():
            for card, sentence in entries:
                matches = self.reg.match(sentence)
                if not matches:
                    continue
                canonicals = {canonical_json(_ability(match)) for match in matches}
                self.assertEqual(
                    len(canonicals),
                    1,
                    f"PC-3 ambiguity for {card!r} / {shape_key!r}: {sentence!r}",
                )

    def test_fingerprint_is_stable(self) -> None:
        for shape_key, entries in self.data.items():
            for card, sentence in entries:
                matches = self.reg.match(sentence)
                if not matches:
                    continue
                first = fingerprint(_ability(matches[0]))
                rematch = self.reg.match(sentence)
                self.assertTrue(rematch, sentence)
                second = fingerprint(_ability(rematch[0]))
                self.assertEqual(
                    first,
                    second,
                    f"fingerprint unstable for {card!r} / {shape_key!r}: {sentence!r}",
                )


class TestB3CostParsing(unittest.TestCase):
    def setUp(self) -> None:
        self.reg = _registry()

    def test_tap_cost(self) -> None:
        ability = _ability(_single_match(self.reg, "{T}: Add {G}."))
        self.assertEqual(_cost_parts(ability), (CostTap(),))

    def test_generic_cost(self) -> None:
        ability = _ability(_single_match(self.reg, "{2}: Add one mana of any color."))
        self.assertEqual(_cost_parts(ability), (CostManaGeneric(QConst(2)),))

    def test_color_cost(self) -> None:
        ability = _ability(_single_match(self.reg, "{R}: This creature gets +1/+0 until end of turn."))
        self.assertEqual(_cost_parts(ability), (CostManaColor("R", QConst(1)),))

    def test_mixed_cost_preserves_order(self) -> None:
        ability = _ability(
            _single_match(self.reg, "{1}{B}, {T}: Each opponent loses 2 life.")
        )
        self.assertEqual(
            _cost_parts(ability),
            (
                CostManaGeneric(QConst(1)),
                CostManaColor("B", QConst(1)),
                CostTap(),
            ),
        )

    def test_multi_symbol_cost_preserves_order(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "{4}{R}{G}: Radha gets +X/+X until end of turn, "
                "where X is the number of lands you control.",
            )
        )
        self.assertEqual(
            _cost_parts(ability),
            (
                CostManaGeneric(QConst(4)),
                CostManaColor("R", QConst(1)),
                CostManaColor("G", QConst(1)),
            ),
        )


class TestB3EffectStructure(unittest.TestCase):
    def setUp(self) -> None:
        self.reg = _registry()

    def test_grant_keyword_to_self_until_eot(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "{B}: This creature gains deathtouch until end of turn.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.GRANT_ABILITY)
        target = _selector(atom, "target")
        self.assertIs(target.mode, SelectorMode.ALL)
        self.assertIs(target.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(target.zone.controller, ControllerRef.YOU)
        keyword_ability = _keyword_ability(atom, "ability")
        self.assertIs(keyword_ability.keyword, Keyword.DEATHTOUCH)
        duration = atom.args.get("duration")
        assert isinstance(duration, DurationEot)

    def test_modify_pt_self_uses_increasing_deltas(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "{R}: This creature gets +1/+0 until end of turn.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        power = atom.args.get("power")
        toughness = atom.args.get("toughness")
        assert isinstance(power, PtDelta)
        assert isinstance(toughness, PtDelta)
        self.assertIs(power.direction, PtDirection.INCREASE)
        self.assertIs(toughness.direction, PtDirection.INCREASE)
        power_mag = power.magnitude
        toughness_mag = toughness.magnitude
        assert isinstance(power_mag, QConst)
        assert isinstance(toughness_mag, QConst)
        self.assertEqual(power_mag.value, 1)
        self.assertEqual(toughness_mag.value, 0)

    def test_radha_uses_qcount_of_lands_you_control(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "{4}{R}{G}: Radha gets +X/+X until end of turn, "
                "where X is the number of lands you control.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        power = atom.args.get("power")
        assert isinstance(power, PtDelta)
        self.assertIsInstance(power.magnitude, QCount)

    def test_jolrael_uses_controller_hand_size_property(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "{4}{G}{G}: Until end of turn, creatures you control have "
                "base power and toughness X/X, where X is the number of cards "
                "in your hand.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.SET_PT)
        power = atom.args.get("power")
        toughness = atom.args.get("toughness")
        assert isinstance(power, QProp)
        assert isinstance(toughness, QProp)
        self.assertEqual(power, toughness)
        self.assertEqual(power.referent, "controller")
        self.assertIs(power.field, QPropField.CARDS_IN_HAND)
        self.assertIs(power.agg, QAgg.FIRST)

    def test_rin_and_seri_uses_qcount_of_dogs_you_control(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "{R}{G}{W}, {T}: Rin and Seri deals damage to any target "
                "equal to the number of Dogs you control.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.DEAL_DAMAGE)
        amount = atom.args.get("amount")
        self.assertIsInstance(amount, QCount)

    def test_lose_life_targets_each_opponent(self) -> None:
        ability = _ability(
            _single_match(self.reg, "{1}{B}, {T}: Each opponent loses 2 life.")
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.LOSE_LIFE)
        controller = atom.args.get("controller")
        self.assertIs(controller, ControllerRef.ALL_OPPONENTS)
        self.assertEqual(_qconst(atom, "amount").value, 2)

    def test_put_counter_uses_plus_one_plus_one_counter(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "{4}{W}{W}, {T}: Put a +1/+1 counter on target creature.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.PUT_COUNTER)
        counter_kind = atom.args.get("counter_kind")
        self.assertIs(counter_kind, CounterKind.PLUS_1_PLUS_1)
        self.assertEqual(_qconst(atom, "count").value, 1)

    def test_draw_then_discard_is_a_sequence(self) -> None:
        ability = _ability(
            _single_match(self.reg, "{T}: Draw a card, then discard a card.")
        )
        effect = ability.effect
        assert isinstance(effect, Seq)
        self.assertEqual(len(effect.steps), 2)
        first, second = effect.steps
        assert isinstance(first, Atom)
        assert isinstance(second, Atom)
        self.assertIs(first.verb, Verb.DRAW)
        self.assertIs(second.verb, Verb.DISCARD)

    def test_scry_uses_constant_count(self) -> None:
        ability = _ability(_single_match(self.reg, "{2}{U}: Scry 1."))
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.SCRY)
        controller = atom.args.get("controller")
        self.assertIs(controller, ControllerRef.YOU)
        self.assertEqual(_qconst(atom, "count").value, 1)

    def test_add_mana_single_color(self) -> None:
        ability = _ability(_single_match(self.reg, "{T}: Add {G}."))
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.ADD_MANA)
        color = atom.args.get("color")
        self.assertEqual(color, "G")
        self.assertEqual(_qconst(atom, "amount").value, 1)

    def test_add_mana_colorless_counts_repeated_c_symbols(self) -> None:
        ability = _ability(
            _single_match(self.reg, "{T}: Add {C}{C}{C}{C}{C}.")
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.ADD_MANA)
        color = atom.args.get("color")
        self.assertEqual(color, "C")
        self.assertEqual(_qconst(atom, "amount").value, 5)

    def test_add_mana_choose_is_a_choose_effect(self) -> None:
        ability = _ability(_single_match(self.reg, "{T}: Add {B} or {G}."))
        effect = ability.effect
        assert isinstance(effect, Choose)
        count = effect.count
        assert isinstance(count, QConst)
        self.assertEqual(count.value, 1)
        self.assertEqual(len(effect.options), 2)
        first, second = effect.options
        assert isinstance(first, Atom)
        assert isinstance(second, Atom)
        self.assertIs(first.verb, Verb.ADD_MANA)
        self.assertIs(second.verb, Verb.ADD_MANA)
        self.assertEqual(first.args.get("color"), "B")
        self.assertEqual(second.args.get("color"), "G")

    def test_add_mana_any_color_uses_colorless_marker(self) -> None:
        ability = _ability(
            _single_match(self.reg, "{T}: Add one mana of any color.")
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.ADD_MANA)
        color = atom.args.get("color")
        self.assertEqual(color, "C")
        self.assertEqual(_qconst(atom, "amount").value, 1)

    def test_create_token_builds_flying_angel_token(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "{T}: Create a 4/4 white Angel creature token with flying.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.CREATE_TOKEN)
        token = atom.args.get("tokens")
        assert isinstance(token, TokenSpec)
        self.assertEqual(token.name, "Angel")
        self.assertEqual(token.type_line, "Angel")
        self.assertEqual(token.types, ("Creature",))
        self.assertEqual(token.subtypes, ("Angel",))
        power = token.power
        toughness = token.toughness
        assert isinstance(power, QConst)
        assert isinstance(toughness, QConst)
        self.assertEqual(power.value, 4)
        self.assertEqual(toughness.value, 4)
        self.assertEqual(token.keywords, (Keyword.FLYING,))
        self.assertEqual(_qconst(atom, "count").value, 1)


if __name__ == "__main__":
    unittest.main()
