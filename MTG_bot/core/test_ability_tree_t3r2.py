"""T3 round 2 — additive grammar-extension tests.

Round-2 scope (KNOWLEDGE/2026-09-22/02-t7-semantic-spot-check.md items 1-6):

- item 1: turn-scoped FAtomPred members LIFE_GAINED_THIS_TURN_GE /
  CARDS_DRAWN_THIS_TURN_GE. Both require the ``who`` slot; ``count`` is
  intentionally NOT enforced as required so QX / QThisTurn dynamics stay
  expressible (a who-only atom is legal).
- item 2: ``CostModifier.condition`` (omitted from the serialization when
  None).
- item 3: ``SpellAbility.additional_costs`` (omitted when empty; holds full
  ``Cost`` nodes, not bare cost parts).
- item 4: optional ``tapped_on_enter`` bool role on MOVE_ZONE / SEARCH,
  serialized as a ``"Bool"``-tagged atom value inside the pairs.
- item 5: "can't phase in" needed NO grammar change; the prevention
  composition's fingerprint is pinned below (byte-identical pre/post edit).
- item 6: ``CostLoyalty.delta`` widened to ``int | Quantity`` (Ugin [−X]).

Guards:
- all nine pre-round-2 fingerprint pins stay byte-identical;
- no pre-round-2 tree serializes any round-2 key or tag;
- round-trip equality for every new construct;
- rejections at every new entry point (bool / zero / type violations).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

import MTG_bot.core.ability_tree as at
import MTG_bot.core.test_ability_tree as T

# ---- small shared builders (local; T's builders serve the pinned trees) ----

_BF_YOU = at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU)
_GRAV_YOU = at.Zone(at.ZoneKind.GRAVEYARD, at.ControllerRef.YOU)
_HAND_YOU = at.Zone(at.ZoneKind.HAND, at.ControllerRef.YOU)
_LIB_ANY = at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY)
_CREATURE = at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature")
_CREATURE_BF = at.Selector(at.QConst(1), at.SelectorMode.TARGET, _CREATURE, _BF_YOU)
_CREATURE_GRAV = at.Selector(at.QConst(1), at.SelectorMode.CHOOSE, _CREATURE, _GRAV_YOU)
_CREATURE_LIB = at.Selector(at.QConst(1), at.SelectorMode.TARGET, _CREATURE, _LIB_ANY)
_CREATURE_HAND = at.Selector(at.QConst(1), at.SelectorMode.TARGET, _CREATURE, _HAND_YOU)


def _draw_one() -> at.Atom:
    return at.Atom(
        at.Verb.DRAW,
        at.AtomArgs(
            pairs=(
                ("controller", at.ControllerRef.YOU),
                ("amount", at.QConst(1)),
            )
        ),
    )


def _cost_modifier_base() -> at.CostModifier:
    return at.CostModifier(
        at.FNot(_CREATURE),
        at.ControllerRef.ANY,
        at.CostDeltaReduceGeneric(at.QConst(1)),
    )


def _cost_modifier_with_condition() -> at.CostModifier:
    return at.CostModifier(
        at.FNot(_CREATURE),
        at.ControllerRef.ANY,
        at.CostDeltaReduceGeneric(at.QConst(1)),
        condition=at.FAtom(
            at.FAtomPred.LIFE_GAINED_THIS_TURN_GE,
            count=at.QConst(5),
            who=at.ControllerRef.YOU,
        ),
    )


def _spell_base() -> at.SpellAbility:
    return at.SpellAbility(at.SpellKind.INSTANT, _draw_one())


def _spell_additional_sacrifice() -> at.SpellAbility:
    return at.SpellAbility(
        at.SpellKind.SORCERY,
        _draw_one(),
        additional_costs=(at.Cost(parts=(at.CostSacrifice(_CREATURE_BF),)),),
    )


def _spell_additional_discard_life() -> at.SpellAbility:
    return at.SpellAbility(
        at.SpellKind.SORCERY,
        _draw_one(),
        additional_costs=(
            at.Cost(parts=(at.CostDiscard(_CREATURE_HAND),)),
            at.Cost(parts=(at.CostLife(at.QConst(2)),)),
        ),
    )


def _move_zone_base() -> at.Atom:
    return at.Atom(
        at.Verb.MOVE_ZONE,
        at.AtomArgs(
            pairs=(
                ("cards", _CREATURE_GRAV),
                ("destination", at.Zone(at.ZoneKind.HAND, at.ControllerRef.YOU)),
            )
        ),
    )


def _move_zone_tapped() -> at.Atom:
    return at.Atom(
        at.Verb.MOVE_ZONE,
        at.AtomArgs(
            pairs=(
                ("cards", _CREATURE_GRAV),
                ("destination", _BF_YOU),
                ("tapped_on_enter", True),
            )
        ),
    )


def _move_zone_untapped_explicit() -> at.Atom:
    return at.Atom(
        at.Verb.MOVE_ZONE,
        at.AtomArgs(
            pairs=(
                ("cards", _CREATURE_GRAV),
                ("destination", _BF_YOU),
                ("tapped_on_enter", False),
            )
        ),
    )


def _search_tapped() -> at.Atom:
    return at.Atom(
        at.Verb.SEARCH,
        at.AtomArgs(
            pairs=(
                ("cards", _CREATURE_LIB),
                ("destination", _BF_YOU),
                ("controller", at.ControllerRef.YOU),
                ("tapped_on_enter", True),
            )
        ),
    )


def _fatom_life_who_only() -> at.FAtom:
    """Legal edge: ``count`` is optional, so a who-only atom is constructible."""
    return at.FAtom(at.FAtomPred.LIFE_GAINED_THIS_TURN_GE, who=at.ControllerRef.YOU)


def _ugin_exile_dynamic() -> at.ActivatedAbility:
    """Ugin, the Intrinsic [−X]: exile up to one creature with CMC <= X and
    at least two colors, where X = its own loyalty."""
    return at.ActivatedAbility(
        cost=at.Cost(parts=(at.CostLoyalty(at.QX()),)),
        effect=at.Atom(
            at.Verb.EXILE,
            at.AtomArgs(
                pairs=(
                    (
                        "target",
                        at.Selector(
                            at.QUnbounded(),
                            at.SelectorMode.ALL,
                            at.FAnd(
                                (
                                    at.FAtom(at.FAtomPred.CMC_LE, count=at.QX()),
                                    at.FAtom(
                                        at.FAtomPred.COLOR_COUNT_GE,
                                        count=at.QConst(2),
                                    ),
                                )
                            ),
                            _BF_YOU,
                        ),
                    ),
                )
            ),
        ),
    )


def _phase_in_prevention() -> at.StaticAbility:
    """ "Can't phase in" (Teferi [−8] family): prevent the opponent's command
    zone cards entering the battlefield until the next turn. NO new grammar
    was needed — this is the item-5 composition (T3 round 2, item 5)."""
    return at.StaticAbility(
        effect=at.Atom(
            at.Verb.PREVENT_EFFECT,
            at.AtomArgs(
                pairs=(
                    (
                        "condition",
                        at.FAtom(
                            at.FAtomPred.CONTROLLER_IS,
                            who=at.ControllerRef.OPPONENT,
                        ),
                    ),
                    (
                        "event",
                        at.ZoneChangeEvent(
                            from_zone=at.Zone(
                                at.ZoneKind.COMMAND, at.ControllerRef.OPPONENT
                            ),
                            to_zone=at.Zone(
                                at.ZoneKind.BATTLEFIELD, at.ControllerRef.OPPONENT
                            ),
                        ),
                    ),
                    ("duration", at.DurationUntilNextTurn()),
                )
            ),
        )
    )


# ---- pinned pre-round-2 fingerprints (captured before any round-2 edit) ----

_PINNED: list[tuple[str, Callable[[], object], str]] = [
    (
        "simple_card",
        T._simple_card,
        "9bd3f0e185eb0f51ca7a99e64f472a22bab2acd4b8cb24582904cc163ffb6a39",
    ),
    (
        "tarmogoyf",
        T._tarmogoyf_like,
        "ef2ac943913f6b8e86237746e283dd6fe7d49be5aacc856263d58f94504072ed",
    ),
    (
        "planeswalker_emblem",
        T._pw_with_emblem,
        "a714acc403cc003d938b5d24f82b7644a6351d2aea6094f9230bfaa572f7d1bf",
    ),
    (
        "token_creator",
        T._token_creator,
        "77b3c7713172bb961d21395135f68e50ce04e0e9d106c257ec10b4cf6a81ddb4",
    ),
    (
        "cost_loyalty_bare",
        lambda: at.Cost(parts=(at.CostLoyalty(-2),)),
        "0839db42dcbe8215dd169b559de30fb331a5279b069cbc50a69975121b734aec",
    ),
    (
        "cost_modifier_no_condition",
        _cost_modifier_base,
        "812b960eb4c89866207d3d86cfda0b4722d6b63c00cf4cd81aa32a91e3998f98",
    ),
    (
        "spell_ability_no_additional",
        _spell_base,
        "e4d6897f8542141dc66d4d2ca1356746d99bf5587535a78019b952619570905d",
    ),
    (
        "move_zone_no_tap",
        _move_zone_base,
        "4b35024107bb304a55dfda5d1a626f9d2010af29943290acf307f5041464f112",
    ),
    (
        "qthis_turn",
        lambda: at.QThisTurn(at.ThisTurnKind.LIFE_GAINED, at.ControllerRef.YOU),
        "f041066bc5249c4ec4a1e1ade8586936742d70656fa733790bec97876d5c4744",
    ),
]

# Round-2 keys/tags that must be ABSENT from every pre-round-2 tree.
_NEW_PRED_NAMES = frozenset({"LIFE_GAINED_THIS_TURN_GE", "CARDS_DRAWN_THIS_TURN_GE"})


def _assert_no_t3r2_keys(d: Any, path: str = "root") -> None:
    """Recursively assert no round-2 key or tag appears in a pre-round-2 tree."""
    if isinstance(d, dict):
        tag = d.get("tag")
        if tag == "CostModifier":
            assert "condition" not in d, (
                f"pre-round-2 tree {path} carries new key 'condition'"
            )
        if tag == "SpellAbility":
            assert "additional_costs" not in d, (
                f"pre-round-2 tree {path} carries new key 'additional_costs'"
            )
        if tag == "CostLoyalty":
            delta = d.get("delta")
            assert isinstance(delta, int) and not isinstance(delta, bool), (
                f"pre-round-2 tree {path} carries a dynamic CostLoyalty delta"
            )
        if tag == "FAtom":
            pred = d.get("pred")
            assert not (
                isinstance(pred, dict) and pred.get("name") in _NEW_PRED_NAMES
            ), f"pre-round-2 tree {path} carries a round-2 predicate"
        if tag == "Bool":
            raise AssertionError(
                f"pre-round-2 tree {path} serializes a Bool atom value"
            )
        for value in d.values():
            _assert_no_t3r2_keys(value, f"{path}.{tag}")
    elif isinstance(d, list):
        if len(d) == 2 and d[0] == "tapped_on_enter":
            raise AssertionError(
                f"pre-round-2 tree {path} carries a tapped_on_enter pair"
            )
        for i, item in enumerate(d):
            _assert_no_t3r2_keys(item, f"{path}[{i}]")


# ---- round-trip catalogue for every new construct ----

_NEW_NODES: list[tuple[str, Callable[[], object]]] = [
    # item 1: turn-scoped predicates
    (
        "fatom_life_gained_const",
        lambda: at.FAtom(
            at.FAtomPred.LIFE_GAINED_THIS_TURN_GE,
            count=at.QConst(3),
            who=at.ControllerRef.YOU,
        ),
    ),
    (
        "fatom_life_gained_qx",
        lambda: at.FAtom(
            at.FAtomPred.LIFE_GAINED_THIS_TURN_GE,
            count=at.QX(),
            who=at.ControllerRef.YOU,
        ),
    ),
    ("fatom_life_gained_who_only", _fatom_life_who_only),
    (
        "fatom_cards_drawn_const",
        lambda: at.FAtom(
            at.FAtomPred.CARDS_DRAWN_THIS_TURN_GE,
            count=at.QConst(2),
            who=at.ControllerRef.OPPONENT,
        ),
    ),
    (
        "fatom_cards_drawn_qthis",
        lambda: at.FAtom(
            at.FAtomPred.CARDS_DRAWN_THIS_TURN_GE,
            count=at.QThisTurn(at.ThisTurnKind.CARDS_DRAWN, at.ControllerRef.OPPONENT),
            who=at.ControllerRef.OPPONENT,
        ),
    ),
    # item 2: CostModifier.condition
    ("cost_modifier_with_condition", _cost_modifier_with_condition),
    # item 3: SpellAbility.additional_costs
    ("spell_additional_sacrifice", _spell_additional_sacrifice),
    ("spell_additional_discard_life", _spell_additional_discard_life),
    # item 4: tapped_on_enter
    ("move_zone_tapped", _move_zone_tapped),
    ("move_zone_untapped_explicit", _move_zone_untapped_explicit),
    ("search_tapped", _search_tapped),
    # item 6: dynamic loyalty delta
    ("cost_loyalty_qx", lambda: at.CostLoyalty(at.QX())),
    ("cost_loyalty_qconst", lambda: at.CostLoyalty(at.QConst(3))),
    ("cost_loyalty_bare_int", lambda: at.CostLoyalty(-4)),
]


# ---- rejection catalogue ----


def _bool_atom_value_nonbool() -> at.Atom:
    node = _move_zone_tapped()
    d = at.to_dict(node)
    for pair in d["args"]["pairs"]:
        if pair[0] == "tapped_on_enter":
            pair[1] = {"tag": "Bool", "value": 1}
    return at.from_dict("Atom", d)


def _rejection_cases() -> list[tuple[str, Callable[[], object]]]:
    return [
        ("cost_loyalty_bool", lambda: at.CostLoyalty(True)),
        ("cost_loyalty_zero", lambda: at.CostLoyalty(0)),
        ("cost_loyalty_qconst_zero", lambda: at.CostLoyalty(at.QConst(0))),
        ("cost_loyalty_str", lambda: at.CostLoyalty("2")),  # type: ignore[arg-type]
        (
            "cost_loyalty_decode_bool_delta",
            lambda: at.from_dict("CostLoyalty", {"tag": "CostLoyalty", "delta": True}),
        ),
        (
            "fatom_life_gained_missing_who",
            lambda: at.FAtom(at.FAtomPred.LIFE_GAINED_THIS_TURN_GE, count=at.QConst(3)),
        ),
        (
            "fatom_cards_drawn_missing_who",
            lambda: at.FAtom(at.FAtomPred.CARDS_DRAWN_THIS_TURN_GE, count=at.QConst(2)),
        ),
        (
            "fatom_cards_drawn_no_slots",
            lambda: at.FAtom(at.FAtomPred.CARDS_DRAWN_THIS_TURN_GE),
        ),
        (
            "fatom_life_gained_extra_slot",
            lambda: at.FAtom(
                at.FAtomPred.LIFE_GAINED_THIS_TURN_GE,
                count=at.QConst(3),
                who=at.ControllerRef.YOU,
                string_value="Bird",
            ),
        ),
        (
            "cost_modifier_condition_str",
            lambda: at.CostModifier(
                at.FNot(_CREATURE),
                at.ControllerRef.ANY,
                at.CostDeltaReduceGeneric(at.QConst(1)),
                "nope",  # type: ignore[arg-type]
            ),
        ),
        (
            "spell_additional_costs_list",
            lambda: at.SpellAbility(
                at.SpellKind.INSTANT,
                _draw_one(),
                additional_costs=[at.Cost()],  # type: ignore[arg-type]
            ),
        ),
        (
            "spell_additional_costs_non_cost",
            lambda: at.SpellAbility(
                at.SpellKind.INSTANT,
                _draw_one(),
                additional_costs=(at.QConst(1),),  # type: ignore[arg-type]
            ),
        ),
        (
            "spell_additional_costs_bare_part",
            lambda: at.SpellAbility(
                at.SpellKind.INSTANT,
                _draw_one(),
                additional_costs=(
                    at.CostSacrifice(_CREATURE_BF),  # type: ignore[arg-type]
                ),
            ),
        ),
        (
            "move_zone_tapped_int",
            lambda: at.Atom(
                at.Verb.MOVE_ZONE,
                at.AtomArgs(
                    pairs=(
                        ("cards", _CREATURE_GRAV),
                        ("destination", _BF_YOU),
                        ("tapped_on_enter", 1),
                    )
                ),
            ),
        ),
        (
            "search_tapped_str",
            lambda: at.Atom(
                at.Verb.SEARCH,
                at.AtomArgs(
                    pairs=(
                        ("cards", _CREATURE_LIB),
                        ("destination", _BF_YOU),
                        ("tapped_on_enter", "yes"),
                    )
                ),
            ),  # type: ignore[arg-type]
        ),
        ("bool_atom_value_nonbool_decode", _bool_atom_value_nonbool),
    ]


# ---- tests ----


@pytest.mark.parametrize("name,build,fp", _PINNED, ids=[n for n, _, _ in _PINNED])
def test_pinned_pre_t3r2_fingerprint(
    name: str, build: Callable[[], object], fp: str
) -> None:
    node = build()
    assert at.fingerprint(node) == fp
    _assert_no_t3r2_keys(at.to_dict(node))


@pytest.mark.parametrize("name,build", _NEW_NODES, ids=[n for n, _ in _NEW_NODES])
def test_t3r2_roundtrip(name: str, build: Callable[[], object]) -> None:
    node = build()
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d, (
        f"{name}: to_dict must yield a tagged dict"
    )
    back = at.from_dict(str(d["tag"]), d)
    assert back == node, f"{name}: from_dict(to_dict(x)) != x"
    assert at.canonical_json(back) == at.canonical_json(node)
    assert at.fingerprint(back) == at.fingerprint(node)


@pytest.mark.parametrize(
    "name,fn", _rejection_cases(), ids=[n for n, _ in _rejection_cases()]
)
def test_t3r2_rejections(name: str, fn: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        fn()


def test_omit_keys_present_when_set() -> None:
    d = at.to_dict(_cost_modifier_with_condition())
    assert "condition" in d
    assert d["condition"]["tag"] == "FAtom"
    d = at.to_dict(_spell_additional_sacrifice())
    assert len(d["additional_costs"]) == 1
    assert d["additional_costs"][0]["tag"] == "Cost"
    d = at.to_dict(_spell_additional_discard_life())
    assert len(d["additional_costs"]) == 2
    pairs = {p[0]: p[1] for p in at.to_dict(_move_zone_tapped())["args"]["pairs"]}
    assert pairs["tapped_on_enter"] == {"tag": "Bool", "value": True}
    pairs = {
        p[0]: p[1] for p in at.to_dict(_move_zone_untapped_explicit())["args"]["pairs"]
    }
    assert pairs["tapped_on_enter"] == {"tag": "Bool", "value": False}


def test_omit_keys_absent_by_default() -> None:
    assert "condition" not in at.to_dict(_cost_modifier_base())
    assert "additional_costs" not in at.to_dict(_spell_base())
    pairs = at.to_dict(_move_zone_base())["args"]["pairs"]
    assert "tapped_on_enter" not in [p[0] for p in pairs]


def test_explicit_empty_omit_fields_decode() -> None:
    # A hand-built tagged dict that spells the empty defaults out loud
    # must decode to the same node as the omitted form (value equality).
    d = at.to_dict(_cost_modifier_base())
    d["condition"] = None
    assert at.from_dict("CostModifier", d) == _cost_modifier_base()
    d2 = at.to_dict(_spell_base())
    d2["additional_costs"] = []
    assert at.from_dict("SpellAbility", d2) == _spell_base()


def test_verb_role_table_pins() -> None:
    # T4 P1a: MOVE_ZONE became the ONE move atom — objects ride one of
    # cards/target/amount, with from/journal_kind/pop_order slots.
    assert at._VERB_ROLES[at.Verb.MOVE_ZONE] == {
        "destination": True,
        "cards": False,
        "target": False,
        "controller": False,
        "amount": False,
        "from": False,
        "journal_kind": False,
        "pop_order": False,
        "tapped_on_enter": False,
    }
    assert at._VERB_ROLES[at.Verb.SEARCH] == {
        "cards": True,
        "destination": True,
        "controller": False,
        "tapped_on_enter": False,
    }
    assert at._ROLE_TYPES["tapped_on_enter"] == (bool,)


def test_new_fatom_rule_rows() -> None:
    rules = at._FATOM_RULES
    assert rules[at.FAtomPred.LIFE_GAINED_THIS_TURN_GE] == (
        frozenset({"count", "who"}),
        frozenset({"count", "who"}),
    )
    assert rules[at.FAtomPred.CARDS_DRAWN_THIS_TURN_GE] == (
        frozenset({"count", "who"}),
        frozenset({"count", "who"}),
    )


def test_new_enum_values() -> None:
    assert at.FAtomPred.LIFE_GAINED_THIS_TURN_GE.value == ("LIFE_GAINED_THIS_TURN_GE")
    assert at.FAtomPred.CARDS_DRAWN_THIS_TURN_GE.value == ("CARDS_DRAWN_THIS_TURN_GE")


def test_fingerprint_sensitivity_new_fields() -> None:
    assert at.fingerprint(_cost_modifier_base()) != at.fingerprint(
        _cost_modifier_with_condition()
    )
    assert at.fingerprint(_spell_base()) != at.fingerprint(
        _spell_additional_sacrifice()
    )
    assert at.fingerprint(_move_zone_base()) != at.fingerprint(_move_zone_tapped())
    assert at.fingerprint(_move_zone_tapped()) != at.fingerprint(
        _move_zone_untapped_explicit()
    )
    assert at.fingerprint(at.Cost(parts=(at.CostLoyalty(-2),))) != (
        at.fingerprint(at.Cost(parts=(at.CostLoyalty(at.QX()),)))
    )
    assert at.fingerprint(
        at.FAtom(
            at.FAtomPred.LIFE_GAINED_THIS_TURN_GE,
            count=at.QConst(3),
            who=at.ControllerRef.YOU,
        )
    ) != at.fingerprint(
        at.FAtom(
            at.FAtomPred.CARDS_DRAWN_THIS_TURN_GE,
            count=at.QConst(3),
            who=at.ControllerRef.YOU,
        )
    )


def test_walk_visits_new_fields() -> None:
    node = _cost_modifier_with_condition()
    visited = list(at.walk(node))
    assert visited[0] is node
    assert any(
        isinstance(v, at.FAtom) and v.pred is at.FAtomPred.LIFE_GAINED_THIS_TURN_GE
        for v in visited
    )
    visited = list(at.walk(_spell_additional_sacrifice()))
    assert any(isinstance(v, at.CostSacrifice) for v in visited)


def test_phase_in_prevention_item5() -> None:
    # Item 5: "can't phase in" needs no grammar change — the composition is
    # expressible in the pre-round-2 grammar and its fingerprint is pinned.
    node = _phase_in_prevention()
    assert at.fingerprint(node) == (
        "68e1909dc33bb2798b9212c3a6ebd6b2150009579f79bdac1e08586f3142b3a7"
    )
    d = at.to_dict(node)
    assert at.from_dict(str(d["tag"]), d) == node


def test_ugin_dynamic_loyalty_item6() -> None:
    # Item 6: Ugin [−X] builds with a dynamic Quantity loyalty delta.
    node = _ugin_exile_dynamic()
    assert at.fingerprint(node) == (
        "f6c6c8ee342cbaccd7e10a7c04e55aa866be7d1e699e8842ed45d0dfbc47dfca"
    )
    back = at.from_dict("ActivatedAbility", at.to_dict(node))
    assert back == node
    part = back.cost.parts[0]
    assert isinstance(part, at.CostLoyalty)
    assert part.delta == at.QX()
    visited = list(at.walk(node))
    assert any(isinstance(v, at.CostLoyalty) for v in visited)
    assert any(isinstance(v, at.QX) for v in visited)
