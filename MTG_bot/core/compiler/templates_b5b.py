"""B5b bucket templates — 79 templates covering 88 of 90 B5b shapes.

Bucket input: ``/tmp/opencode/phase1_buckets/B5b.json`` (90 normalized shape
keys → ``[card, sentence]`` pairs; sentences carry *concrete* numbers, keys
carry ``N`` placeholders).  Templates fullmatch the **concrete** oracle
sentence, never the normalized key.

Coverage (90 = 88 template + 0 rule-reminder + 2 uncovered):

- **84 template-covered shapes** (75 templates: 57 single-shape tids +
  5 multi-shape normalized tids — put-counter ×3, return-cards-hand ×2,
  named-damage ×2, it-gains-kw-eot ×3, if-it-type-then ×2;
  ``B5b-modpt-plus`` is one shape with two concrete rows):
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
  QCount(GY instant-or-sorcery) — grammar round 6 R6-3), and the grammar
  round-7 anaphora batch (doc 2026-09-28/03 §3 R7-A): result-referent
  grants ("It gains …"), the Duress choose/discard chain, the Garruk
  If-it's/Otherwise Conditional pair, Necromentia's choose-name →
  search-by-name → per-exile-token chain, ONE_OF/REST split moves
  (Waker of Waves, See the Truth, Garruk's Harbinger, Cultivate), the
  cast-elsewhere Conditional, LOSE_ABILITY (Soul Sear) and
  GAIN_CONTROL's new duration role (Traitorous Greed) and the grammar
  round-8-C coverage batch (doc 2026-09-28/08 §8-C): Scavenging Ooze's
  C18 was-type Conditional, Peer into the Abyss's round-up-half library
  draw (+ the rounding-directive marker row), Invigorating Surge's
  counter-doubling (QProp COUNTER_COUNT referent=target, R8-11), Garruk
  Unleashed's CONTROLLER_COUNT_GT loyalty gate (R8-9) and the
  ``It gains haste."`` emblem-quote residue marker (C19 — payload lives
  in the emblem attach).
- **0 rule-reminder shapes** — no fully-parenthesised sentences in B5b.
- **2 uncovered shapes** — Sanctum-of-All's additional-trigger gate and
  the search-shuffle boilerplate note (compiler built-in, recorded not
  template-driven).  Round 11 C3 retired Transmogrify's reveal-until dig
  (deferred D14) as a top-of-library SEARCH + TARGET_PLAYER SHUFFLE pair.
  Recorded in ``UNCOVERED`` below and pinned by tests.

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
- Token colors: the printed color word populates ``TokenSpec.color``
  (shapes #21, #22 — round 8 / C-2 repair).
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
from typing import Final

from MTG_bot.core.ability_tree import (
    QX,
    ActivatedAbility,
    Atom,
    AtomArgs,
    CardDrawnEvent,
    Choose,
    Conditional,
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
    DurationPermanent,
    Effect,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    LifeGainedEvent,
    PtDelta,
    PtDirection,
    QAgg,
    QAtLeast,
    QAtMost,
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
    ZonePosition,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    KeywordOutcome,
    RuleReminderOutcome,
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
    """Selector for ``up to two target creatures``.

    Grammar round 8 / C17: targeted "up to N" is TARGET + QAtMost(N)
    (designation 1..2; resolution 0..2) — CHOOSE-for-targeted erases the
    legal-target distribution (C15), so this replaces the interim CHOOSE
    convention from the R7 batches.  Used by "Put a +1/+1 counter on each
    of up to two target creatures" and "Tap up to two target creatures".
    """
    return Selector(
        QAtMost(2),
        SelectorMode.TARGET,
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
    """Selector for ``up to two target creature cards from your graveyard``.

    TARGET + QAtMost(2) per C17 (round 8) — targeted designation 1..2 from
    the graveyard, same collapse repair as _up_to_two_target_creatures.
    """
    return Selector(
        QAtMost(2),
        SelectorMode.TARGET,
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
    """Selector for ``any target`` (the r17-2 idiom).

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
        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
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
                        color="B",  # C-2 repair (round 8): printed "black"
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
                        color="B",  # C-2 repair (round 8): printed "black"
                    ),
                ),
                ("count", QConst(1)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_cont_discard(m: re.Match[str]) -> SentenceOutcome:
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)),
                ("from", Zone(ZoneKind.HAND, ControllerRef.YOU)),
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
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.TARGET_PLAYER)),
                ("from", Zone(ZoneKind.HAND, ControllerRef.TARGET_PLAYER)),
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
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                        ("target", _event_referent()),
                    )
                ),
            ),
        )
    )


def _build_repl_triple_damage(m: re.Match[str]) -> SentenceOutcome:
    """Fiery Emancipation: "If a source you control would deal damage to a
    permanent or player, it deals triple that damage to that permanent or
    player instead."

    Lossy (verbatim): the EVENT recipient "a permanent or player" →
    universal (no player predicate on the event filter).  Faithful since
    round 8 (C-4 repair): the replacement DEAL_DAMAGE atom carries
    dealer=FAtom(CONTROLLER_IS, YOU) — the printed "a source you control"
    dealer side, the 8-A R8-5 dealer role vocabulary; "to that permanent
    or player" rides the event-referent target selector as before.
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
                        # dealer = "a source you control" (R8-5 role)
                        (
                            "dealer",
                            FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                        ),
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
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                        ("target", _event_referent()),
                    )
                ),
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
                verb=Verb.MOVE_ZONE,
                args=AtomArgs(
                    pairs=(
                        ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                        ("target", _event_referent()),
                    )
                ),
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
# Grammar round-7 batch builders (family-2 anaphora — doc 2026-09-28/03 §3)
# ---------------------------------------------------------------------------

_KW_GAIN: dict[str, Keyword] = {
    "indestructible": Keyword.INDESTRUCTIBLE,
    "haste": Keyword.HASTE,
    "vigilance": Keyword.VIGILANCE,
}

_KW_LOSE: dict[str, Keyword] = {
    "indestructible": Keyword.INDESTRUCTIBLE,
}

# C15 (doc 2026-09-28/05): "protection from the color of your choice" is
# a controller decision — it is expanded into the game's five color options
# as an explicit Choose node instead of defaulting one color (the C-3
# colorless-conflation is exactly what C15 forbids in new templates).
_COLORS_WUBRG: tuple[str, ...] = ("W", "U", "B", "R", "G")


_UNIVERSAL: Final[Filter] = FAnd(children=())


def _result_selector(filter: Filter | None = None) -> Selector:
    """Grammar round 7 (R7-1): the anaphoric ``it`` / ``that card`` /
    ``them`` — the object(s) the previous sentence acted on (revealed /
    chosen / exiled / moved).  ``referent="result"`` (C12: the result
    register is compiler state, never an English antecedent); the neutral
    zone mirrors the r8 round-trip canonical selector."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        filter if filter is not None else _UNIVERSAL,
        Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
        referent="result",
    )


def _looked_top_library(filter: Filter | None = None) -> Selector:
    """The set the previous "Look at the top N cards" sentence exposed:
    still on top of your library, so the zone is typed rather than a
    result referent (r8 ONE_OF/REST canonical)."""
    return Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        filter if filter is not None else _UNIVERSAL,
        Zone(
            kind=ZoneKind.LIBRARY,
            controller=ControllerRef.YOU,
            position=ZonePosition.TOP,
        ),
    )


def _build_it_gains_kw_eot(m: re.Match[str]) -> SentenceOutcome:
    """``It gains <kw> until end of turn.`` (Basri Ket, Seasoned
    Hallowblade, Basri Devoted Paladin, Traitorous Greed) — GRANT_ABILITY
    onto the result-referent object with the EOT duration (R7-1)."""
    kw = _KW_GAIN[m.group("kw")]
    atom = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", _result_selector()),
                ("ability", KeywordAbility(keyword=kw)),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_it_gains_haste(m: re.Match[str]) -> SentenceOutcome:
    """``It gains haste.`` (Liliana Waker emblem) — grant with NO
    duration: the emblem's put-onto-battlefield continuation grants
    permanently."""
    atom = Atom(
        verb=Verb.GRANT_ABILITY,
        args=AtomArgs(
            pairs=(
                ("target", _result_selector()),
                ("ability", KeywordAbility(keyword=Keyword.HASTE)),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_it_gains_protection_choice(m: re.Match[str]) -> SentenceOutcome:
    """``It gains protection from the color of your choice until end of
    turn.`` (Feat of Resistance) — C15: the color is a controller
    decision, so the grant is an explicit one-of-five Choose over
    color-parameterized PROTECTION grants; nothing is defaulted."""
    options = tuple(
        Atom(
            verb=Verb.GRANT_ABILITY,
            args=AtomArgs(
                pairs=(
                    ("target", _result_selector()),
                    (
                        "ability",
                        KeywordAbility(
                            keyword=Keyword.PROTECTION,
                            params=(FAtom(pred=FAtomPred.COLOR_HAS, color=color),),
                        ),
                    ),
                    ("duration", DurationEot()),
                )
            ),
        )
        for color in _COLORS_WUBRG
    )
    return EffectOutcome(effect=Choose(count=QConst(1), options=options))


def _build_that_player_discards_that_card(m: re.Match[str]) -> SentenceOutcome:
    """``That player discards that card.`` (Duress s3) — the player is the
    spell's targeted opponent (TARGET_PLAYER role); the card is the card
    the previous CHOOSE picked off the revealed hand → referent="result"
    (R7-1; antecedent ``B4-you-choose-from-it`` is in this batch)."""
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.TARGET_PLAYER)),
                ("from", Zone(ZoneKind.HAND, ControllerRef.TARGET_PLAYER)),
                ("controller", ControllerRef.TARGET_PLAYER),
                ("cards", _result_selector()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_if_it_type_then(m: re.Match[str]) -> SentenceOutcome:
    """``If it's a creature [or land] card, ...`` (Garruk Savage Herald
    s2, Track Down s2) — Conditional whose subject is the previous
    sentence's revealed card (result register; FAtom rules keep the
    referent slot closed to IS_ATTACHED_TO, so the condition's subject is
    the register by executor convention, and the MOVED card itself is the
    referent="result" selector)."""
    then = m.group("then")
    if then == "draw a card":
        if m.group("or_land") is None:
            raise ValueError(
                "B5b-if-it-type-then: bare-creature draw branch is not a"
                " printed sentence shape (pattern over-matched)"
            )
        pred: Filter = FOr(
            children=(
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land"),
            )
        )
        effect: Effect = Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(("controller", ControllerRef.YOU), ("amount", QConst(1)))
            ),
        )
    else:
        if m.group("or_land") is not None:
            raise ValueError(
                "B5b-if-it-type-then: or-land hand-move branch is not a"
                " printed sentence shape (pattern over-matched)"
            )
        pred = FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
        effect = Atom(
            verb=Verb.MOVE_ZONE,
            args=AtomArgs(
                pairs=(
                    ("cards", _result_selector()),
                    ("destination", Zone(ZoneKind.HAND, ControllerRef.YOU)),
                )
            ),
        )
    return EffectOutcome(effect=Conditional(pred=pred, then_effect=effect))


def _build_otherwise_bottom(m: re.Match[str]) -> SentenceOutcome:
    """``Otherwise, put it on the bottom of your library.`` (Garruk
    Savage Herald s3) — the compiler's ``_merge_otherwise`` attaches this
    effect as the preceding Conditional's ``else_effect`` (R7-3); the
    moved card is again the result referent."""
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("cards", _result_selector()),
                (
                    "destination",
                    Zone(
                        ZoneKind.LIBRARY,
                        ControllerRef.YOU,
                        position=ZonePosition.BOTTOM,
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_search_name_exile(m: re.Match[str]) -> SentenceOutcome:
    """``Search target opponent's graveyard, hand, and library for any
    number of cards with that name and exile them.`` (Necromentia s2) —
    the name filter is the CHOOSE_NAME read-back (R7-4); "any number" is
    the unbounded CHOOSE quantity choice (C15: 0..∞ preserved, not a
    defaulted count).  The found cards then leave via EXILE on the result
    referent."""
    search = Atom(
        verb=Verb.SEARCH,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QUnbounded(),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.NAME_CHOSEN),
                        Zone(ZoneKind.GRAVEYARD, ControllerRef.TARGET_PLAYER),
                        zones=(
                            Zone(ZoneKind.HAND, ControllerRef.TARGET_PLAYER),
                            Zone(ZoneKind.LIBRARY, ControllerRef.TARGET_PLAYER),
                        ),
                    ),
                ),
                ("destination", Zone(ZoneKind.EXILE, ControllerRef.TARGET_PLAYER)),
                ("controller", ControllerRef.TARGET_PLAYER),
            )
        ),
    )
    exile = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("destination", Zone(ZoneKind.EXILE, ControllerRef.OWNER)),
                ("target", _result_selector()),
            )
        ),
    )
    return EffectOutcome(effect=Seq(steps=(search, exile)))


def _build_shuffle_then_token_per_exiled(m: re.Match[str]) -> SentenceOutcome:
    """``That player shuffles, then creates a P/T black Zombie creature
    token for each card exiled from their hand this way.`` (Necromentia
    s3) — SHUFFLE + CREATE_TOKEN.  R11-4a: the count is a scoped
    QCount(exiled cards named <chosen> that moved HAND→EXILE under the
    target this turn), NOT the R7-5 THIS_WAY_COUNT tally (which counted
    graveyard/hand/library exiles alike).
    Faithful since round 8: TokenSpec.color="B" carries "black" (C-2
    repair).  Remaining lossy (verbatim): the creating player ("that
    player") has no CREATE_TOKEN controller role, so the creator is
    implicit."""
    token = TokenSpec(
        name="Zombie",
        type_line="Creature — Zombie",
        types=("Creature",),
        subtypes=("Zombie",),
        power=QConst(int(m.group("p"))),
        toughness=QConst(int(m.group("t"))),
        keywords=(),
        abilities=(),
        color="B",  # C-2 repair (round 8)
    )
    shuffle = Atom(
        verb=Verb.SHUFFLE,
        args=AtomArgs(
            pairs=(("zone", Zone(ZoneKind.LIBRARY, ControllerRef.TARGET_PLAYER)),)
        ),
    )
    # R11-4a: the count is "each card exiled FROM THEIR HAND this way" —
    # cards in the target's exile zone that carry the chosen name AND moved
    # hand→exile this turn under the target's control.  A bare
    # QProp(THIS_WAY_COUNT) tallied the whole search (graveyard/hand/library
    # combined), over-creating tokens for non-hand exiles.
    hand_exiles = Selector(
        QUnbounded(),
        SelectorMode.ALL,
        FAnd(
            children=(
                FAtom(pred=FAtomPred.NAME_CHOSEN),
                FAtom(
                    pred=FAtomPred.MOVED_TO_ZONE_THIS_TURN,
                    from_zone=Zone(ZoneKind.HAND, ControllerRef.TARGET_PLAYER),
                    to_zone=Zone(ZoneKind.EXILE, ControllerRef.TARGET_PLAYER),
                    who=ControllerRef.TARGET_PLAYER,
                ),
            )
        ),
        Zone(kind=ZoneKind.EXILE, controller=ControllerRef.TARGET_PLAYER),
    )
    create = Atom(
        verb=Verb.CREATE_TOKEN,
        args=AtomArgs(
            pairs=(
                ("tokens", token),
                ("count", QCount(hand_exiles)),
            )
        ),
    )
    return EffectOutcome(effect=Seq(steps=(shuffle, create)))


def _build_that_permanent_loses_kw(m: re.Match[str]) -> SentenceOutcome:
    """``That permanent loses <kw> until end of turn.`` (Soul Sear s2) —
    Verb.LOSE_ABILITY mirrors GRANT_ABILITY's roles (R7-9a).
    DECISION: "That permanent" is the spell's damaged target → R4
    referent="target" (binds the s0 TARGET selector today), not the
    round-7 result register — the deviation from the spec sketch is
    deliberate and documented (target-vocabulary anaphora binds without
    the register machinery)."""
    kw = _KW_LOSE[m.group("kw")]
    atom = Atom(
        verb=Verb.LOSE_ABILITY,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAnd(children=()),
                        Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
                        referent="target",
                    ),
                ),
                ("ability", KeywordAbility(keyword=kw)),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_one_of_other(m: re.Match[str]) -> SentenceOutcome:
    """``Put one of them into your hand and the other into your
    graveyard.`` (Waker of Waves s3) — the ONE_OF/REST split pair
    (R7-7): exactly one of the looked-at set to hand, everything
    remaining ("the other", here exactly one) to the graveyard."""
    to_hand = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.ONE_OF,
                        FAnd(children=()),
                        _looked_top_library().zone,
                    ),
                ),
                ("destination", Zone(ZoneKind.HAND, ControllerRef.YOU)),
            )
        ),
    )
    to_graveyard = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.REST,
                        FAnd(children=()),
                        _looked_top_library().zone,
                    ),
                ),
                ("destination", Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU)),
            )
        ),
    )
    return EffectOutcome(effect=Seq(steps=(to_hand, to_graveyard)))


def _build_one_of_rest_bottom(m: re.Match[str]) -> SentenceOutcome:
    """``Put one of those cards into your hand and the rest on the bottom
    of your library in any order.`` (See the Truth s2) — ONE_OF/REST
    again; the destination order ("in any order") is controller-chosen
    ordering with no ordering field in the grammar — dropped, documented."""
    to_hand = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.ONE_OF,
                        FAnd(children=()),
                        _looked_top_library().zone,
                    ),
                ),
                ("destination", Zone(ZoneKind.HAND, ControllerRef.YOU)),
            )
        ),
    )
    to_bottom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.REST,
                        FAnd(children=()),
                        _looked_top_library().zone,
                    ),
                ),
                (
                    "destination",
                    Zone(
                        ZoneKind.LIBRARY,
                        ControllerRef.YOU,
                        position=ZonePosition.BOTTOM,
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=Seq(steps=(to_hand, to_bottom)))


def _build_rest_bottom_random(m: re.Match[str]) -> SentenceOutcome:
    """``Put the rest on the bottom of your library in a random order.``
    (Garruk's Harbinger s3) — REST over the looked-at top cards.
    LOSSY: "in a random order" — the destination has no ordering field
    (SelectorMode.RANDOM would replace REST, not order it); dropped,
    documented."""
    atom = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.REST,
                        FAnd(children=()),
                        _looked_top_library().zone,
                    ),
                ),
                (
                    "destination",
                    Zone(
                        ZoneKind.LIBRARY,
                        ControllerRef.YOU,
                        position=ZonePosition.BOTTOM,
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=atom)


def _build_cultivate_search(m: re.Match[str]) -> SentenceOutcome:
    """``Search your library for up to two basic land cards, reveal those
    cards, put one onto the battlefield tapped and the other into your
    hand, then shuffle.`` (Cultivate) — "up to two" is CHOOSE+QConst(2)
    (C15: the 0/1/2 sub-choice stays open); the split is ONE_OF (BF,
    tapped) + REST (hand); the inline "then shuffle" is the same
    search-shuffle step ``_build_search_shuffle`` builds.
    LOSSY: REVEAL counts the searched cards with an unbounded count — the
    grammar cannot reference the found set (b2b's documented REVEAL
    limitation)."""
    search = Atom(
        verb=Verb.SEARCH,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(2),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.SUPERTYPE_EQ, string_value="Basic"),
                        Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
                    ),
                ),
                ("destination", Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)),
                ("controller", ControllerRef.YOU),
            )
        ),
    )
    reveal = Atom(
        verb=Verb.REVEAL,
        args=AtomArgs(
            pairs=(("controller", ControllerRef.YOU), ("count", QUnbounded()))
        ),
    )
    to_bf = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.ONE_OF,
                        FAtom(pred=FAtomPred.SUPERTYPE_EQ, string_value="Basic"),
                        Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
                    ),
                ),
                ("destination", Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU)),
                ("tapped_on_enter", True),
            )
        ),
    )
    to_hand = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.REST,
                        FAtom(pred=FAtomPred.SUPERTYPE_EQ, string_value="Basic"),
                        Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
                    ),
                ),
                ("destination", Zone(ZoneKind.HAND, ControllerRef.YOU)),
            )
        ),
    )
    shuffle = Atom(
        verb=Verb.SHUFFLE,
        args=AtomArgs(pairs=(("zone", Zone(ZoneKind.LIBRARY, ControllerRef.YOU)),)),
    )
    return EffectOutcome(effect=Seq(steps=(search, reveal, to_bf, to_hand, shuffle)))


def _build_transmog_reveal_creature(m: re.Match[str]) -> SentenceOutcome:
    """``That creature's controller reveals cards from the top of their
    library until they reveal a creature card.`` (Transmogrify s2, grammar
    round 11 C3 — the deferred D14 reveal-until dig retired: encoded as a
    top-of-library creature CHOOSE search.  ``ZonePosition.TOP`` enumerates
    exactly the library top (the r8 ``_looked_top_library`` canonical,
    ``entries[-1:]``), so CHOOSE can never reach a deeper card and never a
    bottom-of-library draw; ``ControllerRef.TARGET_PLAYER`` carries "that
    creature's controller" (bound by the s1 exile's target).
    DIVERGENCE: a non-creature top card finds nothing instead of scanning
    deeper — the grammar has no reveal-until iterator; documented.  The
    literal REVEAL is the SEARCH verb's built-in disclosure (b2b
    convention)."""
    search = Atom(
        verb=Verb.SEARCH,
        args=AtomArgs(
            pairs=(
                (
                    "cards",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        Zone(
                            kind=ZoneKind.LIBRARY,
                            controller=ControllerRef.TARGET_PLAYER,
                            position=ZonePosition.TOP,
                        ),
                    ),
                ),
                (
                    "destination",
                    Zone(ZoneKind.BATTLEFIELD, ControllerRef.TARGET_PLAYER),
                ),
                ("controller", ControllerRef.TARGET_PLAYER),
            )
        ),
    )
    return EffectOutcome(effect=search)


def _build_transmog_shuffle_rest(m: re.Match[str]) -> SentenceOutcome:
    """``That player puts that card onto the battlefield, then shuffles the
    rest into their library.`` (Transmogrify s3, grammar round 11 C3 — the
    put-half rides s2's SEARCH destination (the grammar cannot name "that
    card" across the reveal-until; documented lossless-split convention);
    the remaining emission is the remainder SHUFFLE, TARGET_PLAYER-owned so
    the anaphoric "That player" reads the s1-exile target binding (the
    Vodalian ``Zone(LIBRARY, TARGET_PLAYER)`` shuffle precedent).  Neither
    sentence carries a continuation prefix: card assembly folds the
    instant's three plain effects into one ``Seq`` (multi-effect fold)."""
    shuffle = Atom(
        verb=Verb.SHUFFLE,
        args=AtomArgs(
            pairs=(
                (
                    "zone",
                    Zone(
                        kind=ZoneKind.LIBRARY,
                        controller=ControllerRef.TARGET_PLAYER,
                    ),
                ),
            )
        ),
    )
    return EffectOutcome(effect=shuffle)


def _build_cast_elsewhere_instead(m: re.Match[str]) -> SentenceOutcome:
    """``If this spell was cast from anywhere other than your hand, put
    each of those cards into your hand instead.`` (See the Truth s3) —
    Conditional on the cast-zone read-back (CAST_THIS_TURN_FROM, negated
    for "anywhere other than your hand") moving the whole result set to
    hand.
    LOSSY: "instead" — the grammar has no branch-exclusion marker, so the
    Conditional is a sibling step of the normal one-and-rest split
    sequence rather than a replacement of it; documented (the R5
    ReplacementAbility carrier is event-shaped, not cast-zone-shaped).
    "Each of those cards" rides the C2 canonical referent selector —
    referent selectors are pinned to CHOOSE/QConst(1)/neutral-zone, so the
    register's plurality is applied per object executor-side."""
    cond = FNot(
        inner=FAtom(
            pred=FAtomPred.CAST_THIS_TURN_FROM,
            zone=Zone(ZoneKind.HAND, ControllerRef.YOU),
            who=ControllerRef.YOU,
        )
    )
    move = Atom(
        verb=Verb.MOVE_ZONE,
        args=AtomArgs(
            pairs=(
                ("cards", _result_selector()),
                ("destination", Zone(ZoneKind.HAND, ControllerRef.YOU)),
            )
        ),
    )
    return EffectOutcome(effect=Conditional(pred=cond, then_effect=move))


def _build_gain_control_eot(m: re.Match[str]) -> SentenceOutcome:
    """``Gain control of target creature until end of turn.`` (Traitorous
    Greed s1) — GAIN_CONTROL's optional duration role (R7-2,
    ``_VERB_ROLES`` row extended by the grammar phase)."""
    atom = Atom(
        verb=Verb.GAIN_CONTROL,
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
                ("controller", ControllerRef.YOU),
                ("duration", DurationEot()),
            )
        ),
    )
    return EffectOutcome(effect=atom)


# ---------------------------------------------------------------------------
# Grammar round-7-B batch builders (doc 2026-09-28/03 §3, R7-B top-ups)
# ---------------------------------------------------------------------------


def _build_keyword_list_params(m: re.Match[str]) -> SentenceOutcome:
    """``Flying, first strike, lifelink, protection from Demons and from
    Dragons`` (Baneslayer Angel) and ``Reach, hexproof from blue``
    (Sporeweb Weaver) — keyword-list sentences carrying one parameterized
    member that ``_KEYWORDS_BARE_UNBUILDABLE`` proves cannot be built from
    the bare identity string (PROTECTION needs a Filter, and HEXPROOF's
    second ``_KEYWORD_PARAMS`` signature takes one).  The template emits
    ONLY the parameterized member: the bare members (Flying / First
    strike / Lifelink / Reach) already arrive via ``raw.keywords`` and the
    compiler's keyword-dedup merge keeps one copy each, so the card ends
    complete.  Baneslayer's protection filter is the OR of the two named
    creature subtypes (SUBTYPE_EQ is singular, Equipment precedent);
    Sporeweb's hexproof filter is COLOR_HAS blue (Feat-of-Resistance
    param shape).  Lossy (verbatim): Scryfall's keyword field lists bare
    'Hexproof' beside 'Hexproof from' for Sporeweb Weaver, so the card
    also carries the parameterless HEXPROOF the bare path builds — a
    keyword-field artifact, not a template choice.  C16: none — forced
    static grants."""
    if m.group("form").startswith("Flying"):
        return KeywordOutcome(
            keyword=Keyword.PROTECTION,
            params=(
                FOr(
                    children=(
                        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Demon"),
                        FAtom(pred=FAtomPred.SUBTYPE_EQ, string_value="Dragon"),
                    )
                ),
            ),
        )
    return KeywordOutcome(
        keyword=Keyword.HEXPROOF,
        params=(FAtom(pred=FAtomPred.COLOR_HAS, color="U"),),
    )


def _build_if_died_two_tokens(m: re.Match[str]) -> SentenceOutcome:
    """``If a creature died this turn, create two 1/1 green Saproling
    creature tokens.`` (Fungal Rebirth s2) — Conditional over the
    turn-scoped DIED_THIS_TURN atom (resolution-time check, not a
    trigger), then CREATE_TOKEN.  C14: the spelled-out ``two`` is outside
    the number regex, so the count is word-pinned ``QConst(2)`` (Gnarled
    Sage house idiom).  The sentence carries no continuation prefix, so
    the instant's effect fold appends it as the sibling step after s1
    (already landed).  Faithful since round 8: TokenSpec.color="G" carries
    ``green`` (C-2 repair).  C16: none — fully forced."""
    token = TokenSpec(
        name="Saproling",
        type_line="Creature — Saproling",
        types=("Creature",),
        subtypes=("Saproling",),
        power=QConst(1),
        toughness=QConst(1),
        keywords=(),
        abilities=(),
        color="G",  # C-2 repair (round 8)
    )
    return EffectOutcome(
        effect=Conditional(
            pred=FAtom(pred=FAtomPred.DIED_THIS_TURN),
            then_effect=Atom(
                verb=Verb.CREATE_TOKEN,
                args=AtomArgs(pairs=(("tokens", token), ("count", QConst(2)))),
            ),
        )
    )


def _build_would_damage_incarnation(m: re.Match[str]) -> SentenceOutcome:
    """``If a source would deal damage to you, prevent that damage and put
    an incarnation counter on this enchantment.`` (Nine Lives) —
    ReplacementAbility over DamageDealtEvent (r5 landed pattern: Life
    Goes On / Containment Priest / Conclave Mentor).
    ``source=None`` IS the printed universal ``a source`` — no narrowing
    (the mission's flagged lossy candidate stays faithful).
    Faithful since round 8 (C-4 damage-surface repair, R8-5 vocabulary):
    the event filter — which names the DAMAGED object — carries
    ``FAtom(CONTROLLER_IS, who=YOU)``, restoring the printed ``to you``
    recipient (the player's controller is the player itself).
    Remaining lossy (verbatim): ``prevent that damage`` has no PREVENT atom inside the action —
    PREVENT_EFFECT is the duration-scoped restriction verb (can't-be-
    blocked family), not a replacement step; per the landed r5 convention
    the replacement itself subsumes prevention (Containment Priest's
    "exile it instead" carries no prevent atom either), so the action is
    just PUT_COUNTER(INCARNATION, 1) on the self enchantment.
    C16: none — fully forced."""
    return AbilityOutcome(
        ability=ReplacementAbility(
            event=DamageDealtEvent(
                amount=QUnbounded(),
                # "to you" restored (round 8): the damaged-object filter
                # names YOU via the C-4/R8-5 player-identity vocabulary.
                filter=FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
            ),
            condition=None,
            action=Atom(
                verb=Verb.PUT_COUNTER,
                args=AtomArgs(
                    pairs=(
                        (
                            "target",
                            Selector(
                                QConst(1),
                                SelectorMode.CHOOSE,
                                FAtom(pred=FAtomPred.IS_SOURCE),
                                Zone(
                                    kind=ZoneKind.BATTLEFIELD,
                                    controller=ControllerRef.ANY,
                                ),
                            ),
                        ),
                        ("counter_kind", CounterKind.INCARNATION),
                        ("count", QConst(1)),
                    )
                ),
            ),
        )
    )


def _build_flip_won(m: re.Match[str]) -> SentenceOutcome:
    """``If you win the flip, you gain 6 life.`` (Tavern Swindler s2) —
    Conditional gated on FAtomPred.FLIP_WON (who=YOU; r3b vocabulary —
    "you lose it" would be FNot).  Sibling of the b5c B5c-flip-cost
    activation: the two rows together consume the FLIP_COIN orphan verb.
    Assembly note (documented deviation): the sentence has no continuation
    prefix, so the creature-card effect fold wraps it into a
    SpellAbility(CREATURE); rules-wise it is the activation's second
    sentence — the FLIP_WON gate keeps the stochastic branch explicit
    either way.  C16: the coin flip itself is the stochastic vertex;
    gain amount forced."""
    return EffectOutcome(
        effect=Conditional(
            pred=FAtom(pred=FAtomPred.FLIP_WON, who=ControllerRef.YOU),
            then_effect=Atom(
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


def _build_choice_of_grants(m: re.Match[str]) -> SentenceOutcome:
    """``Target creature gets +1/+1 and gains your choice of deathtouch or
    lifelink until end of turn.`` (Alchemist's Gift) — one sentence, one
    spell step: Seq(MODIFY_PT, Choose) where the Choose is the C15
    controller decision — one of two KeywordAbility grants, nothing
    defaulted (Feat-of-Resistance five-way shape, reduced to the printed
    two).  The grant targets the spell's own target via
    ``referent="target"`` (R4 vocabulary) so no second target declaration
    is minted.  C16: target choice (1 creature) × keyword choice
    (deathtouch | lifelink) stay open."""
    p, t = int(m.group("p")), int(m.group("t"))
    grant_target = Selector(
        QConst(1),
        SelectorMode.CHOOSE,
        FAnd(children=()),
        Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
        referent="target",
    )
    mod = Atom(
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
                ("power", PtDelta(PtDirection.INCREASE, QConst(p))),
                ("toughness", PtDelta(PtDirection.INCREASE, QConst(t))),
                ("duration", DurationEot()),
            )
        ),
    )
    grants = tuple(
        Atom(
            verb=Verb.GRANT_ABILITY,
            args=AtomArgs(
                pairs=(
                    ("target", grant_target),
                    ("ability", KeywordAbility(keyword=kw)),
                    ("duration", DurationEot()),
                )
            ),
        )
        for kw in (Keyword.DEATHTOUCH, Keyword.LIFELINK)
    )
    return EffectOutcome(
        effect=Seq(steps=(mod, Choose(count=QConst(1), options=grants)))
    )


def _build_its_controller_token(m: re.Match[str]) -> SentenceOutcome:
    """``Its controller creates a 4/4 white Angel creature token with
    flying.`` (Angelic Ascension s2) and ``Its controller creates a 1/1
    white Soldier creature token.`` (Secure the Scene s2) — CREATE_TOKEN;
    ``Its`` = the spell's exiled target (both cards' s1 already landed
    with a TARGET selector; the non-continuation s2 folds into the same
    SpellAbility Seq, so the antecedent is the ability's own target —
    executor-side referent binding per R4).
    Faithful since round 8: TokenSpec.color="W" carries ``white`` (C-2
    repair — the row's pattern pins the word "white" for both Angel and
    Soldier sentences).  FAITHFUL since grammar round 11 (R11-2, batch 6
    ruling /10): ``Its controller`` lands as the CREATE_TOKEN ``controller``
    role — the exact R4 referent-target Selector shape the Liliana Death
    Mage "its controller loses life" row uses (the antecedent is the s1
    TARGET designation; ``role_players`` folds the exiled card to its
    controller at execution).
    C16: none — fully forced."""
    subtype = m.group("st")
    return EffectOutcome(
        effect=Atom(
            verb=Verb.CREATE_TOKEN,
            args=AtomArgs(
                pairs=(
                    (
                        "controller",
                        Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAnd(children=()),
                            Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
                            referent="target",
                        ),
                    ),
                    (
                        "tokens",
                        TokenSpec(
                            name=subtype,
                            type_line=f"Creature — {subtype}",
                            types=("Creature",),
                            subtypes=(subtype,),
                            power=QConst(int(m.group("p"))),
                            toughness=QConst(int(m.group("t"))),
                            keywords=(Keyword.FLYING,) if m.group("fly") else (),
                            abilities=(),
                            color="W",  # C-2 repair (round 8)
                        ),
                    ),
                )
            ),
        )
    )


def _build_its_controller_loses_life(m: re.Match[str]) -> SentenceOutcome:
    """``Its controller loses 2 life.`` (Liliana, Death Mage [−3] s2) —
    LOSE_LIFE whose controller role carries an R4 ``referent="target"``
    selector: the controller-of-the-selected-object executor convention,
    Gloom-Sower precedent (B2b-gloom-sower puts the event-referent
    Selector in the same role).  ``Its`` = the [−3]'s destroyed creature.
    Assembly note (documented deviation): the sentence has no continuation
    prefix, so the planeswalker effect fold lands it as a card-level
    SpellAbility(PLANESWALKER); rules-wise it belongs inside the [−3]
    ActivatedAbility, whose target the referent names — the closest
    structured binding available without compiler changes.
    C16: none — fully forced."""
    return EffectOutcome(
        effect=Atom(
            verb=Verb.LOSE_LIFE,
            args=AtomArgs(
                pairs=(
                    (
                        "controller",
                        Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAnd(children=()),
                            Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
                            referent="target",
                        ),
                    ),
                    ("amount", QConst(int(m.group(1)))),
                )
            ),
        )
    )


# ---------------------------------------------------------------------------
# Grammar round-8-C coverage batch builders (doc 2026-09-28/08 §8-C)
# ---------------------------------------------------------------------------


def _build_if_was_creature_counter_gain(m: re.Match[str]) -> SentenceOutcome:
    """``If it was a creature card, put a +1/+1 counter on this creature and
    you gain 1 life.`` (Scavenging Ooze) — C18 was-check.  FAtom rules
    keep the referent slot closed to IS_ATTACHED_TO, so the conditional
    subject is the result register by executor convention (the landed
    B5b-if-it-type-then precedent, verbatim); the executor SNAPSHOTS the
    exiled card's printed type at the antecedent event (C18: "was" reads
    the value-at-antecedent-event — the card's printed type is immutable
    across zones, so the register subject carries it).  Then-branch is a
    two-step Seq: PUT_COUNTER on the Ooze itself (B5b self convention
    CHOOSE/QConst(1)/IS_SOURCE/BATTLEFIELD-ANY) + GAIN_LIFE you 1.

    C16: the counter/gain-life pair is gated on the exiled card's printed
    type (game state, not a choice); the exile target of s1 stays open
    there — nothing defaulted here."""
    counter = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.IS_SOURCE),
                        Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                    ),
                ),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                ("count", QConst(1)),
            )
        ),
    )
    gain = Atom(
        verb=Verb.GAIN_LIFE,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("amount", QConst(int(m.group("life")))),
            )
        ),
    )
    return EffectOutcome(
        effect=Conditional(
            pred=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            then_effect=Seq(steps=(counter, gain)),
        )
    )


def _build_peer_half_library(m: re.Match[str]) -> SentenceOutcome:
    """``Target player draws cards equal to half the number of cards in
    their library and loses half their life.`` (Peer into the Abyss s1).

    Draw: DRAW controller=ControllerRef.TARGET_PLAYER, amount = the
    round-up half of the TARGET player's library — "their" is the spell's
    player target, so the count rides
    QCount(Selector(ALL, QUnbounded, universal filter,
    Zone(LIBRARY, TARGET_PLAYER))), not QProp CARDS_IN_LIBRARY (that
    field is pinned to the ability controller, QProp validator).
    Round-up = the closed QBinOp idiom (n + 1) // 2 (QBinOp docstring —
    "Peer needs NO new op", grammar-round-8 grounding) — the companion
    row ``Round up each time.`` is consumed as the rounding directive
    (B5b-peer-round-up-each-time).

    Lossy (C11 class, verbatim): the life-loss half — the grammar has NO
    life-total quantity (no QPropField.LIFE; QCount counts zone objects,
    players are not zone objects), so ``loses half their life`` has no
    expressible amount (R9 grammar item: life-total Quantity field).
    C16: open — which player is targeted (s1 TARGET selector lives with
    the covered target-prefix template); both halves are board-dynamic
    quantities, nothing controller-chosen is defaulted."""
    library_count = QCount(
        Selector(
            QUnbounded(),
            SelectorMode.ALL,
            FAnd(children=()),
            Zone(kind=ZoneKind.LIBRARY, controller=ControllerRef.TARGET_PLAYER),
        )
    )
    half_rounded = QBin(
        op=QBinOp.DIV,
        left=QBin(op=QBinOp.ADD, left=library_count, right=QConst(1)),
        right=QConst(2),
    )
    return EffectOutcome(
        effect=Atom(
            verb=Verb.DRAW,
            args=AtomArgs(
                pairs=(
                    ("controller", ControllerRef.TARGET_PLAYER),
                    ("amount", half_rounded),
                )
            ),
        )
    )


def _build_peer_round_up_each_time(m: re.Match[str]) -> SentenceOutcome:
    """``Round up each time.`` (Peer into the Abyss s2) — rounding
    directive consumed as a RuleReminderOutcome, the landed precedent for
    anaphoric instruction rows being matched rather than defaulted
    (B2b-double-vision-new-targets, reason 'anaphoric_continuation').
    The rounding itself is already the shape of the s1 amount:
    QBinOp.DIV is floor, round-up-half is (n+1)//2 — the closed-operator
    idiom (QBinOp docstring), so this row carries no residual payload and
    must NOT spawn a duplicate draw/lose step.  "each time" = both
    half-computations of s1 (library draw; the life half is dropped
    lossy — see _build_peer_half_library).
    C16: none — computation directive, fully forced."""
    return RuleReminderOutcome(reason="rounding_directive")


def _build_double_counters_on_target(m: re.Match[str]) -> SentenceOutcome:
    """``Put a +1/+1 counter on target creature you control, then double the
    number of +1/+1 counters on that creature.`` (Invigorating Surge) —
    Seq inside the spell's effect: step 1 PUT_COUNTER +1/+1 x1 on the
    TARGET (B5b convention #63 TARGET selector); step 2 doubles by
    PUT_COUNTER of QProp(referent="target", field=COUNTER_COUNT) (R8-11 —
    the counter count of the chosen target): adding the CURRENT count to
    itself is the doubling, the "that creature" anaphor binds
    referent="target" (R4 vocabulary, the spell's designation).
    C16: open — the target creature; the doubled amount is board-dynamic
    (evaluated at resolution), not a choice."""
    target = _target_creature_you_control()
    put_one = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                ("target", target),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                ("count", QConst(1)),
            )
        ),
    )
    double_up = Atom(
        verb=Verb.PUT_COUNTER,
        args=AtomArgs(
            pairs=(
                (
                    "target",
                    Selector(
                        QConst(1),
                        SelectorMode.CHOOSE,
                        FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                        Zone(kind=ZoneKind.ANY, controller=ControllerRef.ANY),
                        referent="target",
                    ),
                ),
                ("counter_kind", CounterKind.PLUS_1_PLUS_1),
                (
                    "count",
                    QProp(referent="target", field=QPropField.COUNTER_COUNT),
                ),
            )
        ),
    )
    return EffectOutcome(effect=Seq(steps=(put_one, double_up)))


def _build_then_if_opponent_more_creatures(m: re.Match[str]) -> SentenceOutcome:
    """``Then if an opponent controls more creatures than you, put a loyalty
    counter on Garruk.`` (Garruk, Unleashed [−2] s2) — "Then " continuation
    merged into the [−2] ActivatedAbility;
    Conditional(CONTROLLER_COUNT_GT) — R8-9 dual-filter comparison:
    inner_filter counts creatures an OPPONENT controls (FAnd TYPE_EQ
    Creature + CONTROLLER_IS who=OPPONENT, the Nine Lives flipped shape),
    right_inner_filter counts YOUR creatures; both slots REQUIRED by the
    predicate's role entry.  "an opponent" = ControllerRef.OPPONENT (the
    per-opponent reading — the executor evaluates each rival, C13-
    adjacent, documented).  Then-branch: PUT_COUNTER LOYALTY (the
    CounterKind exists since T3, Pestilent Haze) x1 on Garruk = the
    ability's SOURCE object (IS_SOURCE CHOOSE selector, B5b self
    convention).
    C16: none new — board comparison gate, forced counter."""
    gated = Conditional(
        pred=FAtom(
            pred=FAtomPred.CONTROLLER_COUNT_GT,
            inner_filter=FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.OPPONENT),
                )
            ),
            right_inner_filter=FAnd(
                children=(
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                    FAtom(pred=FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU),
                )
            ),
        ),
        then_effect=Atom(
            verb=Verb.PUT_COUNTER,
            args=AtomArgs(
                pairs=(
                    (
                        "target",
                        Selector(
                            QConst(1),
                            SelectorMode.CHOOSE,
                            FAtom(pred=FAtomPred.IS_SOURCE),
                            Zone(
                                kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.YOU
                            ),
                        ),
                    ),
                    ("counter_kind", CounterKind.LOYALTY),
                    ("count", QConst(1)),
                )
            ),
        ),
    )
    return EffectOutcome(effect=gated)


def _build_it_gains_haste_emblem_residue(m: re.Match[str]) -> SentenceOutcome:
    """``It gains haste."`` (Liliana, Waker of the Dead — trailing-quote
    ingest artifact: the second sentence of the [−7]'s QUOTED emblem text,
    sentence-splitter residue; class E in the module header, queue-pinned
    since r7-A).

    Consumed as a RuleReminderOutcome (B2b-double-vision precedent).
    C19 binds: the quoted emblem text NEVER enters the row's payload —
    the haste grant is already compiled INSIDE the attached emblem
    CardRecord by ``B5b-it-gains-haste`` (verified: the landed Liliana
    golden's emblem carries the two-ability trigger with the grant).
    Re-granting at the planeswalker's card level would DUPLICATE the
    payload outside the emblem the text belongs to — the marker row is
    the C19-honest consumption (Double Vision class: semantics live
    elsewhere in the tree).
    C16: none — payload lives in the emblem attach."""
    return RuleReminderOutcome(reason="emblem_text_payload_attached")


def _build_spend_this_mana_is_or_sorcery(m: re.Match[str]) -> SentenceOutcome:
    """``Spend this mana only to cast an instant or sorcery spell.``
    (Vodalian Arcanist) — grammar round 9-B row 10, the C21 event-anchored
    sibling of the b4 ALL_YOURS row: Verb.MANA_POLICY (R9-3) with scope
    "THIS_MANA" (the policy binds the mana THIS ability adds — the card's
    own ``{T}: Add {C}`` row — executor-side anchoring) and filter =
    FOr(TYPE_EQ Instant, TYPE_EQ Sorcery) narrowing the permitted spend
    to the two spell types.  No OptionalEffect — the sentence is a
    restriction ("only to"), not a permission; no may to keep open (C15
    silent here).  Executor deferred per the MANA_POLICY orphan precedent
    (PC-6: verb consumed this round — in b4 — stays consumed here).

    C16: none — fully forced restriction (which instant/sorcery to cast is
    the player's casting decision, not this atom's)."""
    instant_or_sorcery = FOr(
        children=(
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Instant"),
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Sorcery"),
        )
    )
    atom = Atom(
        verb=Verb.MANA_POLICY,
        args=AtomArgs(pairs=(("scope", "THIS_MANA"), ("filter", instant_or_sorcery))),
    )
    return AbilityOutcome(ability=StaticAbility(effect=atom))


def _build_play_top_revealed(m: re.Match[str]) -> SentenceOutcome:
    """``Play with the top card of your library revealed.`` (Conspicuous
    Snoop) — grammar round 9-B row 11: the R9-8 REVEAL duration role makes
    the continuous revealed state expressible: REVEAL (controller=YOU,
    count=QConst(1), duration=DurationPermanent) as a StaticAbility — the
    library-top target is IMPLICIT per the LOOK_AT convention (LOOK_AT has
    no zone role — top-of-library, Radha/Sasaya precedent; REVEAL's roles
    mirror it, the count names how many cards stay face-up).

    C16: none — a continuous zone-state rule, fully forced."""
    atom = Atom(
        verb=Verb.REVEAL,
        args=AtomArgs(
            pairs=(
                ("controller", ControllerRef.YOU),
                ("count", QConst(1)),
                ("duration", DurationPermanent()),
            )
        ),
    )
    return AbilityOutcome(ability=StaticAbility(effect=atom))


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
    # --- grammar round-7 batch (family-2 anaphora; doc 2026-09-28/03 §3) ---
    Template(
        tid="B5b-it-gains-kw-eot",
        name="it gains <kw> until end of turn (result-referent grant)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^It gains (?P<kw>indestructible|haste|vigilance) "
            r"until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_it_gains_kw_eot,
    ),
    Template(
        tid="B5b-it-gains-haste",
        name="it gains haste (permanent result-referent grant)",
        bucket=_BUCKET,
        pattern=re.compile(r"^It gains haste\.$"),
        priority=_PRIORITY,
        build=_build_it_gains_haste,
    ),
    Template(
        tid="B5b-it-gains-protection-choice",
        name="it gains protection from the color of your choice (Choose 1-of-5)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^It gains protection from the color of your choice "
            r"until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_it_gains_protection_choice,
    ),
    Template(
        tid="B5b-that-player-discards",
        name="that player discards that card (result-referent discard)",
        bucket=_BUCKET,
        pattern=re.compile(r"^That player discards that card\.$"),
        priority=_PRIORITY,
        build=_build_that_player_discards_that_card,
    ),
    Template(
        tid="B5b-if-it-type-then",
        name="if it's a creature [or land] card, <then> (result Conditional)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If it's a creature(?P<or_land> or land)? card, "
            r"(?P<then>put it into your hand|draw a card)\.$"
        ),
        priority=_PRIORITY,
        build=_build_if_it_type_then,
    ),
    Template(
        tid="B5b-otherwise-bottom",
        name="otherwise put it on the bottom of your library (else_effect)",
        bucket=_BUCKET,
        pattern=re.compile(r"^Otherwise, put it on the bottom of your library\.$"),
        priority=_PRIORITY,
        build=_build_otherwise_bottom,
    ),
    Template(
        tid="B5b-search-name-exile",
        name="search target opponent's zones for any number with that name, exile",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Search target opponent's graveyard, hand, and library for "
            r"any number of cards with that name and exile them\.$"
        ),
        priority=_PRIORITY,
        build=_build_search_name_exile,
    ),
    Template(
        tid="B5b-token-per-exiled-this-way",
        name="that player shuffles, then creates a Zombie token per this-way exile",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^That player shuffles, then creates a (?P<p>\d+)/(?P<t>\d+) "
            r"black Zombie creature token for each card exiled from their "
            r"hand this way\.$"
        ),
        priority=_PRIORITY,
        build=_build_shuffle_then_token_per_exiled,
    ),
    Template(
        tid="B5b-loses-kw-eot",
        name="that permanent loses <kw> until end of turn (LOSE_ABILITY)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^That permanent loses (?P<kw>indestructible) until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_that_permanent_loses_kw,
    ),
    Template(
        tid="B5b-one-of-other",
        name="put one of them into your hand and the other into your graveyard",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Put one of them into your hand and the other into your "
            r"graveyard\.$"
        ),
        priority=_PRIORITY,
        build=_build_one_of_other,
    ),
    Template(
        tid="B5b-one-of-rest-bottom",
        name="put one of those cards into your hand and the rest on bottom",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Put one of those cards into your hand and the rest on the "
            r"bottom of your library in any order\.$"
        ),
        priority=_PRIORITY,
        build=_build_one_of_rest_bottom,
    ),
    Template(
        tid="B5b-rest-bottom-random",
        name="put the rest on the bottom of your library in a random order",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Put the rest on the bottom of your library in a random order\.$"
        ),
        priority=_PRIORITY,
        build=_build_rest_bottom_random,
    ),
    Template(
        tid="B5b-search-one-other-shuffle",
        name="search up to two basic lands, one tapped to BF, other to hand, shuffle",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Search your library for up to two basic land cards, reveal "
            r"those cards, put one onto the battlefield tapped and the other "
            r"into your hand, then shuffle\.$"
        ),
        priority=_PRIORITY,
        build=_build_cultivate_search,
    ),
    Template(
        tid="B5b-cast-elsewhere-instead",
        name="if cast from anywhere other than your hand, those cards to hand instead",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If this spell was cast from anywhere other than your hand, "
            r"put each of those cards into your hand instead\.$"
        ),
        priority=_PRIORITY,
        build=_build_cast_elsewhere_instead,
    ),
    Template(
        tid="B5b-gain-control-eot",
        name="gain control of target creature until end of turn",
        bucket=_BUCKET,
        pattern=re.compile(r"^Gain control of target creature until end of turn\.$"),
        priority=_PRIORITY,
        build=_build_gain_control_eot,
    ),
    # --- grammar round-7-B batch (no-grammar top-ups; doc 2026-09-28/03 §3) ---
    Template(
        tid="B5b-keyword-list-params",
        name="keyword list with parameterized PROTECTION/HEXPROOF member",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^(?P<form>Flying, first strike, lifelink, protection from "
            r"Demons and from Dragons|Reach, hexproof from blue)$"
        ),
        priority=_PRIORITY,
        build=_build_keyword_list_params,
    ),
    Template(
        tid="B5b-if-died-two-tokens",
        name="if a creature died this turn, create two Saproling tokens",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If a creature died this turn, create two 1/1 green Saproling "
            r"creature tokens\.$"
        ),
        priority=_PRIORITY,
        build=_build_if_died_two_tokens,
    ),
    Template(
        tid="B5b-would-damage-incarnation",
        name="would-deal-damage replacement: put an incarnation counter (Nine Lives)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If a source would deal damage to you, prevent that damage and "
            r"put an incarnation counter on this enchantment\.$"
        ),
        priority=_PRIORITY,
        build=_build_would_damage_incarnation,
    ),
    Template(
        tid="B5b-flip-won",
        name="if you win the flip, you gain N life (FLIP_WON Conditional)",
        bucket=_BUCKET,
        pattern=re.compile(r"^If you win the flip, you gain (\d+) life\.$"),
        priority=_PRIORITY,
        build=_build_flip_won,
    ),
    Template(
        tid="B5b-choice-of-grants",
        name="gets +N/+N and gains your choice of two keywords (Choose 1-of-2)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Target creature gets \+(?P<p>\d+)/\+(?P<t>\d+) and gains your "
            r"choice of deathtouch or lifelink until end of turn\.$"
        ),
        priority=_PRIORITY,
        build=_build_choice_of_grants,
    ),
    Template(
        tid="B5b-its-controller-token",
        name="its controller creates a white Angel/Soldier token (controller referent)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Its controller creates a (?P<p>\d+)/(?P<t>\d+) white "
            r"(?P<st>Angel|Soldier) creature token(?P<fly> with flying)?\.$"
        ),
        priority=_PRIORITY,
        build=_build_its_controller_token,
    ),
    Template(
        tid="B5b-its-controller-loses-life",
        name="its controller loses N life (referent-target controller role)",
        bucket=_BUCKET,
        pattern=re.compile(r"^Its controller loses (\d+) life\.$"),
        priority=_PRIORITY,
        build=_build_its_controller_loses_life,
    ),
    # --- grammar round-8-C coverage batch (doc 2026-09-28/08 §8-C) ---
    Template(
        tid="B5b-if-was-creature-counter-gain",
        name="if it was a creature card, counter + gain life (C18 result TYPE_EQ)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^If it was a creature card, put a \+\d+/\+\d+ counter on this "
            r"creature and you gain (?P<life>\d+) life\.$"
        ),
        priority=_PRIORITY,
        build=_build_if_was_creature_counter_gain,
    ),
    Template(
        tid="B5b-peer-half-library",
        name="target player draws round-up half their library (Peer; life-half lossy)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Target player draws cards equal to half the number of cards "
            r"in their library and loses half their life\.$"
        ),
        priority=_PRIORITY,
        build=_build_peer_half_library,
    ),
    Template(
        tid="B5b-peer-round-up-each-time",
        name="round up each time (rounding directive consumed by s1 (n+1)//2)",
        bucket=_BUCKET,
        pattern=re.compile(r"^Round up each time\.$"),
        priority=_PRIORITY,
        build=_build_peer_round_up_each_time,
    ),
    Template(
        tid="B5b-double-counters-target",
        name="counter target, then double its counters (COUNTER_COUNT referent-target)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Put a \+\d+/\+\d+ counter on target creature you control, "
            r"then double the number of \+\d+/\+\d+ counters on that "
            r"creature\.$"
        ),
        priority=_PRIORITY,
        build=_build_double_counters_on_target,
    ),
    Template(
        tid="B5b-then-if-opponent-more-creatures",
        name="then if an opponent controls more creatures than you, loyalty counter (CONTROLLER_COUNT_GT)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Then if an opponent controls more creatures than you, put a "
            r"loyalty counter on Garruk\.$"
        ),
        priority=_PRIORITY,
        build=_build_then_if_opponent_more_creatures,
    ),
    Template(
        tid="B5b-gains-haste-emblem-residue",
        name='it gains haste." (emblem-quote residue marker, C19)',
        bucket=_BUCKET,
        pattern=re.compile(r'^It gains haste\."$'),
        priority=_PRIORITY,
        build=_build_it_gains_haste_emblem_residue,
    ),
    # --- grammar round-9-B coverage batch (doc 2026-09-28/11 §9-B rows 10-11) ---
    Template(
        tid="B5b-spend-this-mana-is-or-sorcery",
        name="mana policy: THIS_MANA anchored to instant/sorcery casts (MANA_POLICY, C21)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^Spend this mana only to cast an instant or sorcery spell\.$"
        ),
        priority=_PRIORITY,
        build=_build_spend_this_mana_is_or_sorcery,
    ),
    Template(
        tid="B5b-play-top-revealed",
        name="continuous revealed top card (REVEAL + DurationPermanent, R9-8)",
        bucket=_BUCKET,
        pattern=re.compile(r"^Play with the top card of your library revealed\.$"),
        priority=_PRIORITY,
        build=_build_play_top_revealed,
    ),
    # --- grammar round-11 C3 coverage batch (Transmogrify reveal-until pair) ---
    Template(
        tid="B5b-transmogrify-reveal-creature",
        name="top-of-library creature search for that player (SEARCH TOP, C3)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^That creature's controller reveals cards from the top of their "
            r"library until they reveal a creature card\.$"
        ),
        priority=_PRIORITY,
        build=_build_transmog_reveal_creature,
    ),
    Template(
        tid="B5b-transmogrify-shuffle-rest",
        name="shuffle-remainder tail (SHUFFLE Zone LIBRARY TARGET_PLAYER, C3)",
        bucket=_BUCKET,
        pattern=re.compile(
            r"^That player puts that card onto the battlefield, then shuffles "
            r"the rest into their library\.$"
        ),
        priority=_PRIORITY,
        build=_build_transmog_shuffle_rest,
    ),
)

UNCOVERED: tuple[tuple[str, str], ...] = (
    (
        "If an ability of another Shrine you control triggers while you control six or more Shrines, that ability triggers an additional time.",
        "Additional trigger with shrine-count gate",
    ),
    (
        "If you search your library this way, shuffle.",
        "Conditional shuffle on library-search trigger",
    ),
)
