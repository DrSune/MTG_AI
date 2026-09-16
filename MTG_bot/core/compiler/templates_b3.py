"""B3 bucket templates: activated abilities with cost : effect.

Each B3 sentence has the form "<cost>: <effect>." where the cost is a
sequence of mana symbols ({T}, {W}, {2}, {2}{U}, etc.) and the effect
is one of a closed set of actions expressible in the ability_tree
grammar.

Public API:
    TEMPLATES: tuple[Template, ...]
    UNCOVERED: tuple[tuple[str, str], ...]
"""

from __future__ import annotations

import re

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    Atom,
    AtomArgs,
    Choose,
    ControllerRef,
    CounterKind,
    Cost,
    CostManaColor,
    CostManaGeneric,
    CostTap,
    DurationEot,
    FAnd,
    FAtom,
    FAtomPred,
    FOr,
    Keyword,
    KeywordAbility,
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
    TokenSpec,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.templates import AbilityOutcome, Template

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


# ---------------------------------------------------------------------------
# Selector helpers
# ---------------------------------------------------------------------------


def _sel_self() -> Selector:
    """The source of the current ability."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.ALL,
        filter=FAtom(pred=FAtomPred.IS_SOURCE),
        zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
    )


def _sel_target_creature() -> Selector:
    """Any target creature."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        zone=Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
    )


def _sel_any_target() -> Selector:
    """Any target (card, player, planeswalker, etc.)."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAnd(children=()),
        zone=Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
    )


def _sel_target_planeswalker() -> Selector:
    """Target planeswalker."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
        zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _sel_target_creature_flying() -> Selector:
    """Target creature with flying."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAnd(children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING),
        )),
        zone=Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
    )


def _sel_creatures_you_control() -> Selector:
    """All creatures you control."""
    return Selector(
        count=QUnbounded(),
        mode=SelectorMode.ALL,
        filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
    )


def _sel_lands_you_control() -> Selector:
    """All lands you control."""
    return Selector(
        count=QUnbounded(),
        mode=SelectorMode.ALL,
        filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land"),
        zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
    )


def _sel_dogs_you_control() -> Selector:
    """All Dogs you control."""
    return Selector(
        count=QUnbounded(),
        mode=SelectorMode.ALL,
        filter=FAnd(children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Dog"),
        )),
        zone=Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
    )


def _sel_target_bird_cat_dog_goat_ox_snake() -> Selector:
    """Target Bird, Cat, Dog, Goat, Ox, or Snake."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAnd(children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FOr(children=(
                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Bird"),
                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Cat"),
                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Dog"),
                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Goat"),
                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Ox"),
                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Snake"),
            )),
        )),
        zone=Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
    )


def _sel_target_creature_with_plus1() -> Selector:
    """Target creature with a +1/+1 counter on it."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAnd(children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FAtom(pred=FAtomPred.HAS_COUNTER, counter_kind=CounterKind.PLUS_1_PLUS_1),
        )),
        zone=Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
    )


def _sel_target_card_from_graveyard() -> Selector:
    """Target card in any graveyard."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAnd(children=()),
        zone=Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.ANY),
    )


def _sel_cards_in_your_graveyard() -> Selector:
    """Target card from your graveyard."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.TARGET,
        filter=FAnd(children=()),
        zone=Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
    )


def _sel_cards_in_your_hand() -> Selector:
    """A card you choose from your hand (for DISCARD)."""
    return Selector(
        count=QConst(1),
        mode=SelectorMode.CHOOSE,
        filter=FAnd(children=()),
        zone=Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
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
        args=AtomArgs(pairs=(
            ("target", sel),
            ("ability", KeywordAbility(keyword=kw)),
            ("duration", DurationEot()),
        )),
    )
    return _build_activated(cost, effect)


def _build_grant_kw_target_creature(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    kw = _KW_MAP[m.group("kw")]
    sel = _sel_target_creature()
    effect = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(pairs=(
            ("target", sel),
            ("ability", KeywordAbility(keyword=kw)),
            ("duration", DurationEot()),
        )),
    )
    return _build_activated(cost, effect)


def _build_grant_kw_all_you(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    kw = _KW_MAP[m.group("kw")]
    sel = _sel_creatures_you_control()
    effect = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(pairs=(
            ("target", sel),
            ("ability", KeywordAbility(keyword=kw)),
            ("duration", DurationEot()),
        )),
    )
    return _build_activated(cost, effect)


def _build_modify_pt_self(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    p = int(m.group("p"))
    t = int(m.group("t"))
    sel = _sel_self()
    effect = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(pairs=(
            ("target", sel),
            ("power", PtDelta(direction=PtDirection.INCREASE, magnitude=QConst(p))),
            ("toughness", PtDelta(direction=PtDirection.INCREASE, magnitude=QConst(t))),
            ("duration", DurationEot()),
        )),
    )
    return _build_activated(cost, effect)


def _build_modify_pt_radha(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_self()
    amount = QCount(_sel_lands_you_control())
    effect = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(pairs=(
            ("target", sel),
            ("power", PtDelta(direction=PtDirection.INCREASE, magnitude=amount)),
            ("toughness", PtDelta(direction=PtDirection.INCREASE, magnitude=amount)),
            ("duration", DurationEot()),
        )),
    )
    return _build_activated(cost, effect)


def _build_set_pt_jolrael(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_creatures_you_control()
    x = QProp(referent="controller", field=QPropField.CARDS_IN_HAND, agg=QAgg.FIRST)
    effect = Atom(
        verb=Verb.SET_PT,
        args=AtomArgs(pairs=(
            ("target", sel),
            ("power", x),
            ("toughness", x),
            ("duration", DurationEot()),
        )),
    )
    return _build_activated(cost, effect)


def _build_deal_dmg_const_planeswalker(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    dmg = int(m.group("dmg"))
    sel = _sel_target_planeswalker()
    effect = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(pairs=(
            ("target", sel),
            ("amount", QConst(dmg)),
        )),
    )
    return _build_activated(cost, effect)


def _build_deal_dmg_const_flying(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    dmg = int(m.group("dmg"))
    sel = _sel_target_creature_flying()
    effect = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(pairs=(
            ("target", sel),
            ("amount", QConst(dmg)),
        )),
    )
    return _build_activated(cost, effect)


def _build_deal_dmg_rin_seri(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_any_target()
    amount = QCount(_sel_dogs_you_control())
    effect = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(pairs=(
            ("target", sel),
            ("amount", amount),
        )),
    )
    return _build_activated(cost, effect)


def _build_lose_life_each_opponent(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    life = int(m.group("life"))
    effect = Atom(
        verb=Verb.LOSE_LIFE,
        args=AtomArgs(pairs=(
            ("controller", ControllerRef.ALL_OPPONENTS),
            ("amount", QConst(life)),
        )),
    )
    return _build_activated(cost, effect)


def _build_exile_target_graveyard(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_target_card_from_graveyard()
    effect = Atom(
        verb=Verb.EXILE,
        args=AtomArgs(pairs=(
            ("target", sel),
        )),
    )
    return _build_activated(cost, effect)


def _build_move_gy_to_library_bottom(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_cards_in_your_graveyard()
    effect = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(pairs=(
            ("cards", sel),
            ("destination", Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU)),
        )),
    )
    return _build_activated(cost, effect)


def _build_put_counter_subtype_list(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_target_bird_cat_dog_goat_ox_snake()
    effect = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(pairs=(
            ("target", sel),
            ("counter_kind", CounterKind.PLUS_1_PLUS_1),
            ("count", QConst(1)),
        )),
    )
    return _build_activated(cost, effect)


def _build_put_counter_target_creature(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_target_creature()
    effect = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(pairs=(
            ("target", sel),
            ("counter_kind", CounterKind.PLUS_1_PLUS_1),
            ("count", QConst(1)),
        )),
    )
    return _build_activated(cost, effect)


def _build_put_counter_creature_with_counter(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_target_creature_with_plus1()
    effect = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(pairs=(
            ("target", sel),
            ("counter_kind", CounterKind.PLUS_1_PLUS_1),
            ("count", QConst(1)),
        )),
    )
    return _build_activated(cost, effect)


def _build_seq_draw_discard(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    draw = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(pairs=(
            ("controller", ControllerRef.YOU),
            ("amount", QConst(1)),
        )),
    )
    discard = Atom(
        verb=Verb.DISCARD,
        args=AtomArgs(pairs=(
            ("controller", ControllerRef.YOU),
            ("cards", _sel_cards_in_your_hand()),
        )),
    )
    effect = Seq(steps=(draw, discard))
    return _build_activated(cost, effect)


def _build_scry_n(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    n = int(m.group("n"))
    effect = Atom(
        verb=Verb.SCRY,
        args=AtomArgs(pairs=(
            ("controller", ControllerRef.YOU),
            ("count", QConst(n)),
        )),
    )
    return _build_activated(cost, effect)


def _build_tap_target_creature(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    sel = _sel_target_creature()
    effect = Atom(
        verb=Verb.TAP,
        args=AtomArgs(pairs=(
            ("target", sel),
        )),
    )
    return _build_activated(cost, effect)


def _build_add_mana_single(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    col = m.group("col")
    effect = Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(pairs=(
            ("controller", ControllerRef.YOU),
            ("amount", QConst(1)),
            ("color", col),
        )),
    )
    return _build_activated(cost, effect)


def _build_add_mana_colorless(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    c_str = m.group("c")
    n = c_str.count("{C}")
    effect = Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(pairs=(
            ("controller", ControllerRef.YOU),
            ("amount", QConst(n)),
            ("color", "C"),
        )),
    )
    return _build_activated(cost, effect)


def _build_add_mana_choose(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    c1 = m.group("c1")
    c2 = m.group("c2")
    opt1 = Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(pairs=(
            ("controller", ControllerRef.YOU),
            ("amount", QConst(1)),
            ("color", c1),
        )),
    )
    opt2 = Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(pairs=(
            ("controller", ControllerRef.YOU),
            ("amount", QConst(1)),
            ("color", c2),
        )),
    )
    effect = Choose(count=QConst(1), options=(opt1, opt2))
    return _build_activated(cost, effect)


def _build_add_mana_any(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    effect = Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(pairs=(
            ("controller", ControllerRef.YOU),
            ("amount", QConst(1)),
            ("color", "C"),
        )),
    )
    return _build_activated(cost, effect)


def _build_create_token(m: re.Match[str]) -> AbilityOutcome:
    cost = _parse_cost(m)
    p = int(m.group("p"))
    t = int(m.group("t"))
    token = TokenSpec(
        name="Angel",
        type_line="Angel",
        types=("Creature",),
        subtypes=("Angel",),
        power=QConst(p),
        toughness=QConst(t),
        keywords=(Keyword.FLYING,),
        abilities=(),
    )
    effect = Atom(
        verb=Verb.CREATE_TOKEN,
        args=AtomArgs(pairs=(
            ("tokens", token),
            ("count", QConst(1)),
        )),
    )
    return _build_activated(cost, effect)


# ---------------------------------------------------------------------------
# Template definitions
# ---------------------------------------------------------------------------

TEMPLATES: tuple[Template, ...] = (
    Template(
        tid="B3-grant-kw-self",
        name="grant keyword to self until eot",
        bucket="B3",
        pattern=re.compile(rf"^{_COST}\s*:\s*This creature gains (?P<kw>[a-z]+) until end of turn\.$"),
        priority=100,
        build=_build_grant_kw_self,
    ),
    Template(
        tid="B3-grant-kw-target-creature",
        name="grant keyword to target creature until eot",
        bucket="B3",
        pattern=re.compile(rf"^{_COST}\s*:\s*Target creature gains (?P<kw>[a-z]+) until end of turn\.$"),
        priority=100,
        build=_build_grant_kw_target_creature,
    ),
    Template(
        tid="B3-grant-kw-all-you",
        name="grant keyword to creatures you control until eot",
        bucket="B3",
        pattern=re.compile(rf"^{_COST}\s*:\s*Creatures you control gain (?P<kw>[a-z]+) until end of turn\.$"),
        priority=100,
        build=_build_grant_kw_all_you,
    ),
    Template(
        tid="B3-modify-pt-self",
        name="modify self P/T until eot",
        bucket="B3",
        pattern=re.compile(rf"^{_COST}\s*:\s*This creature gets \+(?P<p>\d+)/\+(?P<t>\d+) until end of turn\.$"),
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
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Exile target card from a graveyard\.$"
        ),
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
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Draw a card, then discard a card\.$"
        ),
        priority=100,
        build=_build_seq_draw_discard,
    ),
    Template(
        tid="B3-scry-n",
        name="scry N",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Scry (?P<n>\d+)\.$"
        ),
        priority=100,
        build=_build_scry_n,
    ),
    Template(
        tid="B3-tap-target-creature",
        name="tap target creature",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Tap target creature\.$"
        ),
        priority=100,
        build=_build_tap_target_creature,
    ),
    Template(
        tid="B3-add-mana-single",
        name="add one specific color mana",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Add \{{(?P<col>[WUBRG])\}}\.$"
        ),
        priority=100,
        build=_build_add_mana_single,
    ),
    Template(
        tid="B3-add-mana-colorless",
        name="add N colorless mana",
        bucket="B3",
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Add (?P<c>(?:\{{C\}})+)\.$"
        ),
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
        pattern=re.compile(
            rf"^{_COST}\s*:\s*Add one mana of any color\.$"
        ),
        priority=100,
        build=_build_add_mana_any,
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
)


# ---------------------------------------------------------------------------
# UNCOVERED — shapes that cannot be expressed in the current grammar
# ---------------------------------------------------------------------------

UNCOVERED: tuple[tuple[str, str], ...] = (
    (
        "{N}, {T}: Draw a card for each color among permanents you control.",
        "No quantity expression for distinct color count among permanents; "
        "QCount counts objects, not color identities.",
    ),
    (
        "{N}: Another target creature with power N or less can't be blocked this turn.",
        "No power-only threshold predicate; PT_LE/PT_GE compare combined P/T, "
        "not power alone.",
    ),
    (
        "{N}{R}, {T}: This creature fights another target creature.",
        "No FIGHT verb; FIGHT exists only as a Keyword, not as an "
        "activatable effect verb.",
    ),
    (
        "{N}{R}: This creature deals damage equal to its power to target player or planeswalker.",
        "No player-or-planeswalker zone union; Zone is a single ZoneKind, "
        "and players are non-card PLAYER zone objects.",
    ),
    (
        "{N}{W}, {T}: Until end of turn, you may cast a creature spell from among cards exiled with this artifact without paying its mana cost.",
        "No CAST verb / may-cast-from-exile expression in the current "
        "effect grammar.",
    ),
    (
        "{T}: Add {G} for each creature with power N or greater you control.",
        "No power-only threshold predicate for a per-creature mana condition.",
    ),
    (
        "{T}: This creature deals N damage to target player or planeswalker.",
        "No player-or-planeswalker zone union; Zone is a single ZoneKind.",
    ),
)
