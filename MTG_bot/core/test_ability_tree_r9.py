"""Grammar round 8 / phase 8-A — eleven additive items (2026-09-28).

Round-8 scope (spec: KNOWLEDGE 2026-09-28/08; file-name offset is
intentional — round-8 grammar ships in the r9 file, following the
r6-in-r7 / r7-in-r8 precedent):

- R8-1: ``QAtMost(n)`` (n >= 1) — convention C17: with a TARGET-mode
  Selector it is the legal designation of "up to n targets" (1..n
  chosen, 0..remaining resolved); resolution-time "up to" stays CHOOSE.
- R8-2/R8-4: ``TokenSpec.color`` / ``enters_tapped`` / ``enters_attacking``
  trailing optionals (Basri Ket [-2] tokens; ontology R5-11 replaced ``color``
  with the WUBRG tuple ``colors``, omitted when empty), omit-when-None with the
  DUAL registration (_SPECS opt-tags + the NEW _OMIT_IF_EMPTY TokenSpec
  row) — the bare-token byte-shape pin below is the golden-storm guard.
- R8-3: AtomArgs ``color`` vocabulary += ``"ANY"`` ("mana of any one
  color"), distinct from colourless ``"C"`` (C-3 collapse repair; the
  template rows flip in 8-B, not here).
- R8-5: DEAL_DAMAGE optional ``dealer`` / ``recipient`` roles
  (ControllerRef | Selector | Filter — "damage to you" restrictions,
  Nine Lives).
- R8-6: ``FAtomPred.IS_EXILED_WITH_SOURCE`` (no slots; Horizon Scholar /
  Idol of Endurance permission scoping).
- R8-7: ``Verb.GET_EMBLEM`` — role-LESS marker mirroring FLIP_COIN
  exactly (C19: the emblem payload is the card-level attach; the quoted
  text never enters the IR).
- R8-8: ``Verb.ADD_LAND_PLAY`` {count?, duration?} (Azusa, Lost but
  Seeking; executor deferred per the FIGHT orphan precedent).
- R8-9: ``FAtomPred.CONTROLLER_COUNT_GT`` — the dual-filter comparison
  via the new trailing ``FAtom.right_inner_filter`` slot (omit-when-
  None, byte-stable); both filters REQUIRED.
- R8-10: ``ThisTurnKind.NONCOMBAT_DAMAGE`` (Chandra's Incinerator {X}).
- R8-11: ``QProp`` COUNTER_COUNT widened to the "target" referent
  (Invigorating Surge's "double that many counters").

Guards:
- every pre-round-8 pinned fingerprint (the r6 + r7 + r8 pin sets)
  stays byte-identical — all eleven items are additive;
- the bare TokenSpec serializes WITHOUT the three new keys — pinned
  against an explicit expected dict (dual-registration PITFALLS
  2026-09-28: missing the _OMIT_IF_EMPTY row = golden storm);
- the bare FAtom serializes WITHOUT right_inner_filter;
- round-8 constructs round-trip through ``to_dict``/``from_dict`` with
  pinned fingerprints; rejections at every new validation point.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

import MTG_bot.core.ability_tree as at
import MTG_bot.core.test_ability_tree_r6 as R6
import MTG_bot.core.test_ability_tree_r7 as R7
import MTG_bot.core.test_ability_tree_r8 as R8

# ---- builders for the round-8 constructs ------------------------------------

_UNIVERSAL = at.FAnd(())
_NEUTRAL = at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY)
_BF_YOU = at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU)
_CREATURE = at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature")


def _qatmost() -> at.QAtMost:
    return at.QAtMost(3)


def _sel_target_atmost() -> at.Selector:
    """R8-1/C17: "up to two target creatures" = TARGET + QAtMost — a
    legal designation of 1..2, resolved on 0..remaining."""
    return at.Selector(at.QAtMost(2), at.SelectorMode.TARGET, _CREATURE, zones=(_BF_YOU,))


def _token_bare() -> at.TokenSpec:
    """A pre-round-8 token: none of the three new fields is stated."""
    return at.TokenSpec(
        "Treasure",
        "Artifact — Treasure",
        ("Artifact",),
        ("Treasure",),
        None,
        None,
        (),
        (),
    )


def _token_full() -> at.TokenSpec:
    """R8-2/R8-4: a Basri Ket [-2]-style 1/1 white Soldier token."""
    return at.TokenSpec(
        "Soldier",
        "Creature — Soldier Token",
        ("Creature",),
        ("Soldier",),
        at.QConst(1),
        at.QConst(1),
        (),
        (),
        colors=("W",),  # R5-11: the WUBRG tuple replaced the scalar color
        enters_tapped=True,
        enters_attacking=False,
    )


def _mana_any() -> at.Atom:
    """R8-3: "add one mana of any color" — ANY, not colourless C."""
    return at.Atom(
        at.Verb.ADD_MANA,
        at.AtomArgs(
            pairs=(
                ("controller", at.ControllerRef.YOU),
                ("amount", at.QConst(1)),
                ("color", "ANY"),
            )
        ),
    )


def _deal_roles() -> at.Atom:
    """R8-5: damage with the optional dealer/recipient roles — the
    dealer is named by a player-identity FAtom, the recipient is "you"."""
    return at.Atom(
        at.Verb.DEAL_DAMAGE,
        at.AtomArgs(
            pairs=(
                (
                    "target",
                    at.Selector(
                        at.QConst(1), at.SelectorMode.TARGET, _CREATURE, zones=(_BF_YOU,)
                    ),
                ),
                ("amount", at.QConst(2)),
                ("dealer", at.FAtom(at.FAtomPred.IS_SOURCE)),
                ("recipient", at.ControllerRef.YOU),
            )
        ),
    )


def _fatom_exiled_with_source() -> at.FAtom:
    """R8-6: "the card exiled with ~" — no slots (IS_TAPPED precedent)."""
    return at.FAtom(at.FAtomPred.IS_EXILED_WITH_SOURCE)


def _atom_get_emblem() -> at.Atom:
    """R8-7/C19: role-less marker; the payload is the card-level attach."""
    return at.Atom(at.Verb.GET_EMBLEM, at.AtomArgs(pairs=()))


def _atom_add_land_play() -> at.Atom:
    """R8-8: Azusa — "play two additional lands on each of your turns"."""
    return at.Atom(
        at.Verb.ADD_LAND_PLAY,
        at.AtomArgs(
            pairs=(("count", at.QConst(2)), ("duration", at.DurationPermanent()))
        ),
    )


def _fatom_controller_count_gt() -> at.FAtom:
    """R8-9: dual-filter comparison — inner_filter vs right_inner_filter
    (Garruk's "controls more creatures than you" split)."""
    return at.FAtom(
        at.FAtomPred.CONTROLLER_COUNT_GT,
        inner_filter=_CREATURE,
        right_inner_filter=at.FAtom(at.FAtomPred.SUBTYPE_EQ, string_value="Goblin"),
    )


def _qthis_noncombat() -> at.QThisTurn:
    """R8-10: Chandra's Incinerator — {X}, X = noncombat damage dealt by
    you this turn."""
    return at.QThisTurn(at.ThisTurnKind.NONCOMBAT_DAMAGE, at.ControllerRef.YOU)


def _qprop_cc_target() -> at.QProp:
    """R8-11: Invigorating Surge — counter count of the TARGET."""
    return at.QProp(referent="target", field=at.QPropField.COUNTER_COUNT)


# ---- pinned fingerprints (captured after the round-8 edits) -----------------

_NEW_PINS: list[tuple[str, Callable[[], object], str]] = [
    (
        "qatmost",
        _qatmost,
        "028577172c7e1c76f7fa8a307d5258af1e1fea90d86a0c4821c59a54aa33d66a",
    ),
    (
        "sel_target_atmost",
        _sel_target_atmost,
        "c3a5ddafb372d3a1d453a5b982eefa6f5d867f8dc5c2e166789733808d119707",
    ),
    (
        "token_bare",
        _token_bare,
        "153b7771445b6d689118098acc34f28658d9674392db71246dd5dbe1f590d6db",
    ),
    (
        "token_full",
        _token_full,
        # re-pinned 2026-10-30: R5-11 changes the bytes ("color": "W" ->
        # "colors": ["W"]); the r10/r11 pin sets reuse this row.
        "c30cbcae798d8b44a6e54a082513af0b95fab9e849bdaf47c8bb85f831be2c39",
    ),
    (
        "mana_any",
        _mana_any,
        "f95b1fb7c2196bf1738b74be679d00a3e070e36d1b8d9d42eb64766fdb47c228",
    ),
    (
        "deal_roles",
        _deal_roles,
        "dae91ba7012ceb1313060772032366e281f67c565f838c63a0b82aa894c30335",
    ),
    (
        "fatom_exiled_with_source",
        _fatom_exiled_with_source,
        "eab460fe0a40c0d915dba2bba2d833c2e45ecedd083eb0029fbae2fa4086897b",
    ),
    (
        "atom_get_emblem",
        _atom_get_emblem,
        "9cf51cea082481b40926e407f20fb58009dd2c06fb54c657af8ca91fbfe2c7c4",
    ),
    (
        "atom_add_land_play",
        _atom_add_land_play,
        "4b8a3ef1dee2dfc43e66c73aa811f0cc2134506a1e796265f384b1b96cc59fa3",
    ),
    (
        "fatom_controller_count_gt",
        _fatom_controller_count_gt,
        "2ef4156f26c42261d62b335cec1c160029e22f4683bb624f563691275265295e",
    ),
    (
        "qthis_noncombat",
        _qthis_noncombat,
        "f7e24a1c4a3bd4420f2cbe9e5348cc1c78386134c0c09c8586918ef8f7058ece",
    ),
    (
        "qprop_cc_target",
        _qprop_cc_target,
        "b6d90bda61550cfe03c5d934f3022b307d61c26429263651408c4ddc9e97d0b5",
    ),
]

_REJECTIONS: list[tuple[str, Callable[[], object]]] = [
    # R8-1: QAtMost n validation mirrors QAtLeast (0/negatives/bools).
    ("qatmost_zero", lambda: at.QAtMost(0)),
    ("qatmost_negative", lambda: at.QAtMost(-2)),
    ("qatmost_bool", lambda: at.QAtMost(True)),
    ("qatmost_str", lambda: at.QAtMost("3")),  # type: ignore[arg-type]
    # R8-2 / R5-11: TokenSpec colors must be distinct WUBRG letters; the
    # flags must be bools.
    (
        "token_color_nonstr",
        lambda: at.TokenSpec(
            "S",
            "Creature — S",
            ("Creature",),
            ("S",),
            at.QConst(1),
            at.QConst(1),
            (),
            (),
            colors=(7,),  # type: ignore[arg-type]
        ),
    ),
    (
        "token_colors_not_wubrg",
        lambda: at.TokenSpec(
            "S", "Creature — S", ("Creature",), ("S",), at.QConst(1), at.QConst(1),
            (), (), colors=("C",),
        ),
    ),
    (
        "token_colors_repeated",
        lambda: at.TokenSpec(
            "S", "Creature — S", ("Creature",), ("S",), at.QConst(1), at.QConst(1),
            (), (), colors=("W", "W"),
        ),
    ),
    (
        "token_flag_nonbool",
        lambda: at.TokenSpec(
            "S",
            "Creature — S",
            ("Creature",),
            ("S",),
            at.QConst(1),
            at.QConst(1),
            (),
            (),
            enters_tapped="yes",  # type: ignore[arg-type]
        ),
    ),
    (
        "token_flag_int",
        lambda: at.TokenSpec(
            "S",
            "Creature — S",
            ("Creature",),
            ("S",),
            at.QConst(1),
            at.QConst(1),
            (),
            (),
            enters_attacking=1,  # type: ignore[arg-type]
        ),
    ),
    # R8-3: the color vocabulary stays closed even after "ANY".
    (
        "color_bad_value",
        lambda: at.Atom(
            at.Verb.ADD_MANA,
            at.AtomArgs(
                pairs=(
                    ("controller", at.ControllerRef.YOU),
                    ("amount", at.QConst(1)),
                    ("color", "X"),
                )
            ),
        ),
    ),
    # R8-5: dealer/recipient must be ControllerRef/Selector/Filter.
    (
        "dealer_bad_type",
        lambda: at.Atom(
            at.Verb.DEAL_DAMAGE,
            at.AtomArgs(
                pairs=(
                    (
                        "target",
                        at.Selector(
                            at.QConst(1), at.SelectorMode.TARGET, _CREATURE, zones=(_BF_YOU,)
                        ),
                    ),
                    ("amount", at.QConst(2)),
                    ("dealer", at.QConst(3)),
                )
            ),
        ),
    ),
    # R8-6: IS_EXILED_WITH_SOURCE takes NO slots.
    (
        "exiled_with_source_slot",
        lambda: at.FAtom(at.FAtomPred.IS_EXILED_WITH_SOURCE, count=at.QConst(1)),
    ),
    # R8-7: GET_EMBLEM is role-less (C19 — no emblem_ref role exists).
    (
        "get_emblem_with_role",
        lambda: at.Atom(
            at.Verb.GET_EMBLEM,
            at.AtomArgs(
                pairs=(
                    (
                        "target",
                        at.Selector(
                            at.QConst(1), at.SelectorMode.TARGET, _UNIVERSAL, zones=(_NEUTRAL,)
                        ),
                    ),
                )
            ),
        ),
    ),
    # R8-9: CONTROLLER_COUNT_GT requires BOTH filters; the new slot is a
    # Filter, not a quantity.
    (
        "cc_gt_missing_right",
        lambda: at.FAtom(at.FAtomPred.CONTROLLER_COUNT_GT, inner_filter=_CREATURE),
    ),
    (
        "cc_gt_missing_inner",
        lambda: at.FAtom(
            at.FAtomPred.CONTROLLER_COUNT_GT, right_inner_filter=_CREATURE
        ),
    ),
    ("cc_gt_bare", lambda: at.FAtom(at.FAtomPred.CONTROLLER_COUNT_GT)),
    (
        "cc_gt_bad_right_type",
        lambda: at.FAtom(
            at.FAtomPred.CONTROLLER_COUNT_GT,
            inner_filter=_CREATURE,
            right_inner_filter=at.QConst(2),  # type: ignore[arg-type]
        ),
    ),
    # R8-11: COUNTER_COUNT widened to target — but NOT to "controller".
    (
        "cc_controller_referent",
        lambda: at.QProp(referent="controller", field=at.QPropField.COUNTER_COUNT),
    ),
]


# ---- tests ------------------------------------------------------------------


@pytest.mark.parametrize(
    "name,build,fp",
    R6._NEW_PINS + R7._NEW_PINS + R8._NEW_PINS,
    ids=[n for n, _, _ in R6._NEW_PINS + R7._NEW_PINS + R8._NEW_PINS],
)
def test_pinned_pre_r9_fingerprint(
    name: str, build: Callable[[], object], fp: str
) -> None:
    """Byte stability: every pre-round-8 pinned tree (the r6 + r7 + r8
    pin sets) serializes identically — all eleven 8-A items are
    additive, no template opts in yet."""
    node = build()
    assert at.fingerprint(node) == fp
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d


@pytest.mark.parametrize("name,build,fp", _NEW_PINS, ids=[n for n, _, _ in _NEW_PINS])
def test_r9_roundtrip(name: str, build: Callable[[], object], fp: str) -> None:
    node = build()
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d
    back = at.from_dict(d["tag"], d)
    assert back == node, f"{name}: from_dict(to_dict(x)) != x"
    assert at.canonical_json(back) == at.canonical_json(node)
    assert at.fingerprint(back) == at.fingerprint(node) == fp


@pytest.mark.parametrize("name,fn", _REJECTIONS, ids=[n for n, _ in _REJECTIONS])
def test_r9_rejections(name: str, fn: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        fn()


# ---- R8-1: QAtMost + the TARGET designation (C17) ----------------------------


def test_qatmost_roundtrip_and_selector() -> None:
    assert at.QAtMost(1).n == 1
    sel = _sel_target_atmost()
    assert isinstance(sel.count, at.QAtMost)
    # QUnbounded is STILL rejected on TARGET-mode selectors (r3b rule).
    with pytest.raises(ValueError, match="needs a concrete count"):
        at.Selector(at.QUnbounded(), at.SelectorMode.TARGET, _CREATURE, zones=(_BF_YOU,))
    # CHOOSE keeps the resolution-time up-to reading unchanged (C17).
    choose = at.Selector(at.QConst(2), at.SelectorMode.CHOOSE, _CREATURE, zones=(_BF_YOU,))
    assert at.to_dict(choose.count) == {"tag": "QConst", "value": 2}


def test_qatmost_serializes_like_qatleast() -> None:
    assert at.to_dict(at.QAtMost(2)) == {"tag": "QAtMost", "n": 2}
    assert at.from_dict("QAtMost", {"tag": "QAtMost", "n": 2}) == at.QAtMost(2)
    assert "QAtMost" in at._QUANTITY_TAGS


# ---- R8-2/R8-4: TokenSpec — the golden-storm guard ---------------------------


def test_bare_tokenspec_omits_round8_keys_byte_shape() -> None:
    """CRITICAL pin: a pre-round-8 token serializes WITHOUT the three new
    keys — the dual-registration rule (PITFALLS 2026-09-28). Without the
    _OMIT_IF_EMPTY TokenSpec row every token golden byte-diffs."""
    assert at.to_dict(_token_bare()) == {
        "tag": "TokenSpec",
        "name": "Treasure",
        "type_line": "Artifact — Treasure",
        "types": ["Artifact"],
        "subtypes": ["Treasure"],
        "power": None,
        "toughness": None,
        "keywords": [],
        "abilities": [],
    }


def test_full_tokenspec_key_shape() -> None:
    """Stated values serialize; an EXPLICIT False is a stated value (not
    the empty default) and serializes as false."""
    d = at.to_dict(_token_full())
    assert d["colors"] == ["W"]  # re-pinned 2026-10-30: R5-11 colors tuple
    assert "color" not in d
    assert d["enters_tapped"] is True
    assert d["enters_attacking"] is False
    assert d["tag"] == "TokenSpec"


# ---- R8-5: DEAL_DAMAGE optional roles ------------------------------------------


def test_deal_damage_without_roles_still_builds() -> None:
    plain = at.Atom(
        at.Verb.DEAL_DAMAGE,
        at.AtomArgs(
            pairs=(
                (
                    "target",
                    at.Selector(
                        at.QConst(1), at.SelectorMode.TARGET, _CREATURE, zones=(_BF_YOU,)
                    ),
                ),
                ("amount", at.QConst(3)),
            )
        ),
    )
    back = at.from_dict("Atom", at.to_dict(plain))
    assert back == plain


# ---- R8-9: bare FAtom byte shape after the new slot --------------------------


def test_bare_fatom_omits_right_inner_filter_byte_shape() -> None:
    assert at.to_dict(at.FAtom(at.FAtomPred.IS_TAPPED)) == {
        "tag": "FAtom",
        "pred": {"tag": "FAtomPred", "name": "IS_TAPPED"},
        "string_value": None,
        "color": None,
        "colors": [],
        "count": None,
        "counter_kind": None,
        "keyword": None,
        "who": None,
        "inner_filter": None,
    }
    # IS_EXILED_WITH_SOURCE differs only in the pred name.
    assert at.to_dict(_fatom_exiled_with_source()) == at.to_dict(
        at.FAtom(at.FAtomPred.IS_TAPPED)
    ) | {"pred": {"tag": "FAtomPred", "name": "IS_EXILED_WITH_SOURCE"}}


# ---- R8-7/R8-8: table-shape pins ------------------------------------------------


def test_verb_role_tables_r8() -> None:
    assert at._VERB_ROLES[at.Verb.GET_EMBLEM] == {}
    assert at._VERB_ROLES[at.Verb.ADD_LAND_PLAY] == {
        "count": False,
        "duration": False,
    }
    assert at._VERB_ROLES[at.Verb.DEAL_DAMAGE] == {
        "target": True,
        "amount": True,
        "dealer": False,
        "recipient": False,
    }


def test_r8_table_members() -> None:
    assert at.QAtMost(1) is not None
    assert at.FAtomPred.IS_EXILED_WITH_SOURCE.value == "IS_EXILED_WITH_SOURCE"
    assert at.FAtomPred.CONTROLLER_COUNT_GT.value == "CONTROLLER_COUNT_GT"
    assert at.Verb.GET_EMBLEM.value == "GET_EMBLEM"
    assert at.Verb.ADD_LAND_PLAY.value == "ADD_LAND_PLAY"
    assert at.ThisTurnKind.NONCOMBAT_DAMAGE.value == "NONCOMBAT_DAMAGE"
    assert at._ANY_COLOR == "ANY"


def test_add_land_play_bare_builds() -> None:
    """Both roles are optional — the bare marker compiles for "you may
    play an additional land"."""
    bare = at.Atom(at.Verb.ADD_LAND_PLAY, at.AtomArgs(pairs=()))
    assert at.from_dict("Atom", at.to_dict(bare)) == bare


# ---- R8-11: COUNTER_COUNT referent widening ------------------------------------


def test_counter_count_referents() -> None:
    for referent in ("event", "source", "target"):
        q = at.QProp(referent=referent, field=at.QPropField.COUNTER_COUNT)
        assert at.from_dict("QProp", at.to_dict(q)) == q
