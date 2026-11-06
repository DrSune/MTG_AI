"""Bucket B15 — the defending player, the blocker limit and the created token (2026-11-06).

Three rules components, each one mechanism the templates below put in the existing carriers:

* The defending player (CR 506.2, 508.5): ``ControllerRef.DEFENDING_PLAYER``, the player being
  attacked. B11's target noun phrase reads "defending player controls" ("tap target creature
  defending player controls", Master of Diversion), and "Defending player loses N life." is
  LOSE_LIFE in that player's coordinates (Leeching Sliver).
* "Can't be blocked by more than one creature" (CR 509.1b): a PREVENT_EFFECT over
  ``DeclareBlockersEvent(count=QAtLeast(2))``, the attacker becoming blocked by two or more
  creatures, so at most one may block it. The carriers are those of "can't be blocked": the
  creature's own static (Bristling Boar), a static over a class (Challenger Troll), and the
  equipped creature's (Wolfrider's Saddle, beside its +N/+N).
* The created token as a referent: CREATE_TOKEN writes the ``result`` register, so "create a
  1/1 white Soldier creature token, then attach this Equipment to it" is
  Seq(CREATE_TOKEN, ATTACH(this Equipment, result)) (Ancestral Blade). The Kaldheim Equipment
  pay first: "When this Equipment enters, you may pay {2}." is the enters frame around "You may
  pay <cost>." (OptionalEffect(PAY), as Ghostly Pilferer's), and "If you do, create ..., then
  attach this Equipment to it." follows it as an "If you do" (CR 118.12).

Priority 10 as B11 and B14: every sentence here was unparsed before, so no other template
competes.
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    DeclareBlockersEvent,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    OptionalEffect,
    QAtLeast,
    QConst,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler import templates_b2a, templates_b3, templates_b5a, templates_b11
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    SentenceOutcome,
    Template,
)

_BUCKET: Final[str] = "B15"
_PRIORITY: Final[int] = 10

_IS_SOURCE: Final[FAtom] = FAtom(pred=FAtomPred.IS_SOURCE)
#: "equipped creature" in a static (MAPPER_GUIDE): the attachment edge and a creature.
_EQUIPPED: Final[Filter] = FAnd(
    children=(
        FAtom(pred=FAtomPred.IS_ATTACHED_TO_SOURCE),
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
    )
)
_MORE_THAN_ONE: Final[str] = "can't be blocked by more than one creature"

# --------------------------------------------------------------------------- defending player


def _build_defending_player_loses_life(m: re.Match[str]) -> SentenceOutcome:
    """Defending player loses N life. (Leeching Sliver's clause, under its attack frame.)"""
    return EffectOutcome(
        effect=Atom(
            verb=Verb.LOSE_LIFE,
            args=AtomArgs(
                pairs=(
                    ("amount", QConst(int(m.group("n")))),
                    ("controller", ControllerRef.DEFENDING_PLAYER),
                )
            ),
        )
    )


# --------------------------------------------------------------------------- blocker limit


def _cant_be_blocked_by_more_than_one(blocked: Filter) -> Atom:
    """The attacker can't become blocked by two or more creatures (CR 509.1b). The condition
    names the restricted creature as in every "can't be blocked" carrier (B14)."""
    event = DeclareBlockersEvent(FAnd(()), blocked=blocked, count=QAtLeast(2))
    return Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(pairs=(("condition", blocked), ("event", event))),
    )


def _build_self_more_than_one(m: re.Match[str]) -> SentenceOutcome:
    """This creature can't be blocked by more than one creature."""
    return AbilityOutcome(ability=StaticAbility(effect=_cant_be_blocked_by_more_than_one(_IS_SOURCE)))


def _build_power_class_more_than_one(m: re.Match[str]) -> SentenceOutcome:
    """Each creature you control with power N or greater can't be blocked by more than one
    creature. (Challenger Troll; judged in the static's own coordinates, so "you" is its
    controller.)"""
    creatures = FAnd(
        children=(
            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            FAtom(pred=FAtomPred.POWER_GE, count=QConst(int(m.group("n")))),
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        )
    )
    return AbilityOutcome(ability=StaticAbility(effect=_cant_be_blocked_by_more_than_one(creatures)))


def _build_equipped_pt_more_than_one(m: re.Match[str]) -> SentenceOutcome:
    """Equipped creature gets +P/+T and can't be blocked by more than one creature. The +P/+T
    is B11's attached MODIFY_PT; both parts are one static, in printed order."""
    pt = templates_b5a._enchant_pt(m, (1, 2))
    limit = _cant_be_blocked_by_more_than_one(_EQUIPPED)
    return AbilityOutcome(ability=StaticAbility(effect=Seq(steps=(pt, limit))))


# --------------------------------------------------------------------------- created token


def _create_then_attach(m: re.Match[str]) -> Seq:
    """Create the token, then attach this Equipment to it: the token is the ``result`` of the
    create step (verbs._v_create_token)."""
    create = templates_b11._build_create_tokens(m)
    assert isinstance(create, EffectOutcome)
    neutral = (Zone(ZoneKind.ANY, ControllerRef.ANY),)
    attach = Atom(
        verb=Verb.ATTACH,
        args=AtomArgs(
            pairs=(
                (
                    "equipment",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        _IS_SOURCE,
                        zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
                    ),
                ),
                ("target", Selector(QConst(1), SelectorMode.CHOOSE, FAnd(()), neutral, "result")),
            )
        ),
    )
    return Seq(steps=(create.effect, attach))


def _build_etb_create_attach(m: re.Match[str]) -> SentenceOutcome:
    """When this Equipment enters, create <token>, then attach this Equipment to it."""
    return templates_b2a._ability(templates_b2a._etb_event(_IS_SOURCE), _create_then_attach(m))


def _build_if_do_create_attach(m: re.Match[str]) -> SentenceOutcome:
    """If you do, create <token>, then attach this Equipment to it. (Gated on the payment
    before it by the compiler's "If you do" merge, CR 118.12.)"""
    return EffectOutcome(effect=_create_then_attach(m))


def _build_you_may_pay(m: re.Match[str]) -> SentenceOutcome:
    """You may pay <mana>. (Composed with a trigger frame: "When this Equipment enters, you may
    pay {2}.", the Kaldheim Equipment; Ghostly Pilferer's OptionalEffect(PAY) shape.)"""
    cost = templates_b3._parse_cost(m)
    return EffectOutcome(
        effect=OptionalEffect(inner=Atom(verb=Verb.PAY, args=AtomArgs(pairs=(("cost", cost),))))
    )


def _t(tid: str, name: str, pattern: str, build) -> Template:
    return Template(
        tid=tid, name=name, bucket=_BUCKET, pattern=re.compile(pattern), priority=_PRIORITY,
        build=build,
    )


_CREATE_ATTACH: Final[str] = (
    rf"create {templates_b11.TOKEN_RE}, then attach this Equipment to it\.$"
)

TEMPLATES: tuple[Template, ...] = (
    _t("B15-defending-player-loses-life", "defending player loses N life",
       r"^Defending player loses (?P<n>\d+) life\.$", _build_defending_player_loses_life),
    _t("B15-cant-be-blocked-by-more-than-one", f"this creature {_MORE_THAN_ONE}",
       rf"^This creature {_MORE_THAN_ONE}\.$", _build_self_more_than_one),
    _t("B15-power-class-cant-be-blocked-by-more-than-one",
       f"each creature you control with power N or greater {_MORE_THAN_ONE}",
       rf"^Each creature you control with power (?P<n>\d+) or greater {_MORE_THAN_ONE}\.$",
       _build_power_class_more_than_one),
    _t("B15-equipped-pt-cant-be-blocked-by-more-than-one",
       f"equipped creature gets +P/+T and {_MORE_THAN_ONE}",
       rf"^Equipped creature gets \+(\d+)/\+(\d+) and {_MORE_THAN_ONE}\.$",
       _build_equipped_pt_more_than_one),
    _t("B15-etb-create-attach",
       "when this Equipment enters, create <token>, then attach this Equipment to it",
       rf"^When this Equipment enters, {_CREATE_ATTACH}", _build_etb_create_attach),
    _t("B15-if-do-create-attach",
       "if you do, create <token>, then attach this Equipment to it",
       rf"^If you do, {_CREATE_ATTACH}", _build_if_do_create_attach),
    _t("B15-you-may-pay", "you may pay <mana>",
       r"^You may pay (?P<cost>(?:\{[0-9WUBRG]+\})+)\.$", _build_you_may_pay),
)
