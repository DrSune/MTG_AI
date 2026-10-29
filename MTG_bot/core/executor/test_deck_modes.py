"""Deck modes (B-45): the default stays the stress pile byte for byte; "coherent" is two colours."""

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
    # Hash of the M21 deals for seeds 1-5 before deck modes existed (main 3a1e05b, 2026-10-27).
    # re-pinned 2026-10-29: B-49 carrier made 42 noncreature permanents castable (M21 castable pool grew)
    # from 239 to 281 deckable cards, so the deals moved (was "e9fceb12fb91e3ab"). The default ==
    # "stress" identity below is unchanged.
    # re-pinned 2026-10-29 (B-49 follow-up #1): 281 -> 279, the two Chandras with suppressed duration
    # permissions are engine-unsupported (was "d8e619dbf28b3c6d").
    # re-pinned 2026-10-29 (B-49 follow-up #4): 279 -> 278, Ugin's [−X] loyalty cost is gated
    # engine-unsupported (was "fdcbefbd2b37d046").
    deals = [deal_decks(seed, 1409, m21) for seed in range(1, 6)]
    assert hashlib.sha256(repr(deals).encode()).hexdigest()[:16] == "e05cfd168521e687"
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
    for seed in range(1, 6):
        outcome = play_game(seed, pool_mode="castable", supply=m21, deck_mode="coherent")
        assert outcome.crash is None and "game over" in outcome.reason


def test_an_unknown_mode_raises(m21) -> None:
    with pytest.raises(ValueError, match="deck_mode"):
        deal_decks(1, 1409, m21, "constructed")
