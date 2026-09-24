"""Tests for B5a bucket templates (templates_b5a.py).

Covers all 90 shapes in ``/tmp/opencode/phase1_buckets/B5a.json``:
- 49 template-covered (45 templates; B5a-land-add matches 5 basic-land shapes)
- 23 rule-reminder pre-consumed by the compiler
- 18 UNCOVERED (no expressible/attachable construct; recorded in UNCOVERED and pinned)

PC-3: every concrete sentence fullmatches at most one template.
"""

from __future__ import annotations

import json
import os
import re
import unittest
import uuid
from typing import Any

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    Atom,
    AtomArgs,
    ControllerRef,
    Cost,
    CostDiscard,
    CostManaGeneric,
    CostSacrifice,
    CostTap,
    CounterKind,
    CreatureDiesEvent,
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
    SpellAbility,
    StaticAbility,
    TokenSpec,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
    canonical_json,
)
from MTG_bot.core.compiler.compiler import _is_rule_reminder, compile_card
from MTG_bot.core.compiler.ingest import RawCard
from MTG_bot.core.compiler.templates import (
    AdditionalCostOutcome,
    AbilityOutcome,
    ActivationGateOutcome,
    EffectOutcome,
    KeywordOutcome,
    SentenceOutcome,
    TemplateRegistry,
)
from MTG_bot.core.compiler.templates_b5a import TEMPLATES, UNCOVERED
from MTG_bot.core.identity import CardIdentity


# ---------------------------------------------------------------------------
# SHAPES — 90 concrete sentences from B5a.json with expected classification.
# Each entry: (sentence, category, expected_tid)
#   category: "RR" = rule-reminder, "COVERED" = template-covered, "UNCOV" = uncovered
# ---------------------------------------------------------------------------

SHAPES: tuple[tuple[str, str, str], ...] = (
    # shape 1
    (
        "(Any amount of damage a creature with deathtouch deals to a creature is enough to destroy it. Damage dealt by a creature with lifelink also causes its controller to gain that much life.)",
        "RR",
        "",
    ),
    # shape 2
    (
        "(Any amount of damage it deals to a creature is enough to destroy it.)",
        "RR",
        "",
    ),
    # shape 3
    ("(Attacking doesn't cause it to tap.)", "RR", ""),
    # shape 4
    ('(Damage and effects that say "destroy" don\'t destroy it.)', "RR", ""),
    # shape 5
    (
        "(Damage dealt by this creature also causes you to gain that much life.)",
        "RR",
        "",
    ),
    # shape 6
    ("(Each deals damage equal to its power to the other.)", "RR", ""),
    # shape 7
    (
        "(Each of those creatures can deal excess combat damage to the player or planeswalker it's attacking.)",
        "RR",
        "",
    ),
    # shape 8
    (
        '(Exile all spells and abilities from the stack, including this card. The player whose turn it is discards down to their maximum hand size. Damage wears off, and "this turn" and "until end of turn" effects end.)',
        "RR",
        "",
    ),
    # shape 9
    (
        "(It can deal excess combat damage to the player or planeswalker it's attacking.)",
        "RR",
        "",
    ),
    # shape 10
    (
        "(It can't be blocked, targeted, dealt damage, enchanted, or equipped by anything of that color.)",
        "RR",
        "",
    ),
    # shape 11
    (
        "(It can't be the target of spells or abilities your opponents control.)",
        "RR",
        "",
    ),
    # shape 12
    ("(It deals both first-strike and regular combat damage.)", "RR", ""),
    # shape 13
    ("(It deals combat damage before creatures without first strike.)", "RR", ""),
    # shape 14
    (
        '(It\'s an artifact with "{T}, Sacrifice this token: Add one mana of any color.")',
        "RR",
        "",
    ),
    # shape 15
    (
        "(Look at the top card of your library. You may put that card on the bottom.)",
        "RR",
        "",
    ),
    # shape 16
    ("(Put the top four cards of your library into your graveyard.)", "RR", ""),
    # shape 17
    ("(The creature can attack and {T} this turn.)", "RR", ""),
    # shape 18
    ("(They put the top two cards of their library into their graveyard.)", "RR", ""),
    # shape 19
    (
        "(To scry 3, look at the top three cards of your library, then put any number of them on the bottom and the rest on top in any order.)",
        "RR",
        "",
    ),
    # shape 20
    (
        "(Treat it and anything attached to it as though they don't exist until its controller's next turn.)",
        "RR",
        "",
    ),
    # shape 21
    (
        "(Treat them and anything attached to them as though they don't exist.)",
        "RR",
        "",
    ),
    # shape 22
    (
        "(Whenever you cast a noncreature spell, they get +1/+1 until end of turn.)",
        "RR",
        "",
    ),
    # shape 23
    (
        "(You can't be targeted, dealt damage, or enchanted by anything with that name.)",
        "RR",
        "",
    ),
    # shape 24
    ("({T}: Add {B}.)", "COVERED", "B5a-land-add"),
    # shape 25
    ("({T}: Add {G}.)", "COVERED", "B5a-land-add"),
    # shape 26
    ("({T}: Add {R}.)", "COVERED", "B5a-land-add"),
    # shape 27
    ("({T}: Add {U}.)", "COVERED", "B5a-land-add"),
    # shape 28
    ("({T}: Add {W}.)", "COVERED", "B5a-land-add"),
    # shape 29
    ("Activate only as a sorcery.", "UNCOV", ""),
    # shape 30
    (
        "Activate only if a creature died this turn.",
        "COVERED",
        "B5a-activate-only-death",
    ),
    # shape 31
    (
        "Activate only if you control a creature with flying.",
        "COVERED",
        "B5a-activate-only-flying",
    ),
    # shape 32
    (
        "Activate only if you have at least 7 life more than your starting life total and only as a sorcery.",
        "UNCOV",
        "",
    ),
    # shape 33
    ("Add six {R}.", "COVERED", "B5a-add-six-r"),
    # shape 34
    ("Add two mana of any one color.", "COVERED", "B5a-add-any-color"),
    # shape 35
    (
        "As an additional cost to cast this spell, discard a card.",
        "COVERED",
        "B5a-addl-cost-discard",
    ),
    # shape 36
    (
        "As an additional cost to cast this spell, sacrifice a creature.",
        "COVERED",
        "B5a-addl-cost-sacrifice",
    ),
    # shape 37
    (
        "As long as an opponent has eight or more cards in their graveyard, this creature gets +2/+1 and has deathtouch.",
        "UNCOV",
        "",
    ),
    # shape 38
    (
        "As long as the top card of your library is a Goblin card, this creature has all activated abilities of that card.",
        "UNCOV",
        "",
    ),
    # shape 39
    (
        "As long as you control a creature with power 4 or greater, this creature can attack as though it didn't have defender.",
        "UNCOV",
        "",
    ),
    # shape 40
    (
        "As long as you've drawn two or more cards this turn, this creature gets +0/+2 and has vigilance.",
        "COVERED",
        "B5a-gnarled-sage",
    ),
    # shape 41
    ("As this enchantment enters, choose a card name.", "UNCOV", ""),
    # shape 42
    ("Attacking creatures you control get +1/+0.", "COVERED", "B5a-attacking-pt"),
    # shape 43
    (
        "Battalion — Whenever this creature and at least two other creatures attack, put a +1/+1 counter on this creature.",
        "COVERED",
        "B5a-battalion",
    ),
    # shape 44
    ("Choose a card name other than a basic land card name.", "UNCOV", ""),
    # shape 45
    ("Choose one or more —", "UNCOV", ""),
    # shape 46
    ("Choose one —", "UNCOV", ""),
    # shape 47
    (
        "Counter target instant or sorcery spell unless its controller pays {3}.",
        "COVERED",
        "B5a-counter-unless-sps",
    ),
    # shape 48
    (
        "Counter target spell unless its controller pays {1}.",
        "COVERED",
        "B5a-counter-unless-spell",
    ),
    # shape 49
    ("Counter target spell.", "COVERED", "B5a-counter-spell"),
    # shape 50
    (
        "Create an X/X blue and red Weird creature token, where X is the number of instant and sorcery cards in your graveyard.",
        "COVERED",
        "B5a-weird-token",
    ),
    # shape 51
    (
        "Create two 1/1 red Goblin Wizard creature tokens with prowess.",
        "COVERED",
        "B5a-goblin-wizard-tokens",
    ),
    # shape 52
    (
        "Deathtouch (Any amount of damage this deals to a creature is enough to destroy it.)",
        "COVERED",
        "B5a-remind-deathtouch",
    ),
    # shape 53
    ("Defender (This creature can't attack.)", "COVERED", "B5a-remind-defender"),
    # shape 54
    ("Destroy all Equipment attached to that creature.", "UNCOV", ""),
    # shape 55
    (
        "Destroy target creature or planeswalker with mana value 3 or less.",
        "COVERED",
        "B5a-destroy-cw-pw-mv-le",
    ),
    # shape 56
    ("Destroy target creature or planeswalker.", "COVERED", "B5a-destroy-cw-pw"),
    # shape 57
    (
        "Destroy target creature with power 4 or greater.",
        "COVERED",
        "B5a-destroy-power-ge",
    ),
    # shape 58
    ("Destroy target creature.", "COVERED", "B5a-destroy-creature"),
    # shape 59
    ("Destroy target tapped creature.", "COVERED", "B5a-destroy-tapped-creature"),
    # shape 60
    ("Discard a card: Tap this creature.", "COVERED", "B5a-discard-tap-self"),
    # shape 61
    ("Discard a card: This creature can't be blocked this turn.", "UNCOV", ""),
    # shape 62
    (
        "Double strike (This creature deals both first-strike and regular combat damage.)",
        "COVERED",
        "B5a-remind-double-strike",
    ),
    # shape 63
    (
        "Double the power of target creature until end of turn.",
        "COVERED",
        "B5a-double-power",
    ),
    # shape 64
    (
        "Draw a card, then draw cards equal to the number of cards named Frantic Inventory in your graveyard.",
        "COVERED",
        "B5a-draw-frantic-inventory",
    ),
    # shape 65
    ("Draw a card.", "COVERED", "B5a-draw-one"),
    # shape 66
    (
        "Draw three cards, then discard a card.",
        "COVERED",
        "B5a-draw-three-then-discard",
    ),
    # shape 67
    ("Draw two cards.", "COVERED", "B5a-draw-two"),
    # shape 68
    ("During your turn, Radha has first strike.", "UNCOV", ""),
    # shape 69
    ("During your turn, this spell costs {2}{U}{U} less to cast.", "UNCOV", ""),
    # shape 70
    (
        "Each creature you control with a +1/+1 counter on it has trample.",
        "COVERED",
        "B5a-trample-counter",
    ),
    # shape 71
    ("Each opponent who can't loses 3 life.", "UNCOV", ""),
    # shape 72
    ("Each player loses 2 life.", "COVERED", "B5a-lose-life-each-player"),
    # shape 73
    (
        "Enchanted creature doesn't untap during its controller's untap step.",
        "UNCOV",
        "",
    ),
    # shape 74
    (
        "Enchanted creature gets +2/+2 and attacks each combat if able.",
        "COVERED",
        "B5a-enchant-pt-attacks",
    ),
    # shape 75
    (
        'Enchanted creature gets +2/+0 and has "When this creature dies, draw a card."',
        "COVERED",
        "B5a-enchant-pt-death-draw",
    ),
    # shape 76
    (
        "Enchanted creature gets +1/+1 and has flying.",
        "COVERED",
        "B5a-enchant-pt-flying",
    ),
    # shape 77
    (
        "Enchanted creature gets +1/+0 and has trample.",
        "COVERED",
        "B5a-enchant-pt-trample",
    ),
    # shape 78
    (
        "Enchanted creature gets +2/+2, has first strike, and is a Knight in addition to its other types.",
        "COVERED",
        "B5a-enchant-pt-firststrike-knight",
    ),
    # shape 79
    (
        "Enchanted creature gets +3/+1, has flying, and is a Demon in addition to its other types.",
        "COVERED",
        "B5a-enchant-pt-flying-demon",
    ),
    # shape 80
    (
        'Enchanted creature has "Whenever you gain life, put that many +1/+1 counters on this creature."',
        "COVERED",
        "B5a-enchant-gain-life",
    ),
    # shape 81
    (
        "Enchanted permanent can't attack or block, and its activated abilities can't be activated unless they're mana abilities.",
        "UNCOV",
        "",
    ),
    # shape 82
    ("End the turn.", "COVERED", "B5a-end-turn"),
    # shape 83
    (
        "Equip {1} ({1}: Attach to target creature you control. Equip only as a sorcery.)",
        "COVERED",
        "B5a-equip",
    ),
    # shape 84
    (
        "Equipped creature gets +1/+1 for each soul counter on this Equipment.",
        "UNCOV",
        "",
    ),
    # shape 85
    ("Equipped creature gets +1/+1.", "COVERED", "B5a-equipped-pt"),
    # shape 86
    ("Exile Experimental Overload.", "COVERED", "B5a-exile-self"),
    # shape 87
    ("Exile target creature or planeswalker.", "COVERED", "B5a-exile-cw-pw"),
    # shape 88
    ("Exile target creature.", "COVERED", "B5a-exile-creature"),
    # shape 89
    ("Exile target nonland permanent.", "COVERED", "B5a-exile-nonland"),
    # shape 90
    ("Exile that card until this creature leaves the battlefield.", "UNCOV", ""),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry() -> TemplateRegistry:
    """Build a TemplateRegistry with all B5a templates."""
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
    not on the outcome wrappers (AbilityOutcome/EffectOutcome/KeywordOutcome/
    AdditionalCostOutcome).
    """
    if isinstance(outcome, AbilityOutcome):
        return outcome.ability
    if isinstance(outcome, EffectOutcome):
        return outcome.effect
    if isinstance(outcome, KeywordOutcome):
        return KeywordAbility(keyword=outcome.keyword, params=outcome.params)
    if isinstance(outcome, AdditionalCostOutcome):
        return outcome.cost
    if isinstance(outcome, ActivationGateOutcome):
        return outcome.condition
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
    """Verify the B5a template collection is well-formed."""

    def test_45_templates(self) -> None:
        self.assertEqual(len(TEMPLATES), 45)

    def test_unique_tids(self) -> None:
        tids = [t.tid for t in TEMPLATES]
        self.assertEqual(len(tids), len(set(tids)), "duplicate tid found")

    def test_all_bucket_b5a(self) -> None:
        for t in TEMPLATES:
            self.assertEqual(t.bucket, "B5a", f"{t.tid} has bucket {t.bucket}")

    def test_all_priority_50(self) -> None:
        for t in TEMPLATES:
            self.assertEqual(t.priority, 50, f"{t.tid} has priority {t.priority}")

    def test_registry_accepts_all(self) -> None:
        reg = _make_registry()
        self.assertEqual(len(reg), 45)


# ---------------------------------------------------------------------------
# Test: Shape Table Integrity
# ---------------------------------------------------------------------------


class TestShapeTable(unittest.TestCase):
    """Verify the embedded 90-shape table is consistent."""

    def test_90_entries(self) -> None:
        self.assertEqual(len(SHAPES), 90)

    def test_unique_sentences(self) -> None:
        sents = [s[0] for s in SHAPES]
        self.assertEqual(len(sents), len(set(sents)), "duplicate sentence in SHAPES")

    def test_category_counts(self) -> None:
        rr = sum(1 for s in SHAPES if s[1] == "RR")
        covered = sum(1 for s in SHAPES if s[1] == "COVERED")
        uncov = sum(1 for s in SHAPES if s[1] == "UNCOV")
        self.assertEqual(rr, 23, f"RR count {rr} != 23")
        self.assertEqual(covered, 49, f"COVERED count {covered} != 49")
        self.assertEqual(uncov, 18, f"UNCOV count {uncov} != 18")

    def test_covered_tids_valid_and_unique_45(self) -> None:
        covered_tids = [s[2] for s in SHAPES if s[1] == "COVERED"]
        unique_tids = set(covered_tids)
        self.assertEqual(
            len(unique_tids), 45, f"expected 45 unique tids, got {len(unique_tids)}"
        )
        # All tids start with B5a-
        for tid in unique_tids:
            self.assertTrue(tid.startswith("B5a-"), f"bad tid: {tid}")

    def test_rr_and_uncov_have_empty_tid(self) -> None:
        for sent, cat, tid in SHAPES:
            if cat in ("RR", "UNCOV"):
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
# Test: UNCOVERED Attribute
# ---------------------------------------------------------------------------


class TestUncovered(unittest.TestCase):
    """Verify the UNCOVERED attribute is well-formed and pinned to SHAPES."""

    def test_18_rows(self) -> None:
        self.assertEqual(len(UNCOVERED), 18)

    def test_unique_sorted_keys(self) -> None:
        keys = [k for k, _ in UNCOVERED]
        self.assertEqual(len(keys), len(set(keys)), "duplicate shape_key in UNCOVERED")
        self.assertEqual(keys, sorted(keys), "UNCOVERED not sorted by shape_key")

    def test_nonempty_reasons(self) -> None:
        for key, reason in UNCOVERED:
            self.assertTrue(reason, f"empty reason for {key!r}")

    def test_shapes_pin(self) -> None:
        """T4 pin: SHAPES UNCOV keys == UNCOVERED keys."""
        shapes_keys = {
            re.sub(r"\d+", "N", sent) for sent, cat, _ in SHAPES if cat == "UNCOV"
        }
        uncov_keys = {k for k, _ in UNCOVERED}
        self.assertEqual(
            shapes_keys,
            uncov_keys,
            f"SHAPES UNCOV keys != UNCOVERED keys. "
            f"only in SHAPES: {shapes_keys - uncov_keys}; "
            f"only in UNCOVERED: {uncov_keys - shapes_keys}",
        )

    def test_zero_match_per_row(self) -> None:
        """Each UNCOVERED key normalizes to a sentence that matches no template."""
        reg = _make_registry()
        for key, _ in UNCOVERED:
            # Find a concrete sentence from SHAPES that normalizes to this key
            concrete = None
            for sent, cat, _ in SHAPES:
                if cat == "UNCOV" and re.sub(r"\d+", "N", sent) == key:
                    concrete = sent
                    break
            if concrete is None:
                self.fail(f"no concrete sentence for UNCOVERED key {key!r}")
            matches = reg.match(concrete)
            self.assertEqual(
                len(matches),
                0,
                f"UNCOVERED key {key!r} has a matching template: "
                f"{matches[0].template.tid if matches else 'none'}",
            )


# ---------------------------------------------------------------------------
# Test: PC-3 Matching
# ---------------------------------------------------------------------------


class TestMatching(unittest.TestCase):
    """PC-3: every B5a sentence fullmatches at most one template."""

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
# Test: Rule-Reminder Pre-Consumption
# ---------------------------------------------------------------------------


class TestRuleReminder(unittest.TestCase):
    """Verify _is_rule_reminder correctly classifies RR and land shapes."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = _make_registry()

    def test_rr_shapes_are_full_paren(self) -> None:
        """All 23 RR shapes should be consumed as full_paren rule reminders."""
        for sent, cat, _ in SHAPES:
            if cat != "RR":
                continue
            # Build a dummy RawCard (keywords don't matter for full-paren)
            raw = _raw("TestCard", (sent,), types=("Creature", "Beast"))
            rr = _is_rule_reminder(sent, raw)
            if rr is None:
                self.fail(f"RR shape not detected: {sent[:60]}")
            self.assertEqual(rr.reason, "full_paren", f"wrong reason: {sent[:60]}")

    def test_rr_shapes_have_no_template_match(self) -> None:
        """RR shapes should not match any template (they're pre-consumed)."""
        for sent, cat, _ in SHAPES:
            if cat != "RR":
                continue
            matches = self.reg.match(sent)
            self.assertEqual(
                len(matches),
                0,
                f"RR shape matched template: {sent[:60]}",
            )

    def test_basic_land_shapes_escape_rule_reminder(self) -> None:
        """Basic-land ({T}: Add {C}.) shapes are NOT rule reminders
        (activated-cost exception)."""
        for sent, cat, _ in SHAPES:
            if cat != "COVERED" or "B5a-land-add" not in _:
                continue
            raw = _raw("Swamp", (sent,), types=("Basic", "Land"), subtypes=("Swamp",))
            rr = _is_rule_reminder(sent, raw)
            self.assertIsNone(
                rr, f"basic-land shape wrongly consumed as rule reminder: {sent}"
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

    def test_land_add_structure(self) -> None:
        """B5a-land-add: ActivatedAbility, CostTap, ADD_MANA amount=1."""
        for sent, cat, tid in SHAPES:
            if tid != "B5a-land-add":
                continue
            matches = self.reg.match(sent)
            outcome = matches[0].outcome
            if not isinstance(outcome, AbilityOutcome):
                self.fail(f"expected AbilityOutcome, got {type(outcome)}")
            ab = outcome.ability
            if not isinstance(ab, ActivatedAbility):
                self.fail(f"expected ActivatedAbility, got {type(ab)}")
            # Cost should be CostTap
            self.assertEqual(len(ab.cost.parts), 1)
            self.assertIsInstance(ab.cost.parts[0], CostTap)
            # Effect should be ADD_MANA
            if not isinstance(ab.effect, Atom):
                self.fail(f"expected Atom, got {type(ab.effect)}")
            self.assertEqual(ab.effect.verb, Verb.ADD_MANA)
            p = _pairs_dict(ab.effect)
            self.assertEqual(p["controller"], ControllerRef.YOU)
            self.assertEqual(p["amount"], QConst(1))
            # Color matches the sentence (extract the color inside "Add {X}")
            m_color = re.search(r"Add \{([WUBRC])\}", sent)
            if m_color is None:
                self.fail(f"could not extract color from {sent}")
            self.assertEqual(p["color"], m_color.group(1))
            return
        self.fail("no B5a-land-add shapes found")

    def test_additional_cost_discard_structure(self) -> None:
        """B5a-addl-cost-discard: AdditionalCostOutcome, CostDiscard(1 from hand)."""
        outcome = self._match_outcome("B5a-addl-cost-discard")
        if not isinstance(outcome, AdditionalCostOutcome):
            self.fail(f"expected AdditionalCostOutcome, got {type(outcome)}")
        cost = outcome.cost
        self.assertEqual(len(cost.parts), 1)
        cd = cost.parts[0]
        if not isinstance(cd, CostDiscard):
            self.fail(f"expected CostDiscard, got {type(cd)}")
        sel = cd.target
        self.assertEqual(sel.count, QConst(1))
        self.assertEqual(sel.mode, SelectorMode.CHOOSE)
        flt = sel.filter
        if not isinstance(flt, FAnd):
            self.fail(f"expected FAnd filter, got {type(flt)}")
        self.assertEqual(len(flt.children), 0)
        self.assertEqual(sel.zone.kind, ZoneKind.HAND)
        self.assertEqual(sel.zone.controller, ControllerRef.YOU)

    def test_additional_cost_sacrifice_structure(self) -> None:
        """B5a-addl-cost-sacrifice: AdditionalCostOutcome, CostSacrifice(Creature)."""
        outcome = self._match_outcome("B5a-addl-cost-sacrifice")
        if not isinstance(outcome, AdditionalCostOutcome):
            self.fail(f"expected AdditionalCostOutcome, got {type(outcome)}")
        cost = outcome.cost
        self.assertEqual(len(cost.parts), 1)
        cs = cost.parts[0]
        if not isinstance(cs, CostSacrifice):
            self.fail(f"expected CostSacrifice, got {type(cs)}")
        sel = cs.target
        self.assertEqual(sel.count, QConst(1))
        self.assertEqual(sel.mode, SelectorMode.CHOOSE)
        flt = sel.filter
        if not isinstance(flt, FAtom):
            self.fail(f"expected FAtom filter, got {type(flt)}")
        self.assertEqual(flt.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(flt.string_value, "Creature")
        self.assertEqual(sel.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertEqual(sel.zone.controller, ControllerRef.YOU)

    def test_add_six_r(self) -> None:
        """B5a-add-six-r: EffectOutcome, ADD_MANA amount=6 color=R."""
        outcome = self._match_outcome("B5a-add-six-r")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.ADD_MANA)
        p = _pairs_dict(atom)
        self.assertEqual(p["controller"], ControllerRef.YOU)
        self.assertEqual(p["amount"], QConst(6))
        self.assertEqual(p["color"], "R")

    def test_add_any_color(self) -> None:
        """B5a-add-any-color: ADD_MANA amount=2 color='C' (lossy)."""
        outcome = self._match_outcome("B5a-add-any-color")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.ADD_MANA)
        p = _pairs_dict(atom)
        self.assertEqual(p["amount"], QConst(2))
        self.assertEqual(p["color"], "C")

    def test_attacking_pt(self) -> None:
        """B5a-attacking-pt: StaticAbility, MODIFY_PT, IS_ATTACKING in filter."""
        outcome = self._match_outcome("B5a-attacking-pt")
        ab_out = _as_ability(outcome)
        if not isinstance(ab_out.ability, StaticAbility):
            self.fail(f"expected StaticAbility, got {type(ab_out.ability)}")
        atom = _as_atom(ab_out.ability.effect)
        self.assertEqual(atom.verb, Verb.MODIFY_PT)
        p = _pairs_dict(atom)
        # Power +1, Toughness +0
        self.assertIsInstance(p["power"], PtDelta)
        self.assertEqual(p["power"].direction, PtDirection.INCREASE)
        self.assertEqual(p["power"].magnitude, QConst(1))
        self.assertIsInstance(p["toughness"], PtDelta)
        self.assertEqual(p["toughness"].magnitude, QConst(0))
        # Target should contain IS_ATTACKING in canonical form
        target = p["target"]
        self.assertIsInstance(target, Selector)
        canon = canonical_json(target)
        self.assertIn("IS_ATTACKING", canon)

    def test_counter_spell(self) -> None:
        """B5a-counter-spell: COUNTER_SPELL, TARGET zone STACK."""
        outcome = self._match_outcome("B5a-counter-spell")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.COUNTER_SPELL)
        p = _pairs_dict(atom)
        target = p["target"]
        self.assertIsInstance(target, Selector)
        self.assertEqual(target.mode, SelectorMode.TARGET)
        self.assertEqual(target.zone.kind, ZoneKind.STACK)

    def test_weird_token(self) -> None:
        """B5a-weird-token: CREATE_TOKEN, QCount P/T, Weird TokenSpec."""
        outcome = self._match_outcome("B5a-weird-token")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.CREATE_TOKEN)
        p = _pairs_dict(atom)
        spec = p["tokens"]
        self.assertIsInstance(spec, TokenSpec)
        self.assertEqual(spec.name, "Weird")
        self.assertEqual(spec.subtypes, ("Weird",))
        self.assertEqual(p["count"], QConst(1))
        # P/T should be QCount (dynamic)
        self.assertIsInstance(spec.power, QCount)
        self.assertIsInstance(spec.toughness, QCount)

    def test_goblin_wizard_tokens(self) -> None:
        """B5a-goblin-wizard-tokens: CREATE_TOKEN count=2, Goblin Wizard 1/1 PROWESS."""
        outcome = self._match_outcome("B5a-goblin-wizard-tokens")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.CREATE_TOKEN)
        p = _pairs_dict(atom)
        spec = p["tokens"]
        self.assertIsInstance(spec, TokenSpec)
        self.assertEqual(spec.name, "Goblin Wizard")
        self.assertEqual(spec.subtypes, ("Goblin", "Wizard"))
        self.assertEqual(p["count"], QConst(2))
        self.assertEqual(spec.power, QConst(1))
        self.assertEqual(spec.toughness, QConst(1))
        self.assertIn(Keyword.PROWESS, spec.keywords)

    def test_remind_keywords(self) -> None:
        """B5a-remind-*: KeywordOutcome with correct Keyword enum."""
        expected = {
            "B5a-remind-deathtouch": Keyword.DEATHTOUCH,
            "B5a-remind-defender": Keyword.DEFENDER,
            "B5a-remind-double-strike": Keyword.DOUBLE_STRIKE,
        }
        for tid, kw in expected.items():
            outcome = self._match_outcome(tid)
            kw_out = _as_keyword(outcome)
            self.assertEqual(kw_out.keyword, kw, f"{tid}")
            self.assertEqual(kw_out.params, ())

    def test_destroy_family(self) -> None:
        """B5a-destroy-*: DESTROY verb, TARGET selector."""
        destroy_tids = [
            "B5a-destroy-creature",
            "B5a-destroy-cw-pw",
            "B5a-destroy-cw-pw-mv-le",
            "B5a-destroy-tapped-creature",
        ]
        for tid in destroy_tids:
            outcome = self._match_outcome(tid)
            eff = _as_effect(outcome)
            atom = _as_atom(eff.effect)
            self.assertEqual(atom.verb, Verb.DESTROY, f"{tid}")
            p = _pairs_dict(atom)
            target = p["target"]
            self.assertIsInstance(target, Selector, f"{tid}")
            self.assertEqual(target.mode, SelectorMode.TARGET, f"{tid}")
            self.assertEqual(target.zone.kind, ZoneKind.BATTLEFIELD, f"{tid}")

    def test_exile_family(self) -> None:
        """B5a-exile-*: EXILE verb, TARGET selector."""
        exile_tids = [
            "B5a-exile-creature",
            "B5a-exile-cw-pw",
            "B5a-exile-nonland",
            "B5a-exile-self",
        ]
        for tid in exile_tids:
            outcome = self._match_outcome(tid)
            eff = _as_effect(outcome)
            atom = _as_atom(eff.effect)
            self.assertEqual(atom.verb, Verb.EXILE, f"{tid}")
            p = _pairs_dict(atom)
            target = p["target"]
            self.assertIsInstance(target, Selector, f"{tid}")
            self.assertEqual(target.mode, SelectorMode.TARGET, f"{tid}")

    def test_discard_tap_self(self) -> None:
        """B5a-discard-tap-self: ActivatedAbility, CostDiscard, TAP IS_SOURCE."""
        outcome = self._match_outcome("B5a-discard-tap-self")
        ab_out = _as_ability(outcome)
        if not isinstance(ab_out.ability, ActivatedAbility):
            self.fail(f"expected ActivatedAbility, got {type(ab_out.ability)}")
        ab = ab_out.ability
        # Cost should be CostDiscard
        self.assertEqual(len(ab.cost.parts), 1)
        self.assertIsInstance(ab.cost.parts[0], CostDiscard)
        # Effect should be TAP
        atom = _as_atom(ab.effect)
        self.assertEqual(atom.verb, Verb.TAP)
        p = _pairs_dict(atom)
        target = p["target"]
        self.assertIsInstance(target, Selector)
        canon = canonical_json(target)
        self.assertIn("IS_SOURCE", canon)

    def test_draw_one(self) -> None:
        """B5a-draw-one: DRAW amount=1."""
        outcome = self._match_outcome("B5a-draw-one")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.DRAW)
        p = _pairs_dict(atom)
        self.assertEqual(p["amount"], QConst(1))

    def test_draw_two(self) -> None:
        """B5a-draw-two: DRAW amount=2."""
        outcome = self._match_outcome("B5a-draw-two")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.DRAW)
        p = _pairs_dict(atom)
        self.assertEqual(p["amount"], QConst(2))

    def test_draw_three_then_discard(self) -> None:
        """B5a-draw-three-then-discard: Seq(DRAW 3, DISCARD 1)."""
        outcome = self._match_outcome("B5a-draw-three-then-discard")
        eff = _as_effect(outcome)
        if not isinstance(eff.effect, Seq):
            self.fail(f"expected Seq, got {type(eff.effect)}")
        self.assertEqual(len(eff.effect.steps), 2)
        draw, discard = eff.effect.steps
        draw_atom = _as_atom(draw)
        self.assertEqual(draw_atom.verb, Verb.DRAW)
        self.assertEqual(_pairs_dict(draw_atom)["amount"], QConst(3))
        discard_atom = _as_atom(discard)
        self.assertEqual(discard_atom.verb, Verb.DISCARD)

    def test_draw_frantic_inventory(self) -> None:
        """B5a-draw-frantic-inventory: Seq(DRAW 1, DRAW QCount)."""
        outcome = self._match_outcome("B5a-draw-frantic-inventory")
        eff = _as_effect(outcome)
        if not isinstance(eff.effect, Seq):
            self.fail(f"expected Seq, got {type(eff.effect)}")
        self.assertEqual(len(eff.effect.steps), 2)
        first, second = eff.effect.steps
        first_atom = _as_atom(first)
        self.assertEqual(first_atom.verb, Verb.DRAW)
        self.assertEqual(_pairs_dict(first_atom)["amount"], QConst(1))
        second_atom = _as_atom(second)
        self.assertEqual(second_atom.verb, Verb.DRAW)
        self.assertIsInstance(_pairs_dict(second_atom)["amount"], QCount)

    def test_trample_counter(self) -> None:
        """B5a-trample-counter: StaticAbility, GRANT_ABILITY, PLUS_1_PLUS_1."""
        outcome = self._match_outcome("B5a-trample-counter")
        ab_out = _as_ability(outcome)
        if not isinstance(ab_out.ability, StaticAbility):
            self.fail(f"expected StaticAbility, got {type(ab_out.ability)}")
        atom = _as_atom(ab_out.ability.effect)
        self.assertEqual(atom.verb, Verb.GRANT_ABILITY)
        p = _pairs_dict(atom)
        ability = p["ability"]
        self.assertIsInstance(ability, KeywordAbility)
        self.assertEqual(ability.keyword, Keyword.TRAMPLE)
        # Target filter should contain PLUS_1_PLUS_1 counter
        target = p["target"]
        canon = canonical_json(target)
        self.assertIn("PLUS_1_PLUS_1", canon)

    def test_lose_life(self) -> None:
        """B5a-lose-life-each-player: LOSE_LIFE controller=ANY amount=2."""
        outcome = self._match_outcome("B5a-lose-life-each-player")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.LOSE_LIFE)
        p = _pairs_dict(atom)
        self.assertEqual(p["controller"], ControllerRef.ANY)
        self.assertEqual(p["amount"], QConst(2))

    def test_enchant_pt_family(self) -> None:
        """B5a-enchant-pt-*: StaticAbility, Seq with MODIFY_PT step 0."""
        enchant_tids = [
            "B5a-enchant-pt-attacks",
            "B5a-enchant-pt-death-draw",
            "B5a-enchant-pt-flying",
            "B5a-enchant-pt-trample",
            "B5a-enchant-pt-firststrike-knight",
            "B5a-enchant-pt-flying-demon",
        ]
        for tid in enchant_tids:
            outcome = self._match_outcome(tid)
            ab_out = _as_ability(outcome)
            if not isinstance(ab_out.ability, StaticAbility):
                self.fail(f"{tid}: expected StaticAbility, got {type(ab_out.ability)}")
            if not isinstance(ab_out.ability.effect, Seq):
                self.fail(f"{tid}: expected Seq, got {type(ab_out.ability.effect)}")
            steps = ab_out.ability.effect.steps
            self.assertGreaterEqual(len(steps), 2, f"{tid}: expected >=2 steps")
            # Step 0 is MODIFY_PT
            step0 = _as_atom(steps[0])
            self.assertEqual(step0.verb, Verb.MODIFY_PT, f"{tid}")
            p = _pairs_dict(step0)
            self.assertIsInstance(p["power"], PtDelta, f"{tid}")
            self.assertIsInstance(p["toughness"], PtDelta, f"{tid}")

    def test_enchant_pt_attacks_mandate(self) -> None:
        """B5a-enchant-pt-attacks: step 1 is MANDATE_ATTACK."""
        outcome = self._match_outcome("B5a-enchant-pt-attacks")
        ab_out = _as_ability(outcome)
        if not isinstance(ab_out.ability, StaticAbility):
            self.fail("expected StaticAbility")
        if not isinstance(ab_out.ability.effect, Seq):
            self.fail("expected Seq")
        steps = ab_out.ability.effect.steps
        self.assertEqual(len(steps), 2)
        step1 = _as_atom(steps[1])
        self.assertEqual(step1.verb, Verb.MANDATE_ATTACK)

    def test_enchant_pt_flying_grant(self) -> None:
        """B5a-enchant-pt-flying: step 1 is GRANT_ABILITY FLYING."""
        outcome = self._match_outcome("B5a-enchant-pt-flying")
        ab_out = _as_ability(outcome)
        if not isinstance(ab_out.ability, StaticAbility):
            self.fail("expected StaticAbility")
        if not isinstance(ab_out.ability.effect, Seq):
            self.fail("expected Seq")
        steps = ab_out.ability.effect.steps
        self.assertEqual(len(steps), 2)
        step1 = _as_atom(steps[1])
        self.assertEqual(step1.verb, Verb.GRANT_ABILITY)
        p = _pairs_dict(step1)
        self.assertIsInstance(p["ability"], KeywordAbility)
        self.assertEqual(p["ability"].keyword, Keyword.FLYING)

    def test_enchant_pt_firststrike_knight(self) -> None:
        """B5a-enchant-pt-firststrike-knight: 3 steps (PT, GRANT_ABILITY, GRANT_TYPE)."""
        outcome = self._match_outcome("B5a-enchant-pt-firststrike-knight")
        ab_out = _as_ability(outcome)
        if not isinstance(ab_out.ability, StaticAbility):
            self.fail("expected StaticAbility")
        if not isinstance(ab_out.ability.effect, Seq):
            self.fail("expected Seq")
        steps = ab_out.ability.effect.steps
        self.assertEqual(len(steps), 3)
        self.assertEqual(_as_atom(steps[1]).verb, Verb.GRANT_ABILITY)
        self.assertEqual(_as_atom(steps[2]).verb, Verb.GRANT_TYPE)

    def test_enchant_pt_flying_demon(self) -> None:
        """B5a-enchant-pt-flying-demon: 3 steps (PT, GRANT_ABILITY, GRANT_TYPE)."""
        outcome = self._match_outcome("B5a-enchant-pt-flying-demon")
        ab_out = _as_ability(outcome)
        if not isinstance(ab_out.ability, StaticAbility):
            self.fail("expected StaticAbility")
        if not isinstance(ab_out.ability.effect, Seq):
            self.fail("expected Seq")
        steps = ab_out.ability.effect.steps
        self.assertEqual(len(steps), 3)
        self.assertEqual(_as_atom(steps[1]).verb, Verb.GRANT_ABILITY)
        self.assertEqual(_as_atom(steps[2]).verb, Verb.GRANT_TYPE)

    def test_end_turn(self) -> None:
        """B5a-end-turn: END_TURN verb."""
        outcome = self._match_outcome("B5a-end-turn")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.END_TURN)

    def test_equip(self) -> None:
        """B5a-equip: ActivatedAbility, CostManaGeneric(1), ATTACH."""
        outcome = self._match_outcome("B5a-equip")
        ab_out = _as_ability(outcome)
        if not isinstance(ab_out.ability, ActivatedAbility):
            self.fail(f"expected ActivatedAbility, got {type(ab_out.ability)}")
        ab = ab_out.ability
        # Cost: one CostManaGeneric with amount=1
        self.assertEqual(len(ab.cost.parts), 1)
        cpart = ab.cost.parts[0]
        if not isinstance(cpart, CostManaGeneric):
            self.fail(f"expected CostManaGeneric, got {type(cpart)}")
        self.assertEqual(cpart.amount, QConst(1))
        # Effect: ATTACH
        atom = _as_atom(ab.effect)
        self.assertEqual(atom.verb, Verb.ATTACH)

    def test_equipped_pt(self) -> None:
        """B5a-equipped-pt: StaticAbility, MODIFY_PT."""
        outcome = self._match_outcome("B5a-equipped-pt")
        ab_out = _as_ability(outcome)
        if not isinstance(ab_out.ability, StaticAbility):
            self.fail(f"expected StaticAbility, got {type(ab_out.ability)}")
        atom = _as_atom(ab_out.ability.effect)
        self.assertEqual(atom.verb, Verb.MODIFY_PT)
        p = _pairs_dict(atom)
        self.assertIsInstance(p["power"], PtDelta)
        self.assertIsInstance(p["toughness"], PtDelta)

    def test_battalion(self) -> None:
        """B5a-battalion: KeywordOutcome with BATTALION keyword, QConst(2)."""
        outcome = self._match_outcome("B5a-battalion")
        kw = _as_keyword(outcome)
        self.assertEqual(kw.keyword, Keyword.BATTALION)
        self.assertEqual(len(kw.params), 1)
        self.assertIsInstance(kw.params[0], QConst)
        if not isinstance(kw.params[0], QConst):
            self.fail(f"expected QConst, got {type(kw.params[0])}")
        self.assertEqual(kw.params[0].value, 2)

    def test_destroy_power_ge(self) -> None:
        """B5a-destroy-power-ge: EffectOutcome, DESTROY verb, POWER_GE filter."""
        outcome = self._match_outcome("B5a-destroy-power-ge")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.DESTROY)
        p = _pairs_dict(atom)
        target = p["target"]
        if not isinstance(target, Selector):
            self.fail(f"expected Selector, got {type(target)}")
        self.assertEqual(target.mode, SelectorMode.TARGET)
        # Filter should be FAnd with TYPE_EQ Creature + POWER_GE
        if not isinstance(target.filter, FAnd):
            self.fail(f"expected FAnd filter, got {type(target.filter)}")
        preds = [
            child
            for child in target.filter.children
            if isinstance(child, FAtom) and child.pred == FAtomPred.POWER_GE
        ]
        self.assertEqual(len(preds), 1)
        self.assertIsInstance(preds[0].count, QConst)
        if not isinstance(preds[0].count, QConst):
            self.fail(f"expected QConst, got {type(preds[0].count)}")
        self.assertEqual(preds[0].count.value, 4)

    def test_double_power(self) -> None:
        """B5a-double-power: EffectOutcome, SET_PT verb, QBin MUL."""
        outcome = self._match_outcome("B5a-double-power")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.SET_PT)
        p = _pairs_dict(atom)
        # Power should be QBin(MUL, QConst(2), QProp(target, POWER))
        power = p["power"]
        if not isinstance(power, QBin):
            self.fail(f"expected QBin, got {type(power)}")
        self.assertEqual(power.op, QBinOp.MUL)
        self.assertIsInstance(power.left, QConst)
        if not isinstance(power.left, QConst):
            self.fail(f"expected QConst, got {type(power.left)}")
        self.assertEqual(power.left.value, 2)
        self.assertIsInstance(power.right, QProp)
        if not isinstance(power.right, QProp):
            self.fail(f"expected QProp, got {type(power.right)}")
        self.assertEqual(power.right.field, QPropField.POWER)
        # Toughness should be QProp(target, TOUGHNESS)
        self.assertIsInstance(p["toughness"], QProp)
        if not isinstance(p["toughness"], QProp):
            self.fail(f"expected QProp, got {type(p['toughness'])}")
        self.assertEqual(p["toughness"].field, QPropField.TOUGHNESS)
        # Duration should be DurationEot
        self.assertIsInstance(p["duration"], DurationEot)

    def test_enchant_gain_life(self) -> None:
        """B5a-enchant-gain-life: AbilityOutcome, StaticAbility, GRANT_ABILITY."""
        outcome = self._match_outcome("B5a-enchant-gain-life")
        ab_out = _as_ability(outcome)
        if not isinstance(ab_out.ability, StaticAbility):
            self.fail(f"expected StaticAbility, got {type(ab_out.ability)}")
        atom = _as_atom(ab_out.ability.effect)
        self.assertEqual(atom.verb, Verb.GRANT_ABILITY)
        p = _pairs_dict(atom)
        ability = p["ability"]
        if not isinstance(ability, TriggeredAbility):
            self.fail(f"expected TriggeredAbility, got {type(ability)}")
        self.assertIsInstance(ability.event, LifeGainedEvent)
        if not isinstance(ability.event, LifeGainedEvent):
            self.fail(f"expected LifeGainedEvent, got {type(ability.event)}")
        self.assertEqual(ability.event.controller, ControllerRef.YOU)
        # Effect should be PUT_COUNTER with QProp(event, AMOUNT)
        eff_atom = _as_atom(ability.effect)
        self.assertEqual(eff_atom.verb, Verb.PUT_COUNTER)
        ep = _pairs_dict(eff_atom)
        self.assertIsInstance(ep["count"], QProp)
        if not isinstance(ep["count"], QProp):
            self.fail(f"expected QProp, got {type(ep['count'])}")
        self.assertEqual(ep["count"].field, QPropField.AMOUNT)
        self.assertEqual(ep["counter_kind"], CounterKind.PLUS_1_PLUS_1)

    def test_gnarled_sage(self) -> None:
        """B5a-gnarled-sage: StaticAbility, Seq(MODIFY_PT, GRANT_ABILITY) under gate."""
        outcome = self._match_outcome("B5a-gnarled-sage")
        ab_out = _as_ability(outcome)
        sa = ab_out.ability
        if not isinstance(sa, StaticAbility):
            self.fail(f"expected StaticAbility, got {type(sa)}")
        cond = sa.condition
        if not isinstance(cond, FAtom):
            self.fail(f"expected FAtom condition, got {type(cond)}")
        self.assertEqual(cond.pred, FAtomPred.CARDS_DRAWN_THIS_TURN_GE)
        self.assertEqual(cond.count, QConst(2))
        self.assertEqual(cond.who, ControllerRef.YOU)
        seq = sa.effect
        if not isinstance(seq, Seq):
            self.fail(f"expected Seq effect, got {type(seq)}")
        self.assertEqual(len(seq.steps), 2)
        pt = seq.steps[0]
        if not isinstance(pt, Atom):
            self.fail(f"expected Atom, got {type(pt)}")
        self.assertEqual(pt.verb, Verb.MODIFY_PT)
        p = _pairs_dict(pt)
        self.assertIsInstance(p["power"], PtDelta)
        self.assertEqual(p["power"].direction, PtDirection.INCREASE)
        self.assertEqual(p["power"].magnitude, QConst(0))
        self.assertIsInstance(p["toughness"], PtDelta)
        self.assertEqual(p["toughness"].direction, PtDirection.INCREASE)
        self.assertEqual(p["toughness"].magnitude, QConst(2))
        grant = seq.steps[1]
        if not isinstance(grant, Atom):
            self.fail(f"expected Atom, got {type(grant)}")
        self.assertEqual(grant.verb, Verb.GRANT_ABILITY)
        ability = _pairs_dict(grant)["ability"]
        self.assertIsInstance(ability, KeywordAbility)
        self.assertEqual(ability.keyword, Keyword.VIGILANCE)

    def test_activate_only_death(self) -> None:
        """B5a-activate-only-death: ActivationGateOutcome, DIED_THIS_TURN."""
        outcome = self._match_outcome("B5a-activate-only-death")
        if not isinstance(outcome, ActivationGateOutcome):
            self.fail(f"expected ActivationGateOutcome, got {type(outcome)}")
        cond = outcome.condition
        if not isinstance(cond, FAtom):
            self.fail(f"expected FAtom condition, got {type(cond)}")
        self.assertEqual(cond.pred, FAtomPred.DIED_THIS_TURN)

    def test_activate_only_flying(self) -> None:
        """B5a-activate-only-flying: gate, CONTROLLER_COUNT_GE(FAnd(Creature, flying))."""
        outcome = self._match_outcome("B5a-activate-only-flying")
        if not isinstance(outcome, ActivationGateOutcome):
            self.fail(f"expected ActivationGateOutcome, got {type(outcome)}")
        cond = outcome.condition
        if not isinstance(cond, FAtom):
            self.fail(f"expected FAtom condition, got {type(cond)}")
        self.assertEqual(cond.pred, FAtomPred.CONTROLLER_COUNT_GE)
        self.assertEqual(cond.count, QConst(1))
        inner = cond.inner_filter
        if not isinstance(inner, FAnd):
            self.fail(f"expected FAnd inner filter, got {type(inner)}")
        self.assertEqual(len(inner.children), 2)
        first, second = inner.children
        if not isinstance(first, FAtom):
            self.fail(f"expected FAtom, got {type(first)}")
        self.assertEqual(first.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(first.string_value, "Creature")
        if not isinstance(second, FAtom):
            self.fail(f"expected FAtom, got {type(second)}")
        self.assertEqual(second.pred, FAtomPred.KEYWORD_HAS)
        self.assertEqual(second.keyword, Keyword.FLYING)

    def test_counter_unless_sps(self) -> None:
        """B5a-counter-unless-sps: COUNTER_SPELL, FOr(Instant,Sorcery), unless {3}."""
        outcome = self._match_outcome("B5a-counter-unless-sps")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.COUNTER_SPELL)
        p = _pairs_dict(atom)
        target = p["target"]
        self.assertIsInstance(target, Selector)
        self.assertEqual(target.mode, SelectorMode.TARGET)
        self.assertEqual(target.zone.kind, ZoneKind.STACK)
        self.assertEqual(target.zone.controller, ControllerRef.ANY)
        filt = target.filter
        self.assertIsInstance(filt, FOr)
        self.assertEqual(len(filt.children), 2)
        first, second = filt.children
        self.assertIsInstance(first, FAtom)
        self.assertEqual(first.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(first.string_value, "Instant")
        self.assertIsInstance(second, FAtom)
        self.assertEqual(second.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(second.string_value, "Sorcery")
        unless = p["unless"]
        self.assertIsInstance(unless, Cost)
        self.assertEqual(len(unless.parts), 1)
        cmg = unless.parts[0]
        self.assertIsInstance(cmg, CostManaGeneric)
        self.assertEqual(cmg.amount, QConst(3))

    def test_counter_unless_spell(self) -> None:
        """B5a-counter-unless-spell: COUNTER_SPELL, empty filter, unless {1}."""
        outcome = self._match_outcome("B5a-counter-unless-spell")
        eff = _as_effect(outcome)
        atom = _as_atom(eff.effect)
        self.assertEqual(atom.verb, Verb.COUNTER_SPELL)
        p = _pairs_dict(atom)
        target = p["target"]
        self.assertIsInstance(target, Selector)
        self.assertEqual(target.mode, SelectorMode.TARGET)
        self.assertEqual(target.zone.kind, ZoneKind.STACK)
        filt = target.filter
        self.assertIsInstance(filt, FAnd)
        self.assertEqual(len(filt.children), 0)
        unless = p["unless"]
        self.assertIsInstance(unless, Cost)
        self.assertEqual(len(unless.parts), 1)
        cmg = unless.parts[0]
        self.assertIsInstance(cmg, CostManaGeneric)
        self.assertEqual(cmg.amount, QConst(1))


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
        self.assertEqual(len(seen), 45, f"only {len(seen)} unique tids tested")


# ---------------------------------------------------------------------------
# Test: End-to-End compile_card
# ---------------------------------------------------------------------------


class TestEndToEndCompile(unittest.TestCase):
    """Full compile_card pipeline with realistic RawCard stubs."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.reg = _make_registry()

    def test_swamp_land(self) -> None:
        """Swamp: ({T}: Add {B}.) → one ActivatedAbility, no unparsed."""
        raw = _raw(
            "Swamp",
            ("({T}: Add {B}.)",),
            types=("Basic", "Land"),
            subtypes=("Swamp",),
            colors=("B",),
            mana_value=0,
        )
        result = compile_card(raw, self.reg)
        # The land-add template produces an AbilityOutcome (ActivatedAbility)
        self.assertEqual(len(result.card.abilities), 1)
        self.assertIsInstance(result.card.abilities[0], ActivatedAbility)
        self.assertEqual(len(result.unparsed), 0)
        self.assertEqual(len(result.rule_reminders), 0)
        self.assertEqual(len(result.ambiguities), 0)

    def test_finishing_blow_instant(self) -> None:
        """Finishing Blow: covered + uncovered → SpellAbility(INSTANT) + 1 unparsed."""
        raw = _raw(
            "Finishing Blow",
            (
                "Destroy target creature or planeswalker.",
                "Destroy all Equipment attached to that creature.",
            ),
            types=("Instant",),
            colors=("R",),
            mana_cost_raw="{R}",
            mana_value=1,
        )
        result = compile_card(raw, self.reg)
        # One spell ability from the covered sentence
        self.assertEqual(len(result.card.abilities), 1)
        # One unparsed sentence (the uncovered one)
        self.assertEqual(len(result.unparsed), 1)
        self.assertEqual(
            result.unparsed[0][0],
            "Destroy all Equipment attached to that creature.",
        )
        self.assertEqual(len(result.rule_reminders), 0)
        self.assertEqual(len(result.ambiguities), 0)

    def test_additional_cost_discard_attached(self) -> None:
        """Sorcery: effect sentence + additional-cost sentence → SpellAbility with
        a CostDiscard in additional_costs, nothing unparsed."""
        raw = _raw(
            "Blood Ritual",
            (
                "Destroy target creature or planeswalker.",
                "As an additional cost to cast this spell, discard a card.",
            ),
            types=("Sorcery",),
            colors=("B",),
            mana_cost_raw="{B}{B}",
            mana_value=2,
        )
        result = compile_card(raw, self.reg)
        self.assertEqual(len(result.card.abilities), 1)
        ab = result.card.abilities[0]
        if not isinstance(ab, SpellAbility):
            self.fail(f"expected SpellAbility, got {type(ab)}")
        self.assertEqual(len(ab.additional_costs), 1)
        cost = ab.additional_costs[0]
        self.assertEqual(len(cost.parts), 1)
        if not isinstance(cost.parts[0], CostDiscard):
            self.fail(f"expected CostDiscard, got {type(cost.parts[0])}")
        self.assertEqual(len(result.unparsed), 0)
        self.assertEqual(len(result.ambiguities), 0)

    def test_alchemists_gift_rule_reminder(self) -> None:
        """Alchemist's Gift: long parenthetical → rule_reminder, no abilities."""
        sent = (
            "(Any amount of damage a creature with deathtouch deals to a creature "
            "is enough to destroy it. Damage dealt by a creature with lifelink "
            "also causes its controller to gain that much life.)"
        )
        raw = _raw(
            "Alchemist's Gift",
            (sent,),
            types=("Instant",),
            colors=("B",),
            mana_cost_raw="{1}{B}",
            mana_value=2,
        )
        result = compile_card(raw, self.reg)
        # One rule reminder detected
        self.assertEqual(len(result.rule_reminders), 1)
        self.assertEqual(result.rule_reminders[0].reason, "full_paren")
        # No abilities (the sentence was consumed as a reminder)
        self.assertEqual(len(result.card.abilities), 0)
        self.assertEqual(len(result.unparsed), 0)

    def test_seasoned_hallowblade_creature(self) -> None:
        """Seasoned Hallowblade: covered + uncovered → ActivatedAbility + 1 unparsed."""
        raw = _raw(
            "Seasoned Hallowblade",
            (
                "Discard a card: Tap this creature.",
                "Activate only as a sorcery.",
            ),
            types=("Creature",),
            subtypes=("Angel", "Warrior"),
            colors=("W",),
            mana_cost_raw="{W}",
            mana_value=1,
            power_raw="1",
            toughness_raw="2",
        )
        result = compile_card(raw, self.reg)
        # One activated ability from the covered sentence
        self.assertEqual(len(result.card.abilities), 1)
        self.assertIsInstance(result.card.abilities[0], ActivatedAbility)
        # One unparsed (the speed restriction)
        self.assertEqual(len(result.unparsed), 1)
        self.assertEqual(result.unparsed[0][0], "Activate only as a sorcery.")
        self.assertEqual(len(result.rule_reminders), 0)

    def test_cancel_counter_spell(self) -> None:
        """Cancel: Counter target spell. → SpellAbility(INSTANT)."""
        raw = _raw(
            "Cancel",
            ("Counter target spell.",),
            types=("Instant",),
            colors=("U",),
            mana_cost_raw="{U}",
            mana_value=1,
        )
        result = compile_card(raw, self.reg)
        self.assertEqual(len(result.card.abilities), 1)
        self.assertEqual(len(result.unparsed), 0)
        self.assertEqual(len(result.rule_reminders), 0)

    def test_short_sword_equip(self) -> None:
        """Short Sword: Equip {1} + Equipped creature gets +1/+1.
        → ActivatedAbility + StaticAbility."""
        raw = _raw(
            "Short Sword",
            (
                "Equip {1} ({1}: Attach to target creature you control. "
                "Equip only as a sorcery.)",
                "Equipped creature gets +1/+1.",
            ),
            types=("Artifact", "Equipment"),
            mana_cost_raw="{2}",
            mana_value=2,
        )
        result = compile_card(raw, self.reg)
        # Two abilities: ActivatedAbility (equip) + StaticAbility (PT)
        self.assertEqual(len(result.card.abilities), 2)
        self.assertIsInstance(result.card.abilities[0], ActivatedAbility)
        self.assertIsInstance(result.card.abilities[1], StaticAbility)
        self.assertEqual(len(result.unparsed), 0)

    def test_furor_enchant(self) -> None:
        """Furor of the Bitten: Enchanted creature gets +2/+2 and attacks.
        → StaticAbility with Seq."""
        raw = _raw(
            "Furor of the Bitten",
            ("Enchanted creature gets +2/+2 and attacks each combat if able.",),
            types=("Enchantment", "Aura"),
            subtypes=("Enchantment", "Aura"),
            colors=("R",),
            mana_cost_raw="{R}",
            mana_value=1,
        )
        result = compile_card(raw, self.reg)
        self.assertEqual(len(result.card.abilities), 1)
        self.assertIsInstance(result.card.abilities[0], StaticAbility)
        self.assertEqual(len(result.unparsed), 0)

    def test_discontinuity_end_turn(self) -> None:
        """Discontinuity: End the turn. → SpellAbility(INSTANT)."""
        raw = _raw(
            "Discontinuity",
            ("End the turn.",),
            types=("Instant",),
            colors=("U",),
            mana_cost_raw="{U}",
            mana_value=1,
        )
        result = compile_card(raw, self.reg)
        self.assertEqual(len(result.card.abilities), 1)
        self.assertEqual(len(result.unparsed), 0)


# ---------------------------------------------------------------------------
# Test: Optional B5a.json Cross-Check
# ---------------------------------------------------------------------------


class TestB5aJsonCrossCheck(unittest.TestCase):
    """Cross-check the embedded SHAPES table against the source JSON.

    Skipped if B5a.json is not present (it lives in /tmp, not the repo).
    """

    B5A_PATH = "/tmp/opencode/phase1_buckets/B5a.json"

    @classmethod
    @unittest.skipUnless(
        os.path.exists(B5A_PATH),
        f"B5a.json not found at {B5A_PATH}",
    )
    def setUpClass(cls) -> None:
        with open(cls.B5A_PATH) as f:
            cls.json_data: dict[str, list[list[str]]] = json.load(f)

    def test_90_shapes_in_json(self) -> None:
        self.assertEqual(len(self.json_data), 90)

    def test_all_json_sentences_in_table(self) -> None:
        """Every sentence in B5a.json values must appear in SHAPES."""
        table_sents = {s[0] for s in SHAPES}
        json_sents: set[str] = set()
        for pairs in self.json_data.values():
            for _card, sent in pairs:
                json_sents.add(sent)
        self.assertEqual(json_sents, table_sents)

    def test_uncovered_keys_are_json_keys(self) -> None:
        """Every UNCOVERED shape_key is a valid B5a.json key."""
        json_keys = set(self.json_data.keys())
        uncov_keys = {k for k, _ in UNCOVERED}
        self.assertEqual(
            uncov_keys,
            uncov_keys & json_keys,
            f"UNCOVERED keys not in B5a.json: {uncov_keys - json_keys}",
        )

    def test_uncovered_equals_registry_unmatched(self) -> None:
        """Dynamically compute unmatched non-RR shapes and compare with UNCOVERED."""
        reg = _make_registry()
        json_keys = set(self.json_data.keys())
        unmatched: set[str] = set()
        for sent, cat, _ in SHAPES:
            if cat == "RR":
                continue
            key = re.sub(r"\d+", "N", sent)
            if key in json_keys and not reg.match(sent):
                unmatched.add(key)
        uncov_keys = {k for k, _ in UNCOVERED}
        self.assertEqual(
            unmatched,
            uncov_keys,
            f"registry-unmatched != UNCOVERED. "
            f"only unmatched: {unmatched - uncov_keys}; "
            f"only in UNCOVERED: {uncov_keys - unmatched}",
        )
