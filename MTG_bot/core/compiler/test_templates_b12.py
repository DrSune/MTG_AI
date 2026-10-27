"""Bucket B12 and Step 2c (sets round S-3a, KNOWLEDGE /167): a spell's own name as the subject.

Three properties are pinned:
1. identity law: each B12 builder makes exactly the IR of the card that already carries the meaning;
2. the fallback reaches cards that matched nothing (Lava Axe, Incinerate's first sentence) and only
   with the card's own name standing alone;
3. a card whose sentences all compiled before is untouched, over every card of M21, ZNR, M20, KHM.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from MTG_bot.core.compiler import templates_b6
from MTG_bot.core.compiler.compiler import _self_named_sentence, compile_card
from MTG_bot.core.compiler.coverage import _BUCKET_MODULES, build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.compiler.templates import EffectOutcome, TemplateRegistry

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="module")
def registry():
    return build_full_registry()


@pytest.fixture(scope="module")
def without_b12():
    registry = TemplateRegistry()
    for module in _BUCKET_MODULES:
        if module.__name__.endswith("templates_b12"):
            continue
        for template in module.TEMPLATES:
            registry.register(template)
    return registry


def _only(registry, sentence: str, bucket: str | None = None):
    matches = [m for m in registry.match(sentence) if bucket is None or m.template.bucket == bucket]
    assert matches, sentence
    return matches[0]


@pytest.mark.parametrize(
    ("carrier", "self_named"),
    [
        ("Shock deals 2 damage to any target.", "~ deals 2 damage to any target."),
        ("Volcanic Geyser deals X damage to any target.", "~ deals X damage to any target."),
        ("Turn to Slag deals 5 damage to target creature.", "~ deals 5 damage to target creature."),
    ],
)
def test_b12_builds_the_existing_carriers_ir(registry, carrier, self_named) -> None:
    old = _only(registry, carrier)
    new = _only(registry, self_named, "B12")
    assert old.template.bucket != "B12"
    assert repr(new.outcome) == repr(old.outcome)


def test_player_or_planeswalker_damage_is_the_activated_carriers_effect(registry) -> None:
    old = _only(registry, "{T}: This creature deals 1 damage to target player or planeswalker.")
    new = _only(registry, "~ deals 1 damage to target player or planeswalker.", "B12")
    assert repr(new.outcome.effect) == repr(old.outcome.ability.effect)


def test_each_creature_damage_is_the_b6_atom_with_n(registry) -> None:
    new = _only(registry, "~ deals 2 damage to each creature.", "B12")
    assert repr(new.outcome) == repr(EffectOutcome(effect=templates_b6._deals_2_each_creature()))


def _by_name(set_code: str) -> dict:
    return {raw.identity.name: raw for raw in ingest_pool(DATA / f"{set_code}.json").values()}


def test_the_fallback_compiles_spells_that_name_themselves(registry) -> None:
    tenth = _by_name("10E")
    lava_axe = compile_card(tenth["Lava Axe"], registry)
    assert not lava_axe.unparsed
    incinerate = compile_card(tenth["Incinerate"], registry)
    assert [s for s, _ in incinerate.unparsed] == [
        "A creature dealt damage this way can't be regenerated this turn."
    ]


def test_the_own_name_must_stand_alone() -> None:
    def raw(name: str):
        identity = type("Identity", (), {"name": name})()
        return type("Raw", (), {"identity": identity})()

    assert _self_named_sentence("Shock deals 2 damage to any target.", raw("Shock")) == (
        "~ deals 2 damage to any target."
    )
    assert _self_named_sentence("Shockwave deals 2 damage.", raw("Shock")) is None
    assert _self_named_sentence("Fire-Shock deals 2 damage.", raw("Shock")) is None
    # a legendary card is also named by the part before its comma; split cards by their face
    assert _self_named_sentence("Exile Ral.", raw("Ral, Storm Conduit")) == "Exile ~."
    assert _self_named_sentence("Fire deals 2 damage.", raw("Fire // Ice")) == "~ deals 2 damage."
    assert _self_named_sentence("Draw a card.", raw("Opt")) is None


@pytest.mark.parametrize("set_code", ["M21", "ZNR", "M20", "KHM"])
def test_cards_that_compiled_before_are_untouched(registry, without_b12, set_code) -> None:
    changed, reached = [], []
    for raw in ingest_pool(DATA / f"{set_code}.json").values():
        try:
            before = compile_card(raw, without_b12)
        except Exception:  # noqa: BLE001, S112 - a card that cannot compile is outside this property
            continue
        after = compile_card(raw, registry)
        if repr(after.card) == repr(before.card) and after.unparsed == before.unparsed:
            continue
        changed.append(raw.identity.name)
        # Step 2c only re-reads an unparsed sentence that names the card
        assert any(_self_named_sentence(s, raw) for s, _ in before.unparsed), raw.identity.name
        reached.append(raw.identity.name)
    if set_code == "M21":
        assert changed == []  # M21 compiles fully, so nothing can reach Step 2c
    assert changed == reached
