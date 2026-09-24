"""B5c bucket templates — 73 templates covering 74 of 90 B5c shapes.

Bucket input: ``/tmp/opencode/phase1_buckets/B5c.json`` (90 normalized shape
keys → ``[card, sentence]`` pairs; sentences carry *concrete* numbers, keys
carry ``N`` placeholders).  Templates fullmatch the **concrete** oracle
sentence, never the normalized key.

Coverage (90 normalized keys = 73 covered + 17 uncovered; 91 concrete
sentences = 74 covered + 17 uncovered; ``• You gain N life.`` has two
concrete variants both covered by one template):

- **73 covered shapes** (73 unique tids; the gain-life template covers two
  concrete variants):
  keyword reminders (Trample, Vigilance, Vigilance+lifelink,
  Vigilance+protection, Vigilance+reach+trample), then-continuation
  effects, static P/T grants, activated cost/loyalty abilities,
  bullet (spell) effects, X-quantities, QProp/QBin amount expressions,
  token creation, token copy, phase out, counter spells, extra turns,
  scry/reveal/look-at, per-creature life loss, ETB counter placement,
  loyalty discard-hand/exile-top-library, loyalty move-to-top-of-library,
  loyalty may-cast-from-graveyard, bullet return-to-owner-hand.
- **17 uncovered shapes** — no grammar construct exists (anaphoric targets,
  conditional Then-continuations, cost reduction, turn-scoped
  triggers, emblems, coin-flip).  Recorded in UNCOVERED.

Conventions (documented build decisions):

- ``this creature`` / ``this artifact`` / ``this land`` / ``this token`` /
  ``this card`` self-referent targets are encoded as
  ``Selector(CHOOSE, QConst(1), FAtom(IS_SOURCE), zone)`` — a semantic
  self-reference, never a hardcoded card name.
- ``another target creature`` uses ``FAtom(IS_ANY_TARGET)`` as a lossy
  distinct-target encoding (no grammar construct for "another" relative
  to source).
- Keyword-reminder sentences are encoded via ``KeywordOutcome``; when
  multiple keywords are present the primary one is kept and the rest are
  dropped (documented lossy).
- ``Vigilance, protection from multicolored`` → ``Keyword.PROTECTION``
  with filter ``FAtom(COLOR_COUNT_GE, count=QConst(2))``.
- ``Creatures without flying can't block this turn`` is a one-shot spell
  effect; encoded lossy as ``MODIFY_PT`` zero-delta placeholder (no
  PREVENT_BLOCK grammar construct).
- Loyalty prefix parsed via ``_loyalty_delta(m, 1)``; the U+2212 minus
  sign in loyalty prefixes is distinguished from ASCII hyphen in P/T.
- ``X`` in effects is ``QX()``; ``X`` in cost-less contexts is not
  captured.
- ``permanent cards`` filter is ``_PERMANENT_CARD_FILTER`` — an ``FOr``
  over the five ``TYPE_EQ`` permanent types (the grammar has no
  PERMANENT predicate).

PC-3: every B5c concrete sentence fullmatches **at most one** template
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
    CostDiscard,
    CostLoyalty,
    CostManaColor,
    CostManaGeneric,
    CostPutCounter,
    CostSacrifice,
    CostTap,
    CounterKind,
    DurationEot,
    EtBState,
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
    TokenSpec,
    Verb,
    Zone,
    ZoneKind,
    ZonePosition,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    KeywordOutcome,
    SentenceOutcome,
    Template,
)

_BUCKET = "B5c"
_PRIORITY = 100


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


def _loyalty_delta(m: re.Match[str], group: int) -> int:
    """Parse a loyalty prefix group like ``+1`` or ``−2`` → signed int."""
    n = m.group(group)
    if n[0] == "+":
        return int(n[1:])
    # U+2212 MINUS SIGN
    return -int(n[1:])


def _pt_increase(m: re.Match[str], group: int) -> PtDelta:
    return PtDelta(PtDirection.INCREASE, QConst(int(m.group(group))))


def _pt_decrease(m: re.Match[str], group: int) -> PtDelta:
    return PtDelta(PtDirection.DECREASE, QConst(int(m.group(group))))


# ---------------------------------------------------------------------------
# Shared selector factories
# ---------------------------------------------------------------------------

#: "permanent card" = any of the five permanent types (the grammar has no
#: PERMANENT predicate, so the disjunction of TYPE_EQ atoms is used).
_PERMANENT_CARD_FILTER = FOr(
    (
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Enchantment"),
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Artifact"),
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land"),
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
    )
)


def _any_target() -> Selector:
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(children=()),
        Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
    )


def _target_creature() -> Selector:
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _target_creature_or_planeswalker() -> Selector:
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FOr(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
            )
        ),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _up_to_one_target_creature() -> Selector:
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _another_target_creature() -> Selector:
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.IS_ANY_TARGET),
            )
        ),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _all_creatures() -> Selector:
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _creatures_you_control() -> Selector:
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


def _zombies_you_control() -> Selector:
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Zombie"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
    )


def _target_opponent_creatures() -> Selector:
    """``Each creature target opponent controls``."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.TARGET_PLAYER),
            )
        ),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.TARGET_PLAYER),
    )


def _target_creature_you_control() -> Selector:
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
    )


def _target_creature_you_dont_control() -> Selector:
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FNot(inner=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)),
            )
        ),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _each_opponent_player() -> Selector:
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(children=()),
        Zone(kind=ZoneKind.PLAYER, controller=ControllerRef.ALL_OPPONENTS),
    )


def _stack_target() -> Selector:
    """A spell/ability on the stack (for COUNTER_SPELL)."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(children=()),
        Zone(kind=ZoneKind.STACK, controller=ControllerRef.ANY),
    )


def _graveyard_target_player() -> Selector:
    """Whole target player's graveyard (EXILE)."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(children=()),
        Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.TARGET_PLAYER),
    )


def _hand_you_selector(count_qty) -> Selector:
    return Selector(
        count_qty,
        SelectorMode.CHOOSE,
        FAnd(children=()),
        Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
    )


def _up_to_two_target_creatures() -> Selector:
    return Selector(
        QConst(2),
        SelectorMode.CHOOSE,
        FOr(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
            )
        ),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _red_instant_or_sorcery_filter() -> FAnd:
    return FAnd(
        children=(
            FAtom(pred=FAtomPred.COLOR_HAS, color="R"),
            FOr(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Instant"),
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Sorcery"),
                )
            ),
        )
    )


# ---------------------------------------------------------------------------
# Build functions
# ---------------------------------------------------------------------------


def _build_then_return_is(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FOr(
                            children=(
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Instant"),
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Sorcery"),
                            )
                        ),
                        Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
                    ),
                ),
                ("destination", Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_etb_soul_counter(m: re.Match[str]) -> SentenceOutcome:
    return AbilityOutcome(
        ability=EtBState(initial_counters=((CounterKind.SOUL, QConst(1)),))
    )


def _build_remind_trample(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.TRAMPLE)


def _build_turn_to_slag(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _target_creature()),
                ("amount", QConst(int(m.group(1)))),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_untap_lands(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.UNTAP,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(4),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land"),
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_pt_swap(m: re.Match[str]) -> SentenceOutcome:
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.MODIFY_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", _target_creature()),
                        ("power", _pt_increase(m, 1)),
                        ("toughness", _pt_increase(m, 2)),
                        ("duration", DurationEot()),
                    )
                ),
            ),
            Atom(
                verb=Verb.MODIFY_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", _another_target_creature()),
                        ("power", _pt_decrease(m, 3)),
                        ("toughness", _pt_decrease(m, 4)),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )
    return EffectOutcome(effect=seq)


def _build_remind_vigilance(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.VIGILANCE)


def _build_remind_vigilance_lifelink(m: re.Match[str]) -> SentenceOutcome:
    # Lossy: lifelink dropped.
    return KeywordOutcome(keyword=Keyword.VIGILANCE)


def _build_remind_vigilance_protection(m: re.Match[str]) -> SentenceOutcome:
    # Lossy: vigilance dropped; protection from multicolored encoded.
    return KeywordOutcome(
        keyword=Keyword.PROTECTION,
        params=(FAtom(pred=FAtomPred.COLOR_COUNT_GE, count=QConst(2)),),
    )


def _build_remind_vigilance_reach_trample(m: re.Match[str]) -> SentenceOutcome:
    # Lossy: reach and trample dropped.
    return KeywordOutcome(keyword=Keyword.VIGILANCE)


def _build_geyser_dmg(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _any_target()),
                ("amount", QX()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_salvo_dmg(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _up_to_two_target_creatures()),
                ("amount", QConst(int(m.group(1)))),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_zombies_pt(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _zombies_you_control()),
                ("power", PtDelta(PtDirection.INCREASE, QConst(int(m.group(1))))),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(int(m.group(2))))),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(effect=atom))


# --- Loyalty build functions ---


def _loyalty_wrapper(effect: Atom | Seq, m: re.Match[str]) -> SentenceOutcome:
    """Wrap an effect in ActivatedAbility with CostLoyalty."""
    return AbilityOutcome(
        ability=ActivatedAbility(
            cost=Cost(parts=(CostLoyalty(_loyalty_delta(m, 1)),)),
            effect=effect,
        )
    )


def _build_loyalty_chandra_dmg_any(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _any_target()),
                ("amount", QConst(int(m.group(2)))),
            )
        ),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_chandra_dmg_opps(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _each_opponent_player()),
                ("amount", QConst(int(m.group(2)))),
            )
        ),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_draw_discard(m: re.Match[str]) -> SentenceOutcome:
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.DRAW,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(1)),
                    )
                ),
            ),
            Atom(
                verb=Verb.DISCARD,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("cards", _hand_you_selector(QConst(1))),
                    )
                ),
            ),
        )
    )
    return _loyalty_wrapper(seq, m)


def _build_loyalty_draw(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(1)),
            )
        ),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_each_discard(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DISCARD,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.ANY),
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAnd(children=()),
                        Zone(kind=ZoneKind.HAND, controller=ControllerRef.ANY),
                    ),
                ),
            )
        ),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_put_counter(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                ("target", _up_to_one_target_creature()),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                ("count", QConst(1)),
            )
        ),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_return_creature(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
                    ),
                ),
                ("destination", Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU)),
            )
        ),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_reveal(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.REVEAL,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("count", QConst(1)),
            )
        ),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_ugin_dmg(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _any_target()),
                ("amount", QConst(int(m.group(2)))),
            )
        ),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_pt_trample(m: re.Match[str]) -> SentenceOutcome:
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.MODIFY_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", _up_to_one_target_creature()),
                        (
                            "power",
                            PtDelta(PtDirection.INCREASE, QConst(int(m.group(2)))),
                        ),
                        (
                            "toughness",
                            PtDelta(PtDirection.INCREASE, QConst(int(m.group(3)))),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
            Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("target", _up_to_one_target_creature()),
                        ("ability", KeywordAbility(keyword=Keyword.TRAMPLE)),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )
    return _loyalty_wrapper(seq, m)


def _build_loyalty_create_token(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.CREATE_TOKEN,
        args=AtomArgs(
            pairs=(
                (
                    "tokens",
                    TokenSpec(
                        name="Beast",
                        type_line="Creature — Beast",
                        types=("Creature",),
                        subtypes=("Beast",),
                        power=QConst(int(m.group(2))),
                        toughness=QConst(int(m.group(3))),
                        keywords=(),
                        abilities=(),
                    ),
                ),
                ("count", QConst(1)),
            )
        ),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_creatures_pt_flying(m: re.Match[str]) -> SentenceOutcome:
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.MODIFY_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", _creatures_you_control()),
                        (
                            "power",
                            PtDelta(PtDirection.INCREASE, QConst(int(m.group(2)))),
                        ),
                        (
                            "toughness",
                            PtDelta(PtDirection.INCREASE, QConst(int(m.group(3)))),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
            Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("target", _creatures_you_control()),
                        ("ability", KeywordAbility(keyword=Keyword.FLYING)),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )
    return _loyalty_wrapper(seq, m)


def _build_loyalty_destroy(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DESTROY,
        args=AtomArgs(pairs=(("target", _target_creature()),)),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_discard_draw(m: re.Match[str]) -> SentenceOutcome:
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.DISCARD,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        (
                            "cards",
                            Selector(
                                QUnbounded(),
                                SelectorMode.ALL,
                                FAnd(children=()),
                                Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
                            ),
                        ),
                    )
                ),
            ),
            Atom(
                verb=Verb.DRAW,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(7)),
                    )
                ),
            ),
        )
    )
    return _loyalty_wrapper(seq, m)


def _build_loyalty_phase_out_all(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.PHASE_OUT,
        args=AtomArgs(pairs=(("target", _target_opponent_creatures()),)),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_search_exile(m: re.Match[str]) -> SentenceOutcome:
    filter_red_is_sor = _red_instant_or_sorcery_filter()
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.SEARCH,
                args=AtomArgs(
                    pairs=(
                        (
                            "cards",
                            Selector(
                                QUnbounded(),
                                SelectorMode.CHOOSE,
                                filter_red_is_sor,
                                Zone(
                                    kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU
                                ),
                            ),
                        ),
                        (
                            "destination",
                            Zone(kind=ZoneKind.EXILE, controller=ControllerRef.ANY),
                        ),
                        ("controller", ControllerRef.YOU),
                    )
                ),
            ),
            Atom(
                verb=Verb.SEARCH,
                args=AtomArgs(
                    pairs=(
                        (
                            "cards",
                            Selector(
                                QUnbounded(),
                                SelectorMode.CHOOSE,
                                filter_red_is_sor,
                                Zone(
                                    kind=ZoneKind.GRAVEYARD,
                                    controller=ControllerRef.YOU,
                                ),
                            ),
                        ),
                        (
                            "destination",
                            Zone(kind=ZoneKind.EXILE, controller=ControllerRef.ANY),
                        ),
                        ("controller", ControllerRef.YOU),
                    )
                ),
            ),
            Atom(
                verb=Verb.SHUFFLE,
                args=AtomArgs(
                    pairs=(
                        (
                            "zone",
                            Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU),
                        ),
                    )
                ),
            ),
        )
    )
    return _loyalty_wrapper(seq, m)


def _build_loyalty_discard_exile_top(m: re.Match[str]) -> SentenceOutcome:
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.DISCARD,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        (
                            "cards",
                            Selector(
                                QUnbounded(),
                                SelectorMode.ALL,
                                FAnd(children=()),
                                Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
                            ),
                        ),
                    )
                ),
            ),
            Atom(
                verb=Verb.EXILE,
                args=AtomArgs(
                    pairs=(
                        (
                            "target",
                            Selector(
                                QConst(3),
                                SelectorMode.TARGET,
                                FAnd(children=()),
                                Zone(
                                    kind=ZoneKind.LIBRARY,
                                    controller=ControllerRef.YOU,
                                    position=ZonePosition.TOP,
                                ),
                            ),
                        ),
                    )
                ),
            ),
        )
    )
    return _loyalty_wrapper(seq, m)


def _build_loyalty_top_owner_library(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("cards", _target_creature()),
                (
                    "destination",
                    Zone(
                        kind=ZoneKind.LIBRARY,
                        controller=ControllerRef.OWNER,
                        position=ZonePosition.TOP,
                    ),
                ),
            )
        ),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_may_cast_graveyard(m: re.Match[str]) -> SentenceOutcome:
    ability = ActivatedAbility(
        cost=Cost(parts=(CostLoyalty(_loyalty_delta(m, 1)),)),
        effect=OptionalEffect(
            inner=Atom(
                verb=Verb.CAST,
                args=AtomArgs(
                    pairs=(
                        (
                            "source",
                            Selector(
                                QConst(1),
                                SelectorMode.TARGET,
                                _red_instant_or_sorcery_filter(),
                                Zone(
                                    kind=ZoneKind.GRAVEYARD,
                                    controller=ControllerRef.YOU,
                                ),
                            ),
                        ),
                    )
                ),
            )
        ),
    )
    return AbilityOutcome(ability=ability)


def _build_loyalty_extra_turns(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.EXTRA_TURN,
        args=AtomArgs(pairs=(("count", QConst(2)),)),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_pt_qprop(m: re.Match[str]) -> SentenceOutcome:
    x_amount = QProp(
        referent="controller",
        field=QPropField.CARDS_IN_GRAVEYARD,
        agg=QAgg.FIRST,
    )
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _target_creature()),
                ("power", PtDelta(PtDirection.DECREASE, x_amount)),
                ("toughness", PtDelta(PtDirection.DECREASE, x_amount)),
                ("duration", DurationEot()),
            )
        ),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_dmg_power(m: re.Match[str]) -> SentenceOutcome:
    amount = QProp(
        referent=Selector(
            QConst(1),
            SelectorMode.TARGET,
            FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                )
            ),
            Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
        ),
        field=QPropField.POWER,
        agg=QAgg.FIRST,
    )
    atom = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _another_target_creature()),
                ("amount", amount),
            )
        ),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_phase_out_target(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.PHASE_OUT,
        args=AtomArgs(pairs=(("target", _target_creature_you_dont_control()),)),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_lose_per_creature(m: re.Match[str]) -> SentenceOutcome:
    creature_count = QCount(
        Selector(
            QUnbounded(),
            SelectorMode.ALL,
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.TARGET_PLAYER),
        )
    )
    amount = QBin(
        op=QBinOp.MUL,
        left=QConst(int(m.group(2))),
        right=creature_count,
    )
    atom = Atom(
        verb=Verb.LOSE_LIFE,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.TARGET_PLAYER),
                ("amount", amount),
            )
        ),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_gain_draw_put(m: re.Match[str]) -> SentenceOutcome:
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.GAIN_LIFE,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(int(m.group(2)))),
                    )
                ),
            ),
            Atom(
                verb=Verb.DRAW,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(7)),
                    )
                ),
            ),
            Atom(
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        (
                            "cards",
                            Selector(
                                QConst(7),
                                SelectorMode.CHOOSE,
                                _PERMANENT_CARD_FILTER,
                                Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
                            ),
                        ),
                        (
                            "destination",
                            Zone(
                                kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU
                            ),
                        ),
                    )
                ),
            ),
        )
    )
    return _loyalty_wrapper(seq, m)


def _build_loyalty_exile_color_cmc_ux(m: re.Match[str]) -> SentenceOutcome:
    """Ugin [−X]: exile each permanent with mana value X or less that's one
    or more colors.  Dynamic loyalty cost → ``CostLoyalty(QX())``; cannot use
    ``_loyalty_wrapper`` (it parses a signed int delta)."""
    atom = Atom(
        verb=Verb.EXILE,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QUnbounded(),
                        SelectorMode.ALL,
                        FAnd(
                            (
                                FAtom(pred=FAtomPred.CMC_LE, count=QX()),
                                FAtom(pred=FAtomPred.COLOR_COUNT_GE, count=QConst(1)),
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
            cost=Cost(parts=(CostLoyalty(QX()),)),
            effect=atom,
        )
    )


# --- Cost build functions ---


def _build_cost_shrine_dmg(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostManaGeneric(QConst(int(m.group(1)))),
            CostDiscard(
                Selector(
                    QConst(1),
                    SelectorMode.CHOOSE,
                    FOr(
                        children=(
                            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land"),
                            FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Shrine"),
                        )
                    ),
                    Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
                )
            ),
        )
    )
    shrine_count = QCount(
        Selector(
            QUnbounded(),
            SelectorMode.ALL,
            FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Shrine"),
            Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
        )
    )
    atom = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _target_creature_or_planeswalker()),
                ("amount", shrine_count),
            )
        ),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


def _build_cost_sacrifice_counter(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostManaGeneric(QConst(int(m.group(1)))),
            CostSacrifice(
                Selector(
                    QConst(1),
                    SelectorMode.TARGET,
                    FAnd(
                        children=(
                            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                            FNot(inner=FAtom(pred=FAtomPred.IS_SOURCE)),
                        )
                    ),
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                )
            ),
        )
    )
    atom = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    _self_selector(
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU)
                    ),
                ),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                ("count", QConst(1)),
            )
        ),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


def _build_cost_sacrifice_destroy(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostManaGeneric(QConst(int(m.group(1)))),
            CostSacrifice(
                _self_selector(
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU)
                )
            ),
        )
    )
    atom = Atom(
        verb=Verb.DESTROY,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FOr(
                            children=(
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Artifact"),
                                FAtom(
                                    pred=FAtomPred.TYPE_EQ, string_value="Enchantment"
                                ),
                            )
                        ),
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
            )
        ),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


def _build_cost_page_draw(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostManaGeneric(QConst(int(m.group(1)))),
            CostTap(),
            CostPutCounter(
                counter_kind=CounterKind.PAGE,
                target=_self_selector(
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU)
                ),
                count=QConst(1),
            ),
        )
    )
    atom = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(1)),
            )
        ),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


def _build_cost_sacrifice_defender(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostManaGeneric(QConst(int(m.group(1)))),
            CostTap(),
            CostSacrifice(
                Selector(
                    QConst(1),
                    SelectorMode.CHOOSE,
                    FAnd(
                        children=(
                            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                            FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.DEFENDER),
                        )
                    ),
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
                )
            ),
        )
    )
    atom = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(1)),
            )
        ),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


def _build_cost_sacrifice_dmg(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostManaGeneric(QConst(int(m.group(1)))),
            CostTap(),
            CostSacrifice(
                _self_selector(
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU)
                )
            ),
        )
    )
    atom = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _target_creature()),
                ("amount", QConst(int(m.group(2)))),
            )
        ),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


def _build_cost_b_sacrifice_draw(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostManaGeneric(QConst(int(m.group(1)))),
            CostManaColor(color="B", amount=QConst(1)),
            CostSacrifice(
                _self_selector(
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU)
                )
            ),
        )
    )
    atom = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(1)),
            )
        ),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


def _build_cost_b_tap_gain_draw(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostManaGeneric(QConst(int(m.group(1)))),
            CostManaColor(color="B", amount=QConst(1)),
            CostTap(),
            CostSacrifice(
                Selector(
                    QConst(1),
                    SelectorMode.CHOOSE,
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
                )
            ),
        )
    )
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.GAIN_LIFE,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(int(m.group(2)))),
                    )
                ),
            ),
            Atom(
                verb=Verb.DRAW,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(1)),
                    )
                ),
            ),
        )
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=seq))


def _build_cost_u_discard_look(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostManaGeneric(QConst(int(m.group(1)))),
            CostManaColor(color="U", amount=QConst(1)),
            CostDiscard(
                _self_selector(Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU))
            ),
        )
    )
    atom = Atom(
        verb=Verb.LOOK_AT,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("count", QConst(2)),
            )
        ),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


def _build_cost_ub_sacrifice_return(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostManaGeneric(QConst(int(m.group(1)))),
            CostManaColor(color="U", amount=QConst(1)),
            CostManaColor(color="B", amount=QConst(1)),
            CostTap(),
            CostSacrifice(
                _self_selector(
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU)
                )
            ),
        )
    )
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
                    ),
                ),
                (
                    "destination",
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
                ),
            )
        ),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


def _build_cost_wu_discard_draw(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostManaGeneric(QConst(int(m.group(1)))),
            CostManaColor(color="W", amount=QConst(1)),
            CostManaColor(color="U", amount=QConst(1)),
            CostTap(),
            CostDiscard(
                Selector(
                    QConst(1),
                    SelectorMode.CHOOSE,
                    FAtom(pred=FAtomPred.SUPERTYPE_EQ, string_value="Legendary"),
                    Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
                )
            ),
        )
    )
    atom = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(2)),
            )
        ),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


def _build_cost_r_sacrifice_power_dmg(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostManaColor(color="R", amount=QConst(1)),
            CostSacrifice(
                _self_selector(
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU)
                )
            ),
        )
    )
    atom = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _target_creature_or_planeswalker()),
                (
                    "amount",
                    QProp(referent="source", field=QPropField.POWER, agg=QAgg.FIRST),
                ),
            )
        ),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


def _build_cost_page_scry(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostTap(),
            CostPutCounter(
                counter_kind=CounterKind.PAGE,
                target=_self_selector(
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU)
                ),
                count=QConst(1),
            ),
        )
    )
    atom = Atom(
        verb=Verb.SCRY,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("count", QConst(int(m.group(1)))),
            )
        ),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


def _build_cost_sacrifice_exile(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostTap(),
            CostSacrifice(
                _self_selector(
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU)
                )
            ),
        )
    )
    atom = Atom(
        verb=Verb.EXILE,
        args=AtomArgs(pairs=(("target", _graveyard_target_player()),)),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


def _build_cost_sacrifice_discard(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostTap(),
            CostSacrifice(
                _self_selector(
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU)
                )
            ),
        )
    )
    atom = Atom(
        verb=Verb.DISCARD,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.TARGET_PLAYER),
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAnd(children=()),
                        Zone(
                            kind=ZoneKind.HAND, controller=ControllerRef.TARGET_PLAYER
                        ),
                    ),
                ),
            )
        ),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


def _build_cost_sacrifice_search(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostTap(),
            CostSacrifice(
                _self_selector(
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU)
                )
            ),
        )
    )
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.SEARCH,
                args=AtomArgs(
                    pairs=(
                        (
                            "cards",
                            Selector(
                                QConst(1),
                                SelectorMode.CHOOSE,
                                FAnd(
                                    children=(
                                        FAtom(
                                            pred=FAtomPred.SUPERTYPE_EQ,
                                            string_value="Basic",
                                        ),
                                        FAtom(
                                            pred=FAtomPred.TYPE_EQ, string_value="Land"
                                        ),
                                    )
                                ),
                                Zone(
                                    kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU
                                ),
                            ),
                        ),
                        (
                            "destination",
                            Zone(
                                kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU
                            ),
                        ),
                        ("controller", ControllerRef.YOU),
                    )
                ),
            ),
            Atom(
                verb=Verb.SHUFFLE,
                args=AtomArgs(
                    pairs=(
                        (
                            "zone",
                            Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU),
                        ),
                    )
                ),
            ),
        )
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=seq))


def _build_cost_sacrifice_mana(m: re.Match[str]) -> SentenceOutcome:
    cost = Cost(
        parts=(
            CostTap(),
            CostSacrifice(
                _self_selector(
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU)
                )
            ),
        )
    )
    atom = Atom(
        verb=Verb.ADD_MANA,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(1)),
                ("color", "C"),
            )
        ),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


# --- Bullet build functions ---


def _build_bullet_all_pt(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _all_creatures()),
                ("power", PtDelta(PtDirection.DECREASE, QConst(int(m.group(1))))),
                ("toughness", PtDelta(PtDirection.DECREASE, QConst(int(m.group(2))))),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_counter_ability(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.COUNTER_SPELL,
        args=AtomArgs(pairs=(("target", _stack_target()),)),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_counter_spell(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.COUNTER_SPELL,
        args=AtomArgs(pairs=(("target", _stack_target()),)),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_create_token(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.CREATE_TOKEN,
        args=AtomArgs(
            pairs=(
                (
                    "tokens",
                    TokenSpec(
                        name="Beast",
                        type_line="Creature — Beast",
                        types=("Creature",),
                        subtypes=("Beast",),
                        power=QConst(int(m.group(1))),
                        toughness=QConst(int(m.group(2))),
                        keywords=(),
                        abilities=(),
                    ),
                ),
                ("count", QConst(1)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_copy_token(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.COPY,
        args=AtomArgs(
            pairs=(
                (
                    "source",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU),
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_cant_block(m: re.Match[str]) -> SentenceOutcome:
    # Lossy: no PREVENT_BLOCK grammar; encoded as MODIFY_PT zero-delta
    # placeholder on the affected creatures.
    zero = QConst(0)
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
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                                FNot(
                                    inner=FAtom(
                                        pred=FAtomPred.KEYWORD_HAS,
                                        keyword=Keyword.FLYING,
                                    )
                                ),
                            )
                        ),
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
                ("power", PtDelta(PtDirection.INCREASE, zero)),
                ("toughness", PtDelta(PtDirection.INCREASE, zero)),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_destroy_artifact(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DESTROY,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Artifact"),
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_destroy_enchantment(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DESTROY,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Enchantment"),
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_draw(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(1)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_draw_three(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(3)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_exile_graveyard(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.EXILE,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAnd(children=()),
                        Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.ANY),
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_put_counter(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    _self_selector(
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU)
                    ),
                ),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                ("count", QConst(1)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_remove_loyalty(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.REMOVE_COUNTER,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QUnbounded(),
                        SelectorMode.ALL,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
                ("counter_kind", CounterKind.LOYALTY),
                ("count", QConst(2)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_target_draw(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.TARGET_PLAYER),
                ("amount", QConst(1)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_gain_life(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.GAIN_LIFE,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(int(m.group(1)))),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_return_nonland_hand(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FNot(inner=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land")),
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
                (
                    "destination",
                    Zone(kind=ZoneKind.HAND, controller=ControllerRef.OWNER),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_return_two_creatures_hand(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(2),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
                (
                    "destination",
                    Zone(kind=ZoneKind.HAND, controller=ControllerRef.OWNER),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


# ---------------------------------------------------------------------------
# TEMPLATES — 73 entries
# ---------------------------------------------------------------------------

TEMPLATES: tuple[Template, ...] = (
    # --- MISC (13) ---
    Template(
        tid="B5c-then-return-is",
        name="then you may return instant/sorcery from graveyard to hand",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Then you may return an instant or sorcery card from your graveyard to your hand\.$"
        ),
        priority=_PRIORITY,
        build=_build_then_return_is,
    ),
    Template(
        tid="B5c-remind-trample",
        name="trample rule reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Trample \(This creature can deal excess combat damage to the player or planeswalker it's attacking\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_remind_trample,
    ),
    Template(
        tid="B5c-turn-to-slag",
        name="turn to slag deals N damage to target creature",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Turn to Slag deals (?P<dmg>\d+) damage to target creature\.$"
        ),
        priority=_PRIORITY,
        build=_build_turn_to_slag,
    ),
    Template(
        tid="B5c-untap-lands",
        name="untap up to four lands",
        bucket=_BUCKET,
        pattern=re.compile(r"^Untap up to four lands\.$"),
        priority=_PRIORITY,
        build=_build_untap_lands,
    ),
    Template(
        tid="B5c-pt-swap",
        name="target creature gets +A/+B and another gets -C/-D",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Until end of turn, target creature gets \+(?P<p1>\d+)/\+(?P<t1>\d+) "
            r"and another target creature gets -(?P<p2>\d+)/-(?P<t2>\d+)\.$"
        ),
        priority=_PRIORITY,
        build=_build_pt_swap,
    ),
    Template(
        tid="B5c-remind-vigilance",
        name="vigilance rule reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Vigilance \(Attacking doesn't cause this creature to tap\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_remind_vigilance,
    ),
    Template(
        tid="B5c-remind-vigilance-lifelink",
        name="vigilance lifelink rule reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Vigilance, lifelink \(Attacking doesn't cause this creature to tap\. "
            r"Damage dealt by this creature also causes you to gain that much life\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_remind_vigilance_lifelink,
    ),
    Template(
        tid="B5c-remind-vigilance-protection",
        name="vigilance protection from multicolored",
        bucket=_BUCKET,
        pattern=re.compile(r"^Vigilance, protection from multicolored$"),
        priority=_PRIORITY,
        build=_build_remind_vigilance_protection,
    ),
    Template(
        tid="B5c-remind-vigilance-reach-trample",
        name="vigilance reach trample",
        bucket=_BUCKET,
        pattern=re.compile(r"^Vigilance, reach, trample$"),
        priority=_PRIORITY,
        build=_build_remind_vigilance_reach_trample,
    ),
    Template(
        tid="B5c-geyser-dmg",
        name="volcanic geyser deals X damage to any target",
        bucket=_BUCKET,
        pattern=re.compile(r"^Volcanic Geyser deals X damage to any target\.$"),
        priority=_PRIORITY,
        build=_build_geyser_dmg,
    ),
    Template(
        tid="B5c-salvo-dmg",
        name="volcanic salvo deals N damage to up to two targets",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Volcanic Salvo deals (?P<dmg>\d+) damage to each of up to two target creatures and/or planeswalkers\.$"
        ),
        priority=_PRIORITY,
        build=_build_salvo_dmg,
    ),
    Template(
        tid="B5c-zombies-pt",
        name="zombies you control get +A/+B",
        bucket=_BUCKET,
        pattern=re.compile(r"^Zombies you control get \+(?P<p>\d+)/\+(?P<t>\d+)\.$"),
        priority=_PRIORITY,
        build=_build_zombies_pt,
    ),
    Template(
        tid="B5c-etb-soul-counter",
        name="enters with a soul counter",
        bucket=_BUCKET,
        pattern=re.compile(r"^This Equipment enters with a soul counter on it\.$"),
        priority=_PRIORITY,
        build=_build_etb_soul_counter,
    ),
    # --- LOYALTY (25) ---
    Template(
        tid="B5c-loyalty-chandra-dmg-any",
        name="loyalty: chandra deals N damage to any target",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Chandra deals (?P<dmg>\d+) damage to any target\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_chandra_dmg_any,
    ),
    Template(
        tid="B5c-loyalty-chandra-dmg-opps",
        name="loyalty: chandra deals N damage to each opponent",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Chandra deals (?P<dmg>\d+) damage to each opponent\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_chandra_dmg_opps,
    ),
    Template(
        tid="B5c-loyalty-draw-discard",
        name="loyalty: draw a card then discard a card",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Draw a card, then discard a card\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_draw_discard,
    ),
    Template(
        tid="B5c-loyalty-draw",
        name="loyalty: draw a card",
        bucket=_BUCKET,
        pattern=re.compile(r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Draw a card\.$"),
        priority=_PRIORITY,
        build=_build_loyalty_draw,
    ),
    Template(
        tid="B5c-loyalty-each-discard",
        name="loyalty: each player discards a card",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Each player discards a card\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_each_discard,
    ),
    Template(
        tid="B5c-loyalty-put-counter",
        name="loyalty: put +1/+1 counter on up to one target creature",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Put a \+1/\+1 counter on up to one target creature\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_put_counter,
    ),
    Template(
        tid="B5c-loyalty-return-creature",
        name="loyalty: return up to one target creature from graveyard to hand",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Return up to one target creature card from your graveyard to your hand\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_return_creature,
    ),
    Template(
        tid="B5c-loyalty-reveal",
        name="loyalty: reveal top card of library",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Reveal the top card of your library\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_reveal,
    ),
    Template(
        tid="B5c-loyalty-ugin-dmg",
        name="loyalty: ugin deals N damage to any target",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Ugin deals (?P<dmg>\d+) damage to any target\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_ugin_dmg,
    ),
    Template(
        tid="B5c-loyalty-pt-trample",
        name="loyalty: up to one target creature gets +A/+B and gains trample",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Up to one target creature gets "
            r"\+(?P<p>\d+)/\+(?P<t>\d+) and gains trample until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_pt_trample,
    ),
    Template(
        tid="B5c-loyalty-create-token",
        name="loyalty: create A/B green Beast creature token",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Create a (?P<p>\d+)/(?P<t>\d+) green Beast creature token\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_create_token,
    ),
    Template(
        tid="B5c-loyalty-creatures-pt-flying",
        name="loyalty: creatures you control get +A/+B and gain flying",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Creatures you control get "
            r"\+(?P<p>\d+)/\+(?P<t>\d+) and gain flying until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_creatures_pt_flying,
    ),
    Template(
        tid="B5c-loyalty-destroy",
        name="loyalty: destroy target creature",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Destroy target creature\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_destroy,
    ),
    Template(
        tid="B5c-loyalty-discard-draw",
        name="loyalty: discard hand then draw seven",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Discard your hand, then draw seven cards\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_discard_draw,
    ),
    Template(
        tid="B5c-loyalty-phase-out-all",
        name="loyalty: each creature target opponent controls phases out",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Each creature target opponent controls phases out\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_phase_out_all,
    ),
    Template(
        tid="B5c-loyalty-search-exile",
        name="loyalty: search graveyard and library for red instants/sorceries, exile, shuffle",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Search your graveyard and library for any number of "
            r"red instant and/or sorcery cards, exile them, then shuffle\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_search_exile,
    ),
    Template(
        tid="B5c-loyalty-extra-turns",
        name="loyalty: take two extra turns",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Take two extra turns after this one\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_extra_turns,
    ),
    Template(
        tid="B5c-loyalty-pt-qprop",
        name="loyalty: target creature gets -X/-X, X = cards in graveyard",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Target creature gets -X/-X until end of turn, "
            r"where X is the number of cards in your graveyard\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_pt_qprop,
    ),
    Template(
        tid="B5c-loyalty-dmg-power",
        name="loyalty: target creature you control deals power damage to another target",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Target creature you control deals damage "
            r"equal to its power to another target creature\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_dmg_power,
    ),
    Template(
        tid="B5c-loyalty-phase-out-target",
        name="loyalty: target creature you don't control phases out",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Target creature you don't control phases out\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_phase_out_target,
    ),
    Template(
        tid="B5c-loyalty-lose-per-creature",
        name="loyalty: target opponent loses N life per creature in graveyard",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Target opponent loses (?P<n>\d+) life "
            r"for each creature card in their graveyard\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_lose_per_creature,
    ),
    Template(
        tid="B5c-loyalty-gain-draw-put",
        name="loyalty: gain N life, draw seven, put up to seven permanents",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: You gain (?P<life>\d+) life, draw seven cards, "
            r"then put up to seven permanent cards from your hand onto the battlefield\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_gain_draw_put,
    ),
    Template(
        tid="B5c-loyalty-exile-color-cmc-ux",
        name="loyalty: exile each permanent with mana value X or less, one or more colors",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[\u2212X\]: Exile each permanent with mana value X or less "
            r"that's one or more colors\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_exile_color_cmc_ux,
    ),
    Template(
        tid="B5c-loyalty-discard-exile-top",
        name="loyalty: discard hand, exile top three of library",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: "
            r"Discard your hand, then exile the top three cards of your library\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_discard_exile_top,
    ),
    Template(
        tid="B5c-loyalty-top-owner-library",
        name="loyalty: put target creature on top of its owner's library",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: "
            r"Put target creature on top of its owner's library\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_top_owner_library,
    ),
    Template(
        tid="B5c-loyalty-may-cast-graveyard",
        name="loyalty: may cast target red instant or sorcery from graveyard",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: "
            r"You may cast target red instant or sorcery card from your graveyard\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_may_cast_graveyard,
    ),
    # --- COST (17) ---
    Template(
        tid="B5c-cost-shrine-dmg",
        name="{N}, discard land/Shrine: shrine damage",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{(?P<n>\d+)\}, Discard a land card or Shrine card: "
            r"Sanctum of Shattered Heights deals X damage to target creature or planeswalker, "
            r"where X is the number of Shrines you control\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_shrine_dmg,
    ),
    Template(
        tid="B5c-cost-sacrifice-counter",
        name="{N}, sacrifice another creature: put +1/+1 on this creature",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{(?P<n>\d+)\}, Sacrifice another creature: "
            r"Put a \+1/\+1 counter on this creature\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_sacrifice_counter,
    ),
    Template(
        tid="B5c-cost-sacrifice-destroy",
        name="{N}, sacrifice this creature: destroy target artifact or enchantment",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{(?P<n>\d+)\}, Sacrifice this creature: "
            r"Destroy target artifact or enchantment\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_sacrifice_destroy,
    ),
    Template(
        tid="B5c-cost-page-draw",
        name="{N}, {T}, put page counter: draw a card",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{(?P<n>\d+)\}, \{T\}, Put a page counter on this artifact: Draw a card\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_page_draw,
    ),
    Template(
        tid="B5c-cost-sacrifice-defender",
        name="{N}, {T}, sacrifice defender: draw a card",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{(?P<n>\d+)\}, \{T\}, Sacrifice a creature with defender: Draw a card\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_sacrifice_defender,
    ),
    Template(
        tid="B5c-cost-sacrifice-dmg",
        name="{N}, {T}, sacrifice this artifact: it deals N damage",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{(?P<n>\d+)\}, \{T\}, Sacrifice this artifact: "
            r"It deals (?P<dmg>\d+) damage to target creature\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_sacrifice_dmg,
    ),
    Template(
        tid="B5c-cost-b-sacrifice-draw",
        name="{N}{B}, sacrifice this creature: draw a card",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{(?P<n>\d+)\}\{B\}, Sacrifice this creature: Draw a card\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_b_sacrifice_draw,
    ),
    Template(
        tid="B5c-cost-b-tap-gain-draw",
        name="{N}{B}, {T}, sacrifice creature: gain N life and draw",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{(?P<n>\d+)\}\{B\}, \{T\}, Sacrifice a creature: "
            r"You gain (?P<life>\d+) life and draw a card\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_b_tap_gain_draw,
    ),
    Template(
        tid="B5c-cost-u-discard-look",
        name="{N}{U}, discard this card: look at top two cards",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{(?P<n>\d+)\}\{U\}, Discard this card: "
            r"Look at the top two cards of your library\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_u_discard_look,
    ),
    Template(
        tid="B5c-cost-ub-sacrifice-return",
        name="{N}{U}{B}, {T}, sacrifice: return target creature from graveyard",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{(?P<n>\d+)\}\{U\}\{B\}, \{T\}, Sacrifice this creature: "
            r"Return target creature card from your graveyard to the battlefield\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_ub_sacrifice_return,
    ),
    Template(
        tid="B5c-cost-wu-discard-draw",
        name="{N}{W}{U}, {T}, discard legendary: draw two",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{(?P<n>\d+)\}\{W\}\{U\}, \{T\}, Discard a legendary card: Draw two cards\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_wu_discard_draw,
    ),
    Template(
        tid="B5c-cost-r-sacrifice-power-dmg",
        name="{R}, sacrifice this creature: deals power damage",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{R\}, Sacrifice this creature: "
            r"It deals damage equal to its power to target creature or planeswalker\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_r_sacrifice_power_dmg,
    ),
    Template(
        tid="B5c-cost-page-scry",
        name="{T}, put page counter: scry N",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{T\}, Put a page counter on this artifact: Scry (?P<n>\d+)\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_page_scry,
    ),
    Template(
        tid="B5c-cost-sacrifice-exile",
        name="{T}, sacrifice this artifact: exile target player's graveyard",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{T\}, Sacrifice this artifact: Exile target player's graveyard\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_sacrifice_exile,
    ),
    Template(
        tid="B5c-cost-sacrifice-discard",
        name="{T}, sacrifice this creature: target opponent discards",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{T\}, Sacrifice this creature: Target opponent discards a card\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_sacrifice_discard,
    ),
    Template(
        tid="B5c-cost-sacrifice-search",
        name="{T}, sacrifice this land: search for basic land, shuffle",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{T\}, Sacrifice this land: Search your library for a basic land card, "
            r"put it onto the battlefield tapped, then shuffle\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_sacrifice_search,
    ),
    Template(
        tid="B5c-cost-sacrifice-mana",
        name="{T}, sacrifice this token: add one mana of any color",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{T\}, Sacrifice this token: Add one mana of any color\.$"
        ),
        priority=_PRIORITY,
        build=_build_cost_sacrifice_mana,
    ),
    # --- BULLET (17) ---
    Template(
        tid="B5c-bullet-all-pt",
        name="all creatures get -A/-B until end of turn",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\u2022 All creatures get -(?P<p>\d+)/-(?P<t>\d+) until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_bullet_all_pt,
    ),
    Template(
        tid="B5c-bullet-counter-ability",
        name="counter target activated or triggered ability",
        bucket=_BUCKET,
        pattern=re.compile(r"^\u2022 Counter target activated or triggered ability\.$"),
        priority=_PRIORITY,
        build=_build_bullet_counter_ability,
    ),
    Template(
        tid="B5c-bullet-counter-spell",
        name="counter target spell",
        bucket=_BUCKET,
        pattern=re.compile(r"^\u2022 Counter target spell\.$"),
        priority=_PRIORITY,
        build=_build_bullet_counter_spell,
    ),
    Template(
        tid="B5c-bullet-create-token",
        name="create A/B green Beast creature token",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\u2022 Create a (?P<p>\d+)/(?P<t>\d+) green Beast creature token\.$"
        ),
        priority=_PRIORITY,
        build=_build_bullet_create_token,
    ),
    Template(
        tid="B5c-bullet-copy-token",
        name="create a token that's a copy of target creature you control",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\u2022 Create a token that's a copy of target creature you control\.$"
        ),
        priority=_PRIORITY,
        build=_build_bullet_copy_token,
    ),
    Template(
        tid="B5c-bullet-cant-block",
        name="creatures without flying can't block this turn",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\u2022 Creatures without flying can't block this turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_bullet_cant_block,
    ),
    Template(
        tid="B5c-bullet-destroy-artifact",
        name="destroy target artifact",
        bucket=_BUCKET,
        pattern=re.compile(r"^\u2022 Destroy target artifact\.$"),
        priority=_PRIORITY,
        build=_build_bullet_destroy_artifact,
    ),
    Template(
        tid="B5c-bullet-destroy-enchantment",
        name="destroy target enchantment",
        bucket=_BUCKET,
        pattern=re.compile(r"^\u2022 Destroy target enchantment\.$"),
        priority=_PRIORITY,
        build=_build_bullet_destroy_enchantment,
    ),
    Template(
        tid="B5c-bullet-draw",
        name="draw a card",
        bucket=_BUCKET,
        pattern=re.compile(r"^\u2022 Draw a card\.$"),
        priority=_PRIORITY,
        build=_build_bullet_draw,
    ),
    Template(
        tid="B5c-bullet-draw-three",
        name="draw three cards",
        bucket=_BUCKET,
        pattern=re.compile(r"^\u2022 Draw three cards\.$"),
        priority=_PRIORITY,
        build=_build_bullet_draw_three,
    ),
    Template(
        tid="B5c-bullet-exile-graveyard",
        name="exile target card from a graveyard",
        bucket=_BUCKET,
        pattern=re.compile(r"^\u2022 Exile target card from a graveyard\.$"),
        priority=_PRIORITY,
        build=_build_bullet_exile_graveyard,
    ),
    Template(
        tid="B5c-bullet-put-counter",
        name="put +1/+1 counter on this creature",
        bucket=_BUCKET,
        pattern=re.compile(r"^\u2022 Put a \+1/\+1 counter on this creature\.$"),
        priority=_PRIORITY,
        build=_build_bullet_put_counter,
    ),
    Template(
        tid="B5c-bullet-remove-loyalty",
        name="remove two loyalty counters from each planeswalker",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\u2022 Remove two loyalty counters from each planeswalker\.$"
        ),
        priority=_PRIORITY,
        build=_build_bullet_remove_loyalty,
    ),
    Template(
        tid="B5c-bullet-target-draw",
        name="target player draws a card",
        bucket=_BUCKET,
        pattern=re.compile(r"^\u2022 Target player draws a card\.$"),
        priority=_PRIORITY,
        build=_build_bullet_target_draw,
    ),
    Template(
        tid="B5c-bullet-gain-life",
        name="you gain N life",
        bucket=_BUCKET,
        pattern=re.compile(r"^\u2022 You gain (?P<n>\d+) life\.$"),
        priority=_PRIORITY,
        build=_build_bullet_gain_life,
    ),
    Template(
        tid="B5c-bullet-return-nonland-hand",
        name="return target nonland permanent to owner's hand",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\u2022 Return target nonland permanent to its owner's hand\.$"
        ),
        priority=_PRIORITY,
        build=_build_bullet_return_nonland_hand,
    ),
    Template(
        tid="B5c-bullet-return-two-creatures-hand",
        name="return up to two target creatures to owners' hands",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\u2022 Return up to two target creatures to their owners' hands\.$"
        ),
        priority=_PRIORITY,
        build=_build_bullet_return_two_creatures_hand,
    ),
)


# ---------------------------------------------------------------------------
# UNCOVERED — 18 normalized-key rows
# ---------------------------------------------------------------------------

UNCOVERED: tuple[tuple[str, str], ...] = (
    (
        "Then if you control four or more lands, untap that land.",
        "No conditional Then-continuation with land-count condition",
    ),
    (
        "Then it fights up to one target creature you don't control.",
        "No FIGHT verb/anaphoric source in grammar",
    ),
    (
        "Then that creature deals damage equal to its power to target creature you don't control.",
        "No Then-continuation anaphoric power-based DEAL_DAMAGE",
    ),
    (
        "This ability costs {N} less to activate for each Shrine you control.",
        "No activation-cost reduction construct",
    ),
    (
        "Those creatures don't untap during their controller's next untap step.",
        "No turn-scoped untap prevention",
    ),
    (
        "Untap that creature.",
        "No anaphoric target resolution",
    ),
    (
        "Until end of turn, you may cast spells from your hand without paying their mana costs.",
        "No mana-cost waiver grant",
    ),
    (
        "Until end of turn, you may play cards exiled this way.",
        "No 'play cards exiled this way' grant",
    ),
    (
        "Until the end of your next turn, they can't phase in.",
        "Phase-in prevention (compiler built-in; merged into preceding loyalty activation)",
    ),
    (
        '[\u2212N]: Until end of turn, creatures you control gain "You may have this creature assign its combat damage as though it weren\'t blocked."',
        "No embedded replacement ability text",
    ),
    (
        "[\u2212N]: Whenever a creature attacks this turn, put a +N/+N counter on it.",
        "No triggered ability with turn-scoped trigger",
    ),
    (
        "[\u2212N]: Whenever one or more nontoken creatures attack this turn, create that many N/N white Soldier creature tokens that are tapped and attacking.",
        "No triggered ability with attack-count token creation",
    ),
    (
        '[\u2212N]: You get an emblem with "At the beginning of combat on your turn, create a N/N white Soldier creature token, then put a +N/+N counter on each creature you control."',
        "No emblem with embedded trigger",
    ),
    (
        '[\u2212N]: You get an emblem with "At the beginning of combat on your turn, put target creature card from a graveyard onto the battlefield under your control.',
        "No emblem with embedded triggered ability",
    ),
    (
        '[\u2212N]: You get an emblem with "At the beginning of your end step, you may search your library for a creature card, put it onto the battlefield, then shuffle."',
        "No emblem with embedded end-step search trigger",
    ),
    (
        "{N}{R}, {T}, Discard your hand: Until end of turn, whenever a creature you control with power N or less deals combat damage to a player, draw a card.",
        "No turn-scoped combat-damage trigger grant",
    ),
    (
        "{T}, Pay N life: Flip a coin.",
        "No Pay-life coin-flip construct",
    ),
)
