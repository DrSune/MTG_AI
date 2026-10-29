"""Bucket B11 (general clauses): same IR as the specific carriers, more sentences, no crashes."""

from __future__ import annotations

from pathlib import Path

import pytest

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    ActivationWindow,
    Atom,
    ControllerRef,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    Keyword,
    QConst,
    Selector,
    Verb,
    walk,
)
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.errors import StateCorruptionError

DATA = Path(__file__).resolve().parents[2] / "data"
SETS = ("M21", "ZNR", "M20", "KHM")


@pytest.fixture(scope="module")
def registry():
    return build_full_registry()


@pytest.fixture(scope="module")
def sentences():
    out = []
    for code in SETS:
        for raw in ingest_pool(DATA / f"{code}.json").values():
            faces = raw.back_face.sentences if raw.back_face else ()
            out.extend((code, s) for s in (*raw.sentences, *faces))
    return out


def test_where_a_specific_template_also_matches_the_ir_is_identical(registry, sentences):
    # The identity law (DESIGN_ATOM_ONTOLOGY §6): one meaning, one IR. 52 overlaps on 2026-10-27.
    overlaps, differ = 0, []
    for code, sentence in sentences:
        matches = registry.match(sentence)
        general = [m for m in matches if m.template.bucket == "B11"]
        specific = [m for m in matches if m.template.bucket != "B11"]
        if general and specific:
            overlaps += 1
            differ += [(code, sentence) for g in general for s in specific
                       if g.outcome != s.outcome]
    assert differ == []
    assert overlaps >= 50


def test_the_general_clauses_add_coverage_on_every_set(registry, sentences):
    only = {code: 0 for code in SETS}
    for code, sentence in sentences:
        matches = registry.match(sentence)
        if matches and all(m.template.bucket == "B11" for m in matches):
            only[code] += 1
    # 2026-10-27: KHM 26, M20 11, ZNR 14, M21 0 (M21 was already fully compiled).
    assert only["KHM"] >= 20 and only["M20"] >= 10 and only["ZNR"] >= 10


def test_no_set_crashes_the_compiler(registry) -> None:
    # Only the honest refusal (a shape gap) may stop a card; anything else is a template bug that
    # takes a whole set down (B-36..B-38).
    for code in SETS:
        for raw in ingest_pool(DATA / f"{code}.json").values():
            try:
                compile_card(raw, registry)
            except StateCorruptionError:
                pass


def _one(registry, sentence: str):
    matches = [m for m in registry.match(sentence) if m.template.bucket == "B11"]
    assert len(matches) == 1, sentence
    return matches[0].outcome


def _filter_of(outcome):
    selectors = [v for n in walk(outcome.effect) if isinstance(n, Atom)
                 for _, v in n.args.pairs if isinstance(v, Selector)]
    return selectors[0].filter


def test_the_noun_phrase_composes(registry) -> None:
    f = _filter_of(_one(registry, "Destroy target artifact or enchantment you don't control."))
    assert f == FAnd(children=(
        FOr(children=(FAtom(pred=FAtomPred.TYPE_EQ, string_value="Artifact"),
                      FAtom(pred=FAtomPred.TYPE_EQ, string_value="Enchantment"))),
        FNot(inner=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)),
    ))
    # Either suffix order lands on the same filter.
    a = _filter_of(_one(registry, "Exile target creature an opponent controls with flying."))
    b = _filter_of(_one(registry, "Exile target creature with flying an opponent controls."))
    assert a == b
    power = _filter_of(_one(registry, "Destroy target creature with power 3 or less."))
    assert FAtom(pred=FAtomPred.POWER_LE, count=QConst(3)) in power.children


def test_a_phrase_outside_the_grammar_is_left_unparsed(registry) -> None:
    for sentence in (
        "Destroy target creature with decayed.",       # not a bare keyword
        "Destroy target tribal or kindred.",           # not a card type this grammar knows
        "Create a 2/2 black Zombie creature token with decayed.",
        "Enchanted creature gets +2/+2 and has ward {2}.",
    ):
        assert [m for m in registry.match(sentence) if m.template.bucket == "B11"] == []


def test_tokens_are_named_by_their_subtypes(registry) -> None:
    effect = _one(registry, "Create two 4/4 white Angel Warrior creature tokens with flying.").effect
    pairs = dict(effect.args.pairs)
    assert effect.verb is Verb.CREATE_TOKEN and pairs["count"] == QConst(2)
    spec = pairs["tokens"]
    assert (spec.name, spec.type_line, spec.color) == (
        "Angel Warrior", "Creature — Angel Warrior", "W")
    assert spec.keywords == (Keyword.FLYING,)


def test_attached_statics_grant_keywords_in_printed_order(registry) -> None:
    ability = _one(registry, "Equipped creature gets +1/+1 and has vigilance and trample.").ability
    verbs = [n.verb for n in walk(ability) if isinstance(n, Atom)]
    assert verbs == [Verb.MODIFY_PT, Verb.GRANT_ABILITY, Verb.GRANT_ABILITY]


def test_bare_equip_is_sorcery_speed(registry) -> None:
    # B-60 (2026-10-29): CR 702.6a, equip is activated only as a sorcery
    # even when the card omits the reminder text that spells it out.
    ability = _one(registry, "Equip {2}").ability
    assert isinstance(ability, ActivatedAbility)
    assert ability.timing is ActivationWindow.SORCERY
