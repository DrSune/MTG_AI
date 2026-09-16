"""B4 bucket templates — 18 templates covering 18 of 47 B4 shapes.

Bucket input: ``/tmp/opencode/phase1_buckets/B4.json`` (47 normalized shape
keys → ``[card, sentence]`` pairs; sentences carry *concrete* numbers, keys
carry ``N`` placeholders).  Templates fullmatch the **concrete** oracle
sentence, never the normalized key.

Coverage (47 = 18 template + 29 uncovered):

- **18 template-covered shapes**: static P/T grants (self, creatures you
  control, other creatures, opponents' creatures), static keyword grants
  (trample, lifelink, protection), PREVENT_EFFECT (can't block),
  MANDATE_ATTACK, GAIN_CONTROL, DRAW+DISCARD Seq, GAIN_LIFE (QConst and
  QCount), LOSE_LIFE, QProp P/T (Carrion Grub), conditional statics
  (DurationWhileCondition), compound statics (P/T + protection Seq).
- **29 uncovered shapes**: no grammar construct exists (MODIFY_COST,
  ETB tapped, ETB counters, blocking restriction, must-be-blocked,
  turn-scoped repeated statics, targeting restriction, name-choice,
  You may activated abilities, alternate casting, tutor, mana ability).
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
from typing import Callable

from MTG_bot.core.ability_tree import (
    Atom,
    AtomArgs,
    ControllerRef,
    CounterKind,
    DeclareBlockersEvent,
    DurationEot,
    DurationWhileCondition,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
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
    StaticAbility,
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
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Garruk"),
                                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
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
        pattern=re.compile(
            r"^Other Dogs you control get \+(?P<p>\d+)/\+(?P<t>\d+)\.$"
        ),
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
)

UNCOVERED: tuple[tuple[str, str], ...] = (
    ("Creature spells with flying you cast cost {N} less to cast.", "No MODIFY_COST verb in grammar"),
    ("Spells your opponents cast that target this creature cost an additional N life to cast.", "No MODIFY_COST verb in grammar"),
    ("Spells your opponents cast that target this creature cost {N} more to cast.", "No MODIFY_COST verb in grammar"),
    ("This spell costs {N} less to cast if you've gained N or more life this turn.", "No MODIFY_COST verb in grammar"),
    ("This spell costs {N}{U} less to cast if you've cast an instant or sorcery spell this turn.", "No MODIFY_COST verb in grammar"),
    ("This spell costs {X} less to cast, where X is the total amount of noncombat damage dealt to your opponents this turn.", "No MODIFY_COST verb in grammar"),
    ("This spell costs {X} less to cast, where X is the total power of creatures you control.", "No MODIFY_COST verb in grammar"),
    ("This creature enters tapped.", "No TAP_ON_ETB verb in grammar"),
    ("This creature enters with X +N/+N counters on it.", "No ETB counter-placement construct"),
    ("This land enters tapped.", "No TAP_ON_ETB verb in grammar"),
    ("This creature can block only creatures with flying.", "No blocking-restriction grammar construct"),
    ("This creature can't be blocked as long as you've drawn two or more cards this turn.", "No conditional PREVENT_EFFECT with turn-scoped condition"),
    ("This creature must be blocked if able.", "No MUST_BE_BLOCKED grammar construct"),
    ("This creature gets +N/+N until end of turn for each creature tapped this way.", "No per-event repeated static with turn-scoped trigger"),
    ("You can't choose an untapped creature as this spell's target as you cast it.", "No targeting-restriction grammar construct"),
    ("You choose a noncreature, nonland card from it.", "No anaphora / name-choice grammar construct"),
    ("You have protection from the chosen card name.", "No dynamic protection-from-name grammar construct"),
    ("You may activate loyalty abilities of Teferi on any player's turn any time you could cast an instant.", "No cross-card activated ability activation grammar"),
    ("You may cast Goblin spells from the top of your library.", "No alternate-casting / cast-from-zone grammar construct"),
    ("You may cast them this turn.", "No anaphora / cast-them-this-turn grammar construct"),
    ("You may cast this card from your graveyard by paying N life and discarding a card in addition to paying its other costs.", "No alternate-casting with additional cost grammar"),
    ("You may choose new targets for the copy.", "No copy-targeting grammar construct"),
    ("You may look at the top card of your library any time, and you may play lands from the top of your library.", "No complex multi-ability You may construct"),
    ("You may play that card until you exile another card with this enchantment.", "No anaphora / conditional play grammar"),
    ("You may play two additional lands on each of your turns.", "No land-speed-modification grammar construct"),
    ("You may reveal a creature card or Garruk planeswalker card from among them and put it into your hand.", "No complex tutor / reveal-and-put grammar"),
    ("You may search your library and/or graveyard for a card named Basri, Devoted Paladin, reveal it, and put it into your hand.", "No name-specific tutor grammar construct"),
    ("You may search your library and/or graveyard for a card named Liliana, Death Mage, reveal it, and put it into your hand.", "No name-specific tutor grammar construct"),
    ("You may spend mana as though it were mana of any color.", "No mana-color-flooding grammar construct"),
)
