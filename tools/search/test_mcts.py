"""Unit + mini end-to-end tests for the AlphaZero-style generator.

Run: .venv/bin/python -m pytest tools/search/test_mcts.py -q
The end-to-end test uses tiny knobs (k=1, N=1, cap 3) so one game costs a
few model forwards; every other test here is pure arithmetic or engine-
cheap.
"""

from __future__ import annotations

import torch

torch.set_num_threads(1)

import pytest

from tools.search import mcts
from tools.search.rollout import RolloutResult


# ------------------------------------------------------------------ UCB1
def test_ucb_unvisited_first_deterministic():
    u = mcts.Ucb1([2, 5, 9])
    seq = []
    for _ in range(3):  # unvisited arms first, in index order, no rng
        a = u.pick()
        seq.append(a)
        u.push(a, 0.0)
    assert seq == [2, 5, 9]
    # all tied at Q=0 -> exploration term equal too -> tie to LOWEST arm
    assert u.pick() == 2


def test_ucb_exploits_better_arm_and_totals():
    u = mcts.Ucb1([0, 1])
    for _ in range(8):
        a = u.pick()
        u.push(a, 1.0 if a == 1 else 0.0)
    assert sum(u.n.values()) == 8  # N pulls TOTAL, not per arm
    assert u.n[1] >= u.n[0]  # the winning arm accumulated at least as much


def test_ucb_pi_menu_aligned_and_sums_one():
    u = mcts.Ucb1([0, 2])
    for _ in range(6):
        a = u.pick()
        u.push(a, 0.5)
    pi = u.visit_fracs(5)  # menu of 5, arms {0,2} expanded
    assert len(pi) == 5
    assert abs(sum(pi) - 1.0) < 1e-9
    assert pi[1] == 0.0 and pi[3] == 0.0 and pi[4] == 0.0


def test_stable_int_cross_process_determinism():
    assert mcts.stable_int("ucb", 7, 0, 3) == mcts.stable_int("ucb", 7, 0, 3)
    assert mcts.stable_int("ucb", 7, 0, 3) != mcts.stable_int("ucb", 7, 0, 4)


# ----------------------------------------------------------------- values
def _res(result: str, life_diff: int = 0) -> RolloutResult:
    return RolloutResult(
        result=result,
        winner=None,
        reason="",
        turns=5,
        lives=(20, 20),
        life_diff=life_diff,
        asks=0,
        fingerprint="",
    )


def test_value_decided_from_root_seat_perspective():
    assert mcts.rollout_value(_res("seat0"), 0) == (1.0, "decided")
    assert mcts.rollout_value(_res("seat0"), 1) == (0.0, "decided")
    assert mcts.rollout_value(_res("seat1"), 1) == (1.0, "decided")
    assert mcts.rollout_value(_res("draw"), 0) == (0.5, "decided")


def test_value_crash_is_half_in_its_own_bucket():
    v, b = mcts.rollout_value(_res("crash", life_diff=99), 0)
    assert (v, b) == (0.5, "crash")


def test_value_shaping_clamped_and_seat_flipped():
    v, b = mcts.rollout_value(_res("undecided", life_diff=6), 0)
    assert b == "shaping" and v == pytest.approx(0.5 + 6 / 40)
    v1, _ = mcts.rollout_value(_res("undecided", life_diff=6), 1)
    assert v1 == pytest.approx(0.5 - 6 / 40)  # root-seat sign flip
    # clamp at +/-10 life
    hi, _ = mcts.rollout_value(_res("undecided", life_diff=250), 0)
    assert hi == pytest.approx(0.75)
    lo, _ = mcts.rollout_value(_res("undecided", life_diff=-250), 0)
    assert lo == pytest.approx(0.25)
    assert all(
        0.0 <= mcts.rollout_value(_res("undecided", d), s)[0] <= 1.0
        for d in (-999, -3, 0, 4, 999)
        for s in (0, 1)
    )


def test_adv_mix_math_root_seat_edge_over_champion_pick():
    """/74 §5 IMPROVEMENT label: value(search-top1) - value(net-argmax
    champion pick); 0 when either arm was never evaluated or they coincide;
    bounded by the [0,1] backed values."""
    means = {0: 0.7, 1: 0.3, 2: 0.5}
    assert mcts.adv_mix_of(means, 0, 1) == pytest.approx(0.4)
    assert mcts.adv_mix_of(means, 1, 0) == pytest.approx(-0.4)
    assert mcts.adv_mix_of(means, 2, 2) == 0.0  # search pick IS the champion
    assert mcts.adv_mix_of({0: 1.0}, 0, 5) == 0.0  # champion arm apply-crashed
    assert mcts.adv_mix_of({1: 0.2}, 7, 1) == 0.0  # search pick unevaluated
    assert mcts.adv_mix_of({0: 1.0, 1: 0.0}, 0, 1) == 1.0  # endpoints
    assert mcts.adv_mix_of({0: 0.0, 1: 1.0}, 0, 1) == -1.0


# ----------------------------------------------------------- end to end
# These run real net forwards on a shared CPU; under pool load one call can
# blow past the repo's global 120 s pytest-timeout, which would be caught by
# gen_game's crash bucket. Give them a generous per-test budget.
E2E_TIMEOUT = pytest.mark.timeout(1800)


@pytest.fixture(scope="module")
def mini_game():
    return mcts.gen_game(9001, k=1, n_rollouts=1, turn_cap=3)


@E2E_TIMEOUT
def test_mini_game_contract(mini_game):
    assert mini_game["crash"] is None, mini_game["reason"]
    assert mini_game["result"] in ("seat0", "seat1", "draw", "undecided")
    s = mini_game["stats"]
    assert s.asks_searched >= 3 and s.rollouts == s.asks_searched
    eps = [e for seat in (0, 1) for e in mini_game["episodes"][seat]]
    assert eps and all(e["label_class"] == "search" for e in eps)


@E2E_TIMEOUT
def test_mini_rows_pi_value_contract(mini_game):
    for seat in (0, 1):
        for ep in mini_game["episodes"][seat]:
            for r in ep["asks"]:
                assert len(r["pi"]) == len(r["candidates"])
                assert abs(sum(r["pi"]) - 1.0) < 1e-5
                assert all(p >= 0.0 for p in r["pi"])
                assert 0.0 <= r["value"] <= 1.0
                assert 0 <= r["gold_idx"] < len(r["candidates"])
                assert r["gold_idx"] == max(
                    range(len(r["pi"])), key=lambda i: (r["pi"][i], -i)
                )


def test_pi_mix_math_blends_and_keeps_net_mass():
    """AZ-v3 target law: 0.75*visits + 0.25*net over the FULL menu. Both
    inputs sum to 1 so the blend sums to 1 exactly; an option the search
    never visits keeps 0.25*net mass (never a hard zero)."""
    mix = mcts.pi_mix_of([0.5, 0.5, 0.0], [0.2, 0.3, 0.5])
    assert mix == pytest.approx([0.5 * 0.75 + 0.25 * 0.2, 0.45, 0.125])
    assert sum(mix) == pytest.approx(1.0, abs=1e-12)
    assert all(x > 0.0 for x in mix)
    flat = mcts.pi_mix_of([1.0, 0.0], [0.5, 0.5])
    assert flat == pytest.approx([0.875, 0.125])
    with pytest.raises(ValueError):
        mcts.pi_mix_of([0.5, 0.5], [1.0])


@pytest.fixture(scope="module")
def mini_game_greedy():
    return mcts.gen_game(9001, k=1, n_rollouts=1, turn_cap=3, rollout_mix="greedy")


@E2E_TIMEOUT
def test_mini_game_greedy_rollout_mix(mini_game_greedy):
    """/72 AZ-v3: rollout_mix="greedy" drives BOTH seats greedy — no random
    or net draws in the policy ledger — and every row carries a menu-aligned
    pi_mix whose strictly-positive mass is the anti-brittleness property."""
    gg = mini_game_greedy
    assert gg["crash"] is None, gg["reason"]
    assert gg["stats"].policy_mix.get("random", 0) == 0
    assert gg["stats"].policy_mix.get("net", 0) == 0
    assert gg["stats"].policy_mix["greedy"] >= 2 * gg["stats"].asks_searched
    for seat in (0, 1):
        for ep in gg["episodes"][seat]:
            for r in ep["asks"]:
                assert len(r["pi_mix"]) == len(r["candidates"])
                assert abs(sum(r["pi_mix"]) - 1.0) < 1e-6
                assert all(p > 0.0 for p in r["pi_mix"])
                assert r["gold_idx"] == r["pi"].index(max(r["pi"]))


@E2E_TIMEOUT
def test_mini_game_reproducible(mini_game):
    again = mcts.gen_game(9001, k=1, n_rollouts=1, turn_cap=3)
    assert again["result"] == mini_game["result"]
    assert again["reason"] == mini_game["reason"]
    sa, sb = again["stats"], mini_game["stats"]
    assert (sa.asks_searched, sa.rollouts, sa.swallowed) == (
        sb.asks_searched,
        sb.rollouts,
        sb.swallowed,
    )


@E2E_TIMEOUT
def test_mini_cost_ledger_and_cheap_mix(mini_game):
    """Probe-cache accounting is honest and cheap rollouts never see the net."""
    s = mini_game["stats"]
    assert s.probes + s.probe_cache_hits == s.asks_searched
    assert s.probe_cache_hits >= 1  # mid_act handovers do occur on this seed
    assert "net" not in s.policy_mix  # cheap default: net = root probs only
    assert s.policy_mix["greedy"] + s.policy_mix["random"] == 2 * s.rollouts
    assert s.net_fwd == s.asks_searched  # exactly one forward per searched ask


@E2E_TIMEOUT
def test_resume_stall_guard_mirrors_engine():
    """_resume_stalls must agree with what _play ACTUALLY does on the first
    loop iteration of a resume (seed 9100 turn 8: the probe-cache handover
    skipped the stall rule and all 3 apply forks stalled out)."""
    from tools.search.rollout import (
        GREEDY_TEACHER,
        SearchDriver,
        _run,
        _wire,
        play_position,
    )
    from MTG_bot.core.executor.games import _stall_fingerprint, REPEAT_ROUNDS

    pos = None
    for turn in (5, 6, 7, 8):
        try:
            pos = play_position(20261010, at_turn=turn)
            break
        except RuntimeError:
            continue
    assert pos is not None
    g = pos.game
    seat = g.world.active_player
    assert seat is not None
    fp = _stall_fingerprint(g.executor)
    g.stall_seen[seat] = (fp, 1)  # one repeat short of the cap
    assert mcts._resume_stalls(g) is False
    g.stall_seen[seat] = (fp, REPEAT_ROUNDS - 1)  # at the cap
    assert mcts._resume_stalls(g) is True
    # ground truth: the real loop must now end in a STALL reason immediately
    drv = SearchDriver(99, GREEDY_TEACHER, "rollout")
    _wire(g, drv)
    _run(g, drv, g.world.turn + 8, "turn_top")
    assert g.reason.startswith("STALL")


@E2E_TIMEOUT
def test_branch_next_ask_matches_discovery():
    """The probe cache's correctness law: a mid_act branch's carried ask is
    EXACTLY what a fresh discovery probe would find at the suspended branch
    (same site, seat and candidate list) — skipping the probe is lossless."""
    from tools.search.rollout import play_position

    checked = 0
    for turn in range(4, 14):
        try:
            pos = play_position(20261010, at_turn=turn)
        except RuntimeError:  # game ended before the requested turn
            continue
        found = mcts._probe(pos).ask
        if found is None:
            continue
        info, ctx = found
        br = mcts._apply_word(pos, info, list(ctx.candidates)[0], 0, info.seat)
        if br.boundary != "mid_act":
            continue
        assert br.next_ask is not None, "mid_act stop must carry its ask"
        truth = mcts._probe(mcts.Position(br.game, pos.supply, br.boundary)).ask
        assert truth is not None
        assert truth[0].site == br.next_ask[0].site
        assert truth[0].seat == br.next_ask[0].seat
        assert truth[0].index == br.next_ask[0].index == 0
        assert list(truth[1].candidates) == list(br.next_ask[1].candidates)
        checked += 1
        if checked >= 2:
            break
    assert checked >= 1, "no mid_act branch exercised"


class _CountingNet:
    """Pass-through wrapper proving a rollout seat's decisions really came
    from the net (call counter) while keeping BcAsk's stream semantics."""

    def __init__(self, net):
        self.net, self.calls = net, 0

    def decide(self, ctx):
        self.calls += 1
        return self.net.decide(ctx)


@E2E_TIMEOUT
def test_net_spec_rollouts_deterministic_under_seed():
    """/74 §5 IMPROVEMENT: a rollout seat driven by a FRESH root-net instance
    (a) actually plays (decide() called; the seat is a BcAsk, NOT the
    HeuristicTeacher class), and (b) is fully deterministic under the same
    seed — two forks + fresh streams replay the identical game — and the
    net line differs from the greedy line (the mix is not a no-op)."""
    from tools.eval.gameplay_eval_v2 import HeuristicTeacher
    from tools.search.fork import fork
    from tools.search.rollout import play_position, rollout
    from tools.training.ab_duel import BcAsk

    pos = None
    for turn in (6, 8, 10, 12):
        try:
            pos = play_position(20261010, at_turn=turn)
            break
        except RuntimeError:  # game ended before the requested turn
            continue
    assert pos is not None

    def net_seats():
        return {s: _CountingNet(BcAsk.fresh(mcts.NET_SPEC, "cpu")) for s in (0, 1)}

    a, b = net_seats(), net_seats()
    r1 = rollout(fork(pos.game, pos.supply), a, 555, turn_cap=6)
    r2 = rollout(fork(pos.game, pos.supply), b, 555, turn_cap=6)
    assert all(not isinstance(w, HeuristicTeacher) for w in a.values())
    assert sum(w.calls for w in a.values()) > 0  # the net really drove seats
    assert r1.fingerprint and r1.result == r2.result
    assert r1.fingerprint == r2.fingerprint
    rg = rollout(fork(pos.game, pos.supply), "greedy", 555, turn_cap=6)
    assert rg.fingerprint != r1.fingerprint  # net seats != greedy seats
