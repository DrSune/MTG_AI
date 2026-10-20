"""Tests for the typed ability-tree grammar (MTG_bot/core/ability_tree.py).

Covers the task's required suite:

- round-trip to_dict / from_dict / canonical_json / fingerprint for every
  node type (parametrized over a full node catalogue);
- canonical_json determinism across different construction orders;
- fingerprint sensitivity to any leaf change;
- walk() visiting every node exactly once on a nested sample;
- immutability (FrozenInstanceError);
- __post_init__ validation failures (negative QConst, empty Seq, bad
  zone/controller, bad predicate args, bad quantity in arithmetic, ...);
- full synthetic CardRecords: a Tarmogoyf-like creature (SET_PT with
  QCount over a Selector across all graveyards, subtype filter), a
  planeswalker with loyalty + emblem, and a token creator (CREATE_TOKEN
  with TokenSpec) — each builds, serializes, round-trips, and fingerprints
  stably.
"""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError

import pytest

import MTG_bot.core.ability_tree as at

# Valid oracle ids (36-char UUID shape — see core/identity.py).
_OID1 = "01020304-0506-4708-890a-0b0c0d0e0f10"
_OID2 = "11111111-2222-4333-8444-555555555555"
_OID2B = "21212121-3232-4444-8555-666666666666"
_OID3 = "31313131-4242-4555-8666-777777777777"

_BF_YOU = at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU)
_BF_ANY = at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.ANY)


def _src_sel() -> at.Selector:
    """The classic "this permanent" selector."""
    return at.Selector(
        at.QConst(1),
        at.SelectorMode.ALL,
        at.FAtom(at.FAtomPred.IS_SOURCE),
        zones=(_BF_YOU,),
    )


def _simple_card(name: str = "Simple Land") -> at.CardRecord:
    return at.CardRecord(
        oracle_id=_OID1,
        name=name,
        type_line="Basic Land — Plains",
        types=("Basic", "Land"),
        subtypes=("Plains",),
        supertypes=("Basic",),
        colors=(),
        color_identity=frozenset(),
        mana_cost=None,
        mana_value=0,
        power=None,
        toughness=None,
        loyalty=None,
        keywords=(),
        abilities=(),
        is_token=False,
    )


def _tarmogoyf_like(subtype: str = "Bird") -> at.CardRecord:
    """A Tarmogoyf-class creature: SET_PT where both components are
    QCount over a Selector spanning ALL graveyards (ControllerRef.ANY),
    filtered on a subtype."""
    grave = at.Zone(at.ZoneKind.GRAVEYARD, at.ControllerRef.ANY)
    count_sel = at.Selector(
        at.QConst(1),
        at.SelectorMode.ALL,
        at.FAtom(at.FAtomPred.SUBTYPE_EQ, string_value=subtype),
        zones=(grave,),
    )
    set_pt = at.Atom(
        at.Verb.SET_PT,
        at.AtomArgs(
            pairs=(
                ("target", _src_sel()),
                ("power", at.QCount(count_sel)),
                ("toughness", at.QCount(count_sel)),
            )
        ),
    )
    return at.CardRecord(
        oracle_id=_OID1,
        name="Synthetic Tarmogoyf",
        type_line="Creature — Beast",
        types=("Creature",),
        subtypes=("Beast",),
        supertypes=(),
        colors=("G",),
        color_identity=frozenset({"G"}),
        mana_cost=at.Cost(
            parts=(
                at.CostManaGeneric(at.QConst(2)),
                at.CostManaGeneric(at.QConst(1)),
                at.CostManaGeneric(at.QConst(1)),
                at.CostManaColor("G", at.QConst(1)),
            )
        ),
        mana_value=5,
        power=None,  # dynamic P/T — see the SET_PT ability
        toughness=None,
        loyalty=None,
        keywords=(),
        abilities=(at.SpellAbility(at.SpellKind.CREATURE, set_pt),),
        is_token=False,
    )


def _emblem_record() -> at.CardRecord:
    search = at.Atom(
        at.Verb.SEARCH,
        at.AtomArgs(
            pairs=(
                (
                    "cards",
                    at.Selector(
                        at.QConst(1),
                        at.SelectorMode.CHOOSE,
                        at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature"),
                        zones=(at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.YOU),),
                    ),
                ),
                ("destination", at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU)),
            )
        ),
    )
    shuffle = at.Atom(
        at.Verb.SHUFFLE,
        at.AtomArgs(
            pairs=(("zone", at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.YOU)),)
        ),
    )
    return at.CardRecord(
        oracle_id=_OID2B,
        name="Garruk, Unleashed Emblem",
        type_line="Emblem",
        types=("Emblem",),
        subtypes=(),
        supertypes=(),
        colors=(),
        color_identity=frozenset(),
        mana_cost=None,
        mana_value=0,
        power=None,
        toughness=None,
        loyalty=None,
        keywords=(),
        abilities=(
            at.TriggeredAbility(
                at.TurnPhaseEvent(
                    at.Phase.END_TURN,
                    at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
                ),
                None,
                at.OptionalEffect(at.Seq((search, shuffle))),
            ),
        ),
        is_token=True,
    )


def _pw_with_emblem() -> at.CardRecord:
    """A planeswalker: loyalty, two loyalty-cost activated abilities, and
    the emblem embedded as a nested CardRecord."""
    beast = at.TokenSpec(
        name="Beast",
        type_line="Token Creature — Beast",
        types=("Creature",),
        subtypes=("Beast",),
        power=at.QConst(3),
        toughness=at.QConst(3),
        keywords=(),
        abilities=(),
    )
    create = at.Atom(
        at.Verb.CREATE_TOKEN,
        at.AtomArgs(pairs=(("tokens", beast), ("count", at.QConst(1)))),
    )
    put = at.Atom(
        at.Verb.PUT_COUNTER,
        at.AtomArgs(
            pairs=(
                (
                    "target",
                    at.Selector(
                        at.QConst(1),
                        at.SelectorMode.ALL,
                        at.FAtom(at.FAtomPred.NAME_EQ, string_value="Synthetic Garruk"),
                        zones=(_BF_YOU,),
                    ),
                ),
                ("counter_kind", at.CounterKind.LOYALTY),
                ("count", at.QConst(1)),
            )
        ),
    )
    return at.CardRecord(
        oracle_id=_OID2,
        name="Synthetic Garruk",
        type_line="Legendary Planeswalker — Garruk",
        types=("Creature", "Planeswalker", "Garruk"),
        subtypes=("Garruk",),
        supertypes=("Legendary",),
        colors=("G",),
        color_identity=frozenset({"G"}),
        mana_cost=None,
        mana_value=0,
        power=None,
        toughness=None,
        loyalty=4,
        keywords=(),
        abilities=(
            at.ActivatedAbility(at.Cost(parts=(at.CostLoyalty(1),)), create),
            at.ActivatedAbility(at.Cost(parts=(at.CostLoyalty(-2),)), put),
        ),
        is_token=False,
        emblem=_emblem_record(),
    )


def _token_creator() -> at.CardRecord:
    """A Gadrak-class creature: at the beginning of its end step, if it
    controls 4+ artifacts, create a Treasure token for each nontoken
    creature that died this turn. CREATE_TOKEN takes a TokenSpec, never a
    string."""
    treasure = at.TokenSpec(
        name="Treasure",
        type_line="Token Artifact — Treasure",
        types=("Artifact",),
        subtypes=("Treasure",),
        power=None,
        toughness=None,
        keywords=(at.Keyword.TREASURE,),
        abilities=(
            at.ActivatedAbility(
                at.Cost(
                    parts=(
                        at.CostTap(),
                        at.CostSacrifice(
                            at.Selector(
                                at.QConst(1),
                                at.SelectorMode.ALL,
                                at.FAtom(at.FAtomPred.IS_SOURCE),
                                zones=(_BF_YOU,),
                            )
                        ),
                    )
                ),
                at.Atom(
                    at.Verb.ADD_MANA,
                    at.AtomArgs(
                        pairs=(
                            ("controller", at.ControllerRef.YOU),
                            ("amount", at.QConst(1)),
                            ("color", "C"),
                        )
                    ),
                ),
            ),
        ),
    )
    died = at.FAnd(
        (
            at.FAtom(at.FAtomPred.DIED_THIS_TURN),
            at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature"),
            at.FNot(at.FAtom(at.FAtomPred.IS_TOKEN)),
        )
    )
    count_sel = at.Selector(
        at.QConst(1),
        at.SelectorMode.ALL,
        died,
        zones=(at.Zone(at.ZoneKind.GRAVEYARD, at.ControllerRef.YOU),),
    )
    condition = at.FAtom(
        at.FAtomPred.CONTROLLER_COUNT_GE,
        inner_filter=at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Artifact"),
        count=at.QConst(4),
    )
    trigger = at.TriggeredAbility(
        at.TurnPhaseEvent(
            at.Phase.END_TURN,
            at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
        ),
        condition,
        at.Atom(
            at.Verb.CREATE_TOKEN,
            at.AtomArgs(pairs=(("tokens", treasure), ("count", at.QCount(count_sel)))),
        ),
    )
    cant_attack = at.StaticAbility(
        at.Atom(
            at.Verb.PREVENT_EFFECT,
            at.AtomArgs(
                pairs=(
                    ("condition", at.FAtom(at.FAtomPred.IS_SOURCE)),
                    (
                        "event",
                        at.DeclareAttackersEvent(at.FAtom(at.FAtomPred.IS_SOURCE)),
                    ),
                )
            ),
        )
    )
    return at.CardRecord(
        oracle_id=_OID3,
        name="Synthetic Gadrak",
        type_line="Legendary Creature — Dragon",
        types=("Creature",),
        subtypes=("Dragon",),
        supertypes=("Legendary",),
        colors=("B",),
        color_identity=frozenset({"B"}),
        mana_cost=at.Cost(
            parts=(
                at.CostManaGeneric(at.QConst(3)),
                at.CostManaGeneric(at.QConst(2)),
                at.CostManaColor("B", at.QConst(2)),
            )
        ),
        mana_value=7,
        power=at.QConst(5),
        toughness=at.QConst(4),
        loyalty=None,
        keywords=(at.KeywordAbility(at.Keyword.FLYING, ()),),
        abilities=(trigger, cant_attack),
        is_token=False,
    )


def _walk_sample() -> at.CardRecord:
    """A small nested card for the walk() tests. No node is shared between
    two slots, so "every node exactly once" is checkable by identity."""

    def draw_atom() -> at.Atom:
        return at.Atom(
            at.Verb.DRAW,
            at.AtomArgs(
                pairs=(
                    ("controller", at.ControllerRef.YOU),
                    (
                        "amount",
                        at.QCount(
                            at.Selector(
                                at.QConst(1),
                                at.SelectorMode.CHOOSE,
                                at.FAnd(
                                    (
                                        at.FAtom(at.FAtomPred.IS_PERMANENT),
                                        at.FNot(at.FAtom(at.FAtomPred.IS_TAPPED)),
                                    )
                                ),
                                zones=(
                                    at.Zone(
                                        at.ZoneKind.BATTLEFIELD, at.ControllerRef.ANY
                                    ),
                                ),
                            )
                        ),
                    ),
                )
            ),
        )

    return at.CardRecord(
        oracle_id=_OID1,
        name="Walk Sample",
        type_line="Creature — Cat",
        types=("Creature",),
        subtypes=("Cat",),
        supertypes=(),
        colors=("W",),
        color_identity=frozenset({"W"}),
        mana_cost=at.Cost(parts=(at.CostManaColor("W", at.QConst(1)),)),
        mana_value=1,
        power=at.QConst(1),
        toughness=at.QConst(1),
        loyalty=None,
        keywords=(at.KeywordAbility(at.Keyword.DEFENDER, ()),),
        abilities=(
            at.StaticAbility(at.Seq((draw_atom(), at.OptionalEffect(draw_atom())))),
        ),
        is_token=False,
    )


# ---------------------------------------------------------------------------
# The full node catalogue — one representative instance of every node type.
# ---------------------------------------------------------------------------


def _all_nodes() -> list[tuple[str, object]]:
    src = _src_sel()
    lib = at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.YOU)
    tap = at.Atom(at.Verb.TAP, at.AtomArgs(pairs=(("target", src),)))
    untap = at.Atom(at.Verb.UNTAP, at.AtomArgs(pairs=(("target", src),)))
    mill = at.Atom(
        at.Verb.MILL,
        at.AtomArgs(
            pairs=(("controller", at.ControllerRef.YOU), ("amount", at.QConst(4)))
        ),
    )
    nodes: list[tuple[str, object]] = [
        # quantities — all six variants
        ("QConst", at.QConst(0)),
        ("QConst", at.QConst(12)),
        ("QX", at.QX()),
        ("QUnbounded", at.QUnbounded()),
        ("QCount", at.QCount(src)),
        ("QProp-str", at.QProp("controller", at.QPropField.CARDS_IN_HAND)),
        ("QProp-selector", at.QProp(src, at.QPropField.POWER, at.QAgg.MAX)),
        ("QProp-event", at.QProp("event", at.QPropField.AMOUNT)),
        ("QBin-add", at.QBin(at.QBinOp.ADD, at.QConst(1), at.QX())),
        (
            "QBin-nested",
            at.QBin(
                at.QBinOp.DIV,
                at.QBin(at.QBinOp.ADD, at.QConst(3), at.QConst(1)),
                at.QConst(2),
            ),
        ),
        (
            "QBin-min",
            at.QBin(
                at.QBinOp.MIN,
                at.QProp("controller", at.QPropField.CARDS_IN_LIBRARY),
                at.QConst(7),
            ),
        ),
        # zones — every ZoneKind
        *(
            (f"Zone-{kind.name}", at.Zone(kind, at.ControllerRef.ANY))
            for kind in at.ZoneKind
        ),
        ("Zone-you", at.Zone(at.ZoneKind.GRAVEYARD, at.ControllerRef.YOU)),
        (
            "Zone-all-opponents",
            at.Zone(at.ZoneKind.HAND, at.ControllerRef.ALL_OPPONENTS),
        ),
        # selectors — every mode
        (
            "Selector-TARGET",
            at.Selector(
                at.QConst(2),
                at.SelectorMode.TARGET,
                at.FAtom(at.FAtomPred.IS_PERMANENT),
                zones=(_BF_ANY,),
            ),
        ),
        (
            "Selector-CHOOSE",
            at.Selector(
                at.QConst(3),
                at.SelectorMode.CHOOSE,
                at.FAtom(at.FAtomPred.IS_PERMANENT),
                zones=(_BF_ANY,),
            ),
        ),
        (
            "Selector-ALL",
            at.Selector(
                at.QConst(1), at.SelectorMode.ALL, at.FAnd(()), zones=(_BF_ANY,)
            ),
        ),
        (
            "Selector-RANDOM",
            at.Selector(
                at.QConst(1),
                at.SelectorMode.RANDOM,
                at.FAtom(at.FAtomPred.IS_PERMANENT),
                zones=(at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.ANY),),
            ),
        ),
        (
            "Selector-unbounded",
            at.Selector(
                at.QUnbounded(),
                at.SelectorMode.CHOOSE,
                at.FAtom(at.FAtomPred.NAME_EQ, string_value="Frantic Inventory"),
                zones=(lib,),
            ),
        ),
        (
            "Selector-target-player",
            at.Selector(
                at.QConst(1),
                at.SelectorMode.TARGET,
                at.FAnd(()),
                zones=(at.Zone(at.ZoneKind.PLAYER, at.ControllerRef.ANY),),
            ),
        ),
        # filters — every atom predicate plus combinators
        ("FAtom-TYPE_EQ", at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature")),
        ("FAtom-SUBTYPE_EQ", at.FAtom(at.FAtomPred.SUBTYPE_EQ, string_value="Bird")),
        (
            "FAtom-SUPERTYPE_EQ",
            at.FAtom(at.FAtomPred.SUPERTYPE_EQ, string_value="Legendary"),
        ),
        ("FAtom-COLOR_HAS", at.FAtom(at.FAtomPred.COLOR_HAS, color="B")),
        ("FAtom-COLOR_IN", at.FAtom(at.FAtomPred.COLOR_IN, colors=("W", "U"))),
        (
            "FAtom-COLOR_COUNT_GE",
            at.FAtom(at.FAtomPred.COLOR_COUNT_GE, count=at.QConst(2)),
        ),
        ("FAtom-CMC_LE", at.FAtom(at.FAtomPred.CMC_LE, count=at.QConst(3))),
        ("FAtom-CMC_GE", at.FAtom(at.FAtomPred.CMC_GE, count=at.QConst(6))),
        ("FAtom-PT_LE", at.FAtom(at.FAtomPred.PT_LE, count=at.QConst(2))),
        ("FAtom-PT_GE", at.FAtom(at.FAtomPred.PT_GE, count=at.QConst(1))),
        (
            "FAtom-KEYWORD_HAS",
            at.FAtom(at.FAtomPred.KEYWORD_HAS, keyword=at.Keyword.FLYING),
        ),
        (
            "FAtom-NAME_EQ",
            at.FAtom(at.FAtomPred.NAME_EQ, string_value="Frantic Inventory"),
        ),
        ("FAtom-IS_TAPPED", at.FAtom(at.FAtomPred.IS_TAPPED)),
        ("FAtom-IS_UNTAPPED", at.FAtom(at.FAtomPred.IS_UNTAPPED)),
        ("FAtom-IS_ATTACKING", at.FAtom(at.FAtomPred.IS_ATTACKING)),
        ("FAtom-IS_BLOCKING", at.FAtom(at.FAtomPred.IS_BLOCKING)),
        (
            "FAtom-HAS_COUNTER",
            at.FAtom(
                at.FAtomPred.HAS_COUNTER,
                counter_kind=at.CounterKind.PAGE,
                count=at.QConst(4),
            ),
        ),
        (
            "FAtom-CONTROLLER_IS",
            at.FAtom(at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
        ),
        (
            "FAtom-CONTROLLER_IS-target-player",
            at.FAtom(at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.TARGET_PLAYER),
        ),
        (
            "FAtom-CMC_LE-dynamic-count",
            at.FAtom(
                at.FAtomPred.CMC_LE,
                count=at.QProp("controller", at.QPropField.CARDS_IN_HAND),
            ),
        ),
        (
            "FAtom-CONTROLLER_COUNT_GE",
            at.FAtom(
                at.FAtomPred.CONTROLLER_COUNT_GE,
                inner_filter=at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Artifact"),
                count=at.QConst(4),
            ),
        ),
        (
            "FAtom-CONTROLLER_COUNT_LE",
            at.FAtom(
                at.FAtomPred.CONTROLLER_COUNT_LE,
                inner_filter=at.FAtom(at.FAtomPred.IS_PERMANENT),
                count=at.QConst(0),
            ),
        ),
        ("FAtom-IS_SOURCE", at.FAtom(at.FAtomPred.IS_SOURCE)),
        ("FAtom-IS_ANY_TARGET", at.FAtom(at.FAtomPred.IS_ANY_TARGET)),
        ("FAtom-IS_PERMANENT", at.FAtom(at.FAtomPred.IS_PERMANENT)),
        ("FAtom-IS_TOKEN", at.FAtom(at.FAtomPred.IS_TOKEN)),
        ("FAtom-DIED_THIS_TURN", at.FAtom(at.FAtomPred.DIED_THIS_TURN)),
        ("FAtom-IS_ATTACHED_TO_SOURCE", at.FAtom(at.FAtomPred.IS_ATTACHED_TO_SOURCE)),
        (
            "FAnd",
            at.FAnd(
                (at.FAtom(at.FAtomPred.IS_PERMANENT), at.FAtom(at.FAtomPred.IS_TAPPED))
            ),
        ),
        ("FAnd-universal", at.FAnd(())),
        (
            "FOr",
            at.FOr(
                (
                    at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Instant"),
                    at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Sorcery"),
                )
            ),
        ),
        ("FNot", at.FNot(at.FAtom(at.FAtomPred.IS_TOKEN))),
        # durations — all four
        ("DurationEot", at.DurationEot()),
        ("DurationPermanent", at.DurationPermanent()),
        ("DurationUntilNextTurn", at.DurationUntilNextTurn()),
        (
            "DurationWhileCondition",
            at.DurationWhileCondition(at.FAtom(at.FAtomPred.IS_TAPPED)),
        ),
        # events — all twelve
        (
            "ZoneChangeEvent",
            at.ZoneChangeEvent(
                at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY),
                at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU),
            ),
        ),
        (
            "CastSpellEvent",
            at.CastSpellEvent(
                at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Enchantment")
            ),
        ),
        (
            "DeclareAttackersEvent",
            at.DeclareAttackersEvent(at.FAtom(at.FAtomPred.IS_SOURCE)),
        ),
        (
            "DeclareBlockersEvent",
            at.DeclareBlockersEvent(at.FAtom(at.FAtomPred.IS_SOURCE)),
        ),
        # R2 fold (/140): CombatDamageEvent deleted — DamageDealtEvent
        # (below) is the single damage host; the folded shape is pinned
        # in the two entries the fold produced.
        (
            "CounterPlacedEvent",
            at.CounterPlacedEvent(
                at.CounterKind.PLUS_1_PLUS_1, at.FAtom(at.FAtomPred.IS_SOURCE)
            ),
        ),
        (
            "CreatureDiesEvent",
            at.CreatureDiesEvent(at.FAtom(at.FAtomPred.IS_ATTACHED_TO_SOURCE)),
        ),
        (
            "BecomesBlockedEvent",
            at.BecomesBlockedEvent(at.FAtom(at.FAtomPred.IS_PERMANENT)),
        ),
        ("TapStateEvent", at.TapStateEvent(False, at.FAtom(at.FAtomPred.IS_SOURCE))),
        (
            "TurnPhaseEvent",
            at.TurnPhaseEvent(
                at.Phase.END_TURN,
                at.FAtom(pred=at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.YOU),
            ),
        ),
        (
            "StepEvent",
            at.StepEvent(
                at.Phase.COMBAT, at.Step.DECLARE_ATTACKERS, at.ControllerRef.YOU
            ),
        ),
        (
            "DamageDealtEvent",
            at.DamageDealtEvent(at.QConst(2), at.FAtom(at.FAtomPred.IS_SOURCE)),
        ),
        ("TargetingEvent", at.TargetingEvent(at.FAtom(at.FAtomPred.IS_SOURCE))),
        # leaf value types
        ("LiteralName", at.LiteralName("Frantic Inventory")),
        ("PtDelta", at.PtDelta(at.PtDirection.DECREASE, at.QConst(2))),
        (
            "TokenSpec",
            at.TokenSpec(
                name="Treasure",
                type_line="Token Artifact — Treasure",
                types=("Artifact",),
                subtypes=("Treasure",),
                power=None,
                toughness=None,
                keywords=(at.Keyword.TREASURE,),
                abilities=(),
            ),
        ),
        # cost parts — all nine, plus compound and empty costs
        ("CostTap", at.CostTap()),
        ("CostTap-targeted", at.CostTap(src)),
        ("CostManaColor", at.CostManaColor("R", at.QConst(2))),
        ("CostManaGeneric", at.CostManaGeneric(at.QX())),
        ("CostManaHybrid", at.CostManaHybrid(("W", "U"), at.QConst(2))),
        ("CostLife", at.CostLife(at.QConst(2))),
        ("CostSacrifice", at.CostSacrifice(src)),
        (
            "CostDiscard",
            at.CostDiscard(
                at.Selector(
                    at.QConst(1),
                    at.SelectorMode.CHOOSE,
                    at.FAnd(()),
                    zones=(at.Zone(at.ZoneKind.HAND, at.ControllerRef.YOU),),
                )
            ),
        ),
        ("CostPutCounter", at.CostPutCounter(at.CounterKind.PAGE, src)),
        ("CostLoyalty", at.CostLoyalty(-7)),
        (
            "Cost",
            at.Cost(
                parts=(
                    at.CostManaGeneric(at.QConst(1)),
                    at.CostManaColor("B", at.QConst(1)),
                    at.CostTap(),
                )
            ),
        ),
        ("Cost-empty", at.Cost()),
        # effects — all six, several atoms
        ("Seq", at.Seq((tap, untap))),
        ("Choose", at.Choose(at.QConst(1), (tap, untap))),
        ("OptionalEffect", at.OptionalEffect(mill)),
        (
            "Conditional-no-else",
            at.Conditional(at.FAtom(at.FAtomPred.IS_PERMANENT), mill, None),
        ),
        (
            "Conditional-else",
            at.Conditional(at.FAtom(at.FAtomPred.IS_PERMANENT), mill, untap),
        ),
        ("Repeat", at.Repeat(at.QConst(4), mill)),
        (
            "Atom-DEAL_DAMAGE-event-amount",
            at.Atom(
                at.Verb.DEAL_DAMAGE,
                at.AtomArgs(
                    pairs=(
                        ("target", src),
                        ("amount", at.QProp("event", at.QPropField.AMOUNT)),
                    )
                ),
            ),
        ),
        (
            "Atom-MODIFY_PT",
            at.Atom(
                at.Verb.MODIFY_PT,
                at.AtomArgs(
                    pairs=(
                        ("target", src),
                        ("power", at.PtDelta(at.PtDirection.DECREASE, at.QConst(2))),
                        (
                            "toughness",
                            at.PtDelta(at.PtDirection.DECREASE, at.QConst(2)),
                        ),
                        ("duration", at.DurationEot()),
                    )
                ),
            ),
        ),
        (
            "Atom-GRANT_TYPE",
            at.Atom(
                at.Verb.GRANT_TYPE,
                at.AtomArgs(
                    pairs=(
                        ("target", src),
                        ("types", ("Sphinx",)),
                        ("duration", at.DurationEot()),
                    )
                ),
            ),
        ),
        (
            "Atom-PREVENT_EFFECT",
            at.Atom(
                at.Verb.PREVENT_EFFECT,
                at.AtomArgs(
                    pairs=(
                        ("condition", at.FAtom(at.FAtomPred.IS_SOURCE)),
                        (
                            "event",
                            at.DeclareBlockersEvent(at.FAtom(at.FAtomPred.IS_SOURCE)),
                        ),
                        ("controller", at.ControllerRef.OPPONENT),
                    )
                ),
            ),
        ),
        ("Atom-END_TURN", at.Atom(at.Verb.END_TURN, at.AtomArgs(pairs=()))),
        (
            "Atom-MANDATE_ATTACK",
            at.Atom(
                at.Verb.MANDATE_ATTACK,
                at.AtomArgs(
                    pairs=(
                        ("cards", src),
                        ("controller", at.ControllerRef.YOU),
                    )
                ),
            ),
        ),
        (
            "Atom-TAP-duration",
            at.Atom(
                at.Verb.TAP,
                at.AtomArgs(
                    pairs=(
                        ("target", src),
                        ("duration", at.DurationEot()),
                    )
                ),
            ),
        ),
        (
            "Atom-UNTAP-duration",
            at.Atom(
                at.Verb.UNTAP,
                at.AtomArgs(
                    pairs=(
                        ("target", src),
                        ("duration", at.DurationPermanent()),
                    )
                ),
            ),
        ),
        (
            "Atom-MANDATE_ATTACK-duration",
            at.Atom(
                at.Verb.MANDATE_ATTACK,
                at.AtomArgs(
                    pairs=(
                        ("cards", src),
                        ("duration", at.DurationUntilNextTurn()),
                    )
                ),
            ),
        ),
        (
            "AtomArgs-five-roles",
            at.AtomArgs(
                pairs=(
                    ("target", src),
                    ("controller", at.ControllerRef.YOU),
                    ("amount", at.QConst(1)),
                    ("color", "C"),
                    ("destination", at.Zone(at.ZoneKind.EXILE, at.ControllerRef.ANY)),
                )
            ),
        ),
        # abilities — all six
        (
            "StaticAbility",
            at.StaticAbility(
                at.Atom(
                    at.Verb.MODIFY_PT,
                    at.AtomArgs(
                        pairs=(
                            (
                                "target",
                                at.Selector(
                                    at.QConst(1),
                                    at.SelectorMode.ALL,
                                    at.FAnd(()),
                                    zones=(_BF_YOU,),
                                ),
                            ),
                            (
                                "power",
                                at.QProp(
                                    "controller", at.QPropField.CARDS_IN_GRAVEYARD
                                ),
                            ),
                        )
                    ),
                )
            ),
        ),
        (
            "TriggeredAbility",
            at.TriggeredAbility(
                # R2 fold (/140): folded combat-damage shape (ex-CDE).
                at.DamageDealtEvent(
                    at.QUnbounded(), at.FAnd(()), at.FAtom(at.FAtomPred.IS_SOURCE), True
                ),
                None,
                at.OptionalEffect(mill),
            ),
        ),
        ("ActivatedAbility", at.ActivatedAbility(at.Cost(parts=(at.CostTap(),)), mill)),
        ("SpellAbility", at.SpellAbility(at.SpellKind.SORCERY, at.Seq((mill, untap)))),
        ("KeywordAbility-SCRY", at.KeywordAbility(at.Keyword.SCRY, (at.QConst(3),))),
        (
            "KeywordAbility-PROTECTION",
            at.KeywordAbility(
                at.Keyword.PROTECTION,
                (at.FAtom(at.FAtomPred.SUBTYPE_EQ, string_value="Demon"),),
            ),
        ),
        (
            "KeywordAbility-HEXPROOF-param",
            at.KeywordAbility(
                at.Keyword.HEXPROOF,
                (at.FAtom(at.FAtomPred.COLOR_HAS, color="B"),),
            ),
        ),
        ("KeywordAbility-plain", at.KeywordAbility(at.Keyword.FLYING, ())),
        (
            "ReplacementAbility",
            at.ReplacementAbility(
                at.ZoneChangeEvent(
                    at.Zone(at.ZoneKind.COMMAND, at.ControllerRef.YOU),
                    at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU),
                ),
                at.FAtom(at.FAtomPred.NAME_EQ, string_value="The Planeswalker"),
                at.Atom(
                    at.Verb.MOVE_ZONE,
                    at.AtomArgs(
                        pairs=(
                            ("cards", src),
                            (
                                "destination",
                                at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU),
                            ),
                        )
                    ),
                ),
            ),
        ),
        # root
        ("CardRecord-simple", _simple_card()),
        ("CardRecord-tarmogoyf", _tarmogoyf_like()),
        ("CardRecord-planeswalker", _pw_with_emblem()),
        ("CardRecord-token-creator", _token_creator()),
    ]
    return nodes


_ALL_NODES = _all_nodes()


# ---------------------------------------------------------------------------
# Round-trip: to_dict / from_dict / canonical_json / fingerprint
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name,node", _ALL_NODES, ids=[name for name, _ in _ALL_NODES])
def test_roundtrip_every_node_type(name: str, node: object) -> None:
    d = at.to_dict(node)
    assert isinstance(d, dict), f"{name}: to_dict must yield a tagged dict"
    assert "tag" in d
    back = at.from_dict(str(d["tag"]), d)
    assert back == node, f"{name}: from_dict(to_dict(x)) != x"
    assert at.canonical_json(back) == at.canonical_json(node), (
        f"{name}: canonical_json unstable"
    )
    assert at.fingerprint(back) == at.fingerprint(node), f"{name}: fingerprint unstable"


def test_canonical_json_is_valid_compact_json() -> None:
    node = _pw_with_emblem()
    s = at.canonical_json(node)
    assert "\n" not in s
    # canonical form: re-dumping the parsed value reproduces the exact string
    assert json.dumps(json.loads(s), sort_keys=True, separators=(",", ":")) == s
    assert json.loads(s) == at.to_dict(node)


def test_canonical_json_construction_order_independent() -> None:
    # AtomArgs roles inserted in different orders -> identical canonical form
    src = _src_sel()
    q = at.QConst(1)
    a = at.Atom(
        at.Verb.DRAW,
        at.AtomArgs(pairs=(("controller", at.ControllerRef.YOU), ("amount", q))),
    )
    b = at.Atom(
        at.Verb.DRAW,
        at.AtomArgs(pairs=(("amount", q), ("controller", at.ControllerRef.YOU))),
    )
    assert a == b
    assert at.canonical_json(a) == at.canonical_json(b)
    assert at.fingerprint(a) == at.fingerprint(b)
    # the same card built twice independently -> identical fingerprint
    assert at.canonical_json(_tarmogoyf_like()) == at.canonical_json(_tarmogoyf_like())
    assert at.fingerprint(_pw_with_emblem()) == at.fingerprint(_pw_with_emblem())
    assert at.fingerprint(_token_creator()) == at.fingerprint(_token_creator())


def test_fingerprint_changes_when_any_leaf_changes() -> None:
    # direct leaf changes
    assert at.fingerprint(at.QConst(1)) != at.fingerprint(at.QConst(2))
    assert at.fingerprint(at.QX()) != at.fingerprint(at.QUnbounded())
    assert at.fingerprint(
        at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.YOU)
    ) != at.fingerprint(at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.OPPONENT))
    assert at.fingerprint(
        at.FAtom(at.FAtomPred.SUBTYPE_EQ, string_value="Bird")
    ) != at.fingerprint(at.FAtom(at.FAtomPred.SUBTYPE_EQ, string_value="Angel"))
    # a deep leaf change inside a full card record
    base = _tarmogoyf_like(subtype="Bird")
    changed = _tarmogoyf_like(subtype="Angel")
    assert at.fingerprint(base) != at.fingerprint(changed)
    # loyalty leaf
    base_pw = _pw_with_emblem()
    assert at.fingerprint(base_pw) != at.fingerprint(
        at.CardRecord(
            **{**base_pw.__dict__, "loyalty": 5}  # type: ignore[arg-type]
        )
    )
    # token spec leaf (token name inside CREATE_TOKEN's args)
    base_tc = _token_creator()
    other_tc = at.CardRecord(
        **{
            **base_tc.__dict__,
            "name": "Synthetic Gadrak Prime",
        }  # type: ignore[arg-type]
    )
    assert at.fingerprint(base_tc) != at.fingerprint(other_tc)


# ---------------------------------------------------------------------------
# walk() — every node exactly once, card record first
# ---------------------------------------------------------------------------


def test_walk_visits_every_node_exactly_once() -> None:
    node = _walk_sample()
    visited = list(at.walk(node))
    # 1 CardRecord, 1 Cost, 1 CostManaColor, 5 QConst (cost colour, power,
    # toughness, one per selector count), 1 KeywordAbility, 1 StaticAbility,
    # 1 Seq, then per draw atom (x2): 1 Atom, 1 AtomArgs, 1 QCount,
    # 1 Selector, 1 FAnd, 2 FAtom, 1 FNot, 1 Zone, plus 1 OptionalEffect
    assert len(visited) == 30, f"expected 30 nodes, got {len(visited)}"
    assert len({id(v) for v in visited}) == len(visited), (
        "a node was visited twice (object identity)"
    )
    assert visited[0] is node, "the card record must come first"
    # every yielded object is a dataclass grammar node
    for v in visited:
        assert dataclasses.is_dataclass(v) and not isinstance(v, type)


def test_walk_on_leaf_nodes() -> None:
    q = at.QConst(1)
    assert list(at.walk(q)) == [q]
    z = at.Zone(at.ZoneKind.LIBRARY, at.ControllerRef.YOU)
    assert list(at.walk(z)) == [z]


# ---------------------------------------------------------------------------
# Immutability
# ---------------------------------------------------------------------------


def test_immutability() -> None:
    with pytest.raises(FrozenInstanceError):
        at.QConst(1).value = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        _src_sel().mode = at.SelectorMode.TARGET  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        at.AtomArgs().pairs = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        _simple_card().name = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        _tarmogoyf_like().emblem = _simple_card()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------


def _validation_cases() -> list[tuple[str, Callable[[], object]]]:
    q = at.QConst(1)
    src = _src_sel()
    return [
        ("negative QConst", lambda: at.QConst(-1)),
        ("bool QConst", lambda: at.QConst(True)),  # type: ignore[arg-type]
        ("non-int QConst", lambda: at.QConst("1")),  # type: ignore[arg-type]
        ("empty Seq", lambda: at.Seq(())),
        ("empty Choose options", lambda: at.Choose(q, ())),
        ("Seq with non-effect", lambda: at.Seq((q,))),  # type: ignore[arg-type]
        ("Zone with raw kind", lambda: at.Zone("library", at.ControllerRef.YOU)),  # type: ignore[arg-type]
        ("Zone with raw controller", lambda: at.Zone(at.ZoneKind.LIBRARY, "you")),  # type: ignore[arg-type]
        (
            "Selector with raw count",
            lambda: at.Selector(
                "2",
                at.SelectorMode.TARGET,
                at.FAtom(at.FAtomPred.IS_PERMANENT),
                zones=(_BF_ANY,),
            ),
        ),  # type: ignore[arg-type]
        (
            "Selector TARGET with QUnbounded",
            lambda: at.Selector(
                at.QUnbounded(),
                at.SelectorMode.TARGET,
                at.FAtom(at.FAtomPred.IS_PERMANENT),
                zones=(_BF_ANY,),
            ),
        ),
        ("QBin with non-quantity operand", lambda: at.QBin(at.QBinOp.ADD, "x", q)),  # type: ignore[arg-type]
        (
            "QProp AMOUNT with wrong referent",
            lambda: at.QProp("controller", at.QPropField.AMOUNT),
        ),
        (
            "QProp player-field with non-controller",
            lambda: at.QProp("event", at.QPropField.CARDS_IN_HAND),
        ),
        (
            "QProp bad referent type",
            lambda: at.QProp(
                at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY), at.QPropField.POWER
            ),
        ),  # type: ignore[arg-type]
        (
            "QProp aggregation on singular referent",
            lambda: at.QProp("controller", at.QPropField.CARDS_IN_HAND, at.QAgg.MAX),
        ),
        ("QCount with non-selector", lambda: at.QCount(at.QConst(1))),  # type: ignore[arg-type]
        ("FAtom missing required slot", lambda: at.FAtom(at.FAtomPred.TYPE_EQ)),
        (
            "FAtom empty string_value",
            lambda: at.FAtom(at.FAtomPred.TYPE_EQ, string_value="  "),
        ),
        (
            "FAtom foreign slot",
            lambda: at.FAtom(at.FAtomPred.TYPE_EQ, string_value="Creature", color="W"),
        ),
        (
            "FAtom HAS_COUNTER missing kind",
            lambda: at.FAtom(at.FAtomPred.HAS_COUNTER, count=at.QConst(1)),
        ),
        (
            "FAtom HAS_COUNTER count 0",
            lambda: at.FAtom(
                at.FAtomPred.HAS_COUNTER,
                counter_kind=at.CounterKind.PAGE,
                count=at.QConst(0),
            ),
        ),
        (
            "FAtom CONTROLLER_IS with ANY",
            lambda: at.FAtom(at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.ANY),
        ),
        (
            "FAtom CONTROLLER_IS with ALL_OPPONENTS",
            lambda: at.FAtom(
                at.FAtomPred.CONTROLLER_IS, who=at.ControllerRef.ALL_OPPONENTS
            ),
        ),
        ("FAtom COLOR_IN empty", lambda: at.FAtom(at.FAtomPred.COLOR_IN)),
        (
            "FAtom COLOR_IN bad colour",
            lambda: at.FAtom(at.FAtomPred.COLOR_IN, colors=("W", "X")),
        ),
        (
            "FAtom COLOR_COUNT_GE zero",
            lambda: at.FAtom(at.FAtomPred.COLOR_COUNT_GE, count=at.QConst(0)),
        ),
        ("FAtom non-quantity count", lambda: at.FAtom(at.FAtomPred.CMC_LE, count="2")),  # type: ignore[arg-type]
        (
            "FAtom bad inner_filter",
            lambda: at.FAtom(
                at.FAtomPred.CONTROLLER_COUNT_GE, inner_filter="x", count=at.QConst(1)
            ),
        ),  # type: ignore[arg-type]
        (
            "Atom missing required role",
            lambda: at.Atom(at.Verb.DRAW, at.AtomArgs(pairs=(("target", src),))),
        ),
        (
            "Atom missing amount",
            lambda: at.Atom(at.Verb.DEAL_DAMAGE, at.AtomArgs(pairs=(("target", src),))),
        ),
        (
            "Atom extra role",
            lambda: at.Atom(at.Verb.END_TURN, at.AtomArgs(pairs=(("target", src),))),
        ),
        (
            "Atom MODIFY_PT without P/T",
            lambda: at.Atom(at.Verb.MODIFY_PT, at.AtomArgs(pairs=(("target", src),))),
        ),
        ("AtomArgs unknown role", lambda: at.AtomArgs(pairs=(("bogus", q),))),
        (
            "AtomArgs duplicate role",
            lambda: at.AtomArgs(pairs=(("amount", q), ("amount", at.QConst(2)))),
        ),
        (
            "AtomArgs wrong value type for role",
            lambda: at.AtomArgs(
                pairs=(("target", at.Zone(at.ZoneKind.ANY, at.ControllerRef.ANY)),)
            ),
        ),
        ("AtomArgs bad color value", lambda: at.AtomArgs(pairs=(("color", "Q"),))),
        (
            "AtomArgs non-str types tuple",
            lambda: at.AtomArgs(pairs=(("types", (at.QConst(1),)),)),
        ),  # type: ignore[arg-type]
        (
            "TokenSpec creature without P/T",
            lambda: at.TokenSpec(
                name="X",
                type_line="Creature — X",
                types=("Creature",),
                subtypes=("X",),
                power=None,
                toughness=None,
                keywords=(),
                abilities=(),
            ),
        ),
        (
            "TokenSpec artifact with P/T",
            lambda: at.TokenSpec(
                name="X",
                type_line="Artifact",
                types=("Artifact",),
                subtypes=(),
                power=q,
                toughness=None,
                keywords=(),
                abilities=(),
            ),
        ),
        (
            "TokenSpec empty types",
            lambda: at.TokenSpec(
                name="X",
                type_line="Artifact",
                types=(),
                subtypes=(),
                power=None,
                toughness=None,
                keywords=(),
                abilities=(),
            ),
        ),
        (
            "KeywordAbility SCRY without param",
            lambda: at.KeywordAbility(at.Keyword.SCRY),
        ),
        (
            "KeywordAbility FLYING with param",
            lambda: at.KeywordAbility(at.Keyword.FLYING, (q,)),
        ),
        (
            "KeywordAbility PROTECTION with non-filter",
            lambda: at.KeywordAbility(at.Keyword.PROTECTION, (q,)),
        ),
        (
            "KeywordAbility two params for PROTECTION",
            lambda: at.KeywordAbility(
                at.Keyword.PROTECTION,
                (
                    at.FAtom(at.FAtomPred.IS_PERMANENT),
                    at.FAtom(at.FAtomPred.IS_PERMANENT),
                ),
            ),
        ),
        ("CostLoyalty zero", lambda: at.CostLoyalty(0)),
        ("CostManaHybrid same colour", lambda: at.CostManaHybrid(("W", "W"), q)),
        ("CostManaHybrid bad colour", lambda: at.CostManaHybrid(("W", "X"), q)),
        ("CostManaColor bad colour", lambda: at.CostManaColor("Q", q)),
        ("Cost with non-part", lambda: at.Cost(parts=(q,))),  # type: ignore[arg-type]
        (
            "DurationWhileCondition non-filter",
            lambda: at.DurationWhileCondition("nope"),
        ),  # type: ignore[arg-type]
        (
            "TriggeredAbility raw event",
            lambda: at.TriggeredAbility(
                "ZoneChange", None, at.Atom(at.Verb.END_TURN, at.AtomArgs(pairs=()))
            ),
        ),  # type: ignore[arg-type]
        (
            "TriggeredAbility bad condition",
            lambda: at.TriggeredAbility(
                # R2 fold (/140): folded combat-damage shape (ex-CDE).
                at.DamageDealtEvent(
                    at.QUnbounded(),
                    at.FAnd(()),
                    at.FAtom(at.FAtomPred.IS_PERMANENT),
                    True,
                ),
                "x",
                at.Atom(at.Verb.END_TURN, at.AtomArgs(pairs=())),
            ),
        ),  # type: ignore[arg-type]
        (
            "SpellAbility raw kind",
            lambda: at.SpellAbility(
                "instant", at.Atom(at.Verb.END_TURN, at.AtomArgs(pairs=()))
            ),
        ),  # type: ignore[arg-type]
        (
            "ZoneChangeEvent non-zone",
            lambda: at.ZoneChangeEvent(
                "any", at.Zone(at.ZoneKind.BATTLEFIELD, at.ControllerRef.YOU)
            ),
        ),  # type: ignore[arg-type]
        (
            "DamageDealtEvent non-quantity",
            lambda: at.DamageDealtEvent("x", at.FAtom(at.FAtomPred.IS_PERMANENT)),
        ),  # type: ignore[arg-type]
        (
            "CardRecord bad oracle id",
            lambda: at.CardRecord(
                oracle_id="not-a-uuid",
                name="X",
                type_line="Land",
                types=("Land",),
                subtypes=(),
                supertypes=(),
                colors=(),
                color_identity=frozenset(),
                mana_cost=None,
                mana_value=0,
                power=None,
                toughness=None,
                loyalty=None,
                keywords=(),
                abilities=(),
                is_token=False,
            ),
        ),
        (
            "CardRecord P/T on non-creature",
            lambda: at.CardRecord(
                oracle_id=_OID1,
                name="X",
                type_line="Land — Plains",
                types=("Basic", "Land"),
                subtypes=("Plains",),
                supertypes=("Basic",),
                colors=(),
                color_identity=frozenset(),
                mana_cost=None,
                mana_value=0,
                power=q,
                toughness=None,
                loyalty=None,
                keywords=(),
                abilities=(),
                is_token=False,
            ),
        ),
        (
            "CardRecord loyalty on non-PW",
            lambda: at.CardRecord(
                oracle_id=_OID1,
                name="X",
                type_line="Creature — Cat",
                types=("Creature",),
                subtypes=("Cat",),
                supertypes=(),
                colors=(),
                color_identity=frozenset(),
                mana_cost=None,
                mana_value=0,
                power=q,
                toughness=q,
                loyalty=3,
                keywords=(),
                abilities=(),
                is_token=False,
            ),
        ),
        (
            "CardRecord PW without loyalty",
            lambda: at.CardRecord(
                oracle_id=_OID1,
                name="X",
                type_line="Planeswalker",
                types=("Planeswalker",),
                subtypes=(),
                supertypes=(),
                colors=(),
                color_identity=frozenset(),
                mana_cost=None,
                mana_value=0,
                power=None,
                toughness=None,
                loyalty=None,
                keywords=(),
                abilities=(),
                is_token=False,
            ),
        ),
        (
            "CardRecord negative loyalty",
            lambda: at.CardRecord(
                oracle_id=_OID1,
                name="X",
                type_line="Planeswalker",
                types=("Planeswalker",),
                subtypes=(),
                supertypes=(),
                colors=(),
                color_identity=frozenset(),
                mana_cost=None,
                mana_value=0,
                power=None,
                toughness=None,
                loyalty=-2,
                keywords=(),
                abilities=(),
                is_token=False,
            ),
        ),
        (
            "CardRecord emblem on non-PW",
            lambda: at.CardRecord(
                oracle_id=_OID1,
                name="X",
                type_line="Creature — Cat",
                types=("Creature",),
                subtypes=("Cat",),
                supertypes=(),
                colors=(),
                color_identity=frozenset(),
                mana_cost=None,
                mana_value=0,
                power=q,
                toughness=q,
                loyalty=None,
                keywords=(),
                abilities=(),
                is_token=False,
                emblem=_emblem_record(),
            ),
        ),
        (
            "CardRecord bad colour",
            lambda: at.CardRecord(
                oracle_id=_OID1,
                name="X",
                type_line="Land — Plains",
                types=("Land",),
                subtypes=("Plains",),
                supertypes=(),
                colors=("Q",),
                color_identity=frozenset(),
                mana_cost=None,
                mana_value=0,
                power=None,
                toughness=None,
                loyalty=None,
                keywords=(),
                abilities=(),
                is_token=False,
            ),
        ),
        (
            "CardRecord negative mana value",
            lambda: at.CardRecord(
                oracle_id=_OID1,
                name="X",
                type_line="Land — Plains",
                types=("Land",),
                subtypes=("Plains",),
                supertypes=(),
                colors=(),
                color_identity=frozenset(),
                mana_cost=None,
                mana_value=-1,
                power=None,
                toughness=None,
                loyalty=None,
                keywords=(),
                abilities=(),
                is_token=False,
            ),
        ),
        (
            "CardRecord empty name",
            lambda: at.CardRecord(
                oracle_id=_OID1,
                name="  ",
                type_line="Land",
                types=("Land",),
                subtypes=(),
                supertypes=(),
                colors=(),
                color_identity=frozenset(),
                mana_cost=None,
                mana_value=0,
                power=None,
                toughness=None,
                loyalty=None,
                keywords=(),
                abilities=(),
                is_token=False,
            ),
        ),
    ]


@pytest.mark.parametrize(
    "name,fn", _validation_cases(), ids=[n for n, _ in _validation_cases()]
)
def test_validation_failures(name: str, fn: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        fn()


# ---------------------------------------------------------------------------
# from_dict strictness
# ---------------------------------------------------------------------------


def test_from_dict_tag_mismatch() -> None:
    d = at.to_dict(at.QX())
    with pytest.raises(ValueError):
        at.from_dict("QConst", d)


def test_from_dict_unknown_tag() -> None:
    with pytest.raises(ValueError):
        at.from_dict("NotATag", {"tag": "NotATag"})
    with pytest.raises(ValueError):
        at.from_dict("QConst", {"tag": "NotATag"})


def test_from_dict_missing_field() -> None:
    with pytest.raises(ValueError):
        at.from_dict("QConst", {"tag": "QConst"})


def test_from_dict_extra_field() -> None:
    with pytest.raises(ValueError):
        at.from_dict("QConst", {"tag": "QConst", "value": 1, "extra": 2})


def test_from_dict_wrong_value_type() -> None:
    with pytest.raises(ValueError):
        at.from_dict("QConst", {"tag": "QConst", "value": "1"})
    with pytest.raises(ValueError):
        at.from_dict(
            "Zone",
            {
                "tag": "Zone",
                "kind": {"tag": "ZoneKind", "name": "LIBRARY"},
                "controller": {"tag": "ControllerRef", "name": "NOT_A_MEMBER"},
            },
        )
    with pytest.raises(ValueError):
        at.from_dict(
            "QBin",
            {
                "tag": "QBin",
                "op": {"tag": "QBinOp", "name": "ADD"},
                "left": {"tag": "QX"},
                "right": {"tag": "QConst", "value": 1},
                "bogus": 1,
            },
        )


def test_from_dict_non_dict() -> None:
    with pytest.raises(ValueError):
        at.from_dict("QX", "not a dict")  # type: ignore[arg-type]


def test_atom_args_roundtrip_wraps_values() -> None:
    args = at.AtomArgs(
        pairs=(
            ("controller", at.ControllerRef.YOU),
            ("color", "C"),
            ("types", ("Sphinx",)),
            ("amount", at.QConst(2)),
        )
    )
    d = at.to_dict(args)
    back = at.from_dict("AtomArgs", d)
    assert back == args
    assert back.get("color") == "C"
    assert back.get("types") == ("Sphinx",)
    assert back.get("controller") is at.ControllerRef.YOU
    assert back.get("amount") == at.QConst(2)
    assert back.get("missing") is None


# ---------------------------------------------------------------------------
# Closed vocabulary grounding
# ---------------------------------------------------------------------------


def test_verb_count_in_spec_range() -> None:
    # DESIGN_CARD_POOL: ~60 verbs planned; the M21-hypothesised subset must
    # sit in the 30-45 band the rebuild pre-registered. Grammar round 8
    # (KNOWLEDGE 2026-09-28/08, R8-7/R8-8) added GET_EMBLEM + ADD_LAND_PLAY,
    # taking the vocabulary to 46 — the ceiling widens to 50 (still below
    # the ~60 plan) so the guard keeps its teeth.
    assert 30 <= len(at.Verb) <= 50


def test_keyword_enum_is_closed_pool_set() -> None:
    # The 24 distinct MTGJSON keyword strings of the M21 pool normalize to
    # exactly these 23 ("Hexproof from" -> HEXPROOF + Filter param).
    expected = {
        "FLYING",
        "SCRY",
        "VIGILANCE",
        "LIFELINK",
        "FLASH",
        "ENCHANT",
        "TRAMPLE",
        "PROWESS",
        "REACH",
        "HEXPROOF",
        "PROTECTION",
        "MILL",
        "DEFENDER",
        "HASTE",
        "FIGHT",
        "DEATHTOUCH",
        "FIRST_STRIKE",
        "DOUBLE_STRIKE",
        "EQUIP",
        "INDESTRUCTIBLE",
        "TREASURE",
        "BATTALION",
        "MENACE",
    }
    assert {k.name for k in at.Keyword} == expected


def test_every_fatom_pred_has_a_rule_row() -> None:
    for pred in at.FAtomPred:
        required, allowed = at._FATOM_RULES[pred]  # noqa: SLF001
        assert required <= allowed


# ---------------------------------------------------------------------------
# Full synthetic CardRecords — build, serialize, round-trip, fingerprint
# ---------------------------------------------------------------------------


def test_synthetic_tarmogoyf_like() -> None:
    card = _tarmogoyf_like()
    # semantics: SET_PT over QCount across all graveyards, subtype filter
    spell = card.abilities[0]
    assert isinstance(spell, at.SpellAbility)
    effect = spell.effect
    assert isinstance(effect, at.Atom)
    assert effect.verb is at.Verb.SET_PT
    power = effect.args.get("power")
    assert isinstance(power, at.QCount)
    assert power.selector.zones[0] == at.Zone(
        at.ZoneKind.GRAVEYARD, at.ControllerRef.ANY
    )
    assert isinstance(power.selector.filter, at.FAtom)
    assert power.selector.filter.pred is at.FAtomPred.SUBTYPE_EQ
    assert card.power is None and card.toughness is None  # dynamic P/T
    # round-trip + stable fingerprint
    d = at.to_dict(card)
    assert at.from_dict("CardRecord", d) == card
    assert at.fingerprint(card) == at.fingerprint(at.from_dict("CardRecord", d))
    assert at.canonical_json(card) == at.canonical_json(_tarmogoyf_like())
    # walk starts at the record
    assert next(iter(at.walk(card))) is card


def test_synthetic_planeswalker_with_emblem() -> None:
    card = _pw_with_emblem()
    assert card.loyalty == 4
    assert card.emblem is not None
    assert card.emblem.is_token is True
    assert card.emblem.types == ("Emblem",)
    assert card.emblem.oracle_id == _OID2B
    # loyalty costs in both directions
    costs = [a.cost for a in card.abilities if isinstance(a, at.ActivatedAbility)]
    assert len(costs) == 2
    assert any(
        isinstance(p, at.CostLoyalty) and p.delta == 1 for c in costs for p in c.parts
    )
    assert any(
        isinstance(p, at.CostLoyalty) and p.delta == -2 for c in costs for p in c.parts
    )
    # round-trip (including the nested emblem) + stable fingerprint
    d = at.to_dict(card)
    back = at.from_dict("CardRecord", d)
    assert back == card
    assert back.emblem == card.emblem
    assert at.fingerprint(card) == at.fingerprint(back)
    assert at.canonical_json(card) == at.canonical_json(_pw_with_emblem())


def test_synthetic_token_creator() -> None:
    card = _token_creator()
    trigger = card.abilities[0]
    assert isinstance(trigger, at.TriggeredAbility)
    assert isinstance(trigger.event, at.TurnPhaseEvent)
    assert trigger.event.phase is at.Phase.END_TURN
    assert trigger.condition is not None
    assert isinstance(trigger.condition, at.FAtom)
    assert trigger.condition.pred is at.FAtomPred.CONTROLLER_COUNT_GE
    atom = trigger.effect
    assert isinstance(atom, at.Atom)
    assert atom.verb is at.Verb.CREATE_TOKEN
    tokens = atom.args.get("tokens")
    assert isinstance(tokens, at.TokenSpec)
    assert tokens.name == "Treasure"
    assert isinstance(tokens.abilities[0], at.ActivatedAbility)
    count = atom.args.get("count")
    assert isinstance(count, at.QCount)
    # round-trip + stable fingerprint
    d = at.to_dict(card)
    back = at.from_dict("CardRecord", d)
    assert back == card
    assert at.fingerprint(card) == at.fingerprint(back)
    assert at.canonical_json(card) == at.canonical_json(_token_creator())
