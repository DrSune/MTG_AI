"""B14 bucket: "can't be countered" and the statics that read the turn's history.

"Can't be countered" (CR 701.6a, 101.2) is a PREVENT_EFFECT over ``CounteredEvent``, the shape
every other "can't" in the IR has ("This creature can't block.": condition and event filter name
the same object). The engine consults it when a counterspell resolves; the counterspell may still
target the spell. Three carriers:

* "This spell can't be countered." — the spell's own static ability; it functions on the stack
  (CR 113.6g).
* "<Type> [and <type>] spells [you control] can't be countered." — a permanent's static (Gaea's
  Herald, Destiny Spinner, Sphinx of the Final Word).
* "Spells you control can't be countered this turn." — a one-shot effect lasting the turn (Veil of
  Summer); it covers spells cast after it resolved (CR 611.2c).

The statics with a condition of conditions.py: bloodthirst (CR 702.54a, whose reminder text is
the ability), "can't attack unless", "can't be blocked if", "enters with a +1/+1 counter on it
if", and "this creature gets +P/+T [and has <keywords>]" or "has <keywords>" as long as the
condition holds, the condition first or last (Twinblade Paladin, Angel of Vitality, Serra
Ascendant). Each is the existing carrier with the condition put in its condition slot: Gadrak's
"can't attack unless" (StaticAbility.condition = FNot of the condition), Tome Anima's "can't be
blocked as long as", the kicker Baloth's gated EtBState, Thieves' Guild Enforcer's self static
(MODIFY_PT, then GRANT_ABILITY per keyword, the keywords sorted: one static's effects share a
timestamp, CR 613.7, so their printed order means nothing).

Priority 10, as B11: no other template matches these sentences.
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    CounteredEvent,
    CounterKind,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    DurationEot,
    Effect,
    EtBState,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    KeywordAbility,
    PtDelta,
    PtDirection,
    QConst,
    Seq,
    StaticAbility,
    Verb,
)
from MTG_bot.core.compiler import conditions
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    SentenceOutcome,
    Template,
)
from MTG_bot.core.compiler.templates_b6 import _self_selector
from MTG_bot.core.compiler.templates_b11 import _KW_LIST_RE, _keyword_list

_BUCKET: Final[str] = "B14"
_PRIORITY: Final[int] = 10

_SPELL_TYPES: Final[tuple[str, ...]] = (
    "Artifact", "Creature", "Enchantment", "Instant", "Planeswalker", "Sorcery"
)
#: "Creature and enchantment spells": the first type opens the sentence, the second does not.
_TYPES_RE: Final[str] = (
    rf"(?P<t1>{'|'.join(_SPELL_TYPES)})(?: and (?P<t2>{'|'.join(t.lower() for t in _SPELL_TYPES)}))?"
)
_COUNTERS: Final[dict[str, int]] = {"a": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
_COND: Final[str] = rf"(?P<cond>{conditions.PATTERN})"

_IS_SOURCE: Final[FAtom] = FAtom(pred=FAtomPred.IS_SOURCE)


def _cant_be_countered(subject: Filter, **roles: object) -> Atom:
    pairs = (("condition", subject), ("event", CounteredEvent(filter=subject)), *roles.items())
    return Atom(verb=Verb.PREVENT_EFFECT, args=AtomArgs(pairs=pairs))


def _spells(m: re.Match[str], yours: bool) -> Filter:
    """Spells of the matched type(s) ("creature and enchantment spells" are both kinds),
    optionally only the ones you control."""
    parts: list[Filter] = [FAtom(pred=FAtomPred.STACK_KIND_EQ, string_value="SPELL")]
    t1, t2 = m.group("t1"), m.group("t2")
    if t1:
        types = [FAtom(pred=FAtomPred.TYPE_EQ, string_value=t.capitalize()) for t in (t1, t2) if t]
        parts.append(types[0] if len(types) == 1 else FOr(tuple(types)))
    if yours:
        parts.append(FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU))
    return FAnd(tuple(parts))


def _condition(m: re.Match[str]) -> Filter:
    found = conditions.condition(m.group("cond"))
    assert found is not None  # the pattern is the grammar
    return found


def _build_this_spell(m: re.Match[str]) -> SentenceOutcome:
    """This spell can't be countered."""
    return AbilityOutcome(ability=StaticAbility(effect=_cant_be_countered(_IS_SOURCE)))


def _build_spells_static(m: re.Match[str]) -> SentenceOutcome:
    """<Type> [and <type>] spells [you control] can't be countered."""
    return AbilityOutcome(
        ability=StaticAbility(effect=_cant_be_countered(_spells(m, bool(m.group("yours")))))
    )


def _build_spells_this_turn(m: re.Match[str]) -> SentenceOutcome:
    """[<Type> [and <type>]] spells you control can't be countered this turn."""
    return EffectOutcome(effect=_cant_be_countered(_spells(m, True), duration=DurationEot()))


def _build_bloodthirst(m: re.Match[str]) -> SentenceOutcome:
    """Bloodthirst N (If an opponent was dealt damage this turn, this creature enters with N
    +1/+1 counters on it.) — CR 702.54a: the reminder text is the ability."""
    n = int(m.group("n"))
    if _COUNTERS[m.group("word")] != n:
        raise ValueError(f"B14: bloodthirst {n} reminder names {m.group('word')!r} counters")
    condition = conditions.condition("an opponent was dealt damage this turn")
    return AbilityOutcome(
        ability=EtBState(
            initial_counters=((CounterKind.PLUS_1_PLUS_1, QConst(n)),), condition=condition
        )
    )


def _build_cant_attack_unless(m: re.Match[str]) -> SentenceOutcome:
    """This creature can't attack unless <condition>. (Gadrak's carrier.)"""
    atom = Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(("condition", _IS_SOURCE), ("event", DeclareAttackersEvent(filter=_IS_SOURCE)))
        ),
    )
    return AbilityOutcome(ability=StaticAbility(effect=atom, condition=FNot(_condition(m))))


def _build_cant_be_blocked_if(m: re.Match[str]) -> SentenceOutcome:
    """This creature can't be blocked if <condition>. (Tome Anima's carrier.)"""
    atom = Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                ("condition", _IS_SOURCE),
                ("event", DeclareBlockersEvent(FAnd(()), blocked=_IS_SOURCE)),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(effect=atom, condition=_condition(m)))


def _build_enters_with_counters_if(m: re.Match[str]) -> SentenceOutcome:
    """This creature enters with N +1/+1 counter(s) on it if <condition>. (CR 614.1c)"""
    n = _COUNTERS[m.group("word")]
    return AbilityOutcome(
        ability=EtBState(
            initial_counters=((CounterKind.PLUS_1_PLUS_1, QConst(n)),), condition=_condition(m)
        )
    )


#: "gets +P/+T [and has <keywords>]" | "has <keywords>": what a self static gives this creature.
_SELF_STATIC: Final[str] = (
    rf"(?:gets \+(?P<p>\d+)/\+(?P<t>\d+)(?: and has {_KW_LIST_RE})?"
    rf"|has {_KW_LIST_RE.replace('?P<kws>', '?P<kws_only>')})"
)


def _build_self_static_as_long_as(m: re.Match[str]) -> SentenceOutcome:
    """As long as <condition>, this creature gets +P/+T [and has <keywords>] / has <keywords>,
    the condition first or last: one tree for both wordings. "As long as" is the static's
    condition, never a duration; the effect is Thieves' Guild Enforcer's (MODIFY_PT, then a
    GRANT_ABILITY per keyword, on this creature), the keywords sorted by name."""
    steps: list[Effect] = []
    if m.group("p"):
        steps.append(
            Atom(
                verb=Verb.MODIFY_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", _self_selector()),
                        ("power", PtDelta(PtDirection.INCREASE, QConst(int(m.group("p"))))),
                        ("toughness", PtDelta(PtDirection.INCREASE, QConst(int(m.group("t"))))),
                    )
                ),
            )
        )
    keywords = m.group("kws") or m.group("kws_only")
    # One static's effects share a timestamp (CR 613.7), so the printed keyword order means
    # nothing: the grants are sorted, one tree for "flying and lifelink" and "lifelink and flying".
    for keyword in sorted(_keyword_list(keywords) if keywords else (), key=lambda k: k.name):
        steps.append(
            Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("target", _self_selector()),
                        ("ability", KeywordAbility(keyword=keyword)),
                    )
                ),
            )
        )
    effect = steps[0] if len(steps) == 1 else Seq(steps=tuple(steps))
    return AbilityOutcome(ability=StaticAbility(effect=effect, condition=_condition(m)))


def _t(tid: str, name: str, pattern: str, build) -> Template:
    return Template(
        tid=tid, name=name, bucket=_BUCKET, pattern=re.compile(pattern), priority=_PRIORITY,
        build=build,
    )


TEMPLATES: tuple[Template, ...] = (
    _t("B14-this-spell-cant-be-countered", "this spell can't be countered",
       r"^This spell can't be countered\.$", _build_this_spell),
    _t("B14-spells-cant-be-countered", "<type> [and <type>] spells [you control] can't be countered",
       rf"^{_TYPES_RE} spells(?P<yours> you control)? can't be countered\.$",
       _build_spells_static),
    _t("B14-spells-cant-be-countered-this-turn",
       "[<type> [and <type>]] spells you control can't be countered this turn",
       rf"^(?:{_TYPES_RE} spells|Spells) you control can't be countered this turn\.$",
       _build_spells_this_turn),
    _t("B14-bloodthirst", "bloodthirst N (reminder)",
       r"^Bloodthirst (?P<n>\d+) \(If an opponent was dealt damage this turn, this creature enters "
       rf"with (?P<word>{'|'.join(_COUNTERS)}) \+1/\+1 counters? on it\.\)$",
       _build_bloodthirst),
    _t("B14-cant-attack-unless", "this creature can't attack unless <turn-history condition>",
       rf"^This creature can't attack unless {_COND}\.$", _build_cant_attack_unless),
    _t("B14-cant-be-blocked-if", "this creature can't be blocked if <turn-history condition>",
       rf"^This creature can't be blocked if {_COND}\.$", _build_cant_be_blocked_if),
    _t("B14-enters-with-counters-if",
       "this creature enters with N +1/+1 counter(s) on it if <turn-history condition>",
       rf"^{conditions.ABILITY_WORD}This creature enters with (?P<word>{'|'.join(_COUNTERS)}) "
       rf"\+1/\+1 counters? on it if {_COND}\.$",
       _build_enters_with_counters_if),
    _t("B14-as-long-as-self", "as long as <condition>, this creature gets +P/+T or has <keywords>",
       rf"^As long as {_COND}, this creature {_SELF_STATIC}\.$", _build_self_static_as_long_as),
    _t("B14-self-as-long-as", "this creature gets +P/+T or has <keywords> as long as <condition>",
       rf"^This creature {_SELF_STATIC} as long as {_COND}\.$", _build_self_static_as_long_as),
)
