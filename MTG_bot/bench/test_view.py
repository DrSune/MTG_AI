"""The per-seat view must not depend on anything the seat may not know.

The metamorphic test is the load-bearing one. Take a real mid-game position, render a seat's
view, then replace every card that seat cannot see (the opponent's hand, both libraries) with
sentinels and shuffle the libraries. The re-rendered view must be byte-identical and must not
mention a sentinel. An encoder that passes this cannot be omniscient. The bot's current one
fails it by construction (docs/REVIEW_2026-10-24.md A-1).
"""

from __future__ import annotations

import random
import re

import pytest

from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions, render_view
from MTG_bot.core.executor.games import Game, RandomPolicy, _play, _setup_game, deal_decks, get_supply
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_HAND, ZONE_LIBRARY

ORACLE = OracleIndex.for_sets("M21")


def _position(seed: int, turn: int) -> Game:
    supply = get_supply("castable")
    game = _setup_game(seed, supply, deal_decks(seed, 1409, supply))
    _play(
        game,
        RandomPolicy(seed),
        game.world.player_order,
        turn_cap=turn + 2,
        stop_after=lambda g, boundary: boundary == "turn_top" and g.world.turn >= turn,
    )
    return game


def _hide_everything_from(game: Game, viewer: int, seed: int) -> None:
    """Swap every card the viewer cannot see for a sentinel, and shuffle the libraries."""
    world = game.world
    shuffle = random.Random(seed)
    n = 0
    for seat, handle in enumerate(world.player_order):
        zones = world.players[handle].zones
        hidden = list(zones[ZONE_LIBRARY].entries)
        if seat != viewer:
            hidden += zones[ZONE_HAND].entries
        for card in hidden:
            n += 1
            world.cards[card].identity = CardIdentity(
                oracle_id=f"5e471ae1-0000-0000-0000-{n:012d}",
                name=f"SENTINEL {n}",
                type_line="Creature — Sentinel",
                power="9",
                toughness="9",
                oracle_text="SENTINEL TEXT",
            )
        shuffle.shuffle(zones[ZONE_LIBRARY].entries)


@pytest.mark.parametrize("seed,turn", [(3, 3), (3, 6), (4, 6), (5, 3), (5, 6)])
@pytest.mark.parametrize("viewer", [0, 1])
@pytest.mark.parametrize("masked", [False, True])
def test_view_is_invariant_to_hidden_cards(seed: int, turn: int, viewer: int, masked: bool) -> None:
    opts = ViewOptions(mask_names=masked, salt="test")
    game = _position(seed, turn)
    before = render_view(SeatLens(viewer, ORACLE, opts).view(game.executor))
    _hide_everything_from(game, viewer, seed)
    after = render_view(SeatLens(viewer, ORACLE, opts).view(game.executor))
    assert "SENTINEL" not in after
    assert after == before


def test_view_shows_own_hand_and_only_counts_for_the_rest() -> None:
    game = _position(4, 6)
    world = game.world
    me, them = world.player_order
    text = render_view(SeatLens(0, ORACLE).view(game.executor))
    for handle in world.players[me].zone(ZONE_HAND).entries:
        assert world.cards[handle].identity.name in text
    opp_hand = len(world.players[them].zone(ZONE_HAND).entries)
    assert f"hand {opp_hand} cards (hidden)" in text


def test_object_ids_are_never_engine_handles() -> None:
    text = render_view(SeatLens(1, ORACLE).view(_position(5, 6).executor))
    assert not re.search(r"\b(card|player|zone):\d+", text)


def test_masked_view_leaks_no_masked_name() -> None:
    lens = SeatLens(0, ORACLE, ViewOptions(mask_names=True, salt="test"))
    text = render_view(lens.view(_position(3, 6).executor))
    assert lens.masker is not None
    assert lens.masker.leaks(text) == []
    assert re.search(r"\bC\d{3}\b", text)  # something was actually masked


def test_the_swap_is_not_vacuous() -> None:
    # Negative control: the omniscient audit dump DOES change under the same transformation, so
    # the invariance above is a property of the view, not of a swap that touched nothing.
    import json

    from MTG_bot.core.executor.games import world_snapshot

    game = _position(4, 6)
    before = json.dumps(world_snapshot(game.executor), sort_keys=True, default=str)
    _hide_everything_from(game, 0, 4)
    after = json.dumps(world_snapshot(game.executor), sort_keys=True, default=str)
    assert before != after
    assert "SENTINEL" in after
