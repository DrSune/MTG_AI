"""B5c bucket templates — 86 templates covering 88 of 90 B5c shapes.

Bucket input: ``/tmp/opencode/phase1_buckets/B5c.json`` (90 normalized shape
keys → ``[card, sentence]`` pairs; sentences carry *concrete* numbers, keys
carry ``N`` placeholders).  Templates fullmatch the **concrete** oracle
sentence, never the normalized key.

Coverage (90 normalized keys = 88 covered + 2 uncovered; 91 concrete
sentences = 89 covered + 2 uncovered; ``• You gain N life.`` has two
concrete variants both covered by one template; the round-8-C emblem
marker template covers three ``[−N]: You get an emblem with "…"``
shapes — C19 keeps the quoted text out of the IR, the card-level
emblem attach is the payload):

- **88 covered shapes** (86 unique tids; the gain-life template covers two
  concrete variants, the emblem marker covers three):
  keyword reminders (Trample, Vigilance, Vigilance+lifelink,
  Vigilance+protection, Vigilance+reach+trample), then-continuation
  effects, static P/T grants, activated cost/loyalty abilities,
  bullet (spell) effects, X-quantities, QProp/QBin amount expressions,
  token creation, token copy, phase out, counter spells, extra turns,
  scry/reveal/look-at, per-creature life loss, ETB counter placement,
  loyalty discard-hand/exile-top-library, loyalty move-to-top-of-library,
  loyalty may-cast-from-graveyard, bullet return-to-owner-hand,
  loyalty turn-scoped trigger (Basri [−1], Basri Ket [−2] — a
  DelayedTrigger with DurationEot, CR 603.7, since m21-fidelity 2026-10-29;
  it was the round-4 C3 GRANT_ABILITY to the planeswalker, which died with
  it; "it" = the attacker via the event referent).
- **2 uncovered shapes** — embedded replacement text, plus the phase-in
  built-in note.  Round 9-B landed Frost Breath's untap-step prevention
  (R9-4 step+DurationUntilNextStep) and Subira's delayed combat-damage
  draw trigger (R9-5/C22 DelayedTrigger).  Recorded in UNCOVERED.
  Round-8-C landed
  the emblem markers, Basri's attack-token grant, the Catalyst/HoF
  cast-play permissions (CAST cost-waiver idiom) and the Sanctum
  activation-cost reducer; the r7-B no-grammar top-ups (flip-cost,
  then-if-lands, damage-equal-power) are counted here too.

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
    Conditional,
    ControllerRef,
    Cost,
    CostDeltaReduceGeneric,
    CostDiscard,
    CostLife,
    CostLoyalty,
    CostManaColor,
    CostManaGeneric,
    CostModifier,
    CostPutCounter,
    CostSacrifice,
    CostTap,
    CounterKind,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    DelayedTrigger,
    DurationEot,
    DurationUntilNextStep,
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
    QAtMost,
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
    Step,
    TapStateEvent,
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
from MTG_bot.core.compiler.templates_b2b import _to_a_player
from MTG_bot.core.compiler.templates_b5a import target_spell, target_stack_ability

_BUCKET = "B5c"
_PRIORITY = 100


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
        zones=(zone,),
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
    """Selector for ``any target`` (Shock-style; see the r17-2 note).

    r17-2 (geyser-FIX): printed "any target" designates a creature, a
    planeswalker or a player (CR 109.5) — NEVER a card hiding in a hand or
    library. The card side compiles to the battlefield population with the
    FOr type-idiom filter; the PLAYER side joins through the engine's
    idiom widening (query._widen_any_target / selectors._is_any_universal
    recognize this exact shape), so the filter is never evaluated on a
    player handle. (Pre-fix this emitted Zone(ANY, ANY) + the universal
    FAnd, which enumerated opponent-hidden zones — the D10/E3 leak.)
    """
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FOr(
            (
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                # r17-2 discriminator: the third branch never matches a
                # card (no card carries "Player" in its types) — it marks
                # the population as the CR 109.5 "any target" one so the
                # engine widening can tell it apart from the printed
                # "target creature or planeswalker" two-branch shape
                # (which NEVER denotes a player, CR 115.1d).
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Player"),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _target_creature() -> Selector:
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _up_to_one_target_creature() -> Selector:
    """TARGET + QAtMost(1) — grammar round 8 / C17: "up to one target
    creature" (loyalty counter / +A/+B-trample rows) keeps target mode
    with a 1..N designation range; the interim CHOOSE encoding from the
    R7 batches erased the legal-target decision (C15).
    """
    return Selector(
        QAtMost(1),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _all_creatures() -> Selector:
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _target_opponent_creatures() -> Selector:
    """``Each creature target opponent controls``."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.TARGET_OPPONENT),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )


def _each_opponent_player() -> Selector:
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(children=()),
        zones=(Zone(kind=ZoneKind.PLAYER, controller=ControllerRef.ALL_OPPONENTS),),
    )


def _graveyard_target_player() -> Selector:
    """Whole target player's graveyard (EXILE)."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(children=()),
        zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.TARGET_PLAYER),),
    )


def _hand_you_selector(count_qty) -> Selector:
    return Selector(
        count_qty,
        SelectorMode.CHOOSE,
        FAnd(children=()),
        zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),),
    )


def _up_to_two_target_creatures() -> Selector:
    """TARGET + QAtMost(2) — C17 (round 8): Volcanic Salvo's "each of up
    to two target creatures and/or planeswalkers" designates 1..2 targets.
    """
    return Selector(
        QAtMost(2),
        SelectorMode.TARGET,
        FOr(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
                        zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),),
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
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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


def _loyalty_wrapper(effect: Atom | Seq | DelayedTrigger, m: re.Match[str]) -> SentenceOutcome:
    """Wrap an effect in ActivatedAbility with CostLoyalty."""
    return AbilityOutcome(
        ability=ActivatedAbility(
            cost=Cost(parts=(CostLoyalty(_loyalty_delta(m, 1)),)),
            effect=effect,
        )
    )


def _event_reference() -> Selector:
    """Selector bound to the triggering event's subject (grammar round 4,
    object anaphora, convention C2: mode CHOOSE + count QConst(1) + the
    neutral zone + empty zones; the universal filter carries no type
    check).  Per-event subject: declare_attackers → the attacker
    (Selector docstring)."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAnd(children=()),
        zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
        referent="event",
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


def _build_loyalty_basri_attack_counter(m: re.Match[str]) -> SentenceOutcome:
    """Round 4 row #17: [−1] grant a turn-scoped triggered ability —
    whenever a creature attacks this turn, put a +N/+N counter on it.

    A DELAYED triggered ability (CR 603.7): DelayedTrigger(DurationEot,
    DeclareAttackersEvent(Creature), PUT_COUNTER) — Subira's "this turn,
    whenever" shape; it lives for the turn on its own, so it keeps working
    if the planeswalker is gone (CR 603.7c). "it" = the attacker, the
    declare_attackers event subject, bound via the event referent in the
    PUT_COUNTER target role (convention C1: declare_attackers → the
    attacker; C2). m21-fidelity (2026-10-29): it was GRANT_ABILITY(target=
    this planeswalker, the trigger, DurationEot), which died with the
    walker (a -1 at 1 loyalty did nothing). Lossy: none."""
    p = int(m.group("p"))
    t = int(m.group("t"))
    if p != t:
        raise ValueError(
            f"B5c-loyalty-basri-attack-counter expects equal P/T, got +{p}/+{t}"
        )
    delayed = DelayedTrigger(
        duration=DurationEot(),
        event=DeclareAttackersEvent(
            filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
        ),
        condition=None,
        effect=Atom(
            verb=Verb.PUT_COUNTER,
            args=AtomArgs(
                pairs=(
                    ("target", _event_reference()),
                    ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                    ("count", QConst(p)),
                )
            ),
        ),
    )
    return _loyalty_wrapper(delayed, m)


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
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)),
                        ("from", Zone(ZoneKind.HAND, ControllerRef.YOU)),
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
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.ANY)),
                ("from", Zone(ZoneKind.HAND, ControllerRef.ANY)),
                ("controller", ControllerRef.ANY),
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAnd(children=()),
                        zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.ANY),),
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
    """[+N]: "Return up to one target creature card from your graveyard
    to your hand" — TARGET + QAtMost(1) per C17 (round 8; the interim
    CHOOSE shape is replaced)."""
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QAtMost(1),
                        SelectorMode.TARGET,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),),
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
    """Loyalty: "Create a P/T green Beast creature token" — color="G"
    populated (round 8 / C-2 repair)."""
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
                        colors=("G",),  # C-2 repair (round 8)
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
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)),
                        ("from", Zone(ZoneKind.HAND, ControllerRef.YOU)),
                        ("controller", ControllerRef.YOU),
                        (
                            "cards",
                            Selector(
                                QUnbounded(),
                                SelectorMode.ALL,
                                FAnd(children=()),
                                zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),),
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
                                zones=(Zone(
                                    kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU
                                ),),
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
                                zones=(Zone(
                                    kind=ZoneKind.GRAVEYARD,
                                    controller=ControllerRef.YOU,
                                ),),
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
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)),
                        ("from", Zone(ZoneKind.HAND, ControllerRef.YOU)),
                        ("controller", ControllerRef.YOU),
                        (
                            "cards",
                            Selector(
                                QUnbounded(),
                                SelectorMode.ALL,
                                FAnd(children=()),
                                zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),),
                            ),
                        ),
                    )
                ),
            ),
            Atom(
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                        (
                            "target",
                            Selector(
                                QConst(3),
                                SelectorMode.TARGET,
                                FAnd(children=()),
                                zones=(Zone(
                                    kind=ZoneKind.LIBRARY,
                                    controller=ControllerRef.YOU,
                                    position=ZonePosition.TOP,
                                ),),
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
                                zones=(Zone(
                                    kind=ZoneKind.GRAVEYARD,
                                    controller=ControllerRef.YOU,
                                ),),
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
    """Garruk, Savage Herald's -2: "Target creature you control deals damage
    equal to its power to another target creature." V3 (2026-10-29): the
    creature is the damage's ``dealer`` (CR 120.2b), so its deathtouch and
    lifelink apply; the amount reads the same designation."""
    creature_you_control = Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
    )
    amount = QProp(
        referent=creature_you_control,
        field=QPropField.POWER,
        agg=QAgg.FIRST,
    )
    atom = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _another_target_creature()),
                ("amount", amount),
                ("dealer", creature_you_control),
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
            zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.TARGET_OPPONENT),),
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
                ("controller", ControllerRef.TARGET_OPPONENT),
                ("amount", amount),
            )
        ),
    )
    return _loyalty_wrapper(atom, m)


def _build_loyalty_gain_draw_put(m: re.Match[str]) -> SentenceOutcome:
    """Ugin, the Spirit Dragon [-10]: "You gain 7 life, draw seven cards, then
    put up to seven permanent cards from your hand onto the battlefield."

    m21-fidelity (wave 4, 2026-10-30): "up to seven" is QAtMost(7), any
    number from zero to seven (the resolve-time CHOOSE lane asks each pick
    with a NONE stop). It was QConst(7), so every permanent card in hand,
    up to seven, had to go onto the battlefield."""
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
                                QAtMost(7),
                                SelectorMode.CHOOSE,
                                _PERMANENT_CARD_FILTER,
                                zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),),
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
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
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
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
                    zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),),
                )
            ),
        )
    )
    shrine_count = QCount(
        Selector(
            QUnbounded(),
            SelectorMode.ALL,
            FAnd(
                children=(
                    FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Shrine"),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                )
            ),
            zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
                    zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
                            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                        )
                    ),
                    zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
                    FAnd(
                        children=(
                            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                        )
                    ),
                    zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
                        zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),),
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
                    zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),),
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
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                ("target", _graveyard_target_player()),
            )
        ),
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
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.TARGET_OPPONENT)),
                ("from", Zone(ZoneKind.HAND, ControllerRef.TARGET_OPPONENT)),
                ("controller", ControllerRef.TARGET_OPPONENT),
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAnd(children=()),
                        zones=(Zone(
                            kind=ZoneKind.HAND, controller=ControllerRef.TARGET_OPPONENT
                        ),),
                    ),
                ),
            )
        ),
    )
    return AbilityOutcome(ability=ActivatedAbility(cost=cost, effect=atom))


def _build_cost_sacrifice_search(m: re.Match[str]) -> SentenceOutcome:
    """``{T}, Sacrifice this land: Search your library for a basic land
    card, put it onto the battlefield tapped, then shuffle.`` (Fabled
    Passage s1; the s2 conditional-untap tail is the B5c-then-if-lands
    row.)

    C2 (batch 0, 2026-10-02): the printed clause says "onto the battlefield
    TAPPED" and the grammar carries the slot (SEARCH ``tapped_on_enter``
    opt:bool, ``_v_search`` honors it, MOVE_ZONE precedent b2b:1453) — the
    old compile silently DROPPED it, so the <4-land branch entered untapped
    (wave-21b suspect). The flag is stamped here now; the >=4-land falsifier
    is the tail row's Conditional(CONTROLLER_COUNT_GE Lands>=4, UNTAP)."""
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
                                zones=(Zone(
                                    kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU
                                ),),
                            ),
                        ),
                        (
                            "destination",
                            Zone(
                                kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU
                            ),
                        ),
                        ("controller", ControllerRef.YOU),
                        ("tapped_on_enter", True),
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
    """{T}, Sacrifice this token: "Add one mana of any color" —
    color="ANY" (round 8 / R8-3 / C-3 repair)."""
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
                ("color", "ANY"),
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
    # R5-10: an ability, not a spell (STACK_KIND_EQ ACTIVATED or TRIGGERED).
    atom = Atom(
        verb=Verb.COUNTER_SPELL,
        args=AtomArgs(pairs=(("target", target_stack_ability("ACTIVATED", "TRIGGERED")),)),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_counter_spell(m: re.Match[str]) -> SentenceOutcome:
    # R5-10: "target spell" (STACK_KIND_EQ SPELL).
    atom = Atom(
        verb=Verb.COUNTER_SPELL,
        args=AtomArgs(pairs=(("target", target_spell()),)),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_create_token(m: re.Match[str]) -> SentenceOutcome:
    """• "Create a P/T green Beast creature token" — color="G"
    (round 8 / C-2 repair)."""
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
                        colors=("G",),  # C-2 repair (round 8)
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
                        FAnd(
                            children=(
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                                FAtom(
                                    pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU
                                ),
                            )
                        ),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_bullet_cant_block(m: re.Match[str]) -> SentenceOutcome:
    """``• Creatures without flying can't block this turn.`` (Destructive
    Tampering; C5 — the lossy MODIFY_PT zero-delta placeholder is replaced
    by the real PREVENT_EFFECT shape: a universal condition (the clause
    names no object), a DeclareBlockersEvent whose blocker-side ``filter``
    is FAnd(TYPE_EQ Creature, FNot(KEYWORD_HAS FLYING)) — the Shacklegeist
    blocked-slot idiom turned onto the blocker side — and the printed
    "this turn" as DurationEot. PREVENT_EFFECT carries no ``target`` role
    (PITFALLS: atoms with a target= under _VERB_ROLES fail validation)."""
    atom = Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                ("condition", FAnd(children=())),
                (
                    "event",
                    DeclareBlockersEvent(
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
                        )
                    ),
                ),
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
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FAnd(children=()),
                        zones=(Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.ANY),),
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
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
    """• "Return up to two target creatures to their owners' hands" —
    TARGET + QAtMost(2) per C17 (round 8)."""
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QAtMost(2),
                        SelectorMode.TARGET,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
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
# Grammar round-7-B batch builders (doc 2026-09-28/03 §3, R7-B top-ups)
# ---------------------------------------------------------------------------


def _build_flip_coin_pay_life(m: re.Match[str]) -> SentenceOutcome:
    """``{T}, Pay 3 life: Flip a coin.`` (Tavern Swindler s1) —
    ActivatedAbility whose cost is CostTap + CostLife (the standing cost
    parts list; ``CostLife`` already exists in the grammar) and whose
    effect is the role-less Verb.FLIP_COIN atom (r3b: "the coin is
    flipped; the outcome is read by FAtomPred.FLIP_WON, never by an arg").
    Together with the B5b-flip-won row this consumes the FLIP_COIN orphan
    (PC-6 must drop to the standing 1 = PHASE_IN).
    C16: the coin flip is the stochastic decision vertex; the activation
    itself is fully forced."""
    return AbilityOutcome(
        ability=ActivatedAbility(
            cost=Cost(parts=(CostTap(), CostLife(amount=QConst(int(m.group(1)))))),
            effect=Atom(verb=Verb.FLIP_COIN, args=AtomArgs(pairs=())),
        )
    )


def _build_then_if_lands_untap(m: re.Match[str]) -> SentenceOutcome:
    """``Then if you control four or more lands, untap that land.`` (Fabled
    Passage s2) — "Then " continuation merged after the search+shuffle
    effect; Conditional(CONTROLLER_COUNT_GE(Land, QConst(4)), UNTAP).
    The referent is bound ``referent="result"`` (R7-1 result register),
    NOT the doc sketch's ``referent="target"``: checked against the landed
    Fabled Passage golden, s1 is a SEARCH (no TARGET selector exists), so
    "that land" names the card the previous sentence searched-and-moved =
    the result register — the only antecedent that exists today (C12).
    "four or more lands" is a CONTROLLER_COUNT_GE over lands with the
    you-scoped board reading (no ``who`` role on that predicate).
    C16: the four-lands gate is a board condition, the untap target is the
    register — nothing controller-chosen is defaulted."""
    untap = Atom(
        verb=Verb.UNTAP,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land"),
                        zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
                        referent="result",
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(
        effect=Conditional(
            pred=FAtom(
                pred=FAtomPred.CONTROLLER_COUNT_GE,
                inner_filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land"),
                count=QConst(4),
            ),
            then_effect=untap,
        )
    )


def _build_then_that_creature_damage_power(m: re.Match[str]) -> SentenceOutcome:
    """``Then that creature deals damage equal to its power to target
    creature you don't control.`` (Hunter's Edge s2) — "Then "
    continuation; DEAL_DAMAGE with target = the new TARGET creature.
    "That creature" is the previous sentence's countered creature: the
    ``result`` register PUT_COUNTER writes (R7-1). V3 (2026-10-29): it is
    both the ``dealer`` (CR 120.2b: the creature deals the damage, so its
    deathtouch and lifelink apply) and the power read. Before, the amount
    was ``QProp("target")``, which on this two-target spell reads the
    damage step's own target (the opposing creature).
    C16: the damage target is an open controller choice; the amount is
    board-dynamic, not a choice."""
    that_creature = Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
        referent="result",
    )
    return EffectOutcome(
        effect=Atom(
            verb=Verb.DEAL_DAMAGE,
            args=AtomArgs(
                pairs=(
                    ("target", _target_creature_you_dont_control()),
                    (
                        "amount",
                        QProp(referent="result", field=QPropField.POWER),
                    ),
                    ("dealer", that_creature),
                )
            ),
        )
    )


# ---------------------------------------------------------------------------
# Grammar round-7 batch builders (doc 2026-09-28/03 §3 R7-A)
# ---------------------------------------------------------------------------


def _build_untap_that_creature(m: re.Match[str]) -> SentenceOutcome:
    """``Untap that creature.`` (Traitorous Greed s2) — UNTAP whose
    target is the spell's previously-targeted creature (R7-1): R4
    ``referent="target"`` (the neutral-zone CHOOSE/QConst(1) convention
    the B5b counter-unless-pays row established), so the anaphor binds
    the s1 GAIN_CONTROL target today.  C16: no choice — forced."""
    atom = Atom(
        verb=Verb.UNTAP,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        zones=(Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),),
                        referent="target",
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_then_it_fights_up_to_one(m: re.Match[str]) -> SentenceOutcome:
    """``Then it fights up to one target creature you don't control.``
    (Primal Might s2) — Verb.FIGHT (R7-8/R7-9a; the "Then " prefix makes
    this a continuation, merged after the +X/+X step).
    C15: resolution-time "up to one" = CHOOSE + QConst(1) (0..1 open),
    not TARGET — the C-1 collapse fix applies to new templates.
    The attacker ("it") is the prior sentence's +X/+X object: FIGHT has
    no attacker role (the r8 canonical documents the attacker as the
    source object), so the anaphoric attacker binds the result register
    executor-side; documented."""
    atom = Atom(
        verb=Verb.FIGHT,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAnd(
                            children=(
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                                FNot(
                                    inner=FAtom(
                                        pred=FAtomPred.CONTROLLER_IS,
                                        who=ControllerRef.YOU,
                                    )
                                ),
                            )
                        ),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


# ---------------------------------------------------------------------------
# Grammar round-8-C coverage batch builders (doc 2026-09-28/08 §8-C)
# ---------------------------------------------------------------------------


def _build_get_emblem(m: re.Match[str]) -> SentenceOutcome:
    """``[−N]: You get an emblem with "…".`` (Basri Ket / Liliana, Waker of
    the Dead / Garruk, Unleashed — ONE template for all three, C19).

    Verb.GET_EMBLEM (R8-7) is a ROLE-LESS MARKER: the quoted inner text
    NEVER enters the ability IR — the emblem's own abilities are the
    payload via the card-level emblem attach (compile_pool two-pass,
    compiler.py L1374+; all three emblems already attach today — the
    [−N] rows were the last missing piece).  Mirrors the FLIP_COIN
    role-less row exactly.  Executor deferred per the MANDATE_ATTACK /
    FIGHT orphan precedent (PC-6 unaffected: the verb is consumed, the
    attach is compile-pool state).

    C16: none — fully forced (the emblem is granted; its inner decisions
    live in the attached emblem's own compiled tree)."""
    return _loyalty_wrapper(Atom(verb=Verb.GET_EMBLEM, args=AtomArgs(pairs=())), m)


def _build_loyalty_soldier_attack_tokens(m: re.Match[str]) -> SentenceOutcome:
    """``[−2]: Whenever one or more nontoken creatures attack this turn,
    create that many 1/1 white Soldier creature tokens that are tapped and
    attacking.`` (Basri Ket) — a DELAYED triggered ability (CR 603.7):
    DelayedTrigger(DurationEot, DeclareAttackersEvent(nontoken creature),
    CREATE_TOKEN), the Subira "this turn, whenever" shape. It lives for the
    turn on its own (CR 603.7c), so the loyalty PAY decision stays the
    single activation vertex, the trigger fires once per attack
    declaration, and it still works after Basri Ket is gone (a -2 at 2
    loyalty kills him, CR 704.5i). m21-fidelity (2026-10-29): it was
    GRANT_ABILITY(target=Basri, the trigger, DurationEot), which made no
    Soldiers once Basri had died.

    Filter: FAnd(Creature, FNot(IS_TOKEN)) — "nontoken" via the Gadrak
    FAtomPred.IS_TOKEN (FNot precedent: b2b 'another' →
    FNot(IS_SOURCE)); the nontoken condition also blocks the self-feed
    the created tokens would otherwise cause.  "one or more" is intrinsic
    to a filtered event firing (every qualifying declaration event
    satisfies ≥1) — no quantity collapse; the token count stays OPEN via
    QProp(event, THAT_MANY_COUNT) (R7-5).
    TokenSpec carries color="W" (R8-2) + enters_tapped/enters_attacking
    True (R8-4, the C-2 repair this row was the pool case for).
    C16: open — the [−2] loyalty activation, and each attack event's
    attacker set (board-dynamic "that many")."""
    p = int(m.group("p"))
    t = int(m.group("t"))
    delayed = DelayedTrigger(
        duration=DurationEot(),
        event=DeclareAttackersEvent(
            filter=FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FNot(inner=FAtom(pred=FAtomPred.IS_TOKEN)),
                )
            )
        ),
        condition=None,
        effect=Atom(
            verb=Verb.CREATE_TOKEN,
            args=AtomArgs(
                pairs=(
                    (
                        "tokens",
                        TokenSpec(
                            name="Soldier",
                            type_line="Creature — Soldier",
                            types=("Creature",),
                            subtypes=("Soldier",),
                            power=QConst(p),
                            toughness=QConst(t),
                            keywords=(),
                            abilities=(),
                            colors=("W",),
                            enters_tapped=True,
                            enters_attacking=True,
                        ),
                    ),
                    (
                        "count",
                        QProp(referent="event", field=QPropField.THAT_MANY_COUNT),
                    ),
                )
            ),
        ),
    )
    return _loyalty_wrapper(delayed, m)


def _build_waive_cast_from_hand(m: re.Match[str]) -> SentenceOutcome:
    """``Until end of turn, you may cast spells from your hand without
    paying their mana costs.`` (Chandra, Flame's Catalyst [−8] s2).

    House permission idiom (B4-cast-goblin-top-library): empty-cost
    ActivatedAbility carrying OptionalEffect(CAST) — "may" stays the
    open decision (C15), "which card" stays open via the CHOOSE selector
    over your hand (QUnbounded — any number).  The mana waiver is the
    CAST atom's ``cost`` role = Cost(parts=()) — the established empty-
    cost waiver reading (B5c-loyalty-may-cast-graveyard precedent; the
    b3 UNCOVERED note calls it out explicitly).
    Lossy (C11 class, verbatim): "Until end of turn" — CAST/optional-cast
    have no duration role (R9 grammar item: CAST duration role).
    Assembly note: non-continuation second sentence of the [−8]
    activation; the empty-cost ActivatedAbility assembles as a sibling
    node (r7-B deviation-2 class, executor association note).
    C16: open — whether to cast, which cards, how many."""
    atom = Atom(
        verb=Verb.CAST,
        args=AtomArgs(
            pairs=(
                (
                    "source",
                    Selector(
                        QUnbounded(),
                        SelectorMode.CHOOSE,
                        FAnd(children=()),
                        zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),),
                    ),
                ),
                ("cost", Cost(parts=())),
            )
        ),
    )
    return AbilityOutcome(
        ability=ActivatedAbility(cost=Cost(), effect=OptionalEffect(inner=atom))
    )


def _build_play_cards_exiled_this_way(m: re.Match[str]) -> SentenceOutcome:
    """``Until end of turn, you may play cards exiled this way.`` (Chandra,
    Heart of Fire [+1] s2) — same empty-cost ActivatedAbility +
    OptionalEffect(CAST) permission idiom, source scoped by
    FAtomPred.IS_EXILED_WITH_SOURCE (R8-6: "exiled by this ability's
    source" — HoF's own top-three exile; HoF exiles from HER library,
    so Zone(EXILE, YOU) is the printed zone).

    Lossy (C11 class, verbatim): "play" covers lands too, CAST is the
    only from-zone permission verb (R9 item: PLAY-from-zone, or a land
    role on CAST); "Until end of turn" — no CAST duration role.
    C16: open — whether to play, which exiled cards, how many."""
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


def _build_shrine_activation_cost_reduction(m: re.Match[str]) -> SentenceOutcome:
    """``This ability costs {1} less to activate for each Shrine you
    control.`` (Sanctum of Tranquil Light) — CostModifier sibling node
    (T3 round K, b4 precedent _build_total_power_cost_modifier):
    filter=IS_SOURCE (the printed "This ability" anchor object — the
    source card),     delta=CostDeltaReduceGeneric(QBin(MUL, {N},
    QCount(Shrine-you-control))) — the "for each X" multiplication,
    Shrine count via the b2a ``TYPE_EQ "Shrine"`` census (C1 batch,
    2026-10-02: the tribe noun is a type-line word — "Legendary
    Enchantment — Shrine" — read by the executor's TYPE/SUBTYPE/SUPERTYPE
    word test; the superseded "supertype name in NAME_EQ position"
    rationale was wrong: NAME_EQ is the closed-card-name pred and the
    old bake counted 0 on every board, killing the discount).

    Lossy (verbatim): "to activate" — CostModifier's filter vocabulary
    is spell/permanent-scoped, the sibling node's adjacency to the {5}{W}
    activation is the binding signal for the executor (R9 item: ability-
    scope filter for CostModifier).
    C16: none — board-conditioned amount, fully forced."""
    n = int(m.group("n"))
    modifier = CostModifier(
        filter=FAtom(pred=FAtomPred.IS_SOURCE),
        controller_ref=ControllerRef.YOU,
        delta=CostDeltaReduceGeneric(
            amount=QBin(
                op=QBinOp.MUL,
                left=QConst(n),
                right=QCount(
                    Selector(
                        QUnbounded(),
                        SelectorMode.ALL,
                        FAnd(
                            children=(
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Shrine"),
                                FAtom(
                                    pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU
                                ),
                            )
                        ),
                        zones=(Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
                    )
                ),
            )
        ),
    )
    return AbilityOutcome(ability=modifier)


def _build_those_no_untap_next(m: re.Match[str]) -> SentenceOutcome:
    """``Those creatures don't untap during their controller's next untap
    step.`` (Frost Breath s2) — grammar round 9-B row 12, closing the
    Capture-Sphere "step scope dropped" lossy family with the R9-4 slots:
    PREVENT_EFFECT over TapStateEvent(tapped=False — the untap attempt is
    the NEW state being prevented; Capture Sphere mirror), anaphoric
    "Those creatures" = s1's TARGET set via FAtom(IS_ANY_TARGET) on both
    the condition and the event filter (Selfless Savior / Subira-s1
    target-set convention; s1 is ``B5c-tap-up-to-two``'s TARGET QAtMost(2)
    selector), step=Step.UNTAP (R9-4 role) and the NEXT-step lifetime via
    DurationUntilNextStep(UNTAP, owner_scoped=True) — "THEIR controller's"
    binds the step to each affected creature's controller, not the active
    turn.

    The row lands as an EffectOutcome: Frost is an instant, so the
    compiler folds it into the SpellAbility(INSTANT) Seq beside the s1
    tap atom — the prevention is a spell-resolved continuous effect (the
    duration node carries it past resolution), never a stray StaticAbility.
    C16: none — fully forced."""
    targeted = FAtom(pred=FAtomPred.IS_ANY_TARGET)
    atom = Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                ("condition", targeted),
                ("duration", DurationUntilNextStep(step=Step.UNTAP, owner_scoped=True)),
                ("event", TapStateEvent(tapped=False, filter=targeted)),
                ("step", Step.UNTAP),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_subira_delayed_draw(m: re.Match[str]) -> SentenceOutcome:
    """``{1}{R}, {T}, Discard your hand: Until end of turn, whenever a
    creature you control with power 2 or less deals combat damage to a
    player, draw a card.`` (Subira s2) — grammar round 9-B row 13,
    DelayedTrigger (R9-5, C22): the activation's effect IS the delayed
    trigger registration — live DurationEot ("Until end of turn" REQUIRED
    duration — a trigger without a lifetime window would just be a static
    TriggeredAbility), event = DamageDealtEvent(amount=QUnbounded() — any
    amount, the b2b convention), combat=True, source = FAnd(TYPE_EQ
    Creature, CONTROLLER_IS YOU, POWER_LE N) (the dealer side rides the
    R9-4-era ``source`` slot, b2b _noncombat_source_event idiom); the
    trigger's effect is the DRAW atom.  "Discard your hand" cost:
    CostDiscard over ALL cards in your hand (universal filter, the
    b4 _all-cards shape).

    B-57: "to a player" is the damaged-recipient filter b2b's
    ``_to_a_player`` (not a permanent, CR 120.1). It used to be dropped
    (the universal FAnd(())), so a blocked creature drew off its blocker.
    C16: open — which qualifying creature to attack with; draw is forced
    once the event fires."""
    dealer = FAnd(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            FAtom(pred=FAtomPred.POWER_LE, count=QConst(int(m.group("p")))),
        )
    )
    cost = Cost(
        parts=(
            CostManaGeneric(QConst(int(m.group("n")))),
            CostManaColor("R", QConst(1)),
            CostTap(),
            CostDiscard(
                Selector(
                    QUnbounded(),
                    SelectorMode.ALL,
                    FAnd(children=()),
                    zones=(Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),),
                )
            ),
        )
    )
    draw = Atom(
        verb=Verb.DRAW,
        args=AtomArgs(pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))),
    )
    return AbilityOutcome(
        ability=ActivatedAbility(
            cost=cost,
            effect=DelayedTrigger(
                duration=DurationEot(),
                event=DamageDealtEvent(
                    amount=QUnbounded(),
                    filter=_to_a_player(),  # B-57
                    source=dealer,
                    combat=True,
                ),
                condition=None,
                effect=draw,
            ),
        )
    )


def _build_herald_assign_as_unblocked(m: re.Match[str]) -> SentenceOutcome:
    """``[−7]: Until end of turn, creatures you control gain "You may have
    this creature assign its combat damage as though it weren't blocked."``
    (Garruk, Savage Herald — grammar round 10 b5c row, R10-4/C28).

    The quoted embedded ability text is a continuous static:
    ``GRANT_ABILITY(target=creatures you control, ability=StaticAbility(
    OptionalEffect(Atom(DAMAGE_ASSIGN_POLICY, scope=AS_UNBLOCKED))),
    duration=DurationEot)`` — the C28 reading keeps the surface "You may"
    OUTSIDE the atom (OptionalEffect layer, mirror of the MANA_POLICY
    "may spend" reading) while ``DurationEot`` rides the GRANT itself
    (Basri precedent: duration on the grant atom, not the granted
    ability).  The policy verb's executor is deferred per the
    MANA_POLICY / ADD_LAND_PLAY orphan precedent; the grammar side is
    complete.

    C16: open — the [−N] loyalty activation is the single decision
    vertex (no inner may/target beyond the granted optional policy)."""
    granted = StaticAbility(
        effect=OptionalEffect(
            inner=Atom(
                verb=Verb.DAMAGE_ASSIGN_POLICY,
                args=AtomArgs(pairs=(("scope", "AS_UNBLOCKED"),)),
            )
        )
    )
    return _loyalty_wrapper(
        Atom(
            verb=Verb.GRANT_ABILITY,
            args=AtomArgs(
                pairs=(
                    ("target", _creatures_you_control()),
                    ("ability", granted),
                    ("duration", DurationEot()),
                )
            ),
        ),
        m,
    )


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
    # --- LOYALTY (26) ---
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
    Template(
        tid="B5c-loyalty-basri-attack-counter",
        name="loyalty: grant turn-scoped attack counter trigger (Basri)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: "
            r"Whenever a creature attacks this turn, "
            r"put a \+(?P<p>\d+)/\+(?P<t>\d+) counter on it\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_basri_attack_counter,
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
    # --- grammar round-7 batch (doc 2026-09-28/03 §3 R7-A) ---
    Template(
        tid="B5c-untap-that-creature",
        name="untap that creature (target-referent untap)",
        bucket="B5c",
        pattern=re.compile(r"^Untap that creature\.$"),
        priority=100,
        build=_build_untap_that_creature,
    ),
    Template(
        tid="B5c-then-it-fights",
        name="then it fights up to one creature you don't control (FIGHT)",
        bucket="B5c",
        pattern=re.compile(
            r"^Then it fights up to one target creature you don't control\.$"
        ),
        priority=100,
        build=_build_then_it_fights_up_to_one,
    ),
    # --- grammar round-7-B batch (no-grammar top-ups; doc 2026-09-28/03 §3) ---
    Template(
        tid="B5c-flip-cost",
        name="tap, pay N life: flip a coin (Tavern Swindler)",
        bucket="B5c",
        pattern=re.compile(r"^\{T\}, Pay (\d+) life: Flip a coin\.$"),
        priority=100,
        build=_build_flip_coin_pay_life,
    ),
    Template(
        tid="B5c-then-if-lands-untap",
        name="then if you control four or more lands, untap that land (result)",
        bucket="B5c",
        pattern=re.compile(
            r"^Then if you control four or more lands, untap that land\.$"
        ),
        priority=100,
        build=_build_then_if_lands_untap,
    ),
    Template(
        tid="B5c-damage-equal-power",
        name="then that creature deals damage equal to its power (QProp POWER)",
        bucket="B5c",
        pattern=re.compile(
            r"^Then that creature deals damage equal to its power to target "
            r"creature you don't control\.$"
        ),
        priority=_PRIORITY,
        build=_build_then_that_creature_damage_power,
    ),
    # --- grammar round-8-C coverage batch (doc 2026-09-28/08 §8-C) ---
    Template(
        tid="B5c-get-emblem",
        name="loyalty: you get an emblem with (marker, C19)",
        bucket=_BUCKET,
        pattern=re.compile(
            r'^\[(?P<loy>\+\d+|\u2212\d+)\]: You get an emblem with ".+$'
        ),
        priority=_PRIORITY,
        build=_build_get_emblem,
    ),
    Template(
        tid="B5c-loyalty-soldier-attack-tokens",
        name="loyalty: nontoken attackers this turn make that many tapped/attacking Soldier tokens (Basri Ket)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Whenever one or more nontoken "
            r"creatures attack this turn, create that many (?P<p>\d+)/"
            r"(?P<t>\d+) white Soldier creature tokens that are tapped "
            r"and attacking\.$"
        ),
        priority=_PRIORITY,
        build=_build_loyalty_soldier_attack_tokens,
    ),
    Template(
        tid="B5c-waive-cast-from-hand",
        name="until end of turn, cast spells from hand without paying mana costs (Catalyst)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Until end of turn, you may cast spells from your hand "
            r"without paying their mana costs\.$"
        ),
        priority=_PRIORITY,
        build=_build_waive_cast_from_hand,
    ),
    Template(
        tid="B5c-play-cards-exiled-this-way",
        name="until end of turn, play cards exiled this way (Heart of Fire)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Until end of turn, you may play cards exiled this way\.$"
        ),
        priority=_PRIORITY,
        build=_build_play_cards_exiled_this_way,
    ),
    Template(
        tid="B5c-shrine-activation-cost",
        name="this ability costs N less to activate for each Shrine you control",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^This ability costs \{(?P<n>\d+)\} less to activate for each "
            r"Shrine you control\.$"
        ),
        priority=_PRIORITY,
        build=_build_shrine_activation_cost_reduction,
    ),
    # --- grammar round-9-B coverage batch (doc 2026-09-28/11 §9-B rows 12-13) ---
    Template(
        tid="B5c-those-no-untap-next",
        name="targeted creatures skip their controller's next untap step (R9-4 step+duration)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Those creatures don't untap during their controller's next "
            r"untap step\.$"
        ),
        priority=_PRIORITY,
        build=_build_those_no_untap_next,
    ),
    Template(
        tid="B5c-cost-discard-hand-delayed-draw",
        name="delayed combat-damage draw trigger (DelayedTrigger, R9-5/C22)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\{(?P<n>\d+)\}\{R\}, \{T\}, Discard your hand: Until end of "
            r"turn, whenever a creature you control with power (?P<p>\d+) or "
            r"less deals combat damage to a player, draw a card\.$"
        ),
        priority=_PRIORITY,
        build=_build_subira_delayed_draw,
    ),
    # --- grammar round-10 coverage batch (doc 2026-09-29/02 §phase-10-B row 4) ---
    Template(
        tid="B5c-loyalty-assign-as-unblocked",
        name="creatures you control may assign damage as though unblocked (R10-4/C28)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^\[(?P<loy>\+\d+|\u2212\d+)\]: Until end of turn, creatures "
            r"you control gain \"You may have this creature assign its "
            r"combat damage as though it weren't blocked\.\"$"
        ),
        priority=_PRIORITY,
        build=_build_herald_assign_as_unblocked,
    ),
)


# ---------------------------------------------------------------------------
# UNCOVERED — 1 normalized-key row
# ---------------------------------------------------------------------------

UNCOVERED: tuple[tuple[str, str], ...] = (
    (
        "Until the end of your next turn, they can't phase in.",
        "Phase-in prevention (compiler built-in; merged into preceding loyalty activation)",
    ),
)
