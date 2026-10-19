"""Bucket B8 — the ZND-3 party family (spec KNOWLEDGE/2026-10-18/107 §3).

ONE new grammar node does all the quantity work: ``QPartyCount`` (spec
/107 §3.1) — "the number of creatures in your party", i.e. the number of
creatures you control whose type line contributes a DISTINCT party class
(Cleric / Rogue / Warrior / Wizard, up to one each — CR 702.158 "party
ability"). The census (distinct-class, overlay-aware) lives in the
evaluator (executor/quantity.py) exactly like the sanctum's distinct-
color census; the Selector pinned here is the pure POPULATION axis:
TYPE_EQ Creature ∧ CONTROLLER_IS YOU ∧ battlefield (the audited
``_shrine_count`` idiom, spec /107 §3.1).

Twenty-three templates carry the 35 register rows:

* **T1 (11 rows)** — the {1} discount. Costs are cards' static
  properties, so the encoding is the B5c-sanctum ``CostModifier`` sibling
  node (b5c:2569 mirror), never an ability-internal cost patch.
* **T2 (8 rows)** — for-each scaled effects: token / counter / PT /
  mana / life / damage quantities = ``QBin(MUL, unit, QPartyCount)``.
  Practiced Tactics' "twice the number" is the QBin INSIDE the
  DEAL_DAMAGE amount (spec /107 T2: not a damage-multiplier lane).
* **T3 (5 rows)** — full-party heads: four combat-start triggers whose
  intervening "if" is ``FAnd`` of four CONTROLLER_COUNT_GE × SUBTYPE_EQ
  tests (adherent_of_hope's condition shape, b2a:1654; zero new
  predicates) plus Coveted Prize's spell-level ``Conditional`` free cast
  (empty-cost CAST waiver, b5c:2496 idiom).
* **T4 (7 rows)** — X-announcement substitutions: ", where X is the
  number of creatures in your party" binds X := QPartyCount (the
  ``_shrine_count`` substitution idiom, b2a:199).
* **T5 (3 rows)** — "<Name> is also a Cleric, Rogue, Warrior, and
  Wizard.": static ``GRANT_TYPE`` on the self anchor (IS_SOURCE +
  NAME_CONTAINS twin, the b7 self-name anaphor law: the semantic anchor
  is IS_SOURCE, the printed name is only the gate twin). §11 golden: a
  granted class MOVES other cards' party counts — the restricted card's
  encoding stays untouched (board-separation law).
* **T6 (0 rows)** — WITHDRAWN post-gate (see ZND-3f): the reveal-count
  template compiled but executes as a library look (FM2) — a build-only
  test hid it; the row stays UNPARSED until the REVEAL zone-role lane
  lands. Compilation is not representation (Gate law).

FM6 SHARED-TAIL LAW: none of these tails is a ``templates_b6._TAIL_
BUILDERS`` key (every one is quantity-bearing), so each effect is built
locally from the shared b6 anchors (``_etb_event``, ``_self_selector``,
``_referent_target_creature``) — the shared keys are never forked.

Gap ledger (ZND-3 law: these stay UNPARSED, no silent partials):

* **ZND-3d** "Counter target noncreature spell unless its controller
  pays {1} plus an additional {1} for each creature in your party."
  (Concerted Defense) — unless-pay amounts resolve in the PAYER's seat
  (verbs.py:1926–1928); the party would count the victim's board. Needs
  a controller-frozen amount lane — engine item, deferred.
* **ZND-3e** "Archpriest of Iona's power is equal to the number of
  creatures in your party." + "Equipped creature gets +1/+0 for each
  creature in your party and has menace." (Ravager's Mace) — static-layer
  values over a mutable census need the layer re-resolution lane
  (layers.py:740–741); encoding early would mint live wrong-power boards.
* **ZND-3f** "When this creature enters, target opponent reveals a number
  of cards from their hand equal to the number of creatures in your
  party." (Acquisitions Expert) — the REVEAL executor has NO zone role:
  ``Verb.REVEAL`` falls into ``_look`` (verbs.py:1102–1114) reading
  ZONE_LIBRARY, so a from-hand reveal EXECUTES as a library peek — a
  materially different game effect. The count lane works (generic
  ``amount()``); the missing piece is a HAND-zone role on REVEAL
  (engine lane). T6's template was WITHDRAWN (gate FM2): compiled-but-
  misexecuting rows do not count.
* **ZND-3g** "spell with mana value 4 or less" free-cast (Coveted Prize,
  T3): the CHOOSE-from-hand ask gates CMC_LE≤4 over HAND — lands sit in
  hand at CMC 0 and ride the candidate menu (gate FM6). No SPELL-kind
  FAtomPred exists at all: a §8/§10 tokenizer gap (phantom candidates),
  NOT a one-line filter — new predicate before the next set round.

Lossy notes (C11 class, verbatim per house convention):

* Nimble Trapfinder "to a player" — CombatDamageEvent exposes no
  recipient role; same documented drop as the B2b Jeskai Elder lane.
* Coveted Prize: "a spell with mana value 4 or less" is encoded
  CMC_LE≤4 on the CHOOSE-from-hand selector; whether the CAST resolves
  stays the open OptionalEffect decision (C16).
"""

from __future__ import annotations

import re
from typing import Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    CombatDamageEvent,
    Conditional,
    ControllerRef,
    Cost,
    CostDeltaReduceGeneric,
    CostModifier,
    CounterKind,
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
from MTG_bot.core.compiler.templates_b6 import (
    _etb_event,
    _referent_target_creature,
    _self_selector,
)

_BUCKET: Final = "B8"
_PRIORITY: Final[int] = 114  # above B7 (112): the party family is claimed by
# no other module; the order only pins it (B7 convention).

#: The four party classes (CR 702.158). Duplicated from the evaluator's
#: PARTY_CLASSES only in PROSE — templates never re-derive the census.


# ---------------------------------------------------------------------------
# Shared party structure (spec /107 §3.1: ONE node reused by every template)
# ---------------------------------------------------------------------------


def _party_count() -> QPartyCount:
    """``the number of creatures in your party`` → QPartyCount over the
    population axis the spec pins: TYPE_EQ Creature ∧ CONTROLLER_IS YOU ∧
    battlefield (audited ``_shrine_count`` population idiom)."""
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
            Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
        )
    )


def _full_party() -> Filter:
    """``you have a full party`` — the AND of four per-class existence
    claims (spec /107 §3.1, zero new predicates): CONTROLLER_COUNT_GE
    count=1 over SUBTYPE_EQ each class, the adherent_of_hope condition
    shape (b2a:1654). True iff the census hits all four classes."""
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
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _target_creature_on_battlefield() -> Selector:
    """Plain "target creature" — controller ANY is CR-correct (a party
    spell may target any creature on the battlefield); named for what it
    pins, not for the chooser (gate FM7 rename)."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
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
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _combat_event() -> TurnPhaseEvent:
    """``At the beginning of combat on your turn`` (b2a:295 idiom)."""
    return TurnPhaseEvent(
        phase=Phase.COMBAT,
        actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
    )


def _scaled(unit: int) -> QBin:
    """``<unit> for each creature in your party`` = QBin(MUL, unit, party)."""
    return QBin(op=QBinOp.MUL, left=QConst(unit), right=_party_count())


# ---------------------------------------------------------------------------
# T1 — the {1} discount (11 rows: Spellbinder's-Spell shape, shrine lane)
# ---------------------------------------------------------------------------


def _build_discount(m: re.Match[str]) -> SentenceOutcome:
    """``This spell costs {1} less to cast for each creature in your
    party.`` + the ability/activate variant — CostModifier sibling node,
    filter=IS_SOURCE (the printed "This spell"/"This ability" anchor,
    b5c:2569 sanctum mirror; the discount rides the CARD, so the
    legality lane prices it for free)."""
    return AbilityOutcome(
        ability=CostModifier(
            filter=FAtom(pred=FAtomPred.IS_SOURCE),
            controller_ref=ControllerRef.YOU,
            delta=CostDeltaReduceGeneric(amount=_scaled(1)),
        )
    )


# ---------------------------------------------------------------------------
# T2 — for-each scaled effects (8 rows)
# ---------------------------------------------------------------------------


def _build_token_per_party(m: re.Match[str]) -> SentenceOutcome:
    """``When this creature enters, create a 1/1 white Kor Warrior creature
    token for each creature in your party.`` — the b6 TokenSpec idiom with
    the count role scaled by the census."""
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
                                color="W",
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
    creature in your party.`` — self anchor, count = census."""
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
    for each creature in your party.`` — the alpine-houndmaster attack
    shape (b2b:808): power magnitude = 1 × census, toughness explicit
    zero delta (the b5a QConst(0) losslessness rule)."""
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
    party.`` — ADD_MANA amount = census (sanctum fruitful-harvest shape,
    b2a:713)."""
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
    turn for each creature in your party.`` — per-target scaling: every
    target receives unit × census (the census is ability-scoped, not
    per-target)."""
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
    """``Put a +1/+1 counter on it for each creature in your party.``
    (Strength of Solidarity s2) — "it" is the first sentence's designated
    creature: the R7-1 referent="target" neutral-zone convention
    (b6 _referent_target_creature, Gloom-Sower sibling). Assembly note:
    non-continuation second sentence lands card-level (b5c convention)."""
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
    the number of creatures in your party.`` — DEAL_DAMAGE whose AMOUNT is
    QBin(MUL, 2, party) (spec /107 T2: inside the amount, NOT a damage
    multiplier). Dealer omitted = the b6 source-default convention; the
    printed self-name is pure English anaphor for the resolving spell.
    "that creature" rides the referent="target" lane (s1 designated the
    attacker/blocker; assembly note as above)."""
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
# T3 — full-party heads (5 rows)
# ---------------------------------------------------------------------------


def _build_full_pt_indestructible(m: re.Match[str]) -> SentenceOutcome:
    """``At the beginning of combat on your turn, if you have a full
    party, creatures you control get +1/+0 and gain indestructible until
    end of turn.`` — combat trigger + FAnd-of-4 condition (adherent
    shape); effect Seq of the PT pump and the keyword grant."""
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
    flying until end of turn.`` — same combat+condition head; effect Seq
    reuses the ONE target selector across both steps (b5b:960 shape)."""
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
    opponent controls.`` — Verb.CHOOSE records the pick (R7-1); the pool
    is battlefield permanents an opponent controls (FNot TYPE_EQ Land).
    The follow-up legality sentence is a SEPARATE register row (not this
    tranche — its lane never landed; the choice itself is the decision)."""
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
                                Zone(
                                    kind=ZoneKind.BATTLEFIELD,
                                    controller=ControllerRef.ANY,
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
    of turn.`` — GRANT_ABILITY of a TriggeredAbility (b5c:683 precedent);
    the quoted trigger is the Jeskai-Elder event shape, and "to a player"
    is THAT lane's documented lossy drop (CombatDamageEvent carries no
    recipient role). Inside the quotes there is no "may": the draw is
    forced."""
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
                                event=CombatDamageEvent(
                                    filter=FAtom(pred=FAtomPred.IS_SOURCE)
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
    or less from your hand without paying its mana cost.`` (Coveted Prize
    s2) — spell-level Conditional over the empty-cost CAST-waiver idiom
    (b5c:2496): OptionalEffect keeps "may" the open decision, the CHOOSE
    selector over your hand with the CMC_LE≤4 gate keeps "which spell"
    open, and the waiver is Cost(parts=())."""
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
                                    Zone(
                                        kind=ZoneKind.HAND,
                                        controller=ControllerRef.YOU,
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
# T4 — X-announcement substitutions (7 rows; X := QPartyCount)
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
    X is the number of creatures in your party.`` — "up to two" is the
    C17 QAtMost(2) TARGET designation; +X/+X binds X to the census."""
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
                            Zone(
                                kind=ZoneKind.BATTLEFIELD,
                                controller=ControllerRef.ANY,
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
    gain X life, where X is the number of creatures in your party.`` —
    the sanctum-stone-fangs Seq shape with the census as amount."""
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
    or planeswalker, where X is the number of creatures in your party.`` —
    dealer omitted (source default), FOr type menu on the target."""
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
                                Zone(
                                    kind=ZoneKind.BATTLEFIELD,
                                    controller=ControllerRef.ANY,
                                ),
                            ),
                        ),
                        ("amount", _party_count()),
                    )
                ),
            ),
        )
    )


def _build_four_and_x_controller(m: re.Match[str]) -> SentenceOutcome:
    """``Synchronized Spellcraft deals 4 damage to target creature and X
    damage to that creature's controller, where X is the number of
    creatures in your party.`` — Seq of two damage atoms; the second
    target is the controller-of-the-target fold: the 16a designation face
    (selectors.py:437-448) — a TARGET-mode Selector with a PLAYER-side
    zone reads the card designation's controller (Brash Taunter's
    compiled echo), so the one "target creature" designation means BOTH
    the creature and its player."""
    return EffectOutcome(
        effect=Seq(
            steps=(
                Atom(
                    verb=Verb.DEAL_DAMAGE,
                    args=AtomArgs(
                        pairs=(
                            ("target", _target_creature_on_battlefield()),
                            ("amount", QConst(4)),
                        )
                    ),
                ),
                Atom(
                    verb=Verb.DEAL_DAMAGE,
                    args=AtomArgs(
                        pairs=(
                            (
                                "target",
                                Selector(
                                    QConst(1),
                                    SelectorMode.TARGET,
                                    FAnd(children=()),
                                    Zone(
                                        kind=ZoneKind.PLAYER,
                                        controller=ControllerRef.ANY,
                                    ),
                                ),
                            ),
                            ("amount", _party_count()),
                        )
                    ),
                ),
            )
        )
    )


def _build_look_top_x_plus_three(m: re.Match[str]) -> SentenceOutcome:
    """``Look at the top X cards of your library, where X is three plus
    the number of creatures in your party.`` — the b5b look-at-top lane
    with the additive census amount."""
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
# T5 — class signature (3 rows)
# ---------------------------------------------------------------------------


def _build_class_signature(m: re.Match[str]) -> SentenceOutcome:
    """``<Name> is also a Cleric, Rogue, Warrior, and Wizard.`` — static
    GRANT_TYPE on the self anchor (b7 self-name law: IS_SOURCE is the
    semantic anchor, the printed name the NAME_CONTAINS gate twin).
    §11 golden: this grant MOVES other cards' party census through the
    layers overlay; the granted card's own encoding stays untouched
    (board-separation law)."""
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
                                Zone(
                                    kind=ZoneKind.BATTLEFIELD,
                                    controller=ControllerRef.ANY,
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
        "B8-party-four-and-x-controller",
        "4 to creature and X to its controller",
        r"^Synchronized Spellcraft deals 4 damage to target creature and X "
        r"damage to that creature's controller, where X is the number of "
        r"creatures in your party\.$",
        _build_four_and_x_controller,
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
