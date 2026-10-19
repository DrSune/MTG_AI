"""Tests for B5b bucket templates (templates_b5b.py).

Covers all 90 shapes in ``/tmp/opencode/phase1_buckets/B5b.json``
(91 distinct concrete sentences):
- 90 template-covered rows (80 tids, incl. 5 multi-shape normalized tids;
  ``B5b-modpt-plus`` is one shape with two concrete rows; round-11 C3
  retired the Transmogrify reveal-until pair)
- 1 UNCOVERED (no template) + the compiler-built-in search-shuffle
  boilerplate row: "If you search your library this way, shuffle." —
  see test_compiler.py::TestContinuation::test_search_shuffle_*)
- 0 rule-reminder pre-consumed

PC-3: every concrete sentence fullmatches at most one template.
"""

from __future__ import annotations

import json
import os
import unittest
import uuid
from typing import Any

from MTG_bot.core.ability_tree import (
    QX,
    ActivatedAbility,
    Atom,
    CardDrawnEvent,
    Choose,
    Conditional,
    ControllerRef,
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
    FAnd,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    LifeGainedEvent,
    OptionalEffect,
    PtDelta,
    PtDirection,
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
    SpellAbility,
    StaticAbility,
    TokenSpec,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    ZonePosition,
    canonical_json,
)
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.ingest import RawCard
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    KeywordOutcome,
    RuleReminderOutcome,
    SentenceOutcome,
    TemplateRegistry,
)
from MTG_bot.core.compiler.templates_b5b import TEMPLATES
from MTG_bot.core.identity import CardIdentity

# ---------------------------------------------------------------------------
# SHAPES — 91 distinct concrete sentences from B5b.json with expected
# classification.
# Each entry: (sentence, category, expected_tid)
#   category: "COVERED" = template-covered, "UNCOV" = uncovered
# ---------------------------------------------------------------------------

SHAPES: tuple[tuple[str, str, str], ...] = (
    # shape 1
    (
        "Flash (You may cast this spell any time you could cast an instant.)",
        "COVERED",
        "B5b-flash",
    ),
    # shape 2
    (
        "Flying, first strike, lifelink, protection from Demons and from Dragons",
        "COVERED",
        "B5b-keyword-list-params",
    ),
    # shape 3
    (
        "Gadrak can't attack unless you control four or more artifacts.",
        "COVERED",
        "B5b-gadrak-cant-attack-unless-artifacts",
    ),
    # shape 4
    (
        "Gain control of target creature until end of turn.",
        "COVERED",
        "B5b-gain-control-eot",
    ),
    # shape 5
    (
        "Haste (This creature can attack and {T} as soon as it comes under your control.)",
        "COVERED",
        "B5b-haste",
    ),
    # shape 6
    (
        "Hexproof (This creature can't be the target of spells or abilities your opponents control.)",
        "COVERED",
        "B5b-hexproof",
    ),
    # shape 7
    (
        "If a creature died this turn, create two 1/1 green Saproling creature tokens.",
        "COVERED",
        "B5b-if-died-two-tokens",
    ),
    # shape 8
    (
        "If a creature died this turn, you gain 8 life instead.",
        "COVERED",
        "B5b-repl-died-gain-life",
    ),
    # shape 9
    (
        "If a nontoken creature would enter and it wasn't cast, exile it instead.",
        "COVERED",
        "B5b-repl-nontoken-enter-exile",
    ),
    # shape 10
    (
        "If a source would deal damage to you, prevent that damage and put an incarnation counter on this enchantment.",
        "COVERED",
        "B5b-would-damage-incarnation",
    ),
    # shape 11
    (
        "If a source you control would deal damage to a permanent or player, it deals triple that damage to that permanent or player instead.",
        "COVERED",
        "B5b-repl-triple-damage",
    ),
    # shape 12
    (
        "If an ability of another Shrine you control triggers while you control six or more Shrines, that ability triggers an additional time.",
        "COVERED",
        "B5b-sanctum-all-extra-trigger",
    ),
    # shape 13
    (
        "If it was a creature card, put a +1/+1 counter on this creature and you gain 1 life.",
        "COVERED",
        "B5b-if-was-creature-counter-gain",
    ),
    # shape 14
    (
        "If it's a creature card, put it into your hand.",
        "COVERED",
        "B5b-if-it-type-then",
    ),
    # shape 15
    ("If it's a creature or land card, draw a card.", "COVERED", "B5b-if-it-type-then"),
    # shape 16
    (
        "If one or more +1/+1 counters would be put on a creature you control, that many plus one +1/+1 counters are put on that creature instead.",
        "COVERED",
        "B5b-repl-counter-plus-one",
    ),
    # shape 17
    (
        "If that creature or planeswalker would die this turn, exile it instead.",
        "COVERED",
        "B5b-repl-die-exile",
    ),
    # shape 18
    (
        "If that spell would be put into your graveyard, exile it instead.",
        "COVERED",
        "B5b-repl-graveyard-exile",
    ),
    # shape 19
    (
        "If this spell was cast from anywhere other than your hand, put each of those cards into your hand instead.",
        "COVERED",
        "B5b-cast-elsewhere-instead",
    ),
    # shape 20
    (
        "If you control a creature with flying, counter that spell unless its controller pays {4} instead.",
        "COVERED",
        "B5b-counter-unless-pays",
    ),
    # shape 21
    (
        "If you do, create a 5/5 black Demon creature token with flying.",
        "COVERED",
        "B5b-token-demon",
    ),
    # shape 22
    (
        "If you do, create a 2/2 black Zombie creature token.",
        "COVERED",
        "B5b-token-zombie",
    ),
    # shape 23
    ("If you do, discard a card.", "COVERED", "B5b-cont-discard"),
    # shape 24
    ("If you do, draw a card.", "COVERED", "B5b-cont-draw"),
    # shape 25
    (
        "If you do, this creature gets +2/+2 and gains trample until end of turn.",
        "COVERED",
        "B5b-seq-modpt-trample",
    ),
    # shape 26
    ("If you do, you gain 4 life.", "COVERED", "B5b-cont-gain-4"),
    # shape 27
    (
        "If you do, you gain life equal to that creature's mana value.",
        "COVERED",
        "B5b-cont-gain-mv",
    ),
    # shape 28
    ("If you search your library this way, shuffle.", "UNCOV", ""),
    # shape 29
    ("If you win the flip, you gain 6 life.", "COVERED", "B5b-flip-won"),
    # shape 30
    (
        "If you would draw a card except the first one you draw in each of your draw steps, draw two cards instead.",
        "COVERED",
        "B5b-repl-draw-not-first",
    ),
    # shape 31
    ("It gains haste until end of turn.", "COVERED", "B5b-it-gains-kw-eot"),
    # shape 32
    ("It gains haste.", "COVERED", "B5b-it-gains-haste"),
    # shape 33
    ('It gains haste."', "COVERED", "B5b-gains-haste-emblem-residue"),
    # shape 34
    ("It gains indestructible until end of turn.", "COVERED", "B5b-it-gains-kw-eot"),
    # shape 35
    (
        "It gains protection from the color of your choice until end of turn.",
        "COVERED",
        "B5b-it-gains-protection-choice",
    ),
    # shape 36
    ("It gains vigilance until end of turn.", "COVERED", "B5b-it-gains-kw-eot"),
    # shape 37
    (
        "Its controller creates a 4/4 white Angel creature token with flying.",
        "COVERED",
        "B5b-its-controller-token",
    ),
    # shape 38
    (
        "Its controller creates a 1/1 white Soldier creature token.",
        "COVERED",
        "B5b-its-controller-token",
    ),
    # shape 39
    ("Its controller loses 2 life.", "COVERED", "B5b-its-controller-loses-life"),
    # shape 40
    (
        "Kinetic Augur's power is equal to the number of instant and sorcery cards in your graveyard.",
        "COVERED",
        "B5b-set-pt-power-gy-instant-sorcery",
    ),
    # shape 41
    (
        "Lifelink (Damage dealt by this creature also causes you to gain that much life.)",
        "COVERED",
        "B5b-lifelink",
    ),
    # shape 42
    ("Look at the top three cards of your library.", "COVERED", "B5b-look-3"),
    # shape 43
    (
        "Menace (This creature can't be blocked except by two or more creatures.)",
        "COVERED",
        "B5b-menace",
    ),
    # shape 44
    (
        "Noncreature spells cost {1} more to cast.",
        "COVERED",
        "B5b-noncreature-cost-more",
    ),
    # shape 45
    (
        "Otherwise, put it on the bottom of your library.",
        "COVERED",
        "B5b-otherwise-bottom",
    ),
    # shape 46
    (
        "Permanents you control gain hexproof and indestructible until end of turn.",
        "COVERED",
        "B5b-perm-hex-ind",
    ),
    # shape 47
    (
        "Play with the top card of your library revealed.",
        "COVERED",
        "B5b-play-top-revealed",
    ),
    # shape 48
    (
        "Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)",
        "COVERED",
        "B5b-prowess",
    ),
    # shape 49
    ("Put a +1/+1 counter on each creature you control.", "COVERED", "B5b-put-counter"),
    # shape 50
    (
        "Put a +1/+1 counter on each of up to two target creatures.",
        "COVERED",
        "B5b-put-counter",
    ),
    # shape 51
    (
        "Put a +1/+1 counter on target creature you control, then double the number of +1/+1 counters on that creature.",
        "COVERED",
        "B5b-double-counters-target",
    ),
    # shape 52
    (
        "Put a +1/+1 counter on target creature you control.",
        "COVERED",
        "B5b-put-counter",
    ),
    # shape 53
    (
        "Put one of them into your hand and the other into your graveyard.",
        "COVERED",
        "B5b-one-of-other",
    ),
    # shape 54
    (
        "Put one of those cards into your hand and the rest on the bottom of your library in any order.",
        "COVERED",
        "B5b-one-of-rest-bottom",
    ),
    # shape 55
    (
        "Put the rest on the bottom of your library in a random order.",
        "COVERED",
        "B5b-rest-bottom-random",
    ),
    # shape 56
    ("Reach (This creature can block creatures with flying.)", "COVERED", "B5b-reach"),
    # shape 57
    ("Reach, hexproof from blue", "COVERED", "B5b-keyword-list-params"),
    # shape 58
    (
        "Return target creature card from your graveyard to the battlefield.",
        "COVERED",
        "B5b-return-creatures-battlefield",
    ),
    # shape 59
    (
        "Return target permanent card from your graveyard to your hand.",
        "COVERED",
        "B5b-return-cards-hand",
    ),
    # shape 60
    (
        "Return target spell or creature to its owner's hand.",
        "COVERED",
        "B5b-return-spell-creature-owner-hand",
    ),
    # shape 61
    (
        "Return up to two target creature cards from your graveyard to your hand.",
        "COVERED",
        "B5b-return-cards-hand",
    ),
    # shape 62
    ("Round up each time.", "COVERED", "B5b-peer-round-up-each-time"),
    # shape 63
    (
        "Sacrifice this creature: Another target creature you control gains indestructible until end of turn.",
        "COVERED",
        "B5b-sacr-grant",
    ),
    # shape 64
    (
        "Scorching Dragonfire deals 3 damage to target creature or planeswalker.",
        "COVERED",
        "B5b-named-damage",
    ),
    # shape 65
    ("Scry 3, then reveal the top card of your library.", "COVERED", "B5b-scr-reveal"),
    # shape 66
    ("Scry 1.", "COVERED", "B5b-scr"),
    # shape 67
    (
        "Search target opponent's graveyard, hand, and library for any number of cards with that name and exile them.",
        "COVERED",
        "B5b-search-name-exile",
    ),
    # shape 68
    (
        "Search your library for a card, put that card into your hand, then shuffle.",
        "COVERED",
        "B5b-search-shuffle",
    ),
    # shape 69
    (
        "Search your library for up to two basic land cards, reveal those cards, put one onto the battlefield tapped and the other into your hand, then shuffle.",
        "COVERED",
        "B5b-search-one-other-shuffle",
    ),
    # shape 70
    ("Shock deals 2 damage to any target.", "COVERED", "B5b-damage-any"),
    # shape 71
    (
        "Soul Sear deals 5 damage to target creature or planeswalker.",
        "COVERED",
        "B5b-named-damage",
    ),
    # shape 72
    (
        "Spend this mana only to cast an instant or sorcery spell.",
        "COVERED",
        "B5b-spend-this-mana-is-or-sorcery",
    ),
    # shape 73
    (
        "Tap two untapped Spirits you control: Tap target creature you don't control.",
        "COVERED",
        "B5b-tap-spirits",
    ),
    # shape 74
    ("Tap up to two target creatures.", "COVERED", "B5b-tap-2-target"),
    # shape 75
    (
        "Target creature gets +3/+0 and gains first strike until end of turn.",
        "COVERED",
        "B5b-seq-modpt-firststrike",
    ),
    # shape 76
    (
        "Target creature gets +1/+1 and gains your choice of deathtouch or lifelink until end of turn.",
        "COVERED",
        "B5b-choice-of-grants",
    ),
    # shape 77 (two concrete rows)
    ("Target creature gets +1/+0 until end of turn.", "COVERED", "B5b-modpt-plus"),
    ("Target creature gets +4/+4 until end of turn.", "COVERED", "B5b-modpt-plus"),
    # shape 78
    ("Target creature gets -4/-4 until end of turn.", "COVERED", "B5b-modpt-minus"),
    # shape 79
    (
        "Target creature you control gets +1/+1 and gains hexproof until end of turn.",
        "COVERED",
        "B5b-seq-modpt-hexproof",
    ),
    # shape 80
    (
        "Target creature you control gets +X/+X until end of turn.",
        "COVERED",
        "B5b-modpt-x",
    ),
    # shape 81
    ("Target opponent reveals their hand.", "COVERED", "B5b-reveal-hand"),
    # shape 82
    (
        "Target opponent sacrifices a creature of their choice with flying.",
        "COVERED",
        "B5b-sacr-flying",
    ),
    # shape 83
    ("Target player discards two cards.", "COVERED", "B5b-discard-target-2"),
    # shape 84
    (
        "Target player draws cards equal to half the number of cards in their library and loses half their life.",
        "COVERED",
        "B5b-peer-half-library",
    ),
    # shape 85
    (
        "That creature's controller reveals cards from the top of their library until they reveal a creature card.",
        "COVERED",
        "B5b-transmogrify-reveal-creature",
    ),
    # shape 86
    (
        "That permanent loses indestructible until end of turn.",
        "COVERED",
        "B5b-loses-kw-eot",
    ),
    # shape 87
    ("That player discards that card.", "COVERED", "B5b-that-player-discards"),
    # shape 88
    (
        "That player puts that card onto the battlefield, then shuffles the rest into their library.",
        "COVERED",
        "B5b-transmogrify-shuffle-rest",
    ),
    # shape 89
    (
        "That player shuffles, then creates a 2/2 black Zombie creature token for each card exiled from their hand this way.",
        "COVERED",
        "B5b-token-per-exiled-this-way",
    ),
    # shape 90
    (
        "Then if an opponent controls more creatures than you, put a loyalty counter on Garruk.",
        "COVERED",
        "B5b-then-if-opponent-more-creatures",
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry() -> TemplateRegistry:
    """Build a TemplateRegistry with all B5b templates."""
    reg = TemplateRegistry()
    for t in TEMPLATES:
        reg.register(t)
    return reg


def _raw(
    name: str,
    sentences: tuple[str, ...],
    *,
    types: tuple[str, ...] = ("Instant",),
    subtypes: tuple[str, ...] = (),
    colors: tuple[str, ...] = (),
    keywords: tuple[str, ...] = (),
    mana_cost_raw: str | None = None,
    mana_value: int = 0,
    power_raw: str | None = None,
    toughness_raw: str | None = None,
) -> RawCard:
    """Build a minimal RawCard stub for end-to-end compile_card tests."""
    identity = CardIdentity(
        oracle_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"mtg://{name}")),
        name=name,
    )
    type_line = " ".join(types)
    if subtypes:
        type_line += " — " + " ".join(subtypes)
    return RawCard(
        identity=identity,
        type_line=type_line,
        types=types,
        subtypes=subtypes,
        supertypes=(),
        colors=colors,
        color_identity=frozenset(colors),
        mana_cost_raw=mana_cost_raw,
        mana_value=mana_value,
        power_raw=power_raw,
        toughness_raw=toughness_raw,
        loyalty_raw=None,
        keywords=keywords,
        sentences=sentences,
        layout="normal",
        is_token=False,
        is_emblem=False,
        token_name_refs=(),
        related_names=(),
    )


def _inner_node(outcome: SentenceOutcome) -> Any:
    """Extract the serialisable grammar node from a SentenceOutcome.

    canonical_json only works on grammar dataclasses (registered in _TAG),
    not on the outcome wrappers (AbilityOutcome/EffectOutcome/KeywordOutcome).
    """
    if isinstance(outcome, AbilityOutcome):
        return outcome.ability
    if isinstance(outcome, EffectOutcome):
        return outcome.effect
    if isinstance(outcome, KeywordOutcome):
        return KeywordAbility(keyword=outcome.keyword, params=outcome.params)
    if isinstance(outcome, RuleReminderOutcome):
        # r8-C: directive/marker rows (Round-up, emblem-quote residue)
        # carry only their reason string — stable-identity by reason.
        return outcome.reason
    raise TypeError(f"cannot extract inner node from {type(outcome)}")


def _pairs_dict(atom: Atom) -> dict[str, Any]:
    """Extract AtomArgs pairs as a dict for assertion convenience."""
    return dict(atom.args.pairs)


def _as_effect(outcome: SentenceOutcome) -> EffectOutcome:
    """Narrow SentenceOutcome to EffectOutcome (Pyright type guard)."""
    if not isinstance(outcome, EffectOutcome):
        raise AssertionError(f"expected EffectOutcome, got {type(outcome).__name__}")
    return outcome


def _as_ability(outcome: SentenceOutcome) -> AbilityOutcome:
    """Narrow SentenceOutcome to AbilityOutcome (Pyright type guard)."""
    if not isinstance(outcome, AbilityOutcome):
        raise AssertionError(f"expected AbilityOutcome, got {type(outcome).__name__}")
    return outcome


def _as_keyword(outcome: SentenceOutcome) -> KeywordOutcome:
    """Narrow SentenceOutcome to KeywordOutcome (Pyright type guard)."""
    if not isinstance(outcome, KeywordOutcome):
        raise AssertionError(f"expected KeywordOutcome, got {type(outcome).__name__}")
    return outcome


def _as_atom(eff: Any) -> Atom:
    """Narrow Effect to Atom (Pyright type guard)."""
    if not isinstance(eff, Atom):
        raise AssertionError(f"expected Atom, got {type(eff).__name__}")
    return eff


def _as_seq(eff: Any) -> Seq:
    """Narrow Effect to Seq (Pyright type guard)."""
    if not isinstance(eff, Seq):
        raise AssertionError(f"expected Seq, got {type(eff).__name__}")
    return eff


def _as_activated(ab: Any) -> ActivatedAbility:
    """Narrow Ability to ActivatedAbility (Pyright type guard)."""
    if not isinstance(ab, ActivatedAbility):
        raise AssertionError(f"expected ActivatedAbility, got {type(ab).__name__}")
    return ab


def _as_cost_modifier(ab: Any) -> CostModifier:
    """Narrow Ability to CostModifier (Pyright type guard)."""
    if not isinstance(ab, CostModifier):
        raise AssertionError(f"expected CostModifier, got {type(ab).__name__}")
    return ab


def _as_replacement(ab: Any) -> ReplacementAbility:
    """Narrow Ability to ReplacementAbility (Pyright type guard)."""
    assert isinstance(ab, ReplacementAbility), f"got {type(ab).__name__}"
    return ab


def _as_static(ab: Any) -> StaticAbility:
    """Narrow Ability to StaticAbility (Pyright type guard)."""
    assert isinstance(ab, StaticAbility), f"got {type(ab).__name__}"
    return ab


def _find_shape(sent: str) -> tuple[str, str, str]:
    """Find a shape entry by sentence."""
    for s in SHAPES:
        if s[0] == sent:
            return s
    raise AssertionError(f"sentence not in SHAPES: {sent!r}")


# ---------------------------------------------------------------------------
# Test: Template Inventory
# ---------------------------------------------------------------------------


class TestTemplateInventory(unittest.TestCase):
    """Verify the B5b template collection is well-formed."""

    def test_80_templates(self) -> None:
        self.assertEqual(len(TEMPLATES), 80)

    def test_unique_tids(self) -> None:
        tids = [t.tid for t in TEMPLATES]
        self.assertEqual(len(tids), len(set(tids)), "duplicate tid found")

    def test_all_bucket_b5b(self) -> None:
        for t in TEMPLATES:
            self.assertEqual(t.bucket, "B5b", f"{t.tid} has bucket {t.bucket}")

    def test_all_priority_100(self) -> None:
        for t in TEMPLATES:
            self.assertEqual(t.priority, 100, f"{t.tid} has priority {t.priority}")

    def test_registry_accepts_all(self) -> None:
        reg = _make_registry()
        self.assertEqual(len(reg), 80)


# ---------------------------------------------------------------------------
# Test: Shape Table Integrity
# ---------------------------------------------------------------------------


class TestShapeTable(unittest.TestCase):
    """Verify the embedded 91-shape table is consistent."""

    def test_91_entries(self) -> None:
        self.assertEqual(len(SHAPES), 91)

    def test_unique_sentences(self) -> None:
        sents = [s[0] for s in SHAPES]
        self.assertEqual(len(sents), len(set(sents)), "duplicate sentence in SHAPES")

    def test_category_counts(self) -> None:
        covered = sum(1 for s in SHAPES if s[1] == "COVERED")
        uncov = sum(1 for s in SHAPES if s[1] == "UNCOV")
        self.assertEqual(covered, 90, f"COVERED count {covered} != 90")
        self.assertEqual(uncov, 1, f"UNCOV count {uncov} != 1")

    def test_covered_tids_valid_and_unique_80(self) -> None:
        covered_tids = [s[2] for s in SHAPES if s[1] == "COVERED"]
        unique_tids = set(covered_tids)
        self.assertEqual(
            len(unique_tids), 80, f"expected 80 unique tids, got {len(unique_tids)}"
        )
        for tid in unique_tids:
            self.assertTrue(tid.startswith("B5b-"), f"bad tid: {tid}")

    def test_uncov_have_empty_tid(self) -> None:
        for sent, cat, tid in SHAPES:
            if cat == "UNCOV":
                self.assertEqual(
                    tid, "", f"shape with cat={cat} has tid={tid!r}: {sent[:40]}"
                )

    def test_covered_have_nonempty_tid(self) -> None:
        for sent, cat, tid in SHAPES:
            if cat == "COVERED":
                self.assertNotEqual(
                    tid, "", f"covered shape has empty tid: {sent[:40]}"
                )


# ---------------------------------------------------------------------------
# Test: PC-3 Matching
# ---------------------------------------------------------------------------


class TestMatching(unittest.TestCase):
    """PC-3: every B5b sentence fullmatches at most one template."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = _make_registry()

    def test_pc3_at_most_one_match(self) -> None:
        for sent, cat, _ in SHAPES:
            matches = self.reg.match(sent)
            self.assertLessEqual(
                len(matches),
                1,
                f"PC-3 violated ({len(matches)} matches): {sent[:60]}",
            )

    def test_covered_shapes_match_exactly_one(self) -> None:
        for sent, cat, expected_tid in SHAPES:
            if cat != "COVERED":
                continue
            matches = self.reg.match(sent)
            self.assertEqual(len(matches), 1, f"no match for covered: {sent[:60]}")
            self.assertEqual(
                matches[0].template.tid,
                expected_tid,
                f"tid mismatch for {sent[:40]}: got {matches[0].template.tid}, "
                f"expected {expected_tid}",
            )

    def test_uncovered_shapes_zero_matches(self) -> None:
        for sent, cat, _ in SHAPES:
            if cat != "UNCOV":
                continue
            matches = self.reg.match(sent)
            self.assertEqual(
                len(matches),
                0,
                f"unexpected match for uncovered: {sent[:60]}",
            )


# ---------------------------------------------------------------------------
# Test: Structural Assertions (per family)
# ---------------------------------------------------------------------------


class TestStructuralAssertions(unittest.TestCase):
    """Verify the built outcome structures for each template family."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = _make_registry()

    def _match_outcome(self, tid: str) -> SentenceOutcome:
        """Get the outcome for a specific tid by matching its shape."""
        for sent, cat, e_tid in SHAPES:
            if e_tid == tid and cat == "COVERED":
                matches = self.reg.match(sent)
                self.assertEqual(len(matches), 1)
                return matches[0].outcome
        raise AssertionError(f"no covered shape for tid {tid}")

    # -- Keyword outcomes (7 tids) --

    def test_keyword_outcomes(self) -> None:
        """B5b-flash/haste/hexproof/lifelink/menace/prowess/reach: KeywordOutcome."""
        expected = {
            "B5b-flash": Keyword.FLASH,
            "B5b-haste": Keyword.HASTE,
            "B5b-hexproof": Keyword.HEXPROOF,
            "B5b-lifelink": Keyword.LIFELINK,
            "B5b-menace": Keyword.MENACE,
            "B5b-prowess": Keyword.PROWESS,
            "B5b-reach": Keyword.REACH,
        }
        for tid, kw in expected.items():
            outcome = self._match_outcome(tid)
            kw_out = _as_keyword(outcome)
            self.assertEqual(kw_out.keyword, kw, f"{tid}")
            self.assertEqual(kw_out.params, (), f"{tid}")

    # -- Token creation --

    def test_token_demon(self) -> None:
        """B5b-token-demon: CREATE_TOKEN, TokenSpec(Demon, 5/5, FLYING)."""
        outcome = self._match_outcome("B5b-token-demon")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.CREATE_TOKEN)
        p = _pairs_dict(atom)
        spec = p["tokens"]
        self.assertIsInstance(spec, TokenSpec)
        self.assertEqual(spec.name, "Demon")
        self.assertEqual(spec.subtypes, ("Demon",))
        self.assertEqual(spec.power, QConst(5))
        self.assertEqual(spec.toughness, QConst(5))
        self.assertIn(Keyword.FLYING, spec.keywords)
        self.assertEqual(p["count"], QConst(1))

    def test_token_zombie(self) -> None:
        """B5b-token-zombie: CREATE_TOKEN, TokenSpec(Zombie, 2/2)."""
        outcome = self._match_outcome("B5b-token-zombie")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.CREATE_TOKEN)
        p = _pairs_dict(atom)
        spec = p["tokens"]
        self.assertIsInstance(spec, TokenSpec)
        self.assertEqual(spec.name, "Zombie")
        self.assertEqual(spec.subtypes, ("Zombie",))
        self.assertEqual(spec.power, QConst(2))
        self.assertEqual(spec.toughness, QConst(2))
        self.assertEqual(spec.keywords, ())
        self.assertEqual(p["count"], QConst(1))

    # -- Simple effect verbs --

    def test_cont_discard(self) -> None:
        """B5b-cont-discard: merged MOVE_ZONE (T4 P1a), YOU, 1 from HAND."""
        outcome = self._match_outcome("B5b-cont-discard")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.MOVE_ZONE)
        p = _pairs_dict(atom)
        self.assertEqual(p["destination"], Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU))
        self.assertEqual(p["from"], Zone(ZoneKind.HAND, ControllerRef.YOU))
        self.assertEqual(p["controller"], ControllerRef.YOU)
        cards = p["cards"]
        self.assertIsInstance(cards, Selector)
        self.assertEqual(cards.zones[0].kind, ZoneKind.HAND)

    def test_cont_draw(self) -> None:
        """B5b-cont-draw: DRAW, YOU, QConst(1)."""
        outcome = self._match_outcome("B5b-cont-draw")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.DRAW)
        p = _pairs_dict(atom)
        self.assertEqual(p["controller"], ControllerRef.YOU)
        self.assertEqual(p["amount"], QConst(1))

    def test_cont_gain_4(self) -> None:
        """B5b-cont-gain-4: GAIN_LIFE, YOU, QConst(4)."""
        outcome = self._match_outcome("B5b-cont-gain-4")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.GAIN_LIFE)
        p = _pairs_dict(atom)
        self.assertEqual(p["controller"], ControllerRef.YOU)
        self.assertEqual(p["amount"], QConst(4))

    def test_cont_gain_mv(self) -> None:
        """B5b-cont-gain-mv: GAIN_LIFE, YOU, QProp(MANA_VALUE)."""
        outcome = self._match_outcome("B5b-cont-gain-mv")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.GAIN_LIFE)
        p = _pairs_dict(atom)
        self.assertEqual(p["controller"], ControllerRef.YOU)
        amount = p["amount"]
        self.assertIsInstance(amount, QProp)
        self.assertEqual(amount.field, QPropField.MANA_VALUE)

    def test_look_3(self) -> None:
        """B5b-look-3: LOOK_AT, YOU, QConst(3)."""
        outcome = self._match_outcome("B5b-look-3")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.LOOK_AT)
        p = _pairs_dict(atom)
        self.assertEqual(p["controller"], ControllerRef.YOU)
        self.assertEqual(p["count"], QConst(3))

    # -- Put counter (3 concrete rows, 1 tid) --

    def test_put_counter_each_creature(self) -> None:
        """B5b-put-counter: each creature you control → PUT_COUNTER."""
        sent = "Put a +1/+1 counter on each creature you control."
        matches = self.reg.match(sent)
        self.assertEqual(len(matches), 1)
        outcome = matches[0].outcome
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.PUT_COUNTER)
        p = _pairs_dict(atom)
        self.assertEqual(p["counter_kind"], CounterKind.PLUS_1_PLUS_1)
        self.assertEqual(p["count"], QConst(1))
        target = p["target"]
        self.assertIsInstance(target, Selector)
        self.assertEqual(target.mode, SelectorMode.ALL)

    def test_put_counter_up_to_two(self) -> None:
        """B5b-put-counter: each of up to two target creatures — TARGET +
        QAtMost(2) (round 8 / C17 targeted designation 1..2)."""
        sent = "Put a +1/+1 counter on each of up to two target creatures."
        matches = self.reg.match(sent)
        self.assertEqual(len(matches), 1)
        outcome = matches[0].outcome
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.PUT_COUNTER)
        p = _pairs_dict(atom)
        target = p["target"]
        self.assertIsInstance(target, Selector)
        self.assertEqual(target.mode, SelectorMode.TARGET)
        self.assertEqual(target.count, QAtMost(2))

    def test_put_counter_target_creature(self) -> None:
        """B5b-put-counter: target creature you control."""
        sent = "Put a +1/+1 counter on target creature you control."
        matches = self.reg.match(sent)
        self.assertEqual(len(matches), 1)
        outcome = matches[0].outcome
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.PUT_COUNTER)
        p = _pairs_dict(atom)
        target = p["target"]
        self.assertIsInstance(target, Selector)
        self.assertEqual(target.mode, SelectorMode.TARGET)

    # -- Seq effects --

    def test_seq_modpt_trample(self) -> None:
        """B5b-seq-modpt-trample: Seq(MODIFY_PT, GRANT_ABILITY TRAMPLE)."""
        outcome = self._match_outcome("B5b-seq-modpt-trample")
        eff = _as_effect(outcome)
        seq = _as_seq(eff.effect)
        self.assertEqual(len(seq.steps), 2)
        atom0 = _as_atom(seq.steps[0])
        self.assertEqual(atom0.verb, Verb.MODIFY_PT)
        atom1 = _as_atom(seq.steps[1])
        self.assertEqual(atom1.verb, Verb.GRANT_ABILITY)
        p1 = _pairs_dict(atom1)
        ka = p1["ability"]
        self.assertIsInstance(ka, KeywordAbility)
        self.assertEqual(ka.keyword, Keyword.TRAMPLE)

    def test_perm_hex_ind(self) -> None:
        """B5b-perm-hex-ind: Seq(GRANT_ABILITY HEXPROOF, GRANT_ABILITY INDESTRUCTIBLE)."""
        outcome = self._match_outcome("B5b-perm-hex-ind")
        eff = _as_effect(outcome)
        seq = _as_seq(eff.effect)
        self.assertEqual(len(seq.steps), 2)
        atom0 = _as_atom(seq.steps[0])
        self.assertEqual(atom0.verb, Verb.GRANT_ABILITY)
        atom1 = _as_atom(seq.steps[1])
        self.assertEqual(atom1.verb, Verb.GRANT_ABILITY)
        p0 = _pairs_dict(atom0)
        p1 = _pairs_dict(atom1)
        self.assertIsInstance(p0["ability"], KeywordAbility)
        self.assertEqual(p0["ability"].keyword, Keyword.HEXPROOF)
        self.assertIsInstance(p1["ability"], KeywordAbility)
        self.assertEqual(p1["ability"].keyword, Keyword.INDESTRUCTIBLE)

    def test_scr_reveal(self) -> None:
        """B5b-scr-reveal: Seq(SCRY 3, REVEAL 1)."""
        outcome = self._match_outcome("B5b-scr-reveal")
        eff = _as_effect(outcome)
        seq = _as_seq(eff.effect)
        self.assertEqual(len(seq.steps), 2)
        atom0 = _as_atom(seq.steps[0])
        self.assertEqual(atom0.verb, Verb.SCRY)
        atom1 = _as_atom(seq.steps[1])
        self.assertEqual(atom1.verb, Verb.REVEAL)
        p0 = _pairs_dict(atom0)
        self.assertEqual(p0["count"], QConst(3))

    def test_search_shuffle(self) -> None:
        """B5b-search-shuffle: Seq(SEARCH, SHUFFLE)."""
        outcome = self._match_outcome("B5b-search-shuffle")
        eff = _as_effect(outcome)
        seq = _as_seq(eff.effect)
        self.assertEqual(len(seq.steps), 2)
        atom0 = _as_atom(seq.steps[0])
        self.assertEqual(atom0.verb, Verb.SEARCH)
        atom1 = _as_atom(seq.steps[1])
        self.assertEqual(atom1.verb, Verb.SHUFFLE)

    def test_seq_modpt_firststrike(self) -> None:
        """B5b-seq-modpt-firststrike: Seq(MODIFY_PT +3/+0, GRANT_ABILITY FIRST_STRIKE)."""
        outcome = self._match_outcome("B5b-seq-modpt-firststrike")
        eff = _as_effect(outcome)
        seq = _as_seq(eff.effect)
        self.assertEqual(len(seq.steps), 2)
        atom0 = _as_atom(seq.steps[0])
        self.assertEqual(atom0.verb, Verb.MODIFY_PT)
        p0 = _pairs_dict(atom0)
        self.assertIsInstance(p0["power"], PtDelta)
        self.assertEqual(p0["power"].direction, PtDirection.INCREASE)
        self.assertEqual(p0["power"].magnitude, QConst(3))
        self.assertIsInstance(p0["toughness"], PtDelta)
        self.assertEqual(p0["toughness"].magnitude, QConst(0))
        atom1 = _as_atom(seq.steps[1])
        self.assertEqual(atom1.verb, Verb.GRANT_ABILITY)
        p1 = _pairs_dict(atom1)
        ka = p1["ability"]
        self.assertIsInstance(ka, KeywordAbility)
        self.assertEqual(ka.keyword, Keyword.FIRST_STRIKE)

    def test_seq_modpt_hexproof(self) -> None:
        """B5b-seq-modpt-hexproof: Seq(MODIFY_PT +1/+1, GRANT_ABILITY HEXPROOF)."""
        outcome = self._match_outcome("B5b-seq-modpt-hexproof")
        eff = _as_effect(outcome)
        seq = _as_seq(eff.effect)
        self.assertEqual(len(seq.steps), 2)
        atom0 = _as_atom(seq.steps[0])
        self.assertEqual(atom0.verb, Verb.MODIFY_PT)
        atom1 = _as_atom(seq.steps[1])
        self.assertEqual(atom1.verb, Verb.GRANT_ABILITY)
        p1 = _pairs_dict(atom1)
        ka = p1["ability"]
        self.assertIsInstance(ka, KeywordAbility)
        self.assertEqual(ka.keyword, Keyword.HEXPROOF)

    # -- Modify PT --

    def test_modpt_plus(self) -> None:
        """B5b-modpt-plus: MODIFY_PT, TARGET, +N/+N, EOT."""
        # Test both concrete rows
        for sent, expected_p, expected_t in [
            ("Target creature gets +1/+0 until end of turn.", 1, 0),
            ("Target creature gets +4/+4 until end of turn.", 4, 4),
        ]:
            matches = self.reg.match(sent)
            self.assertEqual(len(matches), 1)
            outcome = matches[0].outcome
            eff = _as_effect(outcome)
            atom = _as_atom(eff.effect)
            self.assertEqual(atom.verb, Verb.MODIFY_PT)
            p = _pairs_dict(atom)
            self.assertIsInstance(p["power"], PtDelta)
            self.assertEqual(p["power"].direction, PtDirection.INCREASE)
            self.assertEqual(p["power"].magnitude, QConst(expected_p))
            self.assertIsInstance(p["toughness"], PtDelta)
            self.assertEqual(p["toughness"].magnitude, QConst(expected_t))
            self.assertEqual(p["duration"], DurationEot())

    def test_modpt_minus(self) -> None:
        """B5b-modpt-minus: MODIFY_PT, TARGET, -N/-N, EOT."""
        outcome = self._match_outcome("B5b-modpt-minus")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.MODIFY_PT)
        p = _pairs_dict(atom)
        self.assertIsInstance(p["power"], PtDelta)
        self.assertEqual(p["power"].direction, PtDirection.DECREASE)
        self.assertEqual(p["power"].magnitude, QConst(4))
        self.assertIsInstance(p["toughness"], PtDelta)
        self.assertEqual(p["toughness"].magnitude, QConst(4))
        self.assertEqual(p["duration"], DurationEot())

    def test_modpt_x(self) -> None:
        """B5b-modpt-x: MODIFY_PT, +X/+X, EOT."""
        outcome = self._match_outcome("B5b-modpt-x")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.MODIFY_PT)
        p = _pairs_dict(atom)
        self.assertIsInstance(p["power"], PtDelta)
        self.assertIsInstance(p["power"].magnitude, QX)
        self.assertIsInstance(p["toughness"], PtDelta)
        self.assertIsInstance(p["toughness"].magnitude, QX)
        self.assertEqual(p["duration"], DurationEot())

    # -- Damage --

    def test_named_damage(self) -> None:
        """B5b-named-damage: DEAL_DAMAGE, target creature or planeswalker."""
        for sent, expected_amt in [
            (
                "Scorching Dragonfire deals 3 damage to target creature or planeswalker.",
                3,
            ),
            ("Soul Sear deals 5 damage to target creature or planeswalker.", 5),
        ]:
            matches = self.reg.match(sent)
            self.assertEqual(len(matches), 1)
            outcome = matches[0].outcome
            eff = _as_effect(outcome)
            atom = _as_atom(eff.effect)
            self.assertEqual(atom.verb, Verb.DEAL_DAMAGE)
            p = _pairs_dict(atom)
            self.assertEqual(p["amount"], QConst(expected_amt))
            target = p["target"]
            self.assertIsInstance(target, Selector)
            self.assertEqual(target.mode, SelectorMode.TARGET)

    def test_damage_any(self) -> None:
        """B5b-damage-any: DEAL_DAMAGE, any target, QConst(2)."""
        outcome = self._match_outcome("B5b-damage-any")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.DEAL_DAMAGE)
        p = _pairs_dict(atom)
        self.assertEqual(p["amount"], QConst(2))
        target = p["target"]
        self.assertIsInstance(target, Selector)
        self.assertEqual(target.mode, SelectorMode.TARGET)
        # AMENDED r17-2 (geyser-FIX): "any target" is the battlefield
        # FOr(Creature, Planeswalker) idiom — hidden zones are not a
        # target population (CR 109.5); players join via widening.
        self.assertEqual(target.zones[0].kind, ZoneKind.BATTLEFIELD)
        self.assertIsInstance(target.filter, FOr)

    # -- Zone moves --

    def test_return_creatures_battlefield(self) -> None:
        """B5b-return-creatures-battlefield: MOVE_ZONE, GRAVEYARD → BATTLEFIELD."""
        outcome = self._match_outcome("B5b-return-creatures-battlefield")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.MOVE_ZONE)
        p = _pairs_dict(atom)
        cards = p["cards"]
        self.assertIsInstance(cards, Selector)
        self.assertEqual(cards.zones[0].kind, ZoneKind.GRAVEYARD)
        dest = p["destination"]
        self.assertIsInstance(dest, Zone)
        self.assertEqual(dest.kind, ZoneKind.BATTLEFIELD)

    def test_return_cards_hand(self) -> None:
        """B5b-return-cards-hand: MOVE_ZONE, GRAVEYARD → HAND (2 variants)."""
        for sent in [
            "Return target permanent card from your graveyard to your hand.",
            "Return up to two target creature cards from your graveyard to your hand.",
        ]:
            matches = self.reg.match(sent)
            self.assertEqual(len(matches), 1)
            outcome = matches[0].outcome
            eff = _as_effect(outcome)
            atom = _as_atom(eff.effect)
            self.assertEqual(atom.verb, Verb.MOVE_ZONE)
            p = _pairs_dict(atom)
            dest = p["destination"]
            self.assertIsInstance(dest, Zone)
            self.assertEqual(dest.kind, ZoneKind.HAND)

    def test_return_spell_creature_owner_hand(self) -> None:
        """B5b-return-spell-creature-owner-hand: MOVE_ZONE spell/creature → owner's hand."""
        outcome = self._match_outcome("B5b-return-spell-creature-owner-hand")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.MOVE_ZONE)
        p = _pairs_dict(atom)
        cards = p["cards"]
        self.assertIsInstance(cards, Selector)
        self.assertEqual(cards.mode, SelectorMode.TARGET)
        # R0 zone-fold: spell-on-stack OR permanent is ONE zone set;
        # canonical order BATTLEFIELD < STACK.
        self.assertEqual(
            cards.zones,
            (
                Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),
                Zone(kind=ZoneKind.STACK, controller=ControllerRef.ANY),
            ),
        )
        # Spell-or-creature disjunction: FOr(FNot(IS_PERMANENT), TYPE_EQ Creature)
        flt = cards.filter
        self.assertIsInstance(flt, FOr)
        # R1a canonicalization: FOr children construction-sorted, so the two
        # members are pinned by IDENTITY (exactly one negation + exactly one
        # TYPE_EQ Creature atom), and the order by the canonicalization law.
        self.assertEqual(list(flt.children), sorted(flt.children, key=canonical_json))
        self.assertEqual(len(flt.children), 2)
        negation = next(c for c in flt.children if isinstance(c, FNot))
        creature = next(c for c in flt.children if isinstance(c, FAtom))
        self.assertIs(negation.inner.pred, FAtomPred.IS_PERMANENT)
        self.assertEqual(creature.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(creature.string_value, "Creature")
        dest = p["destination"]
        self.assertIsInstance(dest, Zone)
        self.assertEqual(dest.kind, ZoneKind.HAND)
        self.assertEqual(dest.controller, ControllerRef.OWNER)

    # -- Scry --

    def test_scr(self) -> None:
        """B5b-scr: SCRY, YOU, QConst(1)."""
        outcome = self._match_outcome("B5b-scr")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.SCRY)
        p = _pairs_dict(atom)
        self.assertEqual(p["controller"], ControllerRef.YOU)
        self.assertEqual(p["count"], QConst(1))

    # -- Tap / Sacrifice / Reveal / Discard --

    def test_tap_2_target(self) -> None:
        """B5b-tap-2-target: TAP, up to two target creatures — TARGET +
        QAtMost(2) (round 8 / C17)."""
        outcome = self._match_outcome("B5b-tap-2-target")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.TAP)
        p = _pairs_dict(atom)
        target = p["target"]
        self.assertIsInstance(target, Selector)
        self.assertEqual(target.mode, SelectorMode.TARGET)
        self.assertEqual(target.count, QAtMost(2))

    def test_reveal_hand(self) -> None:
        """B5b-reveal-hand: REVEAL, TARGET_PLAYER, QUnbounded."""
        outcome = self._match_outcome("B5b-reveal-hand")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.REVEAL)
        p = _pairs_dict(atom)
        self.assertEqual(p["controller"], ControllerRef.TARGET_PLAYER)
        self.assertIsInstance(p["count"], QUnbounded)

    def test_sacr_flying(self) -> None:
        """B5b-sacr-flying: SACRIFICE, CHOOSE, Creature+FLYING."""
        outcome = self._match_outcome("B5b-sacr-flying")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.SACRIFICE)
        p = _pairs_dict(atom)
        target = p["target"]
        self.assertIsInstance(target, Selector)
        self.assertEqual(target.mode, SelectorMode.CHOOSE)
        canon = canonical_json(target)
        self.assertIn("FLYING", canon)

    def test_discard_target_2(self) -> None:
        """B5b-discard-target-2: merged MOVE_ZONE (T4 P1a), TARGET_PLAYER,
        2 cards."""
        outcome = self._match_outcome("B5b-discard-target-2")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.MOVE_ZONE)
        p = _pairs_dict(atom)
        self.assertEqual(
            p["destination"], Zone(ZoneKind.GRAVEYARD, ControllerRef.TARGET_PLAYER)
        )
        self.assertEqual(p["from"], Zone(ZoneKind.HAND, ControllerRef.TARGET_PLAYER))
        self.assertEqual(p["controller"], ControllerRef.TARGET_PLAYER)
        cards = p["cards"]
        self.assertIsInstance(cards, Selector)
        self.assertEqual(cards.zones[0].kind, ZoneKind.HAND)

    # -- Ability outcomes (activated abilities) --

    def test_sacr_grant(self) -> None:
        """B5b-sacr-grant: ActivatedAbility, CostSacrifice, GRANT_ABILITY."""
        outcome = self._match_outcome("B5b-sacr-grant")
        ab_out = _as_ability(outcome)
        ab = _as_activated(ab_out.ability)
        self.assertEqual(len(ab.cost.parts), 1)
        self.assertIsInstance(ab.cost.parts[0], CostSacrifice)
        atom = _as_atom(ab.effect)
        self.assertEqual(atom.verb, Verb.GRANT_ABILITY)
        p = _pairs_dict(atom)
        ka = p["ability"]
        self.assertIsInstance(ka, KeywordAbility)
        self.assertEqual(ka.keyword, Keyword.INDESTRUCTIBLE)

    def test_tap_spirits(self) -> None:
        """B5b-tap-spirits: ActivatedAbility, CostTap, TAP."""
        outcome = self._match_outcome("B5b-tap-spirits")
        ab_out = _as_ability(outcome)
        ab = _as_activated(ab_out.ability)
        self.assertEqual(len(ab.cost.parts), 1)
        self.assertIsInstance(ab.cost.parts[0], CostTap)
        atom = _as_atom(ab.effect)
        self.assertEqual(atom.verb, Verb.TAP)

    # -- Cost modifiers --

    def test_noncreature_cost_modifier(self) -> None:
        """B5b-noncreature-cost-more: CostModifier(FNot(Creature), ANY, +{1})."""
        outcome = self._match_outcome("B5b-noncreature-cost-more")
        ab_out = _as_ability(outcome)
        mod = _as_cost_modifier(ab_out.ability)
        self.assertEqual(mod.controller_ref, ControllerRef.ANY)
        delta = mod.delta
        assert isinstance(delta, CostDeltaIncreaseGeneric)
        self.assertEqual(delta.amount, QConst(1))
        flt = mod.filter
        assert isinstance(flt, FNot)
        leaf = flt.inner
        assert isinstance(leaf, FAtom)
        self.assertEqual(leaf.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(leaf.string_value, "Creature")

    # -- Replacement effects (grammar round 5 — doc-07 batch, 8 tids) --

    def test_repl_died_gain_life(self) -> None:
        """B5b-repl-died-gain-life: ReplacementAbility(LifeGainedEvent(YOU),
        DIED_THIS_TURN, GAIN_LIFE 8)."""
        outcome = self._match_outcome("B5b-repl-died-gain-life")
        ab = _as_replacement(_as_ability(outcome).ability)
        event = ab.event
        assert isinstance(event, LifeGainedEvent)
        self.assertIs(event.actor.who, ControllerRef.YOU)
        cond = ab.condition
        assert isinstance(cond, FAtom)
        self.assertEqual(cond.pred, FAtomPred.DIED_THIS_TURN)
        atom = _as_atom(ab.action)
        self.assertEqual(atom.verb, Verb.GAIN_LIFE)
        p = _pairs_dict(atom)
        self.assertEqual(p["controller"], ControllerRef.YOU)
        self.assertEqual(p["amount"], QConst(8))

    def test_repl_nontoken_enter_exile(self) -> None:
        """B5b-repl-nontoken-enter-exile: ANY→BATTLEFIELD zone change of a
        nontoken creature, not-cast condition, exile the event referent."""
        outcome = self._match_outcome("B5b-repl-nontoken-enter-exile")
        ab = _as_replacement(_as_ability(outcome).ability)
        event = ab.event
        assert isinstance(event, ZoneChangeEvent)
        self.assertEqual(event.from_zone.kind, ZoneKind.ANY)
        self.assertEqual(event.to_zone.kind, ZoneKind.BATTLEFIELD)
        subject = event.subject
        assert isinstance(subject, FAnd)
        type_leaf, not_token = subject.children
        assert isinstance(type_leaf, FAtom)
        self.assertEqual(type_leaf.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(type_leaf.string_value, "Creature")
        assert isinstance(not_token, FNot)
        assert isinstance(not_token.inner, FAtom)
        self.assertEqual(not_token.inner.pred, FAtomPred.IS_TOKEN)
        cond = ab.condition
        assert isinstance(cond, FNot)
        was_cast = cond.inner
        assert isinstance(was_cast, FAtom)
        self.assertEqual(was_cast.pred, FAtomPred.WAS_CAST_THIS_TURN)
        self.assertEqual(was_cast.who, ControllerRef.ANY)
        atom = _as_atom(ab.action)
        # T4 P1a: the exile shape is the merged MOVE_ZONE atom.
        self.assertEqual(atom.verb, Verb.MOVE_ZONE)
        p = _pairs_dict(atom)
        self.assertEqual(p["destination"], Zone(ZoneKind.EXILE, ControllerRef.OWNER))
        target = p["target"]
        assert isinstance(target, Selector)
        self.assertEqual(target.referent, "event")

    def test_repl_triple_damage(self) -> None:
        """B5b-repl-triple-damage: DamageDealtEvent(X, source you control) →
        DEAL_DAMAGE 3 * QProp(event, AMOUNT) to the event referent."""
        outcome = self._match_outcome("B5b-repl-triple-damage")
        ab = _as_replacement(_as_ability(outcome).ability)
        event = ab.event
        assert isinstance(event, DamageDealtEvent)
        self.assertIsInstance(event.amount, QX)
        source = event.source
        assert isinstance(source, FAtom)
        self.assertEqual(source.pred, FAtomPred.CONTROLLER_IS)
        self.assertEqual(source.who, ControllerRef.YOU)
        self.assertEqual(event.filter, FAnd(children=()))
        self.assertIsNone(ab.condition)
        atom = _as_atom(ab.action)
        self.assertEqual(atom.verb, Verb.DEAL_DAMAGE)
        p = _pairs_dict(atom)
        # dealer role = "a source you control" (round 8 / R8-5, C-4)
        dealer = p["dealer"]
        assert isinstance(dealer, FAtom)
        self.assertIs(dealer.pred, FAtomPred.CONTROLLER_IS)
        self.assertEqual(dealer.who, ControllerRef.YOU)
        target = p["target"]
        assert isinstance(target, Selector)
        self.assertEqual(target.referent, "event")
        amount = p["amount"]
        assert isinstance(amount, QBin)
        self.assertEqual(amount.op, QBinOp.MUL)
        self.assertEqual(amount.left, QConst(3))
        self.assertEqual(amount.right, QProp("event", QPropField.AMOUNT))

    def test_repl_counter_plus_one(self) -> None:
        """B5b-repl-counter-plus-one: CounterPlacedEvent(+1/+1, QAtLeast(1))
        → PUT_COUNTER QBin(ADD, QProp(event, COUNTER_COUNT), 1)."""
        outcome = self._match_outcome("B5b-repl-counter-plus-one")
        ab = _as_replacement(_as_ability(outcome).ability)
        event = ab.event
        assert isinstance(event, CounterPlacedEvent)
        self.assertEqual(event.counter_kind, CounterKind.PLUS_1_PLUS_1)
        self.assertEqual(event.count, QAtLeast(1))
        flt = event.filter
        assert isinstance(flt, FAnd)
        # R1a canonicalization: FAnd children construction-sorted; members by
        # pred, order by the canonicalization law.
        self.assertEqual(list(flt.children), sorted(flt.children, key=canonical_json))
        by_pred = {c.pred: c for c in flt.children}
        self.assertEqual(len(by_pred), 2)
        type_leaf = by_pred[FAtomPred.TYPE_EQ]
        controller_leaf = by_pred[FAtomPred.CONTROLLER_IS]
        assert isinstance(type_leaf, FAtom)
        self.assertEqual(type_leaf.string_value, "Creature")
        assert isinstance(controller_leaf, FAtom)
        self.assertEqual(controller_leaf.who, ControllerRef.YOU)
        self.assertIsNone(ab.condition)
        atom = _as_atom(ab.action)
        self.assertEqual(atom.verb, Verb.PUT_COUNTER)
        p = _pairs_dict(atom)
        target = p["target"]
        assert isinstance(target, Selector)
        self.assertEqual(target.referent, "event")
        self.assertEqual(p["counter_kind"], CounterKind.PLUS_1_PLUS_1)
        count = p["count"]
        assert isinstance(count, QBin)
        self.assertEqual(count.op, QBinOp.ADD)
        self.assertEqual(count.left, QProp("event", QPropField.COUNTER_COUNT))
        self.assertEqual(count.right, QConst(1))

    def test_repl_die_exile(self) -> None:
        """B5b-repl-die-exile: CreatureDiesEvent(IS_ANY_TARGET) → exile the
        event referent."""
        outcome = self._match_outcome("B5b-repl-die-exile")
        ab = _as_replacement(_as_ability(outcome).ability)
        event = ab.event
        assert isinstance(event, CreatureDiesEvent)
        flt = event.filter
        assert isinstance(flt, FAtom)
        self.assertEqual(flt.pred, FAtomPred.IS_ANY_TARGET)
        self.assertIsNone(ab.condition)
        atom = _as_atom(ab.action)
        # T4 P1a: the exile shape is the merged MOVE_ZONE atom.
        self.assertEqual(atom.verb, Verb.MOVE_ZONE)
        p = _pairs_dict(atom)
        self.assertEqual(p["destination"], Zone(ZoneKind.EXILE, ControllerRef.OWNER))
        target = p["target"]
        assert isinstance(target, Selector)
        self.assertEqual(target.referent, "event")

    def test_repl_graveyard_exile(self) -> None:
        """B5b-repl-graveyard-exile: STACK(any)→GRAVEYARD(you) of the
        spell's target → exile the event referent."""
        outcome = self._match_outcome("B5b-repl-graveyard-exile")
        ab = _as_replacement(_as_ability(outcome).ability)
        event = ab.event
        assert isinstance(event, ZoneChangeEvent)
        self.assertEqual(event.from_zone.kind, ZoneKind.STACK)
        self.assertEqual(event.from_zone.controller, ControllerRef.ANY)
        self.assertEqual(event.to_zone.kind, ZoneKind.GRAVEYARD)
        self.assertEqual(event.to_zone.controller, ControllerRef.YOU)
        subject = event.subject
        assert isinstance(subject, FAtom)
        self.assertEqual(subject.pred, FAtomPred.IS_ANY_TARGET)
        self.assertIsNone(ab.condition)
        atom = _as_atom(ab.action)
        # T4 P1a: the exile shape is the merged MOVE_ZONE atom.
        self.assertEqual(atom.verb, Verb.MOVE_ZONE)
        p = _pairs_dict(atom)
        self.assertEqual(p["destination"], Zone(ZoneKind.EXILE, ControllerRef.OWNER))
        target = p["target"]
        assert isinstance(target, Selector)
        self.assertEqual(target.referent, "event")

    def test_counter_unless_pays(self) -> None:
        """B5b-counter-unless-pays: CostModifier on the spell's target,
        controller_ref=Selector(referent='target'), delta +{3}, flying
        gate (C7)."""
        outcome = self._match_outcome("B5b-counter-unless-pays")
        mod = _as_cost_modifier(_as_ability(outcome).ability)
        flt = mod.filter
        assert isinstance(flt, FAtom)
        self.assertEqual(flt.pred, FAtomPred.IS_ANY_TARGET)
        controller_ref = mod.controller_ref
        assert isinstance(controller_ref, Selector)
        self.assertEqual(controller_ref.referent, "target")
        self.assertEqual(controller_ref.mode, SelectorMode.CHOOSE)
        self.assertEqual(controller_ref.count, QConst(1))
        self.assertEqual(controller_ref.zones[0].kind, ZoneKind.ANY)
        self.assertEqual(controller_ref.zones[0].controller, ControllerRef.ANY)
        delta = mod.delta
        assert isinstance(delta, CostDeltaIncreaseGeneric)
        self.assertEqual(delta.amount, QConst(3))
        cond = mod.condition
        assert isinstance(cond, FAnd)
        # R1a canonicalization: FAnd children construction-sorted; all three
        # conjuncts pinned by pred, order by the canonicalization law.
        self.assertEqual(list(cond.children), sorted(cond.children, key=canonical_json))
        by_pred = {c.pred: c for c in cond.children}
        self.assertEqual(len(by_pred), 3)
        type_leaf = by_pred[FAtomPred.TYPE_EQ]
        keyword_leaf = by_pred[FAtomPred.KEYWORD_HAS]
        controller_leaf = by_pred[FAtomPred.CONTROLLER_IS]
        assert isinstance(type_leaf, FAtom)
        self.assertEqual(type_leaf.string_value, "Creature")
        assert isinstance(keyword_leaf, FAtom)
        self.assertEqual(keyword_leaf.keyword, Keyword.FLYING)
        assert isinstance(controller_leaf, FAtom)
        self.assertEqual(controller_leaf.who, ControllerRef.YOU)

    def test_repl_draw_not_first(self) -> None:
        """B5b-repl-draw-not-first: CardDrawnEvent(YOU) with
        NOT_FIRST_DRAW_THIS_STEP condition → draw 2."""
        outcome = self._match_outcome("B5b-repl-draw-not-first")
        ab = _as_replacement(_as_ability(outcome).ability)
        event = ab.event
        assert isinstance(event, CardDrawnEvent)
        self.assertIs(event.actor.who, ControllerRef.YOU)
        cond = ab.condition
        assert isinstance(cond, FAtom)
        self.assertEqual(cond.pred, FAtomPred.NOT_FIRST_DRAW_THIS_STEP)
        self.assertEqual(cond.who, ControllerRef.YOU)
        atom = _as_atom(ab.action)
        self.assertEqual(atom.verb, Verb.DRAW)
        p = _pairs_dict(atom)
        self.assertEqual(p["controller"], ControllerRef.YOU)
        self.assertEqual(p["amount"], QConst(2))

    # ------------------------------------------------------------------
    # Round-6 batch (Gadrak, Kinetic Augur)
    # ------------------------------------------------------------------

    def test_gadrak_cant_attack_structure(self) -> None:
        """C9 + C10: StaticAbility.condition = FNot(CONTROLLER_COUNT_GE
        Artifact 4) over PREVENT_EFFECT/DeclareAttackersEvent(IS_SOURCE)."""
        outcome = self._match_outcome("B5b-gadrak-cant-attack-unless-artifacts")
        ab = _as_static(_as_ability(outcome).ability)
        cond = ab.condition
        if not isinstance(cond, FNot):
            self.fail(f"expected FNot condition, got {type(cond)}")
        gate = cond.inner
        if not isinstance(gate, FAtom):
            self.fail(f"expected FAtom gate, got {type(gate)}")
        self.assertEqual(gate.pred, FAtomPred.CONTROLLER_COUNT_GE)
        self.assertEqual(gate.count, QConst(4))
        inner_filter = gate.inner_filter
        if not isinstance(inner_filter, FAtom):
            self.fail(f"expected FAtom inner_filter, got {type(inner_filter)}")
        self.assertEqual(inner_filter.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(inner_filter.string_value, "Artifact")
        atom = _as_atom(ab.effect)
        self.assertEqual(atom.verb, Verb.PREVENT_EFFECT)
        p = _pairs_dict(atom)
        condition = p["condition"]
        assert isinstance(condition, FAtom)
        self.assertEqual(condition.pred, FAtomPred.IS_SOURCE)
        event = p["event"]
        if not isinstance(event, DeclareAttackersEvent):
            self.fail(f"expected DeclareAttackersEvent, got {type(event)}")
        self.assertEqual(event.filter, FAtom(pred=FAtomPred.IS_SOURCE))
        self.assertNotIn("duration", p)

    def test_set_pt_power_gy_count_structure(self) -> None:
        """R6-3: SET_PT with the power role ONLY, quantity = QCount over
        the instant-or-sorcery graveyard selector."""
        outcome = self._match_outcome("B5b-set-pt-power-gy-instant-sorcery")
        ab = _as_static(_as_ability(outcome).ability)
        atom = _as_atom(ab.effect)
        self.assertEqual(atom.verb, Verb.SET_PT)
        p = _pairs_dict(atom)
        self.assertIn("power", p)
        self.assertNotIn("toughness", p)
        target = p["target"]
        assert isinstance(target, Selector)
        self.assertEqual(target.mode, SelectorMode.CHOOSE)
        assert isinstance(target.filter, FAtom)
        self.assertEqual(target.filter.pred, FAtomPred.IS_SOURCE)
        power = p["power"]
        if not isinstance(power, QCount):
            self.fail(f"expected QCount power, got {type(power)}")
        cards = power.selector
        self.assertEqual(cards.mode, SelectorMode.ALL)
        self.assertEqual(cards.zones[0].kind, ZoneKind.GRAVEYARD)
        self.assertEqual(cards.zones[0].controller, ControllerRef.YOU)
        filt = cards.filter
        if not isinstance(filt, FOr):
            self.fail(f"expected FOr filter, got {type(filt)}")
        names = [c.string_value for c in filt.children if isinstance(c, FAtom)]
        self.assertEqual(names, ["Instant", "Sorcery"])


# ---------------------------------------------------------------------------
# Test: Canonical Stability (PC-4)
# ---------------------------------------------------------------------------


class TestCanonicalStability(unittest.TestCase):
    """Building each covered outcome twice yields identical canonical_json."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = _make_registry()

    def test_all_covered_shapes_stable(self) -> None:
        seen: set[str] = set()
        for sent, cat, tid in SHAPES:
            if cat != "COVERED":
                continue
            matches = self.reg.match(sent)
            self.assertEqual(len(matches), 1)
            outcome = matches[0].outcome
            inner = _inner_node(outcome)
            canon1 = canonical_json(inner)
            # Rebuild
            matches2 = self.reg.match(sent)
            outcome2 = matches2[0].outcome
            inner2 = _inner_node(outcome2)
            canon2 = canonical_json(inner2)
            self.assertEqual(
                canon1,
                canon2,
                f"canonical instability for {tid} ({sent[:40]})",
            )
            seen.add(tid)
        self.assertEqual(len(seen), 80, f"only {len(seen)} unique tids tested")


# ---------------------------------------------------------------------------
# Test: End-to-End compile_card
# ---------------------------------------------------------------------------


class TestEndToEndCompile(unittest.TestCase):
    """Full compile_card pipeline with realistic RawCard stubs."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = _make_registry()

    def test_shock_damage_any(self) -> None:
        """Shock: Shock deals 2 damage to any target. → SpellAbility, no unparsed."""
        raw = _raw(
            "Shock",
            ("Shock deals 2 damage to any target.",),
            types=("Instant",),
            colors=("B", "R"),
            mana_cost_raw="{B}{R}",
            mana_value=2,
        )
        result = compile_card(raw, self.reg)
        self.assertEqual(len(result.card.abilities), 1)
        self.assertEqual(len(result.unparsed), 0)
        self.assertEqual(len(result.rule_reminders), 0)
        self.assertEqual(len(result.ambiguities), 0)

    def test_opt_scr(self) -> None:
        """Opt: Scry 1. → SpellAbility, no unparsed."""
        raw = _raw(
            "Opt",
            ("Scry 1.",),
            types=("Instant",),
            colors=("U",),
            mana_cost_raw="{U}",
            mana_value=1,
        )
        result = compile_card(raw, self.reg)
        self.assertEqual(len(result.card.abilities), 1)
        self.assertEqual(len(result.unparsed), 0)
        self.assertEqual(len(result.rule_reminders), 0)

    def test_basri_solidarity_put_counter(self) -> None:
        """Basri's Solidarity: Put a +1/+1 counter on each creature you control."""
        raw = _raw(
            "Basri's Solidarity",
            ("Put a +1/+1 counter on each creature you control.",),
            types=("Instant",),
            colors=("W",),
            mana_cost_raw="{W}",
            mana_value=1,
        )
        result = compile_card(raw, self.reg)
        self.assertEqual(len(result.card.abilities), 1)
        self.assertEqual(len(result.unparsed), 0)

    def test_fungal_rebirth_all_covered(self) -> None:
        """Fungal Rebirth: both sentences covered (R7-B) → 1 SpellAbility,
        0 unparsed; the died-this-turn Conditional is a sibling Seq step."""
        raw = _raw(
            "Fungal Rebirth",
            (
                "Return target permanent card from your graveyard to your hand.",
                "If a creature died this turn, create two 1/1 green Saproling creature tokens.",
            ),
            types=("Sorcery",),
            colors=("G",),
            mana_cost_raw="{G}",
            mana_value=1,
        )
        result = compile_card(raw, self.reg)
        self.assertEqual(len(result.card.abilities), 1)
        self.assertEqual(len(result.unparsed), 0)
        spell = result.card.abilities[0]
        assert isinstance(spell, SpellAbility)
        assert isinstance(spell.effect, Seq)
        self.assertEqual(len(spell.effect.steps), 2)
        cond = spell.effect.steps[1]
        assert isinstance(cond, Conditional)

    def test_gnarled_sage_reach(self) -> None:
        """Gnarled Sage: Reach keyword reminder → KeywordAbility, no unparsed."""
        raw = _raw(
            "Gnarled Sage",
            ("Reach (This creature can block creatures with flying.)",),
            types=("Creature",),
            subtypes=("Treefolk", "Soldier"),
            colors=("G",),
            mana_cost_raw="{2}{G}",
            mana_value=3,
            power_raw="2",
            toughness_raw="3",
        )
        result = compile_card(raw, self.reg)
        # C4: the keyword itself stays off the ability list; the only node
        # is the effect-less SpellAbility(CREATURE) cast carrier.
        self.assertEqual(len(result.card.abilities), 1)
        carrier = result.card.abilities[0]
        assert isinstance(carrier, SpellAbility)
        self.assertIsNone(carrier.effect)
        self.assertEqual(len(result.card.keywords), 1)
        self.assertEqual(result.card.keywords[0].keyword, Keyword.REACH)
        self.assertEqual(len(result.unparsed), 0)
        self.assertEqual(len(result.rule_reminders), 0)

    def test_garruk_warsteed_covered_and_builtin(self) -> None:
        """Garruk's Warsteed stub: covered (cont-gain-4) + compiler-built-in
        search-shuffle boilerplate → no unparsed sentence."""
        raw = _raw(
            "Garruk's Warsteed",
            (
                "If you do, you gain 4 life.",
                "If you search your library this way, shuffle.",
            ),
            types=("Creature",),
            subtypes=("Beast", "Horse"),
            colors=("G",),
            mana_cost_raw="{1}{G}",
            mana_value=2,
            power_raw="2",
            toughness_raw="2",
            keywords=("HASTE",),
        )
        result = compile_card(raw, self.reg)
        self.assertEqual(len(result.card.abilities), 1)
        self.assertEqual(len(result.unparsed), 0)


class TestReplacementBatchEndToEnd(unittest.TestCase):
    """Round-5 replacement batch: each new sentence, compiled through the
    full compile_card pipeline, yields exactly one ability node and no
    unparsed residue (the compiler consumes ReplacementAbility /
    CostModifier AbilityOutcomes generically)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = _make_registry()

    def test_replacement_batch_cards_compile(self) -> None:
        cases = (
            ("Life Goes On", "If a creature died this turn, you gain 8 life instead."),
            (
                "Containment Priest",
                (
                    "If a nontoken creature would enter and it wasn't cast, "
                    "exile it instead."
                ),
            ),
            (
                "Fiery Emancipation",
                (
                    "If a source you control would deal damage to a permanent "
                    "or player, it deals triple that damage to that permanent "
                    "or player instead."
                ),
            ),
            (
                "Conclave Mentor",
                (
                    "If one or more +1/+1 counters would be put on a creature "
                    "you control, that many plus one +1/+1 counters are put on "
                    "that creature instead."
                ),
            ),
            (
                "Scorching Dragonfire",
                (
                    "If that creature or planeswalker would die this turn, "
                    "exile it instead."
                ),
            ),
            (
                "Chandra, Flame's Catalyst",
                "If that spell would be put into your graveyard, exile it instead.",
            ),
            (
                "Lofty Denial",
                (
                    "If you control a creature with flying, counter that spell "
                    "unless its controller pays {4} instead."
                ),
            ),
            (
                "Teferi's Ageless Insight",
                (
                    "If you would draw a card except the first one you draw in "
                    "each of your draw steps, draw two cards instead."
                ),
            ),
        )
        for name, sent in cases:
            raw = _raw(name, (sent,))
            result = compile_card(raw, self.reg)
            self.assertEqual(len(result.card.abilities), 1, f"{name}: ability count")
            self.assertEqual(len(result.unparsed), 0, f"{name}: unparsed")
            self.assertEqual(len(result.rule_reminders), 0, f"{name}: rule reminders")


# ---------------------------------------------------------------------------
# Test: Optional B5b.json Cross-Check
# ---------------------------------------------------------------------------


class TestB5bJsonCrossCheck(unittest.TestCase):
    """Cross-check the embedded SHAPES table against the source JSON.

    Skipped if B5b.json is not present (it lives in /tmp, not the repo).
    """

    B5B_PATH = "/tmp/opencode/phase1_buckets/B5b.json"

    @classmethod
    @unittest.skipUnless(
        os.path.exists(B5B_PATH),
        f"B5b.json not found at {B5B_PATH}",
    )
    def setUpClass(cls) -> None:
        with open(cls.B5B_PATH) as f:
            cls.json_data: dict[str, list[list[str]]] = json.load(f)

    def test_90_shapes_in_json(self) -> None:
        self.assertEqual(len(self.json_data), 90)

    def test_all_json_sentences_in_table(self) -> None:
        """Every sentence in B5b.json values must appear in SHAPES."""
        table_sents = {s[0] for s in SHAPES}
        json_sents: set[str] = set()
        for pairs in self.json_data.values():
            for _card, sent in pairs:
                json_sents.add(sent)
        self.assertEqual(json_sents, table_sents)


# ---------------------------------------------------------------------------
# Test: Grammar Round-7 batch (family-2 anaphora; doc 2026-09-28/03 §3 R7-A)
# ---------------------------------------------------------------------------


class TestRound7AnaphoraBatch(unittest.TestCase):
    """Structural assertions for the round-7 anaphora templates (C15/C16)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = _make_registry()

    def _match_one(self, sent: str) -> SentenceOutcome:
        matches = self.reg.match(sent)
        self.assertEqual(len(matches), 1, f"expected 1 match: {sent!r}")
        return matches[0].outcome

    def test_it_gains_kw_eot(self) -> None:
        """GRANT_ABILITY(target=result-referent, KeywordAbility, DurationEot)."""
        outcome = self._match_one("It gains indestructible until end of turn.")
        atom = _as_atom(_as_effect(outcome).effect)
        self.assertEqual(atom.verb, Verb.GRANT_ABILITY)
        p = _pairs_dict(atom)
        sel = p["target"]
        self.assertIsInstance(sel, Selector)
        self.assertEqual(sel.referent, "result")
        self.assertEqual(sel.mode, SelectorMode.CHOOSE)
        self.assertEqual(sel.count, QConst(1))
        ka = p["ability"]
        self.assertIsInstance(ka, KeywordAbility)
        self.assertEqual(ka.keyword, Keyword.INDESTRUCTIBLE)
        self.assertEqual(p["duration"], DurationEot())

    def test_it_gains_haste_no_duration(self) -> None:
        outcome = self._match_one("It gains haste.")
        atom = _as_atom(_as_effect(outcome).effect)
        p = _pairs_dict(atom)
        self.assertEqual(atom.verb, Verb.GRANT_ABILITY)
        self.assertEqual(p["ability"].keyword, Keyword.HASTE)
        self.assertNotIn("duration", p)

    def test_it_gains_protection_choice_is_choose(self) -> None:
        """C15: the color choice stays a Choose(1, 5 colored grants)."""
        outcome = self._match_one(
            "It gains protection from the color of your choice until end of turn."
        )
        choice = _as_effect(outcome).effect
        assert isinstance(choice, Choose)
        self.assertEqual(choice.count, QConst(1))
        self.assertEqual(len(choice.options), 5)
        colors: set[str] = set()
        for opt in choice.options:
            assert isinstance(opt, Atom)
            p = _pairs_dict(opt)
            self.assertEqual(opt.verb, Verb.GRANT_ABILITY)
            self.assertEqual(p["target"].referent, "result")
            ka = p["ability"]
            self.assertEqual(ka.keyword, Keyword.PROTECTION)
            (filt,) = ka.params
            colors.add(filt.color)
        self.assertEqual(colors, {"W", "U", "B", "R", "G"})

    def test_that_player_discards(self) -> None:
        outcome = self._match_one("That player discards that card.")
        atom = _as_atom(_as_effect(outcome).effect)
        p = _pairs_dict(atom)
        # T4 P1a: the discard shape is the merged MOVE_ZONE atom.
        self.assertEqual(atom.verb, Verb.MOVE_ZONE)
        self.assertEqual(p["controller"], ControllerRef.TARGET_PLAYER)
        self.assertEqual(
            p["destination"], Zone(ZoneKind.GRAVEYARD, ControllerRef.TARGET_PLAYER)
        )
        self.assertEqual(p["from"], Zone(ZoneKind.HAND, ControllerRef.TARGET_PLAYER))
        self.assertEqual(p["cards"].referent, "result")

    def test_if_it_creature_conditional(self) -> None:
        outcome = self._match_one("If it's a creature card, put it into your hand.")
        cond = _as_effect(outcome).effect
        assert isinstance(cond, Conditional)
        pred = cond.pred
        assert isinstance(pred, FAtom)
        self.assertIs(pred.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(pred.string_value, "Creature")
        self.assertIsNone(cond.else_effect)
        move = _as_atom(cond.then_effect)
        self.assertEqual(move.verb, Verb.MOVE_ZONE)
        p = _pairs_dict(move)
        self.assertEqual(p["cards"].referent, "result")
        self.assertEqual(p["destination"].kind, ZoneKind.HAND)

    def test_if_it_creature_or_land_draw(self) -> None:
        outcome = self._match_one("If it's a creature or land card, draw a card.")
        cond = _as_effect(outcome).effect
        assert isinstance(cond, Conditional)
        self.assertIsInstance(cond.pred, FOr)
        atom = _as_atom(cond.then_effect)
        self.assertEqual(atom.verb, Verb.DRAW)

    def test_otherwise_bottom(self) -> None:
        outcome = self._match_one("Otherwise, put it on the bottom of your library.")
        atom = _as_atom(_as_effect(outcome).effect)
        p = _pairs_dict(atom)
        self.assertEqual(atom.verb, Verb.MOVE_ZONE)
        self.assertEqual(p["cards"].referent, "result")
        self.assertEqual(p["destination"].position, ZonePosition.BOTTOM)

    def test_search_name_exile(self) -> None:
        outcome = self._match_one(
            "Search target opponent's graveyard, hand, and library "
            "for any number of cards with that name and exile them."
        )
        seq = _as_seq(_as_effect(outcome).effect)
        search = _as_atom(seq.steps[0])
        p = _pairs_dict(search)
        self.assertEqual(search.verb, Verb.SEARCH)
        sel = p["cards"]
        self.assertEqual(sel.mode, SelectorMode.CHOOSE)
        self.assertIsInstance(sel.count, QUnbounded)
        self.assertIs(sel.filter.pred, FAtomPred.NAME_CHOSEN)
        # R0 zone-fold: graveyard+hand+library is ONE 3-element set.
        self.assertEqual(
            sel.zones,
            (
                Zone(ZoneKind.GRAVEYARD, ControllerRef.TARGET_PLAYER),
                Zone(ZoneKind.HAND, ControllerRef.TARGET_PLAYER),
                Zone(ZoneKind.LIBRARY, ControllerRef.TARGET_PLAYER),
            ),
        )
        exile = _as_atom(seq.steps[1])
        # T4 P1a: the exile shape is the merged MOVE_ZONE atom.
        self.assertEqual(exile.verb, Verb.MOVE_ZONE)
        p2 = _pairs_dict(exile)
        self.assertEqual(p2["destination"], Zone(ZoneKind.EXILE, ControllerRef.OWNER))
        self.assertEqual(p2["target"].referent, "result")

    def test_token_per_exiled_this_way(self) -> None:
        outcome = self._match_one(
            "That player shuffles, then creates a 2/2 black Zombie creature "
            "token for each card exiled from their hand this way."
        )
        seq = _as_seq(_as_effect(outcome).effect)
        shuffle = _as_atom(seq.steps[0])
        self.assertEqual(shuffle.verb, Verb.SHUFFLE)
        create = _as_atom(seq.steps[1])
        p = _pairs_dict(create)
        self.assertEqual(create.verb, Verb.CREATE_TOKEN)
        self.assertIsInstance(p["tokens"], TokenSpec)
        # R11-4a: count = QCount over the target's exile zone, filtered to
        # NAME_CHOSEN ∧ HAND→EXILE moves by the target this turn — NOT the
        # old whole-search THIS_WAY_COUNT tally.
        count = p["count"]
        self.assertIsInstance(count, QCount)
        sel = count.selector
        self.assertIs(sel.mode, SelectorMode.ALL)
        self.assertEqual(
            sel.zones[0], Zone(ZoneKind.EXILE, ControllerRef.TARGET_PLAYER)
        )
        # R1a canonicalization: FAnd children construction-sorted; members by
        # pred, order by the canonicalization law.
        self.assertEqual(
            list(sel.filter.children),
            sorted(sel.filter.children, key=canonical_json),
        )
        by_pred = {c.pred: c for c in sel.filter.children}
        self.assertEqual(len(by_pred), 2)
        name_f = by_pred[FAtomPred.NAME_CHOSEN]
        move_f = by_pred[FAtomPred.MOVED_TO_ZONE_THIS_TURN]
        self.assertEqual(
            move_f.from_zone, Zone(ZoneKind.HAND, ControllerRef.TARGET_PLAYER)
        )
        self.assertEqual(
            move_f.to_zone, Zone(ZoneKind.EXILE, ControllerRef.TARGET_PLAYER)
        )
        self.assertIs(move_f.who, ControllerRef.TARGET_PLAYER)

    def test_loses_kw_eot(self) -> None:
        outcome = self._match_one(
            "That permanent loses indestructible until end of turn."
        )
        atom = _as_atom(_as_effect(outcome).effect)
        p = _pairs_dict(atom)
        self.assertEqual(atom.verb, Verb.LOSE_ABILITY)
        self.assertEqual(p["target"].referent, "target")
        self.assertEqual(p["ability"].keyword, Keyword.INDESTRUCTIBLE)
        self.assertEqual(p["duration"], DurationEot())

    def test_one_of_other(self) -> None:
        outcome = self._match_one(
            "Put one of them into your hand and the other into your graveyard."
        )
        seq = _as_seq(_as_effect(outcome).effect)
        first, rest = (_as_atom(s) for s in seq.steps)
        self.assertEqual(_pairs_dict(first)["cards"].mode, SelectorMode.ONE_OF)
        self.assertEqual(_pairs_dict(rest)["cards"].mode, SelectorMode.REST)
        self.assertEqual(_pairs_dict(first)["destination"].kind, ZoneKind.HAND)
        self.assertEqual(_pairs_dict(rest)["destination"].kind, ZoneKind.GRAVEYARD)

    def test_one_of_rest_bottom(self) -> None:
        outcome = self._match_one(
            "Put one of those cards into your hand and the rest on the "
            "bottom of your library in any order."
        )
        seq = _as_seq(_as_effect(outcome).effect)
        first, rest = (_as_atom(s) for s in seq.steps)
        self.assertEqual(_pairs_dict(first)["cards"].mode, SelectorMode.ONE_OF)
        self.assertEqual(_pairs_dict(rest)["cards"].mode, SelectorMode.REST)
        self.assertEqual(_pairs_dict(rest)["destination"].position, ZonePosition.BOTTOM)

    def test_rest_bottom_random(self) -> None:
        outcome = self._match_one(
            "Put the rest on the bottom of your library in a random order."
        )
        atom = _as_atom(_as_effect(outcome).effect)
        p = _pairs_dict(atom)
        self.assertEqual(p["cards"].mode, SelectorMode.REST)
        self.assertEqual(p["destination"].position, ZonePosition.BOTTOM)

    def test_cultivate_split_search(self) -> None:
        outcome = self._match_one(
            "Search your library for up to two basic land cards, reveal "
            "those cards, put one onto the battlefield tapped and the "
            "other into your hand, then shuffle."
        )
        seq = _as_seq(_as_effect(outcome).effect)
        self.assertEqual(len(seq.steps), 5)
        search = _as_atom(seq.steps[0])
        sel = _pairs_dict(search)["cards"]
        self.assertEqual(sel.count, QConst(2))  # C15: up-to stays CHOOSE
        self.assertEqual(sel.mode, SelectorMode.CHOOSE)
        to_bf = _as_atom(seq.steps[2])
        self.assertEqual(_pairs_dict(to_bf)["cards"].mode, SelectorMode.ONE_OF)
        self.assertTrue(_pairs_dict(to_bf)["tapped_on_enter"])
        to_hand = _as_atom(seq.steps[3])
        self.assertEqual(_pairs_dict(to_hand)["cards"].mode, SelectorMode.REST)
        self.assertEqual(_as_atom(seq.steps[4]).verb, Verb.SHUFFLE)

    def test_cast_elsewhere_instead(self) -> None:
        outcome = self._match_one(
            "If this spell was cast from anywhere other than your hand, "
            "put each of those cards into your hand instead."
        )
        cond = _as_effect(outcome).effect
        assert isinstance(cond, Conditional)
        self.assertIsInstance(cond.pred, FNot)
        move = _as_atom(cond.then_effect)
        self.assertEqual(_pairs_dict(move)["cards"].referent, "result")

    def test_gain_control_eot(self) -> None:
        outcome = self._match_one("Gain control of target creature until end of turn.")
        atom = _as_atom(_as_effect(outcome).effect)
        p = _pairs_dict(atom)
        self.assertEqual(atom.verb, Verb.GAIN_CONTROL)
        self.assertEqual(p["target"].mode, SelectorMode.TARGET)
        self.assertEqual(p["duration"], DurationEot())


class TestRound7AnaphoraEndToEnd(unittest.TestCase):
    """Full-card compiles for the round-7 batch sentences (merge paths)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = _make_registry()

    def test_garruk_otherwise_merges_into_else_effect(self) -> None:
        """The Otherwise sentence attaches as the previous Conditional's
        else_effect (R7-3 compiler merge; Garruk Savage Herald [−7] idiom
        compiled as a plain spell sequence for the b5b registry)."""
        raw = _raw(
            "Garruk Reveal Stand-in",
            (
                "If it's a creature card, put it into your hand.",
                "Otherwise, put it on the bottom of your library.",
            ),
            types=("Sorcery",),
        )
        result = compile_card(raw, self.reg)
        self.assertEqual(len(result.unparsed), 0)
        spell = [ab for ab in result.card.abilities if isinstance(ab, SpellAbility)]
        self.assertEqual(len(spell), 1)
        eff = spell[0].effect
        assert isinstance(eff, Conditional)
        self.assertIsNotNone(eff.else_effect)
        move = _as_atom(eff.else_effect)
        self.assertEqual(_pairs_dict(move)["cards"].referent, "result")


class TestRound7BTopUps(unittest.TestCase):
    """Structural + end-to-end assertions for the R7-B top-up rows
    (doc 2026-09-28/03 §3 B-table, no-grammar batch)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = _make_registry()

    def _match_one(self, sent: str) -> SentenceOutcome:
        matches = self.reg.match(sent)
        self.assertEqual(len(matches), 1, f"expected 1 match: {sent!r}")
        return matches[0].outcome

    def test_keyword_list_baneslayer_protection_params(self) -> None:
        """Baneslayer list → KeywordOutcome(PROTECTION, subtype-OR)."""
        outcome = self._match_one(
            "Flying, first strike, lifelink, protection from Demons and from Dragons"
        )
        assert isinstance(outcome, KeywordOutcome)
        self.assertIs(outcome.keyword, Keyword.PROTECTION)
        (filt,) = outcome.params
        assert isinstance(filt, FOr)
        atoms = [c for c in filt.children if isinstance(c, FAtom)]
        self.assertEqual(len(atoms), len(filt.children))
        subs = {a.string_value for a in atoms}
        assert subs == {"Demon", "Dragon"}
        self.assertTrue(all(a.pred is FAtomPred.SUBTYPE_EQ for a in atoms))

    def test_keyword_list_sporeweb_hexproof_params(self) -> None:
        """Sporeweb list → KeywordOutcome(HEXPROOF, COLOR_HAS blue)."""
        outcome = self._match_one("Reach, hexproof from blue")
        assert isinstance(outcome, KeywordOutcome)
        self.assertIs(outcome.keyword, Keyword.HEXPROOF)
        (filt,) = outcome.params
        assert isinstance(filt, FAtom)
        self.assertIs(filt.pred, FAtomPred.COLOR_HAS)
        self.assertEqual(filt.color, "U")

    def test_if_died_two_tokens(self) -> None:
        """DIED_THIS_TURN Conditional; C14 word-pinned QConst(2); token
        carries no colour (C-2 lossy, TokenSpec has no color field)."""
        outcome = self._match_one(
            "If a creature died this turn, create two 1/1 green Saproling "
            "creature tokens."
        )
        cond = _as_effect(outcome).effect
        assert isinstance(cond, Conditional)
        pred = cond.pred
        assert isinstance(pred, FAtom)
        self.assertIs(pred.pred, FAtomPred.DIED_THIS_TURN)
        self.assertIsNone(cond.else_effect)
        atom = _as_atom(cond.then_effect)
        self.assertEqual(atom.verb, Verb.CREATE_TOKEN)
        p = _pairs_dict(atom)
        self.assertEqual(p["count"], QConst(2))
        spec = p["tokens"]
        assert isinstance(spec, TokenSpec)
        self.assertEqual(spec.subtypes, ("Saproling",))
        self.assertEqual(spec.power, QConst(1))
        self.assertEqual(spec.toughness, QConst(1))

    def test_would_damage_incarnation_replacement(self) -> None:
        """Nine Lives: ReplacementAbility over DamageDealtEvent (source=None
        = the printed universal 'a source'; event filter names YOU — the
        printed "to you" recipient, round 8 / C-4); action
        PUT_COUNTER(INCARNATION, 1) on the self enchantment (r5 convention:
        the replacement itself carries the prevention, no PREVENT atom)."""
        outcome = self._match_one(
            "If a source would deal damage to you, prevent that damage and "
            "put an incarnation counter on this enchantment."
        )
        assert isinstance(outcome, AbilityOutcome)
        repl = outcome.ability
        assert isinstance(repl, ReplacementAbility)
        event = repl.event
        assert isinstance(event, DamageDealtEvent)
        self.assertIsNone(event.source)
        # "to you" restored (round 8): damaged-object filter = YOU.
        filt = event.filter
        assert isinstance(filt, FAtom)
        self.assertIs(filt.pred, FAtomPred.CONTROLLER_IS)
        self.assertEqual(filt.who, ControllerRef.YOU)
        self.assertEqual(repl.condition, None)
        atom = _as_atom(repl.action)
        self.assertEqual(atom.verb, Verb.PUT_COUNTER)
        p = _pairs_dict(atom)
        self.assertEqual(p["counter_kind"], CounterKind.INCARNATION)
        self.assertEqual(p["count"], QConst(1))
        sel = p["target"]
        assert isinstance(sel, Selector)
        self.assertEqual(sel.count, QConst(1))
        self.assertEqual(sel.mode, SelectorMode.CHOOSE)
        filt = sel.filter
        assert isinstance(filt, FAtom)
        self.assertIs(filt.pred, FAtomPred.IS_SOURCE)

    def test_flip_won_conditional(self) -> None:
        """Tavern Swindler s2: Conditional(FLIP_WON who=YOU, gain 6)."""
        outcome = self._match_one("If you win the flip, you gain 6 life.")
        cond = _as_effect(outcome).effect
        assert isinstance(cond, Conditional)
        pred = cond.pred
        assert isinstance(pred, FAtom)
        self.assertIs(pred.pred, FAtomPred.FLIP_WON)
        self.assertEqual(pred.who, ControllerRef.YOU)
        atom = _as_atom(cond.then_effect)
        self.assertEqual(atom.verb, Verb.GAIN_LIFE)
        p = _pairs_dict(atom)
        self.assertEqual(p["controller"], ControllerRef.YOU)
        self.assertEqual(p["amount"], QConst(6))

    def test_choice_of_grants_choose(self) -> None:
        """C15: your-choice grant stays a Choose(1-of-2); the grant targets
        the spell's own target via referent='target'."""
        outcome = self._match_one(
            "Target creature gets +1/+1 and gains your choice of deathtouch "
            "or lifelink until end of turn."
        )
        seq = _as_effect(outcome).effect
        assert isinstance(seq, Seq)
        mod, choice = seq.steps
        mod = _as_atom(mod)
        self.assertEqual(mod.verb, Verb.MODIFY_PT)
        mp = _pairs_dict(mod)
        self.assertEqual(mp["target"].mode, SelectorMode.TARGET)
        self.assertEqual(mp["power"], PtDelta(PtDirection.INCREASE, QConst(1)))
        assert isinstance(choice, Choose)
        self.assertEqual(choice.count, QConst(1))
        self.assertEqual(len(choice.options), 2)
        kws = set()
        for opt in choice.options:
            opt = _as_atom(opt)
            self.assertEqual(opt.verb, Verb.GRANT_ABILITY)
            p = _pairs_dict(opt)
            self.assertEqual(p["target"].referent, "target")
            ka = p["ability"]
            assert isinstance(ka, KeywordAbility)
            kws.add(ka.keyword)
            self.assertEqual(p["duration"], DurationEot())
        self.assertEqual(kws, {Keyword.DEATHTOUCH, Keyword.LIFELINK})

    def test_its_controller_tokens(self) -> None:
        """Angel (4/4, flying) and Soldier (1/1) tokens; colour="W"
        faithful (round 8 / C-2 repair), creator still implicit
        (Necromentia precedent)."""
        for sent, pt, flying in [
            (
                "Its controller creates a 4/4 white Angel creature token with flying.",
                (QConst(4), QConst(4)),
                True,
            ),
            (
                "Its controller creates a 1/1 white Soldier creature token.",
                (QConst(1), QConst(1)),
                False,
            ),
        ]:
            outcome = self._match_one(sent)
            atom = _as_atom(_as_effect(outcome).effect)
            self.assertEqual(atom.verb, Verb.CREATE_TOKEN)
            p = _pairs_dict(atom)
            spec = p["tokens"]
            assert isinstance(spec, TokenSpec)
            self.assertEqual((spec.power, spec.toughness), pt)
            self.assertEqual(spec.keywords, (Keyword.FLYING,) if flying else ())
            self.assertEqual(spec.color, "W")  # C-2 repair (round 8)

    def test_its_controller_loses_life(self) -> None:
        """Death Mage [−3] s2: LOSE_LIFE controller role = referent-target
        selector (Gloom-Sower event-reference shape in the controller role)."""
        outcome = self._match_one("Its controller loses 2 life.")
        atom = _as_atom(_as_effect(outcome).effect)
        self.assertEqual(atom.verb, Verb.LOSE_LIFE)
        p = _pairs_dict(atom)
        sel = p["controller"]
        assert isinstance(sel, Selector)
        self.assertEqual(sel.referent, "target")
        self.assertEqual(sel.mode, SelectorMode.CHOOSE)
        self.assertEqual(sel.count, QConst(1))
        self.assertEqual(p["amount"], QConst(2))

    # -- end-to-end card compiles --

    def test_baneslayer_keyword_dedup(self) -> None:
        """Baneslayer: bare members from raw.keywords + template PROTECTION
        merge without duplication (compiler kw_set dedup)."""
        raw = _raw(
            "Baneslayer Angel",
            (
                "Flying, first strike, lifelink, protection from Demons and from Dragons",
            ),
            types=("Creature",),
            subtypes=("Angel",),
            colors=("W",),
            keywords=("First strike", "Flying", "Lifelink", "Protection"),
        )
        result = compile_card(raw, self.reg)
        self.assertEqual(len(result.unparsed), 0)
        kws = [ka.keyword for ka in result.card.keywords]
        self.assertEqual(len(kws), len(set(kws)), f"dup keyword: {kws}")
        self.assertIn(Keyword.PROTECTION, kws)
        self.assertIn(Keyword.FLYING, kws)

    def test_angelic_ascension_seq(self) -> None:
        """Ascension: s1 EXILE (b5c-owned sentence) + s2 CREATE_TOKEN fold
        into one Seq; 0 unparsed — run against the FULL registry because
        the antecedent sentence is owned by another bucket module."""
        from MTG_bot.core.compiler.coverage import build_full_registry

        raw = _raw(
            "Angelic Ascension",
            (
                "Exile target creature or planeswalker.",
                "Its controller creates a 4/4 white Angel creature token with flying.",
            ),
            types=("Instant",),
            colors=("W",),
        )
        result = compile_card(raw, build_full_registry())
        self.assertEqual(len(result.unparsed), 0)
        spells = [ab for ab in result.card.abilities if isinstance(ab, SpellAbility)]
        self.assertEqual(len(spells), 1)
        eff = spells[0].effect
        assert isinstance(eff, Seq)
        self.assertEqual(len(eff.steps), 2)
        create = _as_atom(eff.steps[1])
        self.assertEqual(create.verb, Verb.CREATE_TOKEN)
        # R11-2 anaphoric creator: the emitted CREATE_TOKEN carries a
        # "controller" role — the referent-target Selector (the s1 exile's
        # controller is the antecedent), CHOOSE one, any zone/controller.
        # Same idiom _build_its_controller_loses_life emits (Death Mage).
        roles = dict(create.args.pairs)
        controller_sel = roles["controller"]
        assert isinstance(controller_sel, Selector)
        self.assertEqual(controller_sel.referent, "target")
        self.assertIs(controller_sel.mode, SelectorMode.CHOOSE)
        self.assertEqual(controller_sel.count, QConst(1))
        self.assertIs(controller_sel.zones[0].kind, ZoneKind.ANY)
        self.assertIs(controller_sel.zones[0].controller, ControllerRef.ANY)


# ---------------------------------------------------------------------------
# Round 9-B structural pins (doc 2026-09-28/11 §9-B rows 10-11)
# ---------------------------------------------------------------------------


class TestRound9BManaAndReveal(unittest.TestCase):
    """9-B: Vodalian THIS_MANA restriction (C21) and Snoop continuous
    REVEAL state (R9-8 duration role)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = _make_registry()

    def _match_one(self, sent: str) -> SentenceOutcome:
        matches = self.reg.match(sent)
        self.assertEqual(len(matches), 1, f"expected 1 match: {sent!r}")
        return matches[0].outcome

    def test_vodalian_this_mana(self) -> None:
        outcome = self._match_one(
            "Spend this mana only to cast an instant or sorcery spell."
        )
        ab = _as_ability(outcome).ability
        static = _as_static(ab)
        atom = _as_atom(static.effect)
        self.assertIs(atom.verb, Verb.MANA_POLICY)
        pairs = _pairs_dict(atom)
        self.assertEqual(pairs["scope"], "THIS_MANA")
        spell_types = pairs["filter"]
        assert isinstance(spell_types, FOr)
        instant, sorcery = spell_types.children
        assert isinstance(instant, FAtom) and isinstance(sorcery, FAtom)
        self.assertIs(instant.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(instant.string_value, "Instant")
        self.assertEqual(sorcery.string_value, "Sorcery")
        # restriction, not permission — NO OptionalEffect wrapper (C15)
        self.assertNotIsInstance(static.effect, OptionalEffect)

    def test_snoop_continuous_reveal(self) -> None:
        outcome = self._match_one("Play with the top card of your library revealed.")
        ab = _as_ability(outcome).ability
        static = _as_static(ab)
        atom = _as_atom(static.effect)
        self.assertIs(atom.verb, Verb.REVEAL)
        pairs = _pairs_dict(atom)
        self.assertEqual(pairs["controller"], ControllerRef.YOU)
        self.assertEqual(pairs["count"], QConst(1))
        self.assertEqual(pairs["duration"], DurationPermanent())
        # library-top target IMPLICIT (LOOK_AT convention: no zone role)
