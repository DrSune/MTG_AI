"""Search-substrate gates (KNOWLEDGE/2026-10-10/67).

fork() soundness, rollout reproducibility, and expand() ask-kind coverage
(act menu, attack:, block:) — every position pinned to a deterministic seed.
"""

from __future__ import annotations

import pytest

from tools.search import (
    Position,
    expand,
    fork,
    play_position,
    rollout,
)

SEED = 20261010  # greedy-vs-greedy midgame line used by the bench


def _active_seat(game):
    seat = game.world.active_player
    assert seat is not None  # every pinned position below sits mid-turn
    return game.world.player_order.index(seat)


@pytest.fixture(scope="module")
def pos8():
    return play_position(SEED, at_turn=8, boundary="turn_top")


# ----------------------------------------------------------------- fork laws


def test_fork_isolates_parent(pos8):
    parent = pos8.game
    fp = parent.executor.state_fingerprint()
    child = fork(parent, pos8.supply)
    child.world.players[child.world.active_player].life = 1  # mutate clone
    child.executor.journal.emit("TEST", None, child.world.active_player, "X", ())
    assert parent.executor.state_fingerprint() == fp  # parent untouched


def test_fork_is_deterministic(pos8):
    a = rollout(fork(pos8.game, pos8.supply), "random", 7, turn_cap=25)
    b = rollout(fork(pos8.game, pos8.supply), "random", 7, turn_cap=25)
    assert (a.result, a.reason, a.fingerprint) == (b.result, b.reason, b.fingerprint)
    assert a.asks > 0


def test_fork_carries_no_tracer(pos8):
    assert fork(pos8.game, pos8.supply).trace is None


# -------------------------------------------------------------- rollout laws


def test_rollout_reproducible_and_terminal(pos8):
    g = fork(pos8.game, pos8.supply)
    r = rollout(g, "random", 4242, turn_cap=40)
    assert r.result in {"draw", "seat0", "seat1", "undecided", "crash"}
    assert r.reason
    assert r.turns >= pos8.game.world.turn
    assert isinstance(r.lives, tuple) and len(r.lives) == 2


def test_rollout_consumes_only_its_own_game(pos8):
    """rollout() RUNS the game it is handed (it is a forkable resource);
    the search contract is that callers hand it a fork, leaving the parent
    position pristine — which is exactly what this checks."""
    fp = pos8.game.executor.state_fingerprint()
    child = fork(pos8.game, pos8.supply)
    rollout(child, "random", 5, turn_cap=20)
    assert child.executor.state_fingerprint() != fp  # the fork really ran
    assert pos8.game.executor.state_fingerprint() == fp


# ----------------------------------------------------------------- expand law


def test_expand_leaves_parent_pristine(pos8):
    fp = pos8.game.executor.state_fingerprint()
    seat = _active_seat(pos8.game)
    xs = expand(pos8, seat)
    assert len(xs.options) >= 1
    assert pos8.game.executor.state_fingerprint() == fp


def test_expand_engine_choose_ask(pos8):
    """The pinned t8 active-seat first ask is an engine color choose."""
    seat = _active_seat(pos8.game)
    xs = expand(pos8, seat)
    assert xs.kind == "choose"
    assert xs.site.startswith("choose:")
    assert xs.words == tuple(xs.words) and set(xs.words) == {"0", "1"}
    for o in xs.options:
        assert o.boundary in {"mid_act", "pre_combat", "post_combat"}


def test_expand_act_menu_ask():
    """After the color choose is answered (a mid_act branch), the seat's next
    decision is the act menu itself — kind 'act' on site act:main.

    re-pinned 2026-10-29 (engine/phasing): the two Teferis joined the engine
    supply, so seed 20261010 deals a different second deck, and at turn 8 the
    answered choose now ends the act batch (pre_combat). Turn 9 of the same
    seed is the nearest turn-top where the premise holds (scan in the commit)."""
    pos = play_position(SEED, at_turn=9, boundary="turn_top")
    seat = _active_seat(pos.game)
    branch = expand(pos, seat).options[0]
    assert branch.boundary == "mid_act"
    mid = Position(branch.game, pos.supply, "mid_act")
    xs = expand(mid, seat)
    assert xs.kind == "act" and xs.site == "act:main"
    assert len(xs.options) >= 2  # at least two acts are legal midgame


def test_expand_attack_ask():
    """Seed 20261010 turn 8 pre_combat: the active seat is asked ATTACK/
    DECLINE for its creature — the pinned attack-kind position."""
    pos = play_position(SEED, at_turn=8, boundary="pre_combat")
    att = _active_seat(pos.game)
    xs = expand(pos, att)
    assert xs.kind == "attack"
    assert xs.site.startswith("attack:")
    assert set(xs.words) == {"ATTACK", "DECLINE"}
    for o in xs.options:
        assert o.boundary == "post_combat"  # combat resolves, then clean stop


def test_expand_block_ask():
    """Seed 14 turn 11 pre_combat random-vs-random: seat 0 attacks and the
    defender's first ask is block: (pinned via a full seed scan)."""
    pos = play_position(14, at_turn=11, boundary="pre_combat", policies="random")
    att = _active_seat(pos.game)
    xs = expand(pos, 1 - att, default="random")
    assert xs.kind == "block"
    assert xs.site.startswith("block:")
    assert len(xs.options) == len(xs.words) >= 2


def test_expand_over_game_is_empty(pos8):
    dead = fork(pos8.game, pos8.supply)
    dead.world.players[dead.world.player_order[0]].life = 0
    dead.world.players[dead.world.player_order[1]].life = 0
    xs = expand(Position(dead, pos8.supply, "turn_top"), 0)
    assert xs.kind == "over" and xs.options == ()
