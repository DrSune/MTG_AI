"""fork() soundness: the decision-time search (tools/selfplay/search.py) clones the live game with it.

Positions come from the engine's own seeded random game (``games.RandomPolicy``) stopped at a clean
turn-top boundary, so these tests need no checkpoint and no agent rig.
"""

from __future__ import annotations

import pytest

from MTG_bot.core.executor.games import (
    RandomPolicy,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)
from tools.search.fork import fork

SEED = 20261010


@pytest.fixture(scope="module")
def pos8():
    """The first seed from SEED on whose game is still running at the top of turn 8."""
    supply = get_supply("castable")
    for seed in range(SEED, SEED + 10):
        game = _setup_game(seed, supply, deal_decks(seed, 1409, supply))
        _play(game, RandomPolicy(seed), list(game.world.player_order), 99,
              stop_after=lambda g, boundary: boundary == "turn_top" and g.world.turn >= 8)
        if game.world.turn == 8 and not game.reason:
            return game, supply
    raise AssertionError(f"no seed in [{SEED}, {SEED + 10}) reaches turn 8")


def _play_out(game, seed: int):
    _play(game, RandomPolicy(seed), list(game.world.player_order), 40, resumed=True)
    return game


def test_fork_isolates_parent(pos8):
    parent, supply = pos8
    fp = parent.executor.state_fingerprint()
    child = fork(parent, supply)
    child.world.players[child.world.active_player].life = 1  # mutate the clone
    child.executor.journal.emit("TEST", None, child.world.active_player, "X", ())
    assert parent.executor.state_fingerprint() == fp


def test_playing_a_fork_leaves_the_parent_pristine(pos8):
    parent, supply = pos8
    fp = parent.executor.state_fingerprint()
    child = _play_out(fork(parent, supply), 5)
    assert child.executor.state_fingerprint() != fp  # the fork really ran
    assert parent.executor.state_fingerprint() == fp


def test_fork_is_deterministic(pos8):
    a = _play_out(fork(*pos8), 7)
    b = _play_out(fork(*pos8), 7)
    assert a.reason and a.world.turn > 8
    assert (a.reason, a.executor.state_fingerprint()) == (b.reason, b.executor.state_fingerprint())


def test_fork_carries_no_tracer(pos8, monkeypatch):
    parent, supply = pos8
    monkeypatch.setattr(parent, "trace", object())  # stands in for a TraceRecorder
    assert fork(parent, supply).trace is None
