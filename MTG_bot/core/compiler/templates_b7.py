"""B7 bucket — the ZND-2 LANDFALL + Equipment-ETB family (grammar round 20,
spec KNOWLEDGE/2026-10-18/101).

Two ZNR shape families whose heads the earlier buckets never claimed:

- ``Landfall — Whenever a land you control enters, <effect>.`` — the
  keyword word is PURE HEAD SYNTAX (no ``KeywordAbility`` atom: Landfall
  creates no static, CR 603.8b wraps a plain ``Whenever`` trigger). The
  event is the Garruk's-Uprising subject idiom: a land YOU control enters
  under YOUR control — ``to_zone`` controller YOU plus a subject filter
  ``FAnd(TYPE_EQ "Land", CONTROLLER_IS YOU)``. FM2 falsifier (spec /101
  G-FM2): an object whose type line lacks "Land" is not a subject, and a
  land entering under an opponent fails the ``to_zone`` controller —
  direction rejected twice. (This is the corpus-appropriate CR 603.8b
  reading; the full rule's control-change corner cases stay in the gap
  ledger.)
- ``When this Equipment enters, attach it to target creature you
  control.`` — the class-A self anchor plus the b5a ``_build_equip``
  ATTACH atom, byte-identical shape, wrapped in a TriggeredAbility.

FM6 SHARED-TAIL LAW: every effect tail is built by ``templates_b6``'s
single shared ``_TAIL_BUILDERS`` table via ``_build_tail`` — the same
tail sentence compiles to the same effect tree no matter which head
carries it, and this module NEVER forks a tail encoding.

UNCOVERED on purpose (gap ledger 2026-10-18, honest residue — five
register rows whose landfall tail needs grammar the freeze forbids):
- ``…choose one —`` (Felidar Retreat: modal chooser head, no M21 idiom);
- ``…if this card is in your graveyard and it's your turn, you may cast
  it from your graveyard this turn.`` (Skyclave Shade: self-zone-condition
  cast-from-graveyard);
- ``…this creature can attack this turn as though it didn't have
  defender.`` (Skyclave Squid: no AS_THOUGH attack modifier);
- ``…if it's your main phase, there's an additional combat phase after
  this phase.`` (Moraug: no ADDITIONAL_PHASE atom);
- ``…you gain 4 life if this is the first time this ability has resolved
  this turn.`` (Omnath: no RESOLUTION_COUNT history pred).
Also outside the template by design: the Confounding Conundrum row
("Whenever a land an opponent controls enters, …") is NOT a ``Landfall —``
head (opponent-direction event, trigger-internal anaphor) and stays
residue; and "This land enters tapped." MLD face-B rows already belong to
B4-enters-tapped-land.
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    CounterKind,
    Effect,
    FAnd,
    FAtom,
    FAtomPred,
    QConst,
    Selector,
    SelectorMode,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    SentenceOutcome,
    Template,
)
from MTG_bot.core.compiler.templates_b6 import (
    _alts_suffix,
    _build_tail,
    _etb_event,
)

_BUCKET: Final = "B7"
_PRIORITY: Final[int] = 112  # above B6 (110): the concrete "Landfall — "
# prefix and the "When this Equipment enters" head are claimed by no other
# module, so the order never binds — it only pins the family on top.


def _template(tid: str, name: str, pattern: str, build) -> Template:
    return Template(
        tid=tid,
        name=name,
        bucket=_BUCKET,
        pattern=re.compile(pattern),
        priority=_PRIORITY,
        build=build,
    )


# ---------------------------------------------------------------------------
# Landfall
# ---------------------------------------------------------------------------

#: The landfall effect tails in the committed 2026-10-18 ZNR work
#: register — every sentence is a key of ``templates_b6._TAIL_BUILDERS``
#: (locked by test_templates_b7), so the trees are shared, never forked.
_LANDFALL_TAILS: Final[tuple[str, ...]] = (
    "this creature gets +2/+2 until end of turn.",
    "put a +1/+1 counter on this creature.",
    "creatures you control get +1/+1 until end of turn.",
    "you gain 1 life.",
    "put four +1/+1 counters on target Plant you control.",
    "equipped creature gets +2/+2 until end of turn.",
    "this creature deals 1 damage to each opponent.",
    "add one mana of any color.",
    "each opponent mills three cards.",
    "this creature gains indestructible until end of turn.",
    "create a 1/1 green Insect creature token.",
    "exile the top card of your library.",
    "tap target creature an opponent controls.",
)


def _landfall_event() -> ZoneChangeEvent:
    """``Whenever a land you control enters`` — subject is the described
    filter (b2a ``_etb_event`` law: a generic ``a <class>`` event passes
    the described filter, never None), and the direction is part of the
    event: to_zone controller YOU (CR 603.8b "…enters the battlefield
    under your control")."""
    return ZoneChangeEvent(
        from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
        to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
        subject=FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
    )


def _loyalty_self_selector(name: str) -> Selector:
    """``put a loyalty counter on <Name>.`` — the self-name anaphor.
    Same semantic encoding as b5a ``_build_exile_self`` (CR 201.4: an
    intrinsic ability naming its own object means THAT object → the
    anchor is IS_SOURCE, no hardcoded name), plus the printed gate word
    as a NAME_CONTAINS twin (executor 13c Teferi idiom: proper-noun
    substring of the printed name), so a head whose name does not carry
    the printed word never self-fires."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.IS_SOURCE),
                FAtom(pred=FAtomPred.NAME_CONTAINS, string_value=name),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _build_landfall_trigger(m: re.Match[str]) -> SentenceOutcome:
    name = m.group("name")
    if name is not None:
        effect: Effect = Atom(
            verb=Verb.PUT_COUNTER,
            args=AtomArgs(
                pairs=(
                    ("target", _loyalty_self_selector(name)),
                    ("counter_kind", CounterKind.LOYALTY),
                    ("count", QConst(1)),
                )
            ),
        )
    else:
        effect = _build_tail(m.group("tail"))
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_landfall_event(),
            condition=None,
            effect=effect,
        )
    )


# ---------------------------------------------------------------------------
# Equipment ETB attach
# ---------------------------------------------------------------------------


def _build_equip_etb(m: re.Match[str]) -> SentenceOutcome:
    # The ATTACH atom is the b5a _build_equip Equip-cost atom with the
    # Cost swapped for the ETB trigger wrapper — same slots, same
    # selectors (FM6: one encoding per shape).
    attach = Atom(
        verb=Verb.ATTACH,
        args=AtomArgs(
            pairs=(
                (
                    "equipment",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.IS_SOURCE),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                    ),
                ),
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAnd(
                            children=(
                                FAtom(
                                    pred=FAtomPred.TYPE_EQ,
                                    string_value="Creature",
                                ),
                                FAtom(
                                    pred=FAtomPred.CONTROLLER_IS,
                                    who=ControllerRef.YOU,
                                ),
                            )
                        ),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                    ),
                ),
            )
        ),
    )
    return AbilityOutcome(
        ability=TriggeredAbility(event=_etb_event(), condition=None, effect=attach)
    )


TEMPLATES: tuple[Template, ...] = (
    _template(
        "B7-landfall-trigger",
        "Landfall — whenever a land you control enters, <effect>",
        r"^Landfall — Whenever a land you control enters, "
        r"(?:(?P<tail>" + _alts_suffix(list(_LANDFALL_TAILS)) + r")"
        r"|put a loyalty counter on (?P<name>[^.]+))\.$",
        _build_landfall_trigger,
    ),
    _template(
        "B7-equip-etb",
        "when this Equipment enters, attach it to target creature you control",
        r"^When this Equipment enters, attach it to target creature you "
        r"control\.$",
        _build_equip_etb,
    ),
)
