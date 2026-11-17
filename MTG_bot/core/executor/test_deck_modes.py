"""Deck modes: the default deal is the stress pile byte for byte; "coherent" is two colours."""

from __future__ import annotations

import dataclasses
import hashlib
from collections import Counter

import pytest

from MTG_bot.core.executor.games import (
    COHERENT_LANDS,
    DECK_SIZE,
    MAX_COPIES,
    build_coherent_deck,
    deal_decks,
    deck_rule_copies,
    get_supply,
    play_game,
)


@pytest.fixture(scope="module")
def m21():
    return get_supply("castable", "M21")


def test_the_default_deal_is_the_stress_pile_byte_for_byte(m21) -> None:
    # Hash of the M21 deals for seeds 1-5 (280 deckable cards). It moves whenever the castable
    # M21 pool changes; before re-pinning, check that dropping the changed cards from the old
    # supply reproduces the old hash.
    deals = [deal_decks(seed, 1409, m21) for seed in range(1, 6)]
    assert hashlib.sha256(repr(deals).encode()).hexdigest()[:16] == "2eee0b1b533f0ef2"
    assert deals == [deal_decks(seed, 1409, m21, "stress") for seed in range(1, 6)]


@pytest.mark.parametrize("seed", range(1, 21))
def test_a_coherent_deck_is_two_colours_with_24_basics(m21, seed: int) -> None:
    for deck in deal_decks(seed, 1409, m21, "coherent"):
        assert len(deck) == DECK_SIZE
        lands = [o for o in deck if m21.metas[o].is_land]
        assert len(lands) == COHERENT_LANDS and all(m21.metas[o].is_basic for o in lands)
        basic_names = Counter(m21.metas[o].name for o in lands)
        assert len(basic_names) == 2 and set(basic_names.values()) == {COHERENT_LANDS // 2}
        pair = {
            {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}[n]
            for n in basic_names
        }
        for oid in deck:
            if not m21.metas[oid].is_land:
                assert set(m21.pool.results[oid].card.color_identity) <= pair
        spells = Counter(o for o in deck if not m21.metas[o].is_land)
        assert max(spells.values()) <= MAX_COPIES


def test_coherent_deals_are_seeded_and_vary(m21) -> None:
    assert deal_decks(7, 1409, m21, "coherent") == deal_decks(7, 1409, m21, "coherent")
    pairs = {
        frozenset(m21.metas[o].name for o in deck if m21.metas[o].is_basic)
        for seed in range(1, 31)
        for deck in deal_decks(seed, 1409, m21, "coherent")
    }
    assert len(pairs) >= 6  # ten possible pairs; a stuck sampler would show one


def test_coherent_games_play_to_a_result(m21) -> None:
    # The random policy taps its mana creatures at will and cannot bank mana across steps
    # (CR 500.5, 508.1a), so some games reach the 60-turn cap (seeds 3 and 4); every game
    # must still run crash-free and never stall.
    decisive = 0
    for seed in range(1, 6):
        outcome = play_game(seed, pool_mode="castable", supply=m21, deck_mode="coherent")
        assert outcome.crash is None and not outcome.reason.startswith("STALL")
        decisive += "game over" in outcome.reason
    assert decisive >= 3


def test_an_unknown_mode_raises(m21) -> None:
    with pytest.raises(ValueError, match="deck_mode"):
        deal_decks(1, 1409, m21, "constructed")


def test_a_cards_own_deck_rule_lifts_the_copy_limit() -> None:
    """CR 100.2a, the card winning (CR 101.1): "A deck can have any number of cards named ~."
    (FDN Hare Apparent) and "... up to seven ..." (ELD Seven Dwarves), read off the printed
    sentence (docs/MAPPER_GUIDE.md "Labelled sentences"); every other card keeps MAX_COPIES."""
    rule = "A deck can have any number of cards named Hare Apparent."
    assert deck_rule_copies(rule, "Hare Apparent") == DECK_SIZE
    assert deck_rule_copies(rule, "Rat Colony") is None  # another card's rule
    assert deck_rule_copies("A deck can have up to seven cards named Seven Dwarves.", "Seven Dwarves") == 7
    assert deck_rule_copies("When this creature enters, draw a card.", "Hare Apparent") is None
    for code, lifted in (("FDN", {"Hare Apparent": DECK_SIZE}), ("ELD", {"Seven Dwarves": 7})):
        metas = get_supply("all", code).metas.values()
        assert {m.name: m.max_copies for m in metas if m.max_copies != MAX_COPIES} == lifted


def test_the_coherent_deck_deals_a_deck_rule_card_past_four(m21) -> None:
    # The pool's basics and one colourless spell whose deck rule lifts the limit: all 36 spell
    # slots hold it. Under the four-copy limit alone the pool was refused as too small.
    spell = next(o for o in m21.deckable
                 if not m21.metas[o].is_land and not m21.pool.results[o].card.color_identity)
    basics = [o for o in m21.deckable if m21.metas[o].is_basic]
    sup = dataclasses.replace(m21, deckable=(*basics, spell), metas={
        **m21.metas, spell: dataclasses.replace(m21.metas[spell], max_copies=DECK_SIZE)})
    for seed in range(1, 4):
        assert Counter(build_coherent_deck(seed, sup))[spell] == DECK_SIZE - COHERENT_LANDS
