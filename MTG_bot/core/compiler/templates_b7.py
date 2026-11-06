"""B7 bucket: Landfall triggers and the Equipment ETB attach.

- ``Landfall — Whenever a land you control enters, <effect>.`` The ability word is head syntax
  only: no ``KeywordAbility`` atom, a plain ``Whenever`` trigger (CR 603.8b). The event is a land
  entering under your control: ``to_zone`` controller YOU plus the subject filter
  ``FAnd(TYPE_EQ "Land", CONTROLLER_IS YOU)``, so a nonland object or a land entering under an
  opponent does not trigger it. The rule's control-change corner cases are not modelled.
- ``When this Equipment enters, attach it to target creature you control.`` The b5a
  ``_build_equip`` ATTACH atom, wrapped in a TriggeredAbility.

Every effect tail is built by ``templates_b6._build_tail`` from its shared ``_TAIL_BUILDERS``
table, so a tail sentence compiles to the same tree under any head; this module never forks a
tail encoding.

Not covered (no grammar yet): landfall tails "choose one —" (Felidar Retreat), cast this card
from your graveyard (Skyclave Shade), "as though it didn't have defender" (Skyclave Squid), an
additional combat phase (Moraug), "if this is the first time this ability has resolved this turn"
(Omnath); and "Whenever a land an opponent controls enters" (Confounding Conundrum), which is
not a ``Landfall —`` head.
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
_PRIORITY: Final[int] = 112  # above B6 (110); no other module claims these heads


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

#: The landfall effect tails. Each is a key of ``templates_b6._TAIL_BUILDERS``
#: (test_templates_b7 checks it), so the trees are shared.
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
    """``Whenever a land you control enters``: the subject is the described filter (never None, as
    in b2a ``_etb_event``), and the direction is part of the event, to_zone controller YOU
    (CR 603.8b "…enters the battlefield under your control")."""
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
    """``put a loyalty counter on <Name>.``: the self-name anaphor. An ability naming its own
    object means that object (CR 201.4), so the anchor is IS_SOURCE, as in b5a
    ``_build_exile_self``; the printed name rides along as NAME_CONTAINS, so a source whose name
    lacks the printed word never matches."""
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
    # The b5a _build_equip ATTACH atom (same slots, same selectors) under an ETB trigger
    # instead of the Equip cost.
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
