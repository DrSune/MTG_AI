"""B19 bucket: playing cards from another zone (ontology round R13, DESIGN_ATOM_ONTOLOGY §17).

A permission to play cards from a zone is ``Verb.PERMIT`` (CR 601.3, 305.1): who may play is the
ability's controller; ``source`` names the cards and their zone; ``lands`` is "play" (lands too)
against "cast"; ``alternative`` / ``additional`` change the cost (CR 118.9, 601.2f); ``replace``
is the spell's rider; ``duration`` is how long a resolving ability's permission lasts (CR 611.2a).
A static ability's permission lasts while the static functions (CR 604.2, 611.3a) and names a
population of cards (an ALL selector over its zone).

Statics (an ``AbilityOutcome``):

* "You may cast <spells> from the top of your library." (Conspicuous Snoop's Goblin spells,
  Vizier of the Menagerie's and Garruk's Horde's creature spells, Mystic Forge's artifact and
  colorless spells, Precognition Field's instant and sorcery spells);
* "You may play lands from the top of your library | from your graveyard." (Crucible of Worlds,
  Ancient Greenwarden); Radha, Heart of Keld's sentence with "You may look at the top card of
  your library any time," before it (one static, one effect per clause, as a sentence's effects
  are), and the look alone (Mystic Forge, Vizier);
* "You may cast spells from your hand without paying their mana costs." (Omniscience);
* a card's own: "You may cast this card from your graveyard by paying N life and discarding a
  card in addition to paying its other costs." (Demonic Embrace), "You may cast this card from
  your graveyard or from exile." (Squee), and flashback (CR 702.34a): "Flashback <mana cost>" is
  the permission from the graveyard for that cost, with the exile rider "instead of putting it
  anywhere else any time it would leave the stack".

Resolving (an ``EffectOutcome``: the step of the ability printed above it, the duration required):

* "You may play that card this turn.", "Until end of turn, you may play cards exiled this way."
  and their kin (impulse draw: the ``result`` register, "play" so lands too), "Until the end of
  your next turn, you may play that card.", "You may play that card for as long as it remains
  exiled." (DurationPermanent: the permission ends with the object's stay there, CR 400.7),
  "You may cast them this turn." (spells only), "You may play them this turn without paying
  their mana costs." (Golos);
* "Until end of turn, you may cast spells from your hand without paying their mana costs."
  (Chandra, Flame's Catalyst [-8]; a population read whenever a card is cast, CR 611.2c);
* "You may cast target <card> from your graveyard this turn." (the frames give it its "{T}:"
  or loyalty cost: Zul Ashur, Jace, Vryn's Prodigy), "You may cast <spells> spells from your
  graveyard this turn." (Liliana, Untouched by Death);
* (templates_b3's Idol of Endurance, "Until end of turn, you may cast a creature spell from among
  cards exiled with this artifact without paying its mana cost.", builds with :func:`permit`:
  one play, ``count`` 1);
* "Target instant or sorcery card in your graveyard gains flashback until end of turn." with
  "The flashback cost is equal to that card's mana cost." (Sphinx of Forgotten Lore: the
  graveyard permission at the card's own cost, with flashback's rider, until end of turn).

The rider, a ``RiderOutcome``: "If that spell would be put into your graveyard, exile it
instead." and "If a spell cast this way would be put into your graveyard, exile it instead." are
the ``replace`` role of the cast verb before them (CAST: Chandra, Flame's Catalyst's [-2]; PERMIT:
Jace, Vryn's Prodigy's [-3]), compile_card's fold.

Not read, each waiting for a piece (BACKLOG, "The permission lane still blocked"): Furious Rise's
"until you exile another card with this enchantment" (an event-ended duration: the "end of your
next turn" approximation is stronger than printed in that end step, gate round 3), Muldrotha's
one of each permanent type, Lurrus's once each turn, Quilled Greatwurm's counters from among
creatures, Kethis's granted permission (CR 611.2c locks the cards a "gains" names), Etali's and
Tinybones's cards you don't own, Glimpse the Cosmos's condition and rider sentence.
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    Cost,
    CostDiscard,
    CostLife,
    Duration,
    DurationEot,
    DurationPermanent,
    DurationUntilEndOfNextTurn,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    QConst,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    Verb,
    Zone,
    ZoneKind,
    ZonePosition,
    spell_rider,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    RiderOutcome,
    RuleReminderOutcome,
    SentenceOutcome,
    Template,
)

_BUCKET: Final[str] = "B19"
_PRIORITY: Final[int] = 10

_TOP: Final[Zone] = Zone(ZoneKind.LIBRARY, ControllerRef.YOU, ZonePosition.TOP)
_GRAVEYARD: Final[Zone] = Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)
_EXILE: Final[Zone] = Zone(ZoneKind.EXILE, ControllerRef.YOU)
_HAND: Final[Zone] = Zone(ZoneKind.HAND, ControllerRef.YOU)


def _type(word: str) -> FAtom:
    return FAtom(pred=FAtomPred.TYPE_EQ, string_value=word)


def _kind(words: str) -> Filter | None:
    """The cards a printed noun phrase names, before "spells" or "card(s)", in the compiler's
    conventions: a card type ("creature"), "instant and|or sorcery" (either), a creature type
    ("Goblin": a tribal noun is the subtype and the creature type, MAPPER_GUIDE), a colour word
    before them ("red instant or sorcery"), "artifact spells and colorless" (Mystic Forge: either);
    None for any other phrase (the sentence is left unparsed)."""
    colors = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
    color = None
    head, _, rest = words.partition(" ")
    if head in colors and rest:
        color, words = colors[head], rest
    if words in ("instant and sorcery", "instant or sorcery"):
        kind: Filter = FOr(children=(_type("Instant"), _type("Sorcery")))
    elif words == "artifact spells and colorless":
        kind = FOr(
            children=(
                _type("Artifact"),
                FNot(inner=FAtom(pred=FAtomPred.COLOR_COUNT_GE, count=QConst(1))),
            )
        )
    elif words in ("artifact", "creature", "enchantment", "instant", "sorcery", "planeswalker"):
        kind = _type(words.capitalize())
    elif re.fullmatch(r"[A-Z][a-z]+(?: creature)?", words):
        kind = FAnd(
            children=(
                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value=words.split()[0]),
                _type("Creature"),
            )
        )
    else:
        return None
    if color is None:
        return kind
    return FAnd(children=(kind, FAtom(pred=FAtomPred.COLOR_HAS, color=color)))


def _all(filter_: Filter, *zones: Zone) -> Selector:
    """A population: every card of ``zones`` that passes ``filter_`` (a static's, or a resolving
    "spells from your hand" read whenever a card is played, CR 611.2c)."""
    return Selector(QUnbounded(), SelectorMode.ALL, filter_, zones=tuple(zones))


def _this_card(*zones: Zone) -> Selector:
    """"This card" in the zones it may be played from: a static functioning there (CR 113.6f)."""
    return _all(FAtom(pred=FAtomPred.IS_SOURCE), *zones)


def _result() -> Selector:
    """The ``result`` register (C2's referent, count QConst(1) by that convention, a referent
    being bound, never chosen): the cards the instruction before exiled or chose, "that card",
    "them", "cards exiled this way" alike."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAnd(children=()),
        zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
        referent="result",
    )


def permit(source: Selector, *, lands: bool = False, alternative: Cost | None = None,
           additional: Cost | None = None, duration: Duration | None = None,
           count: int | None = None, rider: bool = False) -> Atom:
    """A PERMIT atom; ``rider`` adds flashback's exile from the stack to anywhere."""
    pairs: list[tuple[str, object]] = [("source", source)]
    if lands:
        pairs.append(("lands", True))
    if alternative is not None:
        pairs.append(("alternative", alternative))
    if additional is not None:
        pairs.append(("additional", additional))
    if duration is not None:
        pairs.append(("duration", duration))
    if count is not None:
        pairs.append(("count", QConst(count)))
    if rider:
        pairs.append(("replace", spell_rider(Zone(ZoneKind.ANY, ControllerRef.ANY))))
    return Atom(verb=Verb.PERMIT, args=AtomArgs(pairs=tuple(pairs)))


def _static(atom: Atom) -> AbilityOutcome:
    return AbilityOutcome(ability=StaticAbility(effect=atom))


_LOOK: Final[Atom] = Atom(
    verb=Verb.LOOK_AT,
    args=AtomArgs(pairs=(("controller", ControllerRef.YOU), ("count", QConst(1)))),
)


# ---------------------------------------------------------------------------- statics


def _build_cast_spells_from_top(m: re.Match[str]) -> SentenceOutcome | None:
    """``You may cast <spells> spells from the top of your library.``: the permission is the
    static's (CR 611.3a), its cards every one of that kind on top. A land is never cast (CR
    305.9), so a land on top is not among them."""
    kind = _kind(m.group("what"))
    if kind is None:
        return None
    return _static(permit(_all(kind, _TOP)))


def _build_play_lands_from(m: re.Match[str]) -> SentenceOutcome:
    """``You may play lands from the top of your library | from your graveyard.``: a land played
    so is the turn's land play (CR 305.2a), at its timing (CR 305.1)."""
    zone = _GRAVEYARD if m.group("zone") == "your graveyard" else _TOP
    return _static(permit(_all(_type("Land"), zone), lands=True))


def _build_look_any_time(m: re.Match[str]) -> SentenceOutcome:
    """``You may look at the top card of your library any time.``: a disclosure static
    (layers' "disclosure" record, as Conspicuous Snoop's REVEAL)."""
    return _static(_LOOK)


def _build_look_and_play_lands_from_top(m: re.Match[str]) -> SentenceOutcome:
    """Radha, Heart of Keld's sentence: the look and the land permission, one static ability with
    one effect per clause, as every sentence of several effects compiles."""
    play = permit(_all(_type("Land"), _TOP), lands=True)
    return AbilityOutcome(ability=StaticAbility(effect=Seq(steps=(_LOOK, play))))


def _build_cast_from_hand_free(m: re.Match[str]) -> SentenceOutcome:
    """``You may cast spells from your hand without paying their mana costs.`` (Omniscience): an
    alternative cost for every spell in your hand (CR 118.9); the hand's own path stays."""
    return _static(permit(_all(FAnd(children=()), _HAND), alternative=Cost()))


def _build_cast_this_card_from_graveyard_recost(m: re.Match[str]) -> SentenceOutcome:
    """``You may cast this card from your graveyard by paying N life and discarding a card in
    addition to paying its other costs.`` (Demonic Embrace): the card's own static, functioning
    from its graveyard (CR 113.6f), its cost the mana cost plus the additional ones (CR 601.2f)."""
    extra = Cost(
        parts=(
            CostLife(amount=QConst(int(m.group("n")))),
            CostDiscard(
                target=Selector(QConst(1), SelectorMode.CHOOSE, FAnd(children=()), zones=(_HAND,))
            ),
        )
    )
    return _static(permit(_this_card(_GRAVEYARD), additional=extra))


def _build_cast_this_card_from_graveyard_or_exile(m: re.Match[str]) -> SentenceOutcome:
    """``You may cast this card from your graveyard or from exile.`` (Squee, the Immortal)."""
    return _static(permit(_this_card(_GRAVEYARD, _EXILE)))


def _build_flashback(m: re.Match[str]) -> SentenceOutcome | None:
    """``Flashback <mana cost>`` (CR 702.34a): "You may cast this card from your graveyard ... by
    paying [cost] rather than paying its mana cost" and "If the flashback cost was paid, exile
    this card instead of putting it anywhere else any time it would leave the stack": the
    permission from the graveyard with that alternative cost, and the rider of a spell cast
    through it (the replacement of its move off the stack to anywhere)."""
    from MTG_bot.core.compiler.compiler import parse_mana_cost

    cost = parse_mana_cost(m.group("cost"))
    if cost is None:
        return None
    return _static(permit(_this_card(_GRAVEYARD), alternative=cost, rider=True))


# ---------------------------------------------------------------------------- resolving

#: "this turn" / "until end of turn" (CR 514.2), "until the end of your next turn", "for as long
#: as it remains exiled" (the object's stay, CR 400.7).
_EOT: Final[Duration] = DurationEot()
_NEXT: Final[Duration] = DurationUntilEndOfNextTurn()

_OBJECTS: Final[str] = r"that card|those cards|them|it|cards exiled this way"


def _build_cast_from_hand_free_eot(m: re.Match[str]) -> SentenceOutcome:
    """``Until end of turn, you may cast spells from your hand without paying their mana costs.``
    (Chandra, Flame's Catalyst [-8]): the rules change for the rest of the turn, so a card that
    reaches your hand later is covered too (CR 611.2c)."""
    return EffectOutcome(
        effect=permit(_all(FAnd(children=()), _HAND), alternative=Cost(), duration=_EOT)
    )


def _build_cast_target_from_graveyard(m: re.Match[str]) -> SentenceOutcome | None:
    """``You may cast|play target <card> from your graveyard this turn.`` (Zul Ashur, Jace, Vryn's
    Prodigy; their cost comes from the frame): the designated card, at its own cost and timing,
    until end of turn."""
    kind = _kind(m.group("what"))
    if kind is None:
        return None
    target = Selector(QConst(1), SelectorMode.TARGET, kind, zones=(_GRAVEYARD,))
    return EffectOutcome(
        effect=permit(target, lands=m.group("verb") == "play", duration=_EOT)
    )


def _build_cast_spells_from_graveyard_eot(m: re.Match[str]) -> SentenceOutcome | None:
    """``You may cast <spells> spells from your graveyard this turn.`` (Liliana, Untouched by
    Death [-3]): a rules change for the turn, read whenever a card is cast (CR 611.2c)."""
    kind = _kind(m.group("what"))
    if kind is None:
        return None
    return EffectOutcome(effect=permit(_all(kind, _GRAVEYARD), duration=_EOT))


def _build_gains_flashback(m: re.Match[str]) -> SentenceOutcome:
    """``Target instant or sorcery card in your graveyard gains flashback until end of turn.``
    (Sphinx of Forgotten Lore, with "The flashback cost is equal to that card's mana cost."): the
    card may be cast from the graveyard until end of turn for its mana cost (no alternative), and
    a spell cast so has flashback's rider (CR 702.34a)."""
    target = Selector(QConst(1), SelectorMode.TARGET, _kind("instant or sorcery"), zones=(_GRAVEYARD,))
    return EffectOutcome(effect=permit(target, duration=_EOT, rider=True))


def _build_spell_rider(m: re.Match[str]) -> SentenceOutcome:
    """``If that spell | a spell cast this way would be put into your graveyard, exile it
    instead.``: the rider of the cast verb before it (compile_card folds it into that verb's
    ``replace`` role)."""
    return RiderOutcome(rider=spell_rider(_GRAVEYARD))


def _template(tid: str, name: str, pattern: str, build) -> Template:
    return Template(tid=tid, name=name, bucket=_BUCKET, pattern=re.compile(pattern),
                    priority=_PRIORITY, build=build)


_PLAY_RESULT_RE: Final[str] = (
    rf"(?:Until end of turn, you may (?P<verb>play|cast) (?P<obj>{_OBJECTS})"
    rf"|You may (?P<verb2>play|cast) (?P<obj2>{_OBJECTS})(?P<window2> this turn| until the end of "
    r"your next turn| for as long as it remains exiled)(?P<free2> without paying their mana costs)?"
    rf"|Until the end of your next turn, you may play (?P<obj3>that card|those cards))\."
)


def _build_play_result(m: re.Match[str]) -> SentenceOutcome:
    """Impulse draw, in the three word orders of :data:`_PLAY_RESULT_RE`: "[Until end of turn, ]you
    may play|cast <them>[ this turn]", "until the end of your next turn" and "for as long as it
    remains exiled" (the object's stay, CR 400.7): the cards the instruction before named (the
    ``result`` register), "play" lands too, "without paying their mana costs" free (Golos)."""
    if m.group("obj") is not None:
        verb, window, free = m.group("verb"), "", None
    elif m.group("obj2") is not None:
        verb, window, free = m.group("verb2"), m.group("window2"), m.group("free2")
    else:
        verb, window, free = "play", " until the end of your next turn", None
    duration: Duration = (
        _NEXT if "next turn" in window
        else DurationPermanent() if "remains exiled" in window
        else _EOT
    )
    alternative = Cost() if free else None
    return EffectOutcome(
        effect=permit(_result(), lands=verb == "play", alternative=alternative,
                      duration=duration)
    )


TEMPLATES: Final[tuple[Template, ...]] = (
    _template("B19-cast-spells-from-top", "you may cast <spells> spells from the top of your library",
              r"You may cast (?P<what>.+?) spells from the top of your library\.",
              _build_cast_spells_from_top),
    _template("B19-play-lands-from", "you may play lands from the top of your library | your graveyard",
              r"You may play lands from (?P<zone>the top of your library|your graveyard)\.",
              _build_play_lands_from),
    _template("B19-look-any-time", "you may look at the top card of your library any time",
              r"You may look at the top card of your library any time\.",
              _build_look_any_time),
    _template("B19-look-and-play-lands-from-top",
              "you may look at the top card ... any time, and you may play lands from the top",
              r"You may look at the top card of your library any time, and you may play lands "
              r"from the top of your library\.",
              _build_look_and_play_lands_from_top),
    _template("B19-cast-from-hand-free", "you may cast spells from your hand without paying",
              r"You may cast spells from your hand without paying their mana costs\.",
              _build_cast_from_hand_free),
    _template("B19-cast-this-from-graveyard-recost",
              "you may cast this card from your graveyard by paying N life and discarding a card",
              r"You may cast this card from your graveyard by paying (?P<n>\d+) life and "
              r"discarding a card in addition to paying its other costs\.",
              _build_cast_this_card_from_graveyard_recost),
    _template("B19-cast-this-from-graveyard-or-exile",
              "you may cast this card from your graveyard or from exile",
              r"You may cast this card from your graveyard or from exile\.",
              _build_cast_this_card_from_graveyard_or_exile),
    _template("B19-flashback", "Flashback <mana cost> (reminder)",
              r"Flashback (?P<cost>(?:\{[^}]+\})+)(?: \(You may cast this card from your graveyard "
              r"for its flashback cost\. Then exile it\.\))?",
              _build_flashback),
    _template("B19-play-result", "impulse: you may play|cast that card|them <window>",
              _PLAY_RESULT_RE, _build_play_result),
    _template("B19-cast-from-hand-free-eot",
              "until end of turn, you may cast spells from your hand without paying",
              r"Until end of turn, you may cast spells from your hand without paying their mana "
              r"costs\.",
              _build_cast_from_hand_free_eot),
    _template("B19-cast-target-from-graveyard-eot",
              "you may cast|play target <card> from your graveyard this turn",
              r"You may (?P<verb>cast|play) target (?P<what>.+?) card from your graveyard this "
              r"turn\.",
              _build_cast_target_from_graveyard),
    _template("B19-cast-spells-from-graveyard-eot",
              "you may cast <spells> spells from your graveyard this turn",
              r"You may cast (?P<what>.+?) spells from your graveyard this turn\.",
              _build_cast_spells_from_graveyard_eot),
    _template("B19-gains-flashback-eot",
              "target instant or sorcery card in your graveyard gains flashback until end of turn",
              r"Target instant or sorcery card in your graveyard gains flashback until end of "
              r"turn\.",
              _build_gains_flashback),
    _template("B19-flashback-cost-is-mana-cost", "the flashback cost is that card's mana cost",
              r"The flashback cost is equal to that card's mana cost\.",
              lambda m: RuleReminderOutcome(reason="flashback_cost")),
    _template("B19-spell-rider", "if that spell would be put into your graveyard, exile it instead",
              r"If (?:that spell|a spell cast this way) would be put into your graveyard, exile it "
              r"instead\.",
              _build_spell_rider),
)
