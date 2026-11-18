"""Round B12's IR (DESIGN_ATOM_ONTOLOGY §19): the opening-hand ability (CR 103.6a), the
prohibitions (CR 101.2: a PREVENT_EFFECT over a cast, a move onto the battlefield, a life gain or a
game outcome) and the game's end (LOSE_GAME and WIN_GAME with their player, CR 104.2b, 104.3e).

Each accepted form round-trips; each refused form is a second encoding of a meaning the IR has, or
a role or a node where it means nothing (the gate rounds' two most frequent MAJOR findings). On the
base (eaedfc1b) the module fails to import: none of the forms exists there.
"""

from __future__ import annotations

import pytest

from MTG_bot.core import ability_tree as at
from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CastSpellEvent,
    ControllerRef,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    GameOutcomeEvent,
    LifeGainedEvent,
    OpeningHandAbility,
    QAtLeast,
    QConst,
    Selector,
    SelectorMode,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    begin_on_battlefield,
    event_player,
)

CREATURE = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
YOU = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
OPPONENT = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT)
GRAVEYARDS = Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY)
BATTLEFIELD = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)


def a(verb: Verb, **roles: object) -> Atom:
    return Atom(verb=verb, args=AtomArgs(pairs=tuple(roles.items())))


def prevent(event: object, condition: object, **roles: object) -> Atom:
    return a(Verb.PREVENT_EFFECT, condition=condition, event=event, **roles)


def card(*abilities: object, types: tuple[str, ...] = ("Enchantment",), token: bool = False):
    return at.CardRecord(
        oracle_id="0a0a0a0a-1111-2222-3333-444444444444", name="Card", type_line=" ".join(types),
        types=types, subtypes=(), supertypes=(), colors=(), color_identity=frozenset(),
        mana_cost=None, mana_value=4, power=None, toughness=None, loyalty=None, keywords=(),
        abilities=tuple(abilities), is_token=token,
    )


def roundtrip(node: object) -> None:
    d = at.to_dict(node)
    assert at.from_dict(str(d["tag"]), d) == node


# ------------------------------------------------------------------ LEYLINE (CR 103.6a)


def test_the_opening_hand_action_is_one_form() -> None:
    """The Leylines' sentence: put this card from your hand onto the battlefield, "you may" its
    OptionalEffect; on an enchantment, an artifact or any permanent card."""
    ability = OpeningHandAbility(begin_on_battlefield())
    roundtrip(ability)
    card(ability)
    card(ability, types=("Artifact",))


@pytest.mark.parametrize(
    "effect",
    [
        # mandatory: CR 103.6 makes every opening-hand action a "may" (the may is its ask)
        begin_on_battlefield().inner,
        # tapped, onto another battlefield, from another zone, another verb: no card prints them
        at.OptionalEffect(a(Verb.MOVE_ZONE, cards=begin_on_battlefield().inner.args.get("cards"),
                            destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                            tapped_on_enter=True)),
        at.OptionalEffect(a(Verb.MOVE_ZONE, cards=begin_on_battlefield().inner.args.get("cards"),
                            destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.OPPONENT))),
        at.OptionalEffect(a(Verb.MOVE_ZONE,
                            cards=Selector(QConst(1), SelectorMode.CHOOSE,
                                           FAtom(pred=FAtomPred.IS_SOURCE),
                                           (Zone(ZoneKind.LIBRARY, ControllerRef.YOU),)),
                            destination=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU))),
        at.OptionalEffect(a(Verb.DRAW, amount=QConst(1), controller=ControllerRef.YOU)),
    ],
)
def test_another_opening_hand_action_is_refused(effect) -> None:
    with pytest.raises(ValueError, match="OpeningHandAbility"):
        OpeningHandAbility(effect)


def test_an_opening_hand_ability_means_nothing_off_a_permanent_card_of_its_own() -> None:
    """CR 103.6a begins the game with a card on the battlefield: an instant or a sorcery cannot be
    there, a token is in no opening hand, two say it twice, and none works from a back face, a
    token's or an emblem's abilities or a grant."""
    ability = OpeningHandAbility(begin_on_battlefield())
    for refused in (
        lambda: card(ability, types=("Instant",)),
        lambda: card(ability, types=("Sorcery",)),
        lambda: card(ability, token=True),
        lambda: card(ability, ability),
        lambda: card(at.BackFace(face_name="Back", abilities=(ability,))),
        lambda: card(at.StaticAbility(a(
            Verb.GRANT_ABILITY, ability=ability,
            target=Selector(QConst(1), SelectorMode.CHOOSE, FAtom(pred=FAtomPred.IS_SOURCE),
                            (BATTLEFIELD,))))),
    ):
        with pytest.raises(ValueError):
            refused()
    with pytest.raises(ValueError):
        at.EmblemSpec(abilities=(ability,))


# ------------------------------------------------------------------ PROHIBIT (CR 101.2)


def test_the_prohibitions_round_trip() -> None:
    """Rule of Law's QAtLeast(2) ordinal, a cast from a zone, a move onto the battlefield, a life
    gain and a game outcome: each a PREVENT_EFFECT whose condition is the event's subject."""
    for node in (
        prevent(CastSpellEvent(filter=FAnd(()), ordinal=QAtLeast(2)), FAnd(())),
        prevent(CastSpellEvent(filter=FNot(CREATURE), ordinal=QAtLeast(2)), FNot(CREATURE)),
        prevent(CastSpellEvent(filter=FAnd(()), from_zone=GRAVEYARDS), FAnd(())),
        prevent(ZoneChangeEvent(GRAVEYARDS, BATTLEFIELD, subject=CREATURE), CREATURE),
        prevent(LifeGainedEvent(actor=OPPONENT), FAnd(()), duration=at.DurationEot()),
        prevent(GameOutcomeEvent(won=False, actor=YOU), FAnd(())),
        prevent(GameOutcomeEvent(won=True, actor=OPPONENT), FAnd(())),
    ):
        roundtrip(node)


@pytest.mark.parametrize(
    ("make", "match"),
    [
        # the condition is the event's subject: anything else says the restriction a second time
        # ("can't cast" as a condition over the caster, the spell's type in the condition)
        (lambda: prevent(CastSpellEvent(filter=FAnd(()), actor=OPPONENT), OPPONENT), "condition"),
        (lambda: prevent(CastSpellEvent(filter=FAnd(())), CREATURE), "condition"),
        (lambda: prevent(LifeGainedEvent(), OPPONENT), "condition"),
        (lambda: prevent(GameOutcomeEvent(won=False), YOU), "condition"),
        (lambda: prevent(ZoneChangeEvent(GRAVEYARDS, BATTLEFIELD, subject=CREATURE), FAnd(())),
         "condition"),
        # a prohibited move with no subject (whose move?), into a graveyard, from the hand, the
        # command zone or anywhere (moves the enter lane does not make)
        (lambda: prevent(ZoneChangeEvent(GRAVEYARDS, BATTLEFIELD), FAnd(())), "names the cards"),
        (lambda: prevent(ZoneChangeEvent(BATTLEFIELD, GRAVEYARDS, subject=CREATURE), CREATURE),
         "entering the battlefield"),
        (lambda: prevent(ZoneChangeEvent(Zone(ZoneKind.HAND, ControllerRef.ANY), BATTLEFIELD,
                                         subject=CREATURE), CREATURE), "entering the battlefield"),
        (lambda: prevent(ZoneChangeEvent(Zone(ZoneKind.COMMAND, ControllerRef.OPPONENT),
                                         BATTLEFIELD, subject=CREATURE), CREATURE),
         "entering the battlefield"),
        (lambda: prevent(ZoneChangeEvent(Zone(ZoneKind.ANY, ControllerRef.ANY), BATTLEFIELD,
                                         subject=CREATURE), CREATURE), "entering the battlefield"),
        # roles that mean nothing on a prohibition
        (lambda: prevent(LifeGainedEvent(), FAnd(()), step=at.Step.UNTAP), "mean nothing"),
        (lambda: prevent(GameOutcomeEvent(won=False, actor=YOU), FAnd(()),
                         controller=ControllerRef.YOU), "mean nothing"),
        # an exact ordinal is a trigger's: "can't cast more than one" is QAtLeast(2), never 2
        (lambda: prevent(CastSpellEvent(filter=FAnd(()), ordinal=2), FAnd(())), "exact event"),
        # the review's two second encodings: a universal actor is the absent one, and the
        # spell's controller is its caster ("your opponents can't cast" is the actor's)
        (lambda: prevent(LifeGainedEvent(actor=FAnd(())), FAnd(())), "universal actor"),
        (lambda: prevent(GameOutcomeEvent(won=False, actor=FAnd(())), FAnd(())), "universal actor"),
        (lambda: prevent(CastSpellEvent(filter=FAnd(()), actor=FAnd(())), FAnd(())),
         "universal actor"),
        (lambda: prevent(CastSpellEvent(filter=OPPONENT), OPPONENT), "names its caster"),
        (lambda: prevent(CastSpellEvent(filter=FAnd((CREATURE, YOU))), FAnd((CREATURE, YOU))),
         "names its caster"),
    ],
)
def test_a_prohibition_says_its_restriction_once(make, match) -> None:
    with pytest.raises(ValueError, match=match):
        make()


def test_the_at_least_ordinal_is_a_prohibitions_alone() -> None:
    """QAtLeast(1) is every cast (the absent ordinal); a trigger's ordinal is the exact Nth; a
    game outcome is never a trigger's, a replacement's or a history's (the game is over)."""
    with pytest.raises(ValueError, match="n >= 2"):
        CastSpellEvent(filter=FAnd(()), ordinal=QAtLeast(1))
    gain = a(Verb.GAIN_LIFE, amount=QConst(1), controller=ControllerRef.YOU)
    with pytest.raises(ValueError, match="prohibition"):
        at.TriggeredAbility(CastSpellEvent(filter=FAnd(()), ordinal=QAtLeast(2)), None, gain)
    with pytest.raises(ValueError, match="prohibition"):
        at.DelayedTrigger(duration=at.DurationEot(), event=CastSpellEvent(
            filter=FAnd(()), ordinal=QAtLeast(2)), condition=None, effect=gain)
    with pytest.raises(ValueError, match="prohibition"):
        at.TriggeredAbility(GameOutcomeEvent(won=False), None, gain)
    with pytest.raises(ValueError, match="prohibition"):
        at.ReplacementAbility(GameOutcomeEvent(won=False), None, gain)
    with pytest.raises(ValueError, match="cannot read GameOutcomeEvent"):
        FAtom(pred=FAtomPred.EVENT_THIS_TURN, event=GameOutcomeEvent(won=False), count=QConst(1))
    with pytest.raises(ValueError):
        GameOutcomeEvent(won=None)  # type: ignore[arg-type]
    at.TriggeredAbility(CastSpellEvent(filter=FAnd(()), ordinal=2), None, gain)  # the trigger's


# ------------------------------------------------------------------ GAMEEND (CR 104)


def test_who_loses_or_wins_is_named_once() -> None:
    """LOSE_GAME names its player in `controller`: you, the printed target, or "that player" of a
    trigger's event (event_player, R_ITSCONTROLLER's referent); WIN_GAME you."""
    for who in (ControllerRef.YOU, ControllerRef.TARGET_PLAYER, ControllerRef.TARGET_OPPONENT,
                event_player()):
        roundtrip(a(Verb.LOSE_GAME, controller=who))
    roundtrip(a(Verb.WIN_GAME, controller=ControllerRef.YOU))


@pytest.mark.parametrize(
    ("verb", "who"),
    [
        # each opponent: EachPlayer around LOSE_GAME(YOU), one form (D21's plural role refused)
        (Verb.LOSE_GAME, ControllerRef.ALL_OPPONENTS),
        (Verb.LOSE_GAME, ControllerRef.OPPONENT),
        (Verb.LOSE_GAME, ControllerRef.ANY),
        (Verb.LOSE_GAME, ControllerRef.DEFENDING_PLAYER),
        (Verb.LOSE_GAME, ControllerRef.OWNER),
        # the designated player's second form (gate round 8, M1), the controller's, the result's
        (Verb.LOSE_GAME, Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()),
                                  (Zone(ZoneKind.ANY, ControllerRef.ANY),), referent="target")),
        (Verb.LOSE_GAME, Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()),
                                  (Zone(ZoneKind.ANY, ControllerRef.ANY),), referent="result")),
        (Verb.LOSE_GAME, Selector(QConst(1), SelectorMode.CHOOSE, CREATURE,
                                  (Zone(ZoneKind.ANY, ControllerRef.ANY),), referent="event")),
        (Verb.WIN_GAME, ControllerRef.TARGET_PLAYER),
        (Verb.WIN_GAME, event_player()),
        (Verb.WIN_GAME, ControllerRef.ALL_OPPONENTS),
    ],
)
def test_another_player_form_is_refused(verb, who) -> None:
    with pytest.raises(ValueError, match="controller must be"):
        a(verb, controller=who)


def test_a_game_result_is_one_players_and_a_resolving_effects() -> None:
    """One player wins (CR 104.2b): EachPlayer around WIN_GAME would rotate "you" past the YOU-only
    rule; and a game result happens as an effect resolves, so a static's never runs ("can't
    lose" is the PREVENT_EFFECT). "Each opponent loses the game" stays EachPlayer's."""
    win, lose = (a(verb, controller=ControllerRef.YOU) for verb in (Verb.WIN_GAME, Verb.LOSE_GAME))
    with pytest.raises(ValueError, match="one player wins"):
        at.EachPlayer(ControllerRef.ALL_OPPONENTS, win)
    at.EachPlayer(ControllerRef.ALL_OPPONENTS, lose)
    for atom in (win, lose):
        with pytest.raises(ValueError, match="never a static's"):
            at.StaticAbility(atom)
    # a static granting a trigger that loses the game is that trigger's own resolving effect
    dies = at.TriggeredAbility(
        at.CreatureDiesEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)), None, lose)
    at.StaticAbility(a(Verb.GRANT_ABILITY, ability=dies, target=Selector(
        QConst(1), SelectorMode.CHOOSE, FAtom(pred=FAtomPred.IS_SOURCE), (BATTLEFIELD,))))


def test_a_game_result_names_its_player() -> None:
    """LOSE_GAME with no player made the ability's controller lose (the base's form): the role is
    required now, as every player verb's ("you lose 2 life")."""
    for verb in (Verb.LOSE_GAME, Verb.WIN_GAME):
        with pytest.raises(ValueError, match="missing required roles"):
            a(verb)
