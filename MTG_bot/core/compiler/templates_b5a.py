"""B5a bucket templates — 34 templates covering 38 of 90 B5a shapes.

Bucket input: ``/tmp/opencode/phase1_buckets/B5a.json`` (90 normalized shape
keys → ``[card, sentence]`` pairs; sentences carry *concrete* numbers, keys
carry ``N`` placeholders).  Templates fullmatch the **concrete** oracle
sentence, never the normalized key.

Coverage (90 = 38 template + 23 rule-reminder + 29 uncovered):

- **38 template-covered shapes** (34 templates; the basic-land
  ``({T}: Add {C}.)`` family is one template for five shapes):
  basic-land tap abilities, ADD_MANA, static P/T grants, counter-spell,
  token creation, keyword rule-reminder sentences (Deathtouch/Defender/
  Double strike), DESTROY, EXILE, activated discard-tap, DRAW (+QCount),
  DISCARD, LOSE_LIFE, GRANT_ABILITY/GRANT_TYPE compound statics, END_TURN,
  Equip, equipped-P/T.
- **23 rule-reminder shapes** — fully parenthesised sentences consumed by
  the compiler's ``_is_rule_reminder`` before template matching (no
  template needed; verified in tests).
- **29 uncovered shapes** — no grammar construct exists (activation gates,
  additional costs, conditional statics, name-choice, modal headers,
  counter-unless-pays, anaphora, POWER_GE, multiplicative P/T, turn
  referents, cost reduction, gain-life trigger, per-counter P/T,
  complex prevention, until-leaves exile).  Recorded in the test file.

Conventions (documented build decisions):

- ``this creature`` / ``this Equipment`` / self-referent targets are
  encoded as ``Selector(CHOOSE, QConst(1), FAtom(IS_SOURCE), zone)`` — a
  semantic self-reference, never a hardcoded card name (shape #86).
- ``enchanted creature`` is
  ``Selector(ALL, QUnbounded, FAnd(TYPE_EQ Creature, IS_ATTACHED_TO_SOURCE),
  Zone(BATTLEFIELD, ANY))``.
- ``+N/+N`` prints as ``PtDelta(INCREASE, QConst(N))`` — a printed ``+0``
  stays ``QConst(0)`` (lossless w.r.t. oracle text, shape #42).
- ``Add two mana of any one color`` → ``ADD_MANA(color="C")`` — lossy:
  the grammar cannot distinguish "any one color" from colorless (shape #34).
- Token colors (red / blue and red) are dropped: ``TokenSpec`` has no
  color field (shapes #50/#51 — grammar gap).
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
from typing import Callable

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ActivatedAbility,
    ControllerRef,
    Cost,
    CostDiscard,
    CostManaGeneric,
    CostTap,
    CounterKind,
    CreatureDiesEvent,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    PtDelta,
    PtDirection,
    QConst,
    QCount,
    QUnbounded,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    TokenSpec,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
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
    """Selector for ``this <permanent>`` — the source of the ability."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(pred=FAtomPred.IS_SOURCE),
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
    # LOSSY: "any one color" is encoded as colorless "C" (no grammar
    # construct for "choose one color at resolution" on ADD_MANA).
    atom = Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(2)),
                ("color", "C"),
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
                        Zone(kind=ZoneKind.BATTLEFIELD,
                             controller=ControllerRef.YOU),
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
                        keywords=(),  # GAP: token color (blue and red) dropped
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
                        abilities=(),  # GAP: token color (red) dropped
                    ),
                ),
                ("count", QConst(2)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_keyword_reminder(keyword: Keyword) -> Callable[[re.Match[str]], SentenceOutcome]:
    def _build(m: re.Match[str]) -> SentenceOutcome:
        return KeywordOutcome(keyword=keyword, params=())

    return _build


def _build_destroy(m: re.Match[str], f: "object", zone: Zone) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DESTROY,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1), SelectorMode.TARGET, f, zone  # type: ignore[arg-type]
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _destroy_target_filter(m: re.Match[str], extra: tuple[object, ...]) -> FAnd:
    base: list[object] = [
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
    ]
    base.extend(extra)
    return FAnd(children=tuple(base))  # type: ignore[arg-type]


def _build_exile_target(m: re.Match[str], f: "object") -> SentenceOutcome:
    atom = Atom(
        verb=Verb.EXILE,
        args=AtomArgs(
            pairs=(
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
        verb=Verb.DISCARD,
        args=AtomArgs(
            pairs=(
                ("controller", _draw_controller()),
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
                        Zone(kind=ZoneKind.BATTLEFIELD,
                             controller=ControllerRef.YOU),
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
        args=AtomArgs(
            pairs=(("target", _enchanted_creature()), ("ability", trigger))
        ),
    )
    return AbilityOutcome(
        ability=StaticAbility(effect=Seq(steps=(pt, grant)))
    )


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
        args=AtomArgs(
            pairs=(("target", _enchanted_creature()), ("types", types))
        ),
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
    return EffectOutcome(
        effect=Atom(verb=Verb.END_TURN, args=AtomArgs(pairs=()))
    )


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
                        Zone(kind=ZoneKind.BATTLEFIELD,
                             controller=ControllerRef.ANY),
                    ),
                ),
            )
        ),
    )
    return AbilityOutcome(
        ability=ActivatedAbility(
            cost=Cost(
                parts=(CostManaGeneric(amount=QConst(int(m.group(1)))),)
            ),
            effect=attach,
        )
    )


def _build_equipped_pt(m: re.Match[str]) -> SentenceOutcome:
    atom = _enchant_pt(m, (1, 2))
    return AbilityOutcome(ability=StaticAbility(effect=atom))


def _build_exile_self(m: re.Match[str]) -> SentenceOutcome:
    # "Exile Experimental Overload" — self-reference by name, encoded
    # semantically as IS_SOURCE (no hardcoded name).
    return _build_exile_target(
        m, FAtom(pred=FAtomPred.IS_SOURCE)  # type: ignore[arg-type]
    )


# +1/+1 counter kind alias
_PLUS_1_PLUS_1 = CounterKind.PLUS_1_PLUS_1


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
                            FAtom(
                                pred=FAtomPred.TYPE_EQ, string_value="Creature"
                            ),
                            FAtom(
                                pred=FAtomPred.CMC_LE,
                                count=QConst(int(m.group(1))),
                            ),
                        )
                    ),
                    FAnd(
                        children=(
                            FAtom(
                                pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"
                            ),
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
                                Zone(kind=ZoneKind.HAND,
                                     controller=ControllerRef.YOU),
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
                                    Zone(kind=ZoneKind.BATTLEFIELD,
                                         controller=ControllerRef.ANY)
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
            r'^Enchanted creature gets \+(\d+)/\+(\d+) and has '
            r'"When this creature dies, draw a card\."$'
        ),
        priority=_PRIORITY,
        build=_build_enchant_pt_death_draw,
    ),
    Template(
        tid="B5a-enchant-pt-flying",
        name="enchanted creature gets +N/+N and has flying",
        bucket=_BUCKET,
        pattern=re.compile(r"^Enchanted creature gets \+(\d+)/\+(\d+) and has flying\.$"),
        priority=_PRIORITY,
        build=_build_enchant_pt_flying,
    ),
    Template(
        tid="B5a-enchant-pt-trample",
        name="enchanted creature gets +N/+N and has trample",
        bucket=_BUCKET,
        pattern=re.compile(r"^Enchanted creature gets \+(\d+)/\+(\d+) and has trample\.$"),
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
        name="equip {N} activated ability",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Equip \{(\d+)\} \(\{\1\}: Attach to target creature you "
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
            m, FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")  # type: ignore[arg-type]
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
)
