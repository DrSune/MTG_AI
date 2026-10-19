"""Grammar round 5 — four additive items (2026-09-25).

Round-5 scope (spec: KNOWLEDGE/2026-09-24/07-round5-replacement-decision.md):

- R5-1: ``FAtomPred.WAS_CAST_THIS_TURN`` — required ``who`` — "[the object]
  was cast this turn (by who)" (Containment Priest; who=ANY = cast by
  anyone; the "and it wasn't cast" condition is
  ``FNot(FAtom(WAS_CAST_THIS_TURN, who=ANY))``). Zone-agnostic — distinct
  from the zone-slot-bearing ``CAST_THIS_TURN_FROM`` (round 4).
- R5-2: ``CounterPlacedEvent.count: Quantity | None = None`` — the number
  placed ("one or more" = ``QAtLeast(1)``); ``opt:quantity`` +
  omit-if-empty; plus the new ``QPropField.COUNTER_COUNT`` — "that many" =
  ``QProp("event", COUNTER_COUNT)`` (the event's counter count;
  event-referent only, like ``AMOUNT``; Conclave Mentor).
- R5-3: ``CostModifier.controller_ref`` widened to
  ``ControllerRef | Selector`` — convention C7: a Selector means the
  controller of the selected object, and the modifier applies to costs
  that controller pays FOR the filtered object, including ``unless``
  payments (Lofty Denial); reuses the ``controller_ref_or_selector``
  dual conv (shared with FAtom.who since round 4).
- R5-4: ``FAtomPred.NOT_FIRST_DRAW_THIS_STEP`` — required ``who`` — "not
  the first card who draws in their draw step" (Teferi's Ageless Insight;
  evaluated against the drawn card, the CardDrawnEvent subject).

Guards:
- every pre-round-5 pinned fingerprint (the round-5 and round-4 pin sets)
  stays byte-identical — all four items are additive;
- bare constructs (count=None / controller_ref=ControllerRef / no who)
  serialize WITHOUT the new keys;
- round-5 constructs round-trip through ``to_dict``/``from_dict`` with
  pinned fingerprints;
- rejections at every new or widened validation point (``ValueError``,
  per the module-wide convention).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

import MTG_bot.core.ability_tree as at
import MTG_bot.core.test_ability_tree_r4 as R4
import MTG_bot.core.test_ability_tree_r5 as R5

# ---- builders for the round-5 constructs -----------------------------------

_UNIVERSAL = at.FAnd(())
_NEUTRAL = at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY)
_CREATURE = at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature")


def _fatom_was_cast_any() -> at.FAtom:
    """R5-1: 'a creature that wasn't cast (by anyone)' — the atom before
    negation (Containment Priest)."""
    return at.FAtom(at.FAtomPred.WAS_CAST_THIS_TURN, who=at.ControllerRef.ANY)


def _priest_condition() -> at.FNot:
    """R5-1: 'it wasn't cast' — the negated form the template uses."""
    return at.FNot(_fatom_was_cast_any())


def _fatom_not_first() -> at.FAtom:
    """R5-4: 'except the first one you draw in each of your draw steps'
    (Teferi's Ageless Insight)."""
    return at.FAtom(at.FAtomPred.NOT_FIRST_DRAW_THIS_STEP, who=at.ControllerRef.YOU)


def _cpe_bare() -> at.CounterPlacedEvent:
    """Pre-round-5 shape: no count key in the serialization."""
    return at.CounterPlacedEvent(at.CounterKind.PLUS_1_PLUS_1, _UNIVERSAL)


def _cpe_one_or_more() -> at.CounterPlacedEvent:
    """R5-2: 'one or more counters' (Conclave Mentor's trigger)."""
    return at.CounterPlacedEvent(
        at.CounterKind.PLUS_1_PLUS_1, _UNIVERSAL, count=at.QAtLeast(1)
    )


def _cpe_that_many() -> at.CounterPlacedEvent:
    """R5-2: 'that many' — the event's counter count."""
    return at.CounterPlacedEvent(
        at.CounterKind.PLUS_1_PLUS_1,
        _UNIVERSAL,
        count=at.QProp(referent="event", field=at.QPropField.COUNTER_COUNT),
    )


def _mentor_action_count() -> at.QBin:
    """R5-2: Conclave Mentor's action count — 'that many plus one'."""
    return at.QBin(
        at.QBinOp.ADD,
        at.QProp(referent="event", field=at.QPropField.COUNTER_COUNT),
        at.QConst(1),
    )


def _lofty_selector() -> at.Selector:
    """R5-3: the targeted spell (Lofty Denial) — referent 'target' under
    convention C2 (CHOOSE + QConst(1) + neutral zone)."""
    return at.Selector(
        at.QConst(1),
        at.SelectorMode.CHOOSE,
        _UNIVERSAL,
        _NEUTRAL,
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
    """R5-3: Lofty Denial s2 — the {1} of s1 becomes {4} under the
    condition: controller of the targeted spell pays +3 generic."""
    return at.CostModifier(
        at.FAtom(at.FAtomPred.IS_ANY_TARGET),
        _lofty_selector(),
        at.CostDeltaIncreaseGeneric(at.QConst(3)),
        condition=_lofty_condition(),
    )


def _cm_plain_ref() -> at.CostModifier:
    """Pre-round-5 shape: controller_ref is a plain ControllerRef."""
    return at.CostModifier(
        at.FAtom(at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
        at.ControllerRef.YOU,
        at.CostDeltaIncreaseGeneric(at.QConst(3)),
    )


# ---- pinned fingerprints (captured after the round-5 edits) ----------------

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
        "3d782a84ed9ca88a3627e5b7ac8cb94545df9433b98346ece6f509bbfe319973",
    ),
    (
        "lofty_cm",
        _lofty_cm,
        # R1a canonicalization re-pin (2026-10-19, docs/DESIGN_ATOM_ONTOLOGY.md
        # §3 SET-R1a): the condition's FAnd children are construction-sorted by
        # canonical_json. Audited permutation-only — pre/post leaf multisets are
        # equal (8 leaves), so this is byte-order, not content (old value
        # e791b88db55731cebe3acd11981ef150332fb89aa1b0a59be269facc019914ee).
        # Reuses this list: test_ability_tree_r7..r11 re-pin with it.
        "2ef580a284db9fbee7407cf943f8929d182d6941957d1517935d2898ddba3aba",
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
    """Byte stability: every pre-round-5 pinned tree (the round-5 pin set)
    serializes identically — all four round-5 items are additive."""
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
    """Byte stability: the round-4 pin set (bare CostModifier, the IOS
    FAtom, the COUNTER_SPELL atoms) stays byte-identical under the R5-3
    union widening of CostModifier.controller_ref."""
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
    """R5-2: COUNTER_COUNT, like AMOUNT, only makes sense on the event
    referent (the event's counter count)."""
    node = at.QProp(referent="event", field=at.QPropField.COUNTER_COUNT)
    d = at.to_dict(node)
    assert d["field"] == {"tag": "QPropField", "name": "COUNTER_COUNT"}
    assert at.from_dict("QProp", d) == node
    back = at.from_dict("QBin", at.to_dict(_mentor_action_count()))
    assert back == _mentor_action_count()
    assert isinstance(back.left, at.QProp)
    assert back.left.field is at.QPropField.COUNTER_COUNT


def test_fatom_was_cast_this_turn_rules() -> None:
    """R5-1: the predicate takes exactly {who}; who=ANY = cast by anyone;
    the who slot accepts a referent Selector (round-4 anaphora)."""
    assert at._FATOM_RULES[at.FAtomPred.WAS_CAST_THIS_TURN] == (
        frozenset({"who"}),
        frozenset({"who"}),
    )
    node = _fatom_was_cast_any()
    assert node.who is at.ControllerRef.ANY
    d = at.to_dict(node)
    # zone slots are the only FAtom slots omitted when None; the other
    # slots (count, ...) still serialize their null defaults (byte-stable)
    assert d["who"] == {"tag": "ControllerRef", "name": "ANY"}
    assert "zone" not in d and d["count"] is None
    sel = at.Selector(
        at.QConst(1),
        at.SelectorMode.CHOOSE,
        _UNIVERSAL,
        _NEUTRAL,
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
    """R5-4: the predicate takes exactly {who}, evaluated against the
    drawn card (the CardDrawnEvent subject)."""
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
    """R5-3: a Selector controller_ref (convention C7) round-trips as a
    Selector, alongside the plain-ControllerRef spelling."""
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
        # R5-1: WAS_CAST_THIS_TURN slot arity
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
        # R5-4: NOT_FIRST_DRAW_THIS_STEP slot arity
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
        # R5-2: CounterPlacedEvent.count validation
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
        # R5-2: QPropField.COUNTER_COUNT event-referent coupling
        # ("qprop_cc_source" removed by grammar round 7, R7-9b: the
        # "source" referent is now LEGAL — Malefic Scythe's "for each soul
        # counter on this Equipment"; r8 pins the relaxed behaviour. The
        # non-source rejections below still hold.)
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
                    _NEUTRAL,
                    referent="event",
                ),
                field=at.QPropField.COUNTER_COUNT,
            ),
        ),
        # R5-3: CostModifier.controller_ref union boundary
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
