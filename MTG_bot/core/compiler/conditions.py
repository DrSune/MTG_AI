"""Turn-history conditions: the "if <condition>" phrases that read what happened this turn, as
Filters.

One grammar for every place a condition is printed: an intervening "if" in a trigger (frames.py,
CR 603.4), a trailing "if"/"unless" after an effect or a static ability (frames.py, templates_b14),
and the relative clause of a target noun phrase (templates_b11). ``PATTERN`` is the grammar as a
regex and ``condition`` builds the Filter of a phrase it matches, from the same table, so a
template can never match a phrase it cannot encode.

Most phrases read the one turn-history atom, ``FAtomPred.EVENT_THIS_TURN`` over an EventSpec:
- "<you|an opponent|a player> lost [N or more] life this turn" (Savage Gorger, Knight of the Ebon
  Legion): LifeLostEvent, one player's total (CR 120.3a: damage to a player is life lost);
- "<you|an opponent> [have|has|didn't] cast a [<colour> [or <colour>]|historic] spell this turn"
  (Nightpack Ambusher, Veil of Summer, Relic Runner; historic is CR 700.6);
- "<you|an opponent> attacked this turn" (raid): only the active player attacks (CR 508.1), so it
  is "<their> turn, and attackers were declared this turn";
- "an opponent was|has been dealt damage this turn" (bloodthirst, CR 702.54a).
Three shapes keep the dedicated atoms their M21 templates use (the frames differential checks they
agree): "a creature died this turn" (DIED_THIS_TURN), "you['ve] gained [N or more] life this turn"
(LIFE_GAINED_THIS_TURN_GE), "you've cast an instant or sorcery spell this turn"
(INSTANT_OR_SORCERY_CAST_THIS_TURN).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Final

from MTG_bot.core.ability_tree import (
    CastSpellEvent,
    ControllerRef,
    DamageDealtEvent,
    DeclareAttackersEvent,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    LifeLostEvent,
    QConst,
    QUnbounded,
)

_NUMBERS: Final[dict[str, int]] = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_N: Final[str] = r"(?:\d+|" + "|".join(_NUMBERS) + ")"
_COLORS: Final[dict[str, str]] = {
    "white": "W", "blue": "U", "black": "B", "red": "R", "green": "G",
}
_COLOR: Final[str] = "(?:" + "|".join(_COLORS) + ")"
_WHO: Final[dict[str, ControllerRef]] = {"you": ControllerRef.YOU, "an opponent": ControllerRef.OPPONENT}

#: Ability words that open a condition-bearing ability in the corpus. CR 207.2c: an ability word
#: has no rules meaning, so it is dropped.
ABILITY_WORD: Final[str] = r"(?:(?:Raid|Morbid) — )?"

#: "creature that was dealt damage this turn": the judged object was dealt damage, any amount,
#: from any source, combat or not, as the object it is now (CR 400.7).
WAS_DEALT_DAMAGE_THIS_TURN: Final[FAtom] = FAtom(
    pred=FAtomPred.SUBJECT_OF_EVENT_THIS_TURN,
    event=DamageDealtEvent(amount=QUnbounded(), filter=FAnd(())),
    count=QConst(1),
)


def _number(word: str | None) -> int:
    if word is None:
        return 1
    return int(word) if word.isdigit() else _NUMBERS[word]


def _happened(event, count: int = 1) -> FAtom:
    return FAtom(pred=FAtomPred.EVENT_THIS_TURN, event=event, count=QConst(count))


def _player(who: str) -> FAtom:
    return FAtom(pred=FAtomPred.CONTROLLER_IS, who=_WHO[who])


def _life_lost(m: re.Match[str]) -> Filter:
    who = m.group("ll_who")
    actor = None if who == "a player" else _player(who)
    return _happened(LifeLostEvent(actor=actor), _number(m.group("ll_n")))


def _spell_filter(desc: str) -> Filter:
    if not desc:
        return FAnd(())
    if desc == "historic":  # CR 700.6
        return FOr(
            (
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Artifact"),
                FAtom(pred=FAtomPred.SUPERTYPE_EQ, string_value="Legendary"),
                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Saga"),
            )
        )
    colors = [FAtom(pred=FAtomPred.COLOR_HAS, color=_COLORS[w]) for w in desc.split(" or ")]
    return colors[0] if len(colors) == 1 else FOr(tuple(colors))


def _cast(m: re.Match[str]) -> Filter:
    who, desc = m.group("c_who"), m.group("c_desc")
    if desc == "instant or sorcery":  # Stormwing Entity's atom
        cast: Filter = FAtom(pred=FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN, who=_WHO[who])
    else:
        cast = _happened(CastSpellEvent(filter=_spell_filter(desc or ""), actor=_player(who)))
    return FNot(cast) if m.group("c_verb") == " didn't cast" else cast


def _attacked(m: re.Match[str]) -> Filter:
    return FAnd(
        (
            FAtom(pred=FAtomPred.TURN_OF, who=_WHO[m.group("a_who")]),
            _happened(DeclareAttackersEvent(filter=FAnd(()))),
        )
    )


def _opponent_dealt_damage(m: re.Match[str]) -> Filter:
    return _happened(
        DamageDealtEvent(
            amount=QUnbounded(), filter=FAtom(pred=FAtomPred.OPPONENT_OF, who=ControllerRef.YOU)
        )
    )


def _creature_died(m: re.Match[str]) -> Filter:
    return FAtom(pred=FAtomPred.DIED_THIS_TURN)


def _life_gained(m: re.Match[str]) -> Filter:
    return FAtom(
        pred=FAtomPred.LIFE_GAINED_THIS_TURN_GE,
        count=QConst(_number(m.group("lg_n"))),
        who=ControllerRef.YOU,
    )


#: (phrase, builder). Group names are unique across the table, so PATTERN can join them.
_PHRASES: Final[tuple[tuple[str, Callable[[re.Match[str]], Filter]], ...]] = (
    (rf"(?P<ll_who>you|an opponent|a player) lost (?:(?P<ll_n>{_N}) or more )?life this turn",
     _life_lost),
    ((r"(?P<c_who>you|an opponent)(?P<c_verb>'ve cast| have cast| has cast| cast| didn't cast) an? "
      rf"(?:(?P<c_desc>instant or sorcery|historic|{_COLOR}(?: or {_COLOR})?) )?spell this turn"),
     _cast),
    (r"(?P<a_who>you|an opponent) attacked this turn", _attacked),
    (r"an opponent (?:was|has been) dealt damage this turn", _opponent_dealt_damage),
    (r"a creature died this turn", _creature_died),
    (rf"you(?:'ve)? gained (?:(?P<lg_n>{_N}) or more )?life this turn", _life_gained),
)
_COMPILED: Final = tuple((re.compile(p), build) for p, build in _PHRASES)

#: The grammar as one regex (no group of its own), to embed in a template's pattern.
PATTERN: Final[str] = "(?:" + "|".join(p for p, _ in _PHRASES) + ")"


def condition(text: str) -> Filter | None:
    """The Filter of a condition phrase (the words after "if" or "unless"), or None when the
    phrase is not in this grammar."""
    for regex, build in _COMPILED:
        m = regex.fullmatch(text)
        if m is not None:
            return build(m)
    return None
