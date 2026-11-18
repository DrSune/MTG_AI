"""B21 bucket: the opening hand, prohibitions and the game's end (DESIGN_ATOM_ONTOLOGY §19).

* "If this card is in your opening hand, you may begin the game with it on the battlefield."
  (the Leylines, CR 103.6a) is an ``OpeningHandAbility`` whose effect is
  ``begin_on_battlefield()``: put this card from your hand onto the battlefield, the "you may" its
  OptionalEffect. ``games.opening_hand_actions`` runs it after the mulligans.
* A prohibition (CR 101.2: "can't" beats "can") is a PREVENT_EFFECT over the event it forbids,
  the one "can't" form every other one has, its condition the event's subject
  (``ability_tree.prohibition_fault``):
  - "Each player can't cast more than one [noncreature] spell each turn." (Rule of Law, Archon
    of Emeria, Deafening Silence): a CastSpellEvent whose ordinal is QAtLeast(2), the casts that
    would be a player's second or later of the spells it describes;
  - "<Players|Your opponents|You> can't cast [<type> [or <type>]] spells [from graveyards [or
    libraries]|from anywhere other than their hands] [this turn|until the end of your next
    turn]." (Grafdigger's Cage, Weathered Runestone, Kunoros, Drannith Magistrate, Silence,
    Steel Golem, Single Combat): a CastSpellEvent with its actor, filter and zone, one
    PREVENT_EFFECT per zone ("graveyards or libraries": a cast comes from one zone); with a
    duration it is the effect of a resolving spell (CR 611.2c);
  - "<Creature|Nonland permanent> cards in graveyards [and libraries] can't enter the
    battlefield." (Grafdigger's Cage, Weathered Runestone, Kunoros): a ZoneChangeEvent from each
    zone onto the battlefield, its subject the cards;
  - "<Players|Your opponents> can't gain life [this turn]." (Giant Cindermaw, Leyline of
    Punishment, Quakebringer, Tibalt, Roiling Vortex): a LifeGainedEvent with its actor;
  - "You can't lose the game and your opponents can't win the game." (Platinum Angel, Herald of
    Eternal Dawn): a GameOutcomeEvent each. DOM Lich's Mastery's "You can't lose the game." alone
    is held back (below).
* "You lose the game." / "Target player|opponent loses the game." and "You win the game." are
  LOSE_GAME and WIN_GAME with their player (Demonic Pact's mode, Door to Nothingness; the
  frames' "At the beginning of your upkeep, if ..., you win the game."). Nine Lives' "you lose
  the game" is B2b's own sentence, the same atom.

Not read, each waiting for its piece: "That player loses the game." alone (a pronoun: Atemsis's
is its record's, Phage's names the card); Lich's Mastery's "You can't lose the game." (the first
of Platinum Angel's two atoms), held back while its three drawbacks do not compile, so the card is
never dealt stronger than printed; a "can't cast" with a condition or a chosen name (Grand
Abolisher, Angelic Arbiter, Serra Avenger, Alhammarret, Ashiok's Erasure); "Damage can't be
prevented." (Leyline of Punishment's other sentence).
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CastSpellEvent,
    ControllerRef,
    DurationEot,
    DurationUntilEndOfNextTurn,
    Effect,
    EventSpec,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    GameOutcomeEvent,
    LifeGainedEvent,
    OpeningHandAbility,
    QAtLeast,
    Seq,
    StaticAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    begin_on_battlefield,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    SentenceOutcome,
    Template,
)

_BUCKET: Final[str] = "B21"
_PRIORITY: Final[int] = 10

_CREATURE: Final[FAtom] = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
_PLAYERS: Final[dict[str, ControllerRef | None]] = {
    "Players": None, "Your opponents": ControllerRef.OPPONENT, "You": ControllerRef.YOU
}
_ZONES: Final[dict[str, ZoneKind]] = {"graveyards": ZoneKind.GRAVEYARD,
                                      "libraries": ZoneKind.LIBRARY}
_DURATIONS: Final[dict[str, object]] = {
    " this turn": DurationEot(), " until the end of your next turn": DurationUntilEndOfNextTurn()
}


def _actor(who: str) -> Filter | None:
    ref = _PLAYERS[who]
    return None if ref is None else FAtom(pred=FAtomPred.CONTROLLER_IS, who=ref)


def prohibit(event: EventSpec, **roles: object) -> Atom:
    """A prohibition (CR 101.2): a PREVENT_EFFECT over ``event``, its condition the event's
    subject (the spell, the moving card; a player's event has none: the universal filter), as
    ``ability_tree.prohibition_fault`` requires."""
    if isinstance(event, CastSpellEvent):
        condition: object = event.filter
    elif isinstance(event, ZoneChangeEvent):
        condition = event.subject
    else:
        condition = FAnd(())
    pairs = (("condition", condition), ("event", event), *roles.items())
    return Atom(verb=Verb.PREVENT_EFFECT, args=AtomArgs(pairs=pairs))


def _carried(atoms: list[Atom], when: str | None) -> SentenceOutcome:
    """A static ability's prohibition, or with a duration a resolving spell's effect (CR 611.2c:
    it changes the rules for that long, its source gone or not)."""
    effect: Effect = atoms[0] if len(atoms) == 1 else Seq(steps=tuple(atoms))
    if when is None:
        return AbilityOutcome(ability=StaticAbility(effect=effect))
    return EffectOutcome(effect=effect)


def _build_opening_hand(m: re.Match[str]) -> SentenceOutcome:
    return AbilityOutcome(ability=OpeningHandAbility(begin_on_battlefield()))


def _build_cast_limit(m: re.Match[str]) -> SentenceOutcome:
    """Each player can't cast more than one [noncreature] spell each turn: the casts that would
    be a player's second or later of those spells (Deafening Silence: "any number of creature
    spells plus one noncreature spell")."""
    spells = FNot(_CREATURE) if m.group("non") else FAnd(())
    return _carried([prohibit(CastSpellEvent(filter=spells, ordinal=QAtLeast(2)))], None)


_SPELL_TYPES: Final[str] = r"(?P<t1>creature)(?: or (?P<t2>planeswalker))?"


def _spells(m: re.Match[str]) -> Filter:
    """The spells named: every spell, or "creature [or planeswalker] spells" (Steel Golem,
    Single Combat)."""
    if m.group("t1") is None:
        return FAnd(())
    if m.group("t2") is None:
        return _CREATURE
    return FOr(children=(_CREATURE, FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker")))


def _build_cant_cast(m: re.Match[str]) -> SentenceOutcome:
    """<Players|Your opponents|You> can't cast [<types>] spells [from <zones>] [<duration>]."""
    actor, spells, when = _actor(m.group("who")), _spells(m), m.group("when")
    roles = {} if when is None else {"duration": _DURATIONS[when]}
    where = m.group("from")
    if where is None:
        events = [CastSpellEvent(filter=spells, actor=actor)]
    elif where == "anywhere other than their hands":
        # "their hands": each caster's own (the zone scopes the caster, binding._cast_zone_matches)
        hand = Zone(ZoneKind.HAND, _PLAYERS[m.group("who")] or ControllerRef.ANY)
        events = [CastSpellEvent(filter=spells, actor=actor, from_zone_not=hand)]
    else:
        events = [
            CastSpellEvent(filter=spells, actor=actor,
                           from_zone=Zone(_ZONES[zone], ControllerRef.ANY))
            for zone in where.split(" or ")
        ]
    return _carried([prohibit(event, **roles) for event in events], when)


def _build_cant_enter(m: re.Match[str]) -> SentenceOutcome:
    """<Creature|Nonland permanent> cards in graveyards [and libraries] can't enter the
    battlefield: a move onto the battlefield from each zone, the card judged where it is."""
    cards = (
        _CREATURE if m.group("what") == "Creature"
        else FAnd(children=(FAtom(pred=FAtomPred.IS_PERMANENT),
                            FNot(FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land"))))
    )
    zones = ["graveyards"] + (["libraries"] if m.group("lib") else [])
    return _carried(
        [
            prohibit(ZoneChangeEvent(from_zone=Zone(_ZONES[zone], ControllerRef.ANY),
                                     to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
                                     subject=cards))
            for zone in zones
        ],
        None,
    )


def _build_cant_gain(m: re.Match[str]) -> SentenceOutcome:
    """<Players|Your opponents> can't gain life [this turn]."""
    when = m.group("when")
    roles = {} if when is None else {"duration": _DURATIONS[when]}
    return _carried([prohibit(LifeGainedEvent(actor=_actor(m.group("who"))), **roles)], when)


def _build_cant_lose(m: re.Match[str]) -> SentenceOutcome:
    """You can't lose the game and your opponents can't win the game: two prohibitions."""
    return _carried(
        [prohibit(GameOutcomeEvent(won=False, actor=_actor("You"))),
         prohibit(GameOutcomeEvent(won=True, actor=_actor("Your opponents")))],
        None,
    )


def game_result(verb: Verb, who: object) -> Atom:
    """LOSE_GAME or WIN_GAME of ``who`` (the ``controller`` role, ability_tree.LOSERS)."""
    return Atom(verb=verb, args=AtomArgs(pairs=(("controller", who),)))


def _build_lose(m: re.Match[str]) -> SentenceOutcome:
    """You lose the game. / Target player|opponent loses the game."""
    who = {None: ControllerRef.YOU, "player": ControllerRef.TARGET_PLAYER,
           "opponent": ControllerRef.TARGET_OPPONENT}[m.group("target")]
    return EffectOutcome(effect=game_result(Verb.LOSE_GAME, who))


def _template(tid: str, name: str, pattern: str, build) -> Template:
    return Template(tid=tid, name=name, bucket=_BUCKET, pattern=re.compile(pattern),
                    priority=_PRIORITY, build=build)


_WHEN: Final[str] = r"(?P<when> this turn| until the end of your next turn)?"

TEMPLATES: Final[tuple[Template, ...]] = (
    _template("B21-opening-hand",
              "if this card is in your opening hand, you may begin the game with it on the "
              "battlefield",
              r"If this card is in your opening hand, you may begin the game with it on the "
              r"battlefield\.",
              _build_opening_hand),
    _template("B21-cast-limit", "each player can't cast more than one [noncreature] spell each turn",
              r"Each player can't cast more than one (?P<non>noncreature )?spell each turn\.",
              _build_cast_limit),
    _template("B21-cant-cast",
              "<who> can't cast [<types>] spells [from <zones>] [this turn|until the end of your "
              "next turn]",
              rf"(?P<who>Players|Your opponents|You) can't cast (?:{_SPELL_TYPES} )?spells"
              r"(?: from (?P<from>graveyards(?: or libraries)?|anywhere other than their hands))?"
              rf"{_WHEN}\.",
              _build_cant_cast),
    _template("B21-cant-enter",
              "<creature|nonland permanent> cards in graveyards [and libraries] can't enter the "
              "battlefield",
              r"(?P<what>Creature|Nonland permanent) cards in graveyards(?P<lib> and libraries)? "
              r"can't enter the battlefield\.",
              _build_cant_enter),
    _template("B21-cant-gain-life", "<players|your opponents> can't gain life [this turn]",
              rf"(?P<who>Players|Your opponents) can't gain life{_WHEN}\.", _build_cant_gain),
    # "You can't lose the game." alone is DOM Lich's Mastery's, whose three drawbacks (draw on
    # gain, exile on loss, lose when it leaves) do not compile: alone it would deal a card
    # stronger than printed in the partial pools. Its tree is this template's first atom; a
    # record maps it with the rest (BACKLOG, "Held back: an upside without its drawbacks").
    _template("B21-cant-lose",
              "you can't lose the game and your opponents can't win the game",
              r"You can't lose the game and your opponents can't win the game\.",
              _build_cant_lose),
    _template("B21-lose-game", "you lose the game | target player|opponent loses the game",
              r"(?:You lose|Target (?P<target>player|opponent) loses) the game\.", _build_lose),
    _template("B21-win-game", "you win the game", r"You win the game\.",
              lambda m: EffectOutcome(effect=game_result(Verb.WIN_GAME, ControllerRef.YOU))),
)
