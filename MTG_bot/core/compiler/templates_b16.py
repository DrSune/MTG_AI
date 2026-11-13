"""B16 bucket: hexproof on a player, and the reveal-until dig.

Two components, each put in the carriers the IR already has:

* Hexproof on a player (CR 702.11c; "hexproof from [quality]", 702.11d): GRANT_ABILITY of the
  HEXPROOF keyword to the player you, the shape of Runed Halo's "You have protection from the
  chosen card name" (``templates_b4._you_player``).
  - "You have hexproof." is a static ability (Leyline of Sanctity, Teyo, the Shieldmage, Crystal
    Barricade, Orbs of Warding).
  - "You and permanents you control gain hexproof [from blue and from black] until end of turn."
    (Veil of Summer, Lazotep Plating) is one grant lasting the turn over one selector: the zone
    set {the battlefield, your player zone} filtered to what you control (a player controls
    themself), as "Permanents you control" is filtered (Heroic Intervention). The quality is the
    keyword's one Filter param, an FOr of COLOR_HAS for "from blue and from black" (Sporeweb
    Weaver's "hexproof from blue" is its one-colour form).
* The reveal-until dig (CR 701.20a: revealing moves nothing).
  - "Reveal cards from the top of your library until you reveal a creature card." is REVEAL with
    ``until`` (Transmogrify's sentence, revealed by you from your library): the creature card is
    the ``result``, every revealed card the window.
  - "Put that card into your hand and the rest on the bottom of your library in a random order."
    moves the ``result`` to your hand, then the rest of the window to the bottom, ``arrange``
    RANDOM (Garruk's Harbinger's "the rest" sentence).
  - Vivien, Nature's Avenger's −1 composes through the loyalty frame, Evolutionary Leap through the
    activated one; Spinner of Souls' trigger is mapped by its record.

Priority 10, as B14 and B15: no other template matches these sentences.
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    DurationEot,
    FAtom,
    FAtomPred,
    FOr,
    Keyword,
    KeywordAbility,
    QConst,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    SentenceOutcome,
    Template,
)
from MTG_bot.core.compiler.templates_b4 import _you_player
from MTG_bot.core.compiler.templates_b5b import _build_rest_bottom_random, _result_selector
from MTG_bot.core.compiler.templates_b11 import _COLOR_LETTER

_BUCKET: Final[str] = "B16"
_PRIORITY: Final[int] = 10
_COLOR: Final[str] = "|".join(_COLOR_LETTER)


def _grant_hexproof(target: Selector, params: tuple = (), duration=None) -> Atom:
    pairs = [("target", target), ("ability", KeywordAbility(keyword=Keyword.HEXPROOF, params=params))]
    if duration is not None:
        pairs.append(("duration", duration))
    return Atom(verb=Verb.GRANT_ABILITY, args=AtomArgs(pairs=tuple(pairs)))


def _build_you_have_hexproof(m: re.Match[str]) -> SentenceOutcome:
    """``You have hexproof.`` (CR 702.11c)."""
    return AbilityOutcome(ability=StaticAbility(effect=_grant_hexproof(_you_player())))


def _build_you_and_permanents_gain_hexproof(m: re.Match[str]) -> SentenceOutcome:
    """``You and permanents you control gain hexproof [from A and from B] until end of turn.``
    (CR 702.11c-d)."""
    you_and_yours = Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
        zones=(
            Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
            Zone(kind=ZoneKind.PLAYER, controller=ControllerRef.YOU),
        ),
    )
    params: tuple = ()
    if m.group("a"):
        colors = (_COLOR_LETTER[m.group("a")], _COLOR_LETTER[m.group("b")])
        params = (FOr(children=tuple(FAtom(pred=FAtomPred.COLOR_HAS, color=c) for c in colors)),)
    return EffectOutcome(effect=_grant_hexproof(you_and_yours, params, DurationEot()))


def _build_reveal_until_creature(m: re.Match[str]) -> SentenceOutcome:
    """``Reveal cards from the top of your library until you reveal a creature card.``"""
    return EffectOutcome(
        effect=Atom(
            verb=Verb.REVEAL,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("count", QConst(1)),
                    ("until", FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")),
                )
            ),
        )
    )


def _build_that_card_to_hand_rest_bottom(m: re.Match[str]) -> SentenceOutcome:
    """``Put that card into your hand and the rest on the bottom of your library in a random
    order.``"""
    to_hand = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("cards", _result_selector()),
                ("destination", Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU)),
            )
        ),
    )
    rest = _build_rest_bottom_random(m)
    assert isinstance(rest, EffectOutcome)
    return EffectOutcome(effect=Seq(steps=(to_hand, rest.effect)))


def _t(tid: str, name: str, pattern: str, build) -> Template:
    return Template(
        tid=tid, name=name, bucket=_BUCKET, pattern=re.compile(pattern), priority=_PRIORITY,
        build=build,
    )


TEMPLATES: tuple[Template, ...] = (
    _t("B16-you-have-hexproof", "you have hexproof", r"^You have hexproof\.$",
       _build_you_have_hexproof),
    _t("B16-you-and-permanents-gain-hexproof",
       "you and permanents you control gain hexproof [from A and from B] until end of turn",
       rf"^You and permanents you control gain hexproof(?: from (?P<a>{_COLOR}) and from "
       rf"(?P<b>{_COLOR}))? until end of turn\.$",
       _build_you_and_permanents_gain_hexproof),
    _t("B16-reveal-until-creature",
       "reveal cards from the top of your library until you reveal a creature card",
       r"^Reveal cards from the top of your library until you reveal a creature card\.$",
       _build_reveal_until_creature),
    _t("B16-that-card-to-hand-rest-bottom",
       "put that card into your hand and the rest on the bottom of your library in a random order",
       r"^Put that card into your hand and the rest on the bottom of your library in a random "
       r"order\.$",
       _build_that_card_to_hand_rest_bottom),
)
