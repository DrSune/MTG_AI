"""B5a bucket templates — 60 templates covering 64 of 90 B5a shapes.

Bucket input: ``/tmp/opencode/phase1_buckets/B5a.json`` (90 normalized shape
keys → ``[card, sentence]`` pairs; sentences carry *concrete* numbers, keys
carry ``N`` placeholders).  Templates fullmatch the **concrete** oracle
sentence, never the normalized key.

Coverage (90 = 64 template + 23 rule-reminder + 3 uncovered):

- **64 template-covered shapes** (60 templates; the basic-land
  ``({T}: Add {C}.)`` family is one template for five shapes):
  basic-land tap abilities, ADD_MANA, static P/T grants, counter-spell,
  token creation, keyword rule-reminder sentences (Deathtouch/Defender/
  Double strike), DESTROY (incl. POWER_GE, T3 round A), EXILE, activated
  discard-tap, DRAW (+QCount), DISCARD, LOSE_LIFE,
  GRANT_ABILITY/GRANT_TYPE compound statics (incl. gain-life counter
  trigger, T3 round F), SET_PT with QBin MUL ("double the power"),
  Battalion keyword outcome (T3: params supplied by the template),
  END_TURN, Equip, equipped-P/T, additional-cost (discard/sacrifice),
  conditional static (Gnarled Sage), activation gate
  (Caged Zombie, Celestial Enforcer), counter-unless-pays
  (Miscast, Lofty Denial), round-6 batch: ZONE_COUNT_GE conditional static
  (Thieves' Guild Enforcer), TURN_OF static grant (Radha) and TURN_OF
  CostModifier (Discontinuity), blocked-side PREVENT_EFFECT
  (Ghostly Pilferer discard, Faith's Fetters attack+block Seq — C11
  lossy), untap-prevention on enchanted creature (Capture Sphere, lossy),
  and grammar round 11 C3: the each-opponent "who can't" life-loss gate
  (Waker +1 tail — Conditional + EachPlayer over a post-discard hand
  count, payment-failure row retired).
- **23 rule-reminder shapes** — fully parenthesised sentences consumed by
  the compiler's ``_is_rule_reminder`` before template matching (no
  template needed; verified in tests).
- **3 uncovered shapes** — the library-top all-abilities grant
  (ability-introspection, R10) plus the two choose-opener modal headers
  (compiler built-in, not templates). Round 11 C3 retired the
  payment-failure row ("who can't") as a Conditional + EachPlayer gate.
  Recorded in ``UNCOVERED`` below and pinned by tests.

Conventions (documented build decisions):

- ``this creature`` / ``this Equipment`` / self-referent targets are
  encoded as ``Selector(CHOOSE, QConst(1), FAtom(IS_SOURCE), zone)`` — a
  semantic self-reference, never a hardcoded card name (shape #86).
- ``enchanted creature`` is
  ``Selector(ALL, QUnbounded, FAnd(TYPE_EQ Creature, IS_ATTACHED_TO_SOURCE),
  Zone(BATTLEFIELD, ANY))``.
- ``+N/+N`` prints as ``PtDelta(INCREASE, QConst(N))`` — a printed ``+0``
  stays ``QConst(0)`` (lossless w.r.t. oracle text, shape #42).
- ``Add two mana of any one color`` → ``ADD_MANA(color="ANY")`` (round 8 /
  C-3 repair; colorless "{C}" rows keep ``"C"`` — shape #34).
- Token colors (round 8 / C-2): the red Goblin Wizard populates
  ``color="R"``; the blue-and-red Weird stays dropped — ``TokenSpec.color``
  is a single-color ``str`` (bichrome needs a color-set field, R9).
- ``Each player loses N life`` → ``LOSE_LIFE(controller=ANY)`` (shape #72).
- ``Counter target spell`` → ``COUNTER_SPELL`` with ``Zone(STACK, ANY)``
  carrying the "spell" semantics (shape #49).
- The Equip sentence (#83) is an ``ActivatedAbility``; the "Equip only as
  a sorcery" speed restriction is unrepresentable (gap, documented in
  test).

PC-3: every B5a concrete sentence fullmatches **at most one** template
(patterns are pairwise disjoint by construction); verified in tests.
"""

from __future__ import annotations

import re
from typing import Callable, Final

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ActivatedAbility,
    ActivationWindow,
    Conditional,
    ControllerRef,
    Cost,
    CostDeltaReduceGeneric,
    CostDeltaReduceMana,
    CostDiscard,
    CostManaGeneric,
    CostModifier,
    CostSacrifice,
    CostTap,
    CounterKind,
    CreatureDiesEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    DurationEot,
    DurationPermanent,
    DurationWhileCondition,
    EachPlayer,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    LifeGainedEvent,
    PtDelta,
    PtDirection,
    QBin,
    QBinOp,
    QConst,
    QCount,
    QProp,
    QPropField,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    TapStateEvent,
    TokenSpec,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    ZonePosition,
)
from MTG_bot.core.compiler.templates import (
    AdditionalCostOutcome,
    AbilityOutcome,
    ActivationGateOutcome,
    EffectOutcome,
    KeywordOutcome,
    SentenceOutcome,
    Template,
)

_BUCKET = "B5a"
_PRIORITY = 50


# ---------------------------------------------------------------------------
# Shared node builders
# ---------------------------------------------------------------------------


def _self_selector(zone: Zone) -> Selector:
    """Selector for ``this <permanent>`` — the source of the ability.

    E1 FOLD-B (/65): a BATTLEFIELD seat passed here folds onto the shared
    CONTROLLER_IS axis exactly like an inline Selector zone — BF-ANY plus
    the seat atom, so the idiom keeps one encoding shape."""
    filt = FAtom(pred=FAtomPred.IS_SOURCE)
    if zone.kind is ZoneKind.BATTLEFIELD and zone.controller is not ControllerRef.ANY:
        filt = FAnd(
            children=(
                filt,
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=zone.controller),
            )
        )
        zone = Zone(kind=zone.kind, controller=ControllerRef.ANY)
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        filt,
        zone,
    )


def _enchanted_creature() -> Selector:
    """Selector for ``enchanted creature`` (the source's attachment target)."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.IS_ATTACHED_TO_SOURCE),
            )
        ),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _pt_delta(m: re.Match[str], group: int) -> PtDelta:
    """``+N`` printed in oracle text → INCREASE by ``QConst(N)``."""
    return PtDelta(PtDirection.INCREASE, QConst(int(m.group(group))))


def _draw_controller() -> ControllerRef:
    return ControllerRef.YOU


# ---------------------------------------------------------------------------
# Build functions (one per template)
# ---------------------------------------------------------------------------


def _build_land_add(m: re.Match[str]) -> SentenceOutcome:
    color = m.group(1)
    atom = Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(1)),
                ("color", color),
            )
        ),
    )
    return AbilityOutcome(
        ability=ActivatedAbility(cost=Cost(parts=(CostTap(),)), effect=atom)
    )


def _build_add_six(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(6)),
                ("color", m.group(1)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_add_any_color(m: re.Match[str]) -> SentenceOutcome:
    # "any one color" = color="ANY" (grammar round 8, R8-3 / C-3 repair):
    # the player picks a color at resolution; "C" stays colorless-only.
    atom = Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(2)),
                ("color", "ANY"),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_attacking_pt(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QUnbounded(),
                        SelectorMode.ALL,
                        FAnd(
                            children=(
                                FAtom(
                                    pred=FAtomPred.TYPE_EQ,
                                    string_value="Creature",
                                ),
                                FAtom(pred=FAtomPred.IS_ATTACKING),
                                FAtom(
                                    pred=FAtomPred.CONTROLLER_IS,
                                    who=ControllerRef.YOU,
                                ),
                            )
                        ),
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
                ("power", _pt_delta(m, 1)),
                ("toughness", _pt_delta(m, 2)),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(effect=atom))


def _build_counter_spell(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.COUNTER_SPELL,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAnd(children=()),
                        Zone(kind=ZoneKind.STACK, controller=ControllerRef.ANY),
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_gnarled_sage(m: re.Match[str]) -> SentenceOutcome:
    # "As long as you've drawn two or more cards this turn, this creature
    # gets +N/+N and has vigilance." — conditional static: the whole
    # Seq(MODIFY_PT, GRANT_ABILITY) is gated on the draw-count condition.
    self_sel = _self_selector(
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY)
    )
    pt = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", self_sel),
                ("power", _pt_delta(m, 1)),
                ("toughness", _pt_delta(m, 2)),
            )
        ),
    )
    grant = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", self_sel),
                ("ability", KeywordAbility(keyword=Keyword.VIGILANCE, params=())),
            )
        ),
    )
    return AbilityOutcome(
        ability=StaticAbility(
            effect=Seq(steps=(pt, grant)),
            condition=FAtom(
                pred=FAtomPred.CARDS_DRAWN_THIS_TURN_GE,
                count=QConst(2),
                who=ControllerRef.YOU,
            ),
        )
    )


def _build_activate_only_death(m: re.Match[str]) -> SentenceOutcome:
    # "Activate only if a creature died this turn." — activation gate.
    return ActivationGateOutcome(condition=FAtom(pred=FAtomPred.DIED_THIS_TURN))


def _build_activate_only_flying(m: re.Match[str]) -> SentenceOutcome:
    # "Activate only if you control a creature with flying." — activation
    # gate (control-based).
    return ActivationGateOutcome(
        condition=FAtom(
            pred=FAtomPred.CONTROLLER_COUNT_GE,
            inner_filter=FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING),
                )
            ),
            count=QConst(1),
        )
    )


def _counter_unless_atom(m: re.Match[str], target_filter: Filter) -> Atom:
    # COUNTER_SPELL with an optional "unless its controller pays {N}" cost.
    return Atom(
        verb=Verb.COUNTER_SPELL,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        target_filter,
                        Zone(kind=ZoneKind.STACK, controller=ControllerRef.ANY),
                    ),
                ),
                (
                    "unless",
                    Cost(parts=(CostManaGeneric(amount=QConst(int(m.group(1)))),)),
                ),
            )
        ),
    )


def _build_activate_only_sorcery(m: re.Match[str]) -> SentenceOutcome:
    """``Activate only as a sorcery.`` (Liliana's Steward s2 tail — grammar
    round 10 b5a row, R10-1): the BARE activation-timing gate. The outcome
    carries ONLY the R9-1 ``window`` slot; the compiler's slot-disjoint
    attach (C25) rewrites ``timing`` on the nearest preceding
    ActivatedAbility whose timing is still free — Steward's s1
    ``{T}, Sacrifice this creature:`` ability built by
    B5c-cost-sacrifice-discard, across the sentence boundary. PC-3: the
    anchor is disjoint from the Speaker compound-gate row (that pattern
    requires its "if you have at least N life" clause).

    C16: none — the gate is a legality restriction, fully forced; the
    activation PAY decision lives in the attached s1 ability."""
    return ActivationGateOutcome(window=ActivationWindow.SORCERY)


def _build_counter_unless_sps(m: re.Match[str]) -> SentenceOutcome:
    # "Counter target instant or sorcery spell unless its controller pays
    # {N}."
    sps_filter = FOr(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Instant"),
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Sorcery"),
        )
    )
    return EffectOutcome(effect=_counter_unless_atom(m, sps_filter))


def _build_counter_unless_spell(m: re.Match[str]) -> SentenceOutcome:
    # "Counter target spell unless its controller pays {N}."
    return EffectOutcome(effect=_counter_unless_atom(m, FAnd(children=())))


def _grave_count_quantity() -> QCount:
    """Number of instant and sorcery cards in your graveyard."""
    return QCount(
        Selector(
            QUnbounded(),
            SelectorMode.ALL,
            FOr(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Instant"),
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Sorcery"),
                )
            ),
            Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
        )
    )


def _build_weird_token(m: re.Match[str]) -> SentenceOutcome:
    x = _grave_count_quantity()
    atom = Atom(
        verb=Verb.CREATE_TOKEN,
        args=AtomArgs(
            pairs=(
                (
                    "tokens",
                    TokenSpec(
                        name="Weird",
                        type_line="Creature — Weird",
                        types=("Creature",),
                        subtypes=("Weird",),
                        power=x,
                        toughness=x,
                        # GAP (stays, 8-B skip): the Weird is blue AND red;
                        # TokenSpec.color is a single-color str (C-2 scope),
                        # so a bichrome token cannot be populated faithfully
                        # without inventing a color-set format (R9 candidate).
                        keywords=(),
                        abilities=(),
                    ),
                ),
                ("count", QConst(1)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_goblin_wizard_tokens(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.CREATE_TOKEN,
        args=AtomArgs(
            pairs=(
                (
                    "tokens",
                    TokenSpec(
                        name="Goblin Wizard",
                        type_line="Creature — Goblin Wizard",
                        types=("Creature",),
                        subtypes=("Goblin", "Wizard"),
                        power=QConst(int(m.group(1))),
                        toughness=QConst(int(m.group(2))),
                        keywords=(Keyword.PROWESS,),
                        abilities=(),
                        color="R",  # C-2 repair (round 8): printed "red"
                    ),
                ),
                ("count", QConst(2)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_keyword_reminder(
    keyword: Keyword,
) -> Callable[[re.Match[str]], SentenceOutcome]:
    def _build(m: re.Match[str]) -> SentenceOutcome:
        return KeywordOutcome(keyword=keyword, params=())

    return _build


def _build_battalion(m: re.Match[str]) -> SentenceOutcome:
    # T5-E (2026-10-10, clause-audit residual closure): the printed
    # trigger leg COMPILES. This sentence used to emit only a
    # KeywordOutcome token whose trigger the r20a binder synthesised
    # behind the encoding (a §10 phantom: token visible, semantics
    # hidden in executor code). The leg mirrors
    # ``binding._keyword_node("BATTALION")`` — DeclareAttackersEvent
    # (IS_SOURCE) -> PUT_COUNTER +1/+1 on self — and carries the
    # CR 508.2 group-of-three as the trigger CONDITION
    # (CONTROLLER_COUNT_GE over attacking creatures; the binder gated
    # the same declaration population at queue time by journal read).
    # No keyword token is emitted, so the record's keywords stay free
    # of BATTALION and the binder's synthetic keyword lane stays inert
    # for this card (no double-fire).
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=DeclareAttackersEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
            condition=FAtom(
                pred=FAtomPred.CONTROLLER_COUNT_GE,
                inner_filter=FAnd(
                    children=(
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        FAtom(pred=FAtomPred.IS_ATTACKING),
                    )
                ),
                count=QConst(3),
            ),
            effect=Atom(
                verb=Verb.PUT_COUNTER,
                args=AtomArgs(
                    pairs=(
                        ("count", QConst(1)),
                        ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                        (
                            "target",
                            Selector(
                                count=QConst(1),
                                mode=SelectorMode.CHOOSE,
                                filter=FAtom(pred=FAtomPred.IS_SOURCE),
                                zone=Zone(
                                    kind=ZoneKind.BATTLEFIELD,
                                    controller=ControllerRef.ANY,
                                ),
                            ),
                        ),
                    )
                ),
            ),
        )
    )


def _build_destroy(m: re.Match[str], f: Filter, zone: Zone) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DESTROY,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(QConst(1), SelectorMode.TARGET, f, zone),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _destroy_target_filter(m: re.Match[str], extra: tuple[Filter, ...]) -> Filter:
    """``target creature [with extra conjuncts]`` — the AND-builder for the
    destroy lanes.

    R1a (ontology §6 V2′): a one-child ``FAnd`` is a phantom wrapper, so the
    builder returns the LONE CONJUNCT bare. Today's only caller always adds
    a ``POWER_GE`` conjunct, so the corpus bytes are unchanged; this is the
    emission-site guard V2′ relies on for future callers."""
    base: list[Filter] = [
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
    ]
    base.extend(extra)
    if len(base) == 1:
        return base[0]
    return FAnd(children=tuple(base))


def _build_destroy_power_ge(m: re.Match[str]) -> SentenceOutcome:
    f = _destroy_target_filter(
        m,
        (FAtom(pred=FAtomPred.POWER_GE, count=QConst(int(m.group(1)))),),
    )
    return _build_destroy(
        m, f, Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY)
    )


def _build_double_power(m: re.Match[str]) -> SentenceOutcome:
    # SET_PT with power = 2 * target.power, toughness = target.toughness,
    # duration = DurationEot.
    atom = Atom(
        verb=Verb.SET_PT,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
                (
                    "power",
                    QBin(
                        op=QBinOp.MUL,
                        left=QConst(2),
                        right=QProp(referent="target", field=QPropField.POWER),
                    ),
                ),
                (
                    "toughness",
                    QProp(referent="target", field=QPropField.TOUGHNESS),
                ),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_exile_target(m: re.Match[str], f: "object") -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        f,  # type: ignore[arg-type]
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_draw_one(m: re.Match[str]) -> SentenceOutcome:
    return EffectOutcome(
        effect=Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(("controller", _draw_controller()), ("amount", QConst(1)))
            ),
        )
    )


def _build_draw_two(m: re.Match[str]) -> SentenceOutcome:
    return EffectOutcome(
        effect=Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(("controller", _draw_controller()), ("amount", QConst(2)))
            ),
        )
    )


def _build_draw_three_then_discard(m: re.Match[str]) -> SentenceOutcome:

    draw = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(("controller", _draw_controller()), ("amount", QConst(3)))
        ),
    )
    discard = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("controller", _draw_controller()),
                (
                    "destination",
                    Zone(ZoneKind.GRAVEYARD, _draw_controller()),
                ),
                ("from", Zone(ZoneKind.HAND, _draw_controller())),
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAnd(children=()),
                        Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=Seq(steps=(draw, discard)))


def _build_draw_frantic_inventory(m: re.Match[str]) -> SentenceOutcome:

    first = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(("controller", _draw_controller()), ("amount", QConst(1)))
        ),
    )
    second_amount = QCount(
        Selector(
            QUnbounded(),
            SelectorMode.ALL,
            FAtom(pred=FAtomPred.NAME_EQ, string_value="Frantic Inventory"),
            Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
        )
    )
    second = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", _draw_controller()),
                ("amount", second_amount),
            )
        ),
    )
    return EffectOutcome(effect=Seq(steps=(first, second)))


def _build_trample_counter(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QUnbounded(),
                        SelectorMode.ALL,
                        FAnd(
                            children=(
                                FAtom(
                                    pred=FAtomPred.TYPE_EQ,
                                    string_value="Creature",
                                ),
                                FAtom(
                                    pred=FAtomPred.HAS_COUNTER,
                                    counter_kind=_PLUS_1_PLUS_1,
                                    count=QConst(int(m.group(2))),
                                ),
                                FAtom(
                                    pred=FAtomPred.CONTROLLER_IS,
                                    who=ControllerRef.YOU,
                                ),
                            )
                        ),
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
                ("ability", KeywordAbility(keyword=Keyword.TRAMPLE, params=())),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(effect=atom))


def _build_lose_life(m: re.Match[str]) -> SentenceOutcome:
    # "Each player" → ANY (the grammar has no ALL_PLAYERS referent;
    # ALL_OPPONENTS is the wrong set, so ANY is the honest choice).
    atom = Atom(
        verb=Verb.LOSE_LIFE,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.ANY),
                ("amount", QConst(int(m.group(1)))),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_each_opp_cant_lose_life(m: re.Match[str]) -> SentenceOutcome:
    """``Each opponent who can't loses 3 life.`` (Liliana Waker +1 tail;
    grammar round 11 C3 — the round-9 "payment-failure condition" UNCOVERED
    row retired: "who can't [discard a card]" resolves to a post-discard
    hand-count gate, the roadmap-sanctioned r21b reading (an opponent
    reduced to an empty hand by the preceding forced discard loses 3).
    EachPlayer(ref=ALL_OPPONENTS) rotates the CONTROLLER role (b2a/b2b
    precedent), so the YOU-relative predicate AND the YOU-relative
    LOSE_LIFE both rebind per opponent.  The sentence carries no ``may``
    and no continuation prefix: the compiler appends this mandatory tail
    to the preceding loyalty ability through the R11-1 loyalty-trailing
    path (``_append_mandatory_to_seq``)."""
    cant_discard = FNot(
        inner=FAtom(
            pred=FAtomPred.ZONE_COUNT_GE,
            who=ControllerRef.YOU,
            zone=Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
            inner_filter=FAnd(children=()),
            count=QConst(1),
        )
    )
    lose = Atom(
        verb=Verb.LOSE_LIFE,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(int(m.group("n")))),
            )
        ),
    )
    return EffectOutcome(
        effect=EachPlayer(
            ref=ControllerRef.ALL_OPPONENTS,
            effect=Conditional(pred=cant_discard, then_effect=lose),
        )
    )


def _enchant_pt(m: re.Match[str], groups: tuple[int, int]) -> Atom:
    return Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _enchanted_creature()),
                ("power", _pt_delta(m, groups[0])),
                ("toughness", _pt_delta(m, groups[1])),
            )
        ),
    )


def _build_enchant_pt_attacks(m: re.Match[str]) -> SentenceOutcome:

    pt = _enchant_pt(m, (1, 2))
    # "attacks each combat if able" → MANDATE_ATTACK; "each combat"
    # repetition is unrepresentable (single-mandate encoding; gap noted
    # in test).
    mandate = Atom(
        verb=Verb.MANDATE_ATTACK,
        args=AtomArgs(pairs=(("cards", _enchanted_creature()),)),
    )
    return AbilityOutcome(ability=StaticAbility(effect=Seq(steps=(pt, mandate))))


def _build_enchant_pt_death_draw(m: re.Match[str]) -> SentenceOutcome:

    pt = _enchant_pt(m, (1, 2))
    # LOSSY: "this creature" in the granted trigger is the enchanted
    # creature; the grammar has no SOURCE controller referent, so the
    # draw is attributed to YOU (documented).
    trigger = TriggeredAbility(
        event=CreatureDiesEvent(filter=FAtom(pred=FAtomPred.IS_SOURCE)),
        condition=None,
        effect=Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(
                    ("controller", _draw_controller()),
                    ("amount", QConst(1)),
                )
            ),
        ),
    )
    grant = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(pairs=(("target", _enchanted_creature()), ("ability", trigger))),
    )
    return AbilityOutcome(ability=StaticAbility(effect=Seq(steps=(pt, grant))))


def _build_enchant_gain_life(m: re.Match[str]) -> SentenceOutcome:
    # Enchanted creature gains a trigger: "Whenever you gain life, put
    # that many +1/+1 counters on this creature."
    # IS_SOURCE inside the granted ability = the enchanted creature.
    trigger = TriggeredAbility(
        event=LifeGainedEvent(
            actor=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
        ),
        condition=None,
        effect=Atom(
            verb=Verb.PUT_COUNTER,
            args=AtomArgs(
                pairs=(
                    (
                        "target",
                        _self_selector(
                            Zone(
                                kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY
                            )
                        ),
                    ),
                    (
                        "counter_kind",
                        CounterKind.PLUS_1_PLUS_1,
                    ),
                    (
                        "count",
                        QProp(referent="event", field=QPropField.AMOUNT),
                    ),
                )
            ),
        ),
    )
    grant = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(pairs=(("target", _enchanted_creature()), ("ability", trigger))),
    )
    return AbilityOutcome(ability=StaticAbility(effect=grant))


def _grant_keyword_atom(keyword: Keyword) -> Atom:
    return Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", _enchanted_creature()),
                ("ability", KeywordAbility(keyword=keyword, params=())),
            )
        ),
    )


def _build_enchant_pt_flying(m: re.Match[str]) -> SentenceOutcome:

    pt = _enchant_pt(m, (1, 2))
    grant = _grant_keyword_atom(Keyword.FLYING)
    return AbilityOutcome(ability=StaticAbility(effect=Seq(steps=(pt, grant))))


def _build_enchant_pt_trample(m: re.Match[str]) -> SentenceOutcome:

    pt = _enchant_pt(m, (1, 2))
    grant = _grant_keyword_atom(Keyword.TRAMPLE)
    return AbilityOutcome(ability=StaticAbility(effect=Seq(steps=(pt, grant))))


def _grant_type_atom(types: tuple[str, ...]) -> Atom:
    return Atom(
        verb=Verb.GRANT_TYPE,
        args=AtomArgs(pairs=(("target", _enchanted_creature()), ("types", types))),
    )


def _build_enchant_pt_firststrike_knight(m: re.Match[str]) -> SentenceOutcome:

    pt = _enchant_pt(m, (1, 2))
    grant_kw = _grant_keyword_atom(Keyword.FIRST_STRIKE)
    grant_type = _grant_type_atom(("Knight",))
    return AbilityOutcome(
        ability=StaticAbility(effect=Seq(steps=(pt, grant_kw, grant_type)))
    )


def _build_enchant_pt_flying_demon(m: re.Match[str]) -> SentenceOutcome:

    pt = _enchant_pt(m, (1, 2))
    grant_kw = _grant_keyword_atom(Keyword.FLYING)
    grant_type = _grant_type_atom(("Demon",))
    return AbilityOutcome(
        ability=StaticAbility(effect=Seq(steps=(pt, grant_kw, grant_type)))
    )


def _build_end_turn(m: re.Match[str]) -> SentenceOutcome:
    return EffectOutcome(effect=Atom(verb=Verb.END_TURN, args=AtomArgs(pairs=())))


def _build_equip(m: re.Match[str]) -> SentenceOutcome:
    # GAP: "Equip only as a sorcery" speed restriction is unrepresentable
    # (no speed-restriction construct on ActivatedAbility).
    attach = Atom(
        verb=Verb.ATTACH,
        args=AtomArgs(
            pairs=(
                (
                    "equipment",
                    _self_selector(
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY)
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
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
            )
        ),
    )
    return AbilityOutcome(
        ability=ActivatedAbility(
            cost=_parse_equip_cost(m.group("cost")),
            effect=attach,
        )
    )


def _parse_equip_cost(raw: str) -> Cost:
    """ZND-4 T1: parse the Equip activation mana ({1}, {2}{R}, {2}{G}, …)
    with the compiler's shared mana parser. Lazy import for the same
    reason as templates_b6._parse_kicker_cost (build() runs at compile
    time only); the returned node for "{1}" is byte-identical to the old
    hand-built CostManaGeneric(QConst(1)) — M21 tree diff 0."""
    from MTG_bot.core.compiler.compiler import parse_mana_cost

    cost = parse_mana_cost(raw)
    if cost is None:
        raise ValueError(f"_parse_equip_cost: unparseable equip cost {raw!r}")
    return cost


def _build_equipped_pt(m: re.Match[str]) -> SentenceOutcome:
    atom = _enchant_pt(m, (1, 2))
    return AbilityOutcome(ability=StaticAbility(effect=atom))


def _build_exile_self(m: re.Match[str]) -> SentenceOutcome:
    # "Exile Experimental Overload" — self-reference by name, encoded
    # semantically as IS_SOURCE (no hardcoded name).
    return _build_exile_target(
        m,
        FAtom(pred=FAtomPred.IS_SOURCE),  # type: ignore[arg-type]
    )


# +1/+1 counter kind alias
_PLUS_1_PLUS_1 = CounterKind.PLUS_1_PLUS_1


# ---------------------------------------------------------------------------
# Round-6 batch builders (conditional statics + restriction semantics)
# ---------------------------------------------------------------------------


def _bf_any() -> Zone:
    return Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY)


def _build_snoop_top_goblin_abilities(m: re.Match[str]) -> SentenceOutcome:
    """As long as the top card of your library is a Goblin card, this
    creature has all activated abilities of that card.  (Conspicuous
    Snoop s3; T5-E closure of the R10 ability-introspection DEFER.)

    The gate is the R6-2 ZONE_COUNT_GE predicate bounded to the library's
    TOP entry (T5-E gave the evaluator its OPTIONAL ``Zone.position``
    window, mirroring the selector idiom) with ``count=1`` — "the top
    card is a Goblin card".  The conditional-static half is the T3
    round-4 ``StaticAbility.condition`` lane (C9: the "as long as"
    predicate lives in the condition, never a duration approximation)
    exactly as the R10 note anticipated; only the GRANT_ABILITY payload
    had no vocabulary then.

    Payload materialization (gap ledger, doc /11 §DEFER stays open): the
    true reading grants the ABILITY SET of a dynamically-referenced card,
    which the closed IR cannot enumerate (no card→ability introspection
    atom; a live ActivatedAbility payload is also ruled out on runtime
    grounds — ``query.legal_activations`` surfaces granted rows in the
    ACTIVATE menu, which would re-pin the scenario/eval packs against an
    ability the top card may not even have).  The payload is therefore a
    registered-INERT static mirror of the card's own top-reveal static
    (s1, templates_b5b): a valid ``ability``-slot node (§8.3), invisible
    to ``granted_activated`` (filters to ActivatedAbility) and to the
    binder's granted-trigger drain (TriggeredAbility only).  The clause's
    observable content — the engine's free top-Goblin cast — stays owned
    by the s2 lane; the grant keeps the STATIC↔DYNAMIC trace (§10): the
    static encoding exists wherever the ask presents the top-Goblin cast."""
    top_goblin = FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Goblin")
    reveal_static = StaticAbility(
        effect=Atom(
            verb=Verb.REVEAL,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("count", QConst(1)),
                    ("duration", DurationPermanent()),
                )
            ),
        )
    )
    grant = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", _self_selector(_bf_any())),
                ("ability", reveal_static),
            )
        ),
    )
    return AbilityOutcome(
        ability=StaticAbility(
            effect=grant,
            condition=FAtom(
                pred=FAtomPred.ZONE_COUNT_GE,
                who=ControllerRef.YOU,
                zone=Zone(
                    kind=ZoneKind.LIBRARY,
                    controller=ControllerRef.YOU,
                    position=ZonePosition.TOP,
                ),
                inner_filter=top_goblin,
                count=QConst(1),
            ),
        )
    )


def _build_aslong_opp_gy_count(m: re.Match[str]) -> SentenceOutcome:
    """As long as an opponent has eight or more cards in their graveyard,
    this creature gets +2/+1 and has deathtouch.  (Thieves' Guild Enforcer;
    grammar round 6 R6-2 — ZONE_COUNT_GE carries who + zone + inner_filter
    + count; C9 — the "as long as" predicate lives in
    ``StaticAbility.condition``, never a duration approximation.  The
    literal "eight" follows the Gnarled Sage pattern idiom; the +N/+N
    digits are captured.)"""
    p, t = int(m.group("p")), int(m.group("t"))
    self_sel = _self_selector(_bf_any())
    pt = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", self_sel),
                ("power", PtDelta(PtDirection.INCREASE, QConst(p))),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(t))),
            )
        ),
    )
    grant = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", self_sel),
                ("ability", KeywordAbility(keyword=Keyword.DEATHTOUCH, params=())),
            )
        ),
    )
    return AbilityOutcome(
        ability=StaticAbility(
            effect=Seq(steps=(pt, grant)),
            condition=FAtom(
                pred=FAtomPred.ZONE_COUNT_GE,
                who=ControllerRef.OPPONENT,
                zone=Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.OPPONENT),
                inner_filter=FAnd(children=()),
                count=QConst(8),
            ),
        )
    )


def _build_radha_first_strike(m: re.Match[str]) -> SentenceOutcome:
    """During your turn, Radha has first strike.  (Radha, Heart of Keld;
    grammar round 6 R6-1 — TURN_OF carries the turn owner, the Phase enum
    has none; "Radha" is the card self-referent, encoded as the house
    IS_SOURCE selector, never a hardcoded name (convention, shape #86).)"""
    atom = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", _self_selector(_bf_any())),
                ("ability", KeywordAbility(keyword=Keyword.FIRST_STRIKE, params=())),
            )
        ),
    )
    return AbilityOutcome(
        ability=StaticAbility(
            atom,
            condition=FAtom(pred=FAtomPred.TURN_OF, who=ControllerRef.YOU),
        )
    )


def _build_during_turn_cost_reduce(m: re.Match[str]) -> SentenceOutcome:
    """During your turn, this spell costs {2}{U}{U} less to cast.
    (Discontinuity; grammar round 6 R6-1 TURN_OF in
    ``CostModifier.condition`` (T3 round-2 slot), Stormwing's delta +
    extra_deltas compound split (generic + colored) — the old UNCOVERED
    reason's "single CostDelta" claim was already fixed by T3 round 4's
    extra_deltas.)"""
    generic = int(m.group("generic"))
    modifier = CostModifier(
        filter=FAtom(pred=FAtomPred.IS_SOURCE),
        controller_ref=ControllerRef.YOU,
        delta=CostDeltaReduceGeneric(amount=QConst(generic)),
        extra_deltas=(CostDeltaReduceMana(color="U", amount=QConst(2)),),
        condition=FAtom(pred=FAtomPred.TURN_OF, who=ControllerRef.YOU),
    )
    return AbilityOutcome(ability=modifier)


def _build_enchant_no_untap(m: re.Match[str]) -> SentenceOutcome:
    """Enchanted creature doesn't untap during its controller's untap step.
    (Capture Sphere; C10 — PREVENT_EFFECT over the untap transition
    (TapStateEvent tapped=False) restricted to the enchanted permanent.)

    LOSSY (verbatim): "during its controller's untap step" — the untap-step
    scope is dropped (Step enum has no UNTAP member; step-scope slot
    registered for round 7, 2026-09-28 decision doc deferred family 3).
    """
    enchanted = FAnd(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FAtom(pred=FAtomPred.IS_ATTACHED_TO_SOURCE),
        )
    )
    atom = Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                ("condition", FAtom(pred=FAtomPred.IS_ATTACHED_TO_SOURCE)),
                ("event", TapStateEvent(tapped=False, filter=enchanted)),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_enchant_cant_attack_block(m: re.Match[str]) -> SentenceOutcome:
    """Enchanted permanent can't attack or block, and its activated
    abilities can't be activated unless they're mana abilities.
    (Faith's Fetters; decision C11 — Seq of two PREVENT_EFFECT atoms on
    the enchanted permanent (IS_ATTACHED_TO_SOURCE), the attack atom over
    DeclareAttackersEvent, the block atom over DeclareBlockersEvent
    following the B4 cant-block idiom (filter selects the restricted
    participant).)

    LOSSY (verbatim, per C11): "and its activated abilities can't be
    activated unless they're mana abilities" is DROPPED — needs an
    ability-activation event class + ability-kind predicate
    (ability-introspection family, 2026-09-28 decision doc deferred
    family 1).
    """
    enchanted = FAtom(pred=FAtomPred.IS_ATTACHED_TO_SOURCE)
    attack = Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                ("condition", enchanted),
                ("event", DeclareAttackersEvent(filter=enchanted)),
            )
        ),
    )
    block = Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                ("condition", enchanted),
                ("event", DeclareBlockersEvent(filter=enchanted)),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(Seq(steps=(attack, block))))


def _build_discard_cant_be_blocked(m: re.Match[str]) -> SentenceOutcome:
    """Discard a card: This creature can't be blocked this turn.
    (Ghostly Pilferer; C10 + R6-4 — costed activation whose PREVENT_EFFECT
    narrows the blocked side to the source via the ``blocked`` slot over a
    universal blocker filter (grammar-round-7 ``_dbe_blocked`` idiom),
    duration until end of turn.)"""
    cost = Cost(
        parts=(
            CostDiscard(
                target=Selector(
                    QConst(1),
                    SelectorMode.CHOOSE,
                    FAnd(children=()),
                    Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
                )
            ),
        )
    )
    atom = Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                ("condition", FAtom(pred=FAtomPred.IS_SOURCE)),
                (
                    "event",
                    DeclareBlockersEvent(
                        FAnd(children=()),
                        blocked=FAtom(pred=FAtomPred.IS_SOURCE),
                    ),
                ),
                ("duration", DurationEot()),
            )
        ),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


# ---------------------------------------------------------------------------
# Grammar round-7 batch builders (doc 2026-09-28/03 §3 R7-A)
# ---------------------------------------------------------------------------


def _result_selector() -> Selector:
    """C2 canonical result-referent selector (grammar round 7, R7-1):
    the object the previous sentence acted on — here the card Kitesail
    Freebooter's ``You choose … from it`` sentence picked."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAnd(children=()),
        Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
        referent="result",
    )


def _equipped_creature() -> Selector:
    """``Equipped creature`` = the permanent attached to the source —
    same structured attachment predicate as ``enchanted creature``
    (IS_ATTACHED_TO_SOURCE is attachment-generic; the aura name is
    historical)."""
    return _enchanted_creature()


def _build_exile_that_until_leaves(m: re.Match[str]) -> SentenceOutcome:
    """``Exile that card until this creature leaves the battlefield.``
    (Kitesail Freebooter s3) — EXILE of the result-referent card.
    LOSSY (C11 verbatim): "until this creature leaves the battlefield"
    — ``_VERB_ROLES[EXILE]`` has no duration role (grammar phase added
    ``DurationUntilLeaves`` but only wired it to GAIN_CONTROL, per the
    round-7 spec's R7-2 role row), so the temporary window is dropped;
    the exiled card would never return. Flagged as an R8 grammar item
    (EXILE duration role); the card CHOICE (result referent) is
    preserved."""
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                ("target", _result_selector()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_etb_choose_name(m: re.Match[str]) -> SentenceOutcome:
    """``As this enchantment enters, choose a card name.`` (Runed Halo s1)
    — Verb.CHOOSE_NAME (R7-4) on an enters trigger; the pick is read back
    by ``FAtomPred.NAME_CHOSEN`` in the protection static (B4).  C16: the
    choice itself is the open decision (any card name)."""
    return AbilityOutcome(
        ability=TriggeredAbility(
            event=ZoneChangeEvent(
                from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
                to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU),
                # R11-B (audit 09-29/04 P0-2): "As THIS enchantment enters"
                # — the entering object is the card itself (class A).
                subject=FAtom(pred=FAtomPred.IS_SOURCE),
            ),
            condition=None,
            effect=Atom(verb=Verb.CHOOSE_NAME, args=AtomArgs(pairs=())),
        )
    )


def _build_choose_name_not_basic(m: re.Match[str]) -> SentenceOutcome:
    """``Choose a card name other than a basic land card name.``
    (Necromentia s1) — CHOOSE_NAME with the exclusion as a name_filter
    (R7-4 role): a name is illegal exactly when it is a BASIC LAND
    card's name (SUPERTYPE Basic AND TYPE Land — closer to the printed
    exclusion than the r8 round-trip canonical's bare-SUPERTYPE form).
    C16: the name choice stays open (all non-basic-land names)."""
    name_filter = FNot(
        inner=FAnd(
            children=(
                FAtom(pred=FAtomPred.SUPERTYPE_EQ, string_value="Basic"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land"),
            )
        )
    )
    atom = Atom(
        verb=Verb.CHOOSE_NAME,
        args=AtomArgs(pairs=(("name_filter", name_filter),)),
    )
    return EffectOutcome(effect=atom)


def _build_equipped_pt_per_soul_counter(m: re.Match[str]) -> SentenceOutcome:
    """``Equipped creature gets +P/+T for each soul counter on this
    Equipment.`` (Malefic Scythe s2) — static MODIFY_PT whose delta
    scales with ``QProp(COUNTER_COUNT, referent="source")`` (R7-9b
    validation relaxation).
    LOSSY (C11 verbatim): ``QProp`` has no counter-kind slot, so the
    "soul" kind is dropped — faithful in context because Malefic Scythe
    only ever carries soul counters."""
    p, t = int(m.group("p")), int(m.group("t"))
    count = QProp(referent="source", field=QPropField.COUNTER_COUNT)
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _equipped_creature()),
                (
                    "power",
                    PtDelta(PtDirection.INCREASE, QBin(QBinOp.MUL, QConst(p), count)),
                ),
                (
                    "toughness",
                    PtDelta(PtDirection.INCREASE, QBin(QBinOp.MUL, QConst(t), count)),
                ),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(effect=atom))


def _build_destroy_attached_equipment(m: re.Match[str]) -> SentenceOutcome:
    """``Destroy all Equipment attached to that creature.`` (Turn to Slag
    s2) — FAtomPred.IS_ATTACHED_TO (R7-1) with the R4 target referent:
    "that creature" is the spell's damaged target, so the filter binds
    the s0 TARGET selector today (deviation from the spec sketch,
    deliberate like B5b-loses-kw-eot)."""
    atom = Atom(
        verb=Verb.DESTROY,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QUnbounded(),
                        SelectorMode.ALL,
                        FAnd(
                            children=(
                                FAtom(
                                    pred=FAtomPred.SUBTYPE_EQ,
                                    string_value="Equipment",
                                ),
                                FAtom(
                                    pred=FAtomPred.IS_ATTACHED_TO,
                                    referent="target",
                                ),
                            )
                        ),
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_speaker_activation_gate(m: re.Match[str]) -> SentenceOutcome:
    """``Activate only if you have at least N life more than your starting
    life total and only as a sorcery.`` (Speaker of the Heavens) — grammar
    round 9-B row 2: LIFE_LEAD_OVER_START_GE (R9-2, bare-count rule row —
    the count slot carries QConst(N), no who/inner_filter) delivered as an
    ActivationGateOutcome, the Caged Zombie plumbing: the compiler attaches
    the condition to the nearest preceding unconditional ActivatedAbility
    (the B3 ``{T}: Create a 4/4 white Angel token`` row).

    C16: none — the gate is a legality condition, fully forced.

    LOSSY (verbatim): "and only as a sorcery" — the ActivationWindow
    vocabulary shipped in R9-1 but NO attach plumbing exists for a bare
    gate sentence carrying timing (ActivationGateOutcome carries a condition
    only; the compiler's gate-attach rewrites the condition slot). A
    pattern-override of the s1 builder would create a second match on that
    sentence (PC-3 hard gate), so the clause is DROPPED with this note —
    R10: gate-outcome timing attachment (ActivationGateOutcome.timing).
    """
    return ActivationGateOutcome(
        condition=FAtom(
            pred=FAtomPred.LIFE_LEAD_OVER_START_GE,
            count=QConst(int(m.group("n"))),
        )
    )


def _build_aslong_attack_despite_defender(m: re.Match[str]) -> SentenceOutcome:
    """``As long as you control a creature with power N or greater, this
    creature can attack as though it didn't have defender.`` (Drowsing
    Tyrannodon) — grammar round 9-B row 3, doc 2026-09-28/11 fidelity note:
    StaticAbility carrying the as-long-as gate in ``condition`` (convention
    C9 — never a duration approximation) over a LOSE_ABILITY atom that
    strips Keyword.DEFENDER from self (``ability`` rides a KeywordAbility,
    the Soul Sear precedent), scoped by DurationWhileCondition inside the
    atom.

    FIDELITY ARGUMENT (C11-class, doc /11): "can attack as though it didn't
    have defender" is encoded as actually LOSING defender — the only
    M21-relevant rules text of Defender is "This creature can't attack", so
    the two effects coincide on this pool; no as-though layer machinery
    exists (deferred family), and losing the keyword is the closest honest
    encoding.

    C16: none — fully forced (state gate + self-targeted keyword loss).
    """
    p = int(m.group("p"))
    cond = FAtom(
        pred=FAtomPred.CONTROLLER_COUNT_GE,
        count=QConst(1),
        inner_filter=FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.POWER_GE, count=QConst(p)),
            )
        ),
    )
    atom = Atom(
        verb=Verb.LOSE_ABILITY,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    _self_selector(
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY)
                    ),
                ),
                ("ability", KeywordAbility(keyword=Keyword.DEFENDER)),
                ("duration", DurationWhileCondition(filter=cond)),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(effect=atom, condition=cond))


# ---------------------------------------------------------------------------
# TEMPLATES
# ---------------------------------------------------------------------------


TEMPLATES: tuple[Template, ...] = (
    Template(
        tid="B5a-land-add",
        name="basic-land tap ability",
        bucket=_BUCKET,
        pattern=re.compile(r"^\(\{T\}: Add \{([WUBRG])\}\.\)$"),
        priority=_PRIORITY,
        build=_build_land_add,
    ),
    Template(
        tid="B5a-add-six-r",
        name="add six of a color",
        bucket=_BUCKET,
        pattern=re.compile(r"^Add six \{([WUBRG])\}\.$"),
        priority=_PRIORITY,
        build=_build_add_six,
    ),
    Template(
        tid="B5a-add-any-color",
        name="add two mana of any one color",
        bucket=_BUCKET,
        pattern=re.compile(r"^Add two mana of any one color\.$"),
        priority=_PRIORITY,
        build=_build_add_any_color,
    ),
    Template(
        tid="B5a-attacking-pt",
        name="attacking creatures you control get +N/+N",
        bucket=_BUCKET,
        pattern=re.compile(r"^Attacking creatures you control get \+(\d+)/\+(\d+)\.$"),
        priority=_PRIORITY,
        build=_build_attacking_pt,
    ),
    Template(
        tid="B5a-counter-spell",
        name="counter target spell",
        bucket=_BUCKET,
        pattern=re.compile(r"^Counter target spell\.$"),
        priority=_PRIORITY,
        build=_build_counter_spell,
    ),
    Template(
        tid="B5a-weird-token",
        name="create an X/X Weird token (X = instants/sorceries in graveyard)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Create an X/X blue and red Weird creature token, where X is the "
            r"number of instant and sorcery cards in your graveyard\.$"
        ),
        priority=_PRIORITY,
        build=_build_weird_token,
    ),
    Template(
        tid="B5a-goblin-wizard-tokens",
        name="create two N/N Goblin Wizard tokens with prowess",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Create two (\d+)/(\d+) red Goblin Wizard creature tokens "
            r"with prowess\.$"
        ),
        priority=_PRIORITY,
        build=_build_goblin_wizard_tokens,
    ),
    Template(
        tid="B5a-remind-deathtouch",
        name="deathtouch keyword rule reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Deathtouch \(Any amount of damage this deals to a creature is "
            r"enough to destroy it\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_keyword_reminder(Keyword.DEATHTOUCH),
    ),
    Template(
        tid="B5a-remind-defender",
        name="defender keyword rule reminder",
        bucket=_BUCKET,
        pattern=re.compile(r"^Defender \(This creature can't attack\.\)$"),
        priority=_PRIORITY,
        build=_build_keyword_reminder(Keyword.DEFENDER),
    ),
    Template(
        tid="B5a-remind-double-strike",
        name="double strike keyword rule reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Double strike \(This creature deals both first-strike and "
            r"regular combat damage\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_keyword_reminder(Keyword.DOUBLE_STRIKE),
    ),
    Template(
        tid="B5a-destroy-cw-pw-mv-le",
        name="destroy target creature or planeswalker with mana value N or less",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Destroy target creature or planeswalker with mana value "
            r"(\d+) or less\.$"
        ),
        priority=_PRIORITY,
        build=lambda m: _build_destroy(
            m,
            FOr(
                children=(
                    FAnd(
                        children=(
                            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                            FAtom(
                                pred=FAtomPred.CMC_LE,
                                count=QConst(int(m.group(1))),
                            ),
                        )
                    ),
                    FAnd(
                        children=(
                            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                            FAtom(
                                pred=FAtomPred.CMC_LE,
                                count=QConst(int(m.group(1))),
                            ),
                        )
                    ),
                )
            ),
            Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
        ),
    ),
    Template(
        tid="B5a-destroy-cw-pw",
        name="destroy target creature or planeswalker",
        bucket=_BUCKET,
        pattern=re.compile(r"^Destroy target creature or planeswalker\.$"),
        priority=_PRIORITY,
        build=lambda m: _build_destroy(
            m,
            FOr(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                )
            ),
            Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
        ),
    ),
    Template(
        tid="B5a-destroy-creature",
        name="destroy target creature",
        bucket=_BUCKET,
        pattern=re.compile(r"^Destroy target creature\.$"),
        priority=_PRIORITY,
        build=lambda m: _build_destroy(
            m,
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
        ),
    ),
    Template(
        tid="B5a-destroy-tapped-creature",
        name="destroy target tapped creature",
        bucket=_BUCKET,
        pattern=re.compile(r"^Destroy target tapped creature\.$"),
        priority=_PRIORITY,
        build=lambda m: _build_destroy(
            m,
            FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.IS_TAPPED),
                )
            ),
            Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
        ),
    ),
    Template(
        tid="B5a-discard-tap-self",
        name="discard a card: tap this creature",
        bucket=_BUCKET,
        pattern=re.compile(r"^Discard a card: Tap this creature\.$"),
        priority=_PRIORITY,
        build=lambda m: AbilityOutcome(
            ability=ActivatedAbility(
                cost=Cost(
                    parts=(
                        CostDiscard(
                            target=Selector(
                                QConst(1),
                                SelectorMode.CHOOSE,
                                FAnd(children=()),
                                Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
                            )
                        ),
                    )
                ),
                effect=Atom(
                    verb=Verb.TAP,
                    args=AtomArgs(
                        pairs=(
                            (
                                "target",
                                _self_selector(
                                    Zone(
                                        kind=ZoneKind.BATTLEFIELD,
                                        controller=ControllerRef.ANY,
                                    )
                                ),
                            ),
                        )
                    ),
                ),
            )
        ),
    ),
    Template(
        tid="B5a-draw-frantic-inventory",
        name="draw a card, then draw = # named cards in graveyard",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Draw a card, then draw cards equal to the number of cards "
            r"named Frantic Inventory in your graveyard\.$"
        ),
        priority=_PRIORITY,
        build=_build_draw_frantic_inventory,
    ),
    Template(
        tid="B5a-draw-one",
        name="draw a card",
        bucket=_BUCKET,
        pattern=re.compile(r"^Draw a card\.$"),
        priority=_PRIORITY,
        build=_build_draw_one,
    ),
    Template(
        tid="B5a-draw-two",
        name="draw two cards",
        bucket=_BUCKET,
        pattern=re.compile(r"^Draw two cards\.$"),
        priority=_PRIORITY,
        build=_build_draw_two,
    ),
    Template(
        tid="B5a-draw-three-then-discard",
        name="draw three cards, then discard a card",
        bucket=_BUCKET,
        pattern=re.compile(r"^Draw three cards, then discard a card\.$"),
        priority=_PRIORITY,
        build=_build_draw_three_then_discard,
    ),
    Template(
        tid="B5a-trample-counter",
        name="each creature you control with +N/+N counters has trample",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Each creature you control with a \+(\d+)/\+(\d+) counter on it "
            r"has trample\.$"
        ),
        priority=_PRIORITY,
        build=_build_trample_counter,
    ),
    Template(
        tid="B5a-lose-life-each-player",
        name="each player loses N life",
        bucket=_BUCKET,
        pattern=re.compile(r"^Each player loses (\d+) life\.$"),
        priority=_PRIORITY,
        build=_build_lose_life,
    ),
    Template(
        tid="B5a-enchant-pt-attacks",
        name="enchanted creature gets +N/+N and attacks each combat if able",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Enchanted creature gets \+(\d+)/\+(\d+) and attacks each "
            r"combat if able\.$"
        ),
        priority=_PRIORITY,
        build=_build_enchant_pt_attacks,
    ),
    Template(
        tid="B5a-enchant-pt-death-draw",
        name='enchanted creature gets +N/+N and has "dies → draw a card"',
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Enchanted creature gets \+(\d+)/\+(\d+) and has "
            r'"When this creature dies, draw a card\."$'
        ),
        priority=_PRIORITY,
        build=_build_enchant_pt_death_draw,
    ),
    Template(
        tid="B5a-enchant-pt-flying",
        name="enchanted creature gets +N/+N and has flying",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Enchanted creature gets \+(\d+)/\+(\d+) and has flying\.$"
        ),
        priority=_PRIORITY,
        build=_build_enchant_pt_flying,
    ),
    Template(
        tid="B5a-enchant-pt-trample",
        name="enchanted creature gets +N/+N and has trample",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Enchanted creature gets \+(\d+)/\+(\d+) and has trample\.$"
        ),
        priority=_PRIORITY,
        build=_build_enchant_pt_trample,
    ),
    Template(
        tid="B5a-enchant-pt-firststrike-knight",
        name="enchanted creature gets +N/+N, has first strike, and is a Knight",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Enchanted creature gets \+(\d+)/\+(\d+), has first strike, "
            r"and is a Knight in addition to its other types\.$"
        ),
        priority=_PRIORITY,
        build=_build_enchant_pt_firststrike_knight,
    ),
    Template(
        tid="B5a-enchant-pt-flying-demon",
        name="enchanted creature gets +N/+N, has flying, and is a Demon",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Enchanted creature gets \+(\d+)/\+(\d+), has flying, "
            r"and is a Demon in addition to its other types\.$"
        ),
        priority=_PRIORITY,
        build=_build_enchant_pt_flying_demon,
    ),
    Template(
        tid="B5a-end-turn",
        name="end the turn",
        bucket=_BUCKET,
        pattern=re.compile(r"^End the turn\.$"),
        priority=_PRIORITY,
        build=_build_end_turn,
    ),
    Template(
        tid="B5a-equip",
        name="equip <mana> activated ability",
        bucket=_BUCKET,
        # ZND-4 T1 (spec /115): single-colorless backref widened to a mana-
        # symbol sequence ("Equip {2}{R} ({2}{R}: …)"). M21's bare
        # "Equip {1} ({1}: …)" still matches with an identical Cost tree
        # (parse_mana_cost("{1}") == the old hand-built generic node) —
        # PC-4 must stay 0-diff (audit-named carrier widen).
        pattern=re.compile(
            r"^Equip (?P<cost>(?:\{[0-9WUBRGT]+\})+) "
            r"\((?P=cost): Attach to target creature you "
            r"control\. Equip only as a sorcery\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_equip,
    ),
    Template(
        tid="B5a-equipped-pt",
        name="equipped creature gets +N/+N",
        bucket=_BUCKET,
        pattern=re.compile(r"^Equipped creature gets \+(\d+)/\+(\d+)\.$"),
        priority=_PRIORITY,
        build=_build_equipped_pt,
    ),
    Template(
        tid="B5a-exile-self",
        name="exile this card (named self-reference)",
        bucket=_BUCKET,
        pattern=re.compile(r"^Exile Experimental Overload\.$"),
        priority=_PRIORITY,
        build=_build_exile_self,
    ),
    Template(
        tid="B5a-exile-cw-pw",
        name="exile target creature or planeswalker",
        bucket=_BUCKET,
        pattern=re.compile(r"^Exile target creature or planeswalker\.$"),
        priority=_PRIORITY,
        build=lambda m: _build_exile_target(
            m,
            FOr(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                )
            ),  # type: ignore[arg-type]
        ),
    ),
    Template(
        tid="B5a-exile-creature",
        name="exile target creature",
        bucket=_BUCKET,
        pattern=re.compile(r"^Exile target creature\.$"),
        priority=_PRIORITY,
        build=lambda m: _build_exile_target(
            m,
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),  # type: ignore[arg-type]
        ),
    ),
    Template(
        tid="B5a-exile-nonland",
        name="exile target nonland permanent",
        bucket=_BUCKET,
        pattern=re.compile(r"^Exile target nonland permanent\.$"),
        priority=_PRIORITY,
        build=lambda m: _build_exile_target(
            m,
            FAnd(
                children=(
                    FAtom(pred=FAtomPred.IS_PERMANENT),
                    FNot(inner=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land")),
                )
            ),  # type: ignore[arg-type]
        ),
    ),
    Template(
        tid="B5a-battalion",
        name="battalion keyword",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Battalion — Whenever this creature and at least two other creatures attack, put a \+1/\+1 counter on this creature\.$"
        ),
        priority=_PRIORITY,
        build=_build_battalion,
    ),
    Template(
        tid="B5a-destroy-power-ge",
        name="destroy target creature with power N or greater",
        bucket=_BUCKET,
        pattern=re.compile(r"^Destroy target creature with power (\d+) or greater\.$"),
        priority=_PRIORITY,
        build=_build_destroy_power_ge,
    ),
    Template(
        tid="B5a-double-power",
        name="double power until end of turn",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Double the power of target creature until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_double_power,
    ),
    Template(
        tid="B5a-enchant-gain-life",
        name="enchanted creature gains life-gain trigger",
        bucket=_BUCKET,
        pattern=re.compile(
            r'^Enchanted creature has "Whenever you gain life, put that many \+1/\+1 counters on this creature\."$'
        ),
        priority=_PRIORITY,
        build=_build_enchant_gain_life,
    ),
    Template(
        tid="B5a-addl-cost-discard",
        name="additional cost to cast: discard a card",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^As an additional cost to cast this spell, discard a card\.$"
        ),
        priority=_PRIORITY,
        build=lambda m: AdditionalCostOutcome(
            cost=Cost(
                parts=(
                    CostDiscard(
                        target=Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAnd(children=()),
                            Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
                        )
                    ),
                )
            )
        ),
    ),
    Template(
        tid="B5a-addl-cost-sacrifice",
        name="additional cost to cast: sacrifice a creature",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^As an additional cost to cast this spell, sacrifice a creature\.$"
        ),
        priority=_PRIORITY,
        build=lambda m: AdditionalCostOutcome(
            cost=Cost(
                parts=(
                    CostSacrifice(
                        target=Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAnd(
                                children=(
                                    FAtom(
                                        pred=FAtomPred.TYPE_EQ, string_value="Creature"
                                    ),
                                    FAtom(
                                        pred=FAtomPred.CONTROLLER_IS,
                                        who=ControllerRef.YOU,
                                    ),
                                )
                            ),
                            Zone(
                                kind=ZoneKind.BATTLEFIELD,
                                controller=ControllerRef.ANY,
                            ),
                        )
                    ),
                )
            )
        ),
    ),
    Template(
        tid="B5a-gnarled-sage",
        name="conditional static: drawn 2+ this turn -> +N/+N and vigilance",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^As long as you've drawn two or more cards this turn, this "
            r"creature gets \+(\d+)/\+(\d+) and has vigilance\.$"
        ),
        priority=_PRIORITY,
        build=_build_gnarled_sage,
    ),
    Template(
        tid="B5a-activate-only-death",
        name="activation gate: a creature died this turn",
        bucket=_BUCKET,
        pattern=re.compile(r"^Activate only if a creature died this turn\.$"),
        priority=_PRIORITY,
        build=_build_activate_only_death,
    ),
    Template(
        tid="B5a-activate-only-flying",
        name="activation gate: you control a creature with flying",
        bucket=_BUCKET,
        pattern=re.compile(r"^Activate only if you control a creature with flying\.$"),
        priority=_PRIORITY,
        build=_build_activate_only_flying,
    ),
    Template(
        tid="B5a-counter-unless-sps",
        name="counter target instant/sorcery unless controller pays {N}",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Counter target instant or sorcery spell unless its controller "
            r"pays \{(\d+)\}\.$"
        ),
        priority=_PRIORITY,
        build=_build_counter_unless_sps,
    ),
    Template(
        tid="B5a-counter-unless-spell",
        name="counter target spell unless controller pays {N}",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Counter target spell unless its controller pays \{(\d+)\}\.$"
        ),
        priority=_PRIORITY,
        build=_build_counter_unless_spell,
    ),
    Template(
        tid="B5a-aslong-opp-gy-count",
        name="as long as an opponent has 8+ GY cards: +N/+N and deathtouch",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^As long as an opponent has eight or more cards in their "
            r"graveyard, this creature gets \+(?P<p>\d+)/\+(?P<t>\d+) and "
            r"has deathtouch\.$"
        ),
        priority=_PRIORITY,
        build=_build_aslong_opp_gy_count,
    ),
    Template(
        tid="B5a-radha-first-strike",
        name="during your turn Radha has first strike",
        bucket=_BUCKET,
        pattern=re.compile(r"^During your turn, Radha has first strike\.$"),
        priority=_PRIORITY,
        build=_build_radha_first_strike,
    ),
    Template(
        tid="B5a-during-turn-cost-reduce",
        name="during your turn this spell costs {N}{U}{U} less to cast",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^During your turn, this spell costs \{(?P<generic>\d+)\}"
            r"\{U\}\{U\} less to cast\.$"
        ),
        priority=_PRIORITY,
        build=_build_during_turn_cost_reduce,
    ),
    Template(
        tid="B5a-enchant-no-untap",
        name="enchanted creature doesn't untap during its controller's untap step",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Enchanted creature doesn't untap during its controller's "
            r"untap step\.$"
        ),
        priority=_PRIORITY,
        build=_build_enchant_no_untap,
    ),
    Template(
        tid="B5a-enchant-cant-attack-block",
        name="enchanted permanent can't attack or block (mana-abilities clause dropped, C11)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Enchanted permanent can't attack or block, and its activated "
            r"abilities can't be activated unless they're mana abilities\.$"
        ),
        priority=_PRIORITY,
        build=_build_enchant_cant_attack_block,
    ),
    Template(
        tid="B5a-discard-cant-be-blocked",
        name="discard a card: this creature can't be blocked this turn",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Discard a card: This creature can't be blocked this turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_discard_cant_be_blocked,
    ),  # --- grammar round-7 batch (doc 2026-09-28/03 §3 R7-A) ---
    Template(
        tid="B5a-exile-that-until-leaves",
        name="exile that card (result referent; until-leaves window lossy)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Exile that card until this creature leaves the battlefield\.$"
        ),
        priority=_PRIORITY,
        build=_build_exile_that_until_leaves,
    ),
    Template(
        tid="B5a-etb-choose-name",
        name="as this enchantment enters, choose a card name",
        bucket=_BUCKET,
        pattern=re.compile(r"^As this enchantment enters, choose a card name\.$"),
        priority=_PRIORITY,
        build=_build_etb_choose_name,
    ),
    Template(
        tid="B5a-choose-name-not-basic",
        name="choose a card name other than a basic land card name",
        bucket=_BUCKET,
        pattern=re.compile(r"^Choose a card name other than a basic land card name\.$"),
        priority=_PRIORITY,
        build=_build_choose_name_not_basic,
    ),
    Template(
        tid="B5a-equipped-per-soul-counter",
        name="equipped creature gets +P/+T per soul counter on this Equipment",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Equipped creature gets \+(?P<p>\d+)/\+(?P<t>\d+) for each "
            r"soul counter on this Equipment\.$"
        ),
        priority=_PRIORITY,
        build=_build_equipped_pt_per_soul_counter,
    ),
    Template(
        tid="B5a-destroy-equipped",
        name="destroy all Equipment attached to that creature (IS_ATTACHED_TO)",
        bucket=_BUCKET,
        pattern=re.compile(r"^Destroy all Equipment attached to that creature\.$"),
        priority=_PRIORITY,
        build=_build_destroy_attached_equipment,
    ),
    Template(
        tid="B5a-speaker-gate",
        name="activation gate: life lead over start (LIFE_LEAD_OVER_START_GE)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Activate only if you have at least (?P<n>\d+) life more than "
            r"your starting life total and only as a sorcery\.$"
        ),
        priority=_PRIORITY,
        build=_build_speaker_activation_gate,
    ),
    Template(
        tid="B5a-aslong-attack-despite-defender",
        name="as-long-as power gate strips Defender (LOSE_ABILITY, C9)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^As long as you control a creature with power (?P<p>\d+) or "
            r"greater, this creature can attack as though it didn't have "
            r"defender\.$"
        ),
        priority=_PRIORITY,
        build=_build_aslong_attack_despite_defender,
    ),
    Template(
        tid="B5a-snoop-top-goblin-abilities",
        name="top-Goblin ability grant (Snoop s3, T5-E closure of R10 DEFER)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^As long as the top card of your library is a Goblin card, "
            r"this creature has all activated abilities of that card\.$"
        ),
        priority=_PRIORITY,
        build=_build_snoop_top_goblin_abilities,
    ),
    Template(
        tid="B5a-activate-sorcery-gate",
        name="activation gate: bare sorcery-timing window (R10-1, C25)",
        bucket=_BUCKET,
        pattern=re.compile(r"^Activate only as a sorcery\.$"),
        priority=_PRIORITY,
        build=_build_activate_only_sorcery,
    ),
    # --- grammar round-11 C3 coverage batch (payment-failure gate) ---
    Template(
        tid="B5a-each-opp-cant-lose-life",
        name="each opponent who-can't life-loss tail (Conditional+EachPlayer, C3)",
        bucket=_BUCKET,
        pattern=re.compile(r"^Each opponent who can't loses (?P<n>\d+) life\.$"),
        priority=_PRIORITY,
        build=_build_each_opp_cant_lose_life,
    ),
)

# UNCOVERED — 2 normalized-key rows
#
# Each row is (shape_key, reason).  shape_key is the B5a.json normalized
# key (digits → "N").  Sorted alphabetically by shape_key.  The T4 test
# pins this set against the SHAPES table.
UNCOVERED: Final[tuple[tuple[str, str], ...]] = (
    (
        "Choose one or more —",
        "handled by the compiler's choose-opener built-in (compiler._wrap_choose_openers), not a template",
    ),
    (
        "Choose one —",
        "handled by the compiler's choose-opener built-in (compiler._wrap_choose_openers), not a template",
    ),
)
