"""The wordings ontology round R12 reads (KNOWLEDGE/2026-11-17/210 I1, I9): each fails on the code
before the round, which has no template for it.

- conditions.py: counts of your permanents and zones, a creature with power N or greater, the
  total power of your creatures, the starting life total, an opponent's graveyard, and the ability
  words in front (threshold, ferocious, formidable, spell mastery);
- B11: "with toughness|mana value N or less|greater" beside power, one form with the specific
  templates (Eliminate's noun phrase is B11's);
- B13: "Whenever you cast a spell that targets this creature|a creature you control";
- B4: "Spells your opponents cast that target a creature or planeswalker you control cost {N}
  more to cast." (Kasmina);
- B3: "Draw a card for each different mana value among nonland permanents you control."
"""

from __future__ import annotations

import pytest

from MTG_bot.core.ability_tree import (
    CastSpellEvent,
    ControllerRef,
    CostModifier,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    QAgg,
    QBin,
    QBinOp,
    QConst,
    QDistinct,
    QProp,
    QPropField,
    SpellAbility,
    StaticAbility,
    TriggeredAbility,
    Zone,
    ZoneKind,
    at_least,
    at_most,
    number_in,
    number_you_control,
)
from MTG_bot.core.compiler import conditions
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.compiler.templates import TemplateRegistry
from MTG_bot.core.compiler.test_templates_b11 import _filter_of, _one

DATA = __import__("pathlib").Path(__file__).resolve().parents[2] / "data"
CREATURE = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
YOURS = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
START = conditions.STARTING_LIFE


@pytest.fixture(scope="module")
def registry() -> TemplateRegistry:
    return build_full_registry()


def _type(name: str) -> FAtom:
    return FAtom(pred=FAtomPred.TYPE_EQ, string_value=name)


@pytest.mark.parametrize(("phrase", "expected"), [
    ("there are seven or more cards in your graveyard",
     at_least(7, quantity=number_in(Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)))),
    ("there are two or more instant and/or sorcery cards in your graveyard",
     at_least(2, quantity=number_in(Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                                    FOr((_type("Instant"), _type("Sorcery")))))),
    ("an opponent has eight or more cards in their graveyard",
     at_least(8, quantity=number_in(Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)),
              who=ControllerRef.OPPONENT)),
    ("you have four or more cards in hand",
     at_least(4, quantity=number_in(Zone(ZoneKind.HAND, ControllerRef.YOU)))),
    ("you control six or more lands", at_least(6, quantity=number_you_control(_type("Land")))),
    ("you control a creature with power 4 or greater",
     at_least(1, quantity=number_you_control(FAnd((CREATURE, at_least(4, field=QPropField.POWER)))))),
    ("you control another creature with power 4 or greater",
     at_least(1, quantity=number_you_control(FAnd((CREATURE, at_least(4, field=QPropField.POWER),
                                                   FNot(FAtom(pred=FAtomPred.IS_SOURCE))))))),
    ("creatures you control have total power 8 or greater",
     at_least(8, quantity=QProp(referent=number_you_control(CREATURE).selector,
                                field=QPropField.POWER, agg=QAgg.SUM))),
    ("your life total is greater than your starting life total",
     at_least(QBin(QBinOp.ADD, START, QConst(1)), quantity=conditions.LIFE)),
    ("your life total is greater than or equal to your starting life total",
     at_least(START, quantity=conditions.LIFE)),
    ("your life total is less than your starting life total",
     FNot(at_least(START, quantity=conditions.LIFE))),
    ("your life total is at least 10 greater than your starting life total",
     at_least(QBin(QBinOp.ADD, START, QConst(10)), quantity=conditions.LIFE)),
    ("you have at least 15 life more than your starting life total", conditions.life_over_start(15)),
])
def test_the_comparison_phrases(phrase, expected) -> None:
    assert conditions.condition(phrase) == expected


def test_b11_compares_toughness_and_mana_value(registry) -> None:
    tough = _filter_of(_one(registry, "Destroy target creature with toughness 4 or greater."))
    assert at_least(4, field=QPropField.TOUGHNESS) in tough.children
    cheap = _filter_of(_one(registry, "Exile target creature with mana value 3 or less."))
    assert at_most(3, field=QPropField.MANA_VALUE) in cheap.children


def _card(code: str, name: str, registry: TemplateRegistry):
    raw = next(rc for rc in ingest_pool(DATA / f"{code}.json").values() if rc.identity.name == name)
    result = compile_card(raw, registry)
    assert not result.unparsed, result.unparsed
    return result.card


def test_cards_the_round_compiles(registry) -> None:
    hero = _card("THB", "Hero of the Pride", registry)
    trigger = next(a for a in hero.abilities if isinstance(a, TriggeredAbility))
    assert trigger.event == CastSpellEvent(
        filter=FAtom(pred=FAtomPred.TARGETS, inner_filter=FAtom(pred=FAtomPred.IS_SOURCE)),
        actor=YOURS)
    wolverine = _card("IKO", "Spelleater Wolverine", registry)
    static = next(a for a in wolverine.abilities if isinstance(a, StaticAbility))
    assert static.condition == at_least(3, quantity=number_in(
        Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU), FOr((_type("Instant"), _type("Sorcery")))))
    rogue = _card("ZNR", "Nimana Skitter-Sneak", registry)
    static = next(a for a in rogue.abilities if isinstance(a, StaticAbility))
    assert static.condition.who is ControllerRef.OPPONENT
    insight = _card("FDN", "Lunar Insight", registry)
    spell = next(a for a in insight.abilities if isinstance(a, SpellAbility))
    amount = spell.effect.args.get("amount")
    assert isinstance(amount, QDistinct) and amount.field is QPropField.MANA_VALUE


def test_kasmina_taxes_spells_at_your_creatures_and_planeswalkers(registry) -> None:
    [match] = registry.match("Spells your opponents cast that target a creature or planeswalker you "
                             "control cost {2} more to cast.")
    modifier = match.outcome.ability
    assert isinstance(modifier, CostModifier)
    assert modifier.filter == FAtom(pred=FAtomPred.TARGETS, inner_filter=FAnd(
        (FOr((CREATURE, _type("Planeswalker"))), YOURS)))
