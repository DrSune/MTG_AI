"""Copies in the IR (DESIGN_ATOM_ONTOLOGY §18, CR 707): the ``CopyOf`` value, COPY's roles,
CREATE_TOKEN of a copy, and the forms that must not validate. Every refusal is a second encoding of
a copy, a role where it means nothing, or a copy where it is none. Each test fails on the base of
the round (70e63ee7): ``CopyOf`` does not exist there."""

from __future__ import annotations

import pytest

from MTG_bot.core.ability_tree import (
    AbilityActivatedEvent,
    AbilityKind,
    ActivatedAbility,
    Atom,
    AtomArgs,
    CardRecord,
    CastSpellEvent,
    Conditional,
    ControllerRef,
    CopyOf,
    Cost,
    DurationEot,
    DurationUntilNextTurn,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    QBin,
    QBinOp,
    QConst,
    QProp,
    QPropField,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    SpellKind,
    TokenSpec,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    canonical_json,
    from_dict,
    to_dict,
)

_BF = (Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),)
_STACK = (Zone(ZoneKind.STACK, ControllerRef.ANY),)
_CREATURE = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
_TARGET = Selector(QConst(1), SelectorMode.TARGET, _CREATURE, zones=_BF)
_SPELL = Selector(QConst(1), SelectorMode.TARGET, FAtom(pred=FAtomPred.TYPE_EQ, string_value="Instant"),
                  zones=_STACK)
_ALL = Selector(QUnbounded(), SelectorMode.ALL, _CREATURE, zones=_BF)


def _ref(name: str) -> Selector:
    return Selector(QConst(1), SelectorMode.CHOOSE, FAnd(children=()),
                    zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),), referent=name)


def _atom(verb: Verb, **roles) -> Atom:
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


def _card(*abilities) -> CardRecord:
    return CardRecord(
        oracle_id="6629a48b-be9a-4636-8add-69d096a1ca7e", name="Copier", type_line="Enchantment",
        types=("Enchantment",), subtypes=(), supertypes=(), colors=(), color_identity=frozenset(),
        mana_cost=None, mana_value=0, power=None, toughness=None, loyalty=None, keywords=(),
        abilities=abilities, is_token=False,
    )


_ETB = ZoneChangeEvent(from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
                       to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                       subject=FAtom(pred=FAtomPred.IS_SOURCE))
_CAST = CastSpellEvent(filter=FAnd(children=()),
                       actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU))


def test_the_three_copy_forms_build_and_round_trip() -> None:
    forms = [
        _atom(Verb.CREATE_TOKEN, tokens=CopyOf(_TARGET), count=QConst(1)),  # a token copy
        _atom(Verb.COPY, source=CopyOf(_SPELL), new_targets=True),  # a copy put onto the stack
        _atom(Verb.COPY, source=CopyOf(_TARGET), cards=_ALL, duration=DurationEot()),  # becomes
    ]
    for atom in forms:
        assert from_dict("Atom", to_dict(atom)) == atom
    # an exception-free copy is its source alone (the exception fields omitted)
    assert "subtypes" not in canonical_json(CopyOf(_TARGET))


def test_a_copys_exceptions_are_canonical() -> None:
    copy = CopyOf(_TARGET, subtypes=("Rogue", "Shapeshifter"), keywords=(Keyword.TRAMPLE, Keyword.HASTE))
    assert copy == CopyOf(_TARGET, subtypes=("Shapeshifter", "Rogue"),
                          keywords=(Keyword.HASTE, Keyword.TRAMPLE))
    assert from_dict("CopyOf", to_dict(copy)) == copy


@pytest.mark.parametrize(
    ("build", "why"),
    [
        # one object is copied
        (lambda: CopyOf(_ALL), "names one object"),
        (lambda: CopyOf(Selector(QConst(2), SelectorMode.TARGET, _CREATURE, zones=_BF)), "names one object"),
        # an exception is a subtype word, a keyword, or a triggered, activated or static ability
        (lambda: CopyOf(_TARGET, subtypes=("Artifact",)), "subtype words"),
        (lambda: CopyOf(_TARGET, subtypes=("Legendary",)), "subtype words"),
        (lambda: CopyOf(_TARGET, subtypes=("Nightmare", "Nightmare")), "distinct"),
        (lambda: CopyOf(_TARGET, abilities=(KeywordAbility(keyword=Keyword.HASTE),)), "keyword"),
        (lambda: CopyOf(_TARGET, abilities=(SpellAbility(kind=SpellKind.INSTANT),)), "keyword"),
    ],
)
def test_a_copyof_that_names_no_one_object_or_no_exception_is_refused(build, why) -> None:
    with pytest.raises(ValueError):
        build()


@pytest.mark.parametrize(
    ("verb", "roles", "match"),
    [
        # a second encoding of a token copy: a COPY of a permanent with nothing becoming it
        (Verb.COPY, {"source": CopyOf(_TARGET)}, "CREATE_TOKEN's"),
        # a copy of a spell is put onto the stack, never made a token
        (Verb.CREATE_TOKEN, {"tokens": CopyOf(_SPELL)}, "never a token"),
        # COPY's source is a CopyOf, a cast verb's a Selector (one type per verb)
        (Verb.COPY, {"source": _SPELL}, "a CopyOf"),
        (Verb.CAST, {"source": CopyOf(_SPELL)}, "a Selector"),
        (Verb.PERMIT, {"source": CopyOf(_TARGET)}, "a Selector"),
        # COPY outside its roles
        (Verb.COPY, {"source": CopyOf(_SPELL), "target": _ALL}, "does not take roles"),
        (Verb.COPY, {"source": CopyOf(_SPELL), "tokens": TokenSpec(
            name="Bear", type_line="Creature — Bear", types=("Creature",), subtypes=("Bear",),
            power=QConst(2), toughness=QConst(2), keywords=(), abilities=())}, "does not take roles"),
        # roles that mean nothing on a copy put onto the stack
        (Verb.COPY, {"source": CopyOf(_SPELL), "duration": DurationEot()}, "duration"),
        (Verb.COPY, {"source": CopyOf(_SPELL), "new_targets": False}, "True or absent"),
        (Verb.COPY, {"source": CopyOf(_SPELL), "count": QConst(1)}, "absent is one copy"),
        # an "except" clause on what is not a copy of a permanent: a stack copy prints none
        (Verb.COPY, {"source": CopyOf(_SPELL, keywords=(Keyword.HASTE,))}, "no exception"),
        # roles that mean nothing on permanents that become copies
        (Verb.COPY, {"source": CopyOf(_TARGET), "cards": _ALL}, "until end of turn"),
        (Verb.COPY, {"source": CopyOf(_TARGET), "cards": _ALL,
                     "duration": DurationUntilNextTurn()}, "until end of turn"),
        (Verb.COPY, {"source": CopyOf(_TARGET), "cards": _ALL, "duration": DurationEot(),
                     "new_targets": True}, "stack's"),
        (Verb.COPY, {"source": CopyOf(_TARGET), "cards": _ALL, "duration": DurationEot(),
                     "count": QConst(2)}, "stack's"),
        (Verb.COPY, {"source": CopyOf(_SPELL), "cards": _ALL, "duration": DurationEot()},
         "no stack object"),
    ],
)
def test_the_copy_forms_that_must_not_validate(verb, roles, match) -> None:
    with pytest.raises(ValueError, match=match):
        Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


@pytest.mark.parametrize("role", ["cards", "target", "ability", "tokens_"])
def test_a_copyof_stands_only_in_tokens_and_copys_source(role) -> None:
    value = CopyOf(_TARGET)
    with pytest.raises(ValueError):
        if role == "ability":
            Atom(verb=Verb.GRANT_ABILITY, args=AtomArgs(pairs=(("target", _TARGET), ("ability", value))))
        elif role == "tokens_":
            Atom(verb=Verb.MOVE_ZONE, args=AtomArgs(pairs=(
                ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)), ("tokens", value))))
        else:
            Atom(verb=Verb.MOVE_ZONE, args=AtomArgs(pairs=(
                ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)), (role, value))))


def _trigger(event, effect) -> TriggeredAbility:
    return TriggeredAbility(event=event, condition=None, effect=effect)


def test_the_event_a_copy_reads_is_the_triggers() -> None:
    """A stack copy of ``event`` is "copy that spell|ability": only under a cast or an activation
    trigger; a cast trigger's event is a spell, which no token copies; ORDINAL counts a cast
    trigger's spell, nowhere else."""
    stack_copy = _atom(Verb.COPY, source=CopyOf(_ref("event")))
    token_copy = _atom(Verb.CREATE_TOKEN, tokens=CopyOf(_ref("event")), count=QConst(1))
    activation = AbilityActivatedEvent(source=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                                       kind=AbilityKind.LOYALTY)
    ordinal = QBin(QBinOp.SUB, QProp("event", QPropField.ORDINAL), QConst(1))
    _card(_trigger(_CAST, stack_copy))  # Double Vision
    _card(_trigger(activation, stack_copy))  # Chandra's Regulator
    _card(_trigger(_ETB, token_copy))  # a token copy of the object an ETB trigger names
    _card(_trigger(_CAST, _atom(Verb.COPY, source=CopyOf(_ref("event")), count=ordinal)))
    for bad in (
        _trigger(_ETB, stack_copy),  # an ETB's object is a permanent, never on the stack
        _trigger(_CAST, token_copy),  # a cast trigger's object is a spell
        _trigger(_ETB, _atom(Verb.COPY, source=CopyOf(_ref("event")), count=ordinal)),
    ):
        with pytest.raises(ValueError, match="event|ORDINAL"):
            _card(bad)
    with pytest.raises(ValueError, match="ORDINAL"):  # a spell has no triggering cast
        _card(SpellAbility(kind=SpellKind.SORCERY, effect=_atom(
            Verb.COPY, source=CopyOf(_SPELL), count=QProp("event", QPropField.ORDINAL))))


def test_the_complement_of_the_result_register_stands_in_a_resolving_selector_only() -> None:
    """"All other Nightmare tokens you control" (Abyssal Harvester) is FNot(IS_RESULT) in the
    moved objects' selector; IS_RESULT itself there is the referent's second form, and outside a
    resolving instruction no register exists."""
    not_result = FNot(inner=FAtom(pred=FAtomPred.IS_RESULT))
    others = Selector(QUnbounded(), SelectorMode.ALL, FAnd(children=(_CREATURE, not_result)), zones=_BF)
    exile = _atom(Verb.MOVE_ZONE, cards=others, destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER))
    made = _atom(Verb.CREATE_TOKEN, tokens=CopyOf(_TARGET), count=QConst(1))
    _card(ActivatedAbility(cost=Cost(), effect=Seq(steps=(made, exile))))
    with pytest.raises(ValueError, match="second form"):
        Selector(QUnbounded(), SelectorMode.ALL, FAtom(pred=FAtomPred.IS_RESULT), zones=_BF)
    with pytest.raises(ValueError, match="second form"):
        Selector(QUnbounded(), SelectorMode.ALL,
                 FOr(children=(_CREATURE, FAtom(pred=FAtomPred.IS_RESULT))), zones=_BF)
    with pytest.raises(ValueError, match="IS_RESULT"):  # a trigger's condition has no register
        _card(TriggeredAbility(event=_ETB, condition=not_result, effect=made))
    with pytest.raises(ValueError, match="IS_RESULT"):  # nor a Conditional's gate
        _card(SpellAbility(kind=SpellKind.SORCERY, effect=Seq(steps=(
            made, Conditional(pred=not_result, then_effect=exile)))))
