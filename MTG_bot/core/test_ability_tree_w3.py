"""Ontology gate round W3 (DESIGN_ATOM_ONTOLOGY §19): the IR's three new forms and every form that
must not validate.

- A state trigger (CR 603.8) is ``TriggeredAbility(event=StateTrigger(filter))``, its state read
  over the object with the ability. Refused: IS_SOURCE anywhere in it, the universal state, an
  intervening "if", once_per_event, a read of an event register it does not have, a target or a
  designated player, a grant, a state anywhere but a trigger's event, and the state written as a
  counter-placed event (the old Nine Lives form).
- "That ability triggers an additional time" (CR 603.2d) is a static ability:
  ``StaticAbility(TRIGGER_ADDITIONAL(count, event=AbilityTriggerEvent(filter, cause?)))``. Refused:
  the old carrier trigger, an event that is not an ability triggering, a count that is not a
  printed number of at least one, two equal steps, the verb anywhere but a card's, token's,
  emblem's or copy's own static, a test that reads no subject in the filter (the static's
  condition is its one home), a cause that is not an object entering the battlefield.
- REVEAL names the cards it shows (CR 701.20a): the top ``count`` of a library, a whole hand
  (``reveal_hand``), or the cards the instruction before found, moved or picked
  (``reveal_result``). Refused: the old "whole library" count (it encoded a hand and a search's
  cards alike), ``cards`` beside the other roles, any other ``cards``, ``reveal_result`` with no
  step before it that found cards, and the old pick form (a top-``count`` reveal after a look).

Every refusal here validated on main 0b7f9c22 (or the class did not exist), so each test fails
there."""

from __future__ import annotations

import pytest

from MTG_bot.core.ability_tree import (
    RESULT_REFERENT,
    AbilityTriggerEvent,
    ActivatedAbility,
    Atom,
    AtomArgs,
    CardRecord,
    ControllerRef,
    Cost,
    CostTap,
    CounteredEvent,
    CounterKind,
    CounterPlacedEvent,
    DelayedTrigger,
    DurationEot,
    EmblemSpec,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    OptionalEffect,
    Phase,
    PhasingEvent,
    QConst,
    QProp,
    QPropField,
    QUnbounded,
    QX,
    ReplacementAbility,
    Selector,
    SelectorMode,
    Seq,
    SpellAbility,
    SpellKind,
    StateTrigger,
    StaticAbility,
    Step,
    StepEvent,
    TokenSpec,
    TriggeredAbility,
    TurnPhaseEvent,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    ZonePosition,
    at_least,
    from_dict,
    number_you_control,
    reveal_hand,
    reveal_result,
    to_dict,
)


def A(verb: Verb, **roles) -> Atom:
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


NINE = FAtom(pred=FAtomPred.HAS_COUNTER, counter_kind=CounterKind.INCARNATION, count=QConst(9))
SOURCE = FAtom(pred=FAtomPred.IS_SOURCE)
YOURS = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
SHRINE = FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Shrine")
THIS = Selector(QConst(1), SelectorMode.CHOOSE, SOURCE, zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))
EXILE_IT = A(Verb.MOVE_ZONE, destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER), target=THIS)
DRAW = A(Verb.DRAW, controller=ControllerRef.YOU, amount=QConst(1))
UPKEEP = TurnPhaseEvent(Phase.UPKEEP, actor=YOURS)
ENTERING = ZoneChangeEvent(
    from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY), to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)
)
EVENT_IT = Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()), zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
                    referent="event")
LIBRARY = Zone(ZoneKind.LIBRARY, ControllerRef.YOU)
TOP = Zone(ZoneKind.LIBRARY, ControllerRef.YOU, ZonePosition.TOP)
HAND_YOU = Zone(ZoneKind.HAND, ControllerRef.YOU)


def extra(event=None, count=QConst(1)) -> Atom:
    return A(Verb.TRIGGER_ADDITIONAL, count=count,
             event=event if event is not None else AbilityTriggerEvent(filter=YOURS, cause=ENTERING))


def card(*abilities, types=("Enchantment",)) -> CardRecord:
    """A card record, the level the placement checks run at (CardRecord.__post_init__)."""
    return CardRecord(
        oracle_id="00000000-0000-4000-8000-0000000000f3", name="W3 Test", type_line=" ".join(types),
        types=types, subtypes=(), supertypes=(), colors=(), color_identity=frozenset(),
        mana_cost=None, mana_value=1, power=None, toughness=None, loyalty=None, keywords=(),
        abilities=abilities, is_token=False,
    )


# ---------------------------------------------------------------------------- state triggers


def test_a_state_trigger_is_a_state_read_over_its_object() -> None:
    nine_lives = TriggeredAbility(event=StateTrigger(filter=NINE), condition=None, effect=EXILE_IT)
    assert from_dict("TriggeredAbility", to_dict(nine_lives)) == nine_lives
    # a state that reads no subject (Phylactery Lich's "you control no permanents with ...")
    none_left = FNot(inner=at_least(1, quantity=number_you_control(
        FAtom(pred=FAtomPred.HAS_COUNTER, counter_kind=CounterKind.CHARGE, count=QConst(1)))))
    TriggeredAbility(event=StateTrigger(filter=none_left), condition=None, effect=EXILE_IT)


@pytest.mark.parametrize("state", [
    SOURCE, FAnd(children=(SOURCE, NINE)), FAnd(()), FNot(inner=SOURCE), FOr(children=(SOURCE, NINE)),
    FAnd(children=(FNot(inner=SOURCE), NINE)),
], ids=["IS_SOURCE", "IS_SOURCE-conjunct", "universal", "never", "always", "nested"])
def test_a_state_says_nothing_twice_and_is_never_always_true(state) -> None:
    with pytest.raises(ValueError, match="StateTrigger"):
        StateTrigger(filter=state)


def test_a_state_trigger_has_no_intervening_if_no_occurrences_and_no_event_to_read() -> None:
    state = StateTrigger(filter=NINE)
    with pytest.raises(ValueError, match="intervening"):
        TriggeredAbility(event=state, condition=YOURS, effect=EXILE_IT)
    with pytest.raises(ValueError, match="no occurrences"):
        TriggeredAbility(event=state, condition=None, effect=EXILE_IT, once_per_event=True)
    for reads_event in (
        A(Verb.MOVE_ZONE, destination=Zone(ZoneKind.EXILE, ControllerRef.OWNER), target=EVENT_IT),
        A(Verb.GAIN_LIFE, controller=ControllerRef.YOU, amount=QProp("event", QPropField.POWER)),
    ):
        with pytest.raises(ValueError, match="no triggering event"):
            TriggeredAbility(event=state, condition=None, effect=reads_event)


def test_a_state_trigger_designates_nothing_and_is_never_granted() -> None:
    """A targeted state trigger with no legal target is removed as it goes on the stack (CR
    603.3d) and triggers again at once while the state holds: a loop no card of the 19 sets
    prints. A granted one would never be checked (the binder checks bound abilities)."""
    state = StateTrigger(filter=NINE)
    creature = Selector(QConst(1), SelectorMode.TARGET, FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),))
    for designating in (A(Verb.DESTROY, target=creature),
                        A(Verb.DRAW, controller=ControllerRef.TARGET_PLAYER, amount=QConst(1))):
        with pytest.raises(ValueError, match="designates nothing"):
            TriggeredAbility(event=state, condition=None, effect=designating)
    with pytest.raises(ValueError, match="granted state trigger"):
        A(Verb.GRANT_ABILITY, target=THIS,
          ability=TriggeredAbility(event=state, condition=None, effect=EXILE_IT))


def test_a_state_is_only_a_triggers_event() -> None:
    state = StateTrigger(filter=NINE)
    with pytest.raises(ValueError, match="delayed trigger can match"):
        DelayedTrigger(duration=DurationEot(), event=state, condition=None, effect=DRAW)
    with pytest.raises(ValueError, match="replacement can replace"):
        ReplacementAbility(event=state, condition=None, action=DRAW)
    with pytest.raises(ValueError, match="a state is no event"):
        A(Verb.PREVENT_EFFECT, condition=YOURS, event=state)
    with pytest.raises(ValueError, match="no journal history"):
        FAtom(pred=FAtomPred.EVENT_THIS_TURN, event=state, count=QConst(1))
    with pytest.raises(ValueError, match="cause"):
        AbilityTriggerEvent(filter=YOURS, cause=state)


def test_the_state_written_as_a_counter_placement_is_refused() -> None:
    """The old Nine Lives form: a placement that tests the count it reaches is the state (CR
    603.8), which it read on every placement while its first instance waited."""
    with pytest.raises(ValueError, match="state trigger"):
        CounterPlacedEvent(counter_kind=CounterKind.INCARNATION, filter=FAnd(children=(SOURCE, NINE)))
    with pytest.raises(ValueError, match="state trigger"):
        CounterPlacedEvent(counter_kind=CounterKind.INCARNATION, filter=NINE)
    # another kind's count is no such state ("whenever a charge counter is put on a creature
    # with nine incarnation counters" says something else)
    CounterPlacedEvent(counter_kind=CounterKind.CHARGE, filter=FAnd(children=(SOURCE, NINE)))


# ---------------------------------------------------------------------------- extra triggers


def test_an_additional_time_is_a_static_with_an_ability_triggering() -> None:
    sanctum = StaticAbility(
        effect=extra(AbilityTriggerEvent(filter=FAnd(children=(SHRINE, YOURS, FNot(inner=SOURCE))))),
        condition=at_least(6, quantity=number_you_control(SHRINE)),
    )
    yarok = StaticAbility(effect=extra())
    for static in (sanctum, yarok):
        assert from_dict("StaticAbility", to_dict(static)) == static
        card(static)
    # a token's, an emblem's own static
    card(SpellAbility(kind=SpellKind.SORCERY, effect=A(
        Verb.CREATE_TOKEN, tokens=TokenSpec(name="Doubler", type_line="Artifact", types=("Artifact",),
                                            subtypes=(), power=None, toughness=None, keywords=(),
                                            abilities=(yarok,)))),
        types=("Sorcery",))
    card(SpellAbility(kind=SpellKind.SORCERY, effect=A(
        Verb.GET_EMBLEM, emblem=EmblemSpec(abilities=(yarok,)), controller=ControllerRef.YOU)),
        types=("Sorcery",))


def test_the_carrier_trigger_is_refused() -> None:
    """The old Sanctum of All form: a trigger of its own, which went on the stack between the
    original and its copy."""
    with pytest.raises(ValueError, match="static ability"):
        TriggeredAbility(event=AbilityTriggerEvent(filter=YOURS), condition=None, effect=DRAW)
    with pytest.raises(ValueError, match="delayed trigger can match"):
        DelayedTrigger(duration=DurationEot(), event=AbilityTriggerEvent(filter=YOURS), condition=None,
                       effect=DRAW)
    with pytest.raises(ValueError, match="replacement can replace"):
        ReplacementAbility(event=AbilityTriggerEvent(filter=YOURS), condition=None, action=DRAW)
    with pytest.raises(ValueError, match="only TRIGGER_ADDITIONAL"):
        A(Verb.PREVENT_EFFECT, condition=YOURS, event=AbilityTriggerEvent(filter=YOURS))


@pytest.mark.parametrize("event", [ENTERING, UPKEEP, CounteredEvent(filter=YOURS)],
                         ids=["zone-change", "turn-phase", "countered"])
def test_an_additional_time_is_over_a_triggered_ability_only(event) -> None:
    with pytest.raises(ValueError, match="AbilityTriggerEvent"):
        extra(event)


@pytest.mark.parametrize("count", [QConst(0), QUnbounded(), QX()], ids=["zero", "unbounded", "X"])
def test_an_additional_time_is_at_least_once(count) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        extra(count=count)


def test_the_six_shrines_are_the_statics_condition_not_the_filter() -> None:
    """A test that reads no subject in the filter would be the static's condition's second
    encoding (the old carrier's filter held Sanctum's count)."""
    with pytest.raises(ValueError, match="static's condition"):
        AbilityTriggerEvent(filter=FAnd(children=(SHRINE, YOURS, at_least(6, quantity=number_you_control(SHRINE)))))


@pytest.mark.parametrize("cause", [
    AbilityTriggerEvent(filter=YOURS), CounteredEvent(filter=YOURS),
    StepEvent(phase=Phase.UPKEEP, step=Step.UNTAP, controller=ControllerRef.YOU),
    PhasingEvent(phased_in=True, filter=YOURS), UPKEEP,
    ZoneChangeEvent(from_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
                    to_zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY)),
    ZoneChangeEvent(from_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
                    to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)),
], ids=["ability-triggering", "countered", "step", "phasing", "upkeep", "dying", "staying"])
def test_a_cause_is_an_object_entering_the_battlefield(cause) -> None:
    """The one cause the 19 sets print (Yarok, Naban, Ancient Greenwarden). A dying creature's
    (Teysa Karlov) needs the copies counted for a look-back trigger whose source has left, which
    the binder does not do: it comes with its card (BACKLOG)."""
    with pytest.raises(ValueError, match="cause"):
        AbilityTriggerEvent(filter=YOURS, cause=cause)


def test_two_additional_times_over_one_ability_are_one_count() -> None:
    """"Two additional times" is one count; two equal steps would be its second encoding."""
    with pytest.raises(ValueError, match="two TRIGGER_ADDITIONAL"):
        Seq(steps=(extra(), extra()))
    StaticAbility(effect=Seq(steps=(extra(), extra(AbilityTriggerEvent(filter=FAnd(children=(SHRINE, YOURS)))))))


@pytest.mark.parametrize("host", ["spell", "trigger", "activation", "granted", "optional"])
def test_an_additional_time_never_resolves_and_is_never_granted(host) -> None:
    effects = {
        "spell": lambda: (SpellAbility(kind=SpellKind.SORCERY, effect=extra()),),
        "trigger": lambda: (TriggeredAbility(event=UPKEEP, condition=None, effect=extra()),),
        "activation": lambda: (ActivatedAbility(cost=Cost(parts=(CostTap(),)), effect=extra()),),
        "granted": lambda: (StaticAbility(effect=A(
            Verb.GRANT_ABILITY, target=THIS, ability=StaticAbility(effect=extra()))),),
        "optional": lambda: (StaticAbility(effect=OptionalEffect(inner=extra())),),
    }
    with pytest.raises(ValueError, match="TRIGGER_ADDITIONAL is a static ability's effect"):
        card(*effects[host]())


# ---------------------------------------------------------------------------- reveals


def test_a_reveal_names_a_hand_or_what_was_found_or_the_top() -> None:
    for atom in (
        reveal_hand(ControllerRef.TARGET_OPPONENT), reveal_hand(ControllerRef.TARGET_PLAYER),
        reveal_result(), A(Verb.REVEAL, controller=ControllerRef.YOU, count=QConst(4)),
        A(Verb.REVEAL, controller=ControllerRef.YOU, count=QConst(1), until=SOURCE),
    ):
        assert from_dict("Atom", to_dict(atom)) == atom
    assert reveal_result().args.get("cards") == RESULT_REFERENT


def test_the_whole_library_count_is_refused() -> None:
    """The old "reveals their hand" (and "reveal those cards") form: the count QUnbounded read the
    library, so the hand's reveal journalled the target's whole library. A second encoding of
    reveal_hand and of reveal_result, and a lie in the record a memory would read."""
    with pytest.raises(ValueError, match="how many cards from the top"):
        A(Verb.REVEAL, controller=ControllerRef.TARGET_OPPONENT, count=QUnbounded())
    with pytest.raises(ValueError, match="how many cards from the top"):
        A(Verb.LOOK_AT, controller=ControllerRef.YOU, count=QUnbounded())
    with pytest.raises(ValueError, match="other cards `cards`"):
        A(Verb.REVEAL, controller=ControllerRef.YOU)
    with pytest.raises(ValueError, match="other cards `cards`"):
        A(Verb.REVEAL, count=QConst(1))


def test_cards_names_the_cards_alone() -> None:
    hand = reveal_hand(ControllerRef.TARGET_OPPONENT).args.get("cards")
    for extra_role in ({"controller": ControllerRef.TARGET_OPPONENT}, {"count": QConst(1)},
                       {"until": SOURCE}):
        with pytest.raises(ValueError, match="alone"):
            A(Verb.REVEAL, cards=hand, **extra_role)
    with pytest.raises(ValueError, match="does not take roles"):
        A(Verb.LOOK_AT, cards=hand, controller=ControllerRef.YOU, count=QConst(1))


@pytest.mark.parametrize("sel", [
    Selector(QUnbounded(), SelectorMode.ALL, SOURCE, zones=(HAND_YOU,)),
    Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()), zones=(HAND_YOU,)),
    Selector(QConst(2), SelectorMode.ALL, FAnd(()), zones=(HAND_YOU,)),
    Selector(QUnbounded(), SelectorMode.ALL, FAnd(()), zones=(LIBRARY,)),
    Selector(QConst(1), SelectorMode.ONE_OF, FAnd(()), zones=(TOP,)),
    Selector(QUnbounded(), SelectorMode.ALL, FAnd(()), zones=(Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),)),
    Selector(QUnbounded(), SelectorMode.ALL, FAnd(()), zones=(HAND_YOU, LIBRARY)),
    Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()), zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
             referent="event"),
    Selector(QConst(1), SelectorMode.CHOOSE, SOURCE, zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
             referent="result"),
], ids=["filtered-hand", "chosen-card", "two-cards", "library", "library-top-pick", "graveyard",
        "two-zones", "event-referent", "filtered-result"])
def test_any_other_cards_is_refused(sel) -> None:
    with pytest.raises(ValueError, match="REVEAL"):
        A(Verb.REVEAL, cards=sel)


def test_a_card_picked_from_a_look_is_revealed_after_its_move() -> None:
    """The old pick form ("reveal a creature card from among them and put it into your hand" as a
    top-1 reveal before the pick) named the look's first card, whatever was picked."""
    look = A(Verb.LOOK_AT, controller=ControllerRef.YOU, count=QConst(4))
    pick = A(Verb.MOVE_ZONE, cards=Selector(QConst(1), SelectorMode.ONE_OF, FAnd(()), zones=(TOP,)),
             destination=HAND_YOU)
    old_reveal = A(Verb.REVEAL, controller=ControllerRef.YOU, count=QConst(1))
    Seq(steps=(look, OptionalEffect(inner=Seq(steps=(pick, reveal_result())))))
    with pytest.raises(ValueError, match="after a look or a search"):
        Seq(steps=(look, OptionalEffect(inner=Seq(steps=(old_reveal, pick)))))
    with pytest.raises(ValueError, match="after a look or a search"):
        Seq(steps=(look, old_reveal, pick))


def test_a_reveal_of_it_follows_the_step_that_found_it() -> None:
    """"Reveal it" reads the cards an instruction before it found, looked at or moved: with none
    before it (first, or after a draw, which writes no register) there is nothing to reveal."""
    search = A(Verb.SEARCH, cards=Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()), zones=(LIBRARY,)),
               destination=HAND_YOU)
    card(SpellAbility(kind=SpellKind.SORCERY, effect=Seq(steps=(search, reveal_result()))), types=("Sorcery",))
    for effect in (reveal_result(), Seq(steps=(DRAW, reveal_result()))):
        with pytest.raises(ValueError, match="reveal of `result`"):
            card(SpellAbility(kind=SpellKind.SORCERY, effect=effect), types=("Sorcery",))


def test_a_card_found_by_a_search_is_revealed_as_its_result() -> None:
    """The old named-tutor form ("search ... for a card named X, reveal it, and put it into your
    hand" with a top-1 reveal after the search) named the library's top card, which nobody saw:
    a graveyard-only search told the opponent the next draw."""
    search = A(Verb.SEARCH, cards=Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()), zones=(LIBRARY,)),
               destination=HAND_YOU)
    Seq(steps=(search, reveal_result()))
    with pytest.raises(ValueError, match="after a look or a search"):
        Seq(steps=(search, A(Verb.REVEAL, controller=ControllerRef.YOU, count=QConst(1))))
