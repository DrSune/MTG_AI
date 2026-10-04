"""Grammar round 11 / batch 6 — two additive members (2026-10-02).

Round-11 scope (authority: KNOWLEDGE/2026-10-02/10-grammar-round-ruling.md;
file-name offset intentional — round-11 grammar ships in the r12 file, the
r6-in-r7 / r10-in-r11 precedent):

- R11-1: ``FAtomPred.OPPONENT_OF`` {who} — the DESTINATION identity pred
  for "deals damage to an opponent" (Chandra's Pyreling / Chandra's
  Incinerator). ``who`` must be a ControllerRef or a referent Selector
  (the CONTROLLER_IS precedent); it is player-total — a card subject can
  never pass (CR 109.5: damage "to an opponent" is damage to a PLAYER).
  Distinct from CONTROLLER_IS on purpose: over a card subject
  CONTROLLER_IS reads the card's controller, which would fire the
  Pyreling trigger on damage to an opponent's CREATURE — exactly the
  negative the ruling forbids.
- R11-2: ``Verb.CREATE_TOKEN`` gains the OPTIONAL role ``controller``
  (_VERB_ROLES row {"tokens": True, "count": False, "controller": False};
  _ROLE_TYPES["controller"] already accepts ControllerRef | Selector).
  No role = the ability's controller: every pre-round-11 emission and
  the whole frozen golden corpus are byte-unchanged except the two
  anaphora cards the batch re-pinned.

Guards pinned below: the closed tables, legality at both accepted
carrier types, and rejection at every new validation point.
"""

from __future__ import annotations

import pytest

import MTG_bot.core.ability_tree as at


def _referent_target_selector() -> at.Selector:
    """The anaphora carrier the templates emit (R11-2 / Death-Mage twin)."""
    return at.Selector(
        at.QConst(1),
        at.SelectorMode.CHOOSE,
        at.FAnd(()),
        at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY),
        referent="target",
    )


# ---- R11-1: OPPONENT_OF — table + legality --------------------------------


def test_opponent_of_rules_row() -> None:
    assert at._FATOM_RULES[at.FAtomPred.OPPONENT_OF] == (
        frozenset({"who"}),
        frozenset({"who"}),
    )


def test_opponent_of_with_controller_ref_legal() -> None:
    atom = at.FAtom(pred=at.FAtomPred.OPPONENT_OF, who=at.ControllerRef.YOU)
    assert atom.pred is at.FAtomPred.OPPONENT_OF
    assert atom.who is at.ControllerRef.YOU


def test_opponent_of_with_referent_selector_legal() -> None:
    atom = at.FAtom(pred=at.FAtomPred.OPPONENT_OF, who=_referent_target_selector())
    assert isinstance(atom.who, at.Selector)
    assert atom.who.referent == "target"


# ---- R11-1: rejections at every new validation point ----------------------


def test_opponent_of_requires_who() -> None:
    with pytest.raises(ValueError, match="requires slot 'who'"):
        at.FAtom(pred=at.FAtomPred.OPPONENT_OF)


def test_opponent_of_rejects_non_referent_selector() -> None:
    bare = at.Selector(
        at.QConst(1),
        at.SelectorMode.ALL,
        at.FAnd(()),
        at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY),
    )
    with pytest.raises(ValueError, match="referent Selector"):
        at.FAtom(pred=at.FAtomPred.OPPONENT_OF, who=bare)


def test_opponent_of_rejects_bare_int() -> None:
    # The generic FAtom who-type gate fires first; the R11-1 gate is the
    # one behind it that admits referent Selectors but not non-referents.
    with pytest.raises(ValueError, match="who must be a ControllerRef"):
        at.FAtom(pred=at.FAtomPred.OPPONENT_OF, who=3)  # type: ignore[arg-type]


# ---- R11-2: CREATE_TOKEN controller role -----------------------------------


def test_create_token_roles_row() -> None:
    assert at._VERB_ROLES[at.Verb.CREATE_TOKEN] == {
        "tokens": True,
        "count": False,
        "controller": False,
    }


def _soldier() -> at.TokenSpec:
    return at.TokenSpec(
        name="Soldier",
        type_line="Token — Creature — Soldier",
        types=("Creature",),
        subtypes=("Soldier",),
        power=at.QConst(1),
        toughness=at.QConst(1),
        keywords=(),
        abilities=(),
    )


def _create(**roles: object) -> at.Atom:
    pairs = [("tokens", _soldier()), ("count", at.QConst(1))]
    pairs += [(r, v) for r, v in roles.items()]
    return at.Atom(verb=at.Verb.CREATE_TOKEN, args=at.AtomArgs(pairs=tuple(pairs)))


def test_create_token_without_controller_still_legal() -> None:
    # The regression face of "optional": every pre-round-11 emission form
    # must keep constructing (27 CREATE_TOKEN corpus rows ride on it).
    assert _create().verb is at.Verb.CREATE_TOKEN


def test_create_token_with_controller_ref_legal() -> None:
    assert _create(controller=at.ControllerRef.YOU) is not None


def test_create_token_with_referent_selector_legal() -> None:
    assert _create(controller=_referent_target_selector()) is not None


def test_create_token_controller_wrong_type_rejected() -> None:
    with pytest.raises(ValueError, match="role 'controller'"):
        _create(controller=at.QConst(1))


def test_create_token_tokens_still_required() -> None:
    # The new role does not loosen the required slot.
    with pytest.raises(ValueError, match="missing required roles"):
        at.Atom(
            verb=at.Verb.CREATE_TOKEN,
            args=at.AtomArgs(pairs=(("controller", at.ControllerRef.YOU),)),
        )
