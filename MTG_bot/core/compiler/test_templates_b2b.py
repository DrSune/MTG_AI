"""Tests for the B2b triggered-ability template bucket.

B2b is the second "triggered ability" bucket: every template compiles a
sentence of the form "When X <trigger>, <effect>." or "Whenever X <trigger>,
<effect>." into a ``TriggeredAbility(event, condition, effect)``.

Layout mirrors ``test_templates_b2a.py``: a coverage class (bucket shape/
occurrence counts, the public API, the pinned EXPECTED table, PC-3 ambiguity
and fingerprint stability) plus an events class and an effect-structure class
that drive the registry end-to-end with concrete oracle sentences and assert
the exact IR each template produces.

Pinned bucket facts (measured against /tmp/opencode/phase1_buckets/B2b.json):
62 shapes, 76 occurrences, 61 covered shapes, 75 matched occurrences, and the
60 templates in ``templates_b2b.TEMPLATES`` (with 1 declared UNCOVERED
shape).  The 9-B batch added ``B2b-do-tap-or-untap`` (Tolarian Kraken s2,
R9-9/C24 do-continuation merge).  The round-10 batch added
``B2b-attackers-against-me-draw`` (Mangara, the Diplomat, R10-3).
The bucket priority is 50 (NOT the 100 used by B1/B3/B4).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from MTG_bot.core.ability_tree import (
    Atom,
    BecomesBlockedEvent,
    CardDrawnEvent,
    CastSpellEvent,
    Choose,
    ControllerRef,
    Cost,
    CostManaGeneric,
    CounterKind,
    CounterPlacedEvent,
    CreatureDiesEvent,
    DamageDealtEvent,
    DeclareAttackersEvent,
    DeclareBlockersEvent,
    DurationEot,
    EachPlayer,
    FAnd,
    FAtom,
    FAtomPred,
    Filter,
    FNot,
    FOr,
    Keyword,
    KeywordAbility,
    LifeGainedEvent,
    LoyaltyActivatedEvent,
    OptionalEffect,
    PtDelta,
    PtDirection,
    QAgg,
    QConst,
    QCount,
    QProp,
    QPropField,
    QUnbounded,
    SacrificeEvent,
    Selector,
    SelectorMode,
    Seq,
    TapStateEvent,
    TargetingEvent,
    TokenSpec,
    TriggeredAbility,
    Verb,
    Zone,
    ZoneChangeEvent,
    ZoneKind,
    ZonePosition,
    canonical_json,
    fingerprint,
)
from MTG_bot.core.compiler import templates_b2b
from MTG_bot.core.compiler.compiler import _merge_do_continuation
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    Match,
    RuleReminderOutcome,
    TemplateRegistry,
)

_B2B_PATH = Path("/tmp/opencode/phase1_buckets/B2b.json")

# Every covered shape key -> (template tid, template name).
EXPECTED: dict[str, tuple[str, str]] = {
    "When this creature enters, you may search your library for a card named Alpine Watchdog and/or a card named Igneous Cur, reveal them, put them into your hand, then shuffle.": (
        "B2b-alpine-houndmaster-etb",
        "Alpine Houndmaster ETB",
    ),
    "When this creature enters, you may search your library for a creature card with mana value N or greater, reveal it, put it into your hand, then shuffle.": (
        "B2b-fierce-empath-etb",
        "Fierce Empath ETB",
    ),
    "When this enchantment enters, draw a card, then discard a card.": (
        "B2b-teferis-tutelage-etb",
        "Teferi's Tutelage ETB",
    ),
    "When this land enters, scry N.": (
        "B2b-temple-etb-scry",
        "Temple ETB Scry",
    ),
    "When this land enters, you gain N life.": (
        "B2b-temple-etb-gain-life",
        "Temple ETB Gain Life",
    ),
    "Whenever a creature an opponent controls dies, that player loses N life.": (
        "B2b-massacre-wurm",
        "Massacre Wurm",
    ),
    "Whenever a creature you control with deathtouch attacks, each opponent loses N life and you gain N life.": (
        "B2b-hooded-blightfang",
        "Hooded Blightfang",
    ),
    "Whenever equipped creature dies, put a soul counter on this Equipment.": (
        "B2b-malefic-scythe",
        "Malefic Scythe",
    ),
    "Whenever one or more +N/+N counters are put on another non-Hydra creature you control, put a +N/+N counter on this creature.": (
        "B2b-wildwood-scorge",
        "Wildwood Scourge",
    ),
    "Whenever this creature attacks, create a N/N white Bird creature token with flying that's tapped and attacking.": (
        "B2b-falconer-adept",
        "Falconer Adept",
    ),
    "Whenever this creature attacks, draw a card.": (
        "B2b-library-larcenist",
        "Library Larcenist",
    ),
    "Whenever this creature attacks, it gets +X/+N until end of turn, where X is the number of other attacking creatures.": (
        "B2b-alpine-houndmaster-attack",
        "Alpine Houndmaster Attack",
    ),
    "Whenever this creature attacks, other creatures you control get +N/+N until end of turn.": (
        "B2b-bolt-hound",
        "Bolt Hound",
    ),
    "Whenever this creature attacks, scry N.": (
        "B2b-spined-megalodon",
        "Spined Megalodon",
    ),
    "Whenever this creature attacks, you may tap any number of untapped creatures you control.": (
        "B2b-siege-striker",
        "Siege Striker",
    ),
    "Whenever this creature is dealt damage, it deals that much damage to target opponent.": (
        "B2b-brash-taunter",
        "Brash Taunter",
    ),
    "Whenever this creature is dealt damage, you gain N life and create a N/N green Saproling creature token.": (
        "B2b-sporeweb-weaver",
        "Sporeweb Weaver",
    ),
    "Whenever this creature or another creature you control dies, if it had a +N/+N counter on it, create a N/N white Knight creature token with vigilance.": (
        "B2b-basris-lieutenant",
        "Basri's Lieutenant",
    ),
    "When this creature enters, you may search your library and/or graveyard for a card named Chandra, Flame's Catalyst, reveal it, and put it into your hand.": (
        "B2b-named-card-search",
        "Named Card Search ETB",
    ),
    "When this creature enters, you may search your library and/or graveyard for a card named Garruk, Savage Herald, reveal it, and put it into your hand.": (
        "B2b-named-card-search",
        "Named Card Search ETB",
    ),
    "When this creature enters, you may search your library and/or graveyard for a card named Teferi, Timeless Voyager, reveal it, and put it into your hand.": (
        "B2b-named-card-search",
        "Named Card Search ETB",
    ),
    "When this enchantment leaves the battlefield, you lose the game.": (
        "B2b-nine-lives-leave",
        "Nine Lives Leave",
    ),
    "Whenever a creature you control with power N or greater enters, draw a card.": (
        "B2b-power-ge-enters-draw",
        "Power N+ Enters Draw",
    ),
    "Whenever an opponent casts their second spell each turn, draw a card.": (
        "B2b-opponent-second-spell-draw",
        "Opponent Second Spell Draw",
    ),
    "Whenever another creature you control enters, this creature deals damage equal to that creature's power to any target.": (
        "B2b-other-enters-power-damage",
        "Other Enters Power Damage",
    ),
    "Whenever another creature you control with flying enters, this creature gets +N/+N until end of turn.": (
        "B2b-flying-enters-self-boost",
        "Flying Enters Self Boost",
    ),
    "Whenever this creature becomes untapped, you may pay {N}.": (
        "B2b-untapped-pay",
        "Untapped Pay",
    ),
    "Whenever this creature or another Rogue you control enters, each opponent mills two cards.": (
        "B2b-other-rogue-enters-mill",
        "Other Rogue Enters Mill",
    ),
    "Whenever you cast a Cat spell, create a N/N white Dog creature token.": (
        "B2b-cast-cat-create-dog",
        "Cast Cat Create Dog",
    ),
    "Whenever you cast a Dog spell, create a N/N green Cat creature token.": (
        "B2b-cast-dog-create-cat",
        "Cast Dog Create Cat",
    ),
    "Whenever you cast a noncreature spell, put a +N/+N counter on this creature.": (
        "B2b-noncreature-counter",
        "Noncreature Cast Counter",
    ),
    "Whenever you cast a noncreature spell, you may have this enchantment become a N/N Sphinx creature with flying in addition to its other types until end of turn.": (
        "B2b-riddleform",
        "Riddleform",
    ),
    "Whenever you cast a spell that's white, blue, black, or red, put a +N/+N counter on this creature.": (
        "B2b-colored-cast-counter",
        "Colored Cast Counter",
    ),
    "Whenever you draw a card, put a +N/+N counter on this creature.": (
        "B2b-draw-counter",
        "Draw Counter",
    ),
    "Whenever you draw a card, target opponent mills two cards.": (
        "B2b-draw-target-mill",
        "Draw Target Mill",
    ),
    "Whenever you draw a card, this creature gets +N/+N until end of turn.": (
        "B2b-draw-self-boost",
        "Draw Self Boost",
    ),
    "Whenever you draw a card, you may pay {N}.": (
        "B2b-draw-pay",
        "Draw Pay",
    ),
    "Whenever you sacrifice a permanent, this creature deals N damage to any target.": (
        "B2b-sacrifice-any-damage",
        "Sacrifice Any Damage",
    ),
    "When this creature enters, you may search your library for a basic land card, put that card onto the battlefield tapped, then shuffle.": (
        "B2b-etb-basic-land",
        "ETB Basic Land Search",
    ),
    "When this enchantment enters, if you control a creature with power N or greater, draw a card.": (
        "B2b-etb-power-condition-draw",
        "ETB Power Condition Draw",
    ),
    "Whenever this creature attacks, if you control a Teferi planeswalker, draw a card.": (
        "B2b-attack-teferi-condition-draw",
        "Attack Teferi Condition Draw",
    ),
    "Whenever this creature attacks, if you control a creature with power N or greater, this creature gets +N/+N until end of turn.": (
        "B2b-attack-power-condition-self-boost",
        "Attack Power Condition Self Boost",
    ),
    "Whenever you attack with two or more creatures with flying, draw a card.": (
        "B2b-attack-two-flying-draw",
        "Attack Two Flying Draw",
    ),
    "Whenever you gain life, target opponent loses that much life.": (
        "B2b-gain-life-target-opponent",
        "Gain Life Target Opponent",
    ),
    # --- Round 5 (grammar round 4/5 shapes) ---
    "Whenever this creature becomes the target of a spell or ability an opponent controls, you may draw two cards.": (
        "B2b-warden-of-the-woods",
        "Warden of the Woods",
    ),
    "Whenever this creature deals combat damage to a player, you may draw a card.": (
        "B2b-jeskai-elder",
        "Jeskai Elder",
    ),
    "Whenever a source you control deals noncombat damage to an opponent, this creature deals that much damage to target creature or planeswalker that player controls.": (
        "B2b-chandras-incinerator",
        "Chandra's Incinerator",
    ),
    "Whenever a source you control deals noncombat damage to an opponent, this creature gets +N/+N and gains double strike until end of turn.": (
        "B2b-chandras-pyreling",
        "Chandra's Pyreling",
    ),
    "Whenever this creature attacks, prevent all combat damage that would be dealt this turn to Dogs you control.": (
        "B2b-pack-leader",
        "Pack Leader",
    ),
    "Whenever this creature becomes blocked by a creature, that creature's controller loses N life and you gain N life.": (
        "B2b-gloom-sower",
        "Gloom Sower",
    ),
    "Whenever a creature you control with deathtouch deals damage to a planeswalker, destroy that planeswalker.": (
        "B2b-hooded-blightfang-pw",
        "Hooded Blightfang Planeswalker",
    ),
    "Whenever one or more Cats you control deal combat damage to a player, destroy up to one target artifact or enchantment that player controls.": (
        "B2b-feline-sovereign",
        "Feline Sovereign",
    ),
    "Whenever an opponent casts a spell from anywhere other than their hand, draw a card.": (
        "B2b-ghostly-pilferer-cast",
        "Ghostly Pilferer Cast",
    ),
    "Whenever you cast your first instant or sorcery spell each turn, copy that spell.": (
        "B2b-double-vision-copy",
        "Double Vision Copy",
    ),
    "Whenever this creature deals combat damage to a player or planeswalker, look at that many cards from the top of your library.": (
        "B2b-garruks-harbinger",
        "Garruk's Harbinger",
    ),
    "Whenever you draw your second card each turn, create a N/N green Cat creature token.": (
        "B2b-jolrael-cat-token",
        "Jolrael Cat Token",
    ),
    "Whenever you draw your second card each turn, this creature gains flying until end of turn.": (
        "B2b-mystic-skyfish",
        "Mystic Skyfish",
    ),
    "Whenever you activate a loyalty ability of a Chandra planeswalker, this creature deals N damage to each opponent.": (
        "B2b-keral-keep-disciples",
        "Keral Keep Disciples",
    ),
    "Whenever this creature blocks a creature with flying, this creature gets +N/+N until end of turn.": (
        "B2b-blocks-flying-pump",
        "Snarespinner",
    ),
    "When you do, you may tap or untap target creature.": (
        "B2b-do-tap-or-untap",
        "Kraken Do Tap Or Untap",
    ),
    "Whenever an opponent attacks with creatures, if two or more of those "
    "creatures are attacking you and/or planeswalkers you control, draw a card.": (
        "B2b-attackers-against-me-draw",
        "Mangara, the Diplomat",
    ),
}


# ---------------------------------------------------------------------------
# Loading & registry helpers
# ---------------------------------------------------------------------------


def _load_b2b() -> dict[str, tuple[tuple[str, str], ...]]:
    raw: dict[str, list[list[str]]] = json.loads(_B2B_PATH.read_text())
    return {
        shape_key: tuple((entry[0], entry[1]) for entry in entries)
        for shape_key, entries in raw.items()
    }


def _registry() -> TemplateRegistry:
    reg = TemplateRegistry()
    for template in templates_b2b.TEMPLATES:
        reg.register(template)
    return reg


def _single_match(reg: TemplateRegistry, sentence: str) -> Match:
    matches = reg.match(sentence)
    assert len(matches) == 1, (
        f"expected exactly one match for {sentence!r}, got {len(matches)}"
    )
    return matches[0]


def _match_value(match: Match) -> object:
    """The IR value of a match for hash/canonical tests — the ability for
    AbilityOutcome templates (the B2b norm), the bare effect for
    EffectOutcome continuations (the 9-B do-continuation row)."""
    outcome = match.outcome
    if isinstance(outcome, AbilityOutcome):
        return outcome.ability
    if isinstance(outcome, EffectOutcome):
        return outcome.effect
    raise AssertionError(f"unexpected outcome kind: {type(outcome).__name__}")


def _ability(match: Match) -> TriggeredAbility:
    outcome = match.outcome
    assert isinstance(outcome, AbilityOutcome), (
        f"expected AbilityOutcome, got {type(outcome).__name__}"
    )
    ability = outcome.ability
    assert isinstance(ability, TriggeredAbility), (
        f"expected TriggeredAbility, got {type(ability).__name__}"
    )
    return ability


# ---------------------------------------------------------------------------
# Effect navigation helpers
# ---------------------------------------------------------------------------


def _atom(ability: TriggeredAbility) -> Atom:
    effect = ability.effect
    assert isinstance(effect, Atom), f"expected Atom, got {type(effect).__name__}"
    return effect


def _seq(ability: TriggeredAbility) -> Seq:
    effect = ability.effect
    assert isinstance(effect, Seq), f"expected Seq, got {type(effect).__name__}"
    return effect


def _optional(ability: TriggeredAbility) -> OptionalEffect:
    effect = ability.effect
    assert isinstance(effect, OptionalEffect), (
        f"expected OptionalEffect, got {type(effect).__name__}"
    )
    return effect


def _atom_step(seq: Seq, index: int) -> Atom:
    step = seq.steps[index]
    assert isinstance(step, Atom), f"expected Atom step, got {type(step).__name__}"
    return step


def _seq_inner(option: OptionalEffect) -> Seq:
    inner = option.inner
    assert isinstance(inner, Seq), f"expected Seq inner, got {type(inner).__name__}"
    return inner


def _atom_inner(option: OptionalEffect) -> Atom:
    inner = option.inner
    assert isinstance(inner, Atom), f"expected Atom inner, got {type(inner).__name__}"
    return inner


# ---------------------------------------------------------------------------
# Atom-arg narrowing helpers
# ---------------------------------------------------------------------------


def _selector(atom: Atom, role: str) -> Selector:
    value = atom.args.get(role)
    assert isinstance(value, Selector), (
        f"role {role!r} expected Selector, got {type(value).__name__}"
    )
    return value


def _qconst(atom: Atom, role: str) -> QConst:
    value = atom.args.get(role)
    assert isinstance(value, QConst), (
        f"role {role!r} expected QConst, got {type(value).__name__}"
    )
    return value


def _qcount(atom: Atom, role: str) -> QCount:
    value = atom.args.get(role)
    assert isinstance(value, QCount), (
        f"role {role!r} expected QCount, got {type(value).__name__}"
    )
    return value


def _qprop(atom: Atom, role: str) -> QProp:
    value = atom.args.get(role)
    assert isinstance(value, QProp), (
        f"role {role!r} expected QProp, got {type(value).__name__}"
    )
    return value


def _pt_delta(atom: Atom, role: str) -> PtDelta:
    value = atom.args.get(role)
    assert isinstance(value, PtDelta), (
        f"role {role!r} expected PtDelta, got {type(value).__name__}"
    )
    return value


def _token(atom: Atom, role: str) -> TokenSpec:
    value = atom.args.get(role)
    assert isinstance(value, TokenSpec), (
        f"role {role!r} expected TokenSpec, got {type(value).__name__}"
    )
    return value


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------


def _leaf_atoms(a_filter: Filter) -> list[FAtom]:
    if isinstance(a_filter, FAtom):
        return [a_filter]
    if isinstance(a_filter, (FAnd, FOr)):
        out: list[FAtom] = []
        for child in a_filter.children:
            out.extend(_leaf_atoms(child))
        return out
    if isinstance(a_filter, FNot):
        return _leaf_atoms(a_filter.inner)
    raise AssertionError(f"unexpected filter type {type(a_filter).__name__}")


def _find_atom(a_filter: Filter, pred: FAtomPred) -> FAtom:
    for atom in _leaf_atoms(a_filter):
        if atom.pred is pred:
            return atom
    raise AssertionError(f"no FAtom with pred {pred.name} in filter")


def _contains_not(a_filter: Filter, pred: FAtomPred) -> bool:
    if isinstance(a_filter, FNot):
        return (
            isinstance(a_filter.inner, FAtom) and a_filter.inner.pred is pred
        ) or _contains_not(a_filter.inner, pred)
    if isinstance(a_filter, (FAnd, FOr)):
        return any(_contains_not(child, pred) for child in a_filter.children)
    return False


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------


class TestB2bCoverage(unittest.TestCase):
    def setUp(self) -> None:
        self.data = _load_b2b()
        self.reg = _registry()

    def test_bucket_file_has_62_shapes_and_76_occurrences(self) -> None:
        self.assertEqual(len(self.data), 62)
        total = sum(len(entries) for entries in self.data.values())
        self.assertEqual(total, 76)

    def test_public_api_counts(self) -> None:
        self.assertEqual(len(templates_b2b.TEMPLATES), 60)
        self.assertEqual(len(templates_b2b.UNCOVERED), 1)

    def test_bucket_labels_b2b(self) -> None:
        for template in templates_b2b.TEMPLATES:
            self.assertEqual(template.bucket, "B2b", template.tid)

    def test_priority_is_50(self) -> None:
        self.assertEqual(templates_b2b._PRIORITY, 50)
        for template in templates_b2b.TEMPLATES:
            self.assertEqual(template.priority, 50, template.tid)

    def test_tids_are_unique(self) -> None:
        tids = [t.tid for t in templates_b2b.TEMPLATES]
        self.assertEqual(len(set(tids)), len(tids))

    def test_covered_shape_and_occurrence_counts(self) -> None:
        covered_shapes = 0
        matched_occurrences = 0
        for entries in self.data.values():
            shape_matched = False
            for _card, sentence in entries:
                if self.reg.match(sentence):
                    matched_occurrences += 1
                    shape_matched = True
            if shape_matched:
                covered_shapes += 1
        self.assertEqual(covered_shapes, 61)
        self.assertEqual(matched_occurrences, 75)

    def test_uncovered_shapes_are_exactly_the_unmatched_shapes(self) -> None:
        unmatched: set[str] = set()
        for shape_key, entries in self.data.items():
            if not any(self.reg.match(sentence) for _card, sentence in entries):
                unmatched.add(shape_key)
        declared = {shape_key for shape_key, _reason in templates_b2b.UNCOVERED}
        self.assertEqual(unmatched, declared)

    def test_uncovered_sentences_do_not_match(self) -> None:
        for shape_key, _reason in templates_b2b.UNCOVERED:
            self.assertIn(shape_key, self.data)
            for _card, sentence in self.data[shape_key]:
                self.assertEqual(self.reg.match(sentence), (), sentence)

    def test_expected_table_covers_exactly_the_matched_shapes(self) -> None:
        covered: set[str] = set()
        for shape_key, entries in self.data.items():
            if any(self.reg.match(sentence) for _card, sentence in entries):
                covered.add(shape_key)
        self.assertEqual(set(EXPECTED), covered)
        self.assertEqual(len(EXPECTED), 61)

    def test_expected_table_matches_registry(self) -> None:
        for shape_key, (tid, name) in EXPECTED.items():
            matched: Match | None = None
            for _card, sentence in self.data[shape_key]:
                ms = self.reg.match(sentence)
                if ms:
                    matched = ms[0]
                    break
            if matched is None:
                self.fail(f"no template matched any sentence of {shape_key!r}")
            self.assertEqual(matched.template.tid, tid, shape_key)
            self.assertEqual(matched.template.name, name, shape_key)

    def test_pc3_ambiguity_is_zero(self) -> None:
        for shape_key, entries in self.data.items():
            for card, sentence in entries:
                matches = self.reg.match(sentence)
                if not matches:
                    continue
                canonicals = {canonical_json(_match_value(match)) for match in matches}
                self.assertEqual(
                    len(canonicals),
                    1,
                    f"PC-3 ambiguity for {card!r} / {shape_key!r}: {sentence!r}",
                )

    def test_fingerprint_is_stable(self) -> None:
        for shape_key, entries in self.data.items():
            for card, sentence in entries:
                matches = self.reg.match(sentence)
                if not matches:
                    continue
                first = fingerprint(_match_value(matches[0]))
                rematch = self.reg.match(sentence)
                self.assertTrue(rematch, sentence)
                second = fingerprint(_match_value(rematch[0]))
                self.assertEqual(
                    first,
                    second,
                    f"fingerprint unstable for {card!r} / {shape_key!r}: {sentence!r}",
                )


# ---------------------------------------------------------------------------
# Trigger events
# ---------------------------------------------------------------------------


class TestB2bTriggerEvents(unittest.TestCase):
    def setUp(self) -> None:
        self.reg = _registry()

    def test_etb_is_zone_change_to_battlefield(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "When this creature enters, you may search your library "
                "for a card named Alpine Watchdog and/or a card named Igneous Cur, "
                "reveal them, put them into your hand, then shuffle.",
            )
        )
        event = ability.event
        assert isinstance(event, ZoneChangeEvent)
        self.assertEqual(event.to_zone, Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU))
        self.assertEqual(event.from_zone, Zone(ZoneKind.ANY, ControllerRef.ANY))

    def test_etb_enchantment_is_zone_change(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "When this enchantment enters, draw a card, then discard a card.",
            )
        )
        event = ability.event
        assert isinstance(event, ZoneChangeEvent)
        self.assertEqual(event.to_zone, Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU))

    def test_etb_land_is_zone_change(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "When this land enters, scry 1.",
            )
        )
        event = ability.event
        assert isinstance(event, ZoneChangeEvent)
        self.assertEqual(event.to_zone, Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU))

    def test_massacre_wurm_is_creature_dies_opponent(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever a creature an opponent controls dies, "
                "that player loses 2 life.",
            )
        )
        event = ability.event
        assert isinstance(event, CreatureDiesEvent)
        assert isinstance(event.filter, FAnd)
        self._assert_has_type_eq_creature(event.filter)
        self._assert_has_controller_opponent(event.filter)

    def test_hooded_blightfang_is_declare_attackers_deathtouch(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever a creature you control with deathtouch attacks, "
                "each opponent loses 1 life and you gain 1 life.",
            )
        )
        event = ability.event
        assert isinstance(event, DeclareAttackersEvent)
        assert isinstance(event.filter, FAnd)
        self._assert_has_type_eq_creature(event.filter)
        self._assert_has_controller_you(event.filter)
        self._assert_has_keyword_deathtouch(event.filter)

    def test_malefic_scythe_is_creature_dies_attached(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever equipped creature dies, "
                "put a soul counter on this Equipment.",
            )
        )
        event = ability.event
        assert isinstance(event, CreatureDiesEvent)
        assert isinstance(event.filter, FAtom)
        self.assertIs(event.filter.pred, FAtomPred.IS_ATTACHED_TO_SOURCE)

    def test_wildwood_scorge_is_counter_placed_plus1(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever one or more +1/+1 counters are put on another "
                "non-Hydra creature you control, "
                "put a +1/+1 counter on this creature.",
            )
        )
        event = ability.event
        assert isinstance(event, CounterPlacedEvent)
        self.assertIs(event.counter_kind, CounterKind.PLUS_1_PLUS_1)
        assert isinstance(event.filter, FAnd)
        self._assert_has_type_eq_creature(event.filter)
        self._assert_has_controller_you(event.filter)
        self.assertTrue(_contains_not(event.filter, FAtomPred.IS_SOURCE))
        # FNot(SUBTYPE_EQ Hydra)
        self.assertTrue(_contains_not(event.filter, FAtomPred.SUBTYPE_EQ))

    def test_falconer_adept_is_attack_event(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature attacks, create a 1/1 white Bird "
                "creature token with flying that's tapped and attacking.",
            )
        )
        event = ability.event
        assert isinstance(event, DeclareAttackersEvent)
        assert isinstance(event.filter, FAtom)
        self.assertIs(event.filter.pred, FAtomPred.IS_SOURCE)

    def test_brash_taunter_is_damage_dealt_source(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature is dealt damage, "
                "it deals that much damage to target opponent.",
            )
        )
        event = ability.event
        assert isinstance(event, DamageDealtEvent)
        assert isinstance(event.filter, FAtom)
        self.assertIs(event.filter.pred, FAtomPred.IS_SOURCE)
        assert isinstance(event.amount, QProp)
        self.assertEqual(event.amount.referent, "event")
        self.assertIs(event.amount.field, QPropField.AMOUNT)
        self.assertIs(event.amount.agg, QAgg.FIRST)

    def test_basris_lieutenant_is_creature_dies_with_condition(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature or another creature you control dies, "
                "if it had a +1/+1 counter on it, "
                "create a 2/2 white Knight creature token with vigilance.",
            )
        )
        event = ability.event
        assert isinstance(event, CreatureDiesEvent)
        assert isinstance(event.filter, FAnd)
        self._assert_has_type_eq_creature(event.filter)
        self._assert_has_controller_you(event.filter)
        # Condition should be HAS_COUNTER
        cond = ability.condition
        self.assertIsNotNone(cond)
        assert isinstance(cond, FAtom)
        self.assertIs(cond.pred, FAtomPred.HAS_COUNTER)
        self.assertIs(cond.counter_kind, CounterKind.PLUS_1_PLUS_1)
        assert isinstance(cond.count, QConst)
        self.assertEqual(cond.count.value, 1)

    def test_named_card_search_is_etb_zone_change(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "When this creature enters, you may search your library "
                "and/or graveyard for a card named Chandra, Flame's Catalyst, "
                "reveal it, and put it into your hand.",
            )
        )
        event = ability.event
        assert isinstance(event, ZoneChangeEvent)
        self.assertEqual(event.from_zone, Zone(ZoneKind.ANY, ControllerRef.ANY))
        self.assertEqual(event.to_zone, Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU))

    def test_nine_lives_is_zone_change_battlefield_to_any(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "When this enchantment leaves the battlefield, you lose the game.",
            )
        )
        event = ability.event
        assert isinstance(event, ZoneChangeEvent)
        self.assertEqual(event.from_zone, Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU))
        self.assertEqual(event.to_zone, Zone(ZoneKind.ANY, ControllerRef.ANY))

    def test_power_ge_enters_is_zone_change_with_subject(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever a creature you control with power 4 or greater enters, "
                "draw a card.",
            )
        )
        event = ability.event
        assert isinstance(event, ZoneChangeEvent)
        self.assertEqual(event.to_zone, Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU))
        assert isinstance(event.subject, FAnd)
        self._assert_has_type_eq_creature(event.subject)
        self._assert_has_controller_you(event.subject)
        power = _find_atom(event.subject, FAtomPred.POWER_GE)
        assert isinstance(power.count, QConst)
        self.assertEqual(power.count.value, 4)

    def test_mangara_is_cast_spell_opponent_second(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever an opponent casts their second spell each turn, draw a card.",
            )
        )
        event = ability.event
        assert isinstance(event, CastSpellEvent)
        self.assertIs(event.actor.who, ControllerRef.OPPONENT)
        self.assertEqual(event.ordinal, 2)
        assert isinstance(event.filter, FAnd)
        self.assertEqual(len(event.filter.children), 0)

    def test_terror_of_peaks_is_other_enter(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever another creature you control enters, this creature "
                "deals damage equal to that creature's power to any target.",
            )
        )
        event = ability.event
        assert isinstance(event, ZoneChangeEvent)
        self.assertEqual(event.to_zone, Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU))
        assert isinstance(event.subject, FAnd)
        self._assert_has_type_eq_creature(event.subject)
        self._assert_has_controller_you(event.subject)
        self.assertTrue(_contains_not(event.subject, FAtomPred.IS_SOURCE))

    def test_watcher_spheres_is_flying_enter(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever another creature you control with flying enters, "
                "this creature gets +1/+1 until end of turn.",
            )
        )
        event = ability.event
        assert isinstance(event, ZoneChangeEvent)
        assert isinstance(event.subject, FAnd)
        self._assert_has_type_eq_creature(event.subject)
        self._assert_has_controller_you(event.subject)
        self._assert_has_keyword_flying(event.subject)
        self.assertTrue(_contains_not(event.subject, FAtomPred.IS_SOURCE))

    def test_ghostly_pilferer_is_tap_state_untapped(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature becomes untapped, you may pay {2}.",
            )
        )
        event = ability.event
        assert isinstance(event, TapStateEvent)
        self.assertFalse(event.tapped)
        assert isinstance(event.filter, FAtom)
        self.assertIs(event.filter.pred, FAtomPred.IS_SOURCE)

    def test_thieves_guild_is_enter_or_rogue(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature or another Rogue you control enters, "
                "each opponent mills two cards.",
            )
        )
        event = ability.event
        assert isinstance(event, ZoneChangeEvent)
        self.assertEqual(event.to_zone, Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU))
        assert isinstance(event.subject, FOr)
        self.assertEqual(len(event.subject.children), 2)
        self.assertTrue(
            any(
                isinstance(child, FAtom) and child.pred is FAtomPred.IS_SOURCE
                for child in event.subject.children
            )
        )
        rogue_branch = next(
            child for child in event.subject.children if isinstance(child, FAnd)
        )
        self._assert_has_subtype_rogue(rogue_branch)
        self._assert_has_controller_you(rogue_branch)
        self.assertTrue(_contains_not(rogue_branch, FAtomPred.IS_SOURCE))

    def test_cast_cat_is_cast_spell_subtype(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you cast a Cat spell, create a 1/1 white Dog creature token.",
            )
        )
        event = ability.event
        assert isinstance(event, CastSpellEvent)
        self.assertIs(event.actor.who, ControllerRef.YOU)
        assert isinstance(event.filter, FAnd)
        self._assert_has_type_eq_creature(event.filter)
        self._assert_has_subtype_cat(event.filter)

    def test_cast_dog_is_cast_spell_subtype(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you cast a Dog spell, create a 1/1 green Cat creature token.",
            )
        )
        event = ability.event
        assert isinstance(event, CastSpellEvent)
        self.assertIs(event.actor.who, ControllerRef.YOU)
        assert isinstance(event.filter, FAnd)
        self._assert_has_type_eq_creature(event.filter)
        self._assert_has_subtype_dog(event.filter)

    def test_noncreature_counter_is_cast_noncreature(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you cast a noncreature spell, put a +1/+1 counter "
                "on this creature.",
            )
        )
        event = ability.event
        assert isinstance(event, CastSpellEvent)
        self.assertIs(event.actor.who, ControllerRef.YOU)
        self.assertTrue(
            _contains_not(event.filter, FAtomPred.TYPE_EQ),
            "expected FNot(TYPE_EQ Creature) filter",
        )
        self._assert_has_type_eq_creature(event.filter)

    def test_quirion_dryad_is_cast_colored(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you cast a spell that's white, blue, black, or red, "
                "put a +1/+1 counter on this creature.",
            )
        )
        event = ability.event
        assert isinstance(event, CastSpellEvent)
        self.assertIs(event.actor.who, ControllerRef.YOU)
        # re-pinned 2026-10-29: V39 changes the filter from COLOR_IN (a subset
        # test: a green-blue spell failed it) to "has any of the four colors",
        # the FOr of COLOR_HAS (CR 105.2). FOr children are construction-
        # sorted (ontology §3 SET-R1a); the SET of colors is the pinned fact.
        assert isinstance(event.filter, FOr)
        self.assertTrue(all(c.pred is FAtomPred.COLOR_HAS for c in event.filter.children))
        self.assertEqual(
            sorted(c.color for c in event.filter.children), ["B", "R", "U", "W"]
        )

    def test_draw_counter_is_card_drawn_you(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you draw a card, put a +1/+1 counter on this creature.",
            )
        )
        event = ability.event
        assert isinstance(event, CardDrawnEvent)
        self.assertIs(event.actor.who, ControllerRef.YOU)

    def test_havoc_jester_is_sacrifice_you(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you sacrifice a permanent, this creature deals 1 "
                "damage to any target.",
            )
        )
        event = ability.event
        assert isinstance(event, SacrificeEvent)
        self.assertIs(event.actor.who, ControllerRef.YOU)

    def test_noncreature_counter_rejects_wrong_counter_size(self) -> None:
        with self.assertRaises(ValueError):
            self.reg.match(
                "Whenever you cast a noncreature spell, put a +2/+2 counter "
                "on this creature."
            )

    def test_solemn_simulacrum_etb_is_zone_change(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "When this creature enters, you may search your library "
                "for a basic land card, put that card onto the battlefield "
                "tapped, then shuffle.",
            )
        )
        event = ability.event
        assert isinstance(event, ZoneChangeEvent)
        self.assertEqual(event.to_zone, Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU))
        self.assertEqual(event.from_zone, Zone(ZoneKind.ANY, ControllerRef.ANY))

    def test_garruks_uprising_etb_power_condition(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "When this enchantment enters, if you control a creature "
                "with power 4 or greater, draw a card.",
            )
        )
        event = ability.event
        assert isinstance(event, ZoneChangeEvent)
        self.assertEqual(event.to_zone, Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU))
        cond = ability.condition
        assert isinstance(cond, FAtom)
        self.assertIs(cond.pred, FAtomPred.CONTROLLER_COUNT_GE)
        # AMENDED r18a (B-8): printed "a creature with power 4 or greater"
        # means ONE or more — the old pin froze the power THRESHOLD in the
        # count slot too, so the gate demanded four 4-power creatures and
        # silently false-fired with a single 4/4 (Historian Teferi's
        # count=1 precedent is the same shape now).
        self.assertEqual(cond.count, QConst(1))
        assert isinstance(cond.inner_filter, FAnd)
        self._assert_has_type_eq_creature(cond.inner_filter)
        power = _find_atom(cond.inner_filter, FAtomPred.POWER_GE)
        self.assertEqual(power.count, QConst(4))

    def test_historian_attack_teferi_condition(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature attacks, if you control a Teferi "
                "planeswalker, draw a card.",
            )
        )
        event = ability.event
        assert isinstance(event, DeclareAttackersEvent)
        assert isinstance(event.filter, FAtom)
        self.assertIs(event.filter.pred, FAtomPred.IS_SOURCE)
        cond = ability.condition
        assert isinstance(cond, FAtom)
        self.assertIs(cond.pred, FAtomPred.CONTROLLER_COUNT_GE)
        self.assertEqual(cond.count, QConst(1))
        assert isinstance(cond.inner_filter, FAnd)
        pw = _find_atom(cond.inner_filter, FAtomPred.TYPE_EQ)
        self.assertEqual(pw.string_value, "Planeswalker")
        name = _find_atom(cond.inner_filter, FAtomPred.NAME_CONTAINS)
        self.assertEqual(name.string_value, "Teferi")

    def test_ornery_attack_power_condition(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature attacks, if you control a creature "
                "with power 4 or greater, this creature gets +2/+2 until "
                "end of turn.",
            )
        )
        event = ability.event
        assert isinstance(event, DeclareAttackersEvent)
        assert isinstance(event.filter, FAtom)
        self.assertIs(event.filter.pred, FAtomPred.IS_SOURCE)
        cond = ability.condition
        assert isinstance(cond, FAtom)
        self.assertIs(cond.pred, FAtomPred.CONTROLLER_COUNT_GE)
        # C2 (batch 1, 2026-10-02) AMENDED: printed "A CREATURE with power
        # 4 or greater" is an existence claim — ONE such creature (the
        # threshold lives only in the POWER_GE filter). The old pin
        # witnessed the count=4 off-by-one (wave-3b suspect).
        self.assertEqual(cond.count, QConst(1))
        assert isinstance(cond.inner_filter, FAnd)
        self._assert_has_type_eq_creature(cond.inner_filter)
        power = _find_atom(cond.inner_filter, FAtomPred.POWER_GE)
        self.assertEqual(power.count, QConst(4))

    def test_tide_skimmer_attack_two_flying(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you attack with two or more creatures with flying, "
                "draw a card.",
            )
        )
        event = ability.event
        assert isinstance(event, DeclareAttackersEvent)
        assert isinstance(event.filter, FAnd)
        self._assert_has_type_eq_creature(event.filter)
        self._assert_has_controller_you(event.filter)
        self._assert_has_keyword_flying(event.filter)
        cond = ability.condition
        assert isinstance(cond, FAtom)
        self.assertIs(cond.pred, FAtomPred.CONTROLLER_COUNT_GE)
        self.assertEqual(cond.count, QConst(2))
        assert isinstance(cond.inner_filter, FAnd)
        self._assert_has_type_eq_creature(cond.inner_filter)
        self._assert_has_controller_you(cond.inner_filter)
        self._assert_has_keyword_flying(cond.inner_filter)
        attacking = _find_atom(cond.inner_filter, FAtomPred.IS_ATTACKING)
        del attacking  # just checking presence

    def test_vito_gain_life_event(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you gain life, target opponent loses that much life.",
            )
        )
        event = ability.event
        assert isinstance(event, LifeGainedEvent)
        self.assertIs(event.actor.who, ControllerRef.YOU)
        self.assertIsNone(ability.condition)

    # --- Round 5 (grammar round 4/5 shapes) ---

    def test_warden_of_the_woods_is_targeting_event(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature becomes the target of a spell or "
                "ability an opponent controls, you may draw two cards.",
            )
        )
        event = ability.event
        assert isinstance(event, TargetingEvent)
        assert isinstance(event.filter, FAtom)
        self.assertIs(event.filter.pred, FAtomPred.IS_SOURCE)
        self.assertIsNone(ability.condition)

    def test_jeskai_elder_is_combat_damage_event(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature deals combat damage to a player, "
                "you may draw a card.",
            )
        )
        event = ability.event
        # R2 fold (/140): CombatDamageEvent folded into DamageDealtEvent —
        # amount unbounded, the old filter moved verbatim to source,
        # combat=True (the COMBAT_DAMAGE feed is now the is_combat=True
        # DAMAGE journal rows).
        assert isinstance(event, DamageDealtEvent)
        self.assertEqual(event.amount, QUnbounded())
        self.assertIs(event.combat, True)
        # re-pinned 2026-10-29: B-57 fix changes the recipient from the
        # universal FAnd(()) to "a player" (not a permanent, CR 120.1).
        self.assertEqual(event.filter, FNot(FAtom(pred=FAtomPred.IS_PERMANENT)))
        assert isinstance(event.source, FAtom)
        self.assertIs(event.source.pred, FAtomPred.IS_SOURCE)
        self.assertIsNone(ability.condition)

    def test_incinerator_is_noncombat_damage_event(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever a source you control deals noncombat damage to an "
                "opponent, this creature deals that much damage to target "
                "creature or planeswalker that player controls.",
            )
        )
        event = ability.event
        assert isinstance(event, DamageDealtEvent)
        self.assertEqual(event.amount, QUnbounded())
        self.assertIs(event.combat, False)
        assert isinstance(event.source, FAtom)
        self.assertIs(event.source.pred, FAtomPred.CONTROLLER_IS)
        self.assertIs(event.source.who, ControllerRef.YOU)
        # R11-1 destination predicate: "to an opponent" is the DamageDealt
        # FILTER over the damage subject — FAtom(OPPONENT_OF, who=YOU),
        # player-total (a card subject never passes). Replaces the vacuous
        # FAnd(()) that let the trigger fire on damage to anything.
        assert isinstance(event.filter, FAtom)
        self.assertIs(event.filter.pred, FAtomPred.OPPONENT_OF)
        self.assertIs(event.filter.who, ControllerRef.YOU)
        self.assertIsNone(ability.condition)

    def test_pyreling_is_noncombat_damage_event(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever a source you control deals noncombat damage to an "
                "opponent, this creature gets +1/+0 and gains double "
                "strike until end of turn.",
            )
        )
        event = ability.event
        assert isinstance(event, DamageDealtEvent)
        self.assertIs(event.combat, False)
        assert isinstance(event.source, FAtom)
        self.assertIs(event.source.who, ControllerRef.YOU)
        # R11-1 destination predicate, pinned in both template shapes
        # (the +1/+0 and the burn-to-target emissions share it).
        assert isinstance(event.filter, FAtom)
        self.assertIs(event.filter.pred, FAtomPred.OPPONENT_OF)
        self.assertIs(event.filter.who, ControllerRef.YOU)

    def test_pack_leader_is_declare_attackers(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature attacks, prevent all combat damage "
                "that would be dealt this turn to Dogs you control.",
            )
        )
        event = ability.event
        assert isinstance(event, DeclareAttackersEvent)
        assert isinstance(event.filter, FAtom)
        self.assertIs(event.filter.pred, FAtomPred.IS_SOURCE)
        self.assertIsNone(ability.condition)

    def test_gloom_sower_is_becomes_blocked(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature becomes blocked by a creature, that "
                "creature's controller loses 2 life and you gain 2 life.",
            )
        )
        event = ability.event
        assert isinstance(event, BecomesBlockedEvent)
        assert isinstance(event.filter, FAtom)
        self.assertIs(event.filter.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(event.filter.string_value, "Creature")

    def test_hooded_blightfang_pw_is_damage_event(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever a creature you control with deathtouch deals "
                "damage to a planeswalker, destroy that planeswalker.",
            )
        )
        event = ability.event
        assert isinstance(event, DamageDealtEvent)
        self.assertEqual(event.amount, QUnbounded())
        assert isinstance(event.source, FAnd)
        self._assert_has_type_eq_creature(event.source)
        self._assert_has_controller_you(event.source)
        self._assert_has_keyword_deathtouch(event.source)
        recipient = event.filter
        assert isinstance(recipient, FAtom)
        self.assertIs(recipient.pred, FAtomPred.SUPERTYPE_EQ)
        self.assertEqual(recipient.string_value, "Planeswalker")

    def test_feline_sovereign_is_combat_damage_cats(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever one or more Cats you control deal combat damage "
                "to a player, destroy up to one target artifact or "
                "enchantment that player controls.",
            )
        )
        event = ability.event
        # R2 fold (/140): the cats filter moved VERBATIM from the old
        # CombatDamageEvent filter slot to DamageDealtEvent.source; amount
        # unbounded, combat=True.
        assert isinstance(event, DamageDealtEvent)
        self.assertEqual(event.amount, QUnbounded())
        self.assertIs(event.combat, True)
        # re-pinned 2026-10-29: B-57 fix changes the recipient from the
        # universal FAnd(()) to "a player" (not a permanent, CR 120.1).
        self.assertEqual(event.filter, FNot(FAtom(pred=FAtomPred.IS_PERMANENT)))
        assert isinstance(event.source, FAnd)
        self._assert_has_type_eq_creature(event.source)
        self._assert_has_controller_you(event.source)
        self._assert_has_subtype_cat(event.source)

    def test_ghostly_pilferer_cast_is_from_zone_not(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever an opponent casts a spell from anywhere other "
                "than their hand, draw a card.",
            )
        )
        event = ability.event
        assert isinstance(event, CastSpellEvent)
        self.assertIs(event.actor.who, ControllerRef.OPPONENT)
        self.assertIsNone(event.from_zone)
        self.assertEqual(
            event.from_zone_not, Zone(ZoneKind.HAND, ControllerRef.OPPONENT)
        )

    def test_double_vision_copy_is_ordinal_cast(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you cast your first instant or sorcery spell "
                "each turn, copy that spell.",
            )
        )
        event = ability.event
        assert isinstance(event, CastSpellEvent)
        self.assertIs(event.actor.who, ControllerRef.YOU)
        self.assertEqual(event.ordinal, 1)
        assert isinstance(event.filter, FOr)
        self.assertEqual(len(event.filter.children), 2)

    def test_garruks_harbinger_is_combat_damage_event(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature deals combat damage to a player or "
                "planeswalker, look at that many cards from the top of your "
                "library.",
            )
        )
        event = ability.event
        assert isinstance(event, DamageDealtEvent)
        self.assertEqual(event.amount, QUnbounded())
        self.assertIs(event.combat, True)
        # B-57: "to a player or planeswalker" is the recipient (it was the
        # universal FAnd(()), which fired on damage to a blocker).
        self.assertEqual(
            event.filter,
            FOr(
                (
                    FNot(FAtom(pred=FAtomPred.IS_PERMANENT)),
                    FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
                )
            ),
        )
        assert isinstance(event.source, FAtom)
        self.assertIs(event.source.pred, FAtomPred.IS_SOURCE)

    def test_jolrael_is_second_draw_event(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you draw your second card each turn, create a "
                "2/2 green Cat creature token.",
            )
        )
        event = ability.event
        assert isinstance(event, CardDrawnEvent)
        self.assertIs(event.actor.who, ControllerRef.YOU)
        self.assertEqual(event.ordinal, 2)

    def test_mystic_skyfish_is_second_draw_event(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you draw your second card each turn, this "
                "creature gains flying until end of turn.",
            )
        )
        event = ability.event
        assert isinstance(event, CardDrawnEvent)
        self.assertIs(event.actor.who, ControllerRef.YOU)
        self.assertEqual(event.ordinal, 2)

    def test_keral_keep_is_loyalty_activation_event(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you activate a loyalty ability of a Chandra "
                "planeswalker, this creature deals 1 damage to each "
                "opponent.",
            )
        )
        event = ability.event
        assert isinstance(event, LoyaltyActivatedEvent)
        self.assertIs(event.actor.who, ControllerRef.YOU)
        assert isinstance(event.filter, FAnd)
        subtype = _find_atom(event.filter, FAtomPred.SUBTYPE_EQ)
        self.assertEqual(subtype.string_value, "Chandra")
        type_atom = _find_atom(event.filter, FAtomPred.TYPE_EQ)
        self.assertEqual(type_atom.string_value, "Planeswalker")

    # --- small filter assertion helpers ---

    def _assert_has_type_eq_creature(self, a_filter: Filter) -> None:
        atom = _find_atom(a_filter, FAtomPred.TYPE_EQ)
        self.assertEqual(atom.string_value, "Creature")

    def _assert_has_controller_you(self, a_filter: Filter) -> None:
        atom = _find_atom(a_filter, FAtomPred.CONTROLLER_IS)
        self.assertIs(atom.who, ControllerRef.YOU)

    def _assert_has_controller_opponent(self, a_filter: Filter) -> None:
        atom = _find_atom(a_filter, FAtomPred.CONTROLLER_IS)
        self.assertIs(atom.who, ControllerRef.OPPONENT)

    def _assert_has_keyword_deathtouch(self, a_filter: Filter) -> None:
        atom = _find_atom(a_filter, FAtomPred.KEYWORD_HAS)
        self.assertIs(atom.keyword, Keyword.DEATHTOUCH)

    def _assert_has_keyword_flying(self, a_filter: Filter) -> None:
        atom = _find_atom(a_filter, FAtomPred.KEYWORD_HAS)
        self.assertIs(atom.keyword, Keyword.FLYING)

    def _assert_has_subtype_rogue(self, a_filter: Filter) -> None:
        atom = _find_atom(a_filter, FAtomPred.SUBTYPE_EQ)
        self.assertEqual(atom.string_value, "Rogue")

    def _assert_has_subtype_cat(self, a_filter: Filter) -> None:
        atom = _find_atom(a_filter, FAtomPred.SUBTYPE_EQ)
        self.assertEqual(atom.string_value, "Cat")

    def _assert_has_subtype_dog(self, a_filter: Filter) -> None:
        atom = _find_atom(a_filter, FAtomPred.SUBTYPE_EQ)
        self.assertEqual(atom.string_value, "Dog")


# ---------------------------------------------------------------------------
# Effect structure
# ---------------------------------------------------------------------------


class TestB2bEffectStructure(unittest.TestCase):
    def setUp(self) -> None:
        self.reg = _registry()

    def test_alpine_houndmaster_etb_optional_search_reveal_shuffle(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "When this creature enters, you may search your library "
                "for a card named Alpine Watchdog and/or a card named Igneous Cur, "
                "reveal them, put them into your hand, then shuffle.",
            )
        )
        option = _optional(ability)
        seq = _seq_inner(option)
        # re-pinned 2026-10-29: m21-fidelity, "a card named A and/or a card named B" is at most
        # one card of EACH name: one up-to-one pick per name (it was one up-to-two pick over
        # FOr(A, B), which could fetch two Alpine Watchdogs).
        self.assertEqual(len(seq.steps), 4)
        # SEARCH x2, in printed order
        for idx, name in ((0, "Alpine Watchdog"), (1, "Igneous Cur")):
            search = _atom_step(seq, idx)
            self.assertIs(search.verb, Verb.SEARCH)
            sel = _selector(search, "cards")
            assert isinstance(sel.count, QConst)
            self.assertEqual(sel.count.value, 1)
            self.assertIs(sel.mode, SelectorMode.CHOOSE)
            assert isinstance(sel.filter, FAtom)
            self.assertEqual(sel.filter.string_value, name)
        # REVEAL
        reveal = _atom_step(seq, 2)
        self.assertIs(reveal.verb, Verb.REVEAL)
        self.assertIs(reveal.args.get("controller"), ControllerRef.YOU)
        assert isinstance(reveal.args.get("count"), QUnbounded)
        # SHUFFLE
        shuffle = _atom_step(seq, 3)
        self.assertIs(shuffle.verb, Verb.SHUFFLE)
        zone = shuffle.args.get("zone")
        assert isinstance(zone, Zone)
        self.assertIs(zone.kind, ZoneKind.LIBRARY)

    def test_fierce_empath_etb_optional_search_cmc_ge(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "When this creature enters, you may search your library "
                "for a creature card with mana value 6 or greater, "
                "reveal it, put it into your hand, then shuffle.",
            )
        )
        option = _optional(ability)
        seq = _seq_inner(option)
        search = _atom_step(seq, 0)
        self.assertIs(search.verb, Verb.SEARCH)
        sel = _selector(search, "cards")
        assert isinstance(sel.filter, FAnd)
        cmc_atom = _find_atom(sel.filter, FAtomPred.CMC_GE)
        assert isinstance(cmc_atom.count, QConst)
        self.assertEqual(cmc_atom.count.value, 6)

    def test_teferis_tutelage_etb_draw_then_discard(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "When this enchantment enters, draw a card, then discard a card.",
            )
        )
        seq = _seq(ability)
        self.assertEqual(len(seq.steps), 2)
        draw = _atom_step(seq, 0)
        self.assertIs(draw.verb, Verb.DRAW)
        self.assertIs(draw.args.get("controller"), ControllerRef.YOU)
        amount = _qconst(draw, "amount")
        self.assertEqual(amount.value, 1)
        discard = _atom_step(seq, 1)
        # T4 P1a: the discard shape is the merged MOVE_ZONE atom.
        self.assertIs(discard.verb, Verb.MOVE_ZONE)
        self.assertIs(discard.args.get("controller"), ControllerRef.YOU)
        self.assertEqual(
            discard.args.get("destination"),
            Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
        )
        self.assertEqual(
            discard.args.get("from"), Zone(ZoneKind.HAND, ControllerRef.YOU)
        )

    def test_temple_scry_etb(self) -> None:
        ability = _ability(_single_match(self.reg, "When this land enters, scry 1."))
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.SCRY)
        self.assertIs(atom.args.get("controller"), ControllerRef.YOU)
        count = _qconst(atom, "count")
        self.assertEqual(count.value, 1)

    def test_temple_gain_life_etb(self) -> None:
        ability = _ability(
            _single_match(self.reg, "When this land enters, you gain 1 life.")
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.GAIN_LIFE)
        self.assertIs(atom.args.get("controller"), ControllerRef.YOU)
        amount = _qconst(atom, "amount")
        self.assertEqual(amount.value, 1)

    def test_massacre_wurm_lose_life(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever a creature an opponent controls dies, "
                "that player loses 2 life.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.LOSE_LIFE)
        self.assertIs(atom.args.get("controller"), ControllerRef.TARGET_PLAYER)
        amount = _qconst(atom, "amount")
        self.assertEqual(amount.value, 2)

    def test_hooded_blightfang_lose_and_gain_life_seq(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever a creature you control with deathtouch attacks, "
                "each opponent loses 1 life and you gain 1 life.",
            )
        )
        seq = _seq(ability)
        self.assertEqual(len(seq.steps), 2)
        lose = _atom_step(seq, 0)
        self.assertIs(lose.verb, Verb.LOSE_LIFE)
        self.assertIs(lose.args.get("controller"), ControllerRef.ALL_OPPONENTS)
        lose_amount = _qconst(lose, "amount")
        self.assertEqual(lose_amount.value, 1)
        gain = _atom_step(seq, 1)
        self.assertIs(gain.verb, Verb.GAIN_LIFE)
        self.assertIs(gain.args.get("controller"), ControllerRef.YOU)
        gain_amount = _qconst(gain, "amount")
        self.assertEqual(gain_amount.value, 1)

    def test_malefic_scythe_put_soul_counter(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever equipped creature dies, "
                "put a soul counter on this Equipment.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.PUT_COUNTER)
        self.assertIs(atom.args.get("counter_kind"), CounterKind.SOUL)
        count = _qconst(atom, "count")
        self.assertEqual(count.value, 1)
        target = _selector(atom, "target")
        assert isinstance(target.filter, FAtom)
        self.assertIs(target.filter.pred, FAtomPred.IS_SOURCE)

    def test_wildwood_scorge_put_plus1_counter(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever one or more +1/+1 counters are put on another "
                "non-Hydra creature you control, "
                "put a +1/+1 counter on this creature.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.PUT_COUNTER)
        self.assertIs(atom.args.get("counter_kind"), CounterKind.PLUS_1_PLUS_1)
        count = _qconst(atom, "count")
        self.assertEqual(count.value, 1)
        target = _selector(atom, "target")
        assert isinstance(target.filter, FAtom)
        self.assertIs(target.filter.pred, FAtomPred.IS_SOURCE)

    def test_falconer_adept_create_bird_token(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature attacks, create a 1/1 white Bird "
                "creature token with flying that's tapped and attacking.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.CREATE_TOKEN)
        token = _token(atom, "tokens")
        self.assertEqual(token.name, "Bird")
        self.assertIn("Bird", token.subtypes)
        assert isinstance(token.power, QConst)
        self.assertEqual(token.power.value, 1)
        assert isinstance(token.toughness, QConst)
        self.assertEqual(token.toughness.value, 1)
        self.assertIn(Keyword.FLYING, token.keywords)
        count = _qconst(atom, "count")
        self.assertEqual(count.value, 1)

    def test_library_larcenist_draw(self) -> None:
        ability = _ability(
            _single_match(self.reg, "Whenever this creature attacks, draw a card.")
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.DRAW)
        self.assertIs(atom.args.get("controller"), ControllerRef.YOU)
        amount = _qconst(atom, "amount")
        self.assertEqual(amount.value, 1)

    def test_alpine_houndmaster_attack_modify_pt_qcount(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature attacks, it gets +X/+0 until end of turn, "
                "where X is the number of other attacking creatures.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        target = _selector(atom, "target")
        assert isinstance(target.filter, FAtom)
        self.assertIs(target.filter.pred, FAtomPred.IS_SOURCE)
        power = _pt_delta(atom, "power")
        self.assertIs(power.direction, PtDirection.INCREASE)
        power_magnitude = power.magnitude
        assert isinstance(power_magnitude, QCount)
        # QCount selector should have IS_ATTACKING and FNot(IS_SOURCE)
        qc_sel = power_magnitude.selector
        assert isinstance(qc_sel.filter, FAnd)
        self._assert_has_type_eq_creature(qc_sel.filter)
        self._assert_has_is_attacking(qc_sel.filter)
        self.assertTrue(_contains_not(qc_sel.filter, FAtomPred.IS_SOURCE))
        toughness = _pt_delta(atom, "toughness")
        self.assertIs(toughness.direction, PtDirection.INCREASE)
        toughness_magnitude = toughness.magnitude
        assert isinstance(toughness_magnitude, QConst)
        self.assertEqual(toughness_magnitude.value, 0)
        self.assertEqual(atom.args.get("duration"), DurationEot())

    def test_bolt_hound_modify_pt_other_creatures(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature attacks, other creatures you control "
                "get +1/+0 until end of turn.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        target = _selector(atom, "target")
        assert isinstance(target.filter, FAnd)
        self._assert_has_type_eq_creature(target.filter)
        self._assert_has_controller_you(target.filter)
        self.assertTrue(_contains_not(target.filter, FAtomPred.IS_SOURCE))
        power = _pt_delta(atom, "power")
        self.assertIs(power.direction, PtDirection.INCREASE)
        power_magnitude = power.magnitude
        assert isinstance(power_magnitude, QConst)
        self.assertEqual(power_magnitude.value, 1)
        toughness = _pt_delta(atom, "toughness")
        self.assertIs(toughness.direction, PtDirection.INCREASE)
        toughness_magnitude = toughness.magnitude
        assert isinstance(toughness_magnitude, QConst)
        self.assertEqual(toughness_magnitude.value, 0)

    def test_spined_megalodon_scry(self) -> None:
        ability = _ability(
            _single_match(self.reg, "Whenever this creature attacks, scry 1.")
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.SCRY)
        self.assertIs(atom.args.get("controller"), ControllerRef.YOU)
        count = _qconst(atom, "count")
        self.assertEqual(count.value, 1)

    def test_siege_striker_optional_tap(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature attacks, you may tap any number "
                "of untapped creatures you control.",
            )
        )
        option = _optional(ability)
        atom = _atom_inner(option)
        self.assertIs(atom.verb, Verb.TAP)
        target = _selector(atom, "target")
        assert isinstance(target.filter, FAnd)
        self._assert_has_type_eq_creature(target.filter)
        self._assert_has_controller_you(target.filter)
        self._assert_has_is_untapped(target.filter)
        self.assertIs(target.mode, SelectorMode.CHOOSE)

    def test_brash_taunter_deal_damage_qprop(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature is dealt damage, "
                "it deals that much damage to target opponent.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.DEAL_DAMAGE)
        target = _selector(atom, "target")
        self.assertIs(target.mode, SelectorMode.TARGET)
        assert isinstance(target.zones[0].kind, ZoneKind)
        amount = _qprop(atom, "amount")
        self.assertEqual(amount.referent, "event")
        self.assertIs(amount.field, QPropField.AMOUNT)
        self.assertIs(amount.agg, QAgg.FIRST)

    def test_sporeweb_weaver_gain_life_and_create_token(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature is dealt damage, you gain 1 life "
                "and create a 1/1 green Saproling creature token.",
            )
        )
        seq = _seq(ability)
        self.assertEqual(len(seq.steps), 2)
        gain = _atom_step(seq, 0)
        self.assertIs(gain.verb, Verb.GAIN_LIFE)
        self.assertIs(gain.args.get("controller"), ControllerRef.YOU)
        gain_amount = _qconst(gain, "amount")
        self.assertEqual(gain_amount.value, 1)
        create = _atom_step(seq, 1)
        self.assertIs(create.verb, Verb.CREATE_TOKEN)
        token = _token(create, "tokens")
        self.assertEqual(token.name, "Saproling")
        self.assertIn("Saproling", token.subtypes)
        assert isinstance(token.power, QConst)
        self.assertEqual(token.power.value, 1)
        assert isinstance(token.toughness, QConst)
        self.assertEqual(token.toughness.value, 1)
        create_count = _qconst(create, "count")
        self.assertEqual(create_count.value, 1)

    def test_basris_lieutenant_create_knight_token(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature or another creature you control dies, "
                "if it had a +1/+1 counter on it, "
                "create a 2/2 white Knight creature token with vigilance.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.CREATE_TOKEN)
        token = _token(atom, "tokens")
        self.assertEqual(token.name, "Knight")
        self.assertIn("Knight", token.subtypes)
        assert isinstance(token.power, QConst)
        self.assertEqual(token.power.value, 2)
        assert isinstance(token.toughness, QConst)
        self.assertEqual(token.toughness.value, 2)
        self.assertIn(Keyword.VIGILANCE, token.keywords)
        count = _qconst(atom, "count")
        self.assertEqual(count.value, 1)

    # --- round-2 template effects ---

    def test_named_card_search_optional_search_reveal_move(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "When this creature enters, you may search your library "
                "and/or graveyard for a card named Chandra, Flame's Catalyst, "
                "reveal it, and put it into your hand.",
            )
        )
        option = _optional(ability)
        seq = _seq_inner(option)
        self.assertEqual(len(seq.steps), 3)
        # SEARCH
        search = _atom_step(seq, 0)
        self.assertIs(search.verb, Verb.SEARCH)
        sel = _selector(search, "cards")
        assert isinstance(sel.count, QConst)
        self.assertEqual(sel.count.value, 1)
        self.assertIs(sel.mode, SelectorMode.CHOOSE)
        assert isinstance(sel.filter, FAtom)
        self.assertIs(sel.filter.pred, FAtomPred.NAME_EQ)
        self.assertEqual(sel.filter.string_value, "Chandra, Flame's Catalyst")
        # R0 zone-fold: ONE set; canonical order GRAVEYARD < LIBRARY.
        self.assertEqual(
            sel.zones,
            (
                Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
                Zone(ZoneKind.LIBRARY, ControllerRef.YOU),
            ),
        )
        self.assertEqual(
            search.args.get("destination"),
            Zone(ZoneKind.HAND, ControllerRef.YOU),
        )
        # REVEAL
        reveal = _atom_step(seq, 1)
        self.assertIs(reveal.verb, Verb.REVEAL)
        self.assertIs(reveal.args.get("controller"), ControllerRef.YOU)
        reveal_count = _qconst(reveal, "count")
        self.assertEqual(reveal_count.value, 1)
        # MOVE_ZONE
        move = _atom_step(seq, 2)
        self.assertIs(move.verb, Verb.MOVE_ZONE)
        move_sel = _selector(move, "cards")
        assert isinstance(move_sel.filter, FAtom)
        self.assertIs(move_sel.filter.pred, FAtomPred.IS_SOURCE)
        self.assertEqual(
            move_sel.zones[0],
            Zone(ZoneKind.LIBRARY, ControllerRef.YOU, position=ZonePosition.TOP),
        )
        self.assertEqual(
            move.args.get("destination"),
            Zone(ZoneKind.HAND, ControllerRef.YOU),
        )

    def test_nine_lives_lose_game(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "When this enchantment leaves the battlefield, you lose the game.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.LOSE_GAME)

    def test_power_ge_enters_draw(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever a creature you control with power 4 or greater enters, "
                "draw a card.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.DRAW)
        self.assertIs(atom.args.get("controller"), ControllerRef.YOU)
        amount = _qconst(atom, "amount")
        self.assertEqual(amount.value, 1)

    def test_mangara_second_spell_draw(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever an opponent casts their second spell each turn, draw a card.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.DRAW)
        self.assertIs(atom.args.get("controller"), ControllerRef.YOU)
        amount = _qconst(atom, "amount")
        self.assertEqual(amount.value, 1)

    def test_terror_of_peaks_deal_damage_qprop_power(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever another creature you control enters, this creature "
                "deals damage equal to that creature's power to any target.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.DEAL_DAMAGE)
        target = _selector(atom, "target")
        self.assertIs(target.mode, SelectorMode.TARGET)
        # AMENDED r17-2 (geyser-FIX): printed "any target" is the
        # battlefield FOr(Creature, Planeswalker) idiom, not the empty
        # FAnd over Zone(ANY, ANY) — the old shape enumerated opponent-
        # hidden zones (D10/E3 leak). Player side joins via the engine's
        # idiom widening (CR 109.5).
        idiom = target.filter
        assert isinstance(idiom, FOr)
        self.assertEqual(len(idiom.children), 3)
        self.assertEqual(target.zones[0], Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY))
        amount = _qprop(atom, "amount")
        self.assertEqual(amount.referent, "event")
        self.assertIs(amount.field, QPropField.POWER)
        self.assertIs(amount.agg, QAgg.FIRST)

    def test_watcher_spheres_modify_pt_eot(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever another creature you control with flying enters, "
                "this creature gets +1/+1 until end of turn.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        target = _selector(atom, "target")
        assert isinstance(target.filter, FAtom)
        self.assertIs(target.filter.pred, FAtomPred.IS_SOURCE)
        power = _pt_delta(atom, "power")
        self.assertIs(power.direction, PtDirection.INCREASE)
        assert isinstance(power.magnitude, QConst)
        self.assertEqual(power.magnitude.value, 1)
        toughness = _pt_delta(atom, "toughness")
        self.assertIs(toughness.direction, PtDirection.INCREASE)
        assert isinstance(toughness.magnitude, QConst)
        self.assertEqual(toughness.magnitude.value, 1)
        self.assertIsInstance(atom.args.get("duration"), DurationEot)

    def test_ghostly_pilferer_optional_pay(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature becomes untapped, you may pay {2}.",
            )
        )
        atom = _atom_inner(_optional(ability))
        self.assertIs(atom.verb, Verb.PAY)
        cost = atom.args.get("cost")
        assert isinstance(cost, Cost)
        self.assertEqual(len(cost.parts), 1)
        part = cost.parts[0]
        assert isinstance(part, CostManaGeneric)
        assert isinstance(part.amount, QConst)
        self.assertEqual(part.amount.value, 2)

    def test_thieves_guild_each_opponent_mill(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature or another Rogue you control enters, "
                "each opponent mills two cards.",
            )
        )
        each = ability.effect
        assert isinstance(each, EachPlayer)
        self.assertIs(each.ref, ControllerRef.ALL_OPPONENTS)
        effect = each.effect
        assert isinstance(effect, Atom)
        # T4 P1a: the mill shape is the merged MOVE_ZONE atom.
        self.assertIs(effect.verb, Verb.MOVE_ZONE)
        self.assertIs(effect.args.get("controller"), ControllerRef.YOU)
        self.assertEqual(
            effect.args.get("destination"),
            Zone(ZoneKind.GRAVEYARD, ControllerRef.YOU),
        )
        self.assertEqual(
            effect.args.get("from"), Zone(ZoneKind.LIBRARY, ControllerRef.YOU)
        )
        self.assertEqual(effect.args.get("journal_kind"), "MILL")
        amount = _qconst(effect, "amount")
        self.assertEqual(amount.value, 2)

    def test_cast_cat_create_dog_token(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you cast a Cat spell, create a 1/1 white Dog creature token.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.CREATE_TOKEN)
        token = _token(atom, "tokens")
        self.assertEqual(token.name, "Dog")
        self.assertEqual(token.type_line, "Creature — Dog")
        self.assertEqual(token.types, ("Creature",))
        self.assertEqual(token.subtypes, ("Dog",))
        assert isinstance(token.power, QConst)
        self.assertEqual(token.power.value, 1)
        assert isinstance(token.toughness, QConst)
        self.assertEqual(token.toughness.value, 1)
        count = _qconst(atom, "count")
        self.assertEqual(count.value, 1)

    def test_cast_dog_create_cat_token(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you cast a Dog spell, create a 1/1 green Cat creature token.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.CREATE_TOKEN)
        token = _token(atom, "tokens")
        self.assertEqual(token.name, "Cat")
        self.assertEqual(token.type_line, "Creature — Cat")
        self.assertEqual(token.subtypes, ("Cat",))
        count = _qconst(atom, "count")
        self.assertEqual(count.value, 1)

    def test_spellgorger_put_plus1_counter(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you cast a noncreature spell, put a +1/+1 counter "
                "on this creature.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.PUT_COUNTER)
        target = _selector(atom, "target")
        assert isinstance(target.filter, FAtom)
        self.assertIs(target.filter.pred, FAtomPred.IS_SOURCE)
        self.assertIs(atom.args.get("counter_kind"), CounterKind.PLUS_1_PLUS_1)
        count = _qconst(atom, "count")
        self.assertEqual(count.value, 1)

    def test_riddleform_optional_grant_seq(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you cast a noncreature spell, you may have this "
                "enchantment become a 3/3 Sphinx creature with flying in "
                "addition to its other types until end of turn.",
            )
        )
        seq = _seq_inner(_optional(ability))
        self.assertEqual(len(seq.steps), 3)
        set_pt = _atom_step(seq, 0)
        self.assertIs(set_pt.verb, Verb.SET_PT)
        power = _qconst(set_pt, "power")
        self.assertEqual(power.value, 3)
        toughness = _qconst(set_pt, "toughness")
        self.assertEqual(toughness.value, 3)
        self.assertIsInstance(set_pt.args.get("duration"), DurationEot)
        grant_type = _atom_step(seq, 1)
        self.assertIs(grant_type.verb, Verb.GRANT_TYPE)
        # re-pinned 2026-10-29: m21-fidelity (review batch C) grants the card type Creature too
        # ("a 3/3 Sphinx creature"); ("Sphinx",) alone left it unable to attack or block.
        self.assertEqual(grant_type.args.get("types"), ("Creature", "Sphinx"))
        self.assertIsInstance(grant_type.args.get("duration"), DurationEot)
        grant_ability = _atom_step(seq, 2)
        self.assertIs(grant_ability.verb, Verb.GRANT_ABILITY)
        granted = grant_ability.args.get("ability")
        assert isinstance(granted, KeywordAbility)
        self.assertIs(granted.keyword, Keyword.FLYING)
        self.assertIsInstance(grant_ability.args.get("duration"), DurationEot)

    def test_quirion_dryad_put_plus1_counter(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you cast a spell that's white, blue, black, or red, "
                "put a +1/+1 counter on this creature.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.PUT_COUNTER)
        self.assertIs(atom.args.get("counter_kind"), CounterKind.PLUS_1_PLUS_1)
        count = _qconst(atom, "count")
        self.assertEqual(count.value, 1)

    def test_lorescale_put_plus1_counter(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you draw a card, put a +1/+1 counter on this creature.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.PUT_COUNTER)
        self.assertIs(atom.args.get("counter_kind"), CounterKind.PLUS_1_PLUS_1)
        count = _qconst(atom, "count")
        self.assertEqual(count.value, 1)

    def test_teferis_tutelage_mill_target(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you draw a card, target opponent mills two cards.",
            )
        )
        atom = _atom(ability)
        # T4 P1a: the mill shape is the merged MOVE_ZONE atom — the milled
        # player's own library and graveyard carry TARGET_PLAYER.
        self.assertIs(atom.verb, Verb.MOVE_ZONE)
        self.assertIs(atom.args.get("controller"), ControllerRef.TARGET_PLAYER)
        self.assertEqual(
            atom.args.get("destination"),
            Zone(ZoneKind.GRAVEYARD, ControllerRef.TARGET_PLAYER),
        )
        self.assertEqual(
            atom.args.get("from"), Zone(ZoneKind.LIBRARY, ControllerRef.TARGET_PLAYER)
        )
        self.assertEqual(atom.args.get("journal_kind"), "MILL")
        amount = _qconst(atom, "amount")
        self.assertEqual(amount.value, 2)

    def test_burlfist_modify_pt_eot(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you draw a card, this creature gets +2/+2 until end of turn.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        power = _pt_delta(atom, "power")
        assert isinstance(power.magnitude, QConst)
        self.assertEqual(power.magnitude.value, 2)
        toughness = _pt_delta(atom, "toughness")
        assert isinstance(toughness.magnitude, QConst)
        self.assertEqual(toughness.magnitude.value, 2)
        self.assertIsInstance(atom.args.get("duration"), DurationEot)

    def test_tolarian_kraken_optional_pay(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you draw a card, you may pay {1}.",
            )
        )
        atom = _atom_inner(_optional(ability))
        self.assertIs(atom.verb, Verb.PAY)
        cost = atom.args.get("cost")
        assert isinstance(cost, Cost)
        part = cost.parts[0]
        assert isinstance(part, CostManaGeneric)
        assert isinstance(part.amount, QConst)
        self.assertEqual(part.amount.value, 1)

    def test_havoc_jester_deal_damage_qconst(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you sacrifice a permanent, this creature deals 1 "
                "damage to any target.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.DEAL_DAMAGE)
        target = _selector(atom, "target")
        self.assertIs(target.mode, SelectorMode.TARGET)
        amount = _qconst(atom, "amount")
        self.assertEqual(amount.value, 1)

    def test_solemn_simulacrum_optional_search_shuffle(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "When this creature enters, you may search your library "
                "for a basic land card, put that card onto the battlefield "
                "tapped, then shuffle.",
            )
        )
        inner = _seq_inner(_optional(ability))
        self.assertEqual(len(inner.steps), 2)
        search = _atom_step(inner, 0)
        self.assertIs(search.verb, Verb.SEARCH)
        cards = _selector(search, "cards")
        self.assertEqual(cards.count, QConst(1))
        self.assertIs(cards.mode, SelectorMode.CHOOSE)
        assert isinstance(cards.filter, FAnd)
        basic = _find_atom(cards.filter, FAtomPred.SUPERTYPE_EQ)
        self.assertEqual(basic.string_value, "Basic")
        land = _find_atom(cards.filter, FAtomPred.TYPE_EQ)
        self.assertEqual(land.string_value, "Land")
        self.assertEqual(cards.zones[0], Zone(ZoneKind.LIBRARY, ControllerRef.YOU))
        dest = search.args.get("destination")
        self.assertEqual(dest, Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU))
        self.assertIs(search.args.get("tapped_on_enter"), True)
        shuffle = _atom_step(inner, 1)
        self.assertIs(shuffle.verb, Verb.SHUFFLE)
        zone = shuffle.args.get("zone")
        self.assertEqual(zone, Zone(ZoneKind.LIBRARY, ControllerRef.YOU))

    def test_garruks_uprising_draw_qconst(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "When this enchantment enters, if you control a creature "
                "with power 4 or greater, draw a card.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.DRAW)
        self.assertIs(atom.args.get("controller"), ControllerRef.YOU)
        amount = _qconst(atom, "amount")
        self.assertEqual(amount.value, 1)

    def test_historian_draw_qconst(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature attacks, if you control a Teferi "
                "planeswalker, draw a card.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.DRAW)
        self.assertIs(atom.args.get("controller"), ControllerRef.YOU)
        amount = _qconst(atom, "amount")
        self.assertEqual(amount.value, 1)

    def test_ornery_modify_pt_eot(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature attacks, if you control a creature "
                "with power 4 or greater, this creature gets +2/+2 until "
                "end of turn.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        target = _selector(atom, "target")
        self.assertIs(target.mode, SelectorMode.CHOOSE)
        assert isinstance(target.filter, FAtom)
        self.assertIs(target.filter.pred, FAtomPred.IS_SOURCE)
        power = _pt_delta(atom, "power")
        self.assertIs(power.direction, PtDirection.INCREASE)
        assert isinstance(power.magnitude, QConst)
        self.assertEqual(power.magnitude.value, 2)
        toughness = _pt_delta(atom, "toughness")
        self.assertIs(toughness.direction, PtDirection.INCREASE)
        assert isinstance(toughness.magnitude, QConst)
        self.assertEqual(toughness.magnitude.value, 2)
        self.assertIsInstance(atom.args.get("duration"), DurationEot)

    def test_tide_skimmer_draw_qconst(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you attack with two or more creatures with flying, "
                "draw a card.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.DRAW)
        self.assertIs(atom.args.get("controller"), ControllerRef.YOU)
        amount = _qconst(atom, "amount")
        self.assertEqual(amount.value, 1)

    def test_vito_lose_life_qprop(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you gain life, target opponent loses that much life.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.LOSE_LIFE)
        self.assertIs(atom.args.get("controller"), ControllerRef.TARGET_PLAYER)
        amount = _qprop(atom, "amount")
        self.assertEqual(amount.referent, "event")
        self.assertIs(amount.field, QPropField.AMOUNT)
        self.assertIs(amount.agg, QAgg.FIRST)

    # --- Round 5 (grammar round 4/5 shapes) ---

    def _referent_selector(self, atom: Atom, role: str) -> Selector:
        selector = _selector(atom, role)
        self.assertEqual(selector.referent, "event")
        self.assertEqual(selector.count, QConst(1))
        self.assertIs(selector.mode, SelectorMode.CHOOSE)
        self.assertEqual(selector.zones[0], Zone(ZoneKind.ANY, ControllerRef.ANY))
        assert isinstance(selector.filter, FAnd)
        self.assertEqual(len(selector.filter.children), 0)
        return selector

    def test_warden_of_the_woods_optional_draw_two(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature becomes the target of a spell or "
                "ability an opponent controls, you may draw two cards.",
            )
        )
        option = _optional(ability)
        draw = _atom_inner(option)
        self.assertIs(draw.verb, Verb.DRAW)
        self.assertIs(draw.args.get("controller"), ControllerRef.YOU)
        amount = _qconst(draw, "amount")
        self.assertEqual(amount.value, 2)

    def test_jeskai_elder_optional_draw_one(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature deals combat damage to a player, "
                "you may draw a card.",
            )
        )
        option = _optional(ability)
        draw = _atom_inner(option)
        self.assertIs(draw.verb, Verb.DRAW)
        self.assertIs(draw.args.get("controller"), ControllerRef.YOU)
        amount = _qconst(draw, "amount")
        self.assertEqual(amount.value, 1)

    def test_incinerator_deals_that_much_to_referent_controlled(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever a source you control deals noncombat damage to an "
                "opponent, this creature deals that much damage to target "
                "creature or planeswalker that player controls.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.DEAL_DAMAGE)
        amount = _qprop(atom, "amount")
        self.assertEqual(amount.referent, "event")
        self.assertIs(amount.field, QPropField.AMOUNT)
        target = _selector(atom, "target")
        self.assertIs(target.mode, SelectorMode.TARGET)
        self.assertEqual(target.zones[0], Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY))
        assert isinstance(target.filter, FAnd)
        self.assertEqual(len(target.filter.children), 2)
        controller_atom = _find_atom(target.filter, FAtomPred.CONTROLLER_IS)
        who = controller_atom.who
        assert isinstance(who, Selector)
        self.assertEqual(who.referent, "event")

    def test_pyreling_modify_pt_and_double_strike_seq(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever a source you control deals noncombat damage to an "
                "opponent, this creature gets +3/+1 and gains double "
                "strike until end of turn.",
            )
        )
        seq = _seq(ability)
        self.assertEqual(len(seq.steps), 2)
        modify = _atom_step(seq, 0)
        self.assertIs(modify.verb, Verb.MODIFY_PT)
        power = modify.args.get("power")
        assert isinstance(power, PtDelta)
        self.assertIs(power.direction, PtDirection.INCREASE)
        self.assertEqual(power.magnitude, QConst(3))
        toughness = modify.args.get("toughness")
        assert isinstance(toughness, PtDelta)
        self.assertEqual(toughness.magnitude, QConst(1))
        self.assertIsInstance(modify.args.get("duration"), DurationEot)
        grant = _atom_step(seq, 1)
        self.assertIs(grant.verb, Verb.GRANT_ABILITY)
        keyword = grant.args.get("ability")
        assert isinstance(keyword, KeywordAbility)
        self.assertIs(keyword.keyword, Keyword.DOUBLE_STRIKE)
        self.assertIsInstance(grant.args.get("duration"), DurationEot)

    def test_pack_leader_prevent_combat_damage_eot(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature attacks, prevent all combat damage "
                "that would be dealt this turn to Dogs you control.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.PREVENT_EFFECT)
        condition = atom.args.get("condition")
        assert isinstance(condition, FAnd)
        self._assert_has_subtype_dog_like(condition)
        event = atom.args.get("event")
        assert isinstance(event, DamageDealtEvent)
        self.assertIs(event.combat, True)
        self.assertIsInstance(atom.args.get("duration"), DurationEot)

    def test_gloom_sower_referent_lose_you_gain_seq(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature becomes blocked by a creature, that "
                "creature's controller loses 3 life and you gain 3 life.",
            )
        )
        seq = _seq(ability)
        self.assertEqual(len(seq.steps), 2)
        lose = _atom_step(seq, 0)
        self.assertIs(lose.verb, Verb.LOSE_LIFE)
        self._referent_selector(lose, "controller")
        self.assertEqual(_qconst(lose, "amount").value, 3)
        gain = _atom_step(seq, 1)
        self.assertIs(gain.verb, Verb.GAIN_LIFE)
        self.assertIs(gain.args.get("controller"), ControllerRef.YOU)
        self.assertEqual(_qconst(gain, "amount").value, 3)

    def test_hooded_blightfang_pw_destroy_referent(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever a creature you control with deathtouch deals "
                "damage to a planeswalker, destroy that planeswalker.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.DESTROY)
        self._referent_selector(atom, "target")

    def test_feline_sovereign_destroy_referent_controlled(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever one or more Cats you control deal combat damage "
                "to a player, destroy up to one target artifact or "
                "enchantment that player controls.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.DESTROY)
        target = _selector(atom, "target")
        self.assertIs(target.mode, SelectorMode.TARGET)
        assert isinstance(target.filter, FAnd)
        controller_atom = _find_atom(target.filter, FAtomPred.CONTROLLER_IS)
        who = controller_atom.who
        assert isinstance(who, Selector)
        self.assertEqual(who.referent, "event")

    def test_ghostly_pilferer_cast_draw_one(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever an opponent casts a spell from anywhere other "
                "than their hand, draw a card.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.DRAW)
        self.assertIs(atom.args.get("controller"), ControllerRef.YOU)
        self.assertEqual(_qconst(atom, "amount").value, 1)

    def test_double_vision_copy_referent_source(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you cast your first instant or sorcery spell "
                "each turn, copy that spell.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.COPY)
        self._referent_selector(atom, "source")

    def test_double_vision_new_targets_is_rule_reminder(self) -> None:
        match = _single_match(
            self.reg,
            "You may choose new targets for the copy.",
        )
        outcome = match.outcome
        assert isinstance(outcome, RuleReminderOutcome)
        self.assertEqual(outcome.reason, "anaphoric_continuation")

    def test_garruks_harbinger_look_at_event_amount(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever this creature deals combat damage to a player or "
                "planeswalker, look at that many cards from the top of your "
                "library.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.LOOK_AT)
        self.assertIs(atom.args.get("controller"), ControllerRef.YOU)
        count = _qprop(atom, "count")
        self.assertEqual(count.referent, "event")
        self.assertIs(count.field, QPropField.AMOUNT)

    def test_jolrael_create_cat_token(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you draw your second card each turn, create a "
                "2/2 green Cat creature token.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.CREATE_TOKEN)
        token = _token(atom, "tokens")
        self.assertEqual(token.name, "Cat")
        self.assertEqual(token.type_line, "Creature — Cat")
        self.assertEqual(token.subtypes, ("Cat",))
        assert isinstance(token.power, QConst)
        self.assertEqual(token.power.value, 2)
        assert isinstance(token.toughness, QConst)
        self.assertEqual(token.toughness.value, 2)
        self.assertEqual(_qconst(atom, "count").value, 1)

    def test_mystic_skyfish_grant_flying_eot(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you draw your second card each turn, this "
                "creature gains flying until end of turn.",
            )
        )
        atom = _atom(ability)
        self.assertIs(atom.verb, Verb.GRANT_ABILITY)
        target = _selector(atom, "target")
        # b2b self-reference convention: battlefield zone, ANY controller.
        self.assertEqual(target.zones[0], Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY))
        assert isinstance(target.filter, FAtom)
        self.assertIs(target.filter.pred, FAtomPred.IS_SOURCE)
        keyword = atom.args.get("ability")
        assert isinstance(keyword, KeywordAbility)
        self.assertIs(keyword.keyword, Keyword.FLYING)
        self.assertIsInstance(atom.args.get("duration"), DurationEot)

    def test_keral_keep_each_opponent_deal_one(self) -> None:
        ability = _ability(
            _single_match(
                self.reg,
                "Whenever you activate a loyalty ability of a Chandra "
                "planeswalker, this creature deals 1 damage to each "
                "opponent.",
            )
        )
        each = ability.effect
        assert isinstance(each, EachPlayer)
        self.assertIs(each.ref, ControllerRef.ALL_OPPONENTS)
        effect = each.effect
        assert isinstance(effect, Atom)
        self.assertIs(effect.verb, Verb.DEAL_DAMAGE)
        target = _selector(effect, "target")
        self.assertIs(target.mode, SelectorMode.CHOOSE)
        self.assertEqual(target.zones[0], Zone(ZoneKind.PLAYER, ControllerRef.YOU))
        self.assertEqual(_qconst(effect, "amount").value, 1)

    def _assert_has_subtype_dog_like(self, a_filter: Filter) -> None:
        atom = _find_atom(a_filter, FAtomPred.SUBTYPE_EQ)
        self.assertEqual(atom.string_value, "Dog")

    # --- small filter assertion helpers ---

    def _assert_has_type_eq_creature(self, a_filter: Filter) -> None:
        atom = _find_atom(a_filter, FAtomPred.TYPE_EQ)
        self.assertEqual(atom.string_value, "Creature")

    def _assert_has_controller_you(self, a_filter: Filter) -> None:
        atom = _find_atom(a_filter, FAtomPred.CONTROLLER_IS)
        self.assertIs(atom.who, ControllerRef.YOU)

    def _assert_has_is_attacking(self, a_filter: Filter) -> None:
        atom = _find_atom(a_filter, FAtomPred.IS_ATTACKING)
        del atom  # just checking presence

    def _assert_has_is_untapped(self, a_filter: Filter) -> None:
        atom = _find_atom(a_filter, FAtomPred.IS_UNTAPPED)
        del atom


class TestB2bRound7BTopUp(unittest.TestCase):
    """R7-B: Snarespinner — first production TRIGGER use of the R6-4
    DeclareBlockersEvent.blocked slot (doc 2026-09-28/03 §3 B-table row 7)."""

    def test_blocks_flying_pump_structure(self) -> None:
        reg = _registry()
        m = _single_match(
            reg,
            "Whenever this creature blocks a creature with flying, this "
            "creature gets +2/+0 until end of turn.",
        )
        ability = _ability(m)
        event = ability.event
        assert isinstance(event, DeclareBlockersEvent)
        # blocker side: IS_SOURCE rides the primary filter (b4 cant-block shape)
        blocker_filter = event.filter
        assert isinstance(blocker_filter, FAtom)
        self.assertIs(blocker_filter.pred, FAtomPred.IS_SOURCE)
        self.assertIsNone(event.subject)
        # blocked side (R6-4 slot): KEYWORD_HAS flying — Shacklegeist idiom,
        # now on the trigger (validation is type-only, __post_init__ permits it)
        blocked = event.blocked
        assert isinstance(blocked, FAtom)
        self.assertIs(blocked.pred, FAtomPred.KEYWORD_HAS)
        self.assertEqual(blocked.keyword, Keyword.FLYING)
        # effect: MODIFY_PT on self, power-only (+2/+0), EOT
        eff = ability.effect
        assert isinstance(eff, Atom)
        self.assertIs(eff.verb, Verb.MODIFY_PT)
        roles = dict(eff.args.pairs)
        self.assertEqual(roles["duration"], DurationEot())
        self.assertNotIn("toughness", roles)
        power = roles["power"]
        assert isinstance(power, PtDelta)
        self.assertEqual(power, PtDelta(PtDirection.INCREASE, QConst(2)))
        target = roles["target"]
        assert isinstance(target, Selector)
        self.assertIs(target.mode, SelectorMode.CHOOSE)
        self.assertEqual(target.filter, FAtom(pred=FAtomPred.IS_SOURCE))


# ---------------------------------------------------------------------------
# Round 9-B — Tolarian Kraken "When you do" do-continuation (R9-9, C24)
# ---------------------------------------------------------------------------


class TestB2bRound9BDoContinuation(unittest.TestCase):
    """R9-B: Tolarian Kraken s2 — the standalone continuation outcome is
    EXACTLY what the compiler's R9-9 do-merge injects inside the s1
    cost-paying OptionalEffect (doc 2026-09-28/11 §R9-9/§9-B row 5)."""

    S1 = "Whenever you draw a card, you may pay {1}."
    S2 = "When you do, you may tap or untap target creature."

    def _creature_target(self) -> Selector:
        return Selector(
            count=QConst(1),
            mode=SelectorMode.TARGET,
            filter=FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
        )

    def test_s2_structure_choose_one_of_two_under_may(self) -> None:
        reg = _registry()
        m = _single_match(reg, self.S2)
        self.assertEqual(m.template.tid, "B2b-do-tap-or-untap")
        outcome = m.outcome
        assert isinstance(outcome, EffectOutcome)
        outer = outcome.effect
        # "you may" — the s2 Optional is its OWN layer (the merge adds none;
        # the r9-A double-wrap pin test_ability_tree_r10 forbids a second)
        assert isinstance(outer, OptionalEffect)
        choice = outer.inner
        assert isinstance(choice, Choose)
        self.assertEqual(choice.count, QConst(1))
        self.assertEqual(len(choice.options), 2)
        target = self._creature_target()
        tap, untap = choice.options
        assert isinstance(tap, Atom) and isinstance(untap, Atom)
        self.assertIs(tap.verb, Verb.TAP)
        self.assertIs(untap.verb, Verb.UNTAP)
        self.assertEqual(dict(tap.args.pairs), {"target": target})
        self.assertEqual(dict(untap.args.pairs), {"target": target})

    def test_pair_merge_final_tree(self) -> None:
        """s1 OptionalEffect(PAY) + s2 continuation → INNER injection:
        OptionalEffect(Seq(PAY, OptionalEffect(Choose(...)))) — never a
        sibling optional (C24)."""
        reg = _registry()
        s1 = _single_match(reg, self.S1)
        s2 = _single_match(reg, self.S2)
        assert isinstance(s1.outcome, AbilityOutcome)
        prior = _ability(s1).effect
        assert isinstance(s2.outcome, EffectOutcome)
        cont = s2.outcome.effect  # the raw standalone EffectOutcome payload
        merged = _merge_do_continuation(prior, cont)
        assert isinstance(prior, OptionalEffect)
        pay = prior.inner  # Atom(PAY, Cost({1}))
        expected = OptionalEffect(inner=Seq(steps=(pay, cont)))
        self.assertEqual(merged, expected)
        # the injection is INSIDE the payment optional, not beside it
        self.assertIsInstance(merged, OptionalEffect)
        assert isinstance(merged, OptionalEffect)
        self.assertIsInstance(merged.inner, Seq)


# ---------------------------------------------------------------------------
# Round 10 — Mangara, the Diplomat attackers-against-me draw (R10-3)
# ---------------------------------------------------------------------------


class TestB2bRound10Mangara(unittest.TestCase):
    """R10: Mangara s1 — first production use of the R10-3
    DeclareAttackersEvent.attacked slot (twin of R6-4 blocked) plus the
    ATTACK_AGAINST_COUNT_GE condition predicate (doc 2026-09-29/02
    §phase-10-B row 3)."""

    S1 = (
        "Whenever an opponent attacks with creatures, if two or more of "
        "those creatures are attacking you and/or planeswalkers you "
        "control, draw a card."
    )

    def test_mangara_structure(self) -> None:
        reg = _registry()
        m = _single_match(reg, self.S1)
        self.assertEqual(m.template.tid, "B2b-attackers-against-me-draw")
        ability = _ability(m)
        # trigger: set-level DeclareAttackersEvent over the opponent's
        # creatures (per-opponent declaration events)
        event = ability.event
        assert isinstance(event, DeclareAttackersEvent)
        event_filter = event.filter
        assert isinstance(event_filter, FAnd)
        self.assertEqual(len(event_filter.children), 2)
        # R1a canonicalization: FAnd children construction-sorted; members by
        # pred, order by the canonicalization law.
        self.assertEqual(
            list(event_filter.children),
            sorted(event_filter.children, key=canonical_json),
        )
        by_pred = {c.pred: c for c in event_filter.children}
        self.assertEqual(len(by_pred), 2)
        kind, controller = by_pred[FAtomPred.TYPE_EQ], by_pred[FAtomPred.CONTROLLER_IS]
        assert isinstance(kind, FAtom) and isinstance(controller, FAtom)
        self.assertIs(kind.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(kind.string_value, "Creature")
        self.assertIs(controller.pred, FAtomPred.CONTROLLER_IS)
        self.assertIs(controller.who, ControllerRef.OPPONENT)
        # attacked side (R10-3 slot): "you and/or planeswalkers you control"
        expected_attacked = templates_b2b._you_or_your_planeswalkers()
        attacked = event.attacked
        assert isinstance(attacked, FOr)
        self.assertEqual(attacked, expected_attacked)
        self.assertEqual(len(attacked.children), 2)
        # R1a canonicalization: FOr/FAnd children construction-sorted, so the
        # two sides and the conjuncts inside the planeswalker branch are
        # pinned by IDENTITY/pred, and each order by the canonicalization law.
        self.assertEqual(
            list(attacked.children), sorted(attacked.children, key=canonical_json)
        )
        you = next(c for c in attacked.children if isinstance(c, FAtom))
        walkers = next(c for c in attacked.children if isinstance(c, FAnd))
        assert isinstance(you, FAtom) and isinstance(walkers, FAnd)
        self.assertIs(you.pred, FAtomPred.CONTROLLER_IS)
        self.assertIs(you.who, ControllerRef.YOU)
        self.assertEqual(
            list(walkers.children), sorted(walkers.children, key=canonical_json)
        )
        pw_by_pred = {c.pred: c for c in walkers.children}
        self.assertEqual(len(pw_by_pred), 2)
        pw_kind = pw_by_pred[FAtomPred.TYPE_EQ]
        pw_controller = pw_by_pred[FAtomPred.CONTROLLER_IS]
        assert isinstance(pw_kind, FAtom) and isinstance(pw_controller, FAtom)
        self.assertEqual(pw_kind.string_value, "Planeswalker")
        self.assertIs(pw_controller.who, ControllerRef.YOU)
        # condition slot: "if two or more of those creatures ..." rides
        # ATTACK_AGAINST_COUNT_GE with the same attacked-side composition
        condition = ability.condition
        assert isinstance(condition, FAtom)
        self.assertIs(condition.pred, FAtomPred.ATTACK_AGAINST_COUNT_GE)
        self.assertEqual(condition.count, QConst(2))
        self.assertEqual(condition.inner_filter, expected_attacked)
        # effect: forced DRAW one card by you
        eff = _atom(ability)
        self.assertIs(eff.verb, Verb.DRAW)
        self.assertEqual(
            dict(eff.args.pairs),
            {"controller": ControllerRef.YOU, "amount": QConst(1)},
        )
