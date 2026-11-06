"""B8 bucket: the party family (ZNR).

"The number of creatures in your party" is one node, ``QPartyCount``: the creatures you control
that cover distinct party classes (Cleric, Rogue, Warrior, Wizard, at most one each;
CR 702.158). The evaluator (executor/quantity.py) does the census; the Selector here is only
the population, creatures you control on the battlefield. For-each amounts are
``QBin(MUL, unit, QPartyCount)``, "where X is the number of creatures in your party" binds X to
it, and "if you have a full party" is the AND of four per-class CONTROLLER_COUNT_GE tests.

No tail here is a ``templates_b6._TAIL_BUILDERS`` key (each carries a quantity), so the effects
are built from the shared b6 anchors.

Left unparsed on purpose, rather than encoded wrong:

* Concerted Defense, "unless its controller pays {1} plus an additional {1} for each creature
  in your party": unless-costs resolve in the payer's seat, so the party would count the
  wrong board.
* Archpriest of Iona's power, Ravager's Mace's "+1/+0 for each creature in your party": a
  static value over a changing census needs layer re-resolution.
* Acquisitions Expert, "target opponent reveals a number of cards from their hand":
  ``Verb.REVEAL`` runs ``_look``, which reads the library.
* Synchronized Spellcraft, "X damage to that creature's controller": the IR has no "that
  creature's controller" recipient, and a second TARGET over the PLAYER zone would let the
  caster pick the player (CR 115.1).

Known loss: Coveted Prize's "a spell with mana value 4 or less" is CMC_LE 4 on the
CHOOSE-from-hand selector; no predicate says "spell", so lands in hand are on the menu.
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    Conditional,
    ControllerRef,
    Cost,
    CostDeltaReduceGeneric,
    CostModifier,
    CounterKind,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DurationEot,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    OptionalEffect,
    Phase,
    PtDelta,
    PtDirection,
    QAtMost,
    QBin,
    QBinOp,
    QConst,
    QPartyCount,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    TokenSpec,
    TriggeredAbility,
    TurnPhaseEvent,
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
from MTG_bot.core.compiler.templates_b2b import _to_a_player
from MTG_bot.core.compiler.templates_b6 import (
    _etb_event,
    _referent_target_creature,
    _self_selector,
)

_BUCKET: Final = "B8"
_PRIORITY: Final[int] = 114  # above B7 (112); no other module claims these heads


# ---------------------------------------------------------------------------
# Shared party structure
# ---------------------------------------------------------------------------


def _party_count() -> QPartyCount:
    """``the number of creatures in your party``: QPartyCount over the creatures you control on
    the battlefield."""
    return QPartyCount(
        selector=Selector(
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
    )


def _full_party() -> Filter:
    """``you have a full party``: CONTROLLER_COUNT_GE 1 over SUBTYPE_EQ for each of the four
    classes, ANDed."""
    return FAnd(
        children=tuple(
            FAtom(
                pred=FAtomPred.CONTROLLER_COUNT_GE,
                count=QConst(1),
                inner_filter=FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value=cls),
            )
            for cls in ("Cleric", "Rogue", "Warrior", "Wizard")
        )
    )


def _template(tid: str, name: str, pattern: str, build) -> Template:
    return Template(
        tid=tid,
        name=name,
        bucket=_BUCKET,
        pattern=re.compile(pattern),
        priority=_PRIORITY,
        build=build,
    )


def _creatures_you_control() -> Selector:
    """``creatures you control`` — ALL-mode population selector."""
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


def _target_creature_on_battlefield() -> Selector:
    """Plain ``target creature``: any creature on the battlefield."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _target_creature_an_opponent_controls() -> Selector:
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _combat_event() -> TurnPhaseEvent:
    """``At the beginning of combat on your turn``."""
    return TurnPhaseEvent(
        phase=Phase.COMBAT,
        actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
    )


def _scaled(unit: int) -> QBin:
    """``<unit> for each creature in your party`` = QBin(MUL, unit, party)."""
    return QBin(op=QBinOp.MUL, left=QConst(unit), right=_party_count())


# ---------------------------------------------------------------------------
# The {1} discount
# ---------------------------------------------------------------------------


def _build_discount(m: re.Match[str]) -> SentenceOutcome:
    """``This spell costs {1} less to cast for each creature in your party.`` and the ability
    variant: a CostModifier on the card, filter IS_SOURCE, so the legality lane prices the
    discount."""
    return AbilityOutcome(
        ability=CostModifier(
            filter=FAtom(pred=FAtomPred.IS_SOURCE),
            controller_ref=ControllerRef.YOU,
            delta=CostDeltaReduceGeneric(amount=_scaled(1)),
        )
    )


# ---------------------------------------------------------------------------
# For-each scaled effects
# ---------------------------------------------------------------------------


def _build_token_per_party(m: re.Match[str]) -> SentenceOutcome:
    """``When this creature enters, create a 1/1 white Kor Warrior creature
    token for each creature in your party.``"""
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_etb_event(),
            condition=None,
            effect=Atom(
                verb=Verb.CREATE_TOKEN,
                args=AtomArgs(
                    pairs=(
                        (
                            "tokens",
                            TokenSpec(
                                name="Kor Warrior",
                                type_line="Creature — Kor Warrior",
                                types=("Creature",),
                                subtypes=("Kor", "Warrior"),
                                power=QConst(1),
                                toughness=QConst(1),
                                keywords=(),
                                abilities=(),
                                colors=("W",),
                            ),
                        ),
                        ("count", _scaled(1)),
                    )
                ),
            ),
        )
    )


def _build_counter_self_per_party(m: re.Match[str]) -> SentenceOutcome:
    """``When this creature enters, put a +1/+1 counter on it for each
    creature in your party.``"""
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_etb_event(),
            condition=None,
            effect=Atom(
                verb=Verb.PUT_COUNTER,
                args=AtomArgs(
                    pairs=(
                        ("target", _self_selector()),
                        ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                        ("count", _party_count()),
                    )
                ),
            ),
        )
    )


def _build_attack_pt_per_party(m: re.Match[str]) -> SentenceOutcome:
    """``Whenever this creature attacks, it gets +1/+0 until end of turn
    for each creature in your party.`` Toughness is an explicit +0, so the printed "+1/+0"
    is kept whole."""
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=DeclareAttackersEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
            condition=None,
            effect=Atom(
                verb=Verb.MODIFY_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", _self_selector()),
                        ("power", PtDelta(PtDirection.INCREASE, _scaled(1))),
                        ("toughness", PtDelta(PtDirection.INCREASE, QConst(0))),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )


def _build_add_red_per_party(m: re.Match[str]) -> SentenceOutcome:
    """``When this creature enters, add {R} for each creature in your
    party.``"""
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_etb_event(),
            condition=None,
            effect=Atom(
                verb=Verb.ADD_MANA,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", _party_count()),
                        ("color", "R"),
                    )
                ),
            ),
        )
    )


def _build_pt_target_per_party(m: re.Match[str]) -> SentenceOutcome:
    """``When this creature enters, target creature gets +1/+1 until end of
    turn for each creature in your party.``"""
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_etb_event(),
            condition=None,
            effect=Atom(
                verb=Verb.MODIFY_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", _target_creature_on_battlefield()),
                        ("power", PtDelta(PtDirection.INCREASE, _scaled(1))),
                        ("toughness", PtDelta(PtDirection.INCREASE, _scaled(1))),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )


def _build_gain_life_per_party(m: re.Match[str]) -> SentenceOutcome:
    """``When this creature enters, you gain 2 life for each creature in
    your party.``"""
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_etb_event(),
            condition=None,
            effect=Atom(
                verb=Verb.GAIN_LIFE,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", _scaled(2)),
                    )
                ),
            ),
        )
    )


def _build_counter_referent_per_party(m: re.Match[str]) -> SentenceOutcome:
    """``Put a +1/+1 counter on it for each creature in your party.`` "It" is the creature the
    previous sentence targeted (b6 ``_referent_target_creature``); the sentence is not a
    continuation, so it lands card-level."""
    return EffectOutcome(
        effect=Atom(
            verb=Verb.PUT_COUNTER,
            args=AtomArgs(
                pairs=(
                    ("target", _referent_target_creature()),
                    ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                    ("count", _party_count()),
                )
            ),
        )
    )


def _build_name_damage_twice(m: re.Match[str]) -> SentenceOutcome:
    """``Practiced Tactics deals damage to that creature equal to twice
    the number of creatures in your party.`` The amount is QBin(MUL, 2, party), not a damage
    multiplier. No dealer role: the source deals it (b6 convention). "That creature" is the
    previous sentence's target."""
    return EffectOutcome(
        effect=Atom(
            verb=Verb.DEAL_DAMAGE,
            args=AtomArgs(
                pairs=(
                    ("target", _referent_target_creature()),
                    ("amount", _scaled(2)),
                )
            ),
        )
    )


# ---------------------------------------------------------------------------
# Full-party heads
# ---------------------------------------------------------------------------


def _build_full_pt_indestructible(m: re.Match[str]) -> SentenceOutcome:
    """``At the beginning of combat on your turn, if you have a full
    party, creatures you control get +1/+0 and gain indestructible until
    end of turn.``"""
    targets = _creatures_you_control()
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_combat_event(),
            condition=_full_party(),
            effect=Seq(
                steps=(
                    Atom(
                        verb=Verb.MODIFY_PT,
                        args=AtomArgs(
                            pairs=(
                                ("target", targets),
                                ("power", PtDelta(PtDirection.INCREASE, QConst(1))),
                                (
                                    "toughness",
                                    PtDelta(PtDirection.INCREASE, QConst(0)),
                                ),
                                ("duration", DurationEot()),
                            )
                        ),
                    ),
                    Atom(
                        verb=Verb.GRANT_ABILITY,
                        args=AtomArgs(
                            pairs=(
                                ("target", targets),
                                (
                                    "ability",
                                    KeywordAbility(
                                        keyword=Keyword.INDESTRUCTIBLE, params=()
                                    ),
                                ),
                                ("duration", DurationEot()),
                            )
                        ),
                    ),
                )
            ),
        )
    )


def _build_full_pt_flying(m: re.Match[str]) -> SentenceOutcome:
    """``...if you have a full party, target creature gets +1/+1 and gains
    flying until end of turn.`` Both steps share the one target selector."""
    target = _target_creature_on_battlefield()
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_combat_event(),
            condition=_full_party(),
            effect=Seq(
                steps=(
                    Atom(
                        verb=Verb.MODIFY_PT,
                        args=AtomArgs(
                            pairs=(
                                ("target", target),
                                ("power", PtDelta(PtDirection.INCREASE, QConst(1))),
                                ("toughness", PtDelta(PtDirection.INCREASE, QConst(1))),
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
                                    KeywordAbility(keyword=Keyword.FLYING, params=()),
                                ),
                                ("duration", DurationEot()),
                            )
                        ),
                    ),
                )
            ),
        )
    )


def _build_full_choose_nonland(m: re.Match[str]) -> SentenceOutcome:
    """``...if you have a full party, choose target nonland permanent an
    opponent controls.`` Verb.CHOOSE records the pick; the card's next sentence is a
    separate row."""
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_combat_event(),
            condition=_full_party(),
            effect=Atom(
                verb=Verb.CHOOSE,
                args=AtomArgs(
                    pairs=(
                        (
                            "target",
                            Selector(
                                QConst(1),
                                SelectorMode.TARGET,
                                FAnd(
                                    children=(
                                        FNot(
                                            inner=FAtom(
                                                pred=FAtomPred.TYPE_EQ,
                                                string_value="Land",
                                            )
                                        ),
                                        FAtom(
                                            pred=FAtomPred.CONTROLLER_IS,
                                            who=ControllerRef.OPPONENT,
                                        ),
                                    )
                                ),
                                zones=(
                                    Zone(
                                        kind=ZoneKind.BATTLEFIELD,
                                        controller=ControllerRef.ANY,
                                    ),
                                ),
                            ),
                        ),
                        ("count", QConst(1)),
                    )
                ),
            ),
        )
    )


def _build_full_grant_draw(m: re.Match[str]) -> SentenceOutcome:
    """``...if you have a full party, creatures you control gain "Whenever
    this creature deals combat damage to a player, draw a card" until end
    of turn.`` GRANT_ABILITY of a TriggeredAbility. "To a player" is b2b's ``_to_a_player``,
    so combat damage to a blocker draws nothing. There is no "may" inside the quotes: the
    draw is forced."""
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_combat_event(),
            condition=_full_party(),
            effect=Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("target", _creatures_you_control()),
                        (
                            "ability",
                            TriggeredAbility(
                                event=DamageDealtEvent(
                                    amount=QUnbounded(),
                                    filter=_to_a_player(),
                                    source=FAtom(pred=FAtomPred.IS_SOURCE),
                                    combat=True,
                                ),
                                condition=None,
                                effect=Atom(
                                    verb=Verb.DRAW,
                                    args=AtomArgs(
                                        pairs=(
                                            ("controller", ControllerRef.YOU),
                                            ("amount", QConst(1)),
                                        )
                                    ),
                                ),
                            ),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )


def _build_full_free_cast(m: re.Match[str]) -> SentenceOutcome:
    """``If you have a full party, you may cast a spell with mana value 4
    or less from your hand without paying its mana cost.`` A Conditional over an optional
    CAST of a chosen hand card with mana value 4 or less; the waived cost is
    Cost(parts=())."""
    return EffectOutcome(
        effect=Conditional(
            pred=_full_party(),
            then_effect=OptionalEffect(
                inner=Atom(
                    verb=Verb.CAST,
                    args=AtomArgs(
                        pairs=(
                            (
                                "source",
                                Selector(
                                    QConst(1),
                                    SelectorMode.CHOOSE,
                                    FAtom(pred=FAtomPred.CMC_LE, count=QConst(4)),
                                    zones=(
                                        Zone(
                                            kind=ZoneKind.HAND,
                                            controller=ControllerRef.YOU,
                                        ),
                                    ),
                                ),
                            ),
                            ("cost", Cost(parts=())),
                        )
                    ),
                )
            ),
        )
    )


# ---------------------------------------------------------------------------
# "where X is the number of creatures in your party" (X := QPartyCount)
# ---------------------------------------------------------------------------


def _build_scry_x_party(m: re.Match[str]) -> SentenceOutcome:
    """``When this creature enters, scry X, where X is the number of
    creatures in your party.``"""
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_etb_event(),
            condition=None,
            effect=Atom(
                verb=Verb.SCRY,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("count", _party_count()),
                    )
                ),
            ),
        )
    )


def _build_up_to_two_x(m: re.Match[str]) -> SentenceOutcome:
    """``Up to two target creatures each get +X/+X until end of turn, where
    X is the number of creatures in your party.`` "Up to two" is TARGET + QAtMost(2)."""
    return EffectOutcome(
        effect=Atom(
            verb=Verb.MODIFY_PT,
            args=AtomArgs(
                pairs=(
                    (
                        "target",
                        Selector(
                            QAtMost(2),
                            SelectorMode.TARGET,
                            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                            zones=(
                                Zone(
                                    kind=ZoneKind.BATTLEFIELD,
                                    controller=ControllerRef.ANY,
                                ),
                            ),
                        ),
                    ),
                    ("power", PtDelta(PtDirection.INCREASE, _party_count())),
                    ("toughness", PtDelta(PtDirection.INCREASE, _party_count())),
                    ("duration", DurationEot()),
                )
            ),
        )
    )


def _build_lose_gain_x(m: re.Match[str]) -> SentenceOutcome:
    """``When this creature enters, each opponent loses X life and you
    gain X life, where X is the number of creatures in your party.``"""
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_etb_event(),
            condition=None,
            effect=Seq(
                steps=(
                    Atom(
                        verb=Verb.LOSE_LIFE,
                        args=AtomArgs(
                            pairs=(
                                ("controller", ControllerRef.ALL_OPPONENTS),
                                ("amount", _party_count()),
                            )
                        ),
                    ),
                    Atom(
                        verb=Verb.GAIN_LIFE,
                        args=AtomArgs(
                            pairs=(
                                ("controller", ControllerRef.YOU),
                                ("amount", _party_count()),
                            )
                        ),
                    ),
                )
            ),
        )
    )


def _build_minus_x_opponent(m: re.Match[str]) -> SentenceOutcome:
    """``When this creature enters, target creature an opponent controls
    gets -X/-X until end of turn, where X is the number of creatures in
    your party.``"""
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_etb_event(),
            condition=None,
            effect=Atom(
                verb=Verb.MODIFY_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", _target_creature_an_opponent_controls()),
                        ("power", PtDelta(PtDirection.DECREASE, _party_count())),
                        ("toughness", PtDelta(PtDirection.DECREASE, _party_count())),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )


def _build_x_to_creature_or_pw(m: re.Match[str]) -> SentenceOutcome:
    """``When this creature enters, it deals X damage to target creature
    or planeswalker, where X is the number of creatures in your party.``"""
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=_etb_event(),
            condition=None,
            effect=Atom(
                verb=Verb.DEAL_DAMAGE,
                args=AtomArgs(
                    pairs=(
                        (
                            "target",
                            Selector(
                                QConst(1),
                                SelectorMode.TARGET,
                                FOr(
                                    children=(
                                        FAtom(
                                            pred=FAtomPred.TYPE_EQ,
                                            string_value="Creature",
                                        ),
                                        FAtom(
                                            pred=FAtomPred.TYPE_EQ,
                                            string_value="Planeswalker",
                                        ),
                                    )
                                ),
                                zones=(
                                    Zone(
                                        kind=ZoneKind.BATTLEFIELD,
                                        controller=ControllerRef.ANY,
                                    ),
                                ),
                            ),
                        ),
                        ("amount", _party_count()),
                    )
                ),
            ),
        )
    )


def _build_look_top_x_plus_three(m: re.Match[str]) -> SentenceOutcome:
    """``Look at the top X cards of your library, where X is three plus
    the number of creatures in your party.``"""
    return EffectOutcome(
        effect=Atom(
            verb=Verb.LOOK_AT,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    (
                        "count",
                        QBin(op=QBinOp.ADD, left=QConst(3), right=_party_count()),
                    ),
                )
            ),
        )
    )


# ---------------------------------------------------------------------------
# Class signature
# ---------------------------------------------------------------------------


def _build_class_signature(m: re.Match[str]) -> SentenceOutcome:
    """``<Name> is also a Cleric, Rogue, Warrior, and Wizard.``: a static GRANT_TYPE on the self
    anchor (IS_SOURCE plus the printed name as NAME_CONTAINS, as in b7). The grant reaches
    party counts through the layers overlay; the card's own type line is untouched."""
    return AbilityOutcome(
        ability=StaticAbility(
            effect=Atom(
                verb=Verb.GRANT_TYPE,
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
                                            pred=FAtomPred.NAME_CONTAINS,
                                            string_value=m.group("name"),
                                        ),
                                    )
                                ),
                                zones=(
                                    Zone(
                                        kind=ZoneKind.BATTLEFIELD,
                                        controller=ControllerRef.ANY,
                                    ),
                                ),
                            ),
                        ),
                        ("types", ("Cleric", "Rogue", "Warrior", "Wizard")),
                    )
                ),
            )
        )
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


TEMPLATES: Final[tuple[Template, ...]] = (
    _template(
        "B8-party-discount",
        "party {1} discount (spell/ability)",
        r"^This (?:spell|ability) costs \{1\} less to (?:cast|activate) "
        r"for each creature in your party\.$",
        _build_discount,
    ),
    _template(
        "B8-party-token-etb",
        "Kor Warrior token per party member (ETB)",
        r"^When this creature enters, create a 1/1 white Kor Warrior "
        r"creature token for each creature in your party\.$",
        _build_token_per_party,
    ),
    _template(
        "B8-party-counter-self-etb",
        "+1/+1 counters on self per party member (ETB)",
        r"^When this creature enters, put a \+1/\+1 counter on it for each "
        r"creature in your party\.$",
        _build_counter_self_per_party,
    ),
    _template(
        "B8-party-attack-pt",
        "self +1/+0 attacking per party member",
        r"^Whenever this creature attacks, it gets \+1/\+0 until end of turn "
        r"for each creature in your party\.$",
        _build_attack_pt_per_party,
    ),
    _template(
        "B8-party-add-red-etb",
        "add red per party member (ETB)",
        r"^When this creature enters, add \{R\} for each creature in your "
        r"party\.$",
        _build_add_red_per_party,
    ),
    _template(
        "B8-party-pt-target-etb",
        "target creature +1/+1 per party member (ETB)",
        r"^When this creature enters, target creature gets \+1/\+1 until end "
        r"of turn for each creature in your party\.$",
        _build_pt_target_per_party,
    ),
    _template(
        "B8-party-gain-life-etb",
        "gain 2 life per party member (ETB)",
        r"^When this creature enters, you gain 2 life for each creature in "
        r"your party\.$",
        _build_gain_life_per_party,
    ),
    _template(
        "B8-party-counter-referent",
        "+1/+1 counter on the referent per party member",
        r"^Put a \+1/\+1 counter on it for each creature in your party\.$",
        _build_counter_referent_per_party,
    ),
    _template(
        "B8-party-twice-damage",
        "self deals damage equal to twice the party",
        r"^Practiced Tactics deals damage to that creature equal to twice "
        r"the number of creatures in your party\.$",
        _build_name_damage_twice,
    ),
    _template(
        "B8-full-pt-indestructible",
        "full party: +1/+0 and indestructible",
        r"^At the beginning of combat on your turn, if you have a full "
        r"party, creatures you control get \+1/\+0 and gain indestructible "
        r"until end of turn\.$",
        _build_full_pt_indestructible,
    ),
    _template(
        "B8-full-pt-flying",
        "full party: target gets +1/+1 and gains flying",
        r"^At the beginning of combat on your turn, if you have a full "
        r"party, target creature gets \+1/\+1 and gains flying until end "
        r"of turn\.$",
        _build_full_pt_flying,
    ),
    _template(
        "B8-full-choose-nonland",
        "full party: choose target nonland permanent an opponent controls",
        r"^At the beginning of combat on your turn, if you have a full "
        r"party, choose target nonland permanent an opponent controls\.$",
        _build_full_choose_nonland,
    ),
    _template(
        "B8-full-grant-draw",
        "full party: creatures gain the combat-damage draw trigger",
        r"^At the beginning of combat on your turn, if you have a full "
        r'party, creatures you control gain "Whenever this creature deals '
        r'combat damage to a player, draw a card" until end of turn\.$',
        _build_full_grant_draw,
    ),
    _template(
        "B8-full-free-cast",
        "full party: free-cast a CMC<=4 spell from hand",
        r"^If you have a full party, you may cast a spell with mana value "
        r"4 or less from your hand without paying its mana cost\.$",
        _build_full_free_cast,
    ),
    _template(
        "B8-party-scry-x",
        "scry X = party (ETB)",
        r"^When this creature enters, scry X, where X is the number of "
        r"creatures in your party\.$",
        _build_scry_x_party,
    ),
    _template(
        "B8-party-up-to-two-x",
        "up to two targets +X/+X = party",
        r"^Up to two target creatures each get \+X/\+X until end of turn, "
        r"where X is the number of creatures in your party\.$",
        _build_up_to_two_x,
    ),
    _template(
        "B8-party-lose-gain-x",
        "each opponent loses X, you gain X = party (ETB)",
        r"^When this creature enters, each opponent loses X life and you "
        r"gain X life, where X is the number of creatures in your party\.$",
        _build_lose_gain_x,
    ),
    _template(
        "B8-party-minus-x-opponent",
        "opponent's creature -X/-X = party (ETB)",
        r"^When this creature enters, target creature an opponent controls "
        r"gets -X/-X until end of turn, where X is the number of creatures "
        r"in your party\.$",
        _build_minus_x_opponent,
    ),
    _template(
        "B8-party-x-creature-or-pw",
        "deals X damage to creature or planeswalker (ETB)",
        r"^When this creature enters, it deals X damage to target creature "
        r"or planeswalker, where X is the number of creatures in your "
        r"party\.$",
        _build_x_to_creature_or_pw,
    ),
    _template(
        "B8-party-look-top-x",
        "look at top X = 3 + party",
        r"^Look at the top X cards of your library, where X is three plus "
        r"the number of creatures in your party\.$",
        _build_look_top_x_plus_three,
    ),
    _template(
        "B8-party-class-signature",
        "is also a Cleric, Rogue, Warrior, and Wizard",
        r"^(?P<name>[A-Z][^.\n]*?) is also a Cleric, Rogue, Warrior, and "
        r"Wizard\.$",
        _build_class_signature,
    ),
)
