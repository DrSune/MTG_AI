"""The printed wordings of hexproof on a player and of the reveal-until dig (templates_b16).

Pinned:
1. "You have hexproof." is Runed Halo's player grant with the HEXPROOF keyword (one selector for
   the player you); "You and permanents you control gain hexproof [from A and from B] until end
   of turn." is one grant lasting the turn over {the battlefield, you}, filtered to what you
   control, the quality an FOr of COLOR_HAS (Sporeweb Weaver's "hexproof from blue");
2. the dig: REVEAL with ``until`` (Transmogrify's, by you), then "that card" to your hand and the
   rest of the window to the bottom (Garruk's Harbinger's "the rest" move);
3. whole cards: Veil of Summer and Teyo, the Shieldmage compile whole; Vivien, Nature's Avenger's
   −1 composes through the loyalty frame with the dig's tail;
4. fallback only: on M21, ZNR, M20, FDN and WAR, a card no B16 sentence is printed on keeps its
   tree, and M21 and ZNR change nowhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    ControllerRef,
    CostLoyalty,
    DurationEot,
    FAtom,
    FAtomPred,
    FOr,
    Keyword,
    KeywordAbility,
    QConst,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    StaticAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler import templates_b16
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.compiler.templates import AbilityOutcome, EffectOutcome, TemplateRegistry

DATA = Path(__file__).resolve().parents[2] / "data"
NEW = {t.tid for t in templates_b16.TEMPLATES}
YOU = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
DIG = (
    "Reveal cards from the top of your library until you reveal a creature card.",
    "Put that card into your hand and the rest on the bottom of your library in a random order.",
)


@pytest.fixture(scope="module")
def registry() -> TemplateRegistry:
    return build_full_registry()


def only(registry: TemplateRegistry, sentence: str):
    matches = registry.match(sentence)
    assert len(matches) == 1, [m.template.tid for m in matches]
    return matches[0].outcome


def card(code: str, name: str):
    (raw,) = [r for r in ingest_pool(DATA / f"{code}.json").values() if r.identity.name == name]
    return raw


# ---------------------------------------------------------------------- 1 hexproof on a player


def test_you_have_hexproof_is_the_halos_player_grant(registry) -> None:
    outcome = only(registry, "You have hexproof.")
    assert isinstance(outcome, AbilityOutcome) and isinstance(outcome.ability, StaticAbility)
    grant = outcome.ability.effect
    assert grant.verb is Verb.GRANT_ABILITY
    assert grant.args.get("ability") == KeywordAbility(keyword=Keyword.HEXPROOF)
    halo = only(registry, "You have protection from the chosen card name.")
    assert grant.args.get("target") == halo.ability.effect.args.get("target")  # one "you"


@pytest.mark.parametrize("quality", ["", " from blue and from black"])
def test_you_and_permanents_you_control_gain_hexproof(registry, quality) -> None:
    outcome = only(
        registry, f"You and permanents you control gain hexproof{quality} until end of turn."
    )
    assert isinstance(outcome, EffectOutcome)
    grant = outcome.effect
    assert grant.verb is Verb.GRANT_ABILITY and grant.args.get("duration") == DurationEot()
    assert grant.args.get("target") == Selector(
        QUnbounded(), SelectorMode.ALL, YOU,
        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY), Zone(ZoneKind.PLAYER, ControllerRef.YOU)),
    )
    params = ()
    if quality:
        params = (FOr((FAtom(pred=FAtomPred.COLOR_HAS, color="U"),
                       FAtom(pred=FAtomPred.COLOR_HAS, color="B"))),)
    assert grant.args.get("ability") == KeywordAbility(keyword=Keyword.HEXPROOF, params=params)


# ------------------------------------------------------------------------------ 2 the dig


def test_the_reveal_is_transmogrifys_by_you(registry) -> None:
    mine = only(registry, DIG[0]).effect
    theirs = only(
        registry,
        "That creature's controller reveals cards from the top of their library until they "
        "reveal a creature card.",
    ).effect
    assert mine.verb is theirs.verb is Verb.REVEAL
    assert mine.args.get("controller") is ControllerRef.YOU
    for role in ("count", "until"):
        assert mine.args.get(role) == theirs.args.get(role)


def test_that_card_to_hand_and_the_rest_to_the_bottom(registry) -> None:
    to_hand, rest = only(registry, DIG[1]).effect.steps
    assert to_hand.verb is Verb.MOVE_ZONE and to_hand.args.get("cards").referent == "result"
    assert to_hand.args.get("destination") == Zone(ZoneKind.HAND, ControllerRef.YOU)
    harbinger_rest = only(registry, "Put the rest on the bottom of your library in a random order.")
    assert rest == harbinger_rest.effect


# ---------------------------------------------------------------------------- 3 whole cards


def test_veil_of_summer_compiles_whole(registry) -> None:
    result = compile_card(card("M20", "Veil of Summer"), registry)
    assert not result.unparsed
    (spell,) = result.card.abilities
    assert isinstance(spell, SpellAbility)
    assert [type(s).__name__ for s in spell.effect.steps] == ["Conditional", "Atom", "Atom"]
    assert spell.effect.steps[2].verb is Verb.GRANT_ABILITY


def test_teyo_compiles_whole(registry) -> None:
    result = compile_card(card("WAR", "Teyo, the Shieldmage"), registry)
    assert not result.unparsed
    assert isinstance(result.card.abilities[0], StaticAbility)


def test_viviens_minus_one_composes_with_the_tail(registry) -> None:
    result = compile_card(card("M20", "Vivien, Nature's Avenger"), registry)
    (minus_one,) = [a for a in result.card.abilities if isinstance(a, ActivatedAbility)]
    assert minus_one.cost.parts == (CostLoyalty(delta=-1),)
    assert minus_one.effect == Seq((only(registry, DIG[0]).effect, only(registry, DIG[1]).effect))
    assert len(result.unparsed) == 2  # the +1 and the -6: the record maps them


# ---------------------------------------------------------------------------- 4 fallback


@pytest.mark.parametrize("set_code", ["M21", "ZNR", "M20", "FDN", "WAR"])
def test_cards_without_a_b16_sentence_are_untouched(registry, set_code) -> None:
    without = TemplateRegistry()
    for template in registry.all():
        if template.tid not in NEW:
            without.register(template)
    changed = []
    for raw in ingest_pool(DATA / f"{set_code}.json").values():
        try:
            before = compile_card(raw, without)
        except Exception:  # noqa: BLE001, S112 - a card that cannot compile is outside this property
            continue
        after = compile_card(raw, registry)
        if repr(after.card) == repr(before.card) and after.unparsed == before.unparsed:
            continue
        changed.append(raw.identity.name)
        assert before.unparsed, raw.identity.name
    expected = {
        "M21": [], "ZNR": [],
        "M20": ["Leyline of Sanctity", "Veil of Summer", "Vivien, Nature's Avenger"],
        "FDN": ["Crystal Barricade"],
        "WAR": ["Lazotep Plating", "Teyo, the Shieldmage"],
    }
    assert sorted(changed) == expected[set_code]


def test_b16_registers_its_templates() -> None:
    assert NEW == {
        "B16-you-have-hexproof",
        "B16-you-and-permanents-gain-hexproof",
        "B16-reveal-until-creature",
        "B16-that-card-to-hand-rest-bottom",
    }
