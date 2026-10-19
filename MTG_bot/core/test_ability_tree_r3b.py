"""T3 round 3b — coin flips, a blocker-subject filter, and ``QAtLeast``.

Round-r3b scope (all additive, byte-stable for every pre-r3b tree):

- ``Verb.FLIP_COIN`` — "flip a coin" (Tavern Swindler, M21).  No roles
  (``_VERB_ROLES[FLIP_COIN] = {}``): the coin flip is a pure event; the
  outcome is read by ``FAtomPred.FLIP_WON``, never by an arg.
- ``FAtomPred.FLIP_WON`` — "if X wins the flip".  ``who`` is REQUIRED
  (``ControllerRef``); "if X *loses* the flip" is ``FNot(FAtom(FLIP_WON,
  who=X))`` — deliberately no separate predicate.
- ``DeclareBlockersEvent.subject`` — optional ``Filter | None = None``
  constraining which creature may block (e.g. "you may block only with
  tapped creatures"), mirroring ``ZoneChangeEvent.subject``.  ``None``
  omits the ``"subject"`` key via ``_OMIT_IF_EMPTY``.
- ``QAtLeast(n)`` — a quantity meaning "at least n" (``n >= 1``).  Added
  to the ``Quantity`` union, ``_Q_CLASSES``, ``_SPECS`` and
  ``_QUANTITY_TAGS``, so every quantity slot (amount/count/power/
  toughness roles, keyword params, atom values) accepts it.  ``n = 0``
  is rejected (redundant with ``QUnbounded``); ``bool`` is rejected
  despite ``isinstance(True, int)``.

Byte stability: the nine pre-round-3b fingerprints in ``_PINNED`` were
captured BEFORE the edit and must stay byte-identical.  No golden tree
contains a ``FLIP_WON`` atom, a ``QAtLeast`` quantity, or a
``DeclareBlockersEvent`` with a subject, and the new field defaults to
``None`` (key omitted), so every pre-existing serialization is
unchanged.

Guards:
- the nine pre-r3b pins stay byte-identical and round-trip;
- the eight r3b constructs round-trip with byte-identical fingerprints;
- ``"subject"`` is omitted when unset and present when set;
- ``QAtLeast`` always serializes ``"n"`` (no omit path);
- construction rejections: ``QAtLeast(0)`` / negative / ``bool`` /
  ``str``; ``FLIP_WON`` without ``who``, with a non-``ControllerRef``
  ``who``, or with extra slots; ``FLIP_COIN`` with any role;
  ``DeclareBlockersEvent.subject`` with a non-``Filter``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

import MTG_bot.core.ability_tree as at

# ---- shared building blocks ------------------------------------------------


_IS_SOURCE = at.FAtom(pred=at.FAtomPred.IS_SOURCE)
_IS_TAPPED = at.FAtom(pred=at.FAtomPred.IS_TAPPED)
_ZONE_BF_YOU = at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU)
_ZONE_ANY_ANY = at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY)
_ZONE_BF_ANY = at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.ANY)


def _end_turn() -> at.Atom:
    return at.Atom(at.Verb.END_TURN, at.AtomArgs())


# ---- builders for the pre-r3b pins ------------------------------------------


def _declare_blockers_plain() -> at.DeclareBlockersEvent:
    """A DeclareBlockersEvent without a subject (every pre-r3b tree)."""
    return at.DeclareBlockersEvent(filter=_IS_SOURCE)


def _zone_change_etb() -> at.ZoneChangeEvent:
    return at.ZoneChangeEvent(
        from_zone=_ZONE_ANY_ANY,
        to_zone=_ZONE_BF_YOU,
    )


def _conditional_single_branch() -> at.Conditional:
    return at.Conditional(
        pred=_IS_TAPPED,
        then_effect=_end_turn(),
    )


def _qconst_3() -> at.QConst:
    return at.QConst(3)


def _qthisturn_life_you() -> at.QThisTurn:
    return at.QThisTurn(at.ThisTurnKind.LIFE_GAINED, at.ControllerRef.YOU)


def _qunbounded() -> at.QUnbounded:
    return at.QUnbounded()


def _choose_qunbounded() -> at.Choose:
    return at.Choose(at.QUnbounded(), (_end_turn(),))


def _selector_zones_union() -> at.Selector:
    return at.Selector(
        at.QConst(1),
        at.SelectorMode.TARGET,
        _IS_SOURCE,
        zones=(at.Zone(at.ZoneKind.PLAYER, at.ControllerRef.ANY), *(_ZONE_BF_ANY,)),
    )


def _spellability_effect_omitted() -> at.SpellAbility:
    return at.SpellAbility(kind=at.SpellKind.CREATURE)


# ---- builders for the r3b constructs -----------------------------------------


def _qatleast_1() -> at.QAtLeast:
    return at.QAtLeast(1)


def _qatleast_2() -> at.QAtLeast:
    return at.QAtLeast(2)


def _choose_qatleast_1() -> at.Choose:
    """QAtLeast as a Choose's count slot — the quantity-union path."""
    return at.Choose(at.QAtLeast(1), (_end_turn(),))


def _blockers_subject_tapped() -> at.DeclareBlockersEvent:
    """DeclareBlockersEvent whose blocking creature must be tapped."""
    return at.DeclareBlockersEvent(
        filter=_IS_SOURCE,
        subject=_IS_TAPPED,
    )


def _flip_won_you() -> at.FAtom:
    return at.FAtom(pred=at.FAtomPred.FLIP_WON, who=at.ControllerRef.YOU)


def _flip_won_opponent() -> at.FAtom:
    return at.FAtom(pred=at.FAtomPred.FLIP_WON, who=at.ControllerRef.OPPONENT)


def _flip_lose_you() -> at.FNot:
    """Losing the flip = NOT winning it (no separate predicate)."""
    return at.FNot(inner=_flip_won_you())


def _flip_coin_atom() -> at.Atom:
    return at.Atom(at.Verb.FLIP_COIN, at.AtomArgs())


def _tavern_swindler_conditional() -> at.Conditional:
    """'If you win the flip, you gain 6 life' (Tavern Swindler, M21)."""
    return at.Conditional(
        pred=_flip_won_you(),
        then_effect=at.Atom(
            at.Verb.GAIN_LIFE,
            at.AtomArgs(
                pairs=(
                    ("controller", at.ControllerRef.YOU),
                    ("amount", at.QConst(6)),
                )
            ),
        ),
    )


# ---- pinned pre-round-3b fingerprints (captured BEFORE the r3b edit) --------

_PINNED: list[tuple[str, Callable[[], object], str]] = [
    (
        "declare_blockers_event_plain",
        _declare_blockers_plain,
        "676d17c326e1e4af99ad3d29b95a8cf6a7f9e0154ae506b55cb3dcd46adfd209",
    ),
    (
        "zone_change_etb",
        _zone_change_etb,
        "5cefa8de9e8e4f168b88ed6a8f75567ed3d96ea9438785af1ba080d30fc2d939",
    ),
    (
        "conditional_single_branch",
        _conditional_single_branch,
        "f5df445b55540de246f473653d3e65b582418c92e63a601ac92d7e449e8db3a9",
    ),
    (
        "qconst_3",
        _qconst_3,
        "2a70ddc34493ac6cb42dca46eed1f410f52451b172cc6a3f5ca125ba4c058085",
    ),
    (
        "qthisturn_life_you",
        _qthisturn_life_you,
        "f041066bc5249c4ec4a1e1ade8586936742d70656fa733790bec97876d5c4744",
    ),
    (
        "qunbounded",
        _qunbounded,
        "67d280b0660fe20c24da371f727d89bcdc08fdb62e3088dc2e40cce0e0a3196a",
    ),
    (
        "choose_qunbounded",
        _choose_qunbounded,
        "80397e15c1ae85bbff3c8ad5aaa634b194a812b250c67af62908181b09fdf583",
    ),
    (
        "selector_zones_union",
        _selector_zones_union,
        "64d3fab5fcfd9239e2c832d0a8fb7852fd14d564061505597cc36409e98045df",
    ),
    (
        "spellability_effect_omitted",
        _spellability_effect_omitted,
        "4ab74b3cff39541af5ef554a5ffefdc68e1a506645aeb726b800c03eadb120b8",
    ),
]

# Round-3b constructs, pinned after the edit (byte-identity for future
# rounds).
_NEW_PINS: list[tuple[str, Callable[[], object], str]] = [
    (
        "qatleast_1",
        _qatleast_1,
        "745df6056b24ddc4e4a396e2125c20942a5aefe510f9ba22aff2008826f023f0",
    ),
    (
        "qatleast_2",
        _qatleast_2,
        "2149863a9b0c60051ef2f60f827668e3ea6c18f602856139b51e9b44d5135c04",
    ),
    (
        "choose_qatleast_1",
        _choose_qatleast_1,
        "91e02ea591c74d396b25ef11eacd792642ff5450abe60ae17837c9e88b55e4b7",
    ),
    (
        "blockers_subject_tapped",
        _blockers_subject_tapped,
        "cdb53762079752f32d673003174a880dae798902afaee788d4bd0fedfd523365",
    ),
    (
        "flip_won_you",
        _flip_won_you,
        "9b0243e4945bdb09ac1cc6728338dc0993d79e854cde4119bb9c311d8233a617",
    ),
    (
        "flip_lose_you",
        _flip_lose_you,
        "a46976f725c69a5902fdead75ff6cfd6479aaf633d63258a165de6bef694053a",
    ),
    (
        "flip_coin_atom",
        _flip_coin_atom,
        "96fff9dafdd0f0f5402b36c6f57f11fab5cf7c54d9e5ec3925c2f95fa06c8503",
    ),
    (
        "tavern_swindler_conditional",
        _tavern_swindler_conditional,
        "fc15ab4646d38f47fea52797007a9fce6fced94f5e4b05ad6f14ca7b626abdb6",
    ),
]


# ---- tests ------------------------------------------------------------------


@pytest.mark.parametrize("name,build,fp", _PINNED, ids=[n for n, _, _ in _PINNED])
def test_pinned_pre_r3b_fingerprint(
    name: str, build: Callable[[], object], fp: str
) -> None:
    """Pre-r3b trees stay byte-identical and round-trip after the edit."""
    node = build()
    assert at.fingerprint(node) == fp
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d
    back = at.from_dict(type(node).__name__, d)
    assert back == node, f"{name}: from_dict(to_dict(x)) != x"
    assert at.fingerprint(back) == fp


def test_plain_blockers_still_omits_subject() -> None:
    """The pre-r3b DeclareBlockersEvent shape must serialize without 'subject'."""
    d = at.to_dict(_declare_blockers_plain())
    assert "subject" not in d
    assert sorted(d.keys()) == ["filter", "tag"]
    back = at.from_dict("DeclareBlockersEvent", d)
    assert back.subject is None


def test_explicit_none_subject_equals_default() -> None:
    explicit = at.DeclareBlockersEvent(filter=_IS_SOURCE, subject=None)
    default = at.DeclareBlockersEvent(filter=_IS_SOURCE)
    assert explicit == default
    assert at.to_dict(explicit) == at.to_dict(default)
    assert at.fingerprint(explicit) == at.fingerprint(default)


@pytest.mark.parametrize("name,build,fp", _NEW_PINS, ids=[n for n, _, _ in _NEW_PINS])
def test_r3b_roundtrip(name: str, build: Callable[[], object], fp: str) -> None:
    node = build()
    d = at.to_dict(node)
    assert isinstance(d, dict) and "tag" in d
    back = at.from_dict(type(node).__name__, d)
    assert back == node, f"{name}: from_dict(to_dict(x)) != x"
    assert at.canonical_json(back) == at.canonical_json(node)
    assert at.fingerprint(back) == at.fingerprint(node) == fp


def test_blockers_subject_serialized_when_set() -> None:
    d = at.to_dict(_blockers_subject_tapped())
    assert "subject" in d
    assert isinstance(d["subject"], dict)
    assert d["subject"]["tag"] == "FAtom"
    assert d["subject"]["pred"]["name"] == "IS_TAPPED"
    assert d["filter"]["pred"]["name"] == "IS_SOURCE"


def test_qatleast_always_serializes_n() -> None:
    for n in (1, 2):
        d = at.to_dict(at.QAtLeast(n))
        assert d == {"tag": "QAtLeast", "n": n}, d
    # "n" has no omit path: from_dict must reject a payload without it.
    with pytest.raises(ValueError):
        at.from_dict("QAtLeast", {"tag": "QAtLeast"})


def test_qatleast_in_atom_amount_role() -> None:
    """QAtLeast reaches Atom args via the quantity union (auto-propagation)."""
    atom = at.Atom(
        at.Verb.GAIN_LIFE,
        at.AtomArgs(
            pairs=(
                ("controller", at.ControllerRef.YOU),
                ("amount", at.QAtLeast(1)),
            )
        ),
    )
    back = at.from_dict("Atom", at.to_dict(atom))
    assert back == atom


def test_flip_won_accepts_any_controller_ref() -> None:
    won = _flip_won_opponent()
    back = at.from_dict("FAtom", at.to_dict(won))
    assert back == won
    assert back.who == at.ControllerRef.OPPONENT


def test_flip_lose_is_fnot_not_a_predicate() -> None:
    """'You lose the flip' must be expressible as FNot(FLIP_WON), not a
    separate predicate — and there is no FLIP_LOSE member."""
    assert not any(p.name == "FLIP_LOSE" for p in at.FAtomPred)
    lose = _flip_lose_you()
    assert isinstance(lose, at.FNot)
    assert isinstance(lose.inner, at.FAtom)
    assert lose.inner.pred == at.FAtomPred.FLIP_WON
    assert lose.inner.who == at.ControllerRef.YOU
    # won and lose must hash to different trees
    assert at.fingerprint(lose) != at.fingerprint(_flip_won_you())


def test_flip_coin_has_no_roles() -> None:
    assert at._VERB_ROLES[at.Verb.FLIP_COIN] == {}


def _rejection_cases() -> list[tuple[str, Callable[[], object]]]:
    return [
        ("qatleast_zero", lambda: at.QAtLeast(0)),
        ("qatleast_negative", lambda: at.QAtLeast(-1)),
        ("qatleast_bool", lambda: at.QAtLeast(True)),
        ("qatleast_str", lambda: at.QAtLeast("1")),  # type: ignore[arg-type]
        (
            "flip_won_without_who",
            lambda: at.FAtom(pred=at.FAtomPred.FLIP_WON),
        ),
        (
            "flip_won_who_str",
            lambda: at.FAtom(pred=at.FAtomPred.FLIP_WON, who="YOU"),  # type: ignore[arg-type]
        ),
        (
            "flip_won_extra_slot",
            lambda: at.FAtom(
                pred=at.FAtomPred.FLIP_WON,
                who=at.ControllerRef.YOU,
                count=at.QConst(1),
            ),
        ),
        (
            "flip_coin_with_role",
            lambda: at.Atom(
                at.Verb.FLIP_COIN,
                at.AtomArgs(
                    pairs=(
                        (
                            "target",
                            at.Selector(
                                at.QConst(1),
                                at.SelectorMode.TARGET,
                                _IS_SOURCE,
                                zones=(_ZONE_BF_ANY,),
                            ),
                        ),
                    )
                ),
            ),
        ),
        (
            "blockers_subject_non_filter",
            lambda: at.DeclareBlockersEvent(
                filter=_IS_SOURCE,
                subject=at.QConst(1),  # type: ignore[arg-type]
            ),
        ),
    ]


@pytest.mark.parametrize(
    "name,fn", _rejection_cases(), ids=[n for n, _ in _rejection_cases()]
)
def test_r3b_rejections(name: str, fn: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        fn()


def test_from_dict_missing_subject_defaults_none() -> None:
    """A serialized tree with the 'subject' key stripped must decode to
    subject=None — the opt: decode injects the default."""
    d: dict[str, Any] = at.to_dict(_blockers_subject_tapped())
    assert "subject" in d
    del d["subject"]
    back = at.from_dict("DeclareBlockersEvent", d)
    assert back.subject is None
    assert back == _declare_blockers_plain()
