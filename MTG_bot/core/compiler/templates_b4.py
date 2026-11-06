"""B4 bucket templates: statics, cost modifiers, permissions and one-shot effects.

Bucket input: ``/tmp/opencode/phase1_buckets/B4.json`` (normalized shape keys → ``[card,
sentence]`` pairs; sentences carry concrete numbers, keys carry ``N`` placeholders). Templates
fullmatch the concrete oracle sentence, never the normalized key.

Conventions:
- Static abilities on permanents → ``AbilityOutcome(StaticAbility(...))``
- Spell effects / one-time actions → ``EffectOutcome(...)``
- Cast-from-zone permissions ("You may cast ... from ...") → an ``ActivatedAbility`` (empty cost
  unless the card prints one) whose effect is ``OptionalEffect(CAST)``
- ``other <Subtype> you control`` → ``FNot(inner=FAtom(IS_SOURCE))`` in the filter

Every B4 sentence fullmatches at most one template (the patterns are pairwise disjoint); the tests
check it.
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
    Verb,
    Zone,
    ZoneKind,
    ZonePosition,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    SentenceOutcome,
    Template,
    and_or_zone_search,
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
    """A static anthem is a StaticAbility, like the rest of its family: on a creature card a bare
    EffectOutcome would fold into the SpellAbility and run once, at cast."""
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
    """``You gain life equal to the number of Cats you control.`` (Rin and Seri, Inseparable): the
    second instruction of the activated ability before it (CR 602.1, CR 608.2c), so an effect the
    compiler's continuation fold appends to that ability, not a StaticAbility of its own."""
    atom = Atom(
        verb=Verb.GAIN_LIFE,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QCount(_cats_you_control())),
            )
        ),
    )
    return EffectOutcome(effect=atom)


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
    (CostModifier.extra_deltas)."""
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
    additional N life to cast.  The TARGETS_SOURCE filter selects the
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
    to cast."""
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
    """Search library and/or graveyard for a named card, reveal it, put it into hand.

    "library and/or graveyard" is a visible zone choice (templates.and_or_zone_search), as in
    the ETB twin; the shuffle sentence joins only the options that search the library."""

    def search_in(zones: tuple[Zone, ...]) -> Seq:
        cards = Selector(
            QConst(1),
            SelectorMode.CHOOSE,
            FAtom(pred=FAtomPred.NAME_EQ, string_value=card_name),
            zones=zones,
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
        return Seq(steps=(search_atom, reveal_atom))

    # "put it into your hand" is the SEARCH's own destination, as in the ETB twin.
    seq = and_or_zone_search(
        search_in,
        Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU),
        Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
    )
    # The sentence is part of the sorcery's effect (Basri's Aegis, Liliana's
    # Scorn): it runs as the spell resolves, after the printed sentence before
    # it (CR 608.2c), and the compiler's search-shuffle tail joins this same
    # OptionalEffect ("If you search your library this way, shuffle", only if
    # the search ran). Same inner tree as the ETB twin B2b-named-card-search
    # (Garruk's Warsteed, Chandra's Firemaw).
    return EffectOutcome(effect=OptionalEffect(inner=seq))


# ---------------------------------------------------------------------------
# Build functions — blocked-side restrictions, MANDATE_BLOCK, ETB X-counters
# ---------------------------------------------------------------------------


def _build_cant_be_blocked_aslong_drawn(m: re.Match[str]) -> SentenceOutcome:
    """This creature can't be blocked as long as you've drawn two or more cards this turn (Tome
    Anima). The "as long as" condition is ``StaticAbility.condition`` (CARDS_DRAWN_THIS_TURN_GE),
    never a duration; the restriction is a PREVENT_EFFECT over a universal DeclareBlockersEvent
    whose ``blocked`` side is the source. The pattern pins the word "two"."""
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
    """This creature must be blocked if able (Canopy Stalker). MANDATE_BLOCK mirrors
    MANDATE_ATTACK: a subject-scoped ``cards`` role."""
    atom = Atom(
        verb=Verb.MANDATE_BLOCK,
        args=AtomArgs(pairs=(("cards", _self_selector()),)),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


def _build_block_only_flying(m: re.Match[str]) -> SentenceOutcome:
    """This creature can block only creatures with flying (Shacklegeist): PREVENT_EFFECT over the
    declarations where the source blocks (subject=IS_SOURCE) a creature without flying
    (``blocked``=FNot(KEYWORD_HAS flying))."""
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
    """This creature enters with X +1/+1 counters on it (Wildwood Scourge, Ivy Elemental, the X
    hydras). An entering-state replacement (CR 614.1c), not a trigger: the permanent enters with
    the counters, so it is never an X-less 0/0 and "whenever a creature with power 4 or greater
    enters" sees its full size. The shape of the constant "enters with N counters" cards; the
    executor stamps the X the spell was cast with (0 when it entered without being cast,
    CR 107.3g)."""
    return AbilityOutcome(
        ability=EtBState(initial_counters=((CounterKind.PLUS_1_PLUS_1, QX()),))
    )


# ---------------------------------------------------------------------------
# Build functions — anaphora: chosen cards and names, this-way counts, looked-at cards
# ---------------------------------------------------------------------------


def _you_player() -> Selector:
    """Selector for the player ``you``: the grant target of player statics like Runed Halo's
    protection."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAnd(children=()),
        zones=(Zone(kind=ZoneKind.PLAYER, controller=ControllerRef.YOU),),
    )


def _noncreature_nonland_pool() -> Selector:
    """Duress / Kitesail Freebooter ``it``: the target opponent's revealed hand is the CHOOSE
    pool (ALL + QUnbounded); the pick size is the verb's ``count`` role."""
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
    """``You choose a noncreature, nonland card from it.`` (Duress, Kitesail Freebooter):
    Verb.CHOOSE records the pick as the ability's result register; the pool is the revealed
    hand ("from it"), the pick size is QConst(1)."""
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
    """``You have protection from the chosen card name.`` (Runed Halo): a static PROTECTION
    grant to the player you, whose param is the CHOOSE_NAME read-back FAtom(NAME_CHOSEN)."""
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
    """``This creature gets +1/+1 until end of turn for each creature tapped this way.`` (Siege
    Striker): THIS_WAY_COUNT, the number the preceding tap-any-number sentence tapped, scales the
    delta via QBin(MUL)."""
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
    among them and put it into your hand.`` (Garruk's Harbinger) —
    OptionalEffect ("may") over Seq(REVEAL 1, MOVE_ZONE ONE_OF): the
    looked-at cards stay on top of the library, so the pool is the TOP
    position and the pick is exactly ONE_OF.  NAME_CONTAINS
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
# Build functions — permissions, land plays, mana policy, activation windows
# ---------------------------------------------------------------------------


def _result_register_selector(count: Quantity) -> Selector:
    """CHOOSE selector over the ability's result register: the neutral Zone(ANY, ANY) and the
    referent "result". ``count`` is QConst(1) for a singular "that card", QUnbounded() for a
    plural "them"."""
    return Selector(
        count,
        SelectorMode.CHOOSE,
        FAnd(children=()),
        zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
        referent="result",
    )


def _build_cast_them_this_turn(m: re.Match[str]) -> SentenceOutcome:
    """``You may cast them this turn.`` (Chandra, Heart of Fire [−9], after "…exile them, then
    shuffle"): the permission idiom, an empty-cost ActivatedAbility + OptionalEffect(CAST).

    "them" is not the ``referent='result'`` register: the permission is used after the [−9]
    resolved, when that register is gone. It is the cards exiled with this permanent,
    ``FAtomPred.IS_EXILED_WITH_SOURCE`` over Zone(EXILE, YOU) with QUnbounded, the shape of
    Chandra's own [+1] permission. The cards are cast for their costs: the CAST has no ``cost``
    role, since the card prints no "without paying its mana cost" waiver (CR 118.9).

    Known limits: both of Chandra's exile abilities record the same permanent as the cause, so
    both permissions read the union of her exiled cards (the grammar has no per-ability exile
    group); and CAST has no duration role, so "this turn" is dropped."""
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
            )
        ),
    )
    return AbilityOutcome(
        ability=ActivatedAbility(cost=Cost(), effect=OptionalEffect(inner=atom))
    )


def _build_look_and_play_top_of_library(m: re.Match[str]) -> SentenceOutcome:
    """``You may look at the top card of your library any time, and you may play lands from the
    top of your library.`` (Radha, Heart of Keld): two permissions in one sentence (the compiler
    splits sentences on ". " only, so one template emits both). The empty-cost ActivatedAbility's
    effect is a Seq of two OptionalEffects, LOOK_AT and a top-land CAST, so the two "may"
    decisions stay independent; Optional(Seq(a, b)) would fuse them into one. LOOK_AT has no zone
    role: it looks at the top of the library (count 1 = "the top card").
    Lossy: lands are played, not cast, but CAST is the only from-zone permission verb
    (ADD_LAND_PLAY counts extra land drops, it is not a from-zone play)."""
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
    """``You may play that card until you exile another card with this enchantment.`` (Furious
    Rise): OptionalEffect(CAST) over the result register ("that card": the card the end-step
    trigger's first sentence exiled). Lossy: no Duration means "until the next such event"
    (DurationUntilLeaves is leaves-the-battlefield only, DurationWhileCondition is a state
    predicate), so the window is dropped; and the card is played through CAST, as in the Radha
    row."""
    atom = Atom(
        verb=Verb.CAST,
        args=AtomArgs(pairs=(("source", _result_register_selector(QConst(1))),)),
    )
    return AbilityOutcome(
        ability=ActivatedAbility(cost=Cost(), effect=OptionalEffect(inner=atom))
    )


def _build_azusa_extra_land_plays(m: re.Match[str]) -> SentenceOutcome:
    """``You may play two additional lands on each of your turns.`` (Azusa, Lost but Seeking):
    ADD_LAND_PLAY with count QConst(2) (the pattern pins the word "two").

    A static ability (CR 604.1; CR 305.2: continuous effects may raise the land allowance):
    StaticAbility(OptionalEffect(ADD_LAND_PLAY)), the Teferi, Master of Time permission shape (the
    "you may" is playing the land; layers._new_static unwraps it). No duration role: the static's
    own lifetime is the window."""
    atom = Atom(
        verb=Verb.ADD_LAND_PLAY,
        args=AtomArgs(pairs=(("count", QConst(2)),)),
    )
    return AbilityOutcome(ability=StaticAbility(effect=OptionalEffect(inner=atom)))


def _build_noncombat_damage_cost_modifier(m: re.Match[str]) -> SentenceOutcome:
    """``This spell costs {X} less to cast, where X is the total amount of noncombat damage dealt to
    your opponents this turn.`` (Chandra's Incinerator): a CostModifier on the source, like
    _build_total_power_cost_modifier, whose amount is QThisTurn(NONCOMBAT_DAMAGE, ALL_OPPONENTS),
    one total across all opponents. The executor reads the referent as the players dealt the
    damage (executor/quantity.py)."""
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
    """``You may spend mana as though it were mana of any color.`` (Chromatic Orrery): MANA_POLICY
    with the scope "ALL_YOURS", covering every spend (Vodalian's "THIS_MANA" is tied to one mana
    event). No duration role: the static's own lifetime is the window. The OptionalEffect keeps
    the "may" open at each spend."""
    atom = Atom(
        verb=Verb.MANA_POLICY,
        args=AtomArgs(pairs=(("scope", "ALL_YOURS"),)),
    )
    return AbilityOutcome(ability=StaticAbility(effect=OptionalEffect(inner=atom)))


def _build_tefei_grant_activation(m: re.Match[str]) -> SentenceOutcome:
    """``You may activate loyalty abilities of Teferi on any player's turn any time you could cast
    an instant.`` (Teferi, Master of Time): GRANT_ACTIVATION with window ActivationWindow.INSTANT,
    wrapped in an OptionalEffect ("you may"). "Teferi" is the card's shortened name, which means
    this object only (CR 201.5, 201.5c), so the holder filter is IS_SOURCE, not every Teferi
    planeswalker."""
    holder = FAtom(pred=FAtomPred.IS_SOURCE)
    atom = Atom(
        verb=Verb.GRANT_ACTIVATION,
        args=AtomArgs(pairs=(("filter", holder), ("window", ActivationWindow.INSTANT))),
    )
    return AbilityOutcome(ability=StaticAbility(effect=OptionalEffect(inner=atom)))


def _build_enthralling_target_choice(m: re.Match[str]) -> SentenceOutcome:
    """``You can't choose an untapped creature as this spell's target as you cast it.``
    (Enthralling Hold): PREVENT_EFFECT over a TargetingEvent on an untapped creature; the condition
    FAtom(IS_ANY_TARGET) scopes it to this spell's own targets, as in Subira's restriction. The
    grammar has no targeting-legality node, so this cannot tell a restriction on the choice from a
    prevention of the targeting; for this card the two coincide."""
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
        # Disjoint from B4-enters-tapped-land below (one noun, one template); both build
        # EtBState(tapped=True).
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
    ),
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
