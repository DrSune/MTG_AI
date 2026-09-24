"""B5b bucket templates — 37 templates covering 41 of 90 B5b shapes.

Bucket input: ``/tmp/opencode/phase1_buckets/B5b.json`` (90 normalized shape
keys → ``[card, sentence]`` pairs; sentences carry *concrete* numbers, keys
carry ``N`` placeholders).  Templates fullmatch the **concrete** oracle
sentence, never the normalized key.

Coverage (90 = 41 template + 0 rule-reminder + 49 uncovered):

- **41 template-covered shapes** (37 templates: 34 single-shape tids +
  3 multi-shape normalized tids — put-counter ×3, return-cards-hand ×2,
  named-damage ×2; ``B5b-modpt-plus`` is one shape with two concrete rows):
  keyword rule-reminder sentences (Flash/Haste/Hexproof/Lifelink/Menace/
  Prowess/Reach), continuation effects (discard/draw/gain-life/gain-mana-
  value/modPT+keyword), token creation (Demon/Zombie), counter placement,
  zone moves (graveyard → battlefield / hand / owner's hand), cost
  modifiers (noncreature spells cost {N} more), scry/reveal,
  search/shuffle, named/any-target damage, activated abilities
  (sacrifice-grant, tap-spirits), P/T modifications (+N, -N, +X),
  reveal-hand, sacrifice-flying, discard-2.
- **0 rule-reminder shapes** — no fully-parenthesised sentences in B5b.
- **49 uncovered shapes** — conditional triggers, anaphora, replacement
  effects, coin-flip gates, fractional computation, modal continuations,
  protection-from-color-choice, multi-zone search, keyword-loss, power-
  tied-to-card-count, and other constructs with no grammar equivalent.
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
    ControllerRef,
    Cost,
    CostDeltaIncreaseGeneric,
    CostModifier,
    CostSacrifice,
    CostTap,
    CounterKind,
    DurationEot,
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    PtDelta,
    PtDirection,
    QAgg,
    QConst,
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
)

UNCOVERED: tuple[tuple[str, str], ...] = (
    (
        "Flying, first strike, lifelink, protection from Demons and from Dragons",
        "Composite keyword list with protection-from-subtypes",
    ),
    (
        "Gadrak can't attack unless you control four or more artifacts.",
        "Conditional attack restriction with artifact-count gate",
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
        "If a creature died this turn, you gain N life instead.",
        "Conditional life-gain replacement on creature-death trigger",
    ),
    (
        "If a nontoken creature would enter and it wasn't cast, exile it instead.",
        "Prevent-and-exile replacement on enter-the-battlefield",
    ),
    (
        "If a source would deal damage to you, prevent that damage and put an incarnation counter on this enchantment.",
        "Prevent-damage-and-put-counter replacement",
    ),
    (
        "If a source you control would deal damage to a permanent or player, it deals triple that damage to that permanent or player instead.",
        "Damage-amplification replacement (triple damage)",
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
        "If one or more +N/+N counters would be put on a creature you control, that many plus one +N/+N counters are put on that creature instead.",
        "Counter-amplification replacement with anaphoric 'that many'",
    ),
    (
        "If that creature or planeswalker would die this turn, exile it instead.",
        "Prevent-death-and-exile replacement with anaphoric 'that'",
    ),
    (
        "If that spell would be put into your graveyard, exile it instead.",
        "Prevent-graveyard-and-exile replacement with anaphoric 'that'",
    ),
    (
        "If this spell was cast from anywhere other than your hand, put each of those cards into your hand instead.",
        "Conditional zone-move with anaphoric 'those cards'",
    ),
    (
        "If you control a creature with flying, counter that spell unless its controller pays {N} instead.",
        "Counter-spell-unless-pays replacement with conditional gate",
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
        "If you would draw a card except the first one you draw in each of your draw steps, draw two cards instead.",
        "Complex draw-replacement with draw-step exclusion",
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
        "Kinetic Augur's power is equal to the number of instant and sorcery cards in your graveyard.",
        "Power-tied-to-card-count static ability",
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
