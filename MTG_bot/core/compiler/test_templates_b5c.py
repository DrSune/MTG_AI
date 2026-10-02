"""Tests for B5c bucket templates (templates_b5c.py).

Covers all 91 distinct concrete sentences in
``/tmp/opencode/phase1_buckets/B5c.json`` (90 normalized keys, 100
occurrences):

- 74 sentences template-covered by 73 templates
  (``B5c-bullet-gain-life`` matches both "You gain 3 life." and
  "You gain 4 life.")
- 17 sentences UNCOVERED (no grammar construct; recorded for gap tracking)
- 0 rule-reminder shapes (B5c has no RR category)

PC-3: every concrete sentence fullmatches at most one template.

The embedded :data:`SHAPES` table is the single source of truth for the
core matching/structural/canonical tests, so they run without the JSON.
The JSON cross-check class (last) is skipped when the file is absent.
"""

from __future__ import annotations

import json
import os
import unittest
from typing import Any

from MTG_bot.core.ability_tree import (
    QX,
    ActivatedAbility,
    Atom,
    Conditional,
    ControllerRef,
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
    PtDirection,
    QAgg,
    QBinOp,
    QAtMost,
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
    TriggeredAbility,
    Verb,
    Zone,
    ZoneKind,
    ZonePosition,
    canonical_json,
)
from MTG_bot.core.compiler.templates import (
    AbilityOutcome,
    EffectOutcome,
    KeywordOutcome,
    SentenceOutcome,
    TemplateRegistry,
)
from MTG_bot.core.compiler.templates_b5c import TEMPLATES, UNCOVERED

# ---------------------------------------------------------------------------
# SHAPES — 91 concrete sentences from B5c.json with expected classification.
# Each entry: (sentence, category, expected_tid)
#   category: "COVERED" = template-covered, "UNCOV" = uncovered (no RR)
# ---------------------------------------------------------------------------

SHAPES: tuple[tuple[str, str, str], ...] = (
    (
        "Then if you control four or more lands, untap that land.",
        "COVERED",
        "B5c-then-if-lands-untap",
    ),
    (
        "Then it fights up to one target creature you don't control.",
        "COVERED",
        "B5c-then-it-fights",
    ),
    (
        "Then that creature deals damage equal to its power to target creature you don't control.",
        "COVERED",
        "B5c-damage-equal-power",
    ),
    (
        "Then you may return an instant or sorcery card from your graveyard to your hand.",
        "COVERED",
        "B5c-then-return-is",
    ),
    (
        "This Equipment enters with a soul counter on it.",
        "COVERED",
        "B5c-etb-soul-counter",
    ),
    (
        "This ability costs {1} less to activate for each Shrine you control.",
        "COVERED",
        "B5c-shrine-activation-cost",
    ),
    (
        "Those creatures don't untap during their controller's next untap step.",
        "COVERED",
        "B5c-those-no-untap-next",
    ),
    (
        "Trample (This creature can deal excess combat damage to the player or planeswalker it's attacking.)",
        "COVERED",
        "B5c-remind-trample",
    ),
    ("Turn to Slag deals 5 damage to target creature.", "COVERED", "B5c-turn-to-slag"),
    ("Untap that creature.", "COVERED", "B5c-untap-that-creature"),
    ("Untap up to four lands.", "COVERED", "B5c-untap-lands"),
    (
        "Until end of turn, target creature gets +0/+2 and another target creature gets -2/-0.",
        "COVERED",
        "B5c-pt-swap",
    ),
    (
        "Until end of turn, you may cast spells from your hand without paying their mana costs.",
        "COVERED",
        "B5c-waive-cast-from-hand",
    ),
    (
        "Until end of turn, you may play cards exiled this way.",
        "COVERED",
        "B5c-play-cards-exiled-this-way",
    ),
    ("Until the end of your next turn, they can't phase in.", "UNCOV", ""),
    (
        "Vigilance (Attacking doesn't cause this creature to tap.)",
        "COVERED",
        "B5c-remind-vigilance",
    ),
    (
        "Vigilance, lifelink (Attacking doesn't cause this creature to tap. Damage dealt by this creature also causes you to gain that much life.)",
        "COVERED",
        "B5c-remind-vigilance-lifelink",
    ),
    (
        "Vigilance, protection from multicolored",
        "COVERED",
        "B5c-remind-vigilance-protection",
    ),
    ("Vigilance, reach, trample", "COVERED", "B5c-remind-vigilance-reach-trample"),
    ("Volcanic Geyser deals X damage to any target.", "COVERED", "B5c-geyser-dmg"),
    (
        "Volcanic Salvo deals 6 damage to each of up to two target creatures and/or planeswalkers.",
        "COVERED",
        "B5c-salvo-dmg",
    ),
    ("Zombies you control get +1/+0.", "COVERED", "B5c-zombies-pt"),
    (
        "[+1]: Chandra deals 2 damage to any target.",
        "COVERED",
        "B5c-loyalty-chandra-dmg-any",
    ),
    (
        "[+1]: Chandra deals 3 damage to each opponent.",
        "COVERED",
        "B5c-loyalty-chandra-dmg-opps",
    ),
    (
        "[+1]: Discard your hand, then exile the top three cards of your library.",
        "COVERED",
        "B5c-loyalty-discard-exile-top",
    ),
    ("[+1]: Draw a card, then discard a card.", "COVERED", "B5c-loyalty-draw-discard"),
    ("[+1]: Draw a card.", "COVERED", "B5c-loyalty-draw"),
    ("[+1]: Each player discards a card.", "COVERED", "B5c-loyalty-each-discard"),
    (
        "[+1]: Put a +1/+1 counter on up to one target creature.",
        "COVERED",
        "B5c-loyalty-put-counter",
    ),
    (
        "[+1]: Return up to one target creature card from your graveyard to your hand.",
        "COVERED",
        "B5c-loyalty-return-creature",
    ),
    ("[+1]: Reveal the top card of your library.", "COVERED", "B5c-loyalty-reveal"),
    (
        "[+1]: Up to one target creature gets +3/+3 and gains trample until end of turn.",
        "COVERED",
        "B5c-loyalty-pt-trample",
    ),
    ("[+2]: Ugin deals 3 damage to any target.", "COVERED", "B5c-loyalty-ugin-dmg"),
    (
        "[−10]: Take two extra turns after this one.",
        "COVERED",
        "B5c-loyalty-extra-turns",
    ),
    (
        "[−10]: You gain 7 life, draw seven cards, then put up to seven permanent cards from your hand onto the battlefield.",
        "COVERED",
        "B5c-loyalty-gain-draw-put",
    ),
    (
        "[−1]: Whenever a creature attacks this turn, put a +1/+1 counter on it.",
        "COVERED",
        "B5c-loyalty-basri-attack-counter",
    ),
    (
        "[−2]: Create a 3/3 green Beast creature token.",
        "COVERED",
        "B5c-loyalty-create-token",
    ),
    (
        "[−2]: Target creature you control deals damage equal to its power to another target creature.",
        "COVERED",
        "B5c-loyalty-dmg-power",
    ),
    (
        "[−2]: Whenever one or more nontoken creatures attack this turn, create that many 1/1 white Soldier creature tokens that are tapped and attacking.",
        "COVERED",
        "B5c-loyalty-soldier-attack-tokens",
    ),
    (
        "[−2]: You may cast target red instant or sorcery card from your graveyard.",
        "COVERED",
        "B5c-loyalty-may-cast-graveyard",
    ),
    ("[−3]: Destroy target creature.", "COVERED", "B5c-loyalty-destroy"),
    (
        "[−3]: Put target creature on top of its owner's library.",
        "COVERED",
        "B5c-loyalty-top-owner-library",
    ),
    (
        "[−3]: Target creature gets -X/-X until end of turn, where X is the number of cards in your graveyard.",
        "COVERED",
        "B5c-loyalty-pt-qprop",
    ),
    (
        "[−3]: Target creature you don't control phases out.",
        "COVERED",
        "B5c-loyalty-phase-out-target",
    ),
    (
        "[−6]: Creatures you control get +2/+2 and gain flying until end of turn.",
        "COVERED",
        "B5c-loyalty-creatures-pt-flying",
    ),
    (
        '[−6]: You get an emblem with "At the beginning of combat on your turn, create a 1/1 white Soldier creature token, then put a +1/+1 counter on each creature you control."',
        "COVERED",
        "B5c-get-emblem",
    ),
    (
        "[−7]: Target opponent loses 2 life for each creature card in their graveyard.",
        "COVERED",
        "B5c-loyalty-lose-per-creature",
    ),
    (
        '[−7]: Until end of turn, creatures you control gain "You may have this creature assign its combat damage as though it weren\'t blocked."',
        "COVERED",
        "B5c-loyalty-assign-as-unblocked",
    ),
    (
        '[−7]: You get an emblem with "At the beginning of combat on your turn, put target creature card from a graveyard onto the battlefield under your control.',
        "COVERED",
        "B5c-get-emblem",
    ),
    (
        '[−7]: You get an emblem with "At the beginning of your end step, you may search your library for a creature card, put it onto the battlefield, then shuffle."',
        "COVERED",
        "B5c-get-emblem",
    ),
    (
        "[−8]: Discard your hand, then draw seven cards.",
        "COVERED",
        "B5c-loyalty-discard-draw",
    ),
    (
        "[−8]: Each creature target opponent controls phases out.",
        "COVERED",
        "B5c-loyalty-phase-out-all",
    ),
    (
        "[−9]: Search your graveyard and library for any number of red instant and/or sorcery cards, exile them, then shuffle.",
        "COVERED",
        "B5c-loyalty-search-exile",
    ),
    (
        "[−X]: Exile each permanent with mana value X or less that's one or more colors.",
        "COVERED",
        "B5c-loyalty-exile-color-cmc-ux",
    ),
    (
        "{1}, Discard a land card or Shrine card: Sanctum of Shattered Heights deals X damage to target creature or planeswalker, where X is the number of Shrines you control.",
        "COVERED",
        "B5c-cost-shrine-dmg",
    ),
    (
        "{1}, Sacrifice another creature: Put a +1/+1 counter on this creature.",
        "COVERED",
        "B5c-cost-sacrifice-counter",
    ),
    (
        "{1}, Sacrifice this creature: Destroy target artifact or enchantment.",
        "COVERED",
        "B5c-cost-sacrifice-destroy",
    ),
    (
        "{1}{B}, Sacrifice this creature: Draw a card.",
        "COVERED",
        "B5c-cost-b-sacrifice-draw",
    ),
    (
        "{1}{B}, {T}, Sacrifice a creature: You gain 1 life and draw a card.",
        "COVERED",
        "B5c-cost-b-tap-gain-draw",
    ),
    (
        "{1}{R}, {T}, Discard your hand: Until end of turn, whenever a creature you control with power 2 or less deals combat damage to a player, draw a card.",
        "COVERED",
        "B5c-cost-discard-hand-delayed-draw",
    ),
    (
        "{1}{U}, Discard this card: Look at the top two cards of your library.",
        "COVERED",
        "B5c-cost-u-discard-look",
    ),
    (
        "{1}{W}{U}, {T}, Discard a legendary card: Draw two cards.",
        "COVERED",
        "B5c-cost-wu-discard-draw",
    ),
    (
        "{2}, {T}, Put a page counter on this artifact: Draw a card.",
        "COVERED",
        "B5c-cost-page-draw",
    ),
    (
        "{2}, {T}, Sacrifice a creature with defender: Draw a card.",
        "COVERED",
        "B5c-cost-sacrifice-defender",
    ),
    (
        "{2}{U}{B}, {T}, Sacrifice this creature: Return target creature card from your graveyard to the battlefield.",
        "COVERED",
        "B5c-cost-ub-sacrifice-return",
    ),
    (
        "{4}, {T}, Sacrifice this artifact: It deals 3 damage to target creature.",
        "COVERED",
        "B5c-cost-sacrifice-dmg",
    ),
    (
        "{R}, Sacrifice this creature: It deals damage equal to its power to target creature or planeswalker.",
        "COVERED",
        "B5c-cost-r-sacrifice-power-dmg",
    ),
    ("{T}, Pay 3 life: Flip a coin.", "COVERED", "B5c-flip-cost"),
    (
        "{T}, Put a page counter on this artifact: Scry 1.",
        "COVERED",
        "B5c-cost-page-scry",
    ),
    (
        "{T}, Sacrifice this artifact: Exile target player's graveyard.",
        "COVERED",
        "B5c-cost-sacrifice-exile",
    ),
    (
        "{T}, Sacrifice this creature: Target opponent discards a card.",
        "COVERED",
        "B5c-cost-sacrifice-discard",
    ),
    (
        "{T}, Sacrifice this land: Search your library for a basic land card, put it onto the battlefield tapped, then shuffle.",
        "COVERED",
        "B5c-cost-sacrifice-search",
    ),
    (
        "{T}, Sacrifice this token: Add one mana of any color.",
        "COVERED",
        "B5c-cost-sacrifice-mana",
    ),
    ("• All creatures get -2/-2 until end of turn.", "COVERED", "B5c-bullet-all-pt"),
    (
        "• Counter target activated or triggered ability.",
        "COVERED",
        "B5c-bullet-counter-ability",
    ),
    ("• Counter target spell.", "COVERED", "B5c-bullet-counter-spell"),
    (
        "• Create a 3/3 green Beast creature token.",
        "COVERED",
        "B5c-bullet-create-token",
    ),
    (
        "• Create a token that's a copy of target creature you control.",
        "COVERED",
        "B5c-bullet-copy-token",
    ),
    (
        "• Creatures without flying can't block this turn.",
        "COVERED",
        "B5c-bullet-cant-block",
    ),
    ("• Destroy target artifact.", "COVERED", "B5c-bullet-destroy-artifact"),
    ("• Destroy target enchantment.", "COVERED", "B5c-bullet-destroy-enchantment"),
    ("• Draw a card.", "COVERED", "B5c-bullet-draw"),
    ("• Draw three cards.", "COVERED", "B5c-bullet-draw-three"),
    ("• Exile target card from a graveyard.", "COVERED", "B5c-bullet-exile-graveyard"),
    ("• Put a +1/+1 counter on this creature.", "COVERED", "B5c-bullet-put-counter"),
    (
        "• Remove two loyalty counters from each planeswalker.",
        "COVERED",
        "B5c-bullet-remove-loyalty",
    ),
    (
        "• Return target nonland permanent to its owner's hand.",
        "COVERED",
        "B5c-bullet-return-nonland-hand",
    ),
    (
        "• Return up to two target creatures to their owners' hands.",
        "COVERED",
        "B5c-bullet-return-two-creatures-hand",
    ),
    ("• Target player draws a card.", "COVERED", "B5c-bullet-target-draw"),
    ("• You gain 3 life.", "COVERED", "B5c-bullet-gain-life"),
    ("• You gain 4 life.", "COVERED", "B5c-bullet-gain-life"),
)


# ---------------------------------------------------------------------------
# Expected outcome-kind per template tid.
#   "effect"    -> EffectOutcome (single effect node)
#   "keyword"   -> KeywordOutcome (rule-reminder keyword)
#   "static"    -> AbilityOutcome(StaticAbility)
#   "activated" -> AbilityOutcome(ActivatedAbility)
# ---------------------------------------------------------------------------

_EXPECTED_EFFECT = (
    "B5c-then-return-is",
    "B5c-then-it-fights",
    "B5c-then-if-lands-untap",
    "B5c-damage-equal-power",
    "B5c-untap-that-creature",
    "B5c-turn-to-slag",
    "B5c-untap-lands",
    "B5c-pt-swap",
    "B5c-geyser-dmg",
    "B5c-salvo-dmg",
    "B5c-bullet-all-pt",
    "B5c-bullet-counter-ability",
    "B5c-bullet-counter-spell",
    "B5c-bullet-create-token",
    "B5c-bullet-copy-token",
    "B5c-bullet-cant-block",
    "B5c-bullet-destroy-artifact",
    "B5c-bullet-destroy-enchantment",
    "B5c-bullet-draw",
    "B5c-bullet-draw-three",
    "B5c-bullet-exile-graveyard",
    "B5c-bullet-put-counter",
    "B5c-bullet-remove-loyalty",
    "B5c-bullet-target-draw",
    "B5c-bullet-gain-life",
    "B5c-bullet-return-nonland-hand",
    "B5c-bullet-return-two-creatures-hand",
)

_EXPECTED_KEYWORD = (
    "B5c-remind-trample",
    "B5c-remind-vigilance",
    "B5c-remind-vigilance-lifelink",
    "B5c-remind-vigilance-protection",
    "B5c-remind-vigilance-reach-trample",
)

_EXPECTED_STATIC = ("B5c-zombies-pt",)

_EXPECTED_ETB = ("B5c-etb-soul-counter",)

_EXPECTED_ACTIVATED = (
    # 27 loyalty
    "B5c-loyalty-chandra-dmg-any",
    "B5c-loyalty-chandra-dmg-opps",
    "B5c-loyalty-draw-discard",
    "B5c-loyalty-draw",
    "B5c-loyalty-each-discard",
    "B5c-loyalty-put-counter",
    "B5c-loyalty-return-creature",
    "B5c-loyalty-reveal",
    "B5c-loyalty-ugin-dmg",
    "B5c-loyalty-pt-trample",
    "B5c-loyalty-create-token",
    "B5c-loyalty-creatures-pt-flying",
    "B5c-loyalty-destroy",
    "B5c-loyalty-discard-draw",
    "B5c-loyalty-phase-out-all",
    "B5c-loyalty-search-exile",
    "B5c-loyalty-extra-turns",
    "B5c-loyalty-pt-qprop",
    "B5c-loyalty-dmg-power",
    "B5c-loyalty-phase-out-target",
    "B5c-loyalty-lose-per-creature",
    "B5c-loyalty-gain-draw-put",
    "B5c-loyalty-exile-color-cmc-ux",
    "B5c-loyalty-discard-exile-top",
    "B5c-loyalty-top-owner-library",
    "B5c-loyalty-may-cast-graveyard",
    "B5c-loyalty-basri-attack-counter",
    # 17 cost
    "B5c-cost-shrine-dmg",
    "B5c-cost-sacrifice-counter",
    "B5c-cost-sacrifice-destroy",
    "B5c-cost-page-draw",
    "B5c-cost-sacrifice-defender",
    "B5c-cost-sacrifice-dmg",
    "B5c-cost-b-sacrifice-draw",
    "B5c-cost-b-tap-gain-draw",
    "B5c-cost-u-discard-look",
    "B5c-cost-ub-sacrifice-return",
    "B5c-cost-wu-discard-draw",
    "B5c-cost-r-sacrifice-power-dmg",
    "B5c-cost-page-scry",
    "B5c-cost-sacrifice-exile",
    "B5c-cost-sacrifice-discard",
    "B5c-cost-sacrifice-search",
    "B5c-cost-sacrifice-mana",
    "B5c-flip-cost",
)

EXPECTED_KIND_BY_TID: dict[str, str] = {}
for _t in _EXPECTED_EFFECT:
    EXPECTED_KIND_BY_TID[_t] = "effect"
for _t in _EXPECTED_KEYWORD:
    EXPECTED_KIND_BY_TID[_t] = "keyword"
for _t in _EXPECTED_STATIC:
    EXPECTED_KIND_BY_TID[_t] = "static"
for _t in _EXPECTED_ETB:
    EXPECTED_KIND_BY_TID[_t] = "ability:EtBState"
for _t in _EXPECTED_ACTIVATED:
    EXPECTED_KIND_BY_TID[_t] = "activated"
# grammar round 8-C (doc 2026-09-28/08): four new ActivatedAbility rows +
# the Sanctum CostModifier sibling (a new outcome kind for this module).
for _t in (
    "B5c-get-emblem",
    "B5c-loyalty-soldier-attack-tokens",
    "B5c-waive-cast-from-hand",
    "B5c-play-cards-exiled-this-way",
):
    EXPECTED_KIND_BY_TID[_t] = "activated"
EXPECTED_KIND_BY_TID["B5c-shrine-activation-cost"] = "ability:CostModifier"
# grammar round 9-B: Frost s2 instant-folded PREVENT (effect) + Subira s2
# delayed-draw activation (activated).
EXPECTED_KIND_BY_TID["B5c-those-no-untap-next"] = "effect"
EXPECTED_KIND_BY_TID["B5c-cost-discard-hand-delayed-draw"] = "activated"
# grammar round 10: Garruk, Savage Herald [−N] assign-as-unblocked grant.
EXPECTED_KIND_BY_TID["B5c-loyalty-assign-as-unblocked"] = "activated"


# Expected LoyaltyActivation delta per loyalty template.
EXPECTED_LOYALTY_DELTA: dict[str, int] = {
    "B5c-loyalty-chandra-dmg-any": 1,
    "B5c-loyalty-chandra-dmg-opps": 1,
    "B5c-loyalty-draw-discard": 1,
    "B5c-loyalty-draw": 1,
    "B5c-loyalty-each-discard": 1,
    "B5c-loyalty-put-counter": 1,
    "B5c-loyalty-return-creature": 1,
    "B5c-loyalty-reveal": 1,
    "B5c-loyalty-ugin-dmg": 2,
    "B5c-loyalty-pt-trample": 1,
    "B5c-loyalty-create-token": -2,
    "B5c-loyalty-creatures-pt-flying": -6,
    "B5c-loyalty-destroy": -3,
    "B5c-loyalty-discard-draw": -8,
    "B5c-loyalty-phase-out-all": -8,
    "B5c-loyalty-search-exile": -9,
    "B5c-loyalty-extra-turns": -10,
    "B5c-loyalty-pt-qprop": -3,
    "B5c-loyalty-dmg-power": -2,
    "B5c-loyalty-phase-out-target": -3,
    "B5c-loyalty-lose-per-creature": -7,
    "B5c-loyalty-gain-draw-put": -10,
    "B5c-loyalty-discard-exile-top": 1,
    "B5c-loyalty-top-owner-library": -3,
    "B5c-loyalty-may-cast-graveyard": -2,
    "B5c-loyalty-basri-attack-counter": -1,
    "B5c-loyalty-assign-as-unblocked": -7,
}

# Expected ordered cost-part types per cost template.
EXPECTED_COST_PARTS: dict[str, tuple[type, ...]] = {
    "B5c-flip-cost": (CostTap, CostLife),
    "B5c-cost-shrine-dmg": (CostManaGeneric, CostDiscard),
    "B5c-cost-sacrifice-counter": (CostManaGeneric, CostSacrifice),
    "B5c-cost-sacrifice-destroy": (CostManaGeneric, CostSacrifice),
    "B5c-cost-page-draw": (CostManaGeneric, CostTap, CostPutCounter),
    "B5c-cost-sacrifice-defender": (CostManaGeneric, CostTap, CostSacrifice),
    "B5c-cost-sacrifice-dmg": (CostManaGeneric, CostTap, CostSacrifice),
    "B5c-cost-b-sacrifice-draw": (CostManaGeneric, CostManaColor, CostSacrifice),
    "B5c-cost-b-tap-gain-draw": (
        CostManaGeneric,
        CostManaColor,
        CostTap,
        CostSacrifice,
    ),
    "B5c-cost-u-discard-look": (CostManaGeneric, CostManaColor, CostDiscard),
    "B5c-cost-ub-sacrifice-return": (
        CostManaGeneric,
        CostManaColor,
        CostManaColor,
        CostTap,
        CostSacrifice,
    ),
    "B5c-cost-wu-discard-draw": (
        CostManaGeneric,
        CostManaColor,
        CostManaColor,
        CostTap,
        CostDiscard,
    ),
    "B5c-cost-r-sacrifice-power-dmg": (CostManaColor, CostSacrifice),
    "B5c-cost-page-scry": (CostTap, CostPutCounter),
    "B5c-cost-sacrifice-exile": (CostTap, CostSacrifice),
    "B5c-cost-sacrifice-discard": (CostTap, CostSacrifice),
    "B5c-cost-sacrifice-search": (CostTap, CostSacrifice),
    "B5c-cost-sacrifice-mana": (CostTap, CostSacrifice),
}

# The single "primary" keyword each rule-reminder template encodes. Several
# are documented lossy (secondary keywords dropped; see templates_b5c.py).
EXPECTED_REMIND_KEYWORD: dict[str, Keyword] = {
    "B5c-remind-trample": Keyword.TRAMPLE,
    "B5c-remind-vigilance": Keyword.VIGILANCE,
    "B5c-remind-vigilance-lifelink": Keyword.VIGILANCE,
    "B5c-remind-vigilance-protection": Keyword.PROTECTION,
    "B5c-remind-vigilance-reach-trample": Keyword.VIGILANCE,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry() -> TemplateRegistry:
    """Build a TemplateRegistry with all B5c templates."""
    reg = TemplateRegistry()
    for t in TEMPLATES:
        reg.register(t)
    return reg


_REG: TemplateRegistry = _make_registry()


def _match_outcome(tid: str) -> SentenceOutcome:
    """Match the covered SHAPES sentence for ``tid`` and return its outcome."""
    for sent, cat, t in SHAPES:
        if t == tid and cat == "COVERED":
            matches = _REG.match(sent)
            assert len(matches) == 1, f"expected 1 match for {tid}, got {len(matches)}"
            return matches[0].outcome
    raise AssertionError(f"no COVERED SHAPES row for tid {tid}")


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


def _kind_of(outcome: SentenceOutcome) -> str:
    """Classify an outcome into effect/keyword/static/activated."""
    if isinstance(outcome, EffectOutcome):
        return "effect"
    if isinstance(outcome, KeywordOutcome):
        return "keyword"
    if isinstance(outcome, AbilityOutcome):
        ability = outcome.ability
        if isinstance(ability, StaticAbility):
            return "static"
        if isinstance(ability, ActivatedAbility):
            return "activated"
        return f"ability:{type(ability).__name__}"
    return f"unknown:{type(outcome).__name__}"


def _as_effect(outcome: SentenceOutcome) -> EffectOutcome:
    if not isinstance(outcome, EffectOutcome):
        raise TypeError(f"expected EffectOutcome, got {type(outcome)}")
    return outcome


def _as_ability(outcome: SentenceOutcome) -> AbilityOutcome:
    if not isinstance(outcome, AbilityOutcome):
        raise TypeError(f"expected AbilityOutcome, got {type(outcome)}")
    return outcome


def _as_keyword(outcome: SentenceOutcome) -> KeywordOutcome:
    if not isinstance(outcome, KeywordOutcome):
        raise TypeError(f"expected KeywordOutcome, got {type(outcome)}")
    return outcome


def _static_ability(outcome: SentenceOutcome) -> StaticAbility:
    outcome = _as_ability(outcome)
    ability = outcome.ability
    if not isinstance(ability, StaticAbility):
        raise TypeError(f"expected StaticAbility, got {type(ability)}")
    return ability


def _activated_ability(outcome: SentenceOutcome) -> ActivatedAbility:
    outcome = _as_ability(outcome)
    ability = outcome.ability
    if not isinstance(ability, ActivatedAbility):
        raise TypeError(f"expected ActivatedAbility, got {type(ability)}")
    return ability


def _activated_effect(tid: str) -> Any:
    return _activated_ability(_match_outcome(tid)).effect


def _seq_steps_as_atoms(seq: Seq) -> tuple[Atom, ...]:
    atoms: list[Atom] = []
    for step in seq.steps:
        if not isinstance(step, Atom):
            raise TypeError(f"expected Atom step, got {type(step)}")
        atoms.append(step)
    return tuple(atoms)


def _as_fatom(value: Any) -> FAtom:
    if not isinstance(value, FAtom):
        raise TypeError(f"expected FAtom, got {type(value)}")
    return value


def _as_cost_loyalty(value: Any) -> CostLoyalty:
    if not isinstance(value, CostLoyalty):
        raise TypeError(f"expected CostLoyalty, got {type(value)}")
    return value


def _as_atom(effect: Any) -> Atom:
    if not isinstance(effect, Atom):
        raise TypeError(f"expected Atom, got {type(effect)}")
    return effect


def _as_seq(effect: Any) -> Seq:
    if not isinstance(effect, Seq):
        raise TypeError(f"expected Seq, got {type(effect)}")
    return effect


def _pairs(atom: Atom) -> dict[str, Any]:
    """AtomArgs pairs as a dict for assertion convenience."""
    return dict(atom.args.pairs)


def _pt_delta(atom: Atom) -> tuple[tuple[str, int], tuple[str, int]]:
    """Return ((power dir, power mag), (tough dir, tough mag)) for MODIFY_PT."""
    d = _pairs(atom)
    power = d["power"]
    tough = d["toughness"]
    return (
        (power.direction.name, int(power.magnitude.value)),
        (tough.direction.name, int(tough.magnitude.value)),
    )


def _cost_part_types(ability: ActivatedAbility) -> tuple[type, ...]:
    return tuple(type(p) for p in ability.cost.parts)


def _find_fnot(node: Any, depth: int = 0) -> Any:
    """Recursively find the first FNot in a filter tree (returns None if none)."""
    if isinstance(node, FNot):
        return node
    if isinstance(node, (FAnd, FOr)):
        for child in node.children:
            found = _find_fnot(child, depth + 1)
            if found is not None:
                return found
    return None


def _find_atom(node: Any, pred: FAtomPred) -> Any:
    """Recursively find the first FAtom with the given predicate."""
    if isinstance(node, FAtom):
        if node.pred is pred:
            return node
        return None
    if isinstance(node, FNot):
        return _find_atom(node.inner, pred)
    if isinstance(node, (FAnd, FOr)):
        for child in node.children:
            found = _find_atom(child, pred)
            if found is not None:
                return found
    return None


# ---------------------------------------------------------------------------
# Test: Template Inventory
# ---------------------------------------------------------------------------


class TestB5cInventory(unittest.TestCase):
    """Verify the B5c template collection is well-formed."""

    def test_87_templates(self) -> None:
        self.assertEqual(len(TEMPLATES), 87)

    def test_unique_tids(self) -> None:
        tids = [t.tid for t in TEMPLATES]
        self.assertEqual(len(tids), len(set(tids)), "duplicate tid found")

    def test_all_bucket_b5c(self) -> None:
        for t in TEMPLATES:
            self.assertEqual(t.bucket, "B5c", f"{t.tid} has bucket {t.bucket}")

    def test_all_priority_100(self) -> None:
        for t in TEMPLATES:
            self.assertEqual(t.priority, 100, f"{t.tid} has priority {t.priority}")

    def test_registry_accepts_all(self) -> None:
        self.assertEqual(len(_REG), 87)

    def test_uncovered_has_1_row(self) -> None:
        self.assertEqual(len(UNCOVERED), 1)


# ---------------------------------------------------------------------------
# Test: Shape Table Integrity
# ---------------------------------------------------------------------------


class TestB5cShapeTable(unittest.TestCase):
    """Verify the embedded 91-shape table is consistent."""

    def test_91_entries(self) -> None:
        self.assertEqual(len(SHAPES), 91)

    def test_unique_sentences(self) -> None:
        sents = [s[0] for s in SHAPES]
        self.assertEqual(len(sents), len(set(sents)), "duplicate sentence in SHAPES")

    def test_category_counts(self) -> None:
        covered = sum(1 for s in SHAPES if s[1] == "COVERED")
        uncov = sum(1 for s in SHAPES if s[1] == "UNCOV")
        rr = sum(1 for s in SHAPES if s[1] == "RR")
        self.assertEqual(covered, 90, f"COVERED count {covered} != 90")
        self.assertEqual(uncov, 1, f"UNCOV count {uncov} != 1")
        self.assertEqual(rr, 0, f"B5c has no rule-reminder shapes, got {rr}")

    def test_covered_tids_valid_and_unique_87(self) -> None:
        covered_tids = [s[2] for s in SHAPES if s[1] == "COVERED"]
        unique_tids = set(covered_tids)
        self.assertEqual(
            len(unique_tids),
            87,
            f"expected 87 unique tids, got {len(unique_tids)}",
        )
        for tid in unique_tids:
            self.assertTrue(tid.startswith("B5c-"), f"bad tid: {tid}")

    def test_uncov_have_empty_tid(self) -> None:
        for sent, cat, tid in SHAPES:
            if cat == "UNCOV":
                self.assertEqual(
                    tid,
                    "",
                    f"shape with cat={cat} has tid={tid!r}: {sent[:40]}",
                )

    def test_covered_have_nonempty_tid(self) -> None:
        for sent, cat, tid in SHAPES:
            if cat == "COVERED":
                self.assertNotEqual(
                    tid,
                    "",
                    f"covered shape has empty tid: {sent[:40]}",
                )

    def test_gain_life_tid_covers_two_sentences(self) -> None:
        """B5c-bullet-gain-life is the one tid covering two concrete sentences."""
        rows = [s[0] for s in SHAPES if s[2] == "B5c-bullet-gain-life"]
        self.assertEqual(len(rows), 2)
        self.assertIn("• You gain 3 life.", rows)
        self.assertIn("• You gain 4 life.", rows)


# ---------------------------------------------------------------------------
# Test: PC-3 Matching
# ---------------------------------------------------------------------------


class TestB5cMatching(unittest.TestCase):
    """PC-3: every B5c sentence fullmatches at most one template."""

    def test_pc3_at_most_one_match(self) -> None:
        for sent, _cat, _ in SHAPES:
            matches = _REG.match(sent)
            self.assertLessEqual(
                len(matches),
                1,
                f"PC-3 violated ({len(matches)} matches): {sent[:60]}",
            )

    def test_covered_shapes_match_exactly_one(self) -> None:
        for sent, cat, expected_tid in SHAPES:
            if cat != "COVERED":
                continue
            matches = _REG.match(sent)
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
            matches = _REG.match(sent)
            self.assertEqual(
                len(matches),
                0,
                f"unexpected match for uncovered: {sent[:60]}",
            )


# ---------------------------------------------------------------------------
# Test: Outcome Kind per template
# ---------------------------------------------------------------------------


class TestB5cOutcomeKind(unittest.TestCase):
    """Every covered template produces the expected outcome kind."""

    def test_kind_table_is_complete(self) -> None:
        covered_tids = {t for _s, c, t in SHAPES if c == "COVERED"}
        self.assertEqual(set(EXPECTED_KIND_BY_TID), covered_tids)
        self.assertEqual(len(EXPECTED_KIND_BY_TID), 87)

    def test_all_kinds_match(self) -> None:
        for tid, expected in EXPECTED_KIND_BY_TID.items():
            outcome = _match_outcome(tid)
            self.assertEqual(
                _kind_of(outcome),
                expected,
                f"{tid}: got kind {_kind_of(outcome)}, expected {expected}",
            )

    def test_kind_counts(self) -> None:
        kinds = [k for k in EXPECTED_KIND_BY_TID.values()]
        self.assertEqual(kinds.count("effect"), 28)
        self.assertEqual(kinds.count("keyword"), 5)
        self.assertEqual(kinds.count("static"), 1)
        self.assertEqual(kinds.count("activated"), 51)
        self.assertEqual(kinds.count("ability:EtBState"), 1)
        self.assertEqual(kinds.count("ability:CostModifier"), 1)


# ---------------------------------------------------------------------------
# Test: IR Structure (per family)
# ---------------------------------------------------------------------------


class TestB5cIrStructure(unittest.TestCase):
    """Assert the concrete grammar nodes built for each template family."""

    # -- simple effect atoms ---------------------------------------------

    def test_turn_to_slag(self) -> None:
        atom = _as_atom(_as_effect(_match_outcome("B5c-turn-to-slag")).effect)
        self.assertIs(atom.verb, Verb.DEAL_DAMAGE)
        amount = _pairs(atom)["amount"]
        self.assertIsInstance(amount, QConst)
        self.assertEqual(amount.value, 5)

    def test_geyser_dmg(self) -> None:
        atom = _as_atom(_as_effect(_match_outcome("B5c-geyser-dmg")).effect)
        self.assertIs(atom.verb, Verb.DEAL_DAMAGE)
        self.assertIsInstance(_pairs(atom)["amount"], QX)

    def test_salvo_dmg(self) -> None:
        atom = _as_atom(_as_effect(_match_outcome("B5c-salvo-dmg")).effect)
        self.assertIs(atom.verb, Verb.DEAL_DAMAGE)
        amount = _pairs(atom)["amount"]
        self.assertIsInstance(amount, QConst)
        self.assertEqual(amount.value, 6)
        target = _pairs(atom)["target"]
        self.assertIsInstance(target, Selector)
        self.assertIs(target.mode, SelectorMode.TARGET)  # C17 (round 8)
        self.assertEqual(target.count, QAtMost(2))
        self.assertIsInstance(target.filter, FOr)
        names = {c.string_value for c in target.filter.children if isinstance(c, FAtom)}
        self.assertEqual(names, {"Creature", "Planeswalker"})

    def test_untap_lands(self) -> None:
        atom = _as_atom(_as_effect(_match_outcome("B5c-untap-lands")).effect)
        self.assertIs(atom.verb, Verb.UNTAP)
        target = _pairs(atom)["target"]
        self.assertIs(target.mode, SelectorMode.CHOOSE)
        self.assertEqual(target.count, QConst(4))
        self.assertEqual(
            target.filter, FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land")
        )

    def test_then_return_is(self) -> None:
        atom = _as_atom(_as_effect(_match_outcome("B5c-then-return-is")).effect)
        self.assertIs(atom.verb, Verb.MOVE_ZONE)
        d = _pairs(atom)
        cards = d["cards"]
        self.assertIsInstance(cards, Selector)
        self.assertIs(cards.zone.kind, ZoneKind.GRAVEYARD)
        self.assertIs(cards.zone.controller, ControllerRef.YOU)
        self.assertIsInstance(cards.filter, FOr)
        dest = d["destination"]
        self.assertIs(dest.kind, ZoneKind.HAND)
        self.assertIs(dest.controller, ControllerRef.YOU)

    def test_pt_swap(self) -> None:
        seq = _as_seq(_as_effect(_match_outcome("B5c-pt-swap")).effect)
        self.assertEqual(len(seq.steps), 2)
        steps = _seq_steps_as_atoms(seq)
        self.assertIs(steps[0].verb, Verb.MODIFY_PT)
        self.assertIs(steps[1].verb, Verb.MODIFY_PT)
        self.assertEqual(_pt_delta(steps[0]), (("INCREASE", 0), ("INCREASE", 2)))
        self.assertEqual(_pt_delta(steps[1]), (("DECREASE", 2), ("DECREASE", 0)))
        # Both steps end-of-turn scoped.
        for step in steps:
            self.assertIsInstance(_pairs(step)["duration"], DurationEot)

    # -- static ---------------------------------------------------------

    def test_zombies_pt(self) -> None:
        outcome = _match_outcome("B5c-zombies-pt")
        ability = _static_ability(outcome)
        atom = _as_atom(ability.effect)
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        self.assertEqual(_pt_delta(atom), (("INCREASE", 1), ("INCREASE", 0)))
        target = _pairs(atom)["target"]
        self.assertIs(target.mode, SelectorMode.ALL)
        fand = target.filter
        self.assertIsInstance(fand, FAnd)
        self.assertIsNotNone(_find_atom(fand, FAtomPred.SUBTYPE_EQ))
        self.assertIsNotNone(_find_atom(fand, FAtomPred.CONTROLLER_IS))

    # -- ETB state ------------------------------------------------------

    def test_etb_soul_counter(self) -> None:
        ability = _as_ability(_match_outcome("B5c-etb-soul-counter")).ability
        if not isinstance(ability, EtBState):
            raise TypeError(f"expected EtBState, got {type(ability)}")
        self.assertEqual(ability.initial_counters, ((CounterKind.SOUL, QConst(1)),))

    # -- rule reminders -------------------------------------------------

    def test_remind_keywords(self) -> None:
        for tid, expected_kw in EXPECTED_REMIND_KEYWORD.items():
            outcome = _as_keyword(_match_outcome(tid))
            self.assertIs(outcome.keyword, expected_kw, f"{tid}: wrong keyword")

    def test_remind_protection_param(self) -> None:
        """protection from multicolored carries a COLOR_COUNT_GE 2 param."""
        outcome = _as_keyword(_match_outcome("B5c-remind-vigilance-protection"))
        self.assertEqual(len(outcome.params), 1)
        param = _as_fatom(outcome.params[0])
        self.assertIs(param.pred, FAtomPred.COLOR_COUNT_GE)
        self.assertEqual(param.count, QConst(2))

    def test_remind_plain_keywords_no_params(self) -> None:
        for tid in (
            "B5c-remind-trample",
            "B5c-remind-vigilance",
            "B5c-remind-vigilance-lifelink",
            "B5c-remind-vigilance-reach-trample",
        ):
            outcome = _as_keyword(_match_outcome(tid))
            self.assertEqual(len(outcome.params), 0, f"{tid}: unexpected params")

    # -- loyalty wrappers ----------------------------------------------

    def test_all_loyalty_deltas(self) -> None:
        for tid, expected in EXPECTED_LOYALTY_DELTA.items():
            ability = _activated_ability(_match_outcome(tid))
            first = _as_cost_loyalty(ability.cost.parts[0])
            self.assertEqual(
                first.delta, expected, f"{tid}: delta {first.delta} != {expected}"
            )

    def test_loyalty_chandra_dmg_any(self) -> None:
        atom = _as_atom(_activated_effect("B5c-loyalty-chandra-dmg-any"))
        self.assertIs(atom.verb, Verb.DEAL_DAMAGE)
        amount = _pairs(atom)["amount"]
        self.assertIsInstance(amount, QConst)
        self.assertEqual(amount.value, 2)

    def test_loyalty_ugin_dmg(self) -> None:
        atom = _as_atom(_activated_effect("B5c-loyalty-ugin-dmg"))
        amount = _pairs(atom)["amount"]
        self.assertIsInstance(amount, QConst)
        self.assertEqual(amount.value, 3)

    def test_loyalty_exile_color_cmc_ux(self) -> None:
        """Ugin [−X]: dynamic loyalty cost, EXILE each colored CMC<=X permanent."""
        ability = _activated_ability(_match_outcome("B5c-loyalty-exile-color-cmc-ux"))
        cost = _as_cost_loyalty(ability.cost.parts[0])
        self.assertIsInstance(cost.delta, QX, "dynamic delta must be QX")
        atom = _as_atom(ability.effect)
        self.assertIs(atom.verb, Verb.EXILE)
        sel = _pairs(atom)["target"]
        self.assertIsInstance(sel.count, QUnbounded)
        self.assertIs(sel.mode, SelectorMode.ALL)
        self.assertIsInstance(sel.filter, FAnd)
        children = sel.filter.children
        self.assertEqual(len(children), 2)
        self.assertIs(children[0].pred, FAtomPred.CMC_LE)
        self.assertIsInstance(children[0].count, QX)
        self.assertIs(children[1].pred, FAtomPred.COLOR_COUNT_GE)
        self.assertEqual(children[1].count, QConst(1))
        self.assertIs(sel.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(sel.zone.controller, ControllerRef.ANY)

    def test_loyalty_gain_draw_put_permanent_filter(self) -> None:
        """Ugin [−10]: put-up-to-seven selector filters permanent cards only."""
        seq = _as_seq(_activated_effect("B5c-loyalty-gain-draw-put"))
        steps = _seq_steps_as_atoms(seq)
        atom = steps[2]
        self.assertIs(atom.verb, Verb.MOVE_ZONE)
        sel = _pairs(atom)["cards"]
        expected = FOr(
            (
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Enchantment"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Artifact"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Land"),
                FAtom(pred=FAtomPred.TYPE_EQ, string_value="Planeswalker"),
            )
        )
        self.assertEqual(sel.filter, expected)
        self.assertIs(sel.zone.kind, ZoneKind.HAND)
        self.assertIs(sel.zone.controller, ControllerRef.YOU)

    def test_loyalty_draw_discard_seq(self) -> None:
        seq = _as_seq(_activated_effect("B5c-loyalty-draw-discard"))
        self.assertEqual(
            [s.verb for s in _seq_steps_as_atoms(seq)], [Verb.DRAW, Verb.DISCARD]
        )

    def test_loyalty_create_token(self) -> None:
        atom = _as_atom(_activated_effect("B5c-loyalty-create-token"))
        self.assertIs(atom.verb, Verb.CREATE_TOKEN)
        d = _pairs(atom)
        self.assertEqual(d["count"], QConst(1))
        spec = d["tokens"]
        self.assertIsInstance(spec, TokenSpec)
        self.assertEqual(spec.name, "Beast")
        self.assertEqual(spec.subtypes, ("Beast",))
        self.assertEqual(spec.power, QConst(3))
        self.assertEqual(spec.toughness, QConst(3))

    def test_loyalty_pt_trample_seq(self) -> None:
        seq = _as_seq(_activated_effect("B5c-loyalty-pt-trample"))
        self.assertEqual(len(seq.steps), 2)
        steps = _seq_steps_as_atoms(seq)
        self.assertIs(steps[0].verb, Verb.MODIFY_PT)
        self.assertEqual(_pt_delta(steps[0]), (("INCREASE", 3), ("INCREASE", 3)))
        self.assertIs(steps[1].verb, Verb.GRANT_ABILITY)
        granted = _pairs(steps[1])["ability"]
        self.assertIsInstance(granted, KeywordAbility)
        self.assertIs(granted.keyword, Keyword.TRAMPLE)

    def test_loyalty_creatures_pt_flying_seq(self) -> None:
        seq = _as_seq(_activated_effect("B5c-loyalty-creatures-pt-flying"))
        self.assertEqual(len(seq.steps), 2)
        steps = _seq_steps_as_atoms(seq)
        self.assertIs(steps[0].verb, Verb.MODIFY_PT)
        self.assertEqual(_pt_delta(steps[0]), (("INCREASE", 2), ("INCREASE", 2)))
        target = _pairs(steps[0])["target"]
        self.assertIs(target.mode, SelectorMode.ALL)
        self.assertIs(steps[1].verb, Verb.GRANT_ABILITY)
        granted = _pairs(steps[1])["ability"]
        self.assertIsInstance(granted, KeywordAbility)
        self.assertIs(granted.keyword, Keyword.FLYING)

    def test_loyalty_pt_qprop(self) -> None:
        atom = _as_atom(_activated_effect("B5c-loyalty-pt-qprop"))
        self.assertIs(atom.verb, Verb.MODIFY_PT)
        power = _pairs(atom)["power"]
        self.assertIs(power.direction, PtDirection.DECREASE)
        mag = power.magnitude
        self.assertIsInstance(mag, QProp)
        self.assertEqual(mag.referent, "controller")
        self.assertIs(mag.field, QPropField.CARDS_IN_GRAVEYARD)
        self.assertIs(mag.agg, QAgg.FIRST)

    def test_loyalty_dmg_power(self) -> None:
        atom = _as_atom(_activated_effect("B5c-loyalty-dmg-power"))
        self.assertIs(atom.verb, Verb.DEAL_DAMAGE)
        amount = _pairs(atom)["amount"]
        self.assertIsInstance(amount, QProp)
        self.assertIs(amount.field, QPropField.POWER)

    def test_loyalty_lose_per_creature(self) -> None:
        atom = _as_atom(_activated_effect("B5c-loyalty-lose-per-creature"))
        self.assertIs(atom.verb, Verb.LOSE_LIFE)
        amount = _pairs(atom)["amount"]
        self.assertEqual(amount.op, QBinOp.MUL)
        self.assertEqual(amount.left, QConst(2))
        self.assertIsInstance(amount.right, QCount)
        self.assertIs(amount.right.selector.zone.kind, ZoneKind.GRAVEYARD)

    def test_loyalty_search_exile_seq(self) -> None:
        seq = _as_seq(_activated_effect("B5c-loyalty-search-exile"))
        self.assertEqual(
            [s.verb for s in _seq_steps_as_atoms(seq)],
            [Verb.SEARCH, Verb.SEARCH, Verb.SHUFFLE],
        )

    def test_loyalty_extra_turns(self) -> None:
        atom = _as_atom(_activated_effect("B5c-loyalty-extra-turns"))
        self.assertIs(atom.verb, Verb.EXTRA_TURN)

    def test_loyalty_discard_exile_top_seq(self) -> None:
        seq = _as_seq(_activated_effect("B5c-loyalty-discard-exile-top"))
        discard, exile = _seq_steps_as_atoms(seq)
        self.assertIs(discard.verb, Verb.DISCARD)
        cards = _pairs(discard)["cards"]
        self.assertIsInstance(cards.count, QUnbounded)
        self.assertIs(cards.mode, SelectorMode.ALL)
        self.assertIs(cards.zone.kind, ZoneKind.HAND)
        self.assertIs(cards.zone.controller, ControllerRef.YOU)
        self.assertIs(exile.verb, Verb.EXILE)
        target = _pairs(exile)["target"]
        self.assertIs(target.mode, SelectorMode.TARGET)
        self.assertEqual(target.count, QConst(3))
        self.assertIs(target.zone.kind, ZoneKind.LIBRARY)
        self.assertIs(target.zone.controller, ControllerRef.YOU)
        self.assertIs(target.zone.position, ZonePosition.TOP)

    def test_loyalty_top_owner_library(self) -> None:
        atom = _as_atom(_activated_effect("B5c-loyalty-top-owner-library"))
        self.assertIs(atom.verb, Verb.MOVE_ZONE)
        d = _pairs(atom)
        cards = d["cards"]
        self.assertIs(cards.mode, SelectorMode.TARGET)
        self.assertEqual(cards.count, QConst(1))
        self.assertIsInstance(cards.filter, FAtom)
        self.assertEqual(_as_fatom(cards.filter).string_value, "Creature")
        self.assertIs(cards.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(cards.zone.controller, ControllerRef.ANY)
        dest = d["destination"]
        self.assertIs(dest.kind, ZoneKind.LIBRARY)
        self.assertIs(dest.controller, ControllerRef.OWNER)
        self.assertIs(dest.position, ZonePosition.TOP)

    def test_loyalty_may_cast_graveyard_optional(self) -> None:
        ability = _activated_ability(_match_outcome("B5c-loyalty-may-cast-graveyard"))
        effect = ability.effect
        if not isinstance(effect, OptionalEffect):
            raise TypeError(f"expected OptionalEffect, got {type(effect)}")
        atom = _as_atom(effect.inner)
        self.assertIs(atom.verb, Verb.CAST)
        source = _pairs(atom)["source"]
        self.assertIs(source.mode, SelectorMode.TARGET)
        self.assertEqual(source.count, QConst(1))
        self.assertIs(source.zone.kind, ZoneKind.GRAVEYARD)
        self.assertIs(source.zone.controller, ControllerRef.YOU)
        # "red instant or sorcery" guard: COLOR_HAS red AND (Instant OR Sorcery).
        self.assertIsInstance(source.filter, FAnd)
        color = _as_fatom(_find_atom(source.filter, FAtomPred.COLOR_HAS))
        self.assertEqual(color.color, "R")
        or_children = [c for c in source.filter.children if isinstance(c, FOr)]
        self.assertEqual(len(or_children), 1)
        names = {
            c.string_value for c in or_children[0].children if isinstance(c, FAtom)
        }
        self.assertEqual(names, {"Instant", "Sorcery"})

    # -- Round 5 (grammar round 4 shapes) ------------------------------

    def test_loyalty_basri_attack_counter(self) -> None:
        """Basri [−1]: GRANT_ABILITY(DurationEot) of a TriggeredAbility."""
        ability = _activated_ability(_match_outcome("B5c-loyalty-basri-attack-counter"))
        delta = _as_cost_loyalty(ability.cost.parts[0]).delta
        self.assertEqual(delta, -1)
        grant = _as_atom(ability.effect)
        self.assertIs(grant.verb, Verb.GRANT_ABILITY)
        target = _pairs(grant)["target"]
        self.assertIs(target.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(target.zone.controller, ControllerRef.YOU)
        self.assertIs(target.filter.pred, FAtomPred.IS_SOURCE)
        self.assertIsInstance(grant.args.get("duration"), DurationEot)
        triggered = grant.args.get("ability")
        if not isinstance(triggered, TriggeredAbility):
            raise TypeError(f"expected TriggeredAbility, got {type(triggered)}")
        event = triggered.event
        if not isinstance(event, DeclareAttackersEvent):
            raise TypeError(f"expected DeclareAttackersEvent, got {type(event)}")
        if not isinstance(event.filter, FAtom):
            raise TypeError(f"expected FAtom filter, got {type(event.filter)}")
        self.assertIs(event.filter.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(event.filter.string_value, "Creature")
        self.assertIsNone(triggered.condition)
        put = _as_atom(triggered.effect)
        self.assertIs(put.verb, Verb.PUT_COUNTER)
        self.assertIs(put.args.get("counter_kind"), CounterKind.PLUS_1_PLUS_1)
        count = _pairs(put)["count"]
        self.assertIsInstance(count, QConst)
        self.assertEqual(count.value, 1)
        put_target = _pairs(put)["target"]
        self.assertIsInstance(put_target, Selector)
        self.assertEqual(put_target.referent, "event")
        self.assertIs(put_target.mode, SelectorMode.CHOOSE)

    # -- cost wrappers -------------------------------------------------

    def test_all_cost_part_types(self) -> None:
        for tid, expected in EXPECTED_COST_PARTS.items():
            ability = _activated_ability(_match_outcome(tid))
            self.assertEqual(
                _cost_part_types(ability),
                expected,
                f"{tid}: cost parts {_cost_part_types(ability)} != {expected}",
            )

    def test_cost_shrine_dmg_amount_is_qcount(self) -> None:
        atom = _as_atom(_activated_effect("B5c-cost-shrine-dmg"))
        self.assertIs(atom.verb, Verb.DEAL_DAMAGE)
        amount = _pairs(atom)["amount"]
        self.assertIsInstance(amount, QCount)

    def test_cost_page_draw_put_counter_target_is_self(self) -> None:
        ability = _activated_ability(_match_outcome("B5c-cost-page-draw"))
        put = next(p for p in ability.cost.parts if isinstance(p, CostPutCounter))
        # The page counter lands on the source permanent itself.
        self.assertIsNotNone(_find_atom(put.target.filter, FAtomPred.IS_SOURCE))

    def test_shrine_cost_reduction_census_is_type_eq_not_name_eq(self) -> None:
        # C1 batch (2026-10-02): the "for each Shrine you control" census
        # must be the type-line word pred (TYPE_EQ "Shrine", the audited
        # sanctum_of_all_search_fire idiom). NAME_EQ is the closed-card-
        # name pred and counted 0 on every board, silently zeroing the
        # discount (the sanctum_tranquil_light STOP, 22c).
        outcome: Any = _match_outcome("B5c-shrine-activation-cost")
        modifier: Any = outcome.ability
        self.assertIsInstance(modifier, CostModifier)
        census: Any = modifier.delta.amount.right  # QBin(MUL, {N}, QCount)
        self.assertIsInstance(census, QCount)
        atom = _find_atom(census.selector.filter, FAtomPred.TYPE_EQ)
        self.assertIsNotNone(atom)
        self.assertEqual(atom.string_value, "Shrine")
        self.assertIsNone(_find_atom(census.selector.filter, FAtomPred.NAME_EQ))

    # -- bullets -------------------------------------------------------

    def test_bullet_draw(self) -> None:
        atom = _as_atom(_as_effect(_match_outcome("B5c-bullet-draw")).effect)
        self.assertIs(atom.verb, Verb.DRAW)
        self.assertEqual(_pairs(atom)["amount"], QConst(1))
        self.assertIs(_pairs(atom)["controller"], ControllerRef.YOU)

    def test_bullet_draw_three(self) -> None:
        atom = _as_atom(_as_effect(_match_outcome("B5c-bullet-draw-three")).effect)
        self.assertIs(atom.verb, Verb.DRAW)
        self.assertEqual(_pairs(atom)["amount"], QConst(3))

    def test_bullet_target_draw(self) -> None:
        atom = _as_atom(_as_effect(_match_outcome("B5c-bullet-target-draw")).effect)
        self.assertIs(atom.verb, Verb.DRAW)
        self.assertEqual(_pairs(atom)["amount"], QConst(1))
        self.assertIs(_pairs(atom)["controller"], ControllerRef.TARGET_PLAYER)

    def test_bullet_gain_life_values(self) -> None:
        for sent, value in (("• You gain 3 life.", 3), ("• You gain 4 life.", 4)):
            matches = _REG.match(sent)
            atom = _as_atom(_as_effect(matches[0].outcome).effect)
            self.assertIs(atom.verb, Verb.GAIN_LIFE)
            amount = _pairs(atom)["amount"]
            self.assertIsInstance(amount, QConst)
            self.assertEqual(amount.value, value)

    def test_bullet_counter(self) -> None:
        for tid in ("B5c-bullet-counter-ability", "B5c-bullet-counter-spell"):
            atom = _as_atom(_as_effect(_match_outcome(tid)).effect)
            self.assertIs(atom.verb, Verb.COUNTER_SPELL)
            self.assertIs(_pairs(atom)["target"].zone.kind, ZoneKind.STACK)

    def test_bullet_create_token(self) -> None:
        atom = _as_atom(_as_effect(_match_outcome("B5c-bullet-create-token")).effect)
        self.assertIs(atom.verb, Verb.CREATE_TOKEN)
        spec = _pairs(atom)["tokens"]
        self.assertIsInstance(spec, TokenSpec)
        self.assertEqual(spec.subtypes, ("Beast",))
        self.assertEqual(spec.power, QConst(3))
        self.assertEqual(spec.toughness, QConst(3))

    def test_bullet_cant_block_is_prevent_effect(self) -> None:
        """C5: 'Creatures without flying can't block this turn' is a real
        PREVENT_EFFECT — universal condition, DeclareBlockersEvent whose
        blocker-side filter names the creature-without-flying set (the
        Shacklegeist FNot(FLYING) idiom on the blocker side), DurationEot,
        and NO target role (PREVENT_EFFECT carries none)."""
        atom = _as_atom(_as_effect(_match_outcome("B5c-bullet-cant-block")).effect)
        self.assertIs(atom.verb, Verb.PREVENT_EFFECT)
        pairs = _pairs(atom)
        self.assertEqual(pairs["condition"], FAnd(children=()))
        event = pairs["event"]
        self.assertIsInstance(event, DeclareBlockersEvent)
        self.assertIsNotNone(_find_fnot(event.filter), "expected FNot(FLYING) guard")
        inner = _find_fnot(event.filter).inner
        self.assertIsInstance(inner, FAtom)
        self.assertIs(inner.pred, FAtomPred.KEYWORD_HAS)
        self.assertEqual(
            event.filter.children[0],
            FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature"),
        )
        self.assertIsInstance(pairs["duration"], DurationEot)
        self.assertNotIn("target", pairs)

    def test_bullet_destroy_zones(self) -> None:
        for tid, subtype in (
            ("B5c-bullet-destroy-artifact", "Artifact"),
            ("B5c-bullet-destroy-enchantment", "Enchantment"),
        ):
            atom = _as_atom(_as_effect(_match_outcome(tid)).effect)
            self.assertIs(atom.verb, Verb.DESTROY)
            target = _pairs(atom)["target"]
            self.assertIs(target.zone.kind, ZoneKind.BATTLEFIELD)
            self.assertEqual(
                target.filter, FAtom(pred=FAtomPred.TYPE_EQ, string_value=subtype)
            )

    def test_bullet_exile_graveyard(self) -> None:
        atom = _as_atom(_as_effect(_match_outcome("B5c-bullet-exile-graveyard")).effect)
        self.assertIs(atom.verb, Verb.EXILE)
        self.assertIs(_pairs(atom)["target"].zone.kind, ZoneKind.GRAVEYARD)

    def test_bullet_return_nonland_hand(self) -> None:
        atom = _as_atom(
            _as_effect(_match_outcome("B5c-bullet-return-nonland-hand")).effect
        )
        self.assertIs(atom.verb, Verb.MOVE_ZONE)
        d = _pairs(atom)
        cards = d["cards"]
        self.assertIs(cards.mode, SelectorMode.TARGET)
        self.assertEqual(cards.count, QConst(1))
        self.assertIsInstance(cards.filter, FNot)
        inner = _as_fatom(cards.filter.inner)
        self.assertIs(inner.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(inner.string_value, "Land")
        self.assertIs(cards.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(cards.zone.controller, ControllerRef.ANY)
        dest = d["destination"]
        self.assertIs(dest.kind, ZoneKind.HAND)
        self.assertIs(dest.controller, ControllerRef.OWNER)

    def test_bullet_return_two_creatures_hand(self) -> None:
        atom = _as_atom(
            _as_effect(_match_outcome("B5c-bullet-return-two-creatures-hand")).effect
        )
        self.assertIs(atom.verb, Verb.MOVE_ZONE)
        d = _pairs(atom)
        cards = d["cards"]
        self.assertIs(cards.mode, SelectorMode.TARGET)  # C17 (round 8)
        self.assertEqual(cards.count, QAtMost(2))
        self.assertIsInstance(cards.filter, FAtom)
        self.assertEqual(_as_fatom(cards.filter).string_value, "Creature")
        self.assertIs(cards.zone.kind, ZoneKind.BATTLEFIELD)
        self.assertIs(cards.zone.controller, ControllerRef.ANY)
        dest = d["destination"]
        self.assertIs(dest.kind, ZoneKind.HAND)
        self.assertIs(dest.controller, ControllerRef.OWNER)

    # -- grammar round-7 batch (doc 2026-09-28/03 §3 R7-A) ---------------

    def test_untap_that_creature(self) -> None:
        atom = _as_atom(_as_effect(_match_outcome("B5c-untap-that-creature")).effect)
        self.assertIs(atom.verb, Verb.UNTAP)
        target = _pairs(atom)["target"]
        self.assertIsInstance(target, Selector)
        # C2 convention: referent selectors pin CHOOSE + QConst(1) + neutral zone
        self.assertIs(target.mode, SelectorMode.CHOOSE)
        self.assertEqual(target.count, QConst(1))
        self.assertEqual(target.referent, "target")
        self.assertIs(target.zone.kind, ZoneKind.ANY)
        self.assertEqual(
            target.filter, FAtom(pred=FAtomPred.TYPE_EQ, string_value="Creature")
        )

    def test_then_it_fights(self) -> None:
        atom = _as_atom(_as_effect(_match_outcome("B5c-then-it-fights")).effect)
        self.assertIs(atom.verb, Verb.FIGHT)
        target = _pairs(atom)["target"]
        self.assertIsInstance(target, Selector)
        # C15: resolution-time "up to one" = CHOOSE + QConst(1) (0..1),
        # never TARGET — the C-1 collapse fix.
        self.assertIs(target.mode, SelectorMode.CHOOSE)
        self.assertEqual(target.count, QConst(1))
        self.assertIs(target.zone.kind, ZoneKind.BATTLEFIELD)
        children = [c for c in target.filter.children if isinstance(c, (FAtom, FNot))]
        self.assertEqual(len(children), 2)


# ---------------------------------------------------------------------------
# Test: Canonical Stability
# ---------------------------------------------------------------------------


class TestB5cCanonicalStability(unittest.TestCase):
    """Building each covered outcome twice yields identical canonical_json."""

    def test_all_covered_shapes_stable(self) -> None:
        seen: set[str] = set()
        for sent, cat, tid in SHAPES:
            if cat != "COVERED":
                continue
            matches = _REG.match(sent)
            self.assertEqual(len(matches), 1)
            canon1 = canonical_json(_inner_node(matches[0].outcome))
            # Rebuild from a fresh match.
            matches2 = _REG.match(sent)
            canon2 = canonical_json(_inner_node(matches2[0].outcome))
            self.assertEqual(
                canon1,
                canon2,
                f"canonical instability for {tid} ({sent[:40]})",
            )
            seen.add(tid)
        self.assertEqual(
            len(seen),
            87,
            f"only {len(seen)} unique tids tested, expected 87",
        )


# ---------------------------------------------------------------------------
# Test: Optional B5c.json Cross-Check
# ---------------------------------------------------------------------------


class TestB5cJsonCrossCheck(unittest.TestCase):
    """Cross-check the embedded SHAPES table against the source JSON.

    Skipped if B5c.json is not present (it lives in /tmp, not the repo).
    """

    B5C_PATH = "/tmp/opencode/phase1_buckets/B5c.json"

    @classmethod
    @unittest.skipUnless(
        os.path.exists(B5C_PATH),
        f"B5c.json not found at {B5C_PATH}",
    )
    def setUpClass(cls) -> None:
        with open(cls.B5C_PATH) as f:
            cls.json_data: dict[str, list[list[str]]] = json.load(f)

    def test_90_normalized_keys(self) -> None:
        self.assertEqual(len(self.json_data), 90)

    def test_occurrence_counts(self) -> None:
        occ = sum(len(v) for v in self.json_data.values())
        sents = {s for v in self.json_data.values() for _c, s in v}
        self.assertEqual(occ, 100)
        self.assertEqual(len(sents), 91)

    def test_all_json_sentences_in_table(self) -> None:
        """Every distinct sentence in B5c.json must appear in SHAPES."""
        table_sents = {s[0] for s in SHAPES}
        json_sents = {s for v in self.json_data.values() for _c, s in v}
        self.assertEqual(json_sents, table_sents)

    def test_uncovered_keys_match_module(self) -> None:
        """JSON keys with zero template matches == module UNCOVERED keys."""
        zero_keys: set[str] = set()
        for key, pairs in self.json_data.items():
            matched = any(_REG.match(sent) for _c, sent in pairs)
            if not matched:
                zero_keys.add(key)
        self.assertEqual(zero_keys, {row[0] for row in UNCOVERED})

    def test_covered_key_count(self) -> None:
        covered = {
            k
            for k, pairs in self.json_data.items()
            if any(_REG.match(sent) for _c, sent in pairs)
        }
        self.assertEqual(len(covered), 89)


class TestB5cRound7BTopUps(unittest.TestCase):
    """Structural assertions for the R7-B top-up rows (doc 2026-09-28/03 §3
    B-table); uses the module's SHAPES-driven _match_outcome helper."""

    def test_flip_cost_activation(self) -> None:
        """B5c-flip-cost: ActivatedAbility Cost(Tap+Life 3) + role-less
        Verb.FLIP_COIN atom (r3b vocabulary)."""
        ability = _activated_ability(_match_outcome("B5c-flip-cost"))
        tap, life = ability.cost.parts
        assert isinstance(tap, CostTap)
        assert isinstance(life, CostLife)
        self.assertEqual(life.amount, QConst(3))
        atom = _as_atom(ability.effect)
        self.assertIs(atom.verb, Verb.FLIP_COIN)
        self.assertEqual(len(atom.args.pairs), 0)

    def test_then_if_lands_untap(self) -> None:
        """Fabled Passage s2: Conditional(CONTROLLER_COUNT_GE(Land,4)) ->
        UNTAP(referent='result' — verified against the landed Fabled Passage
        golden: s1 is a SEARCH with no TARGET selector, so 'that land'
        binds the R7-1 result register, NOT the doc sketch's 'target')."""
        cond = _as_effect(_match_outcome("B5c-then-if-lands-untap")).effect
        assert isinstance(cond, Conditional)
        pred = cond.pred
        assert isinstance(pred, FAtom)
        self.assertIs(pred.pred, FAtomPred.CONTROLLER_COUNT_GE)
        self.assertEqual(pred.count, QConst(4))
        inner = pred.inner_filter
        assert isinstance(inner, FAtom)
        self.assertIs(inner.pred, FAtomPred.TYPE_EQ)
        self.assertEqual(inner.string_value, "Land")
        self.assertIsNone(cond.else_effect)
        atom = _as_atom(cond.then_effect)
        self.assertIs(atom.verb, Verb.UNTAP)
        target = _pairs(atom)["target"]
        assert isinstance(target, Selector)
        # C2 referent-selector pin: CHOOSE + QConst(1) + neutral zone
        self.assertIs(target.mode, SelectorMode.CHOOSE)
        self.assertEqual(target.count, QConst(1))
        self.assertEqual(target.referent, "result")
        self.assertIs(target.zone.kind, ZoneKind.ANY)

    def test_damage_equal_power(self) -> None:
        """Hunter's Edge s2: DEAL_DAMAGE target = new TARGET creature-you-
        dont-control; amount = QProp("target", POWER) (the dealer is the
        referent, DEAL_DAMAGE has no source role — r8 canonical)."""
        atom = _as_atom(_as_effect(_match_outcome("B5c-damage-equal-power")).effect)
        self.assertIs(atom.verb, Verb.DEAL_DAMAGE)
        d = _pairs(atom)
        target = d["target"]
        assert isinstance(target, Selector)
        self.assertIs(target.mode, SelectorMode.TARGET)
        self.assertEqual(target.count, QConst(1))
        amount = d["amount"]
        assert isinstance(amount, QProp)
        self.assertEqual(amount.referent, "target")
        self.assertIs(amount.field, QPropField.POWER)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Round 9-B structural pins (doc 2026-09-28/11 §9-B rows 12-13)
# ---------------------------------------------------------------------------


class TestB5cRound9B(unittest.TestCase):
    """9-B: Frost Breath s2 (R9-4 untap-step prevention, IS_ANY_TARGET
    anaphora) and Subira s2 (R9-5/C22 DelayedTrigger)."""

    def test_frost_s2_untap_prevention(self) -> None:
        outcome = _match_outcome("B5c-those-no-untap-next")
        atom = _as_atom(_as_effect(outcome).effect)
        self.assertIs(atom.verb, Verb.PREVENT_EFFECT)
        pairs = dict(atom.args.pairs)
        cond = pairs["condition"]
        assert isinstance(cond, FAtom)
        self.assertIs(cond.pred, FAtomPred.IS_ANY_TARGET)
        event = pairs["event"]
        assert isinstance(event, TapStateEvent)
        self.assertIs(event.tapped, False)
        self.assertEqual(event.filter, cond)
        self.assertIs(pairs["step"], Step.UNTAP)
        dur = pairs["duration"]
        assert isinstance(dur, DurationUntilNextStep)
        self.assertIs(dur.step, Step.UNTAP)
        self.assertTrue(dur.owner_scoped)  # "THEIR controller's" next untap

    def test_frost_pair_are_bare_effects_for_the_instant_fold(self) -> None:
        """s1 and s2 are BOTH plain EffectOutcomes, so the compiler's
        instant assembly folds Seq(TAP, PREVENT) into the SpellAbility —
        s2 must NOT ship as an AbilityOutcome(StaticAbility) (that would
        bolt a stray static onto a one-shot instant)."""
        # (s1 "Tap up to two target creatures." lives in another bucket's
        # registry; the pair-level fold is verified by the pool PC-1 audit.)
        outcome = _match_outcome("B5c-those-no-untap-next")
        self.assertIsInstance(outcome, EffectOutcome)

    def test_subira_s2_delayed_trigger(self) -> None:
        outcome = _match_outcome("B5c-cost-discard-hand-delayed-draw")
        ability = _activated_ability(outcome)
        n, r, tap, discard = ability.cost.parts
        assert isinstance(n, CostManaGeneric)
        self.assertEqual(n.amount, QConst(1))
        assert isinstance(r, CostManaColor)
        self.assertEqual(r.color, "R")
        assert isinstance(tap, CostTap)
        assert isinstance(discard, CostDiscard)
        hand = discard.target
        assert isinstance(hand, Selector)
        self.assertIs(hand.mode, SelectorMode.ALL)
        self.assertIsInstance(hand.count, QUnbounded)
        self.assertEqual(hand.zone, Zone(ZoneKind.HAND, ControllerRef.YOU))
        dt = ability.effect
        assert isinstance(dt, DelayedTrigger)
        self.assertEqual(dt.duration, DurationEot())
        self.assertIsNone(dt.condition)
        event = dt.event
        assert isinstance(event, DamageDealtEvent)
        self.assertIsInstance(event.amount, QUnbounded)
        self.assertIs(event.combat, True)
        # LOSSY: damaged-recipient filter universal ("to a player" dropped,
        # b2b R8-candidate precedent)
        self.assertEqual(event.filter, FAnd(children=()))
        dealer = event.source
        assert isinstance(dealer, FAnd)
        type_a, controller_a, power_a = dealer.children
        assert isinstance(type_a, FAtom)
        assert isinstance(controller_a, FAtom)
        assert isinstance(power_a, FAtom)
        self.assertEqual(type_a.string_value, "Creature")
        self.assertIs(controller_a.pred, FAtomPred.CONTROLLER_IS)
        self.assertIs(controller_a.who, ControllerRef.YOU)
        self.assertIs(power_a.pred, FAtomPred.POWER_LE)
        self.assertEqual(power_a.count, QConst(2))
        draw = _as_atom(dt.effect)
        self.assertIs(draw.verb, Verb.DRAW)
        self.assertEqual(
            dict(draw.args.pairs),
            {"controller": ControllerRef.YOU, "amount": QConst(1)},
        )


# ---------------------------------------------------------------------------
# Round 10 structural pins (doc 2026-09-29/02 §phase-10-B row 4)
# ---------------------------------------------------------------------------


class TestB5cRound10Herald(unittest.TestCase):
    """R10: Garruk, Savage Herald [−N] — the embedded quoted ability text
    "You may have this creature assign its combat damage as though it
    weren't blocked." lands as GRANT_ABILITY over creatures you control
    of StaticAbility(OptionalEffect(Atom(DAMAGE_ASSIGN_POLICY,
    scope=AS_UNBLOCKED))), DurationEot riding the GRANT (R10-4/C28)."""

    def test_grant_structure(self) -> None:
        outcome = _match_outcome("B5c-loyalty-assign-as-unblocked")
        ability = _activated_ability(outcome)
        (cost_part,) = ability.cost.parts
        loyalty = _as_cost_loyalty(cost_part)
        self.assertEqual(loyalty.delta, -7)
        atom = _as_atom(ability.effect)
        self.assertIs(atom.verb, Verb.GRANT_ABILITY)
        pairs = _pairs(atom)
        # target: ALL creatures you control on the battlefield
        target = pairs["target"]
        assert isinstance(target, Selector)
        self.assertIs(target.mode, SelectorMode.ALL)
        self.assertIsInstance(target.count, QUnbounded)
        self.assertEqual(target.zone, Zone(ZoneKind.BATTLEFIELD, ControllerRef.YOU))
        assert isinstance(target.filter, FAnd)
        kind_a, controller_a = target.filter.children
        assert isinstance(kind_a, FAtom) and isinstance(controller_a, FAtom)
        self.assertEqual(kind_a.string_value, "Creature")
        self.assertIs(controller_a.pred, FAtomPred.CONTROLLER_IS)
        self.assertIs(controller_a.who, ControllerRef.YOU)
        # granted ability: continuous static, "You may" as its OWN
        # OptionalEffect layer outside the policy atom (C28)
        granted = pairs["ability"]
        assert isinstance(granted, StaticAbility)
        self.assertIsNone(granted.condition)
        optional = granted.effect
        assert isinstance(optional, OptionalEffect)
        policy = _as_atom(optional.inner)
        self.assertIs(policy.verb, Verb.DAMAGE_ASSIGN_POLICY)
        self.assertEqual(dict(policy.args.pairs), {"scope": "AS_UNBLOCKED"})
        # duration rides the GRANT atom, not the granted static (Basri)
        self.assertEqual(pairs["duration"], DurationEot())
