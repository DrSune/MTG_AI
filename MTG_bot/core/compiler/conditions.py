"""Conditions: the "if <condition>" phrases that read what happened this turn, and one that reads
the game now (your life total), as Filters.

One grammar for every place a condition is printed: an intervening "if" in a trigger (frames.py,
CR 603.4), a trailing "if"/"unless" after an effect or a static ability, and "as long as" before or
after one (frames.py, templates_b14), and the relative clause of a target noun phrase
(templates_b11). ``PATTERN`` is the grammar as a regex and ``condition`` builds the Filter of a
phrase it matches, from the same table, so a template can never match a phrase it cannot encode.

The phrases that read the game now are the one comparison (``FAtomPred.QTY_GE``, ontology round
R12) of a measure of the game with a number; "N or less" is the same comparison negated at N + 1,
never a second form (CR 107.1: the numbers are integers):
- "you have N or more|less life" (Twinblade Paladin, Angel of Vitality): your life total (CR 119.1);
- your life total against your starting life total (CR 103.4, :func:`life_over_start`): "is greater
  than [or equal to]", "is less than", "is at least N greater than", "you have at least N life more
  than";
- "you control N or more <creatures|lands|artifacts|enchantments>", "you control a|another creature
  with power N or greater" (ferocious), "creatures you control have total power N or greater"
  (formidable): counts and a sum over the permanents you control;
- "there are N or more [creature|land|instant and/or sorcery] cards in your graveyard" (threshold,
  spell mastery), "you have N or more cards in hand": counts of your zones (divergence D28);
- "an opponent has N or more cards in their graveyard": the count of "your" graveyard read for
  each opponent in turn (``FAtom.who``), true when one of them has it.

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
    QAgg,
    QBin,
    QBinOp,
    QConst,
    QProp,
    QPropField,
    Quantity,
    QUnbounded,
    Zone,
    ZoneKind,
    at_least,
    at_most,
    number_in,
    number_you_control,
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
ABILITY_WORD: Final[str] = r"(?:(?:Raid|Morbid|Threshold|Ferocious|Formidable|Spell mastery) — )?"

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


#: Your life total now (CR 119.1) and your starting life total (CR 103.4: 20, 40 in Commander).
LIFE: Final[QProp] = QProp(referent="controller", field=QPropField.LIFE, agg=QAgg.FIRST)
STARTING_LIFE: Final[QProp] = QProp(
    referent="controller", field=QPropField.STARTING_LIFE, agg=QAgg.FIRST
)


def life_over_start(n: int) -> FAtom:
    """"Your life total is at least N greater than your starting life total" (and "you have at least
    N life more than your starting life total", Speaker of the Heavens): your life total is at least
    your starting life total plus N (ledger F11: never a predicate of its own, which would differ
    in Commander, where the start is 40)."""
    start: Quantity = STARTING_LIFE if n == 0 else QBin(QBinOp.ADD, STARTING_LIFE, QConst(n))
    return at_least(start, quantity=LIFE)


def _life_total(m: re.Match[str]) -> Filter:
    n = _number(m.group("lt_n"))
    if m.group("lt_dir") == "more":
        return at_least(n, quantity=LIFE)
    return at_most(n, quantity=LIFE)


def _life_against_start(m: re.Match[str]) -> Filter:
    if m.group("ls_less"):
        return FNot(life_over_start(0))
    if m.group("ls_ge"):
        return life_over_start(0)
    n = m.group("ls_n") or m.group("lm_n")
    return life_over_start(1 if n is None else _number(n))


def _type(name: str) -> FAtom:
    return FAtom(pred=FAtomPred.TYPE_EQ, string_value=name)


#: The cards a graveyard count reads: "cards", "creature cards", "instant and/or sorcery cards".
_CARD_KINDS: Final[dict[str, Filter | None]] = {
    "": None,
    "creature ": _type("Creature"),
    "land ": _type("Land"),
    "instant and/or sorcery ": FOr((_type("Instant"), _type("Sorcery"))),
}
_PERMANENTS: Final[dict[str, str]] = {
    "creatures": "Creature", "lands": "Land", "artifacts": "Artifact", "enchantments": "Enchantment",
}


def _graveyard_count(m: re.Match[str]) -> Filter:
    cards = number_in(Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU), _CARD_KINDS[m.group("gy_kind") or ""])
    return at_least(_number(m.group("gy_n")), quantity=cards)


def _opponent_graveyard_count(m: re.Match[str]) -> Filter:
    cards = number_in(Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU))
    return at_least(_number(m.group("og_n")), quantity=cards, who=ControllerRef.OPPONENT)


def _hand_count(m: re.Match[str]) -> Filter:
    return at_least(_number(m.group("hc_n")), quantity=number_in(Zone(ZoneKind.HAND, ControllerRef.YOU)))


def _you_control_count(m: re.Match[str]) -> Filter:
    permanents = number_you_control(_type(_PERMANENTS[m.group("cc_noun")]))
    return at_least(_number(m.group("cc_n")), quantity=permanents)


def _you_control_power(m: re.Match[str]) -> Filter:
    parts: list[Filter] = [_type("Creature"), at_least(_number(m.group("cp_n")), field=QPropField.POWER)]
    if m.group("cp_det") == "another":
        parts.append(FNot(FAtom(pred=FAtomPred.IS_SOURCE)))
    return at_least(1, quantity=number_you_control(FAnd(tuple(parts))))


def _total_power(m: re.Match[str]) -> Filter:
    yours = number_you_control(_type("Creature")).selector
    total = QProp(referent=yours, field=QPropField.POWER, agg=QAgg.SUM)
    return at_least(_number(m.group("tp_n")), quantity=total)


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
    (rf"you have (?P<lt_n>{_N}) or (?P<lt_dir>more|less) life", _life_total),
    ((r"your life total is (?:(?P<ls_less>less than)|greater than(?P<ls_ge> or equal to)?|at least "
      rf"(?P<ls_n>{_N}) greater than) your starting life total"
      rf"|you have at least (?P<lm_n>{_N}) life more than your starting life total"),
     _life_against_start),
    (rf"there are (?P<gy_n>{_N}) or more (?P<gy_kind>creature |land |instant and/or sorcery )?cards "
     r"in your graveyard", _graveyard_count),
    (rf"an opponent has (?P<og_n>{_N}) or more cards in their graveyard", _opponent_graveyard_count),
    (rf"you have (?P<hc_n>{_N}) or more cards in hand", _hand_count),
    (rf"you control (?P<cc_n>{_N}) or more (?P<cc_noun>creatures|lands|artifacts|enchantments)",
     _you_control_count),
    (rf"you control (?P<cp_det>a|another) creature with power (?P<cp_n>{_N}) or greater",
     _you_control_power),
    (rf"creatures you control have total power (?P<tp_n>{_N}) or greater", _total_power),
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
