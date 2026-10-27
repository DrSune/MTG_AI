"""Grammar round S-1 (KNOWLEDGE /159): what first touch on M20 and KHM broke, pinned.

Each crash took down a whole set's compile, not one card: B-36 a template pattern that outran its
builder, B-37 vehicles, B-38 a back-face planeswalker's emblem, B-39 token printings in ingest.
The keyword-line fallback (B-41) only moves sentences out of the unparsed register; it never
changes a compiled tree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from MTG_bot.core.ability_tree import Keyword
from MTG_bot.core.compiler.compiler import _is_keyword_line, compile_card, compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry, measure_pool
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.compiler.test_ingest import ORACLE_A, _card
from MTG_bot.core.errors import StateCorruptionError

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(scope="module")
def registry():
    return build_full_registry()


def _by_name(set_code: str) -> dict:
    return {raw.identity.name: raw for raw in ingest_pool(DATA / f"{set_code}.json").values()}


def test_the_keyword_grant_pattern_cannot_outrun_its_builder(registry) -> None:
    # B-36: "[a-z]+" matched "haste", which _KW_MAP lacks -> KeyError -> whole-set crash.
    unknown = "{1}{R}, {T}: Target creature gains haste until end of turn."
    assert [m.template.tid for m in registry.match(unknown)
            if m.template.tid.startswith("B3-grant-kw")] == []
    known = "{1}{R}, {T}: Target creature gains flying until end of turn."
    assert any(m.template.tid == "B3-grant-kw-target-creature" for m in registry.match(known))
    # The card that crashed KHM now compiles, its unmapped grant honestly unparsed.
    result = compile_card(_by_name("KHM")["Axgard Cavalry"], registry)
    assert [s for s, _ in result.unparsed] == [
        "{T}: Target creature gains haste until end of turn."
    ]


def test_a_vehicle_is_an_honest_refusal_not_a_value_error(registry) -> None:
    # B-37: printed P/T on a non-creature artifact; crew is not implemented.
    with pytest.raises(StateCorruptionError, match="Vehicle"):
        compile_card(_by_name("KHM")["Raiders' Karve"], registry)


def test_an_emblem_whose_planeswalker_is_a_back_face_stays_an_orphan(registry) -> None:
    # B-38: Valki, God of Lies is a creature; Tibalt (the back face) owns the emblem.
    pool = ingest_pool(DATA / "KHM.json")
    names = {"Valki, God of Lies // Tibalt, Cosmic Impostor", "Tibalt, Cosmic Impostor Emblem",
             "Tyvar Kell", "Tyvar Kell Emblem"}
    compiled = compile_pool(
        {oid: raw for oid, raw in pool.items() if raw.identity.name in names}, registry
    )
    valki = next(r.card for r in compiled.results.values()
                 if r.card.name.startswith("Valki, God of Lies"))
    assert valki.emblem is None
    tyvar = next(r.card for r in compiled.results.values() if r.card.name == "Tyvar Kell")
    assert tyvar.emblem is not None  # a front-face planeswalker still carries its emblem
    measure_pool(pool, registry, "KHM")  # and the whole-set measurement no longer raises


def test_token_printings_that_differ_only_in_their_creators_merge(tmp_path) -> None:
    # B-39: ELD's four Food printings list different reverseRelated cards.
    token = {"text": "{2}, {T}, Sacrifice this token: You gain 3 life.", "types": ("Artifact",),
             "subtypes": ("Food",), "colors": (), "mana_cost": None, "mana_value": 0.0,
             "power": None, "toughness": None, "layout": "token"}
    first = _card(ORACLE_A, "Food", related_cards={"reverseRelated": ["Bake into a Pie"]},
                  uuid="00000000-0000-4000-8000-00000000000a", **token)
    second = _card(ORACLE_A, "Food", related_cards={"reverseRelated": ["Gilded Goose"]},
                   uuid="00000000-0000-4000-8000-00000000000b", **token)
    path = tmp_path / "pool.json"
    path.write_text(json.dumps({"data": {"cards": [], "tokens": [first, second]}}))
    pool = ingest_pool(path)
    assert len(pool) == 1
    assert next(iter(pool.values())).related_names == ("Bake into a Pie", "Gilded Goose")
    # A real difference in a captured field is still corruption.
    third = _card(ORACLE_A, "Food", related_cards={"reverseRelated": ["Gilded Goose"]},
                  **{**token, "text": "{T}: You gain 1 life."})
    path.write_text(json.dumps({"data": {"cards": [], "tokens": [first, third]}}))
    with pytest.raises(StateCorruptionError, match="two different cards"):
        ingest_pool(path)


@pytest.mark.parametrize(
    ("line", "keywords", "expected"),
    [
        ("Flying, haste", ("Flying", "Haste"), True),
        ("Deathtouch, lifelink", ("Deathtouch", "Lifelink"), True),
        ("Flying (This creature can't be blocked except by creatures with flying or reach.)",
         ("Flying",), True),
        (("First strike (This creature deals combat damage before creatures without first "
          "strike.)"), ("First strike",), True),
        ("Flying, haste", ("Flying",), False),  # a keyword the identity does not carry
        ("Changeling (This card is every creature type.)", ("Changeling",), False),  # unbuilt
        ("Protection from black", ("Protection",), False),  # needs a parameter
        ("Scry 2.", ("Scry",), False),
    ],
)
def test_a_keyword_line_needs_every_keyword_carried_and_buildable(line, keywords, expected):
    raw = type("Raw", (), {"keywords": keywords})()
    assert _is_keyword_line(line, raw) is expected


def test_keyword_lines_leave_the_tree_alone_and_the_register(registry) -> None:
    # The abilities come from identity keywords either way; only the register changes.
    for set_code, name in (("ZNR", "Kaza, Roil Chaser"), ("M20", "Volcanic Dragon")):
        result = compile_card(_by_name(set_code)[name], registry)
        assert "Flying, haste" not in [s for s, _ in result.unparsed]
        assert {Keyword.FLYING, Keyword.HASTE} <= {k.keyword for k in result.card.keywords}
