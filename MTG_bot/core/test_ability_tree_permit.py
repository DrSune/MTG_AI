"""The permission verb's IR (ontology round R13, DESIGN_ATOM_ONTOLOGY §17): ``Verb.PERMIT`` and
the cast verbs' shared roles, each meaning with one encoding.

Pinned, each refusal failing on the base (no PERMIT, no ``alternative`` / ``additional`` /
``replace`` / ``lands`` role, no ``permission_fault``):
1. the accepted shapes: a static's population over its zone, a resolving ability's designation or
   population with its duration, a card's own permission from its graveyard, a rider;
2. a permission without its zone or its duration, and a static one with a duration or a count;
3. a second encoding of "may play": an OptionalEffect around a PERMIT, a free activation or a static
   that casts (the old permission row), an activation that casts its own card, "play" spelled two
   ways, a granted static permission, a card-level replacement of a spell leaving the stack;
4. a permission on a verb that cannot carry it: a CAST with a duration, a count or ``lands``, a
   rider on a move, a PERMIT under EachPlayer.
"""

from __future__ import annotations

import pytest

from MTG_bot.core import ability_tree as at
from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    Atom,
    AtomArgs,
    CardRecord,
    ControllerRef,
    Cost,
    CostLife,
    CostManaGeneric,
    CostTap,
    DurationEot,
    DurationPermanent,
    DurationUntilEndOfNextTurn,
    DurationUntilNextTurn,
    EachPlayer,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    OptionalEffect,
    QConst,
    QUnbounded,
    ReplacementAbility,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    SpellKind,
    StaticAbility,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    ZonePosition,
    from_dict,
    to_dict,
)

TOP = Zone(ZoneKind.LIBRARY, ControllerRef.YOU, ZonePosition.TOP)
GY = Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)
EXILE = Zone(ZoneKind.EXILE, ControllerRef.YOU)
HAND = Zone(ZoneKind.HAND, ControllerRef.YOU)
ANY = Zone(ZoneKind.ANY, ControllerRef.ANY)
LAND = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land")
CREATURE = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
SELF = FAtom(pred=FAtomPred.IS_SOURCE)
INTO_GRAVEYARD = at.spell_rider(GY)
OFF_THE_STACK = at.spell_rider(ANY)


def every(filter_=CREATURE, *zones) -> Selector:
    return Selector(QUnbounded(), SelectorMode.ALL, filter_, zones=zones or (TOP,))


def result() -> Selector:
    return Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()), zones=(ANY,), referent="result")


def target(filter_=CREATURE) -> Selector:
    return Selector(QConst(1), SelectorMode.TARGET, filter_, zones=(GY,))


def permit(source: Selector, **roles) -> Atom:
    return Atom(verb=Verb.PERMIT, args=AtomArgs(pairs=(("source", source), *roles.items())))


def cast(source: Selector, **roles) -> Atom:
    return Atom(verb=Verb.CAST, args=AtomArgs(pairs=(("source", source), *roles.items())))


def card(*abilities, types=("Creature",)) -> CardRecord:
    creature = "Creature" in types
    return CardRecord(
        oracle_id="00000000-0000-0000-0013-000000000001",
        name="Permit Test",
        type_line=" ".join(types),
        types=types,
        subtypes=(),
        supertypes=(),
        colors=(),
        color_identity=frozenset(),
        mana_cost=None,
        mana_value=2,
        power=QConst(2) if creature else None,
        toughness=QConst(2) if creature else None,
        loyalty=None,
        keywords=(),
        abilities=abilities,
        is_token=False,
    )


ETB = ZoneChangeEvent(from_zone=ANY, to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                      subject=SELF)


def triggered(effect) -> TriggeredAbility:
    return TriggeredAbility(event=ETB, condition=None, effect=effect)


# ------------------------------------------------------------------------------ 1. accepted


def test_the_accepted_shapes_build_and_round_trip() -> None:
    """Conspicuous Snoop's static, Radha's lands, Omniscience's free casts from the hand, Demonic
    Embrace's own graveyard cast with additional costs, flashback with its rider, an impulse draw
    for each duration, a target permission, Idol of Endurance's one play, and the one-shot CAST
    with its rider: each builds, passes ``permission_fault`` and round-trips through the dict."""
    shapes = (
        StaticAbility(effect=permit(every(FAnd((CREATURE, FAtom(pred=FAtomPred.SUBTYPE_EQ,
                                                                 string_value="Goblin")))))),
        StaticAbility(effect=permit(every(LAND), lands=True)),
        StaticAbility(effect=permit(every(FAnd(()), HAND), alternative=Cost())),
        StaticAbility(effect=permit(every(SELF, GY), additional=Cost(parts=(CostLife(QConst(3)),)))),
        StaticAbility(effect=permit(every(SELF, GY), alternative=Cost(parts=(CostManaGeneric(QConst(2)),)),
                                    replace=OFF_THE_STACK)),
        triggered(permit(result(), lands=True, duration=DurationEot())),
        triggered(permit(result(), lands=True, duration=DurationUntilEndOfNextTurn())),
        triggered(permit(result(), lands=True, duration=DurationPermanent())),
        triggered(permit(target(), duration=DurationEot(), replace=INTO_GRAVEYARD)),
        ActivatedAbility(cost=Cost(parts=(CostTap(),)),
                         effect=permit(every(CREATURE, EXILE), alternative=Cost(), count=QConst(1),
                                       duration=DurationEot())),
        ActivatedAbility(cost=Cost(parts=(CostTap(),)),
                         effect=OptionalEffect(inner=cast(target(), replace=INTO_GRAVEYARD))),
    )
    for ability in shapes:
        rec = card(ability)
        assert at.permission_fault(rec.keywords, rec.abilities) is None, ability
        assert from_dict("CardRecord", to_dict(rec)) == rec


# ------------------------------------------------------------------------------ 2. zone, duration


@pytest.mark.parametrize(
    "source, roles",
    [
        (Selector(QUnbounded(), SelectorMode.ALL, CREATURE, zones=(ANY,)), {}),  # no zone named
        (Selector(QUnbounded(), SelectorMode.ALL, CREATURE,
                  zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),)), {}),
        (Selector(QUnbounded(), SelectorMode.ALL, CREATURE,
                  zones=(Zone(ZoneKind.LIBRARY, ControllerRef.YOU),)), {}),  # the whole library
        (Selector(QUnbounded(), SelectorMode.ALL, CREATURE,
                  zones=(Zone(ZoneKind.GRAVEYARD, ControllerRef.OPPONENT),)), {}),
        (Selector(QUnbounded(), SelectorMode.ALL, CREATURE, zones=(HAND,)), {}),  # the rules' own
    ],
)
def test_a_permission_names_its_zone(source, roles) -> None:
    with pytest.raises(ValueError, match="names the zone|needs no permission"):
        permit(source, **roles)


def test_a_resolving_permission_needs_its_duration() -> None:
    """CR 611.2a: a permission a resolving ability makes lasts as long as it says."""
    rec_error = "its duration is required"
    for ability in (
        triggered(permit(result(), lands=True)),
        ActivatedAbility(cost=Cost(parts=(CostTap(),)), effect=permit(target())),
        SpellAbility(kind=SpellKind.SORCERY, effect=Seq(steps=(permit(result()), permit(target())))),
    ):
        with pytest.raises(ValueError, match=rec_error):
            card(ability, types=("Sorcery",) if isinstance(ability, SpellAbility) else ("Creature",))


@pytest.mark.parametrize(
    "atom, why",
    [
        (permit(every(), duration=DurationEot()), "no duration"),
        (permit(every(), count=QConst(1)), "counts no plays"),
        (permit(target()), "a population"),
        (permit(result()), "a population"),
    ],
)
def test_a_static_permission_lasts_while_the_static_functions(atom, why) -> None:
    with pytest.raises(ValueError, match=why):
        card(StaticAbility(effect=atom))


def test_permit_durations_counts_and_costs_say_one_thing() -> None:
    for roles, why in (
        ({"duration": DurationUntilNextTurn()}, "duration must be one of"),
        ({"count": QUnbounded()}, "a literal of 1 or more"),
        ({"count": QConst(0)}, "a literal of 1 or more"),
        ({"additional": Cost()}, "adds nothing"),
        ({"lands": False}, "second form of absent"),
    ):
        with pytest.raises(ValueError, match=why):
            permit(result(), **roles)
    for mode in (SelectorMode.CHOOSE, SelectorMode.ONE_OF, SelectorMode.RANDOM):
        with pytest.raises(ValueError, match="names its cards ALL"):
            permit(Selector(QConst(1), mode, CREATURE, zones=(GY,)))
    with pytest.raises(ValueError, match="population: its count is QUnbounded"):
        permit(Selector(QConst(2), SelectorMode.ALL, CREATURE, zones=(GY,)))


# ------------------------------------------------------------------------------ 3. one encoding


def test_may_play_has_one_encoding() -> None:
    """The permission's "you may" is its use (CR 601.3): an OptionalEffect around it, anywhere in
    the effect, is a phantom ask and a second byte form; so is the old permission row, a free
    activation or a static whose effect casts."""
    with pytest.raises(ValueError, match="its own \"you may\""):
        OptionalEffect(inner=permit(result(), duration=DurationEot()))
    with pytest.raises(ValueError, match="its own \"you may\""):
        OptionalEffect(inner=Seq(steps=(cast(target()), permit(result(), duration=DurationEot()))))
    with pytest.raises(ValueError, match="old permission row"):
        card(ActivatedAbility(cost=Cost(), effect=OptionalEffect(inner=cast(every()))))
    with pytest.raises(ValueError, match="CAST in a static"):
        card(StaticAbility(effect=cast(every())))
    # the costed row the base wrote for Demonic Embrace's graveyard cast: as an activation it
    # would cast at instant speed from the graveyard (CR 113.6m, 608.2g), or never
    embrace_row = ActivatedAbility(
        cost=Cost(parts=(CostLife(amount=QConst(3)),)),
        effect=OptionalEffect(inner=cast(Selector(QConst(1), SelectorMode.CHOOSE, SELF,
                                                  zones=(GY,)))),
    )
    with pytest.raises(ValueError, match="casts its own card"):
        card(embrace_row)
    card(StaticAbility(effect=permit(every(SELF, GY),
                                     additional=Cost(parts=(CostLife(amount=QConst(3)),)))))


def test_play_and_cast_are_spelled_one_way() -> None:
    """A land is never cast (CR 305.9): "play lands" is ``lands`` True, never a cast of lands;
    playing only nonland cards is casting spells, never ``lands`` with the lands filtered out."""
    with pytest.raises(ValueError, match="a land is never cast"):
        permit(every(LAND))
    with pytest.raises(ValueError, match="leave `lands` out"):
        permit(every(FAnd((CREATURE, FNot(inner=LAND)))), lands=True)
    with pytest.raises(ValueError, match="never uses the stack"):
        permit(every(LAND), lands=True, replace=INTO_GRAVEYARD)
    for role, value in (("alternative", Cost()), ("additional", Cost(parts=(CostTap(),)))):
        with pytest.raises(ValueError, match="special action with no cost"):
            permit(every(LAND), lands=True, **{role: value})
    with pytest.raises(ValueError, match="a land is never cast"):
        cast(target(LAND))


def test_a_granted_static_permission_is_the_resolving_one() -> None:
    """Each card that "gains 'You may play this card from your graveyard'" is the resolving
    PERMIT over those cards, with its duration."""
    grant = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(pairs=(
            ("ability", StaticAbility(effect=permit(every(SELF, GY), lands=True))),
            ("target", Selector(QUnbounded(), SelectorMode.ALL, CREATURE, zones=(GY,))),
            ("duration", DurationEot()),
        )),
    )
    with pytest.raises(ValueError, match="granted static PERMIT"):
        card(triggered(grant))


def test_a_spells_rider_lives_on_its_cast_verb() -> None:
    """"If that spell would be put into your graveyard, exile it instead" is the cast verb's
    ``replace``: a card-level replacement of a zone change from the stack is refused (the base
    compiled Chandra, Flame's Catalyst's rider that way, a static of the planeswalker that read
    "that spell" as any target), and so is any other replacement in the role."""
    stray = ReplacementAbility(
        event=ZoneChangeEvent(from_zone=Zone(ZoneKind.STACK, ControllerRef.ANY), to_zone=GY,
                              subject=FAtom(pred=FAtomPred.IS_ANY_TARGET)),
        condition=None,
        action=INTO_GRAVEYARD.action,
    )
    with pytest.raises(ValueError, match="cast verb's `replace` role"):
        card(stray)
    with pytest.raises(ValueError, match="no other replacement"):
        cast(target(), replace=stray)
    assert INTO_GRAVEYARD != OFF_THE_STACK


# ------------------------------------------------------------------------------ 4. other verbs


def test_a_permission_on_a_verb_that_cannot_carry_it() -> None:
    """CAST casts now (CR 608.2g): no duration, no count, no "play". A move takes no rider. A
    PERMIT under EachPlayer would rotate who may play."""
    for role, value in (("duration", DurationEot()), ("count", QConst(1)), ("lands", True)):
        with pytest.raises(ValueError, match="does not take roles"):
            cast(target(), **{role: value})
    with pytest.raises(ValueError, match="does not take roles"):
        Atom(verb=Verb.MOVE_ZONE, args=AtomArgs(pairs=(
            ("destination", EXILE), ("cards", result()), ("replace", INTO_GRAVEYARD))))
    with pytest.raises(ValueError, match="under EachPlayer"):
        card(triggered(EachPlayer(ref=ControllerRef.ALL_OPPONENTS,
                                  effect=permit(result(), duration=DurationEot()))))


# ------------------------------------------------------------------------------ 5. the review's


def test_a_free_cast_from_the_hand_has_one_encoding() -> None:
    """"You may cast spells from your hand without paying their mana costs" (Omniscience) is the
    static PERMIT over the hand with an empty `alternative`; the cost delta that also wrote it,
    CostDeltaWaiveMana (skipped by the engine), is gone (fresh-eyes review, finding 1)."""
    assert not hasattr(at, "CostDeltaWaiveMana")
    card(StaticAbility(effect=permit(every(FAnd(()), HAND), alternative=Cost())))


def test_a_referent_source_is_the_result_register_whole() -> None:
    """A PERMIT reads the whole `result` register (the cards the instruction before it moved): a
    filter on it would not be read, and another register is never written before it (review,
    finding 2: a filtered `result` played stronger than printed, a `source` register crashed)."""
    with pytest.raises(ValueError, match="a filter on it is not read"):
        permit(Selector(QConst(1), SelectorMode.CHOOSE, CREATURE, zones=(ANY,), referent="result"),
               duration=DurationEot())
    for name in ("source", "controller", "event"):
        with pytest.raises(ValueError, match="not '" + name + "'"):
            permit(Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()), zones=(ANY,), referent=name),
                   duration=DurationEot())


def test_roles_that_limit_or_add_nothing_are_refused() -> None:
    """Review, finding 3: `lands` over cards that are never lands is casting (CR 305.9); a count
    as large as a designation limits nothing (each designated card plays once, CR 400.7); a card
    in a library or a hand is never designated (CR 400.2); a CAST of a permanent or a spell casts
    nothing (CR 601.2a); a lands-only filter written as a disjunction is still lands only."""
    instants = FOr(children=(FAtom(pred=FAtomPred.TYPE_EQ, string_value="Instant"),
                             FAtom(pred=FAtomPred.TYPE_EQ, string_value="Sorcery")))
    with pytest.raises(ValueError, match="never lands is casting"):
        permit(every(instants, GY), lands=True)
    permit(every(instants, GY))  # the same permission, cast
    permit(every(FOr(children=(LAND, CREATURE)), TOP), lands=True)  # play lands, cast creatures
    with pytest.raises(ValueError, match="limits nothing"):
        permit(target(), count=QConst(1), duration=DurationEot())
    permit(Selector(QConst(2), SelectorMode.TARGET, CREATURE, zones=(GY,)), count=QConst(1),
           duration=DurationEot())
    for zone in (TOP, HAND):
        with pytest.raises(ValueError, match="never designated"):
            permit(Selector(QConst(1), SelectorMode.TARGET, CREATURE, zones=(zone,)),
                   alternative=Cost(), duration=DurationEot())
    for kind in (ZoneKind.BATTLEFIELD, ZoneKind.STACK):
        with pytest.raises(ValueError, match="never cast"):
            cast(Selector(QConst(1), SelectorMode.TARGET, CREATURE,
                          zones=(Zone(kind, ControllerRef.ANY),)))
    with pytest.raises(ValueError, match="a land is never cast"):
        cast(target(FOr(children=(LAND, CREATURE))))


# ------------------------------------------------------------------------------ 6. gate round 13

LIBRARY = Zone(ZoneKind.LIBRARY, ControllerRef.YOU)
GATE_13_FORMS = {
    # the hand's lands are the rules' to play (CR 305.1)
    "lands over the hand": (
        lambda: card(StaticAbility(effect=permit(every(FAnd(()), HAND), lands=True,
                                                 alternative=Cost()))),
        "lands` over your hand adds nothing"),
    # a cast never takes a land: the same permission as over every card (CR 305.9)
    "a cast over FNot(Land)": (
        lambda: card(StaticAbility(effect=permit(every(FNot(inner=LAND), GY)))),
        "FNot\\(Land\\) on a cast permission adds nothing"),
    # "play lands and cast spells from the top" is one PERMIT with lands
    "a lands-only and a cast PERMIT over one zone": (
        lambda: card(StaticAbility(effect=Seq(steps=(permit(every(LAND, TOP), lands=True),
                                                     permit(every(FAnd(()), TOP)))))),
        "are one permission"),
    # a card's own alternative cost is its spell's (CR 118.9), wherever it is cast from
    "a card's own cost from the hand": (
        lambda: card(StaticAbility(effect=permit(every(SELF, HAND),
                                                 alternative=Cost(parts=(CostTap(),))))),
        "its spell's alternative cost"),
    # a population over its own card covers the new object it becomes (CR 400.7)
    "a resolving PERMIT over its own card": (
        lambda: card(triggered(permit(every(SELF, GY), duration=DurationEot()))),
        "would cover the card again"),
    # a card in a library or a hand is never designated (CR 400.2)
    "a CAST of a TARGET in a library": (
        lambda: card(triggered(cast(Selector(QConst(1), SelectorMode.TARGET, FAnd(()),
                                             zones=(LIBRARY,))))),
        "never designated"),
    "a CAST of a TARGET in a hand": (
        lambda: card(triggered(cast(Selector(QConst(1), SelectorMode.TARGET, FAnd(()),
                                             zones=(HAND,))))),
        "never designated"),
}


@pytest.mark.parametrize("form", sorted(GATE_13_FORMS))
def test_the_gate_13_forms_are_refused(form: str) -> None:
    """Gate round 13's seven forms the IR accepted on f01b303f (`gate13/ir_forms.py`): each says
    nothing or says what another form says. No tree of the 19 sets uses one."""
    build, why = GATE_13_FORMS[form]
    with pytest.raises(ValueError, match=why):
        build()
