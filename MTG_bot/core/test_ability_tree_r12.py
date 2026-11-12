"""Grammar pins: the OPPONENT_OF predicate and CREATE_TOKEN's optional
``controller`` role.

- ``FAtomPred.OPPONENT_OF`` {who} is the destination identity for "deals
  damage to an opponent" (Chandra's Pyreling). ``who`` is a ControllerRef or
  a referent Selector. It is player-total: a card subject never passes (CR
  109.5: damage "to an opponent" is damage to a PLAYER). CONTROLLER_IS
  would read a card subject's controller and fire the Pyreling trigger on
  damage to an opponent's CREATURE.
- ``Verb.CREATE_TOKEN`` takes an optional ``controller`` (ControllerRef or
  Selector); no role means the ability's controller.
- ``TriggeredAbility.once_per_event`` / ``DelayedTrigger.once_per_event``
  (CR 603.2c): True or absent, omitted from the bytes when absent.

Pinned: the closed tables, legality at both accepted carrier types, and a
rejection at every validation point.
"""

from __future__ import annotations

import pytest

import MTG_bot.core.ability_tree as at


def _referent_target_selector() -> at.Selector:
    """The "its controller" carrier the templates emit (Angelic Ascension's
    token; the same shape as Liliana, Death Mage's life loss)."""
    return at.Selector(
        at.QConst(1),
        at.SelectorMode.CHOOSE,
        at.FAnd(()),
        zones=(at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY),),
        referent="target",
    )


# ---- OPPONENT_OF: table + legality ----------------------------------------


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


# ---- OPPONENT_OF: rejections at every validation point --------------------


def test_opponent_of_requires_who() -> None:
    with pytest.raises(ValueError, match="requires slot 'who'"):
        at.FAtom(pred=at.FAtomPred.OPPONENT_OF)


def test_opponent_of_rejects_non_referent_selector() -> None:
    bare = at.Selector(
        at.QConst(1),
        at.SelectorMode.ALL,
        at.FAnd(()),
        zones=(at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY),),
    )
    with pytest.raises(ValueError, match="referent Selector"):
        at.FAtom(pred=at.FAtomPred.OPPONENT_OF, who=bare)


def test_opponent_of_rejects_bare_int() -> None:
    # The generic FAtom who-type gate fires first; the OPPONENT_OF gate
    # behind it admits referent Selectors but not non-referents.
    with pytest.raises(ValueError, match="who must be a ControllerRef"):
        at.FAtom(pred=at.FAtomPred.OPPONENT_OF, who=3)  # type: ignore[arg-type]


# ---- CREATE_TOKEN controller role -----------------------------------------


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
    # The role is optional: the plain form most CREATE_TOKEN rows emit
    # still constructs.
    assert _create().verb is at.Verb.CREATE_TOKEN


def test_create_token_with_controller_ref_legal() -> None:
    assert _create(controller=at.ControllerRef.YOU) is not None


def test_create_token_with_referent_selector_legal() -> None:
    assert _create(controller=_referent_target_selector()) is not None


def test_create_token_controller_wrong_type_rejected() -> None:
    with pytest.raises(ValueError, match="role 'controller'"):
        _create(controller=at.QConst(1))


def test_create_token_tokens_still_required() -> None:
    # The controller role does not loosen the required slot.
    with pytest.raises(ValueError, match="missing required roles"):
        at.Atom(
            verb=at.Verb.CREATE_TOKEN,
            args=at.AtomArgs(pairs=(("controller", at.ControllerRef.YOU),)),
        )


# ---- once_per_event: the trigger's once-per-event axis (CR 603.2c) ----------


def _attack_trigger(**extra: object) -> at.TriggeredAbility:
    return at.TriggeredAbility(
        at.DeclareAttackersEvent(filter=at.FAnd(())),
        None,
        at.Atom(
            at.Verb.DRAW,
            at.AtomArgs(
                pairs=(("controller", at.ControllerRef.YOU), ("amount", at.QConst(1)))
            ),
        ),
        **extra,
    )


def test_once_per_event_tables() -> None:
    for tag in ("TriggeredAbility", "DelayedTrigger"):
        assert ("once_per_event", "opt:bool") in at._SPECS[tag]
    assert at._OMIT_IF_EMPTY["TriggeredAbility"] == frozenset({"once_per_event"})
    # a reflexive trigger (CR 603.12) also has no duration and no event
    assert at._OMIT_IF_EMPTY["DelayedTrigger"] == frozenset({"duration", "event", "once_per_event"})


def test_once_per_event_absent_keeps_the_bytes_and_true_round_trips() -> None:
    # Absent (once per occurrence) serializes without the key, so a trigger
    # that does not use it keeps its exact bytes.
    assert "once_per_event" not in at.to_dict(_attack_trigger())
    batch = at.to_dict(_attack_trigger(once_per_event=True))
    assert batch["once_per_event"] is True
    assert at.from_dict("TriggeredAbility", batch) == _attack_trigger(once_per_event=True)
    plain = _attack_trigger()
    delayed = at.DelayedTrigger(at.DurationEot(), plain.event, None, plain.effect, True)
    assert at.from_dict("DelayedTrigger", at.to_dict(delayed)) == delayed


@pytest.mark.parametrize("value", [False, 1])
def test_once_per_event_has_one_encoding(value: object) -> None:
    # The default has one encoding: absent. False (or a truthy int) is refused.
    with pytest.raises(ValueError, match="once_per_event"):
        _attack_trigger(once_per_event=value)


_SELF = at.FAtom(at.FAtomPred.IS_SOURCE)
_EQUIPPED = at.FAtom(at.FAtomPred.IS_ATTACHED_TO_SOURCE)
_CREATURE = at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature")


def _dealt(source: at.Filter | None, combat: bool | None) -> at.DamageDealtEvent:
    return at.DamageDealtEvent(at.QUnbounded(), at.FAnd(()), source=source, combat=combat)


@pytest.mark.parametrize(
    "event",
    [
        # "whenever this creature attacks" / "equipped creature attacks": one attacker per
        # declaration, so the flag would be a second encoding of the unflagged trigger
        at.DeclareAttackersEvent(filter=_SELF),
        at.DeclareAttackersEvent(filter=_EQUIPPED),
        at.DeclareAttackersEvent(filter=at.FAnd((_CREATURE, _SELF))),
        # "this creature deals combat damage": one dealer per step
        _dealt(_SELF, True),
        # damage that is not only combat damage: the engine groups a combat damage step only
        _dealt(_CREATURE, False),
        _dealt(_CREATURE, None),
        # "is dealt damage": no dealer named, already one event per recipient (CR 510.2)
        _dealt(None, True),
    ],
)
def test_once_per_event_refused_where_it_changes_nothing(event: object) -> None:
    effect = _attack_trigger().effect
    with pytest.raises(ValueError, match="gathers occurrences"):
        at.TriggeredAbility(event, None, effect, once_per_event=True)
    with pytest.raises(ValueError, match="gathers occurrences"):
        at.DelayedTrigger(at.DurationEot(), event, None, effect, True)
    assert at.TriggeredAbility(event, None, effect).once_per_event is None  # unflagged: fine


def test_once_per_event_kept_where_one_event_gathers_occurrences() -> None:
    effect = _attack_trigger().effect
    for event in (
        at.DeclareAttackersEvent(filter=at.FNot(_SELF)),  # "another creature attacks"
        at.DeclareAttackersEvent(filter=_CREATURE),
        _dealt(_CREATURE, True),  # "one or more creatures deal combat damage"
        at.CreatureDiesEvent(filter=_CREATURE),  # the binder, not the IR, refuses this kind
    ):
        assert at.TriggeredAbility(event, None, effect, once_per_event=True).once_per_event
    assert not at.gathers_occurrences(at.CreatureDiesEvent(filter=_CREATURE))
