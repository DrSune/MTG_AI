"""Deck modes: the default deal is the stress pile byte for byte; "coherent" is two colours."""

from __future__ import annotations

import hashlib
from collections import Counter

import pytest

from MTG_bot.core.executor.games import (
    COHERENT_LANDS,
    DECK_SIZE,
    MAX_COPIES,
    deal_decks,
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
