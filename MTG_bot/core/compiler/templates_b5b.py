"""B5b bucket templates.

Each template fullmatches a concrete oracle sentence of the B5b bucket
(``/tmp/opencode/phase1_buckets/B5b.json``, written by tools/gen_buckets.py),
never the normalized shape key. A sentence fullmatches at most one template
(pinned in tests). A multi-shape template uses one closed alternation for the
varying part, and its builder branches on the captured text.

Conventions:

- ``this creature`` and other self-references are
  ``Selector(QConst(1), CHOOSE, FAtom(IS_SOURCE), Zone(BATTLEFIELD, ANY))``.
- A replacement "If X would ..., do Y instead" compiles to a card-level
  ``ReplacementAbility(event, condition, action)`` via ``AbilityOutcome``,
  whichever sentence it follows: the event scoping binds it to the right
  action. An "instead" that rewrites the spell's own previous instruction
  (CR 608.2c) is a ``KickerEffectOutcome(replaces=True)`` arm instead.
- ``it`` / ``that X`` in a replacement action is the event subject
  (``_event_referent``); after a sentence that revealed, chose, exiled or
  moved something it is the result register (``_result_selector``).
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    QX,
    AbilityTriggerEvent,
    ActivatedAbility,
    Atom,
    AtomArgs,
    CardDrawnEvent,
    Choose,
    Conditional,
    ControllerRef,
    Cost,
    CostDeltaIncreaseGeneric,
    CostManaGeneric,
    CostModifier,
    CostSacrifice,
    CostTap,
    CounterKind,
    CounterPlacedEvent,
    CreatureDiesEvent,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DurationEot,
    DurationPermanent,
    EachPlayer,
    Effect,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    TriggeredAbility,
    PtDelta,
    PtDirection,
    QAgg,
    QAtLeast,
    QAtMost,
    QBin,
    QBinOp,
    Rounding,
    QConst,
    QCount,
    QProp,
    QPropField,
    QUnbounded,
    ReplacementAbility,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    TokenSpec,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    ZonePosition,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    KeywordOutcome,
    KickerEffectOutcome,
    RuleReminderOutcome,
    SentenceOutcome,
    Template,
)
from MTG_bot.core.compiler.templates_b5a import target_spell

_BUCKET = "B5b"
_PRIORITY = 100


# ---------------------------------------------------------------------------
# Shared selector helpers
# ---------------------------------------------------------------------------


def _this_creature() -> Selector:
    """Selector for ``this creature`` — the source of the ability."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(pred=FAtomPred.IS_SOURCE),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _each_creature_you_control() -> Selector:
    """Selector for ``each creature you control``."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _up_to_two_target_creatures() -> Selector:
    """Selector for ``up to two target creatures``: TARGET + QAtMost(2) (designate 1..2,
    resolve 0..2). CHOOSE would erase which targets are legal."""
    return Selector(
        QAtMost(2),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _target_creature_you_control() -> Selector:
    """Selector for ``target creature you control``."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _target_creature_or_pw() -> Selector:
    """Selector for ``target creature or planeswalker``."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FOr(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _target_permanent_card_your_graveyard() -> Selector:
    """Selector for ``target permanent card from your graveyard``."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.IS_PERMANENT),
        zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),),
    )


def _up_to_two_target_creature_cards_your_graveyard() -> Selector:
    """Selector for ``up to two target creature cards from your graveyard``: TARGET +
    QAtMost(2), as in _up_to_two_target_creatures."""
    return Selector(
        QAtMost(2),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),),
    )


def _two_untapped_spirits_you_control() -> Selector:
    """Selector for ``two untapped Spirits you control``."""
    return Selector(
        QConst(2),
        SelectorMode.CHOOSE,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Spirit"),
                FAtom(pred=FAtomPred.IS_UNTAPPED),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _target_creature_not_you() -> Selector:
    """Selector for ``target creature you don't control``."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FNot(inner=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _any_target() -> Selector:
    """Selector for ``any target``: a creature, planeswalker or player (CR 109.5), never a card in
    a hand or library. The card side is the battlefield with the FOr type filter; the player side
    joins through the engine's widening (query._widen_any_target and selectors._is_any_universal
    recognize this exact shape), so the filter is never evaluated on a player."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FOr(
            (
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                # Never matches a card (no card has the type "Player"): it marks the
                # population as CR 109.5 "any target", so the engine widening tells it
                # apart from "target creature or planeswalker", which never denotes a
                # player (CR 115.1d).
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Player"),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _each_permanent_you_control() -> Selector:
    """Selector for ``Permanents you control``."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


# ---------------------------------------------------------------------------
# Build functions (one per template)
# ---------------------------------------------------------------------------


def _build_flash(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.FLASH)


def _build_haste(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.HASTE)


def _build_hexproof(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.HEXPROOF)


def _build_token_demon(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.CREATE_TOKEN,
        args=AtomArgs(
            pairs=(
                (
                    "tokens",
                    TokenSpec(
                        name="Demon",
                        type_line="Creature — Demon",
                        types=("Creature",),
                        subtypes=("Demon",),
                        power=QConst(int(m.group(1))),
                        toughness=QConst(int(m.group(2))),
                        keywords=(Keyword.FLYING,),
                        abilities=(),
                        colors=("B",),
                    ),
                ),
                ("count", QConst(1)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_token_zombie(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.CREATE_TOKEN,
        args=AtomArgs(
            pairs=(
                (
                    "tokens",
                    TokenSpec(
                        name="Zombie",
                        type_line="Creature — Zombie",
                        types=("Creature",),
                        subtypes=("Zombie",),
                        power=QConst(int(m.group(1))),
                        toughness=QConst(int(m.group(2))),
                        keywords=(),
                        abilities=(),
                        colors=("B",),
                    ),
                ),
                ("count", QConst(1)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_cont_discard(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)),
                ("from", Zone(ZoneKind.HAND, ControllerRef.YOU)),
                ("controller", ControllerRef.YOU),
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAnd(children=()),
                        zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),),
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_cont_draw(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(1)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_seq_modpt_trample(m: re.Match[str]) -> SentenceOutcome:
    target = _this_creature()
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.MODIFY_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        (
                            "power",
                            PtDelta(PtDirection.INCREASE, QConst(int(m.group(1)))),
                        ),
                        (
                            "toughness",
                            PtDelta(PtDirection.INCREASE, QConst(int(m.group(2)))),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
            Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        ("ability", KeywordAbility(keyword=Keyword.TRAMPLE, params=())),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )
    return EffectOutcome(effect=seq)


def _build_cont_gain_4(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.GAIN_LIFE,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(int(m.group(1)))),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_cont_gain_mv(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.GAIN_LIFE,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QProp("target", QPropField.MANA_VALUE, QAgg.FIRST)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_lifelink(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.LIFELINK)


def _build_look_3(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.LOOK_AT,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("count", QConst(3)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_menace(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.MENACE)


def _build_perm_hex_ind(m: re.Match[str]) -> SentenceOutcome:
    target = _each_permanent_you_control()
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        (
                            "ability",
                            KeywordAbility(keyword=Keyword.HEXPROOF, params=()),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
            Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        (
                            "ability",
                            KeywordAbility(keyword=Keyword.INDESTRUCTIBLE, params=()),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )
    return EffectOutcome(effect=seq)


def _build_prowess(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.PROWESS)


def _build_put_counter(m: re.Match[str]) -> SentenceOutcome:
    target_desc = m.group(3)
    if target_desc == "each creature you control":
        target = _each_creature_you_control()
    elif target_desc == "each of up to two target creatures":
        target = _up_to_two_target_creatures()
    elif target_desc == "target creature you control":
        target = _target_creature_you_control()
    else:
        raise ValueError(f"unexpected put-counter target: {target_desc!r}")
    atom = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                ("target", target),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                ("count", QConst(1)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_reach(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.REACH)


def _build_return_creatures_battlefield(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),),
                    ),
                ),
                (
                    "destination",
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_return_cards_hand(m: re.Match[str]) -> SentenceOutcome:
    card_desc = m.group(1)
    if card_desc == "target permanent card":
        cards = _target_permanent_card_your_graveyard()
    elif card_desc == "up to two target creature cards":
        cards = _up_to_two_target_creature_cards_your_graveyard()
    elif card_desc == "target card":
        # Any card from your graveyard (Bala Ged Recovery): the empty FAnd matches all.
        cards = Selector(
            QConst(1),
            SelectorMode.TARGET,
            FAnd(children=()),
            zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),),
        )
    else:
        raise ValueError(f"unexpected return-cards-hand description: {card_desc!r}")
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("cards", cards),
                ("destination", Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_return_spell_creature_owner_hand(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FOr(
                            children=(
                                FAtom(pred=FAtomPred.STACK_KIND_EQ, string_value="SPELL"),
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                            )
                        ),
                        zones=(Zone(kind=ZoneKind.STACK, controller=ControllerRef.ANY), *(
                            Zone(
                                kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY
                            ),
                        )),
                    ),
                ),
                (
                    "destination",
                    Zone(kind=ZoneKind.HAND, controller=ControllerRef.OWNER),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_sacr_grant(m: re.Match[str]) -> SentenceOutcome:
    """Selfless Savior: "Sacrifice this creature: Another target creature you
    control gains indestructible until end of turn." "Another" is FNot(IS_SOURCE),
    so the Savior cannot target itself (CR 601.2c, 602.2b)."""
    effect = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAnd(
                            children=(
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                                FAtom(
                                    pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU
                                ),
                                FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
                            )
                        ),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                    ),
                ),
                ("ability", KeywordAbility(keyword=Keyword.INDESTRUCTIBLE, params=())),
                ("duration", DurationEot()),
            )
        ),
    )
    ability = ActivatedAbility(
        cost=Cost(parts=(CostSacrifice(target=_this_creature()),)),
        effect=effect,
    )
    return AbilityOutcome(ability=ability)


def _build_named_damage(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _target_creature_or_pw()),
                ("amount", QConst(int(m.group(2)))),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_scr_reveal(m: re.Match[str]) -> SentenceOutcome:
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.SCRY,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("count", QConst(int(m.group(1)))),
                    )
                ),
            ),
            Atom(
                verb=Verb.REVEAL,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("count", QConst(1)),
                    )
                ),
            ),
        )
    )
    return EffectOutcome(effect=seq)


def _build_scr(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.SCRY,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("count", QConst(int(m.group(1)))),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_search_shuffle(m: re.Match[str]) -> SentenceOutcome:
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.SEARCH,
                args=AtomArgs(
                    pairs=(
                        (
                            "cards",
                            Selector(
                                QConst(1),
                                SelectorMode.CHOOSE,
                                FAnd(children=()),
                                zones=(Zone(
                                    kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU
                                ),),
                            ),
                        ),
                        (
                            "destination",
                            Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
                        ),
                        ("controller", ControllerRef.YOU),
                    )
                ),
            ),
            Atom(
                verb=Verb.SHUFFLE,
                args=AtomArgs(
                    pairs=(
                        (
                            "zone",
                            Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU),
                        ),
                    )
                ),
            ),
        )
    )
    return EffectOutcome(effect=seq)


def _build_damage_any(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _any_target()),
                ("amount", QConst(int(m.group(1)))),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_tap_spirits(m: re.Match[str]) -> SentenceOutcome:
    effect = Atom(
        verb=Verb.TAP,
        args=AtomArgs(pairs=(("target", _target_creature_not_you()),)),
    )
    ability = ActivatedAbility(
        cost=Cost(parts=(CostTap(target=_two_untapped_spirits_you_control()),)),
        effect=effect,
    )
    return AbilityOutcome(ability=ability)


def _build_tap_2_target(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.TAP,
        args=AtomArgs(pairs=(("target", _up_to_two_target_creatures()),)),
    )
    return EffectOutcome(effect=atom)


def _build_seq_modpt_firststrike(m: re.Match[str]) -> SentenceOutcome:
    target = Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.MODIFY_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        (
                            "power",
                            PtDelta(PtDirection.INCREASE, QConst(int(m.group(1)))),
                        ),
                        (
                            "toughness",
                            PtDelta(PtDirection.INCREASE, QConst(int(m.group(2)))),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
            Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        (
                            "ability",
                            KeywordAbility(keyword=Keyword.FIRST_STRIKE, params=()),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )
    return EffectOutcome(effect=seq)


def _build_modpt_plus(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                    ),
                ),
                ("power", PtDelta(PtDirection.INCREASE, QConst(int(m.group(1))))),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(int(m.group(2))))),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_modpt_minus(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                    ),
                ),
                ("power", PtDelta(PtDirection.DECREASE, QConst(int(m.group(1))))),
                ("toughness", PtDelta(PtDirection.DECREASE, QConst(int(m.group(2))))),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_seq_modpt_hexproof(m: re.Match[str]) -> SentenceOutcome:
    target = _target_creature_you_control()
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.MODIFY_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        (
                            "power",
                            PtDelta(PtDirection.INCREASE, QConst(int(m.group(1)))),
                        ),
                        (
                            "toughness",
                            PtDelta(PtDirection.INCREASE, QConst(int(m.group(2)))),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
            Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        (
                            "ability",
                            KeywordAbility(keyword=Keyword.HEXPROOF, params=()),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )
    return EffectOutcome(effect=seq)


def _build_modpt_x(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _target_creature_you_control()),
                ("power", PtDelta(PtDirection.INCREASE, QX())),
                ("toughness", PtDelta(PtDirection.INCREASE, QX())),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_reveal_hand(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.REVEAL,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.TARGET_OPPONENT),
                ("count", QUnbounded()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_sacr_flying(m: re.Match[str]) -> SentenceOutcome:
    """Run Afoul: "Target opponent sacrifices a creature of their choice with
    flying."

    The edict shape: EachPlayer(TARGET_OPPONENT, ...) rotates the controller to
    the player who sacrifices, and the SACRIFICE pick is YOU-relative
    (CONTROLLER_IS YOU), so only that player's fliers are candidates and that
    player chooses (CR 701.21a). The ref gives the spell its player target
    slot, which offers opponents only (CR 102.2).
    """
    atom = Atom(
        verb=Verb.SACRIFICE,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAnd(
                            children=(
                                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                                FAtom(
                                    pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING
                                ),
                            )
                        ),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=EachPlayer(ref=ControllerRef.TARGET_OPPONENT, effect=atom))


def _build_discard_target_2(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.TARGET_PLAYER)),
                ("from", Zone(ZoneKind.HAND, ControllerRef.TARGET_PLAYER)),
                ("controller", ControllerRef.TARGET_PLAYER),
                (
                    "cards",
                    Selector(
                        QConst(2),
                        SelectorMode.CHOOSE,
                        FAnd(children=()),
                        zones=(Zone(
                            kind=ZoneKind.HAND, controller=ControllerRef.TARGET_PLAYER
                        ),),
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_noncreature_cost_modifier(m: re.Match[str]) -> SentenceOutcome:
    """Noncreature spells cost {N} more to cast (Vryn Wingmare)."""
    modifier = CostModifier(
        filter=FNot(inner=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")),
        controller_ref=ControllerRef.ANY,
        delta=CostDeltaIncreaseGeneric(amount=QConst(int(m.group(1)))),
    )
    return AbilityOutcome(ability=modifier)


# ---------------------------------------------------------------------------
# Replacement-effect builders
# ---------------------------------------------------------------------------


def _event_referent() -> Selector:
    """``it`` / ``that X`` in a replacement action: the event subject, a referent-bound
    CHOOSE of one in the neutral zone."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAnd(children=()),
        zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
        referent="event",
    )


def _build_repl_died_gain_life(m: re.Match[str]) -> SentenceOutcome:
    """Life Goes On: "If a creature died this turn, you gain 8 life
    instead."

    The "instead" replaces only the spell's own previous instruction ("You
    gain 4 life."; CR 608.2c, 614.1a), so it is the conditional arm
    KickerEffectOutcome(pred=DIED_THIS_TURN, replaces=True), which the
    compiler folds into Conditional(DIED_THIS_TURN, gain 8, else=gain 4):
    one life gain, its amount chosen at resolution. A card-level
    ReplacementAbility would turn every later life gain that turn into 8.
    """
    return KickerEffectOutcome(
        effect=Atom(
            verb=Verb.GAIN_LIFE,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("amount", QConst(int(m.group(1)))),
                )
            ),
        ),
        replaces=True,
        pred=FAtom(pred=FAtomPred.DIED_THIS_TURN),
    )


def _build_repl_nontoken_enter_exile(m: re.Match[str]) -> SentenceOutcome:
    """Containment Priest: "If a nontoken creature would enter and it
    wasn't cast, exile it instead."
    """
    return AbilityOutcome(
        ability=ReplacementAbility(
            event=ZoneChangeEvent(
                from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
                to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
                subject=FAnd(
                    children=(
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        FNot(inner=FAtom(pred=FAtomPred.IS_TOKEN)),
                    )
                ),
            ),
            condition=FNot(
                inner=FAtom(pred=FAtomPred.WAS_CAST_THIS_TURN, who=ControllerRef.ANY)
            ),
            action=Atom(
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                        ("target", _event_referent()),
                    )
                ),
            ),
        )
    )


def _build_repl_triple_damage(m: re.Match[str]) -> SentenceOutcome:
    """Fiery Emancipation: "If a source you control would deal damage to a
    permanent or player, it deals triple that damage to that permanent or
    player instead."

    Lossy: the event recipient "a permanent or player" is universal (no
    player predicate on the event filter).
    """
    return AbilityOutcome(
        ability=ReplacementAbility(
            event=DamageDealtEvent(
                amount=QX(),
                filter=FAnd(children=()),
                source=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            ),
            condition=None,
            action=Atom(
                verb=Verb.DEAL_DAMAGE,
                args=AtomArgs(
                    pairs=(
                        (
                            "dealer",
                            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                        ),
                        ("target", _event_referent()),
                        (
                            "amount",
                            QBin(
                                QBinOp.MUL,
                                QConst(3),
                                QProp("event", QPropField.AMOUNT),
                            ),
                        ),
                    )
                ),
            ),
        )
    )


def _build_repl_counter_plus_one(m: re.Match[str]) -> SentenceOutcome:
    """Conclave Mentor: "If one or more +1/+1 counters would be put on a
    creature you control, that many plus one +1/+1 counters are put on
    that creature instead."
    """
    return AbilityOutcome(
        ability=ReplacementAbility(
            event=CounterPlacedEvent(
                counter_kind=CounterKind.PLUS_1_PLUS_1,
                filter=FAnd(
                    children=(
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                    )
                ),
                count=QAtLeast(1),
            ),
            condition=None,
            action=Atom(
                verb=Verb.PUT_COUNTER,
                args=AtomArgs(
                    pairs=(
                        ("target", _event_referent()),
                        ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                        (
                            "count",
                            QBin(
                                QBinOp.ADD,
                                QProp("event", QPropField.COUNTER_COUNT),
                                QConst(1),
                            ),
                        ),
                    )
                ),
            ),
        )
    )


def _build_repl_die_exile(m: re.Match[str]) -> SentenceOutcome:
    """Scorching Dragonfire: "If that creature or planeswalker would die
    this turn, exile it instead."

    The tree drops "this turn" (ReplacementAbility has no duration;
    docs/BACKLOG.md B-77), but play is right: the executor gives a resolving
    instant's ReplacementAbility an end-of-turn lifetime scoped to the cast's
    designation (stack.py).
    """
    return AbilityOutcome(
        ability=ReplacementAbility(
            event=CreatureDiesEvent(filter=FAtom(pred=FAtomPred.IS_ANY_TARGET)),
            condition=None,
            action=Atom(
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                        ("target", _event_referent()),
                    )
                ),
            ),
        )
    )


def _build_repl_graveyard_exile(m: re.Match[str]) -> SentenceOutcome:
    """Chandra, Flame's Catalyst [−2]: "If that spell would be put into
    your graveyard, exile it instead."

    "that spell" is the ability's target (IS_ANY_TARGET).
    """
    return AbilityOutcome(
        ability=ReplacementAbility(
            event=ZoneChangeEvent(
                from_zone=Zone(ZoneKind.STACK, ControllerRef.ANY),
                to_zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                subject=FAtom(pred=FAtomPred.IS_ANY_TARGET),
            ),
            condition=None,
            action=Atom(
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                        ("target", _event_referent()),
                    )
                ),
            ),
        )
    )


def _build_counter_unless_pays(m: re.Match[str]) -> SentenceOutcome:
    """Lofty Denial: "If you control a creature with flying, counter that
    spell unless its controller pays {4} instead."

    The "instead" rewrites the spell's own previous instruction ("Counter
    target spell unless its controller pays {1}."; CR 608.2c), as in Life
    Goes On: the arm KickerEffectOutcome(pred, replaces=True) folds into
    Conditional(you control a creature with flying, COUNTER unless {4},
    else=COUNTER unless {1}). "that spell" is the same TARGET selector as
    the first sentence, so both branches share one target slot.
    """
    counter = Atom(
        verb=Verb.COUNTER_SPELL,
        args=AtomArgs(
            pairs=(
                # the first sentence's "target spell"
                ("target", target_spell()),
                ("unless", Cost(parts=(CostManaGeneric(amount=QConst(int(m.group(1)))),))),
            )
        ),
    )
    you_control_a_flier = FAtom(
        pred=FAtomPred.CONTROLLER_COUNT_GE,
        inner_filter=FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING),
            )
        ),
        count=QConst(1),
    )
    return KickerEffectOutcome(effect=counter, replaces=True, pred=you_control_a_flier)


def _build_repl_draw_not_first(m: re.Match[str]) -> SentenceOutcome:
    """Teferi's Ageless Insight: "If you would draw a card except the
    first one you draw in each of your draw steps, draw two cards
    instead."
    """
    return AbilityOutcome(
        ability=ReplacementAbility(
            event=CardDrawnEvent(
                actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
            ),
            condition=FAtom(
                pred=FAtomPred.NOT_FIRST_DRAW_THIS_STEP, who=ControllerRef.YOU
            ),
            action=Atom(
                verb=Verb.DRAW,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(2)),
                    )
                ),
            ),
        )
    )


def _build_cant_attack_unless_artifacts(m: re.Match[str]) -> SentenceOutcome:
    """Gadrak can't attack unless you control four or more artifacts.

    The "unless" gate is ``StaticAbility.condition`` = FNot(CONTROLLER_COUNT_GE
    Artifact), never a duration; the restriction is a PREVENT_EFFECT over
    DeclareAttackersEvent with the source as event filter. "Gadrak" is the
    self-referent (IS_SOURCE)."""
    is_source = FAtom(pred=FAtomPred.IS_SOURCE)
    atom = Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                ("condition", is_source),
                ("event", DeclareAttackersEvent(filter=is_source)),
            )
        ),
    )
    return AbilityOutcome(
        ability=StaticAbility(
            effect=atom,
            condition=FNot(
                inner=FAtom(
                    pred=FAtomPred.CONTROLLER_COUNT_GE,
                    inner_filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Artifact"),
                    count=QConst(4),
                )
            ),
        )
    )


def _build_set_pt_power_gy_count(m: re.Match[str]) -> SentenceOutcome:
    """Kinetic Augur's power is equal to the number of instant and sorcery
    cards in your graveyard: SET_PT with only the power role (each role is
    optional, at least one is required)."""
    atom = Atom(
        verb=Verb.SET_PT,
        args=AtomArgs(
            pairs=(
                ("target", _this_creature()),
                (
                    "power",
                    QCount(
                        Selector(
                            QUnbounded(),
                            SelectorMode.ALL,
                            FOr(
                                children=(
                                    FAtom(
                                        pred=FAtomPred.TYPE_EQ,
                                        string_value="Instant",
                                    ),
                                    FAtom(
                                        pred=FAtomPred.TYPE_EQ,
                                        string_value="Sorcery",
                                    ),
                                )
                            ),
                            zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),),
                        )
                    ),
                ),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


# ---------------------------------------------------------------------------
# Anaphora builders
# ---------------------------------------------------------------------------

_KW_GAIN: dict[str, Keyword] = {
    "indestructible": Keyword.INDESTRUCTIBLE,
    "haste": Keyword.HASTE,
    "vigilance": Keyword.VIGILANCE,
}

_KW_LOSE: dict[str, Keyword] = {
    "indestructible": Keyword.INDESTRUCTIBLE,
}

# "protection from the color of your choice" is a controller decision: an explicit Choose over
# the five colors, never a defaulted one.
_COLORS_WUBRG: tuple[str, ...] = ("W", "U", "B", "R", "G")


_UNIVERSAL: Final[Filter] = FAnd(children=())


def _result_selector() -> Selector:
    """The anaphoric ``it`` / ``that card`` / ``them``: the object(s) the previous sentence
    revealed, chose, exiled or moved. ``referent="result"`` reads the compiler's result
    register, never an English antecedent."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        _UNIVERSAL,
        zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
        referent="result",
    )


def _looked_top_library() -> Selector:
    """The set the previous "Look at the top N cards" sentence exposed:
    still on top of your library, so the zone is typed rather than a
    result referent."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        _UNIVERSAL,
        zones=(Zone(
            kind=ZoneKind.LIBRARY,
            controller=ControllerRef.YOU,
            position=ZonePosition.TOP,
        ),),
    )


def _build_it_gains_kw_eot(m: re.Match[str]) -> SentenceOutcome:
    """``It gains <kw> until end of turn.`` (Basri Ket, Seasoned
    Hallowblade, Basri Devoted Paladin, Traitorous Greed) — GRANT_ABILITY
    onto the result-referent object with the EOT duration."""
    kw = _KW_GAIN[m.group("kw")]
    atom = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", _result_selector()),
                ("ability", KeywordAbility(keyword=kw)),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_it_gains_haste(m: re.Match[str]) -> SentenceOutcome:
    """``It gains haste.`` (Liliana Waker emblem) — grant with NO
    duration: the emblem's put-onto-battlefield continuation grants
    permanently."""
    atom = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", _result_selector()),
                ("ability", KeywordAbility(keyword=Keyword.HASTE)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_it_gains_protection_choice(m: re.Match[str]) -> SentenceOutcome:
    """``It gains protection from the color of your choice until end of
    turn.`` (Feat of Resistance) — the color is a controller
    decision, so the grant is an explicit one-of-five Choose over
    color-parameterized PROTECTION grants; nothing is defaulted."""
    options = tuple(
        Atom(
            verb=Verb.GRANT_ABILITY,
            args=AtomArgs(
                pairs=(
                    ("target", _result_selector()),
                    (
                        "ability",
                        KeywordAbility(
                            keyword=Keyword.PROTECTION,
                            params=(FAtom(pred=FAtomPred.COLOR_HAS, color=color),),
                        ),
                    ),
                    ("duration", DurationEot()),
                )
            ),
        )
        for color in _COLORS_WUBRG
    )
    return EffectOutcome(effect=Choose(count=QConst(1), options=options))


def _build_that_player_discards_that_card(m: re.Match[str]) -> SentenceOutcome:
    """``That player discards that card.`` (Duress s3) — the player is the
    spell's targeted opponent (TARGET_PLAYER role); the card is the one the
    previous CHOOSE (``B4-you-choose-from-it``) picked off the revealed hand,
    referent="result"."""
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.TARGET_PLAYER)),
                ("from", Zone(ZoneKind.HAND, ControllerRef.TARGET_PLAYER)),
                ("controller", ControllerRef.TARGET_PLAYER),
                ("cards", _result_selector()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_if_it_type_then(m: re.Match[str]) -> SentenceOutcome:
    """``If it's a creature [or land] card, ...`` (Garruk Savage Herald
    s2, Track Down s2) — Conditional on the previous sentence's revealed
    card. FAtom has a referent slot only on IS_ATTACHED_TO, so the
    condition's subject is the result register by executor convention; the
    moved card is the referent="result" selector."""
    then = m.group("then")
    if then == "draw a card":
        if m.group("or_land") is None:
            raise ValueError(
                "B5b-if-it-type-then: bare-creature draw branch is not a"
                " printed sentence shape (pattern over-matched)"
            )
        pred: Filter = FOr(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land"),
            )
        )
        effect: Effect = Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))
            ),
        )
    else:
        if m.group("or_land") is not None:
            raise ValueError(
                "B5b-if-it-type-then: or-land hand-move branch is not a"
                " printed sentence shape (pattern over-matched)"
            )
        pred = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
        effect = Atom(
            verb=Verb.MOVE_ZONE,
            args=AtomArgs(
                pairs=(
                    ("cards", _result_selector()),
                    ("destination", Zone(ZoneKind.HAND, ControllerRef.YOU)),
                )
            ),
        )
    return EffectOutcome(effect=Conditional(pred=pred, then_effect=effect))


def _build_otherwise_bottom(m: re.Match[str]) -> SentenceOutcome:
    """``Otherwise, put it on the bottom of your library.`` (Garruk
    Savage Herald s3) — the compiler's ``_merge_otherwise`` attaches this
    effect as the preceding Conditional's ``else_effect``; the
    moved card is again the result referent."""
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("cards", _result_selector()),
                (
                    "destination",
                    Zone(
                        ZoneKind.LIBRARY,
                        ControllerRef.YOU,
                        position=ZonePosition.BOTTOM,
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_search_name_exile(m: re.Match[str]) -> SentenceOutcome:
    """``Search target opponent's graveyard, hand, and library for any
    number of cards with that name and exile them.`` (Necromentia s2) —
    the name filter reads the CHOOSE_NAME pick; "any number" is an
    unbounded CHOOSE (0 or more, not a defaulted count). The found cards
    then go to exile via the result referent."""
    search = Atom(
        verb=Verb.SEARCH,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QUnbounded(),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.NAME_CHOSEN),
                        zones=(Zone(ZoneKind.GRAVEYARD, ControllerRef.TARGET_OPPONENT), *(
                            Zone(ZoneKind.HAND, ControllerRef.TARGET_OPPONENT),
                            Zone(ZoneKind.LIBRARY, ControllerRef.TARGET_OPPONENT),
                        )),
                    ),
                ),
                ("destination", Zone(ZoneKind.EXILE, ControllerRef.TARGET_OPPONENT)),
                ("controller", ControllerRef.TARGET_OPPONENT),
            )
        ),
    )
    exile = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                ("target", _result_selector()),
            )
        ),
    )
    return EffectOutcome(effect=Seq(steps=(search, exile)))


def _build_shuffle_then_token_per_exiled(m: re.Match[str]) -> SentenceOutcome:
    """``That player shuffles, then creates a P/T black Zombie creature
    token for each card exiled from their hand this way.`` (Necromentia
    s3) — SHUFFLE + CREATE_TOKEN. "that player ... creates" is the
    CREATE_TOKEN ``controller`` role, TARGET_PLAYER (CR 111.2: the player
    who creates a token owns and controls it)."""
    token = TokenSpec(
        name="Zombie",
        type_line="Creature — Zombie",
        types=("Creature",),
        subtypes=("Zombie",),
        power=QConst(int(m.group("p"))),
        toughness=QConst(int(m.group("t"))),
        keywords=(),
        abilities=(),
        colors=("B",),
    )
    shuffle = Atom(
        verb=Verb.SHUFFLE,
        args=AtomArgs(
            pairs=(("zone", Zone(ZoneKind.LIBRARY, ControllerRef.TARGET_PLAYER)),)
        ),
    )
    # "each card exiled from their hand this way": chosen-name cards in the target's exile that
    # moved there from their hand this turn. THIS_WAY_COUNT would also count the graveyard and
    # library exiles of the search.
    hand_exiles = Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.NAME_CHOSEN),
                FAtom(
                    pred=FAtomPred.MOVED_TO_ZONE_THIS_TURN,
                    from_zone=Zone(ZoneKind.HAND, ControllerRef.TARGET_PLAYER),
                    to_zone=Zone(ZoneKind.EXILE, ControllerRef.TARGET_PLAYER),
                    who=ControllerRef.TARGET_PLAYER,
                ),
            )
        ),
        zones=(Zone(kind=ZoneKind.EXILE, controller=ControllerRef.TARGET_PLAYER),),
    )
    create = Atom(
        verb=Verb.CREATE_TOKEN,
        args=AtomArgs(
            pairs=(
                ("tokens", token),
                ("count", QCount(hand_exiles)),
                # CR 111.2: "that player" (the target opponent) creates them.
                ("controller", ControllerRef.TARGET_PLAYER),
            )
        ),
    )
    return EffectOutcome(effect=Seq(steps=(shuffle, create)))


def _build_that_permanent_loses_kw(m: re.Match[str]) -> SentenceOutcome:
    """``That permanent loses <kw> until end of turn.`` (Soul Sear s2) —
    Verb.LOSE_ABILITY mirrors GRANT_ABILITY's roles. "That permanent" is the
    spell's damaged target, so it binds referent="target", not the result
    register."""
    kw = _KW_LOSE[m.group("kw")]
    atom = Atom(
        verb=Verb.LOSE_ABILITY,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAnd(children=()),
                        zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
                        referent="target",
                    ),
                ),
                ("ability", KeywordAbility(keyword=kw)),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_one_of_other(m: re.Match[str]) -> SentenceOutcome:
    """``Put one of them into your hand and the other into your
    graveyard.`` (Waker of Waves s3) — the ONE_OF/REST split pair:
    exactly one of the looked-at set to hand, everything
    remaining ("the other", here exactly one) to the graveyard."""
    to_hand = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.ONE_OF,
                        FAnd(children=()),
                        zones=_looked_top_library().zones,
                    ),
                ),
                ("destination", Zone(ZoneKind.HAND, ControllerRef.YOU)),
            )
        ),
    )
    to_graveyard = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.REST,
                        FAnd(children=()),
                        zones=_looked_top_library().zones,
                    ),
                ),
                ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)),
            )
        ),
    )
    return EffectOutcome(effect=Seq(steps=(to_hand, to_graveyard)))


def _build_one_of_rest_bottom(m: re.Match[str]) -> SentenceOutcome:
    """``Put one of those cards into your hand and the rest on the bottom
    of your library in any order.`` (See the Truth s2) — ONE_OF/REST
    again. "In any order" is CR 401.4's default for cards put into a
    library together (their owner arranges them), so the move carries no
    ``arrange`` role."""
    to_hand = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.ONE_OF,
                        FAnd(children=()),
                        zones=_looked_top_library().zones,
                    ),
                ),
                ("destination", Zone(ZoneKind.HAND, ControllerRef.YOU)),
            )
        ),
    )
    to_bottom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.REST,
                        FAnd(children=()),
                        zones=_looked_top_library().zones,
                    ),
                ),
                (
                    "destination",
                    Zone(
                        ZoneKind.LIBRARY,
                        ControllerRef.YOU,
                        position=ZonePosition.BOTTOM,
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=Seq(steps=(to_hand, to_bottom)))


def _build_rest_bottom_random(m: re.Match[str]) -> SentenceOutcome:
    """``Put the rest on the bottom of your library in a random order.``
    (Garruk's Harbinger s3) — REST over the looked-at top cards, with
    ``arrange`` RANDOM: the order is random instead of the owner's choice
    (CR 401.4)."""
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.REST,
                        FAnd(children=()),
                        zones=_looked_top_library().zones,
                    ),
                ),
                (
                    "destination",
                    Zone(
                        ZoneKind.LIBRARY,
                        ControllerRef.YOU,
                        position=ZonePosition.BOTTOM,
                    ),
                ),
                ("arrange", "RANDOM"),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_cultivate_search(m: re.Match[str]) -> SentenceOutcome:
    """``Search your library for up to two basic land cards, reveal those
    cards, put one onto the battlefield tapped and the other into your
    hand, then shuffle.`` (Cultivate) — "up to two" is CHOOSE+QConst(2)
    (the 0/1/2 sub-choice stays open); the split is ONE_OF (battlefield,
    tapped) + REST (hand); the inline "then shuffle" is the same
    search-shuffle step ``_build_search_shuffle`` builds.
    Lossy: REVEAL has an unbounded count, since the grammar cannot
    reference the found set."""
    search = Atom(
        verb=Verb.SEARCH,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(2),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.SUPERTYPE_EQ, string_value="Basic"),
                        zones=(Zone(ZoneKind.LIBRARY, ControllerRef.YOU),),
                    ),
                ),
                ("destination", Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)),
                ("controller", ControllerRef.YOU),
            )
        ),
    )
    reveal = Atom(
        verb=Verb.REVEAL,
        args=AtomArgs(
            pairs=(("controller", ControllerRef.YOU), ("count", QUnbounded()))
        ),
    )
    to_bf = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.ONE_OF,
                        FAtom(pred=FAtomPred.SUPERTYPE_EQ, string_value="Basic"),
                        zones=(Zone(ZoneKind.LIBRARY, ControllerRef.YOU),),
                    ),
                ),
                ("destination", Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)),
                ("tapped_on_enter", True),
            )
        ),
    )
    to_hand = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.REST,
                        FAtom(pred=FAtomPred.SUPERTYPE_EQ, string_value="Basic"),
                        zones=(Zone(ZoneKind.LIBRARY, ControllerRef.YOU),),
                    ),
                ),
                ("destination", Zone(ZoneKind.HAND, ControllerRef.YOU)),
            )
        ),
    )
    shuffle = Atom(
        verb=Verb.SHUFFLE,
        args=AtomArgs(pairs=(("zone", Zone(ZoneKind.LIBRARY, ControllerRef.YOU)),)),
    )
    return EffectOutcome(effect=Seq(steps=(search, reveal, to_bf, to_hand, shuffle)))


def _its_controller() -> Selector:
    """"That creature's controller" / "that player" after "Exile target creature":
    the controller of the designated object (referent "target"), as it last existed
    on the battlefield (CR 608.2h). Not a player target: the spell has one target."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        _UNIVERSAL,
        zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
        referent="target",
    )


def _build_transmog_reveal_creature(m: re.Match[str]) -> SentenceOutcome:
    """``That creature's controller reveals cards from the top of their
    library until they reveal a creature card.`` (Transmogrify s2):
    REVEAL with an ``until`` filter, revealed by the exiled creature's
    controller from their library. The first creature card revealed is the
    ``result`` ("that card" of s3); nothing moves."""
    return EffectOutcome(
        effect=Atom(
            verb=Verb.REVEAL,
            args=AtomArgs(
                pairs=(
                    ("controller", _its_controller()),
                    ("count", QConst(1)),
                    ("until", FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")),
                )
            ),
        )
    )


def _build_transmog_shuffle_rest(m: re.Match[str]) -> SentenceOutcome:
    """``That player puts that card onto the battlefield, then shuffles the
    rest into their library.`` (Transmogrify s3): EachPlayer over the exiled
    creature's controller, so "that player" puts the revealed creature card
    (the ``result``) onto the battlefield under their control (CR 110.2a) and
    shuffles their library, which holds the rest of the revealed cards."""
    put = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("cards", _result_selector()),
                ("destination", Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)),
            )
        ),
    )
    shuffle = Atom(
        verb=Verb.SHUFFLE,
        args=AtomArgs(pairs=(("zone", Zone(ZoneKind.LIBRARY, ControllerRef.YOU)),)),
    )
    return EffectOutcome(
        effect=EachPlayer(ref=_its_controller(), effect=Seq(steps=(put, shuffle)))
    )


def _build_cast_elsewhere_instead(m: re.Match[str]) -> SentenceOutcome:
    """``If this spell was cast from anywhere other than your hand, put
    each of those cards into your hand instead.`` (See the Truth s3) —
    Conditional on the cast zone (CAST_THIS_TURN_FROM, negated for
    "anywhere other than your hand") moving the whole result set to hand.
    Lossy: "instead" — the grammar has no branch-exclusion marker, so the
    Conditional is a sibling step after the one-and-rest split rather than
    a replacement of it (ReplacementAbility is event-shaped, not
    cast-zone-shaped). A referent selector is always CHOOSE/QConst(1)/
    neutral zone, so the executor applies the register's plurality per
    object."""
    cond = FNot(
        inner=FAtom(
            pred=FAtomPred.CAST_THIS_TURN_FROM,
            zone=Zone(ZoneKind.HAND, ControllerRef.YOU),
            who=ControllerRef.YOU,
        )
    )
    move = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("cards", _result_selector()),
                ("destination", Zone(ZoneKind.HAND, ControllerRef.YOU)),
            )
        ),
    )
    return EffectOutcome(effect=Conditional(pred=cond, then_effect=move))


def _build_gain_control_eot(m: re.Match[str]) -> SentenceOutcome:
    """``Gain control of target creature until end of turn.`` (Traitorous
    Greed s1) — GAIN_CONTROL with its optional duration role."""
    atom = Atom(
        verb=Verb.GAIN_CONTROL,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                    ),
                ),
                ("controller", ControllerRef.YOU),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_keyword_list_params(m: re.Match[str]) -> SentenceOutcome:
    """``Flying, first strike, lifelink, protection from Demons and from
    Dragons`` (Baneslayer Angel) and ``Reach, hexproof from blue``
    (Sporeweb Weaver) — keyword lists with one parameterized member, which
    ``_KEYWORDS_BARE_UNBUILDABLE`` marks as not buildable from the bare
    keyword string (PROTECTION and "hexproof from" take a Filter). The
    template emits only that member: the bare members arrive via
    ``raw.keywords`` and the compiler's keyword merge keeps one copy each.
    Baneslayer's filter is the OR of the two subtypes (SUBTYPE_EQ is
    singular); Sporeweb's is COLOR_HAS blue. Scryfall also lists a bare
    'Hexproof' for Sporeweb Weaver, but the bare keyword path builds a
    keyword only if the face prints it (compiler._face_prints_keyword)."""
    if m.group("form").startswith("Flying"):
        return KeywordOutcome(
            keyword=Keyword.PROTECTION,
            params=(
                FOr(
                    children=(
                        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Demon"),
                        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Dragon"),
                    )
                ),
            ),
        )
    return KeywordOutcome(
        keyword=Keyword.HEXPROOF,
        params=(FAtom(pred=FAtomPred.COLOR_HAS, color="U"),),
    )


def _build_if_died_two_tokens(m: re.Match[str]) -> SentenceOutcome:
    """``If a creature died this turn, create two 1/1 green Saproling
    creature tokens.`` (Fungal Rebirth s2) — Conditional over the
    turn-scoped DIED_THIS_TURN atom (checked at resolution, not a
    trigger), then CREATE_TOKEN. The spelled-out ``two`` is outside the
    number regex, so the pattern pins the word and the count is
    ``QConst(2)``."""
    token = TokenSpec(
        name="Saproling",
        type_line="Creature — Saproling",
        types=("Creature",),
        subtypes=("Saproling",),
        power=QConst(1),
        toughness=QConst(1),
        keywords=(),
        abilities=(),
        colors=("G",),
    )
    return EffectOutcome(
        effect=Conditional(
            pred=FAtom(pred=FAtomPred.DIED_THIS_TURN),
            then_effect=Atom(
                verb=Verb.CREATE_TOKEN,
                args=AtomArgs(pairs=(("tokens", token), ("count", QConst(2)))),
            ),
        )
    )


def _build_would_damage_incarnation(m: re.Match[str]) -> SentenceOutcome:
    """``If a source would deal damage to you, prevent that damage and put
    an incarnation counter on this enchantment.`` (Nine Lives) —
    ReplacementAbility over DamageDealtEvent. ``source=None`` is the printed
    universal "a source". The event filter names the damaged object, here
    you: ``FAtom(CONTROLLER_IS, who=YOU)`` (a player is its own controller).
    "prevent that damage" has no atom: the replacement itself replaces the
    damage (PREVENT_EFFECT is the duration-scoped restriction verb, not a
    replacement step), so the action is just PUT_COUNTER(INCARNATION, 1) on
    this enchantment."""
    return AbilityOutcome(
        ability=ReplacementAbility(
            event=DamageDealtEvent(
                amount=QUnbounded(),
                filter=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            ),
            condition=None,
            action=Atom(
                verb=Verb.PUT_COUNTER,
                args=AtomArgs(
                    pairs=(
                        (
                            "target",
                            Selector(
                                QConst(1),
                                SelectorMode.CHOOSE,
                                FAtom(pred=FAtomPred.IS_SOURCE),
                                zones=(Zone(
                                    kind=ZoneKind.BATTLEFIELD,
                                    controller=ControllerRef.ANY,
                                ),),
                            ),
                        ),
                        ("counter_kind", CounterKind.INCARNATION),
                        ("count", QConst(1)),
                    )
                ),
            ),
        )
    )


def _build_flip_won(m: re.Match[str]) -> SentenceOutcome:
    """``If you win the flip, you gain 6 life.`` (Tavern Swindler s2) —
    Conditional gated on FAtomPred.FLIP_WON (who=YOU; "you lose it" would be
    FNot). The compiler appends it to the B5c-flip-cost activation it is
    printed under (compiler._activation_trailing_idx)."""
    return EffectOutcome(
        effect=Conditional(
            pred=FAtom(pred=FAtomPred.FLIP_WON, who=ControllerRef.YOU),
            then_effect=Atom(
                verb=Verb.GAIN_LIFE,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(int(m.group(1)))),
                    )
                ),
            ),
        )
    )


def _build_choice_of_grants(m: re.Match[str]) -> SentenceOutcome:
    """``Target creature gets +1/+1 and gains your choice of deathtouch or
    lifelink until end of turn.`` (Alchemist's Gift) — one spell step,
    Seq(MODIFY_PT, Choose): the Choose is the controller's pick of one of
    the two keyword grants, nothing defaulted. The grant names the spell's
    own target via ``referent="target"``, so no second target is declared."""
    p, t = int(m.group("p")), int(m.group("t"))
    grant_target = Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAnd(children=()),
        zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
        referent="target",
    )
    mod = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                    ),
                ),
                ("power", PtDelta(PtDirection.INCREASE, QConst(p))),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(t))),
                ("duration", DurationEot()),
            )
        ),
    )
    grants = tuple(
        Atom(
            verb=Verb.GRANT_ABILITY,
            args=AtomArgs(
                pairs=(
                    ("target", grant_target),
                    ("ability", KeywordAbility(keyword=kw)),
                    ("duration", DurationEot()),
                )
            ),
        )
        for kw in (Keyword.DEATHTOUCH, Keyword.LIFELINK)
    )
    return EffectOutcome(
        effect=Seq(steps=(mod, Choose(count=QConst(1), options=grants)))
    )


def _build_its_controller_token(m: re.Match[str]) -> SentenceOutcome:
    """``Its controller creates a 4/4 white Angel creature token with
    flying.`` (Angelic Ascension s2) and ``Its controller creates a 1/1
    white Soldier creature token.`` (Secure the Scene s2) — CREATE_TOKEN
    whose ``controller`` role is a ``referent="target"`` selector: ``Its``
    is the spell's exiled target (s1's TARGET selector, in the same
    SpellAbility Seq), and ``role_players`` folds the exiled card to its
    controller at execution."""
    subtype = m.group("st")
    return EffectOutcome(
        effect=Atom(
            verb=Verb.CREATE_TOKEN,
            args=AtomArgs(
                pairs=(
                    (
                        "controller",
                        Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAnd(children=()),
                            zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
                            referent="target",
                        ),
                    ),
                    (
                        "tokens",
                        TokenSpec(
                            name=subtype,
                            type_line=f"Creature — {subtype}",
                            types=("Creature",),
                            subtypes=(subtype,),
                            power=QConst(int(m.group("p"))),
                            toughness=QConst(int(m.group("t"))),
                            keywords=(Keyword.FLYING,) if m.group("fly") else (),
                            abilities=(),
                            colors=("W",),
                        ),
                    ),
                )
            ),
        )
    )


def _build_its_controller_loses_life(m: re.Match[str]) -> SentenceOutcome:
    """``Its controller loses 2 life.`` (Liliana, Death Mage [−3] s2) —
    LOSE_LIFE whose controller role is a ``referent="target"`` selector,
    read as the controller of the selected object (B2b-gloom-sower puts the
    event referent in the same role). ``Its`` is the [−3]'s destroyed
    creature."""
    return EffectOutcome(
        effect=Atom(
            verb=Verb.LOSE_LIFE,
            args=AtomArgs(
                pairs=(
                    (
                        "controller",
                        Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAnd(children=()),
                            zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
                            referent="target",
                        ),
                    ),
                    ("amount", QConst(int(m.group(1)))),
                )
            ),
        )
    )


def _build_if_was_creature_counter_gain(m: re.Match[str]) -> SentenceOutcome:
    """``If it was a creature card, put a +1/+1 counter on this creature and
    you gain 1 life.`` (Scavenging Ooze) — a Conditional on the result
    register, as in _build_if_it_type_then. "was" reads the value at the
    antecedent event; a card's printed type does not change across zones,
    so the register's subject carries it. Then-branch: PUT_COUNTER on the
    Ooze itself, then GAIN_LIFE."""
    counter = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.IS_SOURCE),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                    ),
                ),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                ("count", QConst(1)),
            )
        ),
    )
    gain = Atom(
        verb=Verb.GAIN_LIFE,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(int(m.group("life")))),
            )
        ),
    )
    return EffectOutcome(
        effect=Conditional(
            pred=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            then_effect=Seq(steps=(counter, gain)),
        )
    )


def _build_peer_half_library(m: re.Match[str]) -> SentenceOutcome:
    """``Target player draws cards equal to half the number of cards in
    their library and loses half their life.`` (Peer into the Abyss s1).

    Draw: DRAW controller=TARGET_PLAYER, amount = half the target player's
    library. "their" is the spell's player target, so the count is a QCount
    over Zone(LIBRARY, TARGET_PLAYER), not QProp CARDS_IN_LIBRARY (that
    field is pinned to the ability controller).

    Life loss: ``EachPlayer(TARGET_PLAYER, LOSE_LIFE(YOU, ceil(LIFE / 2)))``.
    A life total is read only through QProp(controller, LIFE), so the step
    rotates the controller to the target player and reads their life, never
    the caster's. The draw step's TARGET_PLAYER reads give the spell its
    player target slot. Printed order: draw, then lose. Both halves round up
    (CR 107.1a; "Round up each time." is s2)."""
    library_count = QCount(
        Selector(
            QUnbounded(),
            SelectorMode.ALL,
            FAnd(children=()),
            zones=(Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.TARGET_PLAYER),),
        )
    )
    half_rounded = QBin(
        op=QBinOp.DIV,
        left=library_count,
        right=QConst(2),
        rounding=Rounding.CEIL,
    )
    draw = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.TARGET_PLAYER),
                ("amount", half_rounded),
            )
        ),
    )
    half_life = QBin(
        op=QBinOp.DIV,
        left=QProp(referent="controller", field=QPropField.LIFE),
        right=QConst(2),
        rounding=Rounding.CEIL,
    )
    lose = EachPlayer(
        ref=ControllerRef.TARGET_PLAYER,
        effect=Atom(
            verb=Verb.LOSE_LIFE,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("amount", half_life),
                )
            ),
        ),
    )
    return EffectOutcome(effect=Seq(steps=(draw, lose)))


def _build_peer_round_up_each_time(m: re.Match[str]) -> SentenceOutcome:
    """``Round up each time.`` (Peer into the Abyss s2) — consumed as a
    RuleReminderOutcome: the rounding is already s1's policy (each DIV in
    _build_peer_half_library carries Rounding.CEIL), so this row adds no
    payload and must not spawn a second draw/lose step."""
    return RuleReminderOutcome(reason="rounding_directive")


def _build_double_counters_on_target(m: re.Match[str]) -> SentenceOutcome:
    """``Put a +1/+1 counter on target creature you control, then double the
    number of +1/+1 counters on that creature.`` (Invigorating Surge) —
    Seq: PUT_COUNTER +1/+1 on the target, then PUT_COUNTER of the target's
    current COUNTER_COUNT (adding the count to itself doubles it); "that
    creature" binds referent="target"."""
    target = _target_creature_you_control()
    put_one = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                ("target", target),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                ("count", QConst(1)),
            )
        ),
    )
    double_up = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
                        referent="target",
                    ),
                ),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                (
                    "count",
                    QProp(referent="target", field=QPropField.COUNTER_COUNT),
                ),
            )
        ),
    )
    return EffectOutcome(effect=Seq(steps=(put_one, double_up)))


def _build_then_if_opponent_more_creatures(m: re.Match[str]) -> SentenceOutcome:
    """``Then if an opponent controls more creatures than you, put a loyalty
    counter on Garruk.`` (Garruk, Unleashed [−2] s2) — the "Then "
    continuation merges into the [−2] ActivatedAbility. Conditional on
    CONTROLLER_COUNT_GT, a two-filter comparison (both required):
    inner_filter counts the creatures an opponent controls,
    right_inner_filter counts yours. "an opponent" is ControllerRef.OPPONENT
    (the executor evaluates each opponent). Then-branch: one LOYALTY
    counter on Garruk, the ability's source."""
    gated = Conditional(
        pred=FAtom(
            pred=FAtomPred.CONTROLLER_COUNT_GT,
            inner_filter=FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT),
                )
            ),
            right_inner_filter=FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                )
            ),
        ),
        then_effect=Atom(
            verb=Verb.PUT_COUNTER,
            args=AtomArgs(
                pairs=(
                    (
                        "target",
                        Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAnd(
                                children=(
                                    FAtom(pred=FAtomPred.IS_SOURCE),
                                    FAtom(
                                        pred=FAtomPred.CONTROLLER_IS,
                                        who=ControllerRef.YOU,
                                    ),
                                )
                            ),
                            zones=(Zone(
                                kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY
                            ),),
                        ),
                    ),
                    ("counter_kind", CounterKind.LOYALTY),
                    ("count", QConst(1)),
                )
            ),
        ),
    )
    return EffectOutcome(effect=gated)


def _build_it_gains_haste_emblem_residue(m: re.Match[str]) -> SentenceOutcome:
    """``It gains haste."`` (Liliana, Waker of the Dead): sentence-splitter
    residue, the second sentence of the [−7]'s quoted emblem text.

    Consumed as a RuleReminderOutcome: the haste grant is already compiled
    inside the attached emblem by ``B5b-it-gains-haste``, so granting it at
    the planeswalker's card level would duplicate it outside the emblem."""
    return RuleReminderOutcome(reason="emblem_text_payload_attached")


def _build_spend_this_mana_is_or_sorcery(m: re.Match[str]) -> SentenceOutcome:
    """``Spend this mana only to cast an instant or sorcery spell.``
    (Vodalian Arcanist) — Verb.MANA_POLICY with scope "THIS_MANA" (the
    executor binds it to the mana this card's own ``{T}: Add {C}`` adds)
    and filter FOr(Instant, Sorcery). A restriction ("only to"), not a
    permission, so there is no OptionalEffect."""
    instant_or_sorcery = FOr(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Instant"),
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Sorcery"),
        )
    )
    atom = Atom(
        verb=Verb.MANA_POLICY,
        args=AtomArgs(pairs=(("scope", "THIS_MANA"), ("filter", instant_or_sorcery))),
    )
    return AbilityOutcome(ability=StaticAbility(effect=atom))


def _build_play_top_revealed(m: re.Match[str]) -> SentenceOutcome:
    """``Play with the top card of your library revealed.`` (Conspicuous
    Snoop) — a StaticAbility of REVEAL(controller=YOU, count=QConst(1),
    duration=DurationPermanent). The library top is implicit, as for
    LOOK_AT (no zone role); the count is how many cards stay face up."""
    atom = Atom(
        verb=Verb.REVEAL,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("count", QConst(1)),
                ("duration", DurationPermanent()),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(effect=atom))


def _build_sanctum_all_extra_trigger(m: re.Match[str]) -> SentenceOutcome:
    """``If an ability of another Shrine you control triggers while you
    control six or more Shrines, that ability triggers an additional
    time.`` (Sanctum of All s2) — an AbilityTriggerEvent over the triggering
    ability's source: SUBTYPE_EQ Shrine + CONTROLLER_IS YOU + FNot(IS_SOURCE)
    for "another". "while you control six or more Shrines" (CONTROLLER_COUNT_GE)
    is part of that event, read as the Shrine's ability triggers: it is in the
    event's filter, not the condition, which only an intervening "if" is (CR
    603.4). The effect is TRIGGER_ADDITIONAL with its count axis, QConst(1) for
    "an additional time"."""
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=AbilityTriggerEvent(
                filter=FAnd(
                    children=(
                        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Shrine"),
                        FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                        FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
                        FAtom(
                            pred=FAtomPred.CONTROLLER_COUNT_GE,
                            count=QConst(6),
                            inner_filter=FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Shrine"),
                        ),
                    )
                )
            ),
            condition=None,
            effect=Atom(
                verb=Verb.TRIGGER_ADDITIONAL,
                args=AtomArgs(pairs=(("count", QConst(1)),)),
            ),
        )
    )


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------


TEMPLATES: tuple[Template, ...] = (
    Template(
        tid="B5b-flash",
        name="flash keyword rule-reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Flash \(You may cast this spell any time you could cast "
            r"an instant\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_flash,
    ),
    Template(
        tid="B5b-haste",
        name="haste keyword rule-reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Haste \(This creature can attack and \{T\} as soon as it "
            r"comes under your control\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_haste,
    ),
    Template(
        tid="B5b-hexproof",
        name="hexproof keyword rule-reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Hexproof \(This creature can't be the target of spells or "
            r"abilities your opponents control\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_hexproof,
    ),
    Template(
        tid="B5b-token-demon",
        name="if you do, create a N/N black Demon token with flying",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If you do, create a (\d+)/(\d+) black Demon creature "
            r"token with flying\.$"
        ),
        priority=_PRIORITY,
        build=_build_token_demon,
    ),
    Template(
        tid="B5b-token-zombie",
        name="if you do, create a N/N black Zombie token",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If you do, create a (\d+)/(\d+) black Zombie creature "
            r"token\.$"
        ),
        priority=_PRIORITY,
        build=_build_token_zombie,
    ),
    Template(
        tid="B5b-cont-discard",
        name="if you do, discard a card",
        bucket=_BUCKET,
        pattern=re.compile(r"^If you do, discard a card\.$"),
        priority=_PRIORITY,
        build=_build_cont_discard,
    ),
    Template(
        tid="B5b-cont-draw",
        name="if you do, draw a card",
        bucket=_BUCKET,
        pattern=re.compile(r"^If you do, draw a card\.$"),
        priority=_PRIORITY,
        build=_build_cont_draw,
    ),
    Template(
        tid="B5b-seq-modpt-trample",
        name="if you do, this creature gets +N/+N and gains trample until eot",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If you do, this creature gets \+(\d+)/\+(\d+) and gains "
            r"trample until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_seq_modpt_trample,
    ),
    Template(
        tid="B5b-cont-gain-4",
        name="if you do, you gain N life",
        bucket=_BUCKET,
        pattern=re.compile(r"^If you do, you gain (\d+) life\.$"),
        priority=_PRIORITY,
        build=_build_cont_gain_4,
    ),
    Template(
        tid="B5b-cont-gain-mv",
        name="if you do, you gain life equal to that creature's mana value",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If you do, you gain life equal to that creature's mana "
            r"value\.$"
        ),
        priority=_PRIORITY,
        build=_build_cont_gain_mv,
    ),
    Template(
        tid="B5b-lifelink",
        name="lifelink keyword rule-reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Lifelink \(Damage dealt by this creature also causes you "
            r"to gain that much life\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_lifelink,
    ),
    Template(
        tid="B5b-look-3",
        name="look at the top three cards of your library",
        bucket=_BUCKET,
        pattern=re.compile(r"^Look at the top three cards of your library\.$"),
        priority=_PRIORITY,
        build=_build_look_3,
    ),
    Template(
        tid="B5b-menace",
        name="menace keyword rule-reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Menace \(This creature can't be blocked except by two or "
            r"more creatures\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_menace,
    ),
    Template(
        tid="B5b-perm-hex-ind",
        name="permanents you control gain hexproof and indestructible until eot",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Permanents you control gain hexproof and indestructible "
            r"until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_perm_hex_ind,
    ),
    Template(
        tid="B5b-prowess",
        name="prowess keyword rule-reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Prowess \(Whenever you cast a noncreature spell, this "
            r"creature gets \+\d+/\+\d+ until end of turn\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_prowess,
    ),
    Template(
        tid="B5b-put-counter",
        name="put a +N/+N counter on <target>",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Put a \+(\d+)/\+(\d+) counter on "
            r"(each creature you control|each of up to two target creatures"
            r"|target creature you control)\.$"
        ),
        priority=_PRIORITY,
        build=_build_put_counter,
    ),
    Template(
        tid="B5b-reach",
        name="reach keyword rule-reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Reach \(This creature can block creatures with flying\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_reach,
    ),
    Template(
        tid="B5b-return-creatures-battlefield",
        name="return target creature card from graveyard to battlefield",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Return target creature card from your graveyard to the "
            r"battlefield\.$"
        ),
        priority=_PRIORITY,
        build=_build_return_creatures_battlefield,
    ),
    Template(
        tid="B5b-return-cards-hand",
        name="return <cards> from graveyard to hand",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Return (target permanent card|target card|up to two target creature cards) "
            r"from your graveyard to your hand\.$"
        ),
        priority=_PRIORITY,
        build=_build_return_cards_hand,
    ),
    Template(
        tid="B5b-sacr-grant",
        name="sacrifice this creature: another target creature you control gains indestructible until eot",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Sacrifice this creature: Another target creature you "
            r"control gains indestructible until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_sacr_grant,
    ),
    Template(
        tid="B5b-named-damage",
        name="<card> deals N damage to target creature or planeswalker",
        bucket=_BUCKET,
        # The subject never spans a colon: "<cost>: ... deals N damage" is an
        # activated ability (CR 602.1), never this spell effect (Elite
        # Headhunter, Chandra, Bold Pyromancer's [−3]).
        pattern=re.compile(
            r"^([^:]+) deals (\d+) damage to target creature or "
            r"planeswalker\.$"
        ),
        priority=_PRIORITY,
        build=_build_named_damage,
    ),
    Template(
        tid="B5b-scr-reveal",
        name="scry N, then reveal the top card of your library",
        bucket=_BUCKET,
        pattern=re.compile(r"^Scry (\d+), then reveal the top card of your library\.$"),
        priority=_PRIORITY,
        build=_build_scr_reveal,
    ),
    Template(
        tid="B5b-scr",
        name="scry N",
        bucket=_BUCKET,
        pattern=re.compile(r"^Scry (\d+)\.$"),
        priority=_PRIORITY,
        build=_build_scr,
    ),
    Template(
        tid="B5b-search-shuffle",
        name="search library for a card, put into hand, then shuffle",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Search your library for a card, put that card into your "
            r"hand, then shuffle\.$"
        ),
        priority=_PRIORITY,
        build=_build_search_shuffle,
    ),
    Template(
        tid="B5b-damage-any",
        name="shock deals N damage to any target",
        bucket=_BUCKET,
        pattern=re.compile(r"^Shock deals (\d+) damage to any target\.$"),
        priority=_PRIORITY,
        build=_build_damage_any,
    ),
    Template(
        tid="B5b-tap-spirits",
        name="tap two untapped spirits you control: tap target creature you don't control",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Tap two untapped Spirits you control: Tap target creature "
            r"you don't control\.$"
        ),
        priority=_PRIORITY,
        build=_build_tap_spirits,
    ),
    Template(
        tid="B5b-tap-2-target",
        name="tap up to two target creatures",
        bucket=_BUCKET,
        pattern=re.compile(r"^Tap up to two target creatures\.$"),
        priority=_PRIORITY,
        build=_build_tap_2_target,
    ),
    Template(
        tid="B5b-seq-modpt-firststrike",
        name="target creature gets +N/+N and gains first strike until eot",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Target creature gets \+(\d+)/\+(\d+) and gains first "
            r"strike until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_seq_modpt_firststrike,
    ),
    Template(
        tid="B5b-modpt-plus",
        name="target creature gets +N/+N until eot",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Target creature gets \+(\d+)/\+(\d+) until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_modpt_plus,
    ),
    Template(
        tid="B5b-modpt-minus",
        name="target creature gets -N/-N until eot",
        bucket=_BUCKET,
        pattern=re.compile(r"^Target creature gets -(\d+)/-(\d+) until end of turn\.$"),
        priority=_PRIORITY,
        build=_build_modpt_minus,
    ),
    Template(
        tid="B5b-seq-modpt-hexproof",
        name="target creature you control gets +N/+N and gains hexproof until eot",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Target creature you control gets \+(\d+)/\+(\d+) and gains "
            r"hexproof until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_seq_modpt_hexproof,
    ),
    Template(
        tid="B5b-modpt-x",
        name="target creature you control gets +X/+X until eot",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Target creature you control gets \+X/\+X until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_modpt_x,
    ),
    Template(
        tid="B5b-reveal-hand",
        name="target opponent reveals their hand",
        bucket=_BUCKET,
        pattern=re.compile(r"^Target opponent reveals their hand\.$"),
        priority=_PRIORITY,
        build=_build_reveal_hand,
    ),
    Template(
        tid="B5b-sacr-flying",
        name="target opponent sacrifices a creature of their choice with flying",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Target opponent sacrifices a creature of their choice "
            r"with flying\.$"
        ),
        priority=_PRIORITY,
        build=_build_sacr_flying,
    ),
    Template(
        tid="B5b-discard-target-2",
        name="target player discards two cards",
        bucket=_BUCKET,
        pattern=re.compile(r"^Target player discards two cards\.$"),
        priority=_PRIORITY,
        build=_build_discard_target_2,
    ),
    Template(
        tid="B5b-noncreature-cost-more",
        name="noncreature spells cost {N} more to cast",
        bucket=_BUCKET,
        pattern=re.compile(r"^Noncreature spells cost \{(\d+)\} more to cast\.$"),
        priority=_PRIORITY,
        build=_build_noncreature_cost_modifier,
    ),
    Template(
        tid="B5b-return-spell-creature-owner-hand",
        name="return target spell or creature to its owner's hand",
        bucket=_BUCKET,
        pattern=re.compile(r"^Return target spell or creature to its owner's hand\.$"),
        priority=_PRIORITY,
        build=_build_return_spell_creature_owner_hand,
    ),
    Template(
        tid="B5b-repl-died-gain-life",
        name="if a creature died this turn, you gain N life instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If a creature died this turn, you gain (\d+) life instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_repl_died_gain_life,
    ),
    Template(
        tid="B5b-repl-nontoken-enter-exile",
        name="if a nontoken creature would enter and it wasn't cast, exile it instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If a nontoken creature would enter and it wasn't cast, "
            r"exile it instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_repl_nontoken_enter_exile,
    ),
    Template(
        tid="B5b-repl-triple-damage",
        name="a source you control deals triple damage instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If a source you control would deal damage to a permanent or "
            r"player, it deals triple that damage to that permanent or "
            r"player instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_repl_triple_damage,
    ),
    Template(
        tid="B5b-repl-counter-plus-one",
        name="that many plus one +1/+1 counters are put instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If one or more \+1/\+1 counters would be put on a creature "
            r"you control, that many plus one \+1/\+1 counters are put on "
            r"that creature instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_repl_counter_plus_one,
    ),
    Template(
        tid="B5b-repl-die-exile",
        name="if that creature or planeswalker would die this turn, exile it instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If that creature or planeswalker would die this turn, "
            r"exile it instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_repl_die_exile,
    ),
    Template(
        tid="B5b-repl-graveyard-exile",
        name="if that spell would be put into your graveyard, exile it instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If that spell would be put into your graveyard, "
            r"exile it instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_repl_graveyard_exile,
    ),
    Template(
        tid="B5b-counter-unless-pays",
        name="counter that spell unless its controller pays {N} instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If you control a creature with flying, counter that spell "
            r"unless its controller pays \{(\d+)\} instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_counter_unless_pays,
    ),
    Template(
        tid="B5b-repl-draw-not-first",
        name="if you would draw a card except the first this step, draw two instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If you would draw a card except the first one you draw in "
            r"each of your draw steps, draw two cards instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_repl_draw_not_first,
    ),
    Template(
        tid="B5b-gadrak-cant-attack-unless-artifacts",
        name="Gadrak can't attack unless you control four or more artifacts",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Gadrak can't attack unless you control four or more "
            r"artifacts\.$"
        ),
        priority=_PRIORITY,
        build=_build_cant_attack_unless_artifacts,
    ),
    Template(
        tid="B5b-set-pt-power-gy-instant-sorcery",
        name="named creature's power equals instant+sorcery count in your graveyard",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Kinetic Augur's power is equal to the number of instant and "
            r"sorcery cards in your graveyard\.$"
        ),
        priority=_PRIORITY,
        build=_build_set_pt_power_gy_count,
    ),
    Template(
        tid="B5b-it-gains-kw-eot",
        name="it gains <kw> until end of turn (result-referent grant)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^It gains (?P<kw>indestructible|haste|vigilance) "
            r"until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_it_gains_kw_eot,
    ),
    Template(
        tid="B5b-it-gains-haste",
        name="it gains haste (permanent result-referent grant)",
        bucket=_BUCKET,
        pattern=re.compile(r"^It gains haste\.$"),
        priority=_PRIORITY,
        build=_build_it_gains_haste,
    ),
    Template(
        tid="B5b-it-gains-protection-choice",
        name="it gains protection from the color of your choice (Choose 1-of-5)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^It gains protection from the color of your choice "
            r"until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_it_gains_protection_choice,
    ),
    Template(
        tid="B5b-that-player-discards",
        name="that player discards that card (result-referent discard)",
        bucket=_BUCKET,
        pattern=re.compile(r"^That player discards that card\.$"),
        priority=_PRIORITY,
        build=_build_that_player_discards_that_card,
    ),
    Template(
        tid="B5b-if-it-type-then",
        name="if it's a creature [or land] card, <then> (result Conditional)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If it's a creature(?P<or_land> or land)? card, "
            r"(?P<then>put it into your hand|draw a card)\.$"
        ),
        priority=_PRIORITY,
        build=_build_if_it_type_then,
    ),
    Template(
        tid="B5b-otherwise-bottom",
        name="otherwise put it on the bottom of your library (else_effect)",
        bucket=_BUCKET,
        pattern=re.compile(r"^Otherwise, put it on the bottom of your library\.$"),
        priority=_PRIORITY,
        build=_build_otherwise_bottom,
    ),
    Template(
        tid="B5b-search-name-exile",
        name="search target opponent's zones for any number with that name, exile",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Search target opponent's graveyard, hand, and library for "
            r"any number of cards with that name and exile them\.$"
        ),
        priority=_PRIORITY,
        build=_build_search_name_exile,
    ),
    Template(
        tid="B5b-token-per-exiled-this-way",
        name="that player shuffles, then creates a Zombie token per this-way exile",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^That player shuffles, then creates a (?P<p>\d+)/(?P<t>\d+) "
            r"black Zombie creature token for each card exiled from their "
            r"hand this way\.$"
        ),
        priority=_PRIORITY,
        build=_build_shuffle_then_token_per_exiled,
    ),
    Template(
        tid="B5b-loses-kw-eot",
        name="that permanent loses <kw> until end of turn (LOSE_ABILITY)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^That permanent loses (?P<kw>indestructible) until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_that_permanent_loses_kw,
    ),
    Template(
        tid="B5b-one-of-other",
        name="put one of them into your hand and the other into your graveyard",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Put one of them into your hand and the other into your "
            r"graveyard\.$"
        ),
        priority=_PRIORITY,
        build=_build_one_of_other,
    ),
    Template(
        tid="B5b-one-of-rest-bottom",
        name="put one of those cards into your hand and the rest on bottom",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Put one of those cards into your hand and the rest on the "
            r"bottom of your library in any order\.$"
        ),
        priority=_PRIORITY,
        build=_build_one_of_rest_bottom,
    ),
    Template(
        tid="B5b-rest-bottom-random",
        name="put the rest on the bottom of your library in a random order",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Put the rest on the bottom of your library in a random order\.$"
        ),
        priority=_PRIORITY,
        build=_build_rest_bottom_random,
    ),
    Template(
        tid="B5b-search-one-other-shuffle",
        name="search up to two basic lands, one tapped to BF, other to hand, shuffle",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Search your library for up to two basic land cards, reveal "
            r"those cards, put one onto the battlefield tapped and the other "
            r"into your hand, then shuffle\.$"
        ),
        priority=_PRIORITY,
        build=_build_cultivate_search,
    ),
    Template(
        tid="B5b-cast-elsewhere-instead",
        name="if cast from anywhere other than your hand, those cards to hand instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If this spell was cast from anywhere other than your hand, "
            r"put each of those cards into your hand instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_cast_elsewhere_instead,
    ),
    Template(
        tid="B5b-gain-control-eot",
        name="gain control of target creature until end of turn",
        bucket=_BUCKET,
        pattern=re.compile(r"^Gain control of target creature until end of turn\.$"),
        priority=_PRIORITY,
        build=_build_gain_control_eot,
    ),
    Template(
        tid="B5b-keyword-list-params",
        name="keyword list with parameterized PROTECTION/HEXPROOF member",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^(?P<form>Flying, first strike, lifelink, protection from "
            r"Demons and from Dragons|Reach, hexproof from blue)$"
        ),
        priority=_PRIORITY,
        build=_build_keyword_list_params,
    ),
    Template(
        tid="B5b-if-died-two-tokens",
        name="if a creature died this turn, create two Saproling tokens",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If a creature died this turn, create two 1/1 green Saproling "
            r"creature tokens\.$"
        ),
        priority=_PRIORITY,
        build=_build_if_died_two_tokens,
    ),
    Template(
        tid="B5b-would-damage-incarnation",
        name="would-deal-damage replacement: put an incarnation counter (Nine Lives)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If a source would deal damage to you, prevent that damage and "
            r"put an incarnation counter on this enchantment\.$"
        ),
        priority=_PRIORITY,
        build=_build_would_damage_incarnation,
    ),
    Template(
        tid="B5b-flip-won",
        name="if you win the flip, you gain N life (FLIP_WON Conditional)",
        bucket=_BUCKET,
        pattern=re.compile(r"^If you win the flip, you gain (\d+) life\.$"),
        priority=_PRIORITY,
        build=_build_flip_won,
    ),
    Template(
        tid="B5b-choice-of-grants",
        name="gets +N/+N and gains your choice of two keywords (Choose 1-of-2)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Target creature gets \+(?P<p>\d+)/\+(?P<t>\d+) and gains your "
            r"choice of deathtouch or lifelink until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_choice_of_grants,
    ),
    Template(
        tid="B5b-its-controller-token",
        name="its controller creates a white Angel/Soldier token (controller referent)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Its controller creates a (?P<p>\d+)/(?P<t>\d+) white "
            r"(?P<st>Angel|Soldier) creature token(?P<fly> with flying)?\.$"
        ),
        priority=_PRIORITY,
        build=_build_its_controller_token,
    ),
    Template(
        tid="B5b-its-controller-loses-life",
        name="its controller loses N life (referent-target controller role)",
        bucket=_BUCKET,
        pattern=re.compile(r"^Its controller loses (\d+) life\.$"),
        priority=_PRIORITY,
        build=_build_its_controller_loses_life,
    ),
    Template(
        tid="B5b-if-was-creature-counter-gain",
        name="if it was a creature card, counter + gain life (C18 result TYPE_EQ)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If it was a creature card, put a \+\d+/\+\d+ counter on this "
            r"creature and you gain (?P<life>\d+) life\.$"
        ),
        priority=_PRIORITY,
        build=_build_if_was_creature_counter_gain,
    ),
    Template(
        tid="B5b-peer-half-library",
        name="target player draws round-up half their library, loses round-up half their life (Peer)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Target player draws cards equal to half the number of cards "
            r"in their library and loses half their life\.$"
        ),
        priority=_PRIORITY,
        build=_build_peer_half_library,
    ),
    Template(
        tid="B5b-peer-round-up-each-time",
        name="round up each time (rounding directive consumed by s1 (n+1)//2)",
        bucket=_BUCKET,
        pattern=re.compile(r"^Round up each time\.$"),
        priority=_PRIORITY,
        build=_build_peer_round_up_each_time,
    ),
    Template(
        tid="B5b-double-counters-target",
        name="counter target, then double its counters (COUNTER_COUNT referent-target)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Put a \+\d+/\+\d+ counter on target creature you control, "
            r"then double the number of \+\d+/\+\d+ counters on that "
            r"creature\.$"
        ),
        priority=_PRIORITY,
        build=_build_double_counters_on_target,
    ),
    Template(
        tid="B5b-then-if-opponent-more-creatures",
        name="then if an opponent controls more creatures than you, loyalty counter (CONTROLLER_COUNT_GT)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Then if an opponent controls more creatures than you, put a "
            r"loyalty counter on Garruk\.$"
        ),
        priority=_PRIORITY,
        build=_build_then_if_opponent_more_creatures,
    ),
    Template(
        tid="B5b-gains-haste-emblem-residue",
        name='it gains haste." (emblem-quote residue marker, C19)',
        bucket=_BUCKET,
        pattern=re.compile(r'^It gains haste\."$'),
        priority=_PRIORITY,
        build=_build_it_gains_haste_emblem_residue,
    ),
    Template(
        tid="B5b-spend-this-mana-is-or-sorcery",
        name="mana policy: THIS_MANA anchored to instant/sorcery casts (MANA_POLICY, C21)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Spend this mana only to cast an instant or sorcery spell\.$"
        ),
        priority=_PRIORITY,
        build=_build_spend_this_mana_is_or_sorcery,
    ),
    Template(
        tid="B5b-play-top-revealed",
        name="continuous revealed top card (REVEAL + DurationPermanent, R9-8)",
        bucket=_BUCKET,
        pattern=re.compile(r"^Play with the top card of your library revealed\.$"),
        priority=_PRIORITY,
        build=_build_play_top_revealed,
    ),
    Template(
        tid="B5b-transmogrify-reveal-creature",
        name="that creature's controller reveals until a creature card (REVEAL until)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^That creature's controller reveals cards from the top of their "
            r"library until they reveal a creature card\.$"
        ),
        priority=_PRIORITY,
        build=_build_transmog_reveal_creature,
    ),
    Template(
        tid="B5b-transmogrify-shuffle-rest",
        name="that player puts that card onto the battlefield, shuffles the rest (EachPlayer)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^That player puts that card onto the battlefield, then shuffles "
            r"the rest into their library\.$"
        ),
        priority=_PRIORITY,
        build=_build_transmog_shuffle_rest,
    ),
    Template(
        tid="B5b-sanctum-all-extra-trigger",
        name="Sanctum-of-All extra-trigger (AbilityTriggerEvent + TRIGGER_ADDITIONAL, T5-D)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If an ability of another Shrine you control triggers while "
            r"you control six or more Shrines, that ability triggers an "
            r"additional time\.$"
        ),
        priority=_PRIORITY,
        build=_build_sanctum_all_extra_trigger,
    ),
)
