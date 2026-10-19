"""T3 round 4 — six additive grammar items (2026-09-24).

Round-4 scope (spec: KNOWLEDGE/2026-09-24/02-grammar-round3-decision.md):

- R3-1: ``StaticAbility.condition: Filter | None = None`` — scopes WHEN a
  continuous effect applies ("As long as you've drawn two or more cards
  this turn, ..."); ``opt:filter`` + omit-if-empty.
- R3-2: ``ActivatedAbility.condition: Filter | None = None`` — gates
  activation ("Activate only if a creature died this turn").
- R3-3: ``COUNTER_SPELL`` gains an optional ``unless`` role (a ``Cost``
  value — "unless its controller pays {3}"); ``target`` stays required.
- R3-4: ``FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN`` — required
  ``who`` slot (precedent: LIFE_GAINED_THIS_TURN_GE).
- R3-5: ``CostModifier.extra_deltas: tuple[CostDelta, ...] = ()`` —
  further cost deltas beyond the single ``delta`` slot; ``tup:cost_delta``
  + omit-if-empty.
- R3-6: ``FAtomPred.TARGETS_SOURCE`` — "spells your opponents cast that
  target this creature"; no slots (precedent: IS_SOURCE).

Guards:
- every pre-round-4 pinned fingerprint (the round-3 pin set) stays
  byte-identical — all six items are additive optional slots/enums/roles;
- bare constructs (condition=None / extra_deltas=()) serialize WITHOUT
  the new keys;
- round-4 constructs round-trip through ``to_dict``/``from_dict`` with
  pinned fingerprints;
- rejections at every new or widened validation point (``ValueError``,
  per the module-wide convention).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

import MTG_bot.core.ability_tree as at
import MTG_bot.core.test_ability_tree_r3 as R3

# ---- builders for the round-4 constructs -----------------------------------

_STACK_ANY = at.Zone(at.ZoneKind.STACK, at.ControllerRef.ANY)
_TARGET_SPELL = at.Selector(
    at.QConst(1), at.SelectorMode.TARGET, at.FAtom(at.FAtomPred.IS_SOURCE), zones=(_STACK_ANY,)
)
_CREATURE = at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature")
_BF_YOU = at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU)
_CREATURE_BF = at.Selector(at.QConst(1), at.SelectorMode.TARGET, _CREATURE, zones=(_BF_YOU,))
_CM_FILTER = at.FAtom(at.FAtomPred.IS_PERMANENT)
_CM_DELTA = at.CostDeltaReduceGeneric(at.QConst(2))


def _draw_one() -> at.Atom:
    return at.Atom(
        at.Verb.DRAW,
        at.AtomArgs(
            pairs=(("amount", at.QConst(1)), ("controller", at.ControllerRef.YOU))
        ),
    )


def _sacrifice() -> at.Atom:
    return at.Atom(at.Verb.SACRIFICE, at.AtomArgs(pairs=(("target", _CREATURE_BF),)))


def _static_condition() -> at.FAtom:
    """'You've drawn two or more cards this turn' (state predicate)."""
    return at.FAtom(
        at.FAtomPred.CARDS_DRAWN_THIS_TURN_GE,
        count=at.QConst(2),
        who=at.ControllerRef.YOU,
    )


def _static_cond() -> at.StaticAbility:
    """R3-1: static effect scoped by a condition."""
    return at.StaticAbility(_draw_one(), condition=_static_condition())


def _static_bare() -> at.StaticAbility:
    """Pre-round-4 shape: no condition key in the serialization."""
    return at.StaticAbility(_draw_one())


def _activated_condition() -> at.FAtom:
    """'A creature died this turn' (state predicate)."""
    return at.FAtom(at.FAtomPred.DIED_THIS_TURN)


def _activated_cond() -> at.ActivatedAbility:
    """R3-2: activation gated by a condition."""
    return at.ActivatedAbility(
        at.Cost(parts=()), _sacrifice(), condition=_activated_condition()
    )


def _activated_bare() -> at.ActivatedAbility:
    return at.ActivatedAbility(at.Cost(parts=()), _sacrifice())


def _cost3() -> at.Cost:
    return at.Cost(parts=(at.CostManaGeneric(at.QConst(3)),))


def _counter_unless() -> at.Atom:
    """R3-3: COUNTER_SPELL with the optional ``unless`` cost role."""
    return at.Atom(
        at.Verb.COUNTER_SPELL,
        at.AtomArgs(pairs=(("target", _TARGET_SPELL), ("unless", _cost3()))),
    )


def _counter_bare() -> at.Atom:
    """Pre-round-4 shape: COUNTER_SPELL with ``target`` only."""
    return at.Atom(
        at.Verb.COUNTER_SPELL, at.AtomArgs(pairs=(("target", _TARGET_SPELL),))
    )


def _cm_no_extra() -> at.CostModifier:
    """Pre-round-4 shape: single delta, no ``extra_deltas`` key."""
    return at.CostModifier(_CM_FILTER, at.ControllerRef.YOU, _CM_DELTA)


def _cm_two() -> at.CostModifier:
    """R3-5: '{2}{U} less' = generic 2 + 1 blue via ``extra_deltas``."""
    return at.CostModifier(
        _CM_FILTER,
        at.ControllerRef.YOU,
        _CM_DELTA,
        extra_deltas=(
            at.CostDeltaReduceMana("U", at.QConst(1)),
            at.CostDeltaIncreaseLife(at.QConst(3)),
        ),
    )


def _fatom_ios() -> at.FAtom:
    """R3-4: 'you've cast an instant or sorcery this turn'."""
    return at.FAtom(
        at.FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN, who=at.ControllerRef.YOU
    )


def _fatom_ts() -> at.FAtom:
    """R3-6: 'spells your opponents cast that target this creature'."""
    return at.FAtom(at.FAtomPred.TARGETS_SOURCE)


# ---- pinned fingerprints (captured after the round-4 edits) ----------------

_NEW_PINS: list[tuple[str, Callable[[], object], str]] = [
    (
        "static_cond",
        _static_cond,
        "a2c9facb690ec90b51cffe964d182ec221b06f2b9dda4661c1f6809f0d5c3d37",
    ),
    (
        "static_bare",
        _static_bare,
        "12ba01fff85835342faf5d3c777478cd5ceac5feb596035d711c531f19630a5e",
    ),
    (
        "activated_cond",
        _activated_cond,
        "4f09b7dc65f97a05f4aa1d0268eed05dacdf0de8bc473af7446382ff4ed9e1e1",
    ),
    (
        "activated_bare",
        _activated_bare,
        "4dbd1feb5bf348de49980e8a716609b481e935d8151a80ecbe76dee6773cfd3b",
    ),
    (
        "counter_unless",
        _counter_unless,
        "aa1736ad794ce87cce46b30ffde80554d0cccc18506fcf409de43695cc8e6d68",
    ),
    (
        "counter_bare",
        _counter_bare,
        "5b9a95ac5d13e8e153c999adcd8c116978699b0ec7bbd2105759a3e42e78f39d",
    ),
    (
        "cm_no_extra",
        _cm_no_extra,
        "153eb656cf0b478f4b88f08962928eddd15ca4f5cb536d495e1a0f383f9c3402",
    ),
    (
        "cm_two",
        _cm_two,
        "5fcddd1856c52a39d1e1c87e0c41d7f8413b94694e4046bbbafa4d13e15d4a86",
    ),
    (
        "fatom_ios",
        _fatom_ios,
        "ea27cdc5884f3c535f19a61313fca42feffd82219e60978fe9ae427bb3c7b166",
    ),
    (
        "fatom_ts",
        _fatom_ts,
        "b22db523817bb0380b139d62bfee5f3c65e2ddf5bd9ef5d4073a78e9f24fe22e",
    ),
]


# ---- tests ----------------------------------------------------------------


@pytest.mark.parametrize("name,build,fp", R3._PINNED, ids=[n for n, _, _ in R3._PINNED])
def test_pinned_pre_r4_fingerprint(
    name: str, build: Callable[[], object], fp: str
) -> None:
    """Byte stability: every pre-round-4 pinned tree serializes identically."""
    node = build()
    assert at.fingerprint(node) == fp
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d


@pytest.mark.parametrize("name,build,fp", _NEW_PINS, ids=[n for n, _, _ in _NEW_PINS])
def test_r4_roundtrip(name: str, build: Callable[[], object], fp: str) -> None:
    node = build()
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d
    back = at.from_dict(d["tag"], d)
    assert back == node, f"{name}: from_dict(to_dict(x)) != x"
    assert at.canonical_json(back) == at.canonical_json(node)
    assert at.fingerprint(back) == at.fingerprint(node) == fp


def test_bare_abilities_omit_condition() -> None:
    d = at.to_dict(_static_bare())
    assert set(d.keys()) == {"tag", "effect"}, (
        f"bare StaticAbility must omit 'condition': {sorted(d)}"
    )
    d = at.to_dict(_activated_bare())
    assert set(d.keys()) == {"tag", "cost", "effect"}, (
        f"bare ActivatedAbility must omit 'condition': {sorted(d)}"
    )


def test_explicit_none_condition_equals_default() -> None:
    explicit = at.StaticAbility(_draw_one(), condition=None)
    default = _static_bare()
    assert explicit == default
    assert at.to_dict(explicit) == at.to_dict(default)
    assert at.fingerprint(explicit) == at.fingerprint(default)
    back = at.from_dict("StaticAbility", at.to_dict(default))
    assert back.condition is None


def test_cm_omits_extra_deltas_when_empty() -> None:
    d = at.to_dict(_cm_no_extra())
    assert set(d.keys()) == {"tag", "filter", "controller_ref", "delta"}, (
        f"CostModifier without extra_deltas must omit the key: {sorted(d)}"
    )
    d = at.to_dict(_cm_two())
    assert "extra_deltas" in d
    assert len(d["extra_deltas"]) == 2
    assert [x["tag"] for x in d["extra_deltas"]] == [
        "CostDeltaReduceMana",
        "CostDeltaIncreaseLife",
    ]


def test_from_dict_missing_condition_defaults_none() -> None:
    d: dict[str, Any] = {"tag": "StaticAbility", "effect": at.to_dict(_draw_one())}
    back = at.from_dict("StaticAbility", d)
    assert back.condition is None
    assert back == _static_bare()

    d2: dict[str, Any] = {
        "tag": "ActivatedAbility",
        "cost": at.to_dict(at.Cost(parts=())),
        "effect": at.to_dict(_sacrifice()),
    }
    back2 = at.from_dict("ActivatedAbility", d2)
    assert back2.condition is None
    assert back2 == _activated_bare()


def test_from_dict_missing_extra_deltas_defaults_empty() -> None:
    d = at.to_dict(_cm_no_extra())
    assert "extra_deltas" not in d
    back = at.from_dict("CostModifier", d)
    assert back.extra_deltas == ()
    assert back == _cm_no_extra()


def test_r4_enum_and_table_members() -> None:
    assert (
        at.FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN.value
        == "INSTANT_OR_SORCERY_CAST_THIS_TURN"
    )
    assert at.FAtomPred.TARGETS_SOURCE.value == "TARGETS_SOURCE"
    assert at._VERB_ROLES[at.Verb.COUNTER_SPELL] == {"target": True, "unless": False}
    assert at._ROLE_TYPES["unless"] == (at.Cost,)
    assert at._FATOM_RULES[at.FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN] == (
        frozenset({"who"}),
        frozenset({"who"}),
    )
    assert at._FATOM_RULES[at.FAtomPred.TARGETS_SOURCE] == (frozenset(), frozenset())


def _rejection_cases() -> list[tuple[str, Callable[[], object]]]:
    return [
        (
            "static_str_condition",
            lambda: at.StaticAbility(_draw_one(), condition="drew"),  # type: ignore[arg-type]
        ),
        (
            "activated_str_condition",
            lambda: at.ActivatedAbility(
                at.Cost(parts=()),
                _sacrifice(),
                condition="died",  # type: ignore[arg-type]
            ),
        ),
        (
            "counter_missing_target",
            lambda: at.Atom(at.Verb.COUNTER_SPELL, at.AtomArgs()),
        ),
        (
            "counter_unless_non_cost",
            lambda: at.Atom(
                at.Verb.COUNTER_SPELL,
                at.AtomArgs(
                    pairs=(
                        ("target", _TARGET_SPELL),
                        ("unless", "3"),  # type: ignore[tuple-item]
                    )
                ),
            ),
        ),
        (
            "counter_unknown_role",
            lambda: at.Atom(
                at.Verb.COUNTER_SPELL,
                at.AtomArgs(
                    pairs=(
                        ("target", _TARGET_SPELL),
                        ("zap", at.QConst(1)),  # type: ignore[tuple-item]
                    )
                ),
            ),
        ),
        (
            "fatom_ios_missing_who",
            lambda: at.FAtom(at.FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN),
        ),
        (
            "fatom_ios_forbidden_count_slot",
            lambda: at.FAtom(
                at.FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN,
                who=at.ControllerRef.YOU,
                count=at.QConst(1),
            ),
        ),
        (
            "fatom_ts_forbidden_who_slot",
            lambda: at.FAtom(at.FAtomPred.TARGETS_SOURCE, who=at.ControllerRef.YOU),
        ),
        (
            "cm_extra_deltas_non_delta",
            lambda: at.CostModifier(
                _CM_FILTER,
                at.ControllerRef.YOU,
                _CM_DELTA,
                extra_deltas=(at.QConst(1),),  # type: ignore[arg-type]
            ),
        ),
        (
            "from_dict_static_bad_condition_tag",
            lambda: at.from_dict(
                "StaticAbility",
                {
                    "tag": "StaticAbility",
                    "effect": at.to_dict(_draw_one()),
                    "condition": {"tag": "Cost", "parts": []},
                },
            ),
        ),
    ]


@pytest.mark.parametrize(
    "name,fn", _rejection_cases(), ids=[n for n, _ in _rejection_cases()]
)
def test_r4_rejections(name: str, fn: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        fn()
