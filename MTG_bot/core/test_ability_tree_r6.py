"""Grammar pins: the was-cast and not-first-draw predicates, counter-placed
counts, and a Selector as a cost modifier's controller.

- ``FAtomPred.WAS_CAST_THIS_TURN`` — required ``who`` — "[the object]
  was cast this turn (by who)" (Containment Priest; who=ANY = cast by
  anyone; the "and it wasn't cast" condition is
  ``FNot(FAtom(WAS_CAST_THIS_TURN, who=ANY))``). Zone-agnostic — distinct
  from the zone-slot-bearing ``CAST_THIS_TURN_FROM``.
- ``CounterPlacedEvent.count: Quantity | None = None`` — the number
  placed ("one or more" = ``QAtLeast(1)``); ``opt:quantity`` +
  omit-if-empty; plus ``QPropField.COUNTER_COUNT`` — "that many" =
  ``QProp("event", COUNTER_COUNT)`` (the event's counter count; Conclave
  Mentor).
- ``CostModifier.controller_ref: ControllerRef | Selector`` — a Selector
  means the controller of the selected object, and the modifier applies to
  costs that controller pays FOR the filtered object, including ``unless``
  payments (Lofty Denial); the same ``controller_ref_or_selector``
  conversion as FAtom.who.
- ``FAtomPred.NOT_FIRST_DRAW_THIS_STEP`` — required ``who`` — "not
  the first card who draws in their draw step" (Teferi's Ageless Insight;
  evaluated against the drawn card, the CardDrawnEvent subject).

Guards:
- the test_ability_tree_r4 and r5 pin sets keep their fingerprints;
- bare constructs (count=None / controller_ref=ControllerRef / no who)
  serialize WITHOUT the optional keys;
- the constructs round-trip through ``to_dict``/``from_dict`` with
  pinned fingerprints;
- every validation point rejects bad input with ``ValueError``.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

import MTG_bot.core.ability_tree as at
import MTG_bot.core.test_ability_tree_r4 as R4
import MTG_bot.core.test_ability_tree_r5 as R5

# ---- builders --------------------------------------------------------------

_UNIVERSAL = at.FAnd(())
_NEUTRAL = at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY)
_CREATURE = at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature")


def _fatom_was_cast_any() -> at.FAtom:
    """'A creature that wasn't cast (by anyone)' — the atom before
    negation (Containment Priest)."""
    return at.FAtom(at.FAtomPred.WAS_CAST_THIS_TURN, who=at.ControllerRef.ANY)


def _priest_condition() -> at.FNot:
    """'It wasn't cast' — the negated form the template uses."""
    return at.FNot(_fatom_was_cast_any())


def _fatom_not_first() -> at.FAtom:
    """'Except the first one you draw in each of your draw steps'
    (Teferi's Ageless Insight)."""
    return at.FAtom(at.FAtomPred.NOT_FIRST_DRAW_THIS_STEP, who=at.ControllerRef.YOU)


def _cpe_bare() -> at.CounterPlacedEvent:
    """Bare shape: no count key in the serialization."""
    return at.CounterPlacedEvent(at.CounterKind.PLUS_1_PLUS_1, _UNIVERSAL)


def _cpe_one_or_more() -> at.CounterPlacedEvent:
    """'One or more counters' (Conclave Mentor's trigger)."""
    return at.CounterPlacedEvent(
        at.CounterKind.PLUS_1_PLUS_1, _UNIVERSAL, count=at.QAtLeast(1)
    )


def _cpe_that_many() -> at.CounterPlacedEvent:
    """'That many' — the event's counter count."""
    return at.CounterPlacedEvent(
        at.CounterKind.PLUS_1_PLUS_1,
        _UNIVERSAL,
        count=at.QProp(referent="event", field=at.QPropField.COUNTER_COUNT),
    )


def _mentor_action_count() -> at.QBin:
    """Conclave Mentor's action count — 'that many plus one'."""
    return at.QBin(
        at.QBinOp.ADD,
        at.QProp(referent="event", field=at.QPropField.COUNTER_COUNT),
        at.QConst(1),
    )


def _lofty_selector() -> at.Selector:
    """The targeted spell (Lofty Denial) — a referent 'target' selector
    (CHOOSE + QConst(1) + neutral zone)."""
    return at.Selector(
        at.QConst(1),
        at.SelectorMode.CHOOSE,
        _UNIVERSAL,
        zones=(_NEUTRAL,),
        referent="target",
    )


def _lofty_condition() -> at.FAnd:
    """Lofty Denial s2 condition: a creature with flying you control."""
    return at.FAnd(
        (
            _CREATURE,
            at.FAtom(at.FAtomPred.KEYWORD_HAS, keyword=at.Keyword.FLYING),
            at.FAtom(at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
        )
    )


def _lofty_cm() -> at.CostModifier:
    """Lofty Denial s2 — the {1} of s1 becomes {4} under the
    condition: controller of the targeted spell pays +3 generic."""
    return at.CostModifier(
        at.FAtom(at.FAtomPred.IS_ANY_TARGET),
        _lofty_selector(),
        at.CostDeltaIncreaseGeneric(at.QConst(3)),
        condition=_lofty_condition(),
    )


def _cm_plain_ref() -> at.CostModifier:
    """Bare shape: controller_ref is a plain ControllerRef."""
    return at.CostModifier(
        at.FAtom(at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
        at.ControllerRef.YOU,
        at.CostDeltaIncreaseGeneric(at.QConst(3)),
    )


# ---- pinned fingerprints ---------------------------------------------------

_NEW_PINS: list[tuple[str, Callable[[], object], str]] = [
    (
        "cpe_bare",
        _cpe_bare,
        "8b93c87ed9e04dacc7ecfb4ab19a021433ea914601ac1d238b269fa898e8df75",
    ),
    (
        "cpe_one_or_more",
        _cpe_one_or_more,
        "9439c3a3a3651f18f439cee8835b3ea924398a9e142dcb2da2283a69aff2fc84",
    ),
    (
        "cpe_that_many",
        _cpe_that_many,
        "76d7a8b41225ad4b11aa54b01f08f2fe844c94bae08b13118f7bbd51434147d3",
    ),
    (
        "mentor_action_count",
        _mentor_action_count,
        "83a873ca2c161346d2a972a93108c8460fc83426612357d5e02fe12632068ef9",
    ),
    (
        "fatom_was_cast_any",
        _fatom_was_cast_any,
        "8ead4889e2002f6fc780676d726fda2db6b7654cd91f5b2d31afd3d5c40cbe8d",
    ),
    (
        "priest_condition",
        _priest_condition,
        "dbb8147826a4067b9156f0d2cbe749e00ffc2fb9422fa811d49c776c0964f7b4",
    ),
    (
        "fatom_not_first",
        _fatom_not_first,
        "25d14fa7a6cce26c3d1a5663370ac213b184faea1019fd359833c2bbe14b5b79",
    ),
    (
        "lofty_selector",
        _lofty_selector,
        "0a15788038321385d5fd2b9afd871544fb6971c67fe797054135c758c3fe96f6",
    ),
    (
        "lofty_cm",
        _lofty_cm,
        # The condition's FAnd children are sorted at construction by
        # canonical_json (docs/DESIGN_ATOM_ONTOLOGY.md §3), so the bytes follow
        # canonical order, not printed order. test_ability_tree_r7..r11 re-check
        # this list.
        "b7639782a262d52df2154dc40c6717214ce724bb912136f4ffdd387c33d872cd",
    ),
    (
        "cm_plain_ref",
        _cm_plain_ref,
        "19cb18459c5d02d817a466e8826b33e95f631f87ef85ac502f701cb6ce31cfdb",
    ),
]


# ---- tests ----------------------------------------------------------------


@pytest.mark.parametrize(
    "name,build,fp", R5._NEW_PINS, ids=[n for n, _, _ in R5._NEW_PINS]
)
def test_pinned_pre_r6_r5_fingerprint(
    name: str, build: Callable[[], object], fp: str
) -> None:
    """Byte stability: the test_ability_tree_r5 pin set keeps its
    fingerprints."""
    node = build()
    assert at.fingerprint(node) == fp
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d


@pytest.mark.parametrize(
    "name,build,fp", R4._NEW_PINS, ids=[n for n, _, _ in R4._NEW_PINS]
)
def test_pinned_pre_r6_r4_fingerprint(
    name: str, build: Callable[[], object], fp: str
) -> None:
    """Byte stability: the test_ability_tree_r4 pin set (bare CostModifier,
    the IOS FAtom, the COUNTER_SPELL atoms) keeps its fingerprints with
    CostModifier.controller_ref a ControllerRef | Selector union."""
    node = build()
    assert at.fingerprint(node) == fp
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d


@pytest.mark.parametrize("name,build,fp", _NEW_PINS, ids=[n for n, _, _ in _NEW_PINS])
def test_r6_roundtrip(name: str, build: Callable[[], object], fp: str) -> None:
    node = build()
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d
    back = at.from_dict(d["tag"], d)
    assert back == node, f"{name}: from_dict(to_dict(x)) != x"
    assert at.canonical_json(back) == at.canonical_json(node)
    assert at.fingerprint(back) == at.fingerprint(node) == fp


def test_cpe_omits_count_when_none() -> None:
    d = at.to_dict(_cpe_bare())
    assert set(d.keys()) == {"tag", "counter_kind", "filter"}, (
        f"bare CounterPlacedEvent must omit 'count': {sorted(d)}"
    )
    d = at.to_dict(_cpe_one_or_more())
    assert d["count"] == {"tag": "QAtLeast", "n": 1}
    d = at.to_dict(_cpe_that_many())
    assert d["count"]["tag"] == "QProp"


def test_cpe_explicit_none_equals_default() -> None:
    explicit = at.CounterPlacedEvent(
        at.CounterKind.PLUS_1_PLUS_1, _UNIVERSAL, count=None
    )
    default = _cpe_bare()
    assert explicit == default
    assert at.to_dict(explicit) == at.to_dict(default)
    assert at.fingerprint(explicit) == at.fingerprint(default)
    back = at.from_dict("CounterPlacedEvent", at.to_dict(default))
    assert back.count is None


def test_qprop_counter_count_event_only() -> None:
    """COUNTER_COUNT on the event referent: "that many" is the event's
    counter count (Conclave Mentor)."""
    node = at.QProp(referent="event", field=at.QPropField.COUNTER_COUNT)
    d = at.to_dict(node)
    assert d["field"] == {"tag": "QPropField", "name": "COUNTER_COUNT"}
    assert at.from_dict("QProp", d) == node
    back = at.from_dict("QBin", at.to_dict(_mentor_action_count()))
    assert back == _mentor_action_count()
    assert isinstance(back.left, at.QProp)
    assert back.left.field is at.QPropField.COUNTER_COUNT


def test_fatom_was_cast_this_turn_rules() -> None:
    """The predicate takes exactly {who}; who=ANY = cast by anyone; the
    who slot accepts a referent Selector."""
    assert at._FATOM_RULES[at.FAtomPred.WAS_CAST_THIS_TURN] == (
        frozenset({"who"}),
        frozenset({"who"}),
    )
    node = _fatom_was_cast_any()
    assert node.who is at.ControllerRef.ANY
    d = at.to_dict(node)
    # the zone slots are omitted when None; count still serializes its
    # null default
    assert d["who"] == {"tag": "ControllerRef", "name": "ANY"}
    assert "zone" not in d and d["count"] is None
    sel = at.Selector(
        at.QConst(1),
        at.SelectorMode.CHOOSE,
        _UNIVERSAL,
        zones=(_NEUTRAL,),
        referent="controller",
    )
    with_sel = at.FAtom(at.FAtomPred.WAS_CAST_THIS_TURN, who=sel)
    assert at.from_dict("FAtom", at.to_dict(with_sel)) == with_sel
    # the negated template condition round-trips
    cond = _priest_condition()
    d = at.to_dict(cond)
    assert d["tag"] == "FNot"
    assert at.from_dict(d["tag"], d) == cond


def test_fatom_not_first_draw_this_step_rules() -> None:
    """The predicate takes exactly {who}, evaluated against the drawn card
    (the CardDrawnEvent subject)."""
    assert at._FATOM_RULES[at.FAtomPred.NOT_FIRST_DRAW_THIS_STEP] == (
        frozenset({"who"}),
        frozenset({"who"}),
    )
    node = _fatom_not_first()
    assert node.who is at.ControllerRef.YOU
    d = at.to_dict(node)
    assert d["who"] == {"tag": "ControllerRef", "name": "YOU"}
    assert "zone" not in d and d["count"] is None


def test_costmodifier_selector_roundtrip() -> None:
    """A Selector controller_ref round-trips as a Selector, alongside the
    plain-ControllerRef spelling."""
    node = _lofty_cm()
    d = at.to_dict(node)
    assert d["controller_ref"]["tag"] == "Selector"
    back = at.from_dict("CostModifier", d)
    assert back == node
    assert isinstance(back.controller_ref, at.Selector)
    assert back.controller_ref.referent == "target"
    # the plain-ControllerRef spelling still decodes (byte-stable)
    plain = _cm_plain_ref()
    d = at.to_dict(plain)
    assert d["controller_ref"] == {"tag": "ControllerRef", "name": "YOU"}
    assert at.from_dict("CostModifier", d) == plain


def test_r6_table_members() -> None:
    assert at.QPropField.COUNTER_COUNT.value == "COUNTER_COUNT"
    assert at.FAtomPred.WAS_CAST_THIS_TURN.value == "WAS_CAST_THIS_TURN"
    assert at.FAtomPred.NOT_FIRST_DRAW_THIS_STEP.value == "NOT_FIRST_DRAW_THIS_STEP"
    assert at._OMIT_IF_EMPTY["CounterPlacedEvent"] == frozenset({"count"})


def _rejection_cases() -> list[tuple[str, Callable[[], object]]]:
    return [
        # WAS_CAST_THIS_TURN slot arity
        (
            "was_cast_missing_who",
            lambda: at.FAtom(at.FAtomPred.WAS_CAST_THIS_TURN),
        ),
        (
            "was_cast_unrequested_count",
            lambda: at.FAtom(
                at.FAtomPred.WAS_CAST_THIS_TURN,
                who=at.ControllerRef.YOU,
                count=at.QConst(1),
            ),
        ),
        (
            "was_cast_unrequested_zone",
            lambda: at.FAtom(
                at.FAtomPred.WAS_CAST_THIS_TURN,
                who=at.ControllerRef.YOU,
                zone=at.Zone(at.ZoneKind.HAND, at.ControllerRef.YOU),
            ),
        ),
        # NOT_FIRST_DRAW_THIS_STEP slot arity
        (
            "not_first_missing_who",
            lambda: at.FAtom(at.FAtomPred.NOT_FIRST_DRAW_THIS_STEP),
        ),
        (
            "not_first_unrequested_count",
            lambda: at.FAtom(
                at.FAtomPred.NOT_FIRST_DRAW_THIS_STEP,
                who=at.ControllerRef.YOU,
                count=at.QConst(1),
            ),
        ),
        # CounterPlacedEvent.count validation
        (
            "cpe_count_int",
            lambda: at.CounterPlacedEvent(
                at.CounterKind.PLUS_1_PLUS_1,
                _UNIVERSAL,
                count=3,  # type: ignore[arg-type]
            ),
        ),
        (
            "cpe_count_str",
            lambda: at.CounterPlacedEvent(
                at.CounterKind.PLUS_1_PLUS_1,
                _UNIVERSAL,
                count="3",  # type: ignore[arg-type]
            ),
        ),
        # QPropField.COUNTER_COUNT takes the "event", "source" or "target"
        # referent (test_ability_tree_r8/r9 pin the last two); the controller
        # and a Selector are rejected.
        (
            "qprop_cc_controller",
            lambda: at.QProp(referent="controller", field=at.QPropField.COUNTER_COUNT),
        ),
        (
            "qprop_cc_selector_referent",
            lambda: at.QProp(
                referent=at.Selector(
                    at.QConst(1),
                    at.SelectorMode.CHOOSE,
                    _UNIVERSAL,
                    zones=(_NEUTRAL,),
                    referent="event",
                ),
                field=at.QPropField.COUNTER_COUNT,
            ),
        ),
        # CostModifier.controller_ref union boundary
        (
            "cm_controllerref_qconst",
            lambda: at.CostModifier(
                _UNIVERSAL,
                at.QConst(1),  # type: ignore[arg-type]
                at.CostDeltaIncreaseGeneric(at.QConst(3)),
            ),
        ),
        (
            "cm_controllerref_str",
            lambda: at.CostModifier(
                _UNIVERSAL,
                "you",  # type: ignore[arg-type]
                at.CostDeltaIncreaseGeneric(at.QConst(3)),
            ),
        ),
    ]


@pytest.mark.parametrize(
    "name,fn", _rejection_cases(), ids=[n for n, _ in _rejection_cases()]
)
def test_r6_rejections(name: str, fn: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        fn()
