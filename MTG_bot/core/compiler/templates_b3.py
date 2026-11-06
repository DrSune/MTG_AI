"""B3 bucket templates: activated abilities with cost : effect.

Each B3 sentence has the form "<cost>: <effect>." where the cost is a
sequence of mana symbols ({T}, {W}, {2}, {2}{U}, etc.) and the effect
is one of a closed set of actions expressible in the ability_tree
grammar.
"""

from __future__ import annotations

import re

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    Atom,
    AtomArgs,
    Choose,
    ControllerRef,
    Cost,
    CostManaColor,
    CostManaGeneric,
    CostTap,
    CounterKind,
    DeclareBlockersEvent,
    DurationEot,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    OptionalEffect,
    PtDelta,
    PtDirection,
    QAgg,
    QConst,
    QCount,
    QDistinctColorCount,
    QProp,
    QPropField,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    TokenSpec,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    SentenceOutcome,
    Template,
)

# ---------------------------------------------------------------------------
# Cost regex constants
# ---------------------------------------------------------------------------

_COST_TOKEN = r"\{[0-9WUBRGT]+\}"
_COST_SEP = r"(?:\s*,\s*)?"
_COST = rf"(?P<cost>{_COST_TOKEN}({_COST_SEP}{_COST_TOKEN})*)"


def _parse_cost(m: re.Match[str]) -> Cost:
    """Parse the 'cost' group into a Cost node."""
    cost_str = m.group("cost")
    tokens = re.findall(r"\{([0-9WUBRGT]+)\}", cost_str)
    parts: list[CostTap | CostManaColor | CostManaGeneric] = []
    for tok in tokens:
        if tok == "T":
            parts.append(CostTap())
        elif tok.isdigit():
            parts.append(CostManaGeneric(QConst(int(tok))))
        else:
            for ch in tok:
                parts.append(CostManaColor(ch, QConst(1)))
    return Cost(parts=tuple(parts))


# ---------------------------------------------------------------------------
# Keyword name → enum map
# ---------------------------------------------------------------------------

_KW_MAP: dict[str, Keyword] = {
    "deathtouch": Keyword.DEATHTOUCH,
    "indestructible": Keyword.INDESTRUCTIBLE,
    "flying": Keyword.FLYING,
    "lifelink": Keyword.LIFELINK,
}

#: The ``kw`` group of the grant templates, built from the map so a pattern can never match a word
#: its builder cannot look up (the KeyError would abort a whole-set compile). A sentence granting
#: another keyword stays unparsed until that keyword joins the map with an executor test.
_KW_ALT: str = "|".join(re.escape(k) for k in sorted(_KW_MAP, key=len, reverse=True))


# ---------------------------------------------------------------------------
# Selector helpers
# ---------------------------------------------------------------------------


def _sel_self() -> Selector:
    """The source of the current ability."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.ALL,
        filter=FAnd(
            children=(
                FAtom(pred=FAtomPred.IS_SOURCE),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _sel_target_creature() -> Selector:
    """Target creature, on the battlefield: Zone(ANY, ANY) would let a spell target a creature
    card in a graveyard or library."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _sel_any_target() -> Selector:
    """Any target: a creature, planeswalker or player (CR 109.5), never a card in a hand or
    library. The card side is the battlefield with the FOr type filter; the player side joins
    through the engine's widening (query._widen_any_target and selectors._is_any_universal
    recognize this exact shape), so the filter is never evaluated on a player."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FOr(
            (
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                # Never matches a card (no card has the type "Player"): it marks the CR 109.5
                # "any target" shape, so the widening can tell it from "target creature or
                # planeswalker", which never denotes a player (CR 115.1d).
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Player"),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _sel_target_planeswalker() -> Selector:
    """Target planeswalker."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _sel_target_player_or_planeswalker() -> Selector:
    """Target player or planeswalker: PLAYER ∪ BATTLEFIELD."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FOr(
            children=(
                FNot(inner=FAtom(pred=FAtomPred.IS_PERMANENT)),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
            )
        ),
        
        zones=(Zone(kind=ZoneKind.PLAYER, controller=ControllerRef.ANY), *(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),)),
    )


def _sel_target_creature_flying() -> Selector:
    """Target creature with flying."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _sel_creatures_you_control() -> Selector:
    """All creatures you control."""
    return Selector(
        count=QUnbounded(),
        mode=SelectorMode.ALL,
        filter=FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _sel_lands_you_control() -> Selector:
    """All lands you control."""
    return Selector(
        count=QUnbounded(),
        mode=SelectorMode.ALL,
        filter=FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _sel_dogs_you_control() -> Selector:
    """All Dogs you control."""
    return Selector(
        count=QUnbounded(),
        mode=SelectorMode.ALL,
        filter=FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Dog"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _sel_target_bird_cat_dog_goat_ox_snake() -> Selector:
    """Target Bird, Cat, Dog, Goat, Ox, or Snake."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FOr(
                    children=(
                        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Bird"),
                        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Cat"),
                        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Dog"),
                        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Goat"),
                        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Ox"),
                        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Snake"),
                    )
                ),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _sel_target_creature_with_plus1() -> Selector:
    """Target creature with a +1/+1 counter on it."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(
                    pred=FAtomPred.HAS_COUNTER, counter_kind=CounterKind.PLUS_1_PLUS_1
                ),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _sel_target_card_from_graveyard() -> Selector:
    """Target card in any graveyard."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAnd(children=()),
        zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.ANY),),
    )


def _sel_cards_in_your_graveyard() -> Selector:
    """Target card from your graveyard."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAnd(children=()),
        zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),),
    )


def _sel_cards_in_your_hand() -> Selector:
    """A card you choose from your hand (for DISCARD)."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.CHOOSE,
        filter=FAnd(children=()),
        zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),),
    )


# ---------------------------------------------------------------------------
# Build helpers
# ---------------------------------------------------------------------------


def _build_activated(cost: Cost, effect: Atom | Seq | Choose) -> AbilityOutcome:
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=effect))


# ---------------------------------------------------------------------------
# Template build functions
# ---------------------------------------------------------------------------


def _build_grant_kw_self(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    kw = _KW_MAP[m.group("kw")]
    sel = _sel_self()
    effect = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", sel),
                ("ability", KeywordAbility(keyword=kw)),
                ("duration", DurationEot()),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_grant_kw_target_creature(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    kw = _KW_MAP[m.group("kw")]
    sel = _sel_target_creature()
    effect = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", sel),
                ("ability", KeywordAbility(keyword=kw)),
                ("duration", DurationEot()),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_grant_kw_all_you(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    kw = _KW_MAP[m.group("kw")]
    sel = _sel_creatures_you_control()
    effect = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", sel),
                ("ability", KeywordAbility(keyword=kw)),
                ("duration", DurationEot()),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_modify_pt_self(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    p = int(m.group("p"))
    t = int(m.group("t"))
    sel = _sel_self()
    effect = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", sel),
                ("power", PtDelta(direction=PtDirection.INCREASE, magnitude=QConst(p))),
                (
                    "toughness",
                    PtDelta(direction=PtDirection.INCREASE, magnitude=QConst(t)),
                ),
                ("duration", DurationEot()),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_modify_pt_radha(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_self()
    amount = QCount(_sel_lands_you_control())
    effect = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", sel),
                ("power", PtDelta(direction=PtDirection.INCREASE, magnitude=amount)),
                (
                    "toughness",
                    PtDelta(direction=PtDirection.INCREASE, magnitude=amount),
                ),
                ("duration", DurationEot()),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_set_pt_jolrael(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_creatures_you_control()
    x = QProp(referent="controller", field=QPropField.CARDS_IN_HAND, agg=QAgg.FIRST)
    effect = Atom(
        verb=Verb.SET_PT,
        args=AtomArgs(
            pairs=(
                ("target", sel),
                ("power", x),
                ("toughness", x),
                ("duration", DurationEot()),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_deal_dmg_const_planeswalker(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    dmg = int(m.group("dmg"))
    sel = _sel_target_planeswalker()
    effect = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", sel),
                ("amount", QConst(dmg)),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_deal_dmg_const_flying(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    dmg = int(m.group("dmg"))
    sel = _sel_target_creature_flying()
    effect = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", sel),
                ("amount", QConst(dmg)),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_deal_dmg_rin_seri(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_any_target()
    amount = QCount(_sel_dogs_you_control())
    effect = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", sel),
                ("amount", amount),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_deal_dmg_power_player_or_planeswalker(
    m: re.Match[str],
) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_target_player_or_planeswalker()
    amount = QProp(referent="source", field=QPropField.POWER, agg=QAgg.FIRST)
    effect = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", sel),
                ("amount", amount),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_deal_dmg_const_player_or_planeswalker(
    m: re.Match[str],
) -> AbilityOutcome:
    cost = _parse_cost(m)
    dmg = int(m.group("dmg"))
    sel = _sel_target_player_or_planeswalker()
    effect = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", sel),
                ("amount", QConst(dmg)),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_lose_life_each_opponent(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    life = int(m.group("life"))
    effect = Atom(
        verb=Verb.LOSE_LIFE,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.ALL_OPPONENTS),
                ("amount", QConst(life)),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_exile_target_graveyard(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_target_card_from_graveyard()
    effect = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                ("target", sel),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_move_gy_to_library_bottom(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_cards_in_your_graveyard()
    effect = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("cards", sel),
                (
                    "destination",
                    Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU),
                ),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_put_counter_subtype_list(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_target_bird_cat_dog_goat_ox_snake()
    effect = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                ("target", sel),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                ("count", QConst(1)),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_put_counter_target_creature(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_target_creature()
    effect = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                ("target", sel),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                ("count", QConst(1)),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_put_counter_creature_with_counter(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_target_creature_with_plus1()
    effect = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                ("target", sel),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                ("count", QConst(1)),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_seq_draw_discard(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    draw = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(1)),
            )
        ),
    )
    discard = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)),
                ("from", Zone(ZoneKind.HAND, ControllerRef.YOU)),
                ("controller", ControllerRef.YOU),
                ("cards", _sel_cards_in_your_hand()),
            )
        ),
    )
    effect = Seq(steps=(draw, discard))
    return _build_activated(cost, effect)


def _build_draw_per_distinct_color(m: re.Match[str]) -> AbilityOutcome:
    """``{5}, {T}: Draw a card for each color among permanents you control.`` (Chromatic
    Orrery): QDistinctColorCount counts the distinct colors among all permanents you control."""
    cost = _parse_cost(m)
    effect = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                (
                    "amount",
                    QDistinctColorCount(
                        Selector(
                            count=QUnbounded(),
                            mode=SelectorMode.ALL,
                            filter=FAnd(
                                children=(
                                    FAtom(pred=FAtomPred.IS_PERMANENT),
                                    FAtom(
                                        pred=FAtomPred.CONTROLLER_IS,
                                        who=ControllerRef.YOU,
                                    ),
                                )
                            ),
                            zones=(Zone(
                                kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY
                            ),),
                        )
                    ),
                ),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_scry_n(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    n = int(m.group("n"))
    effect = Atom(
        verb=Verb.SCRY,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("count", QConst(n)),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_tap_target_creature(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_target_creature()
    effect = Atom(
        verb=Verb.TAP,
        args=AtomArgs(pairs=(("target", sel),)),
    )
    return _build_activated(cost, effect)


def _build_add_mana_single(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    col = m.group("col")
    effect = Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(1)),
                ("color", col),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_add_mana_colorless(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    c_str = m.group("c")
    n = c_str.count("{C}")
    effect = Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(n)),
                ("color", "C"),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_add_mana_choose(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    c1 = m.group("c1")
    c2 = m.group("c2")
    opt1 = Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(1)),
                ("color", c1),
            )
        ),
    )
    opt2 = Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(1)),
                ("color", c2),
            )
        ),
    )
    effect = Choose(count=QConst(1), options=(opt1, opt2))
    return _build_activated(cost, effect)


def _build_add_mana_any(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    effect = Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(1)),
                ("color", "ANY"),  # any color, not colorless "C"
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_add_mana_g_per_power_ge_creatures_you(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    n = int(m.group("n"))
    sel = Selector(
        count=QUnbounded(),
        mode=SelectorMode.ALL,
        filter=FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.POWER_GE, count=QConst(n)),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )
    effect = Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QCount(sel)),
                ("color", "G"),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_create_token(m: re.Match[str]) -> AbilityOutcome:
    """``{cost}: Create a P/T white Angel creature token with flying.`` (Speaker of the Heavens).
    The type line is "Creature — Angel" (CR 205.1, CR 111.3): the executor mints a token's identity
    from its type line, so a bare "Angel" would not be a creature."""
    cost = _parse_cost(m)
    p = int(m.group("p"))
    t = int(m.group("t"))
    token = TokenSpec(
        name="Angel",
        type_line="Creature — Angel",
        types=("Creature",),
        subtypes=("Angel",),
        power=QConst(p),
        toughness=QConst(t),
        keywords=(Keyword.FLYING,),
        abilities=(),
        colors=("W",),
    )
    effect = Atom(
        verb=Verb.CREATE_TOKEN,
        args=AtomArgs(
            pairs=(
                ("tokens", token),
                ("count", QConst(1)),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_target_cant_be_blocked(m: re.Match[str]) -> AbilityOutcome:
    """Another target creature with power N or less can't be blocked this turn (Subira, Tulzidi
    Caravanner). PREVENT_EFFECT over a DeclareBlockersEvent whose ``blocked`` side is the
    ability's target (IS_ANY_TARGET) with power N or less, and not the source ("another")."""
    blocked = FAnd(
        children=(
            FAtom(pred=FAtomPred.IS_ANY_TARGET),
            FAtom(pred=FAtomPred.POWER_LE, count=QConst(int(m.group("pw")))),
            FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
        )
    )
    effect = Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                ("condition", FAtom(pred=FAtomPred.IS_ANY_TARGET)),
                (
                    "event",
                    DeclareBlockersEvent(FAnd(children=()), blocked=blocked),
                ),
                ("duration", DurationEot()),
            )
        ),
    )
    return _build_activated(_parse_cost(m), effect)


def _build_fight_another(m: re.Match[str]) -> SentenceOutcome:
    """``{COST}: This creature fights another target creature.`` (Brash Taunter). FIGHT's one
    ``target`` role is the other fighter; the source is implicit. "another" excludes the source:
    FNot(IS_SOURCE). The damage exchange is FIGHT's own rule, never a sentence."""
    cost = _parse_cost(m)
    effect = Atom(
        verb=Verb.FIGHT,
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
                                FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
                            )
                        ),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                    ),
                ),
            )
        ),
    )
    return _build_activated(cost, effect)


def _build_may_cast_exiled_creature(m: re.Match[str]) -> SentenceOutcome:
    """``{1}{W}, {T}: Until end of turn, you may cast a creature spell from among cards exiled with
    this artifact without paying its mana cost.`` (Idol of Endurance). The Idol's ETB exiled them
    from your graveyard, so Zone(EXILE, YOU); the empty CAST ``cost`` is the waiver. Lossy: CAST has
    no duration role, so "Until end of turn" is dropped."""
    cost = _parse_cost(m)
    effect = OptionalEffect(
        inner=Atom(
            verb=Verb.CAST,
            args=AtomArgs(
                pairs=(
                    (
                        "source",
                        Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAnd(
                                children=(
                                    FAtom(
                                        pred=FAtomPred.TYPE_EQ,
                                        string_value="Creature",
                                    ),
                                    FAtom(pred=FAtomPred.IS_EXILED_WITH_SOURCE),
                                )
                            ),
                            zones=(Zone(kind=ZoneKind.EXILE, controller=ControllerRef.YOU),),
                        ),
                    ),
                    ("cost", Cost(parts=())),
                )
            ),
        )
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=effect))


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

TEMPLATES: tuple[Template, ...] = (
    Template(
        tid="B3-grant-kw-self",
        name="grant keyword to self until eot",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*This creature gains (?P<kw>{_KW_ALT}) until end of turn\.$"
        ),
        priority=100,
        build=_build_grant_kw_self,
    ),
    Template(
        tid="B3-grant-kw-target-creature",
        name="grant keyword to target creature until eot",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Target creature gains (?P<kw>{_KW_ALT}) until end of turn\.$"
        ),
        priority=100,
        build=_build_grant_kw_target_creature,
    ),
    Template(
        tid="B3-grant-kw-all-you",
        name="grant keyword to creatures you control until eot",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Creatures you control gain (?P<kw>{_KW_ALT}) until end of turn\.$"
        ),
        priority=100,
        build=_build_grant_kw_all_you,
    ),
    Template(
        tid="B3-modify-pt-self",
        name="modify self P/T until eot",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*This creature gets \+(?P<p>\d+)/\+(?P<t>\d+) until end of turn\.$"
        ),
        priority=100,
        build=_build_modify_pt_self,
    ),
    Template(
        tid="B3-modify-pt-radha",
        name="Radha dynamic P/T from lands you control",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Radha gets \+X/\+X until end of turn, "
            rf"where X is the number of lands you control\.$"
        ),
        priority=100,
        build=_build_modify_pt_radha,
    ),
    Template(
        tid="B3-set-pt-jolrael",
        name="Jolrael dynamic P/T from hand size",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Until end of turn, creatures you control have "
            rf"base power and toughness X/X, where X is the number of cards "
            rf"in your hand\.$"
        ),
        priority=100,
        build=_build_set_pt_jolrael,
    ),
    Template(
        tid="B3-deal-dmg-const-planeswalker",
        name="deal constant damage to target planeswalker",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*This creature deals (?P<dmg>\d+) damage "
            rf"to target planeswalker\.$"
        ),
        priority=100,
        build=_build_deal_dmg_const_planeswalker,
    ),
    Template(
        tid="B3-deal-dmg-const-flying",
        name="deal constant damage to target creature with flying",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*This creature deals (?P<dmg>\d+) damage "
            rf"to target creature with flying\.$"
        ),
        priority=100,
        build=_build_deal_dmg_const_flying,
    ),
    Template(
        tid="B3-deal-dmg-rin-seri",
        name="Rin and Seri damage equal to Dogs you control",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Rin and Seri deals damage to any target "
            rf"equal to the number of Dogs you control\.$"
        ),
        priority=100,
        build=_build_deal_dmg_rin_seri,
    ),
    Template(
        tid="B3-deal-dmg-power-player-or-planeswalker",
        name="deal damage equal to power to target player or planeswalker",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*This creature deals damage equal to its power "
            rf"to target player or planeswalker\.$"
        ),
        priority=100,
        build=_build_deal_dmg_power_player_or_planeswalker,
    ),
    Template(
        tid="B3-deal-dmg-const-player-or-planeswalker",
        name="deal constant damage to target player or planeswalker",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*This creature deals (?P<dmg>\d+) damage "
            rf"to target player or planeswalker\.$"
        ),
        priority=100,
        build=_build_deal_dmg_const_player_or_planeswalker,
    ),
    Template(
        tid="B3-lose-life-each-opponent",
        name="each opponent loses constant life",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Each opponent loses (?P<life>\d+) life\.$"
        ),
        priority=100,
        build=_build_lose_life_each_opponent,
    ),
    Template(
        tid="B3-exile-target-graveyard",
        name="exile target card from a graveyard",
        bucket="B3",
        pattern=re.compile(rf"^{_COST}\s*:\s*Exile target card from a graveyard\.$"),
        priority=100,
        build=_build_exile_target_graveyard,
    ),
    Template(
        tid="B3-move-gy-to-library-bottom",
        name="put target card from your graveyard on bottom of library",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Put target card from your graveyard "
            rf"on the bottom of your library\.$"
        ),
        priority=100,
        build=_build_move_gy_to_library_bottom,
    ),
    Template(
        tid="B3-put-counter-subtype-list",
        name="put +N/+N on target Bird/Cat/Dog/Goat/Ox/Snake",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Put a \+(?P<p>\d+)/\+(?P<t>\d+) counter "
            rf"on target Bird, Cat, Dog, Goat, Ox, or Snake\.$"
        ),
        priority=100,
        build=_build_put_counter_subtype_list,
    ),
    Template(
        tid="B3-put-counter-target-creature",
        name="put +N/+N on target creature",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Put a \+(?P<p>\d+)/\+(?P<t>\d+) counter "
            rf"on target creature\.$"
        ),
        priority=100,
        build=_build_put_counter_target_creature,
    ),
    Template(
        tid="B3-put-counter-creature-with-counter",
        name="put +1/+1 on target creature with a +1/+1 counter",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Put a \+(?P<p>\d+)/\+(?P<t>\d+) counter "
            rf"on target creature with a \+(?P<cp>\d+)/\+(?P<ct>\d+) "
            rf"counter on it\.$"
        ),
        priority=100,
        build=_build_put_counter_creature_with_counter,
    ),
    Template(
        tid="B3-seq-draw-discard",
        name="draw a card then discard a card",
        bucket="B3",
        pattern=re.compile(rf"^{_COST}\s*:\s*Draw a card, then discard a card\.$"),
        priority=100,
        build=_build_seq_draw_discard,
    ),
    Template(
        tid="B3-scry-n",
        name="scry N",
        bucket="B3",
        pattern=re.compile(rf"^{_COST}\s*:\s*Scry (?P<n>\d+)\.$"),
        priority=100,
        build=_build_scry_n,
    ),
    Template(
        tid="B3-tap-target-creature",
        name="tap target creature",
        bucket="B3",
        pattern=re.compile(rf"^{_COST}\s*:\s*Tap target creature\.$"),
        priority=100,
        build=_build_tap_target_creature,
    ),
    Template(
        tid="B3-add-mana-single",
        name="add one specific color mana",
        bucket="B3",
        pattern=re.compile(rf"^{_COST}\s*:\s*Add \{{(?P<col>[WUBRG])\}}\.$"),
        priority=100,
        build=_build_add_mana_single,
    ),
    Template(
        tid="B3-add-mana-colorless",
        name="add N colorless mana",
        bucket="B3",
        pattern=re.compile(rf"^{_COST}\s*:\s*Add (?P<c>(?:\{{C\}})+)\.$"),
        priority=100,
        build=_build_add_mana_colorless,
    ),
    Template(
        tid="B3-add-mana-choose",
        name="add one of two colors",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Add \{{(?P<c1>[WUBRG])\}} or "
            rf"\{{(?P<c2>[WUBRG])\}}\.$"
        ),
        priority=100,
        build=_build_add_mana_choose,
    ),
    Template(
        tid="B3-add-mana-any",
        name="add one mana of any color",
        bucket="B3",
        pattern=re.compile(rf"^{_COST}\s*:\s*Add one mana of any color\.$"),
        priority=100,
        build=_build_add_mana_any,
    ),
    Template(
        tid="B3-add-mana-g-per-power-ge-creatures-you",
        name="add G per creature with power N or greater you control",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Add \{{G\}} for each creature with power "
            rf"(?P<n>\d+) or greater you control\.$"
        ),
        priority=100,
        build=_build_add_mana_g_per_power_ge_creatures_you,
    ),
    Template(
        tid="B3-create-token",
        name="create angel token with flying",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Create a (?P<p>\d+)/(?P<t>\d+) white "
            rf"Angel creature token with flying\.$"
        ),
        priority=100,
        build=_build_create_token,
    ),
    Template(
        tid="B3-target-cant-be-blocked",
        name="another target creature with power N or less can't be blocked this turn",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Another target creature with power "
            rf"(?P<pw>\d+) or less can't be blocked this turn\.$"
        ),
        priority=100,
        build=_build_target_cant_be_blocked,
    ),
    Template(
        tid="B3-fights-target",
        name="this creature fights another target creature",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*This creature fights another target creature\.$"
        ),
        priority=100,
        build=_build_fight_another,
    ),
    Template(
        tid="B3-idol-cast-exiled-creature",
        name="until end of turn, cast creature from cards exiled with this artifact free (IS_EXILED_WITH_SOURCE)",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Until end of turn, you may cast a creature "
            rf"spell from among cards exiled with this artifact without "
            rf"paying its mana cost\.$"
        ),
        priority=100,
        build=_build_may_cast_exiled_creature,
    ),
    Template(
        tid="B3-draw-per-distinct-color",
        name="draw a card per distinct color among permanents you control",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Draw a card for each color among permanents "
            rf"you control\.$"
        ),
        priority=100,
        build=_build_draw_per_distinct_color,
    ),
)

# ---------------------------------------------------------------------------
# UNCOVERED — shapes that cannot be expressed in the current grammar
# ---------------------------------------------------------------------------

UNCOVERED: tuple[tuple[str, str], ...] = ()
