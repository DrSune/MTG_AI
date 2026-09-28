"""B5b bucket templates — 47 templates covering 51 of 90 B5b shapes.

Bucket input: ``/tmp/opencode/phase1_buckets/B5b.json`` (90 normalized shape
keys → ``[card, sentence]`` pairs; sentences carry *concrete* numbers, keys
carry ``N`` placeholders).  Templates fullmatch the **concrete** oracle
sentence, never the normalized key.

Coverage (90 = 51 template + 0 rule-reminder + 39 uncovered):

- **51 template-covered shapes** (47 templates: 44 single-shape tids +
  3 multi-shape normalized tids — put-counter ×3, return-cards-hand ×2,
  named-damage ×2; ``B5b-modpt-plus`` is one shape with two concrete rows):
  keyword rule-reminder sentences (Flash/Haste/Hexproof/Lifelink/Menace/
  Prowess/Reach), continuation effects (discard/draw/gain-life/gain-mana-
  value/modPT+keyword), token creation (Demon/Zombie), counter placement,
  zone moves (graveyard → battlefield / hand / owner's hand), cost
  modifiers (noncreature spells cost {N} more), scry/reveal,
  search/shuffle, named/any-target damage, activated abilities
  (sacrifice-grant, tap-spirits), P/T modifications (+N, -N, +X),
  reveal-hand, sacrifice-flying, discard-2, replacement/"instead" effects
  (died-gain-life, nontoken-enter-exile, triple-damage, counter-plus-one,
  die-exile, graveyard-exile, draw-not-first) and the counter-unless-pays
  cost modifier (grammar round 5, doc-07 batch), conditional attack
  restriction (Gadrak: StaticAbility.condition = FNot(CONTROLLER_COUNT_GE
  Artifact) over a PREVENT_EFFECT/DeclareAttackersEvent — C9/C10) and
  dynamic power definition (Kinetic Augur: SET_PT power-only via
  QCount(GY instant-or-sorcery) — grammar round 6 R6-3).
- **0 rule-reminder shapes** — no fully-parenthesised sentences in B5b.
- **39 uncovered shapes** — conditional triggers, anaphora,
  coin-flip gates, fractional computation, modal continuations,
  protection-from-color-choice, multi-zone search, keyword-loss, and
  other constructs with no grammar equivalent.
  Recorded in the test file.

Conventions (documented build decisions):

- ``this creature`` / self-referent targets are encoded as
  ``Selector(QConst(1), SelectorMode.CHOOSE, FAtom(IS_SOURCE),
  Zone(BATTLEFIELD, ANY))`` — B5a's semantic self-reference convention
  (shapes #25, #63).
- ``another target creature you control`` →
  ``Selector(QConst(1), TARGET, FAnd(TYPE_EQ Creature, CONTROLLER_IS You),
  Zone(BATTLEFIELD, ANY))`` (shape #63).
- ``target creature or planeswalker`` →
  ``Selector(QConst(1), TARGET, FOr(TYPE_EQ Creature, TYPE_EQ
  Planeswalker), Zone(BATTLEFIELD, ANY))`` (shapes #64, #71).
- ``any target`` (Shock) →
  ``Selector(QConst(1), TARGET, FAnd(children=()), Zone(ANY, ANY))``
  (shape #70).
- ``+N/+N`` → ``PtDelta(INCREASE, QConst(N))``; ``-N/-N`` →
  ``PtDelta(DECREASE, QConst(N))``; ``+X/+X`` →
  ``PtDelta(INCREASE, QX())`` (shapes #25, #75, #77, #78, #79, #80).
- Token colors (black) are dropped: ``TokenSpec`` has no color field
  (shapes #21, #22 — grammar gap).
- ``that creature's mana value`` → ``QProp("target", MANA_VALUE, FIRST)``
  — best-effort; the sacrificed creature has no clean grammar referent
  (shape #27).
- Multi-shape templates use a single closed-alternation pattern for the
  varying part; the builder branches on the captured text (put-counter,
  return-cards-hand, named-damage).  ``B5b-modpt-plus`` covers two
  concrete rows for one normalized shape without branching.
- ``Sacrifice this creature:`` and ``Tap two untapped Spirits you control:``
  are ``ActivatedAbility`` nodes with typed cost parts (shapes #63, #73).
- ``Return target spell or creature to its owner's hand`` →
  ``Selector(QConst(1), TARGET, FOr(FNot(IS_PERMANENT), TYPE_EQ Creature),
  Zone(STACK, ANY), zones=(Zone(BATTLEFIELD, ANY),))`` with destination
  ``Zone(HAND, OWNER)`` (shape #60 — spell-or-creature disjunction over
  STACK ∪ BATTLEFIELD; "its owner" is ``ControllerRef.OWNER``).
- ``Noncreature spells cost {N} more to cast`` →
  ``CostModifier(FNot(TYPE_EQ Creature), ANY, CostDeltaIncreaseGeneric)``
  as a sibling ``Ability`` node via ``AbilityOutcome`` (shape #44; no
  "you" in the sentence → ``ControllerRef.ANY``).
- **C6** (doc-07, binding): a replacement "If X would …, do Y instead"
  sentence compiles to a card-level ``ReplacementAbility(event,
  condition, action)`` via ``AbilityOutcome`` regardless of which
  sentence it follows — the event scoping binds it to the right action.
- **C7** (doc-07, binding): a ``Selector`` in ``CostModifier.controller_ref``
  means *the controller of the selected object*; the modifier applies to
  costs that controller pays for the filtered object, including ``unless``
  payments (``B5b-counter-unless-pays``: ``Selector(referent="target")``
  makes the targeted spell's controller pay the {1}→{4} unless-cost).
- **C8** (doc-07, binding): ``it`` / ``that X`` in a replacement action is
  the event subject → ``Selector(referent="event")`` (convention C2 shape:
  CHOOSE + ``QConst(1)`` + neutral zone ``Zone(ANY, ANY)``).

PC-3: every B5b concrete sentence fullmatches **at most one** template
(patterns are pairwise disjoint by construction); verified in tests.
"""

from __future__ import annotations

import re

from MTG_bot.core.ability_tree import (
    QX,
    ActivatedAbility,
    Atom,
    AtomArgs,
    CardDrawnEvent,
    ControllerRef,
    Cost,
    CostDeltaIncreaseGeneric,
    CostModifier,
    CostSacrifice,
    CostTap,
    CounterKind,
    CounterPlacedEvent,
    CreatureDiesEvent,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DurationEot,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    LifeGainedEvent,
    PtDelta,
    PtDirection,
    QAgg,
    QAtLeast,
    QBin,
    QBinOp,
    QConst,
    QCount,
    QProp,
    QPropField,
    QUnbounded,
    ReplacementAbility,
    Selector,
    SelectorMode,
    Seq,
    StaticAbility,
    TokenSpec,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    KeywordOutcome,
    SentenceOutcome,
    Template,
)

_BUCKET = "B5b"
_PRIORITY = 100


# ---------------------------------------------------------------------------
# Shared selector helpers
# ---------------------------------------------------------------------------


def _this_creature() -> Selector:
    """Selector for ``this creature`` — the source of the ability."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAtom(pred=FAtomPred.IS_SOURCE),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _each_creature_you_control() -> Selector:
    """Selector for ``each creature you control``."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _up_to_two_target_creatures() -> Selector:
    """Selector for ``up to two target creatures``."""
    return Selector(
        QConst(2),
        SelectorMode.CHOOSE,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _target_creature_you_control() -> Selector:
    """Selector for ``target creature you control``."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _target_creature_or_pw() -> Selector:
    """Selector for ``target creature or planeswalker``."""
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


def _target_permanent_card_your_graveyard() -> Selector:
    """Selector for ``target permanent card from your graveyard``."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.IS_PERMANENT),
        Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
    )


def _up_to_two_target_creature_cards_your_graveyard() -> Selector:
    """Selector for ``up to two target creature cards from your graveyard``."""
    return Selector(
        QConst(2),
        SelectorMode.CHOOSE,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
    )


def _two_untapped_spirits_you_control() -> Selector:
    """Selector for ``two untapped Spirits you control``."""
    return Selector(
        QConst(2),
        SelectorMode.CHOOSE,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Spirit"),
                FAtom(pred=FAtomPred.IS_UNTAPPED),
                FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            )
        ),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


def _target_creature_not_you() -> Selector:
    """Selector for ``target creature you don't control``."""
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


def _any_target() -> Selector:
    """Selector for ``any target`` (Shock-style)."""
    return Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAnd(children=()),
        Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
    )


def _each_permanent_you_control() -> Selector:
    """Selector for ``Permanents you control``."""
    return Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )


# ---------------------------------------------------------------------------
# Build functions (one per template)
# ---------------------------------------------------------------------------


def _build_flash(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.FLASH)


def _build_haste(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.HASTE)


def _build_hexproof(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.HEXPROOF)


def _build_token_demon(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.CREATE_TOKEN,
        args=AtomArgs(
            pairs=(
                (
                    "tokens",
                    TokenSpec(
                        name="Demon",
                        type_line="Creature — Demon",
                        types=("Creature",),
                        subtypes=("Demon",),
                        power=QConst(int(m.group(1))),
                        toughness=QConst(int(m.group(2))),
                        keywords=(Keyword.FLYING,),
                        abilities=(),
                    ),
                ),
                ("count", QConst(1)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_token_zombie(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.CREATE_TOKEN,
        args=AtomArgs(
            pairs=(
                (
                    "tokens",
                    TokenSpec(
                        name="Zombie",
                        type_line="Creature — Zombie",
                        types=("Creature",),
                        subtypes=("Zombie",),
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


def _build_cont_discard(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DISCARD,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
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
    return EffectOutcome(effect=atom)


def _build_cont_draw(m: re.Match[str]) -> SentenceOutcome:
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


def _build_seq_modpt_trample(m: re.Match[str]) -> SentenceOutcome:
    target = _this_creature()
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.MODIFY_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        (
                            "power",
                            PtDelta(PtDirection.INCREASE, QConst(int(m.group(1)))),
                        ),
                        (
                            "toughness",
                            PtDelta(PtDirection.INCREASE, QConst(int(m.group(2)))),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
            Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        ("ability", KeywordAbility(keyword=Keyword.TRAMPLE, params=())),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )
    return EffectOutcome(effect=seq)


def _build_cont_gain_4(m: re.Match[str]) -> SentenceOutcome:
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


def _build_cont_gain_mv(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.GAIN_LIFE,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QProp("target", QPropField.MANA_VALUE, QAgg.FIRST)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_lifelink(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.LIFELINK)


def _build_look_3(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.LOOK_AT,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("count", QConst(3)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_menace(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.MENACE)


def _build_perm_hex_ind(m: re.Match[str]) -> SentenceOutcome:
    target = _each_permanent_you_control()
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        (
                            "ability",
                            KeywordAbility(keyword=Keyword.HEXPROOF, params=()),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
            Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        (
                            "ability",
                            KeywordAbility(keyword=Keyword.INDESTRUCTIBLE, params=()),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )
    return EffectOutcome(effect=seq)


def _build_prowess(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.PROWESS)


def _build_put_counter(m: re.Match[str]) -> SentenceOutcome:
    """Branch on the captured target description (group 3)."""
    target_desc = m.group(3)
    if target_desc == "each creature you control":
        target = _each_creature_you_control()
    elif target_desc == "each of up to two target creatures":
        target = _up_to_two_target_creatures()
    elif target_desc == "target creature you control":
        target = _target_creature_you_control()
    else:
        raise ValueError(f"unexpected put-counter target: {target_desc!r}")
    atom = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                ("target", target),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                ("count", QConst(1)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_reach(m: re.Match[str]) -> SentenceOutcome:
    return KeywordOutcome(keyword=Keyword.REACH)


def _build_return_creatures_battlefield(m: re.Match[str]) -> SentenceOutcome:
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
                    Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_return_cards_hand(m: re.Match[str]) -> SentenceOutcome:
    """Branch on the captured card description (group 1)."""
    card_desc = m.group(1)
    if card_desc == "target permanent card":
        cards = _target_permanent_card_your_graveyard()
    elif card_desc == "up to two target creature cards":
        cards = _up_to_two_target_creature_cards_your_graveyard()
    else:
        raise ValueError(f"unexpected return-cards-hand description: {card_desc!r}")
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("cards", cards),
                ("destination", Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_return_spell_creature_owner_hand(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.TARGET,
                        FOr(
                            children=(
                                FNot(inner=FAtom(pred=FAtomPred.IS_PERMANENT)),
                                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                            )
                        ),
                        Zone(kind=ZoneKind.STACK, controller=ControllerRef.ANY),
                        zones=(
                            Zone(
                                kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY
                            ),
                        ),
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


def _build_sacr_grant(m: re.Match[str]) -> SentenceOutcome:
    effect = Atom(
        verb=Verb.GRANT_ABILITY,
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
                                FAtom(
                                    pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU
                                ),
                            )
                        ),
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
                ("ability", KeywordAbility(keyword=Keyword.INDESTRUCTIBLE, params=())),
                ("duration", DurationEot()),
            )
        ),
    )
    ability = ActivatedAbility(
        cost=Cost(parts=(CostSacrifice(target=_this_creature()),)),
        effect=effect,
    )
    return AbilityOutcome(ability=ability)


def _build_named_damage(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _target_creature_or_pw()),
                ("amount", QConst(int(m.group(2)))),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_scr_reveal(m: re.Match[str]) -> SentenceOutcome:
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.SCRY,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("count", QConst(int(m.group(1)))),
                    )
                ),
            ),
            Atom(
                verb=Verb.REVEAL,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("count", QConst(1)),
                    )
                ),
            ),
        )
    )
    return EffectOutcome(effect=seq)


def _build_scr(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.SCRY,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("count", QConst(int(m.group(1)))),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_search_shuffle(m: re.Match[str]) -> SentenceOutcome:
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
                                FAnd(children=()),
                                Zone(
                                    kind=ZoneKind.LIBRARY, controller=ControllerRef.YOU
                                ),
                            ),
                        ),
                        (
                            "destination",
                            Zone(kind=ZoneKind.HAND, controller=ControllerRef.YOU),
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
    return EffectOutcome(effect=seq)


def _build_damage_any(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DEAL_DAMAGE,
        args=AtomArgs(
            pairs=(
                ("target", _any_target()),
                ("amount", QConst(int(m.group(1)))),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_tap_spirits(m: re.Match[str]) -> SentenceOutcome:
    effect = Atom(
        verb=Verb.TAP,
        args=AtomArgs(pairs=(("target", _target_creature_not_you()),)),
    )
    ability = ActivatedAbility(
        cost=Cost(parts=(CostTap(target=_two_untapped_spirits_you_control()),)),
        effect=effect,
    )
    return AbilityOutcome(ability=ability)


def _build_tap_2_target(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.TAP,
        args=AtomArgs(pairs=(("target", _up_to_two_target_creatures()),)),
    )
    return EffectOutcome(effect=atom)


def _build_seq_modpt_firststrike(m: re.Match[str]) -> SentenceOutcome:
    target = Selector(
        QConst(1),
        SelectorMode.TARGET,
        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
    )
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.MODIFY_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        (
                            "power",
                            PtDelta(PtDirection.INCREASE, QConst(int(m.group(1)))),
                        ),
                        (
                            "toughness",
                            PtDelta(PtDirection.INCREASE, QConst(int(m.group(2)))),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
            Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        (
                            "ability",
                            KeywordAbility(keyword=Keyword.FIRST_STRIKE, params=()),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )
    return EffectOutcome(effect=seq)


def _build_modpt_plus(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MODIFY_PT,
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
                ("power", PtDelta(PtDirection.INCREASE, QConst(int(m.group(1))))),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(int(m.group(2))))),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_modpt_minus(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MODIFY_PT,
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
                ("power", PtDelta(PtDirection.DECREASE, QConst(int(m.group(1))))),
                ("toughness", PtDelta(PtDirection.DECREASE, QConst(int(m.group(2))))),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_seq_modpt_hexproof(m: re.Match[str]) -> SentenceOutcome:
    target = _target_creature_you_control()
    seq = Seq(
        steps=(
            Atom(
                verb=Verb.MODIFY_PT,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        (
                            "power",
                            PtDelta(PtDirection.INCREASE, QConst(int(m.group(1)))),
                        ),
                        (
                            "toughness",
                            PtDelta(PtDirection.INCREASE, QConst(int(m.group(2)))),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
            Atom(
                verb=Verb.GRANT_ABILITY,
                args=AtomArgs(
                    pairs=(
                        ("target", target),
                        (
                            "ability",
                            KeywordAbility(keyword=Keyword.HEXPROOF, params=()),
                        ),
                        ("duration", DurationEot()),
                    )
                ),
            ),
        )
    )
    return EffectOutcome(effect=seq)


def _build_modpt_x(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MODIFY_PT,
        args=AtomArgs(
            pairs=(
                ("target", _target_creature_you_control()),
                ("power", PtDelta(PtDirection.INCREASE, QX())),
                ("toughness", PtDelta(PtDirection.INCREASE, QX())),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_reveal_hand(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.REVEAL,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.TARGET_PLAYER),
                ("count", QUnbounded()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_sacr_flying(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.SACRIFICE,
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
                                FAtom(
                                    pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING
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


def _build_discard_target_2(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.DISCARD,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.TARGET_PLAYER),
                (
                    "cards",
                    Selector(
                        QConst(2),
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
    return EffectOutcome(effect=atom)


def _build_noncreature_cost_modifier(m: re.Match[str]) -> SentenceOutcome:
    """Noncreature spells cost {N} more to cast (Vryn Wingmare)."""
    modifier = CostModifier(
        filter=FNot(inner=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")),
        controller_ref=ControllerRef.ANY,
        delta=CostDeltaIncreaseGeneric(amount=QConst(int(m.group(1)))),
    )
    return AbilityOutcome(ability=modifier)


# ---------------------------------------------------------------------------
# Replacement-effect builders (grammar round 5 — doc-07 binding batch)
# ---------------------------------------------------------------------------


def _event_referent() -> Selector:
    """Convention C8: ``it`` / ``that X`` in a replacement action = the
    event subject → referent-bound selector (C2 shape: CHOOSE, QConst(1),
    neutral zone, empty zones)."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAnd(children=()),
        Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
        referent="event",
    )


def _build_repl_died_gain_life(m: re.Match[str]) -> SentenceOutcome:
    """Life Goes On: "If a creature died this turn, you gain 8 life
    instead."

    Lossy: event amount scoping dropped (LifeGainedEvent has no amount
    field) — the replacement fires on any life gain this turn.
    """
    return AbilityOutcome(
        ability=ReplacementAbility(
            event=LifeGainedEvent(controller=ControllerRef.YOU),
            condition=FAtom(pred=FAtomPred.DIED_THIS_TURN),
            action=Atom(
                verb=Verb.GAIN_LIFE,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(int(m.group(1)))),
                    )
                ),
            ),
        )
    )


def _build_repl_nontoken_enter_exile(m: re.Match[str]) -> SentenceOutcome:
    """Containment Priest: "If a nontoken creature would enter and it
    wasn't cast, exile it instead."

    Lossy: none.
    """
    return AbilityOutcome(
        ability=ReplacementAbility(
            event=ZoneChangeEvent(
                from_zone=Zone(ZoneKind.ANY, ControllerRef.ANY),
                to_zone=Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),
                subject=FAnd(
                    children=(
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        FNot(inner=FAtom(pred=FAtomPred.IS_TOKEN)),
                    )
                ),
            ),
            condition=FNot(
                inner=FAtom(pred=FAtomPred.WAS_CAST_THIS_TURN, who=ControllerRef.ANY)
            ),
            action=Atom(
                verb=Verb.EXILE,
                args=AtomArgs(pairs=(("target", _event_referent()),)),
            ),
        )
    )


def _build_repl_triple_damage(m: re.Match[str]) -> SentenceOutcome:
    """Fiery Emancipation: "If a source you control would deal damage to a
    permanent or player, it deals triple that damage to that permanent or
    player instead."

    Lossy (verbatim): recipient "a permanent or player" → universal (no
    player predicate); the replaced damage's source omitted (no source
    role on DEAL_DAMAGE).
    """
    return AbilityOutcome(
        ability=ReplacementAbility(
            event=DamageDealtEvent(
                amount=QX(),
                filter=FAnd(children=()),
                source=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            ),
            condition=None,
            action=Atom(
                verb=Verb.DEAL_DAMAGE,
                args=AtomArgs(
                    pairs=(
                        ("target", _event_referent()),
                        (
                            "amount",
                            QBin(
                                QBinOp.MUL,
                                QConst(3),
                                QProp("event", QPropField.AMOUNT),
                            ),
                        ),
                    )
                ),
            ),
        )
    )


def _build_repl_counter_plus_one(m: re.Match[str]) -> SentenceOutcome:
    """Conclave Mentor: "If one or more +1/+1 counters would be put on a
    creature you control, that many plus one +1/+1 counters are put on
    that creature instead."

    Lossy: none — "one or more" = QAtLeast(1); "that many" =
    QProp("event", COUNTER_COUNT) (grammar round 5, R5-2).
    """
    return AbilityOutcome(
        ability=ReplacementAbility(
            event=CounterPlacedEvent(
                counter_kind=CounterKind.PLUS_1_PLUS_1,
                filter=FAnd(
                    children=(
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                    )
                ),
                count=QAtLeast(1),
            ),
            condition=None,
            action=Atom(
                verb=Verb.PUT_COUNTER,
                args=AtomArgs(
                    pairs=(
                        ("target", _event_referent()),
                        ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                        (
                            "count",
                            QBin(
                                QBinOp.ADD,
                                QProp("event", QPropField.COUNTER_COUNT),
                                QConst(1),
                            ),
                        ),
                    )
                ),
            ),
        )
    )


def _build_repl_die_exile(m: re.Match[str]) -> SentenceOutcome:
    """Scorching Dragonfire: "If that creature or planeswalker would die
    this turn, exile it instead."

    Lossy (verbatim): "this turn" scoping dropped (death is a moment;
    CreatureDiesEvent has no turn-scope slot).
    """
    return AbilityOutcome(
        ability=ReplacementAbility(
            event=CreatureDiesEvent(filter=FAtom(pred=FAtomPred.IS_ANY_TARGET)),
            condition=None,
            action=Atom(
                verb=Verb.EXILE,
                args=AtomArgs(pairs=(("target", _event_referent()),)),
            ),
        )
    )


def _build_repl_graveyard_exile(m: re.Match[str]) -> SentenceOutcome:
    """Chandra, Flame's Catalyst [−2]: "If that spell would be put into
    your graveyard, exile it instead."

    Lossy (verbatim): "that spell" = the spell's target (IS_ANY_TARGET) —
    documented C6/C8.
    """
    return AbilityOutcome(
        ability=ReplacementAbility(
            event=ZoneChangeEvent(
                from_zone=Zone(ZoneKind.STACK, ControllerRef.ANY),
                to_zone=Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                subject=FAtom(pred=FAtomPred.IS_ANY_TARGET),
            ),
            condition=None,
            action=Atom(
                verb=Verb.EXILE,
                args=AtomArgs(pairs=(("target", _event_referent()),)),
            ),
        )
    )


def _build_counter_unless_pays(m: re.Match[str]) -> SentenceOutcome:
    """Lofty Denial: "If you control a creature with flying, counter that
    spell unless its controller pays {4} instead."

    Convention C7: the modifier's ``controller_ref`` referent Selector
    means the controller of the targeted spell pays the {1}→{4}
    unless-cost.

    Lossy (verbatim): "{4} instead" = +3 delta (relies on s1's {1}; same
    card) — a captured {N} compiles to the delta N-1, = 3 for the only
    concrete row.
    """
    n = int(m.group(1))
    return AbilityOutcome(
        ability=CostModifier(
            filter=FAtom(pred=FAtomPred.IS_ANY_TARGET),
            controller_ref=Selector(
                QConst(1),
                SelectorMode.CHOOSE,
                FAnd(children=()),
                Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
                referent="target",
            ),
            delta=CostDeltaIncreaseGeneric(amount=QConst(n - 1)),
            condition=FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.KEYWORD_HAS, keyword=Keyword.FLYING),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                )
            ),
        )
    )


def _build_repl_draw_not_first(m: re.Match[str]) -> SentenceOutcome:
    """Teferi's Ageless Insight: "If you would draw a card except the
    first one you draw in each of your draw steps, draw two cards
    instead."

    Lossy: none — "except the first one you draw" =
    FAtom(NOT_FIRST_DRAW_THIS_STEP, who=YOU) (grammar round 5, R5-4).
    """
    return AbilityOutcome(
        ability=ReplacementAbility(
            event=CardDrawnEvent(controller=ControllerRef.YOU),
            condition=FAtom(
                pred=FAtomPred.NOT_FIRST_DRAW_THIS_STEP, who=ControllerRef.YOU
            ),
            action=Atom(
                verb=Verb.DRAW,
                args=AtomArgs(
                    pairs=(
                        ("controller", ControllerRef.YOU),
                        ("amount", QConst(2)),
                    )
                ),
            ),
        )
    )


# ---------------------------------------------------------------------------
# Round-6 batch builders (Gadrak, Kinetic Augur — decision doc guessed b4,
# the JSON partition owns these keys in B5b)
# ---------------------------------------------------------------------------


def _build_cant_attack_unless_artifacts(m: re.Match[str]) -> SentenceOutcome:
    """Gadrak can't attack unless you control four or more artifacts.
    (Gadrak, the Crown-Scourge; C9 — the "unless" gate is
    ``StaticAbility.condition`` = FNot(CONTROLLER_COUNT_GE Artifact), never
    a duration approximation; C10 — the restriction is a PREVENT_EFFECT
    over DeclareAttackersEvent with the source as event filter (B4
    cant-block idiom).  "Gadrak" is the card self-referent (IS_SOURCE).
    The literal "four" follows the Gnarled Sage word-pinned pattern idiom.)"""
    is_source = FAtom(pred=FAtomPred.IS_SOURCE)
    atom = Atom(
        verb=Verb.PREVENT_EFFECT,
        args=AtomArgs(
            pairs=(
                ("condition", is_source),
                ("event", DeclareAttackersEvent(filter=is_source)),
            )
        ),
    )
    return AbilityOutcome(
        ability=StaticAbility(
            effect=atom,
            condition=FNot(
                inner=FAtom(
                    pred=FAtomPred.CONTROLLER_COUNT_GE,
                    inner_filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Artifact"),
                    count=QConst(4),
                )
            ),
        )
    )


def _build_set_pt_power_gy_count(m: re.Match[str]) -> SentenceOutcome:
    """Kinetic Augur's power is equal to the number of instant and sorcery
    cards in your graveyard.  (Kinetic Augur; grammar round 6 R6-3 —
    SET_PT power/toughness roles are each optional with at-least-one
    enforced, so the power-only definition carries a single role; the
    count reuses B5a's Weird-token instant-or-sorcery graveyard QCount
    shape.  Named subject = the card self-referent, IS_SOURCE.)"""
    atom = Atom(
        verb=Verb.SET_PT,
        args=AtomArgs(
            pairs=(
                ("target", _this_creature()),
                (
                    "power",
                    QCount(
                        Selector(
                            QUnbounded(),
                            SelectorMode.ALL,
                            FOr(
                                children=(
                                    FAtom(
                                        pred=FAtomPred.TYPE_EQ,
                                        string_value="Instant",
                                    ),
                                    FAtom(
                                        pred=FAtomPred.TYPE_EQ,
                                        string_value="Sorcery",
                                    ),
                                )
                            ),
                            Zone(kind=ZoneKind.GRAVEYARD, controller=ControllerRef.YOU),
                        )
                    ),
                ),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(atom))


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------

TEMPLATES: tuple[Template, ...] = (
    Template(
        tid="B5b-flash",
        name="flash keyword rule-reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Flash \(You may cast this spell any time you could cast "
            r"an instant\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_flash,
    ),
    Template(
        tid="B5b-haste",
        name="haste keyword rule-reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Haste \(This creature can attack and \{T\} as soon as it "
            r"comes under your control\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_haste,
    ),
    Template(
        tid="B5b-hexproof",
        name="hexproof keyword rule-reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Hexproof \(This creature can't be the target of spells or "
            r"abilities your opponents control\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_hexproof,
    ),
    Template(
        tid="B5b-token-demon",
        name="if you do, create a N/N black Demon token with flying",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If you do, create a (\d+)/(\d+) black Demon creature "
            r"token with flying\.$"
        ),
        priority=_PRIORITY,
        build=_build_token_demon,
    ),
    Template(
        tid="B5b-token-zombie",
        name="if you do, create a N/N black Zombie token",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If you do, create a (\d+)/(\d+) black Zombie creature "
            r"token\.$"
        ),
        priority=_PRIORITY,
        build=_build_token_zombie,
    ),
    Template(
        tid="B5b-cont-discard",
        name="if you do, discard a card",
        bucket=_BUCKET,
        pattern=re.compile(r"^If you do, discard a card\.$"),
        priority=_PRIORITY,
        build=_build_cont_discard,
    ),
    Template(
        tid="B5b-cont-draw",
        name="if you do, draw a card",
        bucket=_BUCKET,
        pattern=re.compile(r"^If you do, draw a card\.$"),
        priority=_PRIORITY,
        build=_build_cont_draw,
    ),
    Template(
        tid="B5b-seq-modpt-trample",
        name="if you do, this creature gets +N/+N and gains trample until eot",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If you do, this creature gets \+(\d+)/\+(\d+) and gains "
            r"trample until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_seq_modpt_trample,
    ),
    Template(
        tid="B5b-cont-gain-4",
        name="if you do, you gain N life",
        bucket=_BUCKET,
        pattern=re.compile(r"^If you do, you gain (\d+) life\.$"),
        priority=_PRIORITY,
        build=_build_cont_gain_4,
    ),
    Template(
        tid="B5b-cont-gain-mv",
        name="if you do, you gain life equal to that creature's mana value",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If you do, you gain life equal to that creature's mana "
            r"value\.$"
        ),
        priority=_PRIORITY,
        build=_build_cont_gain_mv,
    ),
    Template(
        tid="B5b-lifelink",
        name="lifelink keyword rule-reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Lifelink \(Damage dealt by this creature also causes you "
            r"to gain that much life\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_lifelink,
    ),
    Template(
        tid="B5b-look-3",
        name="look at the top three cards of your library",
        bucket=_BUCKET,
        pattern=re.compile(r"^Look at the top three cards of your library\.$"),
        priority=_PRIORITY,
        build=_build_look_3,
    ),
    Template(
        tid="B5b-menace",
        name="menace keyword rule-reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Menace \(This creature can't be blocked except by two or "
            r"more creatures\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_menace,
    ),
    Template(
        tid="B5b-perm-hex-ind",
        name="permanents you control gain hexproof and indestructible until eot",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Permanents you control gain hexproof and indestructible "
            r"until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_perm_hex_ind,
    ),
    Template(
        tid="B5b-prowess",
        name="prowess keyword rule-reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Prowess \(Whenever you cast a noncreature spell, this "
            r"creature gets \+\d+/\+\d+ until end of turn\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_prowess,
    ),
    Template(
        tid="B5b-put-counter",
        name="put a +N/+N counter on <target>",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Put a \+(\d+)/\+(\d+) counter on "
            r"(each creature you control|each of up to two target creatures"
            r"|target creature you control)\.$"
        ),
        priority=_PRIORITY,
        build=_build_put_counter,
    ),
    Template(
        tid="B5b-reach",
        name="reach keyword rule-reminder",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Reach \(This creature can block creatures with flying\.\)$"
        ),
        priority=_PRIORITY,
        build=_build_reach,
    ),
    Template(
        tid="B5b-return-creatures-battlefield",
        name="return target creature card from graveyard to battlefield",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Return target creature card from your graveyard to the "
            r"battlefield\.$"
        ),
        priority=_PRIORITY,
        build=_build_return_creatures_battlefield,
    ),
    Template(
        tid="B5b-return-cards-hand",
        name="return <cards> from graveyard to hand",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Return (target permanent card|up to two target creature cards) "
            r"from your graveyard to your hand\.$"
        ),
        priority=_PRIORITY,
        build=_build_return_cards_hand,
    ),
    Template(
        tid="B5b-sacr-grant",
        name="sacrifice this creature: another target creature you control gains indestructible until eot",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Sacrifice this creature: Another target creature you "
            r"control gains indestructible until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_sacr_grant,
    ),
    Template(
        tid="B5b-named-damage",
        name="<card> deals N damage to target creature or planeswalker",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^(.+) deals (\d+) damage to target creature or "
            r"planeswalker\.$"
        ),
        priority=_PRIORITY,
        build=_build_named_damage,
    ),
    Template(
        tid="B5b-scr-reveal",
        name="scry N, then reveal the top card of your library",
        bucket=_BUCKET,
        pattern=re.compile(r"^Scry (\d+), then reveal the top card of your library\.$"),
        priority=_PRIORITY,
        build=_build_scr_reveal,
    ),
    Template(
        tid="B5b-scr",
        name="scry N",
        bucket=_BUCKET,
        pattern=re.compile(r"^Scry (\d+)\.$"),
        priority=_PRIORITY,
        build=_build_scr,
    ),
    Template(
        tid="B5b-search-shuffle",
        name="search library for a card, put into hand, then shuffle",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Search your library for a card, put that card into your "
            r"hand, then shuffle\.$"
        ),
        priority=_PRIORITY,
        build=_build_search_shuffle,
    ),
    Template(
        tid="B5b-damage-any",
        name="shock deals N damage to any target",
        bucket=_BUCKET,
        pattern=re.compile(r"^Shock deals (\d+) damage to any target\.$"),
        priority=_PRIORITY,
        build=_build_damage_any,
    ),
    Template(
        tid="B5b-tap-spirits",
        name="tap two untapped spirits you control: tap target creature you don't control",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Tap two untapped Spirits you control: Tap target creature "
            r"you don't control\.$"
        ),
        priority=_PRIORITY,
        build=_build_tap_spirits,
    ),
    Template(
        tid="B5b-tap-2-target",
        name="tap up to two target creatures",
        bucket=_BUCKET,
        pattern=re.compile(r"^Tap up to two target creatures\.$"),
        priority=_PRIORITY,
        build=_build_tap_2_target,
    ),
    Template(
        tid="B5b-seq-modpt-firststrike",
        name="target creature gets +N/+N and gains first strike until eot",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Target creature gets \+(\d+)/\+(\d+) and gains first "
            r"strike until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_seq_modpt_firststrike,
    ),
    Template(
        tid="B5b-modpt-plus",
        name="target creature gets +N/+N until eot",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Target creature gets \+(\d+)/\+(\d+) until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_modpt_plus,
    ),
    Template(
        tid="B5b-modpt-minus",
        name="target creature gets -N/-N until eot",
        bucket=_BUCKET,
        pattern=re.compile(r"^Target creature gets -(\d+)/-(\d+) until end of turn\.$"),
        priority=_PRIORITY,
        build=_build_modpt_minus,
    ),
    Template(
        tid="B5b-seq-modpt-hexproof",
        name="target creature you control gets +N/+N and gains hexproof until eot",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Target creature you control gets \+(\d+)/\+(\d+) and gains "
            r"hexproof until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_seq_modpt_hexproof,
    ),
    Template(
        tid="B5b-modpt-x",
        name="target creature you control gets +X/+X until eot",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Target creature you control gets \+X/\+X until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_modpt_x,
    ),
    Template(
        tid="B5b-reveal-hand",
        name="target opponent reveals their hand",
        bucket=_BUCKET,
        pattern=re.compile(r"^Target opponent reveals their hand\.$"),
        priority=_PRIORITY,
        build=_build_reveal_hand,
    ),
    Template(
        tid="B5b-sacr-flying",
        name="target opponent sacrifices a creature of their choice with flying",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Target opponent sacrifices a creature of their choice "
            r"with flying\.$"
        ),
        priority=_PRIORITY,
        build=_build_sacr_flying,
    ),
    Template(
        tid="B5b-discard-target-2",
        name="target player discards two cards",
        bucket=_BUCKET,
        pattern=re.compile(r"^Target player discards two cards\.$"),
        priority=_PRIORITY,
        build=_build_discard_target_2,
    ),
    Template(
        tid="B5b-noncreature-cost-more",
        name="noncreature spells cost {N} more to cast",
        bucket=_BUCKET,
        pattern=re.compile(r"^Noncreature spells cost \{(\d+)\} more to cast\.$"),
        priority=_PRIORITY,
        build=_build_noncreature_cost_modifier,
    ),
    Template(
        tid="B5b-return-spell-creature-owner-hand",
        name="return target spell or creature to its owner's hand",
        bucket=_BUCKET,
        pattern=re.compile(r"^Return target spell or creature to its owner's hand\.$"),
        priority=_PRIORITY,
        build=_build_return_spell_creature_owner_hand,
    ),
    Template(
        tid="B5b-repl-died-gain-life",
        name="if a creature died this turn, you gain N life instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If a creature died this turn, you gain (\d+) life instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_repl_died_gain_life,
    ),
    Template(
        tid="B5b-repl-nontoken-enter-exile",
        name="if a nontoken creature would enter and it wasn't cast, exile it instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If a nontoken creature would enter and it wasn't cast, "
            r"exile it instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_repl_nontoken_enter_exile,
    ),
    Template(
        tid="B5b-repl-triple-damage",
        name="a source you control deals triple damage instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If a source you control would deal damage to a permanent or "
            r"player, it deals triple that damage to that permanent or "
            r"player instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_repl_triple_damage,
    ),
    Template(
        tid="B5b-repl-counter-plus-one",
        name="that many plus one +1/+1 counters are put instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If one or more \+1/\+1 counters would be put on a creature "
            r"you control, that many plus one \+1/\+1 counters are put on "
            r"that creature instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_repl_counter_plus_one,
    ),
    Template(
        tid="B5b-repl-die-exile",
        name="if that creature or planeswalker would die this turn, exile it instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If that creature or planeswalker would die this turn, "
            r"exile it instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_repl_die_exile,
    ),
    Template(
        tid="B5b-repl-graveyard-exile",
        name="if that spell would be put into your graveyard, exile it instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If that spell would be put into your graveyard, "
            r"exile it instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_repl_graveyard_exile,
    ),
    Template(
        tid="B5b-counter-unless-pays",
        name="counter that spell unless its controller pays {N} instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If you control a creature with flying, counter that spell "
            r"unless its controller pays \{(\d+)\} instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_counter_unless_pays,
    ),
    Template(
        tid="B5b-repl-draw-not-first",
        name="if you would draw a card except the first this step, draw two instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If you would draw a card except the first one you draw in "
            r"each of your draw steps, draw two cards instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_repl_draw_not_first,
    ),
    Template(
        tid="B5b-gadrak-cant-attack-unless-artifacts",
        name="Gadrak can't attack unless you control four or more artifacts",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Gadrak can't attack unless you control four or more "
            r"artifacts\.$"
        ),
        priority=_PRIORITY,
        build=_build_cant_attack_unless_artifacts,
    ),
    Template(
        tid="B5b-set-pt-power-gy-instant-sorcery",
        name="named creature's power equals instant+sorcery count in your graveyard",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Kinetic Augur's power is equal to the number of instant and "
            r"sorcery cards in your graveyard\.$"
        ),
        priority=_PRIORITY,
        build=_build_set_pt_power_gy_count,
    ),
)

UNCOVERED: tuple[tuple[str, str], ...] = (
    (
        "Flying, first strike, lifelink, protection from Demons and from Dragons",
        "Composite keyword list with protection-from-subtypes",
    ),
    (
        "Gain control of target creature until end of turn.",
        "GAIN_CONTROL has no duration role - 'until end of turn' inexpressible",
    ),
    (
        "If a creature died this turn, create two N/N green Saproling creature tokens.",
        "Conditional token creation on creature-death trigger",
    ),
    (
        "If a source would deal damage to you, prevent that damage and put an incarnation counter on this enchantment.",
        "Prevent-damage-and-put-counter replacement",
    ),
    (
        "If an ability of another Shrine you control triggers while you control six or more Shrines, that ability triggers an additional time.",
        "Additional trigger with shrine-count gate",
    ),
    (
        "If it was a creature card, put a +N/+N counter on this creature and you gain N life.",
        "Conditional counter-and-gain-life with anaphoric 'it'",
    ),
    (
        "If it's a creature card, put it into your hand.",
        "Conditional zone-move with anaphoric 'it'",
    ),
    (
        "If it's a creature or land card, draw a card.",
        "Conditional draw with anaphoric 'it'",
    ),
    (
        "If this spell was cast from anywhere other than your hand, put each of those cards into your hand instead.",
        "Conditional zone-move with anaphoric 'those cards'",
    ),
    (
        "If you search your library this way, shuffle.",
        "Conditional shuffle on library-search trigger",
    ),
    (
        "If you win the flip, you gain N life.",
        "Conditional life-gain on coin-flip outcome",
    ),
    (
        "It gains haste until end of turn.",
        "Anaphoric 'It' keyword grant with duration",
    ),
    (
        "It gains haste.",
        "Anaphoric 'It' keyword grant without duration",
    ),
    (
        'It gains haste."',
        "Anaphoric 'It' keyword grant with trailing quote",
    ),
    (
        "It gains indestructible until end of turn.",
        "Anaphoric 'It' keyword grant (indestructible) with duration",
    ),
    (
        "It gains protection from the color of your choice until end of turn.",
        "Anaphoric 'It' protection-from-color-choice grant",
    ),
    (
        "It gains vigilance until end of turn.",
        "Anaphoric 'It' keyword grant (vigilance) with duration",
    ),
    (
        "Its controller creates a N/N white Angel creature token with flying.",
        "Controller-referent token creation with anaphoric 'Its'",
    ),
    (
        "Its controller creates a N/N white Soldier creature token.",
        "Controller-referent token creation with anaphoric 'Its'",
    ),
    (
        "Its controller loses N life.",
        "Controller-referent life-loss with anaphoric 'Its'",
    ),
    (
        "Otherwise, put it on the bottom of your library.",
        "Anaphoric 'it' zone-move (conditional branch)",
    ),
    (
        "Play with the top card of your library revealed.",
        "No top-card-revealed-play-state grammar construct",
    ),
    (
        "Put a +N/+N counter on target creature you control, then double the number of +N/+N counters on that creature.",
        "Counter-placement with follow-up doubling (multi-step counter)",
    ),
    (
        "Put one of them into your hand and the other into your graveyard.",
        "Anaphoric 'them' split zone-move (hand + graveyard)",
    ),
    (
        "Put one of those cards into your hand and the rest on the bottom of your library in any order.",
        "Anaphoric 'those cards' split zone-move with bottom-shuffle",
    ),
    (
        "Put the rest on the bottom of your library in a random order.",
        "Anaphoric 'the rest' random-order bottom-shuffle",
    ),
    (
        "Reach, hexproof from blue",
        "Composite keyword with colored hexproof variant",
    ),
    (
        "Round up each time.",
        "Anaphoric 'each time' rounding instruction",
    ),
    (
        "Search target opponent's graveyard, hand, and library for any number of cards with that name and exile them.",
        "Multi-zone search-and-exile with name anaphora",
    ),
    (
        "Search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped and the other into your hand, then shuffle.",
        "Complex tutor with reveal, split-zone, and shuffle",
    ),
    (
        "Spend this mana only to cast an instant or sorcery spell.",
        "No mana-restriction grammar construct",
    ),
    (
        "Target creature gets +N/+N and gains your choice of deathtouch or lifelink until end of turn.",
        "Keyword-choice grant with anaphoric 'your choice'",
    ),
    (
        "Target player draws cards equal to half the number of cards in their library and loses half their life.",
        "Half-library draw with half-life loss (fractional computation)",
    ),
    (
        "That creature's controller reveals cards from the top of their library until they reveal a creature card.",
        "Anaphoric controller reveal-until-creature (search-until)",
    ),
    (
        "That permanent loses indestructible until end of turn.",
        "Anaphoric 'That permanent' keyword-loss with duration",
    ),
    (
        "That player discards that card.",
        "Anaphoric 'That player' / 'that card' discard (modal continuation)",
    ),
    (
        "That player puts that card onto the battlefield, then shuffles the rest into their library.",
        "Anaphoric zone-move with shuffle-remainder (modal continuation)",
    ),
    (
        "That player shuffles, then creates a N/N black Zombie creature token for each card exiled from their hand this way.",
        "Anaphoric shuffle + per-card token creation (modal continuation)",
    ),
    (
        "Then if an opponent controls more creatures than you, put a loyalty counter on Garruk.",
        "Conditional loyalty-counter with opponent-creature-count gate",
    ),
)
