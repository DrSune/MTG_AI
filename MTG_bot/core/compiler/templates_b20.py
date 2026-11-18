"""B20 bucket: copies (DESIGN_ATOM_ONTOLOGY §18, CR 707).

"A copy of <object>" is the ``CopyOf`` value: the object, and the copy effect's exceptions, which
become part of the copy's copiable values (CR 707.9a-b). Where the copy goes is the verb's:

* "Create a token that's a copy of <object>[, except <exceptions>]." is ``CREATE_TOKEN`` with the
  CopyOf as its ``tokens`` (CR 707.5): the object is "target <noun phrase>" (B11's grammar, with
  "another" and "target permanent") or "this creature"; "it" is a record's (it reads the
  ``result`` register, which only an earlier move or token writes). The exceptions printed in the 19 sets that
  the value carries: "it's a <Subtype> in addition to its other types", "it has haste and "At the
  beginning of the end step, sacrifice this token."" (Electroduplicate, Chandra, Flameshaper).
  As a clause it takes any trigger frame (frames.py: Extravagant Replication's upkeep, Homunculus
  Horde's second card drawn).
* "Copy target instant or sorcery spell[ you control]." is ``COPY`` with no ``cards`` (CR
  707.10): a copy put onto the stack (Twincast, Reverberate), its target the counterspells'
  ``target_spell`` selector.
* "Whenever you cast an instant or sorcery spell, copy it for each other instant and sorcery spell
  you've cast before it this turn." (Thousand-Year Storm): COPY of the cast spell, ``count`` its
  ordinal among them less one (QProp ORDINAL). Double Vision's "copy that spell" is B2b's.
* "You may choose new targets for the copy|copies." (CR 707.10c) is no ability: the compiler folds
  it into the ``new_targets`` role of the one COPY printed before it (``NewTargetsOutcome``).

Not read, each waiting for its piece: "becomes a copy of" with another duration or a static (Oko,
Saheeli, Valki, Metamorphic Alteration), "enter as a copy" (the Clones), the exceptions "isn't
legendary", "it's 1/1", "enters with an additional counter" and an artifact type added (Helm of the
Host, Jace, Nightmare Shepherd, Littjara Mirrorlake, Saheeli), copies of a triggered ability or a
permanent spell (Lithoform Engine, Strionic Resonator), a delayed "when you next cast" (Teach by
Example, Repeated Reverberation: delayed triggers that remember their spell), a card copy cast
(Chandra, Pyromaster, Elite Arcanist, Spelltwine).
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CastSpellEvent,
    ControllerRef,
    CopyOf,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    Phase,
    QBin,
    QBinOp,
    QConst,
    QProp,
    QPropField,
    Selector,
    SelectorMode,
    TriggeredAbility,
    TurnPhaseEvent,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    NewTargetsOutcome,
    SentenceOutcome,
    Template,
)
from MTG_bot.core.compiler.templates_b5a import target_spell
from MTG_bot.core.compiler.templates_b11 import _KEYWORDS, _NP_RE, _np_filter

_BUCKET: Final[str] = "B20"
_PRIORITY: Final[int] = 10

_BATTLEFIELD: Final[Zone] = Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY)
_YOU: Final[FAtom] = FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
_INSTANT_OR_SORCERY: Final[FOr] = FOr(
    children=(
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Instant"),
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Sorcery"),
    )
)


def _referent(name: str) -> Selector:
    """A bound object (C2's referent convention): "it", "that spell"."""
    return Selector(
        QConst(1), SelectorMode.CHOOSE, FAnd(children=()),
        zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),), referent=name,
    )


def that_spell() -> CopyOf:
    """"That spell", "it": a cast trigger's spell (the event register)."""
    return CopyOf(_referent("event"))


def copy_token(copy: CopyOf) -> Atom:
    """"Create a token that's a copy of ..." (CR 707.5)."""
    return Atom(verb=Verb.CREATE_TOKEN, args=AtomArgs(pairs=(("tokens", copy), ("count", QConst(1)))))


def copy_spell(copy: CopyOf, count: object = None) -> Atom:
    """A COPY put onto the stack (CR 707.10), ``count`` copies (absent: one)."""
    pairs: list[tuple[str, object]] = [("source", copy)]
    if count is not None:
        pairs.append(("count", count))
    return Atom(verb=Verb.COPY, args=AtomArgs(pairs=tuple(pairs)))


#: The ability "At the beginning of the end step, sacrifice this token." (each end step: no actor,
#: MAPPER_GUIDE), which a copy gains (Electroduplicate).
_SACRIFICE_AT_END = TriggeredAbility(
    event=TurnPhaseEvent(phase=Phase.END_TURN),
    condition=None,
    effect=Atom(
        verb=Verb.SACRIFICE,
        args=AtomArgs(pairs=(("target", Selector(
            QConst(1), SelectorMode.CHOOSE, FAtom(pred=FAtomPred.IS_SOURCE), zones=(_BATTLEFIELD,)
        )),)),
    ),
)
#: The sentence's end: the exceptions printed in the 19 sets, or none. A quoted ability ends the
#: sentence with its own period inside the quote.
_END_RE: Final[str] = (
    r"(?:, except it's an? (?P<sub>[A-Z][a-z]+) in addition to its other types\."
    r"|, except it has (?P<kw>haste)(?:\.|(?P<sac> and \"At the beginning of the end step, "
    r"sacrifice this token\.\"))"
    r"|\.)"
)
#: Not "it": a sentence alone cannot tell whether the instruction before it moved or made the
#: object (a first sentence, or after "Destroy target creature.", which writes no register, made
#: no token: gate round B3, M3a). Abyssal Harvester's "it" is its record's.
_OBJECT_RE: Final[str] = (
    rf"(?P<obj>this creature|target permanent|(?P<another>another )?{_NP_RE})"
)
_COPY_TOKEN_RE: Final[str] = rf"Create a token that's a copy of {_OBJECT_RE}{_END_RE}"


def _copied(m: re.Match[str]) -> CopyOf:
    obj = m.group("obj")
    if obj == "this creature":
        source = Selector(
            QConst(1), SelectorMode.CHOOSE, FAtom(pred=FAtomPred.IS_SOURCE), zones=(_BATTLEFIELD,)
        )
    else:
        filter_ = (
            FAtom(pred=FAtomPred.IS_PERMANENT) if obj == "target permanent" else _np_filter(m)
        )
        if m.group("another"):
            filter_ = FAnd(children=(filter_, FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE))))
        source = Selector(QConst(1), SelectorMode.TARGET, filter_, zones=(_BATTLEFIELD,))
    return CopyOf(
        source,
        subtypes=(m.group("sub"),) if m.group("sub") else (),
        keywords=(_KEYWORDS[m.group("kw")],) if m.group("kw") else (),
        abilities=(_SACRIFICE_AT_END,) if m.group("sac") else (),
    )


def _build_copy_token(m: re.Match[str]) -> SentenceOutcome:
    return EffectOutcome(effect=copy_token(_copied(m)))


def copy_token_sentence(sentence: str) -> SentenceOutcome:
    """The tree of a "Create a token that's a copy of ..." sentence (Sublime Epiphany's bullet
    reads its mode through it, one form)."""
    m = re.fullmatch(_COPY_TOKEN_RE, sentence)
    assert m is not None, sentence
    return _build_copy_token(m)


def _build_copy_target_spell(m: re.Match[str]) -> SentenceOutcome:
    # "target instant or sorcery spell" is the counterspells' one selector (templates_b5a's
    # target_spell: STACK_KIND_EQ SPELL beside the types, Miscast's bytes): one encoding.
    filter_ = FAnd(children=(_INSTANT_OR_SORCERY, _YOU)) if m.group("you") else _INSTANT_OR_SORCERY
    return EffectOutcome(effect=copy_spell(CopyOf(target_spell(filter_))))


def _build_storm_copies(m: re.Match[str]) -> SentenceOutcome:
    """Thousand-Year Storm: the cast's ordinal among your instant and sorcery spells this turn,
    less one, is the number of them cast before it."""
    count = QBin(QBinOp.SUB, QProp("event", QPropField.ORDINAL), QConst(1))
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=CastSpellEvent(filter=_INSTANT_OR_SORCERY, actor=_YOU),
            condition=None,
            effect=copy_spell(that_spell(), count),
        )
    )


def _template(tid: str, name: str, pattern: str, build) -> Template:
    return Template(tid=tid, name=name, bucket=_BUCKET, pattern=re.compile(pattern),
                    priority=_PRIORITY, build=build)


TEMPLATES: Final[tuple[Template, ...]] = (
    _template("B20-copy-token", "create a token that's a copy of <object>[, except ...]",
              _COPY_TOKEN_RE, _build_copy_token),
    _template("B20-copy-target-spell", "copy target instant or sorcery spell [you control]",
              r"Copy target instant or sorcery spell(?P<you> you control)?\.",
              _build_copy_target_spell),
    _template("B20-storm-copies",
              "whenever you cast an instant or sorcery spell, copy it for each other ... before it",
              r"Whenever you cast an instant or sorcery spell, copy it for each other instant and "
              r"sorcery spell you've cast before it this turn\.",
              _build_storm_copies),
    _template("B20-new-targets", "you may choose new targets for the copy|copies",
              r"You may choose new targets for the cop(?:y|ies)\.",
              lambda m: NewTargetsOutcome()),
)
