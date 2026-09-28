"""B4 bucket templates — 34 templates covering 34 of 47 B4 shapes.

Bucket input: ``/tmp/opencode/phase1_buckets/B4.json`` (47 normalized shape
keys → ``[card, sentence]`` pairs; sentences carry *concrete* numbers, keys
carry ``N`` placeholders).  Templates fullmatch the **concrete** oracle
sentence, never the normalized key.

Coverage (47 = 34 template + 13 uncovered):

- **34 template-covered shapes**: static P/T grants (self, creatures you
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
- **13 uncovered shapes**: no grammar construct exists (damage-based cost
  reduction without MODIFY_COST, per-event repeated statics, targeting
  restriction, chosen-name anaphora, complex You may constructs,
  mana-color flooding).  Recorded in UNCOVERED.

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
    FNot,
    Keyword,
    KeywordAbility,
    OptionalEffect,
    PtDelta,
    PtDirection,
    QAgg,
    QConst,
    QCount,
    QProp,
    QPropField,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
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
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
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
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
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
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ALL_OPPONENTS),
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
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
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
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
    )


def _graveyard_creature_cards() -> Selector:
    """Selector for ``creature cards in your graveyard``."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
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
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
    )


def _discard_two_from_hand() -> Selector:
    """Selector for ``two cards from a player's hand`` (CHOOSE mode)."""
    return Selector(
        QConst(2),
        SelectorMode.CHOOSE,
        FAnd(children=()),
        Zone(kind=ZoneKind.HAND, controller=ControllerRef.ANY),
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
    return EffectOutcome(effect=atom)


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
        verb=Verb.DISCARD,
        args=AtomArgs(
            pairs=(
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
        Zone(
            kind=ZoneKind.LIBRARY,
            controller=ControllerRef.YOU,
            position=ZonePosition.TOP,
        ),
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
                    Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
                )
            ),
        )
    )
    source = Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(pred=FAtomPred.IS_SOURCE),
        Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
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
        Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU),
        zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),),
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
                        Zone(
                            kind=ZoneKind.LIBRARY,
                            controller=ControllerRef.YOU,
                            position=ZonePosition.TOP,
                        ),
                    ),
                ),
                ("destination", Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU)),
            )
        ),
    )
    seq = Seq(steps=(search_atom, reveal_atom, move_atom))
    ability = ActivatedAbility(
        cost=Cost(),
        effect=OptionalEffect(inner=seq),
    )
    return AbilityOutcome(ability=ability)


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
                        Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
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
# Template definitions
# ---------------------------------------------------------------------------

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
        name="this creature enters tapped",
        bucket=_BUCKET,
        pattern=re.compile(r"^This creature enters tapped\.$"),
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
    ),
)

UNCOVERED: tuple[tuple[str, str], ...] = (
    (
        "This spell costs {X} less to cast, where X is the total amount of noncombat damage dealt to your opponents this turn.",
        "No MODIFY_COST verb in grammar",
    ),
    (
        "This creature gets +N/+N until end of turn for each creature tapped this way.",
        (
            "No per-event repeated static with turn-scoped trigger "
            "(round-7 family: trigger-counted statics)"
        ),
    ),
    (
        "You can't choose an untapped creature as this spell's target as you cast it.",
        "No targeting-restriction grammar construct (round-7 family: target legality)",
    ),
    (
        "You choose a noncreature, nonland card from it.",
        "No anaphora / name-choice grammar construct",
    ),
    (
        "You have protection from the chosen card name.",
        (
            "No dynamic protection-from-name grammar construct "
            "(round-7 family: chosen-name anaphora)"
        ),
    ),
    (
        "You may activate loyalty abilities of Teferi on any player's turn any time you could cast an instant.",
        "No cross-card activated ability activation grammar",
    ),
    (
        "You may cast them this turn.",
        "No anaphora / cast-them-this-turn grammar construct",
    ),
    ("You may choose new targets for the copy.", "No copy-targeting grammar construct"),
    (
        "You may look at the top card of your library any time, and you may play lands from the top of your library.",
        "No complex multi-ability You may construct",
    ),
    (
        "You may play that card until you exile another card with this enchantment.",
        "No anaphora / conditional play grammar",
    ),
    (
        "You may play two additional lands on each of your turns.",
        "No land-speed-modification grammar construct",
    ),
    (
        "You may reveal a creature card or Garruk planeswalker card from among them and put it into your hand.",
        "No complex tutor / reveal-and-put grammar",
    ),
    (
        "You may spend mana as though it were mana of any color.",
        "No mana-color-flooding grammar construct",
    ),
)
