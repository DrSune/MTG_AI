"""Grammar round 6 — five additive items (2026-09-28).

Round-6 scope (spec: KNOWLEDGE/2026-09-28/01-grammar-round6-decision.md;
file-name offset is intentional — round-5 grammar shipped in the r6 file):

- R6-1: ``FAtomPred.TURN_OF`` — required ``who`` — "it is <who>'s turn"
  ("During your turn, …"; Radha, Heart of Keld; Discontinuity — the Phase
  enum carries no turn owner).
- R6-2: ``FAtomPred.ZONE_COUNT_GE`` — required ``who`` + ``zone`` +
  ``inner_filter`` + ``count`` — "<who> has >= count cards in their
  <zone> matching inner_filter" (Thieves' Guild Enforcer: "an opponent
  has 8 or more cards in their graveyard").
- R6-3: ``_VERB_ROLES[SET_PT]`` — power/toughness each become optional,
  but the at-least-one-role check (previously MODIFY_PT-only) is
  extended to SET_PT: a zero-role SET_PT raises. Validation-only —
  both-role SET_PT (the only pre-r6 shape in the templates) is
  serialization-untouched.
- R6-4: ``DeclareBlockersEvent.blocked: Filter | None = None`` — narrows
  the BLOCKED-side creature ("can't be blocked"; Tome Anima, Ghostly
  Pilferer, Subira, Shacklegeist); ``opt:filter`` + omit-if-empty.
- R6-5: ``Verb.MANDATE_BLOCK`` — "must be blocked if able" (Canopy
  Stalker); ``_VERB_ROLES`` row mirrors MANDATE_ATTACK exactly.

Guards:
- every pre-round-6 pinned fingerprint (the round-6 pin set) stays
  byte-identical — all five items are additive;
- bare constructs (DeclareBlockersEvent without blocked) serialize
  WITHOUT the new key — pinned against explicit expected dicts;
- round-6 constructs round-trip through ``to_dict``/``from_dict`` with
  pinned fingerprints;
- rejections at every new or widened validation point (``ValueError``,
  per the module-wide convention).
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

import MTG_bot.core.ability_tree as at
import MTG_bot.core.test_ability_tree_r6 as R6

# ---- builders for the round-6 constructs -----------------------------------

_UNIVERSAL = at.FAnd(())
_NEUTRAL = at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY)
_BF_YOU = at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU)
_GY_OPP = at.Zone(at.ZoneKind.GRAVEYARD, at.ControllerRef.OPPONENT)
_IS_SOURCE = at.FAtom(at.FAtomPred.IS_SOURCE)


def _src_sel() -> at.Selector:
    """The classic "this permanent" selector (r6-file idiom)."""
    return at.Selector(at.QConst(1), at.SelectorMode.ALL, _IS_SOURCE, zones=(_BF_YOU,))


def _fatom_turn_of_you() -> at.FAtom:
    """R6-1: "it is your turn" — the Radha/Discontinuity condition."""
    return at.FAtom(at.FAtomPred.TURN_OF, who=at.ControllerRef.YOU)


def _fatom_zone_count_ge() -> at.FAtom:
    """R6-2: "an opponent has 8 or more cards in their graveyard"
    (Thieves' Guild Enforcer's condition)."""
    return at.FAtom(
        at.FAtomPred.ZONE_COUNT_GE,
        who=at.ControllerRef.OPPONENT,
        zone=_GY_OPP,
        inner_filter=_UNIVERSAL,
        count=at.QConst(8),
    )


def _target_sel() -> at.Selector:
    """A creature-target selector for the SET_PT atoms."""
    return at.Selector(
        at.QConst(1),
        at.SelectorMode.TARGET,
        at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(_BF_YOU,),
    )


def _set_pt_power_only() -> at.Atom:
    """R6-3: Kinetic Augur — "power is equal to the number of …": the
    single-component (power-only) SET_PT that r6 unblocks."""
    return at.Atom(
        at.Verb.SET_PT,
        at.AtomArgs(pairs=(("target", _target_sel()), ("power", at.QConst(4)))),
    )


def _set_pt_toughness_only() -> at.Atom:
    """R6-3: the mirrored single-component case (toughness-only)."""
    return at.Atom(
        at.Verb.SET_PT,
        at.AtomArgs(pairs=(("target", _target_sel()), ("toughness", at.QConst(3)))),
    )


def _set_pt_both() -> at.Atom:
    """Pre-r6 shape: both roles set — the only SET_PT spelling the
    pre-batch templates ever built; validation-only change, untouched."""
    return at.Atom(
        at.Verb.SET_PT,
        at.AtomArgs(
            pairs=(
                ("target", _target_sel()),
                ("power", at.QConst(4)),
                ("toughness", at.QConst(3)),
            )
        ),
    )


def _dbe_bare() -> at.DeclareBlockersEvent:
    """Pre-r3b shape: neither subject nor blocked — no key for either."""
    return at.DeclareBlockersEvent(_UNIVERSAL)


def _dbe_subject() -> at.DeclareBlockersEvent:
    """Pre-r6 shape: subject only — the serialization must not gain a
    'blocked' key (byte-stability guard)."""
    return at.DeclareBlockersEvent(_UNIVERSAL, subject=_IS_SOURCE)


def _dbe_blocked() -> at.DeclareBlockersEvent:
    """R6-4: "can't be blocked" — the prevented declaration where the
    blocked side is the source (Tome Anima / Ghostly Pilferer idiom)."""
    return at.DeclareBlockersEvent(_UNIVERSAL, blocked=_IS_SOURCE)


def _dbe_both() -> at.DeclareBlockersEvent:
    """R6-4 with subject kept: "can block only creatures with flying"
    (Shacklegeist): blocker=source, blocked-side narrowed by the filter."""
    return at.DeclareBlockersEvent(_UNIVERSAL, subject=_IS_SOURCE, blocked=_IS_SOURCE)


def _mandate_block() -> at.Atom:
    """R6-5: "must be blocked if able" (Canopy Stalker)."""
    return at.Atom(at.Verb.MANDATE_BLOCK, at.AtomArgs(pairs=(("cards", _src_sel()),)))


# ---- pinned fingerprints (captured after the round-6 edits) ----------------

_NEW_PINS: list[tuple[str, Callable[[], object], str]] = [
    (
        "fatom_turn_of_you",
        _fatom_turn_of_you,
        "d79cc84efcad0b86ea94d05d23751928c2a2d7120c96db7aae3ea02e35879091",
    ),
    (
        "fatom_zone_count_ge",
        _fatom_zone_count_ge,
        "5382a52e870bcdf8131a54d2b129fb3649f0b541386781f05659f49e7cddc8bf",
    ),
    (
        "set_pt_power_only",
        _set_pt_power_only,
        "fc035267e323ee389d36d38b2f30ce97dab89b641a9d50d6a543f9c7efb3017e",
    ),
    (
        "set_pt_toughness_only",
        _set_pt_toughness_only,
        "095d077317b9b5522136264cac1e174e81654b40967485183cfb921b30d8951d",
    ),
    (
        "set_pt_both",
        _set_pt_both,
        "a1eaac50d1ff4934766d70ff24f884f36b7926af3bab7e4672b755cd0dcbc0fa",
    ),
    (
        "dbe_bare",
        _dbe_bare,
        "953d48daab9061c2aa8c1b1c073296b63c6e364653a8cee0fad8b14fc111431c",
    ),
    (
        "dbe_subject",
        _dbe_subject,
        "68aa98a20f8adcd6ce364eebe4b7113c34889a8ba070290a0d02c683df2180a8",
    ),
    (
        "dbe_blocked",
        _dbe_blocked,
        "f842d378e398972ec144b748dfaa1827e7b19d6e3ee684061d587b18cc5a6873",
    ),
    (
        "mandate_block",
        _mandate_block,
        "5e5b56b51df84f35cec57b5d22d1ef9a68e574307fb5d1ff12bca1aaa94ea395",
    ),
]


# ---- tests ----------------------------------------------------------------


@pytest.mark.parametrize(
    "name,build,fp", R6._NEW_PINS, ids=[n for n, _, _ in R6._NEW_PINS]
)
def test_pinned_pre_r7_r6_fingerprint(
    name: str, build: Callable[[], object], fp: str
) -> None:
    """Byte stability: every pre-round-6 pinned tree (the round-6 pin set)
    serializes identically — all five round-6 items are additive."""
    node = build()
    assert at.fingerprint(node) == fp
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d


@pytest.mark.parametrize("name,build,fp", _NEW_PINS, ids=[n for n, _, _ in _NEW_PINS])
def test_r7_roundtrip(name: str, build: Callable[[], object], fp: str) -> None:
    node = build()
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d
    back = at.from_dict(d["tag"], d)
    assert back == node, f"{name}: from_dict(to_dict(x)) != x"
    assert at.canonical_json(back) == at.canonical_json(node)
    assert at.fingerprint(back) == at.fingerprint(node) == fp


def test_fatom_turn_of_rules() -> None:
    """R6-1: the predicate takes exactly {who} (CONTROLLER_IS pattern);
    the who slot accepts a referent Selector (round-4 anaphora)."""
    assert at._FATOM_RULES[at.FAtomPred.TURN_OF] == (
        frozenset({"who"}),
        frozenset({"who"}),
    )
    node = _fatom_turn_of_you()
    d = at.to_dict(node)
    assert d["who"] == {"tag": "ControllerRef", "name": "YOU"}
    assert "zone" not in d and d["count"] is None
    sel = at.Selector(
        at.QConst(1),
        at.SelectorMode.CHOOSE,
        _UNIVERSAL,
        zones=(_NEUTRAL,),
        referent="controller",
    )
    with_sel = at.FAtom(at.FAtomPred.TURN_OF, who=sel)
    assert at.from_dict("FAtom", at.to_dict(with_sel)) == with_sel


def test_fatom_zone_count_ge_rules() -> None:
    """R6-2: required==allowed=={who, zone, inner_filter, count}
    (CONTROLLER_COUNT_GE style plus the required who/zone slots)."""
    assert at._FATOM_RULES[at.FAtomPred.ZONE_COUNT_GE] == (
        frozenset({"who", "zone", "inner_filter", "count"}),
        frozenset({"who", "zone", "inner_filter", "count"}),
    )
    node = _fatom_zone_count_ge()
    d = at.to_dict(node)
    assert d["who"] == {"tag": "ControllerRef", "name": "OPPONENT"}
    assert d["zone"]["tag"] == "Zone"
    assert d["zone"]["kind"] == {"tag": "ZoneKind", "name": "GRAVEYARD"}
    assert d["inner_filter"] == {"tag": "FAnd", "children": []}
    assert d["count"] == {"tag": "QConst", "value": 8}
    assert "from_zone" not in d and "to_zone" not in d


def test_set_pt_single_role_builds() -> None:
    """R6-3: power-only and toughness-only SET_PT atoms build, carry the
    right pair set, and round-trip."""
    for node, role in (
        (_set_pt_power_only(), "power"),
        (_set_pt_toughness_only(), "toughness"),
    ):
        roles = dict(node.args.pairs)
        assert set(roles) == {"target", role}
        d = at.to_dict(node)
        assert len(d["args"]["pairs"]) == 2
        assert at.from_dict("Atom", d) == node
    both = _set_pt_both()
    assert set(dict(both.args.pairs)) == {"target", "power", "toughness"}
    assert at.from_dict("Atom", at.to_dict(both)) == both


def test_set_pt_zero_role_raises_message() -> None:
    """R6-3: the extended at-least-one check fires on SET_PT with the
    class-prefixed message style."""
    with pytest.raises(ValueError, match="SET_PT needs at least one"):
        at.Atom(at.Verb.SET_PT, at.AtomArgs(pairs=(("target", _target_sel()),)))


def test_modify_pt_zero_role_unchanged() -> None:
    """R6-3 regression: the MODIFY_PT at-least-one error message is
    byte-identical to the pre-r6 wording."""
    with pytest.raises(
        ValueError,
        match="Atom: MODIFY_PT needs at least one of power/toughness",
    ):
        at.Atom(at.Verb.MODIFY_PT, at.AtomArgs(pairs=(("target", _target_sel()),)))


def test_dbe_omits_blocked_when_none() -> None:
    """R6-4 byte-stability guard: the pre-r6 constructions serialize to
    EXACTLY their pre-r6 dicts — no 'blocked' key appears."""
    assert at.to_dict(_dbe_bare()) == {
        "tag": "DeclareBlockersEvent",
        "filter": {"tag": "FAnd", "children": []},
    }
    subject_dict = at.to_dict(_dbe_subject())
    assert "blocked" not in subject_dict
    assert set(subject_dict) == {"tag", "filter", "subject"}
    # pre-r3b / pre-r6 fingerprints pinned above cover the byte level


def test_dbe_blocked_roundtrip_and_none_default() -> None:
    """R6-4: blocked=<filter> round-trips; an absent key decodes to None;
    explicit None equals the default spelling."""
    node = _dbe_blocked()
    d = at.to_dict(node)
    assert "blocked" in d and d["blocked"]["tag"] == "FAtom"
    assert at.from_dict("DeclareBlockersEvent", d) == node
    both = _dbe_both()
    assert at.from_dict("DeclareBlockersEvent", at.to_dict(both)) == both
    back = at.from_dict("DeclareBlockersEvent", at.to_dict(_dbe_bare()))
    assert back.blocked is None and back.subject is None
    explicit = at.DeclareBlockersEvent(_UNIVERSAL, blocked=None)
    assert explicit == _dbe_bare()
    assert at.to_dict(explicit) == at.to_dict(_dbe_bare())
    assert at.fingerprint(explicit) == at.fingerprint(_dbe_bare())


def test_mandate_block_roles_mirror_attack() -> None:
    """R6-5: the MANDATE_BLOCK role row mirrors MANDATE_ATTACK exactly;
    optional controller/duration build and round-trip."""
    assert (
        at._VERB_ROLES[at.Verb.MANDATE_BLOCK] == at._VERB_ROLES[at.Verb.MANDATE_ATTACK]
    )
    assert at._VERB_ROLES[at.Verb.MANDATE_BLOCK] == {
        "cards": True,
        "controller": False,
        "duration": False,
    }
    full = at.Atom(
        at.Verb.MANDATE_BLOCK,
        at.AtomArgs(
            pairs=(
                ("cards", _src_sel()),
                ("controller", at.ControllerRef.YOU),
                ("duration", at.DurationEot()),
            )
        ),
    )
    assert at.from_dict("Atom", at.to_dict(full)) == full


def test_r7_table_members() -> None:
    assert at.FAtomPred.TURN_OF.value == "TURN_OF"
    assert at.FAtomPred.ZONE_COUNT_GE.value == "ZONE_COUNT_GE"
    assert at.Verb.MANDATE_BLOCK.value == "MANDATE_BLOCK"
    assert at._OMIT_IF_EMPTY["DeclareBlockersEvent"] == frozenset(
        {"subject", "blocked"}
    )
    spec = dict(at._SPECS["DeclareBlockersEvent"])
    assert spec["blocked"] == "opt:filter"


def _rejection_cases() -> list[tuple[str, Callable[[], object]]]:
    return [
        # R6-1: TURN_OF slot arity
        (
            "turn_of_missing_who",
            lambda: at.FAtom(at.FAtomPred.TURN_OF),
        ),
        (
            "turn_of_unrequested_count",
            lambda: at.FAtom(
                at.FAtomPred.TURN_OF, who=at.ControllerRef.YOU, count=at.QConst(1)
            ),
        ),
        # R6-2: ZONE_COUNT_GE slot arity + slot value types
        (
            "zc_missing_who",
            lambda: at.FAtom(
                at.FAtomPred.ZONE_COUNT_GE,
                zone=_GY_OPP,
                inner_filter=_UNIVERSAL,
                count=at.QConst(8),
            ),
        ),
        (
            "zc_missing_zone",
            lambda: at.FAtom(
                at.FAtomPred.ZONE_COUNT_GE,
                who=at.ControllerRef.OPPONENT,
                inner_filter=_UNIVERSAL,
                count=at.QConst(8),
            ),
        ),
        (
            "zc_missing_inner_filter",
            lambda: at.FAtom(
                at.FAtomPred.ZONE_COUNT_GE,
                who=at.ControllerRef.OPPONENT,
                zone=_GY_OPP,
                count=at.QConst(8),
            ),
        ),
        (
            "zc_unrequested_string_value",
            lambda: at.FAtom(
                at.FAtomPred.ZONE_COUNT_GE,
                who=at.ControllerRef.OPPONENT,
                zone=_GY_OPP,
                inner_filter=_UNIVERSAL,
                count=at.QConst(8),
                string_value="Creature",
            ),
        ),
        (
            "zc_count_int",
            lambda: at.FAtom(
                at.FAtomPred.ZONE_COUNT_GE,
                who=at.ControllerRef.OPPONENT,
                zone=_GY_OPP,
                inner_filter=_UNIVERSAL,
                count=8,  # type: ignore[arg-type]
            ),
        ),
        (
            "zc_zone_enum_not_zone",
            lambda: at.FAtom(
                at.FAtomPred.ZONE_COUNT_GE,
                who=at.ControllerRef.OPPONENT,
                zone=at.ZoneKind.GRAVEYARD,  # type: ignore[arg-type]
                inner_filter=_UNIVERSAL,
                count=at.QConst(8),
            ),
        ),
        # R6-3: SET_PT at-least-one-role
        (
            "set_pt_zero_role",
            lambda: at.Atom(
                at.Verb.SET_PT, at.AtomArgs(pairs=(("target", _target_sel()),))
            ),
        ),
        # R6-3: role value types unchanged
        (
            "set_pt_power_string",
            lambda: at.AtomArgs(pairs=(("power", "four"),)),  # type: ignore[list-item]
        ),
        # R6-4: DeclareBlockersEvent.blocked validation
        (
            "dbe_blocked_int",
            lambda: at.DeclareBlockersEvent(_UNIVERSAL, blocked=3),  # type: ignore[arg-type]
        ),
        (
            "dbe_blocked_str",
            lambda: at.DeclareBlockersEvent(_UNIVERSAL, blocked="flying"),  # type: ignore[arg-type]
        ),
        # R6-5: MANDATE_BLOCK role arity (cards required, mirror of attack)
        (
            "mandate_block_missing_cards",
            lambda: at.Atom(at.Verb.MANDATE_BLOCK, at.AtomArgs(pairs=())),
        ),
        (
            "mandate_block_target_role",
            lambda: at.Atom(
                at.Verb.MANDATE_BLOCK,
                at.AtomArgs(pairs=(("target", _target_sel()),)),
            ),
        ),
    ]


@pytest.mark.parametrize(
    "name,fn", _rejection_cases(), ids=[n for n, _ in _rejection_cases()]
)
def test_r7_rejections(name: str, fn: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        fn()
