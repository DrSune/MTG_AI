"""Tests for B5b bucket templates (templates_b5b.py).

Covers all 90 shapes in ``/tmp/opencode/phase1_buckets/B5b.json``
(91 distinct concrete sentences):
- 42 template-covered rows over 41 shapes / 37 tids (34 single-shape tids,
  3 multi-shape tids, plus one shape with two concrete rows)
- 49 UNCOVERED (no template; 48 have no grammar construct, 1 is
  compiler-built-in: "If you search your library this way, shuffle." —
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
    ControllerRef,
    CostDeltaIncreaseGeneric,
    CostModifier,
    CostSacrifice,
    CostTap,
    CounterKind,
    DurationEot,
    FAtom,
    FAtomPred,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    PtDelta,
    PtDirection,
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
    canonical_json,
)
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.ingest import RawCard
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    KeywordOutcome,
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
        "UNCOV",
        "",
    ),
    # shape 3
    ("Gadrak can't attack unless you control four or more artifacts.", "UNCOV", ""),
    # shape 4
    ("Gain control of target creature until end of turn.", "UNCOV", ""),
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
        "UNCOV",
        "",
    ),
    # shape 8
    ("If a creature died this turn, you gain 8 life instead.", "UNCOV", ""),
    # shape 9
    (
        "If a nontoken creature would enter and it wasn't cast, exile it instead.",
        "UNCOV",
        "",
    ),
    # shape 10
    (
        "If a source would deal damage to you, prevent that damage and put an incarnation counter on this enchantment.",
        "UNCOV",
        "",
    ),
    # shape 11
    (
        "If a source you control would deal damage to a permanent or player, it deals triple that damage to that permanent or player instead.",
        "UNCOV",
        "",
    ),
    # shape 12
    (
        "If an ability of another Shrine you control triggers while you control six or more Shrines, that ability triggers an additional time.",
        "UNCOV",
        "",
    ),
    # shape 13
    (
        "If it was a creature card, put a +1/+1 counter on this creature and you gain 1 life.",
        "UNCOV",
        "",
    ),
    # shape 14
    ("If it's a creature card, put it into your hand.", "UNCOV", ""),
    # shape 15
    ("If it's a creature or land card, draw a card.", "UNCOV", ""),
    # shape 16
    (
        "If one or more +1/+1 counters would be put on a creature you control, that many plus one +1/+1 counters are put on that creature instead.",
        "UNCOV",
        "",
    ),
    # shape 17
    (
        "If that creature or planeswalker would die this turn, exile it instead.",
        "UNCOV",
        "",
    ),
    # shape 18
    ("If that spell would be put into your graveyard, exile it instead.", "UNCOV", ""),
    # shape 19
    (
        "If this spell was cast from anywhere other than your hand, put each of those cards into your hand instead.",
        "UNCOV",
        "",
    ),
    # shape 20
    (
        "If you control a creature with flying, counter that spell unless its controller pays {4} instead.",
        "UNCOV",
        "",
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
    ("If you win the flip, you gain 6 life.", "UNCOV", ""),
    # shape 30
    (
        "If you would draw a card except the first one you draw in each of your draw steps, draw two cards instead.",
        "UNCOV",
        "",
    ),
    # shape 31
    ("It gains haste until end of turn.", "UNCOV", ""),
    # shape 32
    ("It gains haste.", "UNCOV", ""),
    # shape 33
    ('It gains haste."', "UNCOV", ""),
    # shape 34
    ("It gains indestructible until end of turn.", "UNCOV", ""),
    # shape 35
    (
        "It gains protection from the color of your choice until end of turn.",
        "UNCOV",
        "",
    ),
    # shape 36
    ("It gains vigilance until end of turn.", "UNCOV", ""),
    # shape 37
    (
        "Its controller creates a 4/4 white Angel creature token with flying.",
        "UNCOV",
        "",
    ),
    # shape 38
    ("Its controller creates a 1/1 white Soldier creature token.", "UNCOV", ""),
    # shape 39
    ("Its controller loses 2 life.", "UNCOV", ""),
    # shape 40
    (
        "Kinetic Augur's power is equal to the number of instant and sorcery cards in your graveyard.",
        "UNCOV",
        "",
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
    ("Otherwise, put it on the bottom of your library.", "UNCOV", ""),
    # shape 46
    (
        "Permanents you control gain hexproof and indestructible until end of turn.",
        "COVERED",
        "B5b-perm-hex-ind",
    ),
    # shape 47
    ("Play with the top card of your library revealed.", "UNCOV", ""),
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
        "UNCOV",
        "",
    ),
    # shape 52
    (
        "Put a +1/+1 counter on target creature you control.",
        "COVERED",
        "B5b-put-counter",
    ),
    # shape 53
    ("Put one of them into your hand and the other into your graveyard.", "UNCOV", ""),
    # shape 54
    (
        "Put one of those cards into your hand and the rest on the bottom of your library in any order.",
        "UNCOV",
        "",
    ),
    # shape 55
    ("Put the rest on the bottom of your library in a random order.", "UNCOV", ""),
    # shape 56
    ("Reach (This creature can block creatures with flying.)", "COVERED", "B5b-reach"),
    # shape 57
    ("Reach, hexproof from blue", "UNCOV", ""),
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
    ("Round up each time.", "UNCOV", ""),
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
        "UNCOV",
        "",
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
        "UNCOV",
        "",
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
    ("Spend this mana only to cast an instant or sorcery spell.", "UNCOV", ""),
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
        "UNCOV",
        "",
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
        "UNCOV",
        "",
    ),
    # shape 85
    (
        "That creature's controller reveals cards from the top of their library until they reveal a creature card.",
        "UNCOV",
        "",
    ),
    # shape 86
    ("That permanent loses indestructible until end of turn.", "UNCOV", ""),
    # shape 87
    ("That player discards that card.", "UNCOV", ""),
    # shape 88
    (
        "That player puts that card onto the battlefield, then shuffles the rest into their library.",
        "UNCOV",
        "",
    ),
    # shape 89
    (
        "That player shuffles, then creates a 2/2 black Zombie creature token for each card exiled from their hand this way.",
        "UNCOV",
        "",
    ),
    # shape 90
    (
        "Then if an opponent controls more creatures than you, put a loyalty counter on Garruk.",
        "UNCOV",
        "",
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

    def test_37_templates(self) -> None:
        self.assertEqual(len(TEMPLATES), 37)

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
        self.assertEqual(len(reg), 37)


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
        self.assertEqual(covered, 42, f"COVERED count {covered} != 42")
        self.assertEqual(uncov, 49, f"UNCOV count {uncov} != 49")

    def test_covered_tids_valid_and_unique_37(self) -> None:
        covered_tids = [s[2] for s in SHAPES if s[1] == "COVERED"]
        unique_tids = set(covered_tids)
        self.assertEqual(
            len(unique_tids), 37, f"expected 37 unique tids, got {len(unique_tids)}"
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
        """B5b-cont-discard: DISCARD, YOU, 1 card from HAND."""
        outcome = self._match_outcome("B5b-cont-discard")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.DISCARD)
        p = _pairs_dict(atom)
        self.assertEqual(p["controller"], ControllerRef.YOU)
        cards = p["cards"]
        self.assertIsInstance(cards, Selector)
        self.assertEqual(cards.zone.kind, ZoneKind.HAND)

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
        """B5b-put-counter: each of up to two target creatures."""
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
        self.assertEqual(target.mode, SelectorMode.CHOOSE)

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
        self.assertEqual(target.zone.kind, ZoneKind.ANY)

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
        self.assertEqual(cards.zone.kind, ZoneKind.GRAVEYARD)
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
        self.assertEqual(cards.zone.kind, ZoneKind.STACK)
        self.assertEqual(
            cards.zones,
            (Zone(kind=ZoneKind.BATTLEFIELD, controller=ControllerRef.ANY),),
        )
        # Spell-or-creature disjunction: FOr(FNot(IS_PERMANENT), TYPE_EQ Creature)
        flt = cards.filter
        self.assertIsInstance(flt, FOr)
        first, second = flt.children
        self.assertIsInstance(first, FNot)
        self.assertIsInstance(second, FAtom)
        self.assertEqual(second.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(second.string_value, "Creature")
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
        """B5b-tap-2-target: TAP, up to two target creatures."""
        outcome = self._match_outcome("B5b-tap-2-target")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.TAP)
        p = _pairs_dict(atom)
        target = p["target"]
        self.assertIsInstance(target, Selector)
        self.assertEqual(target.mode, SelectorMode.CHOOSE)

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
        """B5b-discard-target-2: DISCARD, TARGET_PLAYER, 2 cards."""
        outcome = self._match_outcome("B5b-discard-target-2")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.DISCARD)
        p = _pairs_dict(atom)
        self.assertEqual(p["controller"], ControllerRef.TARGET_PLAYER)
        cards = p["cards"]
        self.assertIsInstance(cards, Selector)
        self.assertEqual(cards.zone.kind, ZoneKind.HAND)

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
        self.assertEqual(len(seen), 37, f"only {len(seen)} unique tids tested")


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

    def test_fungal_rebirth_covered_and_uncov(self) -> None:
        """Fungal Rebirth: covered + uncovered → 1 ability + 1 unparsed."""
        raw = _raw(
            "Fungal Rebirth",
            (
                "If a creature died this turn, create two 1/1 green Saproling creature tokens.",
                "Return target permanent card from your graveyard to your hand.",
            ),
            types=("Sorcery",),
            colors=("G",),
            mana_cost_raw="{G}",
            mana_value=1,
        )
        result = compile_card(raw, self.reg)
        # First sentence is UNCOV, second is COVERED
        self.assertEqual(len(result.card.abilities), 1)
        self.assertEqual(len(result.unparsed), 1)
        self.assertEqual(
            result.unparsed[0][0],
            "If a creature died this turn, create two 1/1 green Saproling creature tokens.",
        )

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
        self.assertEqual(len(result.card.abilities), 0)
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
