"""T3 round 3 — ``SpellAbility.effect`` becomes optional.

Round-3 scope:

- ``SpellAbility.effect`` is now ``Effect | None = None``.  An effect-less
  ``SpellAbility`` carries only ``additional_costs`` — the grammar shape of
  a castable card whose only relevant sentence is "As an additional cost
  to cast this spell, ..." (M21 Goremand, Sparkhunter Masticore).
- Serialization: ``_SPECS`` slot ``opt:effect``; ``to_dict`` omits the
  ``"effect"`` key when effect is ``None`` (via ``_OMIT_IF_EMPTY``);
  ``from_dict`` injects ``None`` when the key is absent.
- Byte stability: every pre-round-3 tree (all goldens carry a non-None
  effect) serializes identically — the four pinned fingerprints below were
  captured BEFORE the edit and must stay byte-identical.

Guards:
- the four pre-round-3 ``SpellAbility`` fingerprint pins stay byte-identical;
- pre-round-3 trees still serialize the ``"effect"`` key;
- effect-less constructs round-trip and omit ``"effect"`` while keeping
  ``"additional_costs"``;
- rejections at the widened entry point (non-Effect effect values, bad
  effect tags / payloads in ``from_dict``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

import MTG_bot.core.ability_tree as at
import MTG_bot.core.test_ability_tree_t3r2 as T2

# ---- effect-less SpellAbility builders (new in round 3) -------------------

_CARD = at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Card")
_CREATURE = at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature")
_BF_YOU = at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU)
_HAND_YOU = at.Zone(at.ZoneKind.HAND, at.ControllerRef.YOU)
_CREATURE_BF = at.Selector(at.QConst(1), at.SelectorMode.TARGET, _CREATURE, zones=(_BF_YOU,))
_CARD_HAND = at.Selector(at.QConst(1), at.SelectorMode.CHOOSE, _CARD, zones=(_HAND_YOU,))


def _spell_effectless_sacrifice() -> at.SpellAbility:
    """Effect-less creature spell with a sacrifice additional cost."""
    return at.SpellAbility(
        at.SpellKind.CREATURE,
        None,
        additional_costs=(at.Cost(parts=(at.CostSacrifice(_CREATURE_BF),)),),
    )


def _spell_effectless_discard() -> at.SpellAbility:
    """Effect-less creature spell with a discard additional cost."""
    return at.SpellAbility(
        at.SpellKind.CREATURE,
        None,
        additional_costs=(at.Cost(parts=(at.CostDiscard(_CARD_HAND),)),),
    )


def _spell_effectless_bare() -> at.SpellAbility:
    """Effect-less, cost-less spell — the minimum representable form."""
    return at.SpellAbility(at.SpellKind.CREATURE, None)


def _spell_explicit_none() -> at.SpellAbility:
    return at.SpellAbility(at.SpellKind.CREATURE, None)


# ---- pinned pre-round-3 fingerprints (captured before any round-3 edit) ---

_PINNED: list[tuple[str, Callable[[], object], str]] = [
    (
        "spell_instant_draw_nocost",
        T2._spell_base,
        "e4d6897f8542141dc66d4d2ca1356746d99bf5587535a78019b952619570905d",
    ),
    (
        "spell_creature_draw_nocost",
        lambda: at.SpellAbility(at.SpellKind.CREATURE, T2._draw_one()),
        "47279b0494954e142776afb42e40ea65bf078ea145345c15d8f07417c502eb99",
    ),
    (
        "spell_sacrifice_cost",
        T2._spell_additional_sacrifice,
        "db2ea464ce21b9130c49b1a5d951b3a6603d26776e68d2ac1a7abfca241edd6f",
    ),
    (
        "spell_discard_life_costs",
        T2._spell_additional_discard_life,
        "93dc3f1d9c8261245ee01a3ae2d050540faecd15ef31d87ae3036e0e1a373892",
    ),
]

# Round-3 constructs, pinned after the edit (byte-identity for future rounds).
_NEW_PINS: list[tuple[str, Callable[[], at.SpellAbility], str]] = [
    (
        "spell_effectless_sacrifice",
        _spell_effectless_sacrifice,
        "03fcfd65c7965d2f460fd2004ed79545d7ede188f5b4b1982866731d99bcb769",
    ),
    (
        "spell_effectless_discard",
        _spell_effectless_discard,
        "4d64a329dac8c1cefa56342225013c76b2a2efbfdecf78f69924a844a695123f",
    ),
    (
        "spell_effectless_bare",
        _spell_effectless_bare,
        "4ab74b3cff39541af5ef554a5ffefdc68e1a506645aeb726b800c03eadb120b8",
    ),
]


def _assert_effect_key_present(d: Any, path: str = "root") -> None:
    """Recursively assert every SpellAbility in a pre-round-3 tree keeps 'effect'."""
    if not isinstance(d, dict):
        return
    if d.get("tag") == "SpellAbility":
        assert "effect" in d, f"pre-round-3 SpellAbility at {path} lost 'effect'"
    for value in d.values():
        _assert_effect_key_present(
            value, f"{path}.{value if isinstance(value, str) else 'x'}"
        )


# ---- tests ----------------------------------------------------------------


@pytest.mark.parametrize("name,build,fp", _PINNED, ids=[n for n, _, _ in _PINNED])
def test_pinned_pre_r3_fingerprint(
    name: str, build: Callable[[], object], fp: str
) -> None:
    node = build()
    assert at.fingerprint(node) == fp
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d
    _assert_effect_key_present(d)


@pytest.mark.parametrize("name,build,fp", _NEW_PINS, ids=[n for n, _, _ in _NEW_PINS])
def test_effectless_roundtrip(
    name: str, build: Callable[[], at.SpellAbility], fp: str
) -> None:
    node = build()
    d = at.to_dict(node)
    assert isinstance(d, dict) and d["tag"] == "SpellAbility"
    assert "effect" not in d, f"{name}: to_dict must omit the 'effect' key"
    back = at.from_dict("SpellAbility", d)
    assert back == node, f"{name}: from_dict(to_dict(x)) != x"
    assert at.canonical_json(back) == at.canonical_json(node)
    assert at.fingerprint(back) == at.fingerprint(node) == fp


def test_effectless_keeps_additional_costs() -> None:
    d = at.to_dict(_spell_effectless_sacrifice())
    assert "additional_costs" in d
    assert len(d["additional_costs"]) == 1
    assert d["additional_costs"][0]["tag"] == "Cost"
    # The bare form serializes to tag + kind only.
    bare = at.to_dict(_spell_effectless_bare())
    assert sorted(bare.keys()) == ["kind", "tag"]
    assert bare["kind"]["name"] == "CREATURE"


def test_explicit_none_equals_default() -> None:
    explicit = at.SpellAbility(at.SpellKind.CREATURE, None)
    default = at.SpellAbility(at.SpellKind.CREATURE)
    assert explicit == default
    assert at.to_dict(explicit) == at.to_dict(default)
    assert at.fingerprint(explicit) == at.fingerprint(default)
    back = at.from_dict("SpellAbility", at.to_dict(default))
    assert back.effect is None
    assert back.additional_costs == ()


def test_prer3_trees_still_serialize_effect() -> None:
    for build in (
        T2._spell_base,
        T2._spell_additional_sacrifice,
        T2._spell_additional_discard_life,
    ):
        d = at.to_dict(build())
        assert "effect" in d, f"{build.__name__} lost its 'effect' key"
        assert isinstance(d["effect"], dict)


def test_from_dict_missing_effect_defaults_none() -> None:
    d: dict[str, Any] = {
        "tag": "SpellAbility",
        "kind": {"tag": "SpellKind", "name": "CREATURE"},
    }
    back = at.from_dict("SpellAbility", d)
    assert back.effect is None
    assert back.additional_costs == ()
    assert back == at.SpellAbility(at.SpellKind.CREATURE)


def _rejection_cases() -> list[tuple[str, Callable[[], object]]]:
    return [
        (
            "spell_str_effect",
            lambda: at.SpellAbility(at.SpellKind.INSTANT, "Draw a card"),  # type: ignore[arg-type]
        ),
        (
            "spell_cost_effect",
            lambda: at.SpellAbility(
                at.SpellKind.INSTANT,
                at.Cost(parts=(at.CostLife(at.QConst(1)),)),  # type: ignore[arg-type]
            ),
        ),
        (
            "from_dict_bad_effect_tag",
            lambda: at.from_dict(
                "SpellAbility",
                {
                    "tag": "SpellAbility",
                    "kind": {"tag": "SpellKind", "name": "INSTANT"},
                    "effect": {"tag": "Cost", "parts": []},
                },
            ),
        ),
        (
            "from_dict_non_dict_effect",
            lambda: at.from_dict(
                "SpellAbility",
                {
                    "tag": "SpellAbility",
                    "kind": {"tag": "SpellKind", "name": "INSTANT"},
                    "effect": 7,  # type: ignore[dict-item]
                },
            ),
        ),
    ]


@pytest.mark.parametrize(
    "name,fn", _rejection_cases(), ids=[n for n, _ in _rejection_cases()]
)
def test_r3_rejections(name: str, fn: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        fn()
