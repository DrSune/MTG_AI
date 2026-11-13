"""B17 bucket: a colour or a creature type chosen as a permanent enters (ontology round R9).

"As this artifact enters, choose a creature type." is a replacement effect (CR 614.1c): the choice
is made before the permanent enters (CR 614.12a). It is the EtBState effect Runed Halo's card name
uses, ``Verb.CHOOSE_NAME``, with the ``quality`` role: COLOR or CREATURE_TYPE. The abilities that
read "the chosen color" or "the chosen type" are linked to it (CR 607.2d) and read it back with
``FAtomPred.NAME_CHOSEN`` of the same quality, in the source's coordinates:

* "As this artifact|creature|enchantment|land enters, choose a color|creature type." (Diamond
  Knight, Icon of Ancestry and 16 more sentences of the 19 sets).
* "Whenever you cast a spell of the chosen color|type, put a +1/+1 counter on this creature."
  (Diamond Knight). ``CHOSEN_CAST_RE`` and ``chosen_cast_event`` are the head the frame
  B13-cast-chosen shares, composing any clause that parses alone ("you gain 1 life": Diamond Mare,
  Prism Ring).
* "[Other] creatures you control of the chosen type|color get +P/+T." (Icon of Ancestry, Rally the
  Ranks, Obelisk of Urd, Heraldic Banner, Adaptive Automaton).
* "You may reveal a creature card of the chosen type from among them and put it into your hand."
  (Icon of Ancestry; Garruk's Harbinger's shape, templates_b4.reveal_one_from_among).

"The chosen type" is always a creature type here. Where a card chose another kind of type
(Umori's card type, Convincing Mirage's basic land type), the read has no CHOOSE_NAME of its
quality, and the card is refused (ability_tree.chosen_quality_fault). Not matched, and why:
"As it enters, choose a color." (Uncharted Haven: a template sees no context to tell "it" is the
card) and "As The Ringhart Crest enters, ..." (a face named in full).

Priority 10, as B14-B16: no other template matches these sentences.
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CastSpellEvent,
    ControllerRef,
    CounterKind,
    EtBState,
    FAnd,
    FAtom,
    FAtomPred,
    PtDelta,
    PtDirection,
    QConst,
    Selector,
    StaticAbility,
    Verb,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    SentenceOutcome,
    Template,
)
from MTG_bot.core.compiler.templates_b2b import (
    _ability,
    _other_creatures_you_control,
    _self_selector,
)
from MTG_bot.core.compiler.templates_b4 import (
    _creatures_you_control,
    reveal_one_from_among,
)

_BUCKET: Final[str] = "B17"
_PRIORITY: Final[int] = 10
#: How the text names each quality: "choose a creature type", "the chosen type".
_QUALITY: Final[dict[str, str]] = {
    "color": "COLOR",
    "creature type": "CREATURE_TYPE",
    "type": "CREATURE_TYPE",
}
#: The head of a cast trigger that reads the chosen colour or creature type.
CHOSEN_CAST_RE: Final[str] = r"Whenever you cast a spell of the chosen (?P<quality>color|type)"


def _chosen(m: re.Match[str]) -> FAtom:
    return FAtom(pred=FAtomPred.NAME_CHOSEN, string_value=_QUALITY[m.group("quality")])


def chosen_cast_event(m: re.Match[str]) -> CastSpellEvent:
    """You cast a spell that has the source's chosen colour or creature type (the spell's
    description is the event's ``filter``)."""
    return CastSpellEvent(
        filter=_chosen(m), actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
    )


def _build_choose_quality(m: re.Match[str]) -> SentenceOutcome:
    """``As this <permanent> enters, choose a color|creature type.``"""
    choose = Atom(
        verb=Verb.CHOOSE_NAME,
        args=AtomArgs(pairs=(("quality", _QUALITY[m.group("quality")]),)),
    )
    return AbilityOutcome(ability=EtBState(effect=choose))


def _build_cast_chosen_counter(m: re.Match[str]) -> SentenceOutcome:
    """``Whenever you cast a spell of the chosen color, put a +1/+1 counter on this creature.``
    (Spellgorger Weird's counter on its source)."""
    counter = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                ("target", _self_selector()),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                ("count", QConst(1)),
            )
        ),
    )
    return _ability(chosen_cast_event(m), counter)


def _build_chosen_anthem(m: re.Match[str]) -> SentenceOutcome:
    """``[Other] creatures you control of the chosen type|color get +P/+T.``: a static, as
    "Creatures you control get +P/+T" is (B4), its selector narrowed to the chosen quality."""
    base = _other_creatures_you_control() if m.group("other") else _creatures_you_control()
    assert isinstance(base.filter, FAnd)  # both are "creature you control" conjunctions
    creatures = Selector(
        base.count, base.mode, FAnd(children=(*base.filter.children, _chosen(m))), zones=base.zones
    )
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", creatures),
                ("power", PtDelta(PtDirection.INCREASE, QConst(int(m.group("p"))))),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(int(m.group("t"))))),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(effect=atom))


def _build_reveal_chosen_type(m: re.Match[str]) -> SentenceOutcome:
    """``You may reveal a creature card of the chosen type from among them and put it into your
    hand.``"""
    creature = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
    return EffectOutcome(effect=reveal_one_from_among(FAnd(children=(creature, _chosen(m)))))


def _t(tid: str, name: str, pattern: str, build) -> Template:
    return Template(
        tid=tid, name=name, bucket=_BUCKET, pattern=re.compile(pattern), priority=_PRIORITY,
        build=build,
    )


TEMPLATES: tuple[Template, ...] = (
    _t("B17-etb-choose-quality", "as this permanent enters, choose a color|creature type",
       r"^As this (?:artifact|creature|enchantment|land) enters, choose a "
       r"(?P<quality>color|creature type)\.$",
       _build_choose_quality),
    _t("B17-cast-chosen-counter",
       "whenever you cast a spell of the chosen color|type, put a +1/+1 counter on this creature",
       rf"^{CHOSEN_CAST_RE}, put a \+1/\+1 counter on this creature\.$",
       _build_cast_chosen_counter),
    _t("B17-chosen-anthem", "[other] creatures you control of the chosen type|color get +P/+T",
       r"^(?:(?P<other>Other) c|C)reatures you control of the chosen (?P<quality>type|color) get "
       r"\+(?P<p>\d+)/\+(?P<t>\d+)\.$",
       _build_chosen_anthem),
    _t("B17-reveal-chosen-type",
       "you may reveal a creature card of the chosen type from among them and put it into your hand",
       r"^You may reveal a creature card of the chosen (?P<quality>type) from among them and put it "
       r"into your hand\.$",
       _build_reveal_chosen_type),
)
