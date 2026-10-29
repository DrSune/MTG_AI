"""B4 bucket templates — 46 templates covering 46 of 47 B4 shapes.

Bucket input: ``/tmp/opencode/phase1_buckets/B4.json`` (47 normalized shape
keys → ``[card, sentence]`` pairs; sentences carry *concrete* numbers, keys
carry ``N`` placeholders).  Templates fullmatch the **concrete** oracle
sentence, never the normalized key.

Coverage (47 = 46 template + 1 uncovered):

- **46 template-covered shapes**: static P/T grants (self, creatures you
  control, other creatures, opponents' creatures), static keyword grants
  (trample, lifelink, protection), PREVENT_EFFECT (can't block),
  PREVENT_EFFECT blocked-side (can't be blocked as long as drawn —
  C9 StaticAbility.condition; can block only flying — subject+blocked
  narrowing), MANDATE_BLOCK (must be blocked if able, R6-5),
  MANDATE_ATTACK, GAIN_CONTROL, DRAW+DISCARD Seq, GAIN_LIFE (QConst and
  QCount), LOSE_LIFE, QProp P/T (Carrion Grub), conditional statics
  (DurationWhileCondition), compound statics (P/T + protection Seq),
   COST_MODIFIER (Watcher of the Spheres, Volcanic Salvo, Sanguine
   Indulgence; Stormwing Entity's compound {N}{U} reduction; opponent
   spell-cost increases — Terror of the Peaks, Pursued Whale),
   ETB_STATE (tapped creature, tapped land),
   ETB X +1/+1 counters (Wildwood Scourge: ZoneChangeEvent subject
   IS_SOURCE + PUT_COUNTER count QX, target bound to the event referent),
   ACTIVATED_ABILITY (cast from top of library, graveyard recast with
   additional cost), TUTOR (name-specific library/graveyard search for
   Basri / Liliana).
- **1 uncovered shape**: copy-retarget anaphora ("new targets for the
  copy").  The round-8-C batch landed the cast-them-this-turn register
  hop, the Radha two-permission sentence, Furious Rise's play-that-card,
  Azusa's ADD_LAND_PLAY and the QThisTurn(NONCOMBAT_DAMAGE) cost reducer;
  the round-9-B batch (doc 2026-09-28/11) landed the Orrery MANA_POLICY
  flooding permission, Teferi's GRANT_ACTIVATION instant-window permission
  and the Enthralling targeting-legality PREVENT row (C11-class note).
  Recorded in UNCOVERED.

Conventions:
- Static abilities on permanents → ``AbilityOutcome(StaticAbility(...))``
- Spell effects / one-time actions → ``EffectOutcome(...)``
- ``this creature`` → ``Selector(CHOOSE, QConst(1), FAtom(IS_SOURCE), zone)``
- ``enchanted creature`` → ``Selector(ALL, QUnbounded,
  FAnd(TYPE_EQ Creature, IS_ATTACHED_TO_SOURCE), Zone(BATTLEFIELD, ANY))``
- ``creatures you control`` → ``Selector(ALL, QUnbounded,
  FAnd(TYPE_EQ Creature, CONTROLLER_IS YOU), Zone(BATTLEFIELD, YOU))``
- ``+N/+N`` → ``PtDelta(INCREASE, QConst(N))``
- ``-N/-N`` → ``PtDelta(DECREASE, QConst(N))``
- ``other <Subtype> you control`` → ``FNot(inner=FAtom(IS_SOURCE))`` in filter

PC-3: every B4 concrete sentence fullmatches **at most one** template
(patterns are pairwise disjoint by construction); verified in tests.
"""

from __future__ import annotations

import re

from MTG_bot.core.ability_tree import (
    QX,
    ActivatedAbility,
    ActivationWindow,
    Atom,
    AtomArgs,
    ControllerRef,
    Cost,
    CostDeltaIncreaseGeneric,
    CostDeltaIncreaseLife,
    CostDeltaReduceGeneric,
    CostDeltaReduceMana,
    CostDiscard,
    CostLife,
    CostModifier,
    CounterKind,
    DeclareBlockersEvent,
    DurationEot,
    DurationWhileCondition,
    EtBState,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    OptionalEffect,
    PtDelta,
    PtDirection,
    QAgg,
    QBin,
    QBinOp,
    QConst,
    QCount,
    QProp,
    QPropField,
    QThisTurn,
    Quantity,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    TargetingEvent,
    ThisTurnKind,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    ZonePosition,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    SentenceOutcome,
    Template,
)

_BUCKET = "B4"
_PRIORITY = 100

# Keyword string → enum map for "have <keyword>" patterns.
_KW_MAP: dict[str, Keyword] = {
    "trample": Keyword.TRAMPLE,
    "flying": Keyword.FLYING,
    "haste": Keyword.HASTE,
    "reach": Keyword.REACH,
    "vigilance": Keyword.VIGILANCE,
    "deathtouch": Keyword.DEATHTOUCH,
    "lifelink": Keyword.LIFELINK,
    "defender": Keyword.DEFENDER,
    "menace": Keyword.MENACE,
}


# ---------------------------------------------------------------------------
# Shared node builders
# ---------------------------------------------------------------------------


def _self_selector() -> Selector:
    """Selector for ``this creature`` — the source of the ability."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(pred=FAtomPred.IS_SOURCE),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _creatures_you_control() -> Selector:
    """Selector for ``creatures you control``."""
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


def _creatures_opponents_control() -> Selector:
    """Selector for ``creatures your opponents control``."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _other_creatures() -> Selector:
    """Selector for ``other creatures`` (all creatures except the source)."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _other_creatures_you_control(subtype: str) -> Selector:
    """Selector for ``other <Subtype> you control`` (singular subtype)."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value=subtype),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _graveyard_creature_cards() -> Selector:
    """Selector for ``creature cards in your graveyard``."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),),
    )


def _cats_you_control() -> Selector:
    """Selector for ``Cats you control`` (for QCount)."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Cat"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _discard_two_from_hand() -> Selector:
    """Selector for ``two cards from a player's hand`` (CHOOSE mode)."""
    return Selector(
        QConst(2),
        SelectorMode.CHOOSE,
        FAnd(children=()),
        zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.ANY),),
    )


# ---------------------------------------------------------------------------
# Build functions (one per template)
# ---------------------------------------------------------------------------


def _build_mandate_attack_you(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MANDATE_ATTACK,
        args=AtomArgs(
            pairs=(
                ("cards", _creatures_you_control()),
                ("controller", ControllerRef.YOU),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_grant_trample_eot_you(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", _creatures_you_control()),
                ("ability", KeywordAbility(keyword=Keyword.TRAMPLE)),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_modify_pt_eot_you(m: re.Match[str]) -> SentenceOutcome:
    p, t = int(m.group("p")), int(m.group("t"))
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _creatures_you_control()),
                ("power", PtDelta(PtDirection.INCREASE, QConst(p))),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(t))),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_modify_pt_static_you(m: re.Match[str]) -> SentenceOutcome:
    p, t = int(m.group("p")), int(m.group("t"))
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _creatures_you_control()),
                ("power", PtDelta(PtDirection.INCREASE, QConst(p))),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(t))),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_grant_kw_static_you(m: re.Match[str]) -> SentenceOutcome:
    kw_str = m.group("kw")
    kw = _KW_MAP[kw_str]
    atom = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", _creatures_you_control()),
                ("ability", KeywordAbility(keyword=kw)),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_modify_pt_static_opponents(m: re.Match[str]) -> SentenceOutcome:
    """14f FIDELITY FIX (doc 09-30/09, B-11-family static miscompile):
    a bare static anthem sentence is an ABILITY, not a card-level
    EffectOutcome — this row was the one outlier of its family (static-you,
    grant-kw-static-you, other-cats, other-dogs, other-creatures all wrap
    ``StaticAbility``), so on a creature card the bare atom folded into
    the SpellAbility and ran ONCE at cast (Waker of Waves' −1/−0: a
    one-shot cast-time debuff instead of a continuous effect).  The
    StaticAbility wrapper is the executor's live-anthem path (layers
    attach + scope-resolved recompute, 12d); the card then carries no
    cast effect (creature SpellAbility nodes only fold EffectOutcomes —
    the card joins the B-1 not-castable set exactly as the 14e capture
    moved Swindler/Hallowblade, ruled precedent)."""
    p, t = int(m.group("p")), int(m.group("t"))
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _creatures_opponents_control()),
                ("power", PtDelta(PtDirection.DECREASE, QConst(p))),
                ("toughness", PtDelta(PtDirection.DECREASE, QConst(t))),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_modify_pt_protect_other_cats(m: re.Match[str]) -> SentenceOutcome:
    p, t = int(m.group("p")), int(m.group("t"))
    target = _other_creatures_you_control("Cat")
    atom_pt = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", target),
                ("power", PtDelta(PtDirection.INCREASE, QConst(p))),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(t))),
            )
        ),
    )
    atom_prot = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", target),
                (
                    "ability",
                    KeywordAbility(
                        keyword=Keyword.PROTECTION,
                        params=(FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Dog"),),
                    ),
                ),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(Seq(steps=(atom_pt, atom_prot))))


def _build_modify_pt_other_dogs(m: re.Match[str]) -> SentenceOutcome:
    p, t = int(m.group("p")), int(m.group("t"))
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _other_creatures_you_control("Dog")),
                ("power", PtDelta(PtDirection.INCREASE, QConst(p))),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(t))),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_modify_pt_other_creatures(m: re.Match[str]) -> SentenceOutcome:
    p, t = int(m.group("p")), int(m.group("t"))
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _other_creatures()),
                ("power", PtDelta(PtDirection.DECREASE, QConst(p))),
                ("toughness", PtDelta(PtDirection.DECREASE, QConst(t))),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_cant_block(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                ("condition", FAtom(pred=FAtomPred.IS_SOURCE)),
                ("event", DeclareBlockersEvent(FAtom(pred=FAtomPred.IS_SOURCE))),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_modify_pt_while_garruk(m: re.Match[str]) -> SentenceOutcome:
    p, t = int(m.group("p")), int(m.group("t"))
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _self_selector()),
                ("power", PtDelta(PtDirection.INCREASE, QConst(p))),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(t))),
                (
                    "duration",
                    DurationWhileCondition(
                        FAnd(
                            children=(
                                FAtom(
                                    pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"
                                ),
                                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Garruk"),
                                FAtom(
                                    pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU
                                ),
                            )
                        )
                    ),
                ),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_modify_pt_qprop_graveyard(m: re.Match[str]) -> SentenceOutcome:
    t = int(m.group("t"))
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _self_selector()),
                (
                    "power",
                    PtDelta(
                        PtDirection.INCREASE,
                        QProp(
                            referent=_graveyard_creature_cards(),
                            field=QPropField.POWER,
                            agg=QAgg.MAX,
                        ),
                    ),
                ),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(t))),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_grant_lifelink_while_counter(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", _self_selector()),
                ("ability", KeywordAbility(keyword=Keyword.LIFELINK)),
                (
                    "duration",
                    DurationWhileCondition(
                        FAtom(
                            pred=FAtomPred.HAS_COUNTER,
                            counter_kind=CounterKind.PLUS_1_PLUS_1,
                            count=QConst(1),
                        )
                    ),
                ),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_gain_control_enchanted(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.GAIN_CONTROL,
        args=AtomArgs(
            pairs=(
                ("target", _enchanted_creature()),
                ("controller", ControllerRef.YOU),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_draw_discard_bad_deal(m: re.Match[str]) -> SentenceOutcome:
    atom_draw = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(2)),
            )
        ),
    )
    atom_discard = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.OPPONENT)),
                ("from", Zone(ZoneKind.HAND, ControllerRef.OPPONENT)),
                ("controller", ControllerRef.OPPONENT),
                ("cards", _discard_two_from_hand()),
            )
        ),
    )
    return EffectOutcome(effect=Seq(steps=(atom_draw, atom_discard)))


def _build_gain_life_n(m: re.Match[str]) -> SentenceOutcome:
    n = int(m.group("n"))
    atom = Atom(
        verb=Verb.GAIN_LIFE,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(n)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_gain_life_qcount_cats(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.GAIN_LIFE,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QCount(_cats_you_control())),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_lose_life_n(m: re.Match[str]) -> SentenceOutcome:
    n = int(m.group("n"))
    atom = Atom(
        verb=Verb.LOSE_LIFE,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(n)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


# ---------------------------------------------------------------------------
# Build functions — cost modifiers, ETB state, activated abilities, tutors
# ---------------------------------------------------------------------------


def _build_watcher_cost_modifier(m: re.Match[str]) -> SentenceOutcome:
    """Creature spells with flying you cast cost {N} less to cast."""
    n = int(m.group("n"))
    modifier = CostModifier(
        filter=FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING),
            )
        ),
        controller_ref=ControllerRef.YOU,
        delta=CostDeltaReduceGeneric(amount=QConst(n)),
    )
    return AbilityOutcome(ability=modifier)


def _build_total_power_cost_modifier(m: re.Match[str]) -> SentenceOutcome:
    """This spell costs {X} less to cast, where X is the total power of
    creatures you control."""
    modifier = CostModifier(
        filter=FAtom(pred=FAtomPred.IS_SOURCE),
        controller_ref=ControllerRef.YOU,
        delta=CostDeltaReduceGeneric(
            amount=QProp(
                referent=_creatures_you_control(),
                field=QPropField.POWER,
                agg=QAgg.SUM,
            )
        ),
    )
    return AbilityOutcome(ability=modifier)


def _build_conditional_life_cost_modifier(m: re.Match[str]) -> SentenceOutcome:
    """This spell costs {N} less to cast if you've gained N or more life
    this turn."""
    cost_n = int(m.group("cost_n"))
    life_n = int(m.group("life_n"))
    modifier = CostModifier(
        filter=FAtom(pred=FAtomPred.IS_SOURCE),
        controller_ref=ControllerRef.YOU,
        delta=CostDeltaReduceGeneric(amount=QConst(cost_n)),
        condition=FAtom(
            pred=FAtomPred.LIFE_GAINED_THIS_TURN_GE,
            count=QConst(life_n),
            who=ControllerRef.YOU,
        ),
    )
    return AbilityOutcome(ability=modifier)


def _build_stormwing_cost(m: re.Match[str]) -> SentenceOutcome:
    """This spell costs {N}{U} less to cast if you've cast an instant or
    sorcery spell this turn.  Compound reduction: generic N plus one blue
    (CostModifier.extra_deltas, T3 round R3-5)."""
    n = int(m.group("n"))
    modifier = CostModifier(
        filter=FAtom(pred=FAtomPred.IS_SOURCE),
        controller_ref=ControllerRef.YOU,
        delta=CostDeltaReduceGeneric(amount=QConst(n)),
        extra_deltas=(CostDeltaReduceMana(color="U", amount=QConst(1)),),
        condition=FAtom(
            pred=FAtomPred.INSTANT_OR_SORCERY_CAST_THIS_TURN,
            who=ControllerRef.YOU,
        ),
    )
    return AbilityOutcome(ability=modifier)


def _build_opponent_spell_cost_life(m: re.Match[str]) -> SentenceOutcome:
    """Spells your opponents cast that target this creature cost an
    additional N life to cast.  R3-6: TARGETS_SOURCE filter selects the
    affected spells; controller_ref scopes whose."""
    n = int(m.group("n"))
    modifier = CostModifier(
        filter=FAtom(pred=FAtomPred.TARGETS_SOURCE),
        controller_ref=ControllerRef.OPPONENT,
        delta=CostDeltaIncreaseLife(amount=QConst(n)),
    )
    return AbilityOutcome(ability=modifier)


def _build_opponent_spell_cost_mana(m: re.Match[str]) -> SentenceOutcome:
    """Spells your opponents cast that target this creature cost {N} more
    to cast.  R3-6: TARGETS_SOURCE filter, opponent-scoped generic
    increase."""
    n = int(m.group("n"))
    modifier = CostModifier(
        filter=FAtom(pred=FAtomPred.TARGETS_SOURCE),
        controller_ref=ControllerRef.OPPONENT,
        delta=CostDeltaIncreaseGeneric(amount=QConst(n)),
    )
    return AbilityOutcome(ability=modifier)


def _build_enters_tapped(m: re.Match[str]) -> SentenceOutcome:
    """This creature/land enters tapped."""
    return AbilityOutcome(ability=EtBState(tapped=True))


def _build_cast_goblin_top_library(m: re.Match[str]) -> SentenceOutcome:
    """You may cast Goblin spells from the top of your library."""
    source = Selector(
        QUnbounded(),
        SelectorMode.CHOOSE,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Goblin"),
            )
        ),
        zones=(Zone(
            kind=ZoneKind.LIBRARY,
            controller=ControllerRef.YOU,
            position=ZonePosition.TOP,
        ),),
    )
    atom = Atom(
        verb=Verb.CAST,
        args=AtomArgs(pairs=(("source", source),)),
    )
    ability = ActivatedAbility(
        cost=Cost(),
        effect=OptionalEffect(inner=atom),
    )
    return AbilityOutcome(ability=ability)


def _build_cast_graveyard_recost(m: re.Match[str]) -> SentenceOutcome:
    """You may cast this card from your graveyard by paying N life and
    discarding a card in addition to paying its other costs."""
    n = int(m.group("n"))
    cost = Cost(
        parts=(
            CostLife(amount=QConst(n)),
            CostDiscard(
                target=Selector(
                    QConst(1),
                    SelectorMode.CHOOSE,
                    FAnd(children=()),
                    zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),),
                )
            ),
        )
    )
    source = Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(pred=FAtomPred.IS_SOURCE),
        zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),),
    )
    atom = Atom(
        verb=Verb.CAST,
        args=AtomArgs(pairs=(("source", source),)),
    )
    ability = ActivatedAbility(
        cost=cost,
        effect=OptionalEffect(inner=atom),
    )
    return AbilityOutcome(ability=ability)


def _build_search_basri(m: re.Match[str]) -> SentenceOutcome:
    """You may search your library and/or graveyard for a card named
    Basri, Devoted Paladin, reveal it, and put it into your hand."""
    return _build_search_named_card("Basri, Devoted Paladin")


def _build_search_liliana(m: re.Match[str]) -> SentenceOutcome:
    """You may search your library and/or graveyard for a card named
    Liliana, Death Mage, reveal it, and put it into your hand."""
    return _build_search_named_card("Liliana, Death Mage")


def _build_search_named_card(card_name: str) -> SentenceOutcome:
    """Shared tutor builder: search library/graveyard for a named card,
    reveal it, put it into hand."""
    cards = Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(pred=FAtomPred.NAME_EQ, string_value=card_name),
        zones=(Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU), *(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),)),
    )
    search_atom = Atom(
        verb=Verb.SEARCH,
        args=AtomArgs(
            pairs=(
                ("cards", cards),
                ("destination", Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU)),
            )
        ),
    )
    reveal_atom = Atom(
        verb=Verb.REVEAL,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("count", QConst(1)),
            )
        ),
    )
    move_atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.IS_SOURCE),
                        zones=(Zone(
                            kind=ZoneKind.LIBRARY,
                            controller=ControllerRef.YOU,
                            position=ZonePosition.TOP,
                        ),),
                    ),
                ),
                ("destination", Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU)),
            )
        ),
    )
    seq = Seq(steps=(search_atom, reveal_atom, move_atom))
    # The sentence is part of the SORCERY's effect (Basri's Aegis, Liliana's
    # Scorn): it runs as the spell resolves, after the printed sentence before
    # it (CR 608.2c), and the compiler's search-shuffle tail joins this same
    # OptionalEffect ("If you search your library this way, shuffle", only if
    # the search ran). Same inner bytes as the ETB twin B2b-named-card-search
    # (Garruk's Warsteed, Chandra's Firemaw). m21-fidelity (review batches A
    # and C, 2026-10-29): this was a free ActivatedAbility (cost {}) on the
    # sorcery, so the spell never searched when it resolved.
    return EffectOutcome(effect=OptionalEffect(inner=seq))


# ---------------------------------------------------------------------------
# Build functions — round-6 batch (blocked-side restrictions, MANDATE_BLOCK,
# ETB X-counters)
# ---------------------------------------------------------------------------


def _build_cant_be_blocked_aslong_drawn(m: re.Match[str]) -> SentenceOutcome:
    """This creature can't be blocked as long as you've drawn N or more
    cards this turn.  (Tome Anima; grammar round 6 C9 — the "as long as"
    condition lives in ``StaticAbility.condition``
    (CARDS_DRAWN_THIS_TURN_GE, b5a Gnarled Sage precedent), NEVER a
    duration approximation; C10 — the restriction is a PREVENT_EFFECT over
    a universal DeclareBlockersEvent whose R6-4 ``blocked`` slot names the
    source as the blocked-side participant.)  The literal "two" follows the
    Gnarled Sage pattern idiom (b5a pins ``drawn two or more``)."""
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
            )
        ),
    )
    return AbilityOutcome(
        ability=StaticAbility(
            effect=atom,
            condition=FAtom(
                pred=FAtomPred.CARDS_DRAWN_THIS_TURN_GE,
                count=QConst(2),
                who=ControllerRef.YOU,
            ),
        )
    )


def _build_must_block(m: re.Match[str]) -> SentenceOutcome:
    """This creature must be blocked if able.  (Canopy Stalker; grammar
    round 6 R6-5 — MANDATE_BLOCK mirrors MANDATE_ATTACK: subject-scoped
    ``cards`` role, executor deferred per the PHASE_IN-orphan
    precedent.)"""
    atom = Atom(
        verb=Verb.MANDATE_BLOCK,
        args=AtomArgs(pairs=(("cards", _self_selector()),)),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_block_only_flying(m: re.Match[str]) -> SentenceOutcome:
    """This creature can block only creatures with flying.  (Shacklegeist;
    C10 — PREVENT_EFFECT whose blocked-side ``blocked`` slot (R6-4) is
    FNot(KEYWORD_HAS flying): the prevented declarations are exactly the
    source-as-blocker declarations (subject=IS_SOURCE, grammar-round-7
    ``_dbe_both`` idiom) over a non-flying blocked creature.)"""
    atom = Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                ("condition", FAtom(pred=FAtomPred.IS_SOURCE)),
                (
                    "event",
                    DeclareBlockersEvent(
                        FAnd(children=()),
                        subject=FAtom(pred=FAtomPred.IS_SOURCE),
                        blocked=FNot(
                            inner=FAtom(
                                pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING
                            )
                        ),
                    ),
                ),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_enters_with_x_counters(m: re.Match[str]) -> SentenceOutcome:
    """This creature enters with X +1/+1 counters on it.  (Wildwood
    Scourge; bucket-ownership deviation: the round-6 decision doc guessed
    b2a, but the JSON partition owns this key in B4.  X semantics per the
    b5c event-referent precedent (convention C2 + ``QX()`` — b5c line
    ~551 ``_event_reference`` / b5b C8): ETB ZoneChangeEvent with
    subject=IS_SOURCE, then PUT_COUNTER on the event's subject object.)"""
    atom = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAnd(children=()),
                        zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
                        referent="event",
                    ),
                ),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                ("count", QX()),
            )
        ),
    )
    ability = TriggeredAbility(
        event=ZoneChangeEvent(
            from_zone=Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
            to_zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
            subject=FAtom(pred=FAtomPred.IS_SOURCE),
        ),
        condition=None,
        effect=atom,
    )
    return AbilityOutcome(ability=ability)


# ---------------------------------------------------------------------------
# Grammar round-7 batch builders (doc 2026-09-28/03 §3 R7-A)
# ---------------------------------------------------------------------------


def _you_player() -> Selector:
    """Selector for the player ``you`` (b2b's player-zone precedent) —
    the grant target of self-statics like Runed Halo's protection."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAnd(children=()),
        zones=(Zone(kind=ZoneKind.PLAYER, controller=ControllerRef.YOU),),
    )


def _noncreature_nonland_pool() -> Selector:
    """Duress / Kitesail Freebooter ``it`` — the whole revealed hand of
    the target opponent is the CHOOSE pool (ALL + QUnbounded); the pick
    itself is the verb's ``count`` role (r8 CHOOSE canonical)."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FNot(inner=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")),
                FNot(inner=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land")),
            )
        ),
        zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.TARGET_PLAYER),),
    )


def _build_you_choose_from_it(m: re.Match[str]) -> SentenceOutcome:
    """``You choose a noncreature, nonland card from it.`` (Duress s2,
    Kitesail Freebooter s2) — Verb.CHOOSE (R7-1) records the pick as the
    ability's result register; the pool is the revealed hand ("from it"),
    the pick size is QConst(1)."""
    atom = Atom(
        verb=Verb.CHOOSE,
        args=AtomArgs(
            pairs=(
                ("target", _noncreature_nonland_pool()),
                ("count", QConst(1)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_you_have_protection_chosen_name(m: re.Match[str]) -> SentenceOutcome:
    """``You have protection from the chosen card name.`` (Runed Halo s2)
    — static grant of KeywordAbility(PROTECTION) whose param is the
    CHOOSE_NAME read-back FAtom(NAME_CHOSEN) (R7-4); the granted object
    is the player zone for YOU (b2b precedent)."""
    atom = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", _you_player()),
                (
                    "ability",
                    KeywordAbility(
                        keyword=Keyword.PROTECTION,
                        params=(FAtom(pred=FAtomPred.NAME_CHOSEN),),
                    ),
                ),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(effect=atom))


def _build_modpt_eot_per_tapped_this_way(m: re.Match[str]) -> SentenceOutcome:
    """``This creature gets +1/+1 until end of turn for each creature
    tapped this way.`` (Siege Striker s3) — the this-way counter (R7-5
    THIS_WAY_COUNT) scales the delta via QBin(MUL); the tap-set comes
    from the preceding optional tap-any-number ability (B2b, covered)."""
    p, t = int(m.group("p")), int(m.group("t"))
    scale = QBin(
        op=QBinOp.MUL,
        left=QConst(p),
        right=QProp(referent="event", field=QPropField.THIS_WAY_COUNT),
    )
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _self_selector()),
                ("power", PtDelta(PtDirection.INCREASE, scale)),
                (
                    "toughness",
                    PtDelta(
                        PtDirection.INCREASE, QBin(QBinOp.MUL, QConst(t), _this_way())
                    ),
                ),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _this_way() -> QProp:
    return QProp(referent="event", field=QPropField.THIS_WAY_COUNT)


def _build_reveal_one_from_among(m: re.Match[str]) -> SentenceOutcome:
    """``You may reveal a creature card or Garruk planeswalker card from
    among them and put it into your hand.`` (Garruk's Harbinger s2) —
    OptionalEffect ("may") over Seq(REVEAL 1, MOVE_ZONE ONE_OF): the
    looked-at cards stay on top of the library, so the pool is the TOP
    position and the pick is exactly ONE_OF (R7-7).  NAME_CONTAINS
    "Garruk" covers the planeswalker leg."""
    pick_filter: Filter = FOr(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                    FAtom(pred=FAtomPred.NAME_CONTAINS, string_value="Garruk"),
                )
            ),
        )
    )
    pool = Zone(
        kind=ZoneKind.LIBRARY,
        controller=ControllerRef.YOU,
        position=ZonePosition.TOP,
    )
    reveal = Atom(
        verb=Verb.REVEAL,
        args=AtomArgs(pairs=(("controller", ControllerRef.YOU), ("count", QConst(1)))),
    )
    move = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(QConst(1), SelectorMode.ONE_OF, pick_filter, zones=(pool,)),
                ),
                ("destination", Zone(ZoneKind.HAND, ControllerRef.YOU)),
            )
        ),
    )
    return EffectOutcome(effect=OptionalEffect(inner=Seq(steps=(reveal, move))))


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Grammar round-8-C coverage batch builders (doc 2026-09-28/08 §8-C)
# ---------------------------------------------------------------------------


def _result_register_selector(count: Quantity) -> Selector:
    """Neutral-zone CHOOSE selector bound to the ability's result register
    (C2 convention: mode CHOOSE + the neutral Zone(ANY, ANY) + the
    structured referent string).  ``count`` is QConst(1) for a singular
    "that card" and QUnbounded() for a plural "them" — the register holds
    whatever the previous sentence produced, the controller then picks
    any number of them (HoF's "You may cast them this turn")."""
    return Selector(
        count,
        SelectorMode.CHOOSE,
        FAnd(children=()),
        zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
        referent="result",
    )


def _build_cast_them_this_turn(m: re.Match[str]) -> SentenceOutcome:
    """``You may cast them this turn.`` (Chandra, Heart of Fire [−9] s3 —
    the anaphoric follow-on to "…exile them, then shuffle").

    Permission idiom (B4-cast-goblin-top-library): empty-cost
    ActivatedAbility + OptionalEffect(CAST).  14f FIDELITY FIX (doc
    09-30/09): "them" was compiled as the ``referent='result'`` register —
    anaphora that crosses resolutions (the exile ran in the [−9]'s effect
    execution; the permission activates later, when the per-resolution
    register is gone, 14e's residual).  The executor already models the
    exact printed relation — "cards exiled [by this permanent]" — as
    ``FAtomPred.IS_EXILED_WITH_SOURCE`` (R8-6; world half: in exile NOW,
    history half: journalled cause = this ability's source), and Chandra's
    OWN [+1] play-permission row compiles that filter.  "them" is the
    plural of the same population: CHOOSE + QUnbounded + Zone(EXILE, YOU),
    the [+1] row's shape down to the filter (the C2 referent-selector pin
    is not in play — this is no referent selector).  Mana waiver via the
    CAST atom's cost role = Cost(parts=()) (the established empty-cost
    waiver reading, see the b3 UNCOVERED note).
    Documented fidelity edge (shared with the [+1] row's golden — the
    pred's frozen reading is SOURCE-scoped, not row-scoped): both of
    Chandra's exiles carry the same permanent as journalled cause, so the
    two permissions read the union of her exiled-with population.  The
    grammar has no per-ability exile group; the union is the pred's
    established semantics, not an invention of this row.
    Lossy (C11 class, verbatim): "this turn" — CAST has no duration role
    (R9 grammar item: CAST duration role).
    Assembly note: the [−9]'s third sentence; the empty-cost
    ActivatedAbility assembles as a sibling node (r7-B deviation-2
    class — the population hop is the executor's journal read).
    C16: open — whether to cast; WHICH cards is the executor-side
    CHOOSE-QUnbounded reading (all candidates, the [+1] row's twin)."""
    atom = Atom(
        verb=Verb.CAST,
        args=AtomArgs(
            pairs=(
                (
                    "source",
                    Selector(
                        QUnbounded(),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.IS_EXILED_WITH_SOURCE),
                        zones=(Zone(kind=ZoneKind.EXILE, controller=ControllerRef.YOU),),
                    ),
                ),
                ("cost", Cost(parts=())),
            )
        ),
    )
    return AbilityOutcome(
        ability=ActivatedAbility(cost=Cost(), effect=OptionalEffect(inner=atom))
    )


def _build_look_and_play_top_of_library(m: re.Match[str]) -> SentenceOutcome:
    """``You may look at the top card of your library any time, and you may
    play lands from the top of your library.`` (Radha, Heart of Keld) —
    TWO permissions in one sentence (the compiler splits sentences on ". "
    only, never ", and ", so one template emits both).  The empty-cost
    ActivatedAbility effect is a Seq of TWO sibling OptionalEffect steps
    — LOOK_AT and top-land CAST — keeping BOTH may-decisions open (C15:
    Optional(Seq(a, b)) would fuse them into one decision; Seq of
    Optionals keeps two independent vertices, the same shape the default
    continuation merge uses for "do X. You may do Y").
    LOOK_AT carries no zone role — the B2b precedent (Sasaya) notes
    "LOOK_AT implicitly looks at the top of the library"; count=1 = "the
    top card".  "any time" is the static permission reading (the
    empty-cost ActivatedAbility idiom).
    Lossy (C11 class, verbatim): lands are PLAYED, not cast — CAST is the
    only from-zone permission verb (ADD_LAND_PLAY is the additional-drop
    count, not a from-zone play); same note as the HoF row.
    C16: open — whether to look, whether to play the top land."""
    look = OptionalEffect(
        inner=Atom(
            verb=Verb.LOOK_AT,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.YOU),
                    ("count", QConst(1)),
                )
            ),
        )
    )
    play_top = OptionalEffect(
        inner=Atom(
            verb=Verb.CAST,
            args=AtomArgs(
                pairs=(
                    (
                        "source",
                        Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land"),
                            zones=(Zone(
                                kind=ZoneKind.LIBRARY,
                                controller=ControllerRef.YOU,
                                position=ZonePosition.TOP,
                            ),),
                        ),
                    ),
                )
            ),
        )
    )
    return AbilityOutcome(
        ability=ActivatedAbility(cost=Cost(), effect=Seq(steps=(look, play_top)))
    )


def _build_play_that_card_until(m: re.Match[str]) -> SentenceOutcome:
    """``You may play that card until you exile another card with this
    enchantment.`` (Furious Rise s2) — OptionalEffect(CAST) over the
    result register (QConst(1): "that card" singular — the end-step exile
    of s1).
    Lossy (C11 class, verbatim): "until you exile another card with this
    enchantment" — the Duration vocabulary has no until-the-next-event
    variant (DurationUntilLeaves is leaves-the-battlefield only,
    DurationWhileCondition is a state predicate) — the window is dropped
    (R9 grammar item: until-next-event duration).  CAST-for-play as in
    the Radha/HoF rows.
    Assembly note: s2 of the end-step trigger; the empty-cost
    ActivatedAbility assembles as a sibling node (r7-B deviation-2).
    C16: open — whether to play the exiled card."""
    atom = Atom(
        verb=Verb.CAST,
        args=AtomArgs(pairs=(("source", _result_register_selector(QConst(1))),)),
    )
    return AbilityOutcome(
        ability=ActivatedAbility(cost=Cost(), effect=OptionalEffect(inner=atom))
    )


def _build_azusa_extra_land_plays(m: re.Match[str]) -> SentenceOutcome:
    """``You may play two additional lands on each of your turns.`` (Azusa,
    Lost but Seeking) — Verb.ADD_LAND_PLAY (R8-8): count = QConst(2) —
    C14 spelled-number word-pin ("two" is not digit-normalized into the
    shape; Gnarled-Sage precedent).

    A STATIC ability (CR 604.1; 305.2: continuous effects may raise the
    land allowance): StaticAbility(OptionalEffect(ADD_LAND_PLAY)), the
    Teferi, Master of Time permission shape (the "you may" is the use,
    playing the land; layers._new_static unwraps it). No duration role: the
    static's own lifetime is the window, as for every other static atom.
    m21-fidelity (adversarial gate, 2026-10-29): this was a free activated
    ability (cost {}), so nothing was granted until it was activated and
    each activation added two more land plays (0 -> 2 -> 4 -> 6).
    C16: open — whether to use either additional land play."""
    atom = Atom(
        verb=Verb.ADD_LAND_PLAY,
        args=AtomArgs(pairs=(("count", QConst(2)),)),
    )
    return AbilityOutcome(ability=StaticAbility(effect=OptionalEffect(inner=atom)))


def _build_noncombat_damage_cost_modifier(m: re.Match[str]) -> SentenceOutcome:
    """``This spell costs {X} less to cast, where X is the total amount of
    noncombat damage dealt to your opponents this turn.`` (Chandra's
    Incinerator) — CostModifier sibling (b4 _build_total_power_cost_
    modifier precedent: filter=IS_SOURCE, delta=CostDeltaReduceGeneric
    with a dynamic amount): amount = QThisTurn(NONCOMBAT_DAMAGE,
    ALL_OPPONENTS) — R8-10's this-turn kind aggregated across ALL
    opponents (the single total across the opponent set the printed
    "total … to your opponents" asks for).
    Lossy (C11 class, verbatim): QThisTurn's referent is a
    ControllerRef — the R8-10 grounding note reads it DEALT-BY-the
    referent while the printed text is dealt-TO-the-opponents; no
    damage-recipient quantity exists (dealer and recipient sides cannot
    both be pinned in one node — R9 item: damage-received this-turn
    referent).  The executor binds the ALL_OPPONENTS reading to the
    recipient side per this docstring.
    C16: none — board-dynamic amount, fully forced."""
    modifier = CostModifier(
        filter=FAtom(pred=FAtomPred.IS_SOURCE),
        controller_ref=ControllerRef.YOU,
        delta=CostDeltaReduceGeneric(
            amount=QThisTurn(
                kind=ThisTurnKind.NONCOMBAT_DAMAGE,
                referent=ControllerRef.ALL_OPPONENTS,
            )
        ),
    )
    return AbilityOutcome(ability=modifier)


def _build_spend_mana_any_color(m: re.Match[str]) -> SentenceOutcome:
    """``You may spend mana as though it were mana of any color.``
    (Chromatic Orrery) — grammar round 9-B row 7: Verb.MANA_POLICY (R9-3,
    C21) with the closed scope string "ALL_YOURS" (the permanent
    color-flooding permission, distinct from Vodalian's event-anchored
    "THIS_MANA").  No filter role value — the permission covers every
    spend.

    DURATION NOTE (verbatim): MANA_POLICY carries no duration role; the
    static's own permanence IS the DurationPermanent reading (the same
    carrier judgement as the round-8-C CAST-waiver rows, which used the
    OptionalEffect-inside-static shape).  OptionalEffect wrap keeps the
    "may" decision open at each spend (C15 — the policy permits, the
    controller decides per spend).  Executor deferred per the
    ADD_LAND_PLAY orphan precedent (PC-6: verb consumed this round).
    C16: open — whether/how each mana payment uses the flooding policy."""
    atom = Atom(
        verb=Verb.MANA_POLICY,
        args=AtomArgs(pairs=(("scope", "ALL_YOURS"),)),
    )
    return AbilityOutcome(ability=StaticAbility(effect=OptionalEffect(inner=atom)))


def _build_tefei_grant_activation(m: re.Match[str]) -> SentenceOutcome:
    """``You may activate loyalty abilities of Teferi on any player's turn
    any time you could cast an instant.`` (Teferi, Master of Time) —
    grammar round 9-B row 8, closing the 8-C withdrawal: Verb.
    GRANT_ACTIVATION (R9-7) with filter = FAnd(TYPE_EQ Planeswalker,
    NAME_CONTAINS "Teferi") (the ability-holder gate) and window =
    ActivationWindow.INSTANT — "any time you could cast an instant" names
    the instant window EXACTLY (R9-1 vocabulary; NOT SORCERY — the r10
    grammar fixture's SORCERY example is unrelated to this row's text).
    OptionalEffect wrap per C15 ("you may"); executor deferred per the
    GRANT_ABILITY-adjacent orphan precedent (PC-6: verb consumed this round).

    C16: open — WHICH loyalty ability and WHEN inside the widened window."""
    holder = FAnd(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
            FAtom(pred=FAtomPred.NAME_CONTAINS, string_value="Teferi"),
        )
    )
    atom = Atom(
        verb=Verb.GRANT_ACTIVATION,
        args=AtomArgs(pairs=(("filter", holder), ("window", ActivationWindow.INSTANT))),
    )
    return AbilityOutcome(ability=StaticAbility(effect=OptionalEffect(inner=atom)))


def _build_enthralling_target_choice(m: re.Match[str]) -> SentenceOutcome:
    """``You can't choose an untapped creature as this spell's target as
    you cast it.`` (Enthralling Hold) — grammar round 9-B row 9, C11-class
    encoding: choice-restriction ≈ owner-scoped targeting PREVENTION.
    PREVENT_EFFECT over TargetingEvent whose filter narrows the would-be
    target (FAnd(TYPE_EQ Creature, IS_UNTAPPED)); the SPELL SCOPE rides
    the condition slot as FAtom(IS_ANY_TARGET) — the b3/Subira precedent
    that a spell-internal restriction binds to the spell's own target
    set ("as you cast it" = the targeting event IS the spell's choice).
    FIDELITY NOTE (C11-class): the grammar cannot distinguish choosing at
    target-declaration from a prevention that fires on targeting itself —
    on this pool the two coincide (the restriction only ever applies to
    this spell's own choices); no targeting-legality node exists
    (round-7 family, doc /11 §DEFER adjacent).

    C16: none — a legality restriction, fully forced."""
    untapped_creature = FAnd(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FAtom(pred=FAtomPred.IS_UNTAPPED),
        )
    )
    atom = Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                ("condition", FAtom(pred=FAtomPred.IS_ANY_TARGET)),
                ("event", TargetingEvent(filter=untapped_creature)),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(effect=atom))


TEMPLATES: tuple[Template, ...] = (
    Template(
        tid="B4-mandate-attack-you",
        name="creatures you control attack each combat if able",
        bucket=_BUCKET,
        pattern=re.compile(r"^Creatures you control attack each combat if able\.$"),
        priority=_PRIORITY,
        build=_build_mandate_attack_you,
    ),
    Template(
        tid="B4-grant-trample-eot-you",
        name="creatures you control gain trample until end of turn",
        bucket=_BUCKET,
        pattern=re.compile(r"^Creatures you control gain trample until end of turn\.$"),
        priority=_PRIORITY,
        build=_build_grant_trample_eot_you,
    ),
    Template(
        tid="B4-modify-pt-eot-you",
        name="creatures you control get +P/+T until end of turn",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Creatures you control get \+(?P<p>\d+)/\+(?P<t>\d+) until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_modify_pt_eot_you,
    ),
    Template(
        tid="B4-modify-pt-static-you",
        name="creatures you control get +P/+T (static)",
        bucket=_BUCKET,
        pattern=re.compile(r"^Creatures you control get \+(?P<p>\d+)/\+(?P<t>\d+)\.$"),
        priority=_PRIORITY,
        build=_build_modify_pt_static_you,
    ),
    Template(
        tid="B4-grant-kw-static-you",
        name="creatures you control have <keyword> (static)",
        bucket=_BUCKET,
        pattern=re.compile(r"^Creatures you control have (?P<kw>[a-z]+)\.$"),
        priority=_PRIORITY,
        build=_build_grant_kw_static_you,
    ),
    Template(
        tid="B4-modify-pt-static-opponents",
        name="creatures your opponents control get -P/-T",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Creatures your opponents control get -(?P<p>\d+)/-(?P<t>\d+)\.$"
        ),
        priority=_PRIORITY,
        build=_build_modify_pt_static_opponents,
    ),
    Template(
        tid="B4-modify-pt-protect-other-cats",
        name="other cats you control get +P/+T and have protection from dogs",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Other Cats you control get \+(?P<p>\d+)/\+(?P<t>\d+) "
            r"and have protection from Dogs\.$"
        ),
        priority=_PRIORITY,
        build=_build_modify_pt_protect_other_cats,
    ),
    Template(
        tid="B4-modify-pt-other-dogs",
        name="other dogs you control get +P/+T",
        bucket=_BUCKET,
        pattern=re.compile(r"^Other Dogs you control get \+(?P<p>\d+)/\+(?P<t>\d+)\.$"),
        priority=_PRIORITY,
        build=_build_modify_pt_other_dogs,
    ),
    Template(
        tid="B4-modify-pt-other-creatures",
        name="other creatures get -P/-T",
        bucket=_BUCKET,
        pattern=re.compile(r"^Other creatures get -(?P<p>\d+)/-(?P<t>\d+)\.$"),
        priority=_PRIORITY,
        build=_build_modify_pt_other_creatures,
    ),
    Template(
        tid="B4-cant-block",
        name="this creature can't block",
        bucket=_BUCKET,
        pattern=re.compile(r"^This creature can't block\.$"),
        priority=_PRIORITY,
        build=_build_cant_block,
    ),
    Template(
        tid="B4-modify-pt-while-garruk",
        name="this creature gets +P/+T as long as you control a Garruk planeswalker",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^This creature gets \+(?P<p>\d+)/\+(?P<t>\d+) "
            r"as long as you control a Garruk planeswalker\.$"
        ),
        priority=_PRIORITY,
        build=_build_modify_pt_while_garruk,
    ),
    Template(
        tid="B4-modify-pt-qprop-graveyard",
        name="this creature gets +X/+T, X = greatest power in graveyard",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^This creature gets \+X/\+(?P<t>\d+), "
            r"where X is the greatest power among creature cards in your graveyard\.$"
        ),
        priority=_PRIORITY,
        build=_build_modify_pt_qprop_graveyard,
    ),
    Template(
        tid="B4-grant-lifelink-while-counter",
        name="this creature has lifelink as long as it has a +1/+1 counter",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^This creature has lifelink as long as it has a "
            r"\+(?P<p>\d+)/\+(?P<t>\d+) counter on it\.$"
        ),
        priority=_PRIORITY,
        build=_build_grant_lifelink_while_counter,
    ),
    Template(
        tid="B4-gain-control-enchanted",
        name="you control enchanted creature",
        bucket=_BUCKET,
        pattern=re.compile(r"^You control enchanted creature\.$"),
        priority=_PRIORITY,
        build=_build_gain_control_enchanted,
    ),
    Template(
        tid="B4-draw-discard-bad-deal",
        name="you draw two cards and each opponent discards two cards",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^You draw two cards and each opponent discards two cards\.$"
        ),
        priority=_PRIORITY,
        build=_build_draw_discard_bad_deal,
    ),
    Template(
        tid="B4-gain-life-n",
        name="you gain N life",
        bucket=_BUCKET,
        pattern=re.compile(r"^You gain (?P<n>\d+) life\.$"),
        priority=_PRIORITY,
        build=_build_gain_life_n,
    ),
    Template(
        tid="B4-gain-life-qcount-cats",
        name="you gain life equal to the number of cats you control",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^You gain life equal to the number of Cats you control\.$"
        ),
        priority=_PRIORITY,
        build=_build_gain_life_qcount_cats,
    ),
    Template(
        tid="B4-lose-life-n",
        name="you lose N life",
        bucket=_BUCKET,
        pattern=re.compile(r"^You lose (?P<n>\d+) life\.$"),
        priority=_PRIORITY,
        build=_build_lose_life_n,
    ),
    Template(
        tid="B4-cost-modifier-watcher",
        name="creature spells with flying you cast cost N less",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Creature spells with flying you cast cost \{(?P<n>\d+)\} less to cast\.$"
        ),
        priority=_PRIORITY,
        build=_build_watcher_cost_modifier,
    ),
    Template(
        tid="B4-cost-modifier-total-power",
        name="this spell costs X less, X = total power of creatures you control",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^This spell costs \{X\} less to cast, "
            r"where X is the total power of creatures you control\.$"
        ),
        priority=_PRIORITY,
        build=_build_total_power_cost_modifier,
    ),
    Template(
        tid="B4-cost-modifier-conditional-life",
        name="this spell costs N less if you've gained N or more life this turn",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^This spell costs \{(?P<cost_n>\d+)\} less to cast if you've "
            r"gained (?P<life_n>\d+) or more life this turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_conditional_life_cost_modifier,
    ),
    Template(
        tid="B4-enters-tapped-creature",
        # ZND-2 T3: widened to the non-land permanent nouns, DISJOINT from
        # B4-enters-tapped-land below (one noun, one template — identical
        # overlap on two patterns would be a tolerated-but-ugnoy double
        # claim; the tree is type-independent: EtBState(tapped=True)).
        # M21 census 2026-10-18: zero "This artifact/enchantment enters
        # tapped." sentences (buckets and goldens stay byte-identical);
        # ZNR gains Spare Supplies.
        name="this creature/artifact/enchantment enters tapped",
        bucket=_BUCKET,
        pattern=re.compile(r"^This (?:creature|artifact|enchantment) enters tapped\.$"),
        priority=_PRIORITY,
        build=_build_enters_tapped,
    ),
    Template(
        tid="B4-enters-tapped-land",
        name="this land enters tapped",
        bucket=_BUCKET,
        pattern=re.compile(r"^This land enters tapped\.$"),
        priority=_PRIORITY,
        build=_build_enters_tapped,
    ),
    Template(
        tid="B4-cast-goblin-top-library",
        name="you may cast Goblin spells from the top of your library",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^You may cast Goblin spells from the top of your library\.$"
        ),
        priority=_PRIORITY,
        build=_build_cast_goblin_top_library,
    ),
    Template(
        tid="B4-cast-graveyard-recost",
        name="you may cast this card from graveyard by paying N life and discarding",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^You may cast this card from your graveyard by paying (?P<n>\d+) life "
            r"and discarding a card in addition to paying its other costs\.$"
        ),
        priority=_PRIORITY,
        build=_build_cast_graveyard_recost,
    ),
    Template(
        tid="B4-tutor-basri",
        name="you may search library/graveyard for Basri, Devoted Paladin",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^You may search your library and/or graveyard for a card named "
            r"Basri, Devoted Paladin, reveal it, and put it into your hand\.$"
        ),
        priority=_PRIORITY,
        build=_build_search_basri,
    ),
    Template(
        tid="B4-tutor-liliana",
        name="you may search library/graveyard for Liliana, Death Mage",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^You may search your library and/or graveyard for a card named "
            r"Liliana, Death Mage, reveal it, and put it into your hand\.$"
        ),
        priority=_PRIORITY,
        build=_build_search_liliana,
    ),
    Template(
        tid="B4-stormwing-cost",
        name="this spell costs {N}{U} less if you've cast an instant/sorcery this turn",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^This spell costs \{(?P<n>\d+)\}\{U\} less to cast if you've cast an "
            r"instant or sorcery spell this turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_stormwing_cost,
    ),
    Template(
        tid="B4-opponent-spell-cost-life",
        name="opponent spells targeting this creature cost an additional N life",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Spells your opponents cast that target this creature cost an "
            r"additional (?P<n>\d+) life to cast\.$"
        ),
        priority=_PRIORITY,
        build=_build_opponent_spell_cost_life,
    ),
    Template(
        tid="B4-opponent-spell-cost-mana",
        name="opponent spells targeting this creature cost {N} more",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Spells your opponents cast that target this creature cost "
            r"\{(?P<n>\d+)\} more to cast\.$"
        ),
        priority=_PRIORITY,
        build=_build_opponent_spell_cost_mana,
    ),
    Template(
        tid="B4-cant-be-blocked-aslong-drawn",
        name="this creature can't be blocked as long as you've drawn two this turn",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^This creature can't be blocked as long as you've drawn two "
            r"or more cards this turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_cant_be_blocked_aslong_drawn,
    ),
    Template(
        tid="B4-must-block",
        name="this creature must be blocked if able",
        bucket=_BUCKET,
        pattern=re.compile(r"^This creature must be blocked if able\.$"),
        priority=_PRIORITY,
        build=_build_must_block,
    ),
    Template(
        tid="B4-block-only-flying",
        name="this creature can block only creatures with flying",
        bucket=_BUCKET,
        pattern=re.compile(r"^This creature can block only creatures with flying\.$"),
        priority=_PRIORITY,
        build=_build_block_only_flying,
    ),
    Template(
        tid="B4-enters-with-x-counters",
        name="this creature enters with X +1/+1 counters on it",
        bucket=_BUCKET,
        pattern=re.compile(r"^This creature enters with X \+1/\+1 counters on it\.$"),
        priority=_PRIORITY,
        build=_build_enters_with_x_counters,
    ),  # --- grammar round-7 batch (doc 2026-09-28/03 §3 R7-A) ---
    Template(
        tid="B4-you-choose-from-it",
        name="you choose a noncreature nonland card from it (CHOOSE)",
        bucket=_BUCKET,
        pattern=re.compile(r"^You choose a noncreature, nonland card from it\.$"),
        priority=_PRIORITY,
        build=_build_you_choose_from_it,
    ),
    Template(
        tid="B4-protection-chosen-name",
        name="you have protection from the chosen card name",
        bucket=_BUCKET,
        pattern=re.compile(r"^You have protection from the chosen card name\.$"),
        priority=_PRIORITY,
        build=_build_you_have_protection_chosen_name,
    ),
    Template(
        tid="B4-per-tapped-this-way",
        name="this creature gets +P/+T EOT for each creature tapped this way",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^This creature gets \+(?P<p>\d+)/\+(?P<t>\d+) until end of turn "
            r"for each creature tapped this way\.$"
        ),
        priority=_PRIORITY,
        build=_build_modpt_eot_per_tapped_this_way,
    ),
    Template(
        tid="B4-reveal-one-from-among",
        name="you may reveal a creature or Garruk PW from among them to hand",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^You may reveal a creature card or Garruk planeswalker card "
            r"from among them and put it into your hand\.$"
        ),
        priority=_PRIORITY,
        build=_build_reveal_one_from_among,
    ),
    # --- grammar round-8-C coverage batch (doc 2026-09-28/08 §8-C) ---
    Template(
        tid="B4-cast-them-this-turn",
        name="you may cast them this turn (result-register CAST + cost waiver)",
        bucket=_BUCKET,
        pattern=re.compile(r"^You may cast them this turn\.$"),
        priority=_PRIORITY,
        build=_build_cast_them_this_turn,
    ),
    Template(
        tid="B4-look-play-top-of-library",
        name="look at top card any time AND play lands from top (two optionals, C15)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^You may look at the top card of your library any time, and "
            r"you may play lands from the top of your library\.$"
        ),
        priority=_PRIORITY,
        build=_build_look_and_play_top_of_library,
    ),
    Template(
        tid="B4-play-that-card-until",
        name="you may play that card until you exile another (result-register CAST; duration lossy)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^You may play that card until you exile another card with "
            r"this enchantment\.$"
        ),
        priority=_PRIORITY,
        build=_build_play_that_card_until,
    ),
    Template(
        tid="B4-azusa-extra-land-plays",
        name="you may play two additional lands each of your turns (ADD_LAND_PLAY)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^You may play two additional lands on each of your turns\.$"
        ),
        priority=_PRIORITY,
        build=_build_azusa_extra_land_plays,
    ),
    Template(
        tid="B4-noncombat-damage-cost-modifier",
        name="this spell costs X less where X is noncombat damage this turn (QThisTurn)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^This spell costs \{X\} less to cast, where X is the total "
            r"amount of noncombat damage dealt to your opponents this "
            r"turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_noncombat_damage_cost_modifier,
    ),
    # --- grammar round-9-B coverage batch (doc 2026-09-28/11 §9-B rows 7-9) ---
    Template(
        tid="B4-spend-any-color",
        name="mana policy: spend mana as though any color (MANA_POLICY ALL_YOURS)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^You may spend mana as though it were mana of any color\.$"
        ),
        priority=_PRIORITY,
        build=_build_spend_mana_any_color,
    ),
    Template(
        tid="B4-teferi-grant-activation",
        name="activation permission: Teferi loyalty abilities, instant window (GRANT_ACTIVATION)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^You may activate loyalty abilities of Teferi on any player's "
            r"turn any time you could cast an instant\.$"
        ),
        priority=_PRIORITY,
        build=_build_tefei_grant_activation,
    ),
    Template(
        tid="B4-enthralling-target-choice",
        name="targeting legality: no untapped creature choice (PREVENT over TargetingEvent, C11-class)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^You can't choose an untapped creature as this spell's target "
            r"as you cast it\.$"
        ),
        priority=_PRIORITY,
        build=_build_enthralling_target_choice,
    ),
)

UNCOVERED: tuple[tuple[str, str], ...] = (
    (
        "You may choose new targets for the copy.",
        "No copy-targeting grammar construct",
    ),
)
