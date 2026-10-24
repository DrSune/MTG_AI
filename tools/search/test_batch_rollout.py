"""Tests for batched multi-seat rollout inference (/79 cost gate).

Run: .venv/bin/python -m pytest tools/search/test_batch_rollout.py -q

Binding invariant: batching changes ONLY the tensor layout of the forward.
Batched rollout decisions must be BIT-IDENTICAL to the sequential per-seat
BcAsk path (same forks, same seeds, same fresh streams) — otherwise the
on-policy /74 §5 labels measured through this path would not be comparable
to the sequential ones.
"""

from __future__ import annotations

import json
import threading

import torch

torch.set_num_threads(1)

import pytest

from tools.search import batch_net, gen_games, mcts
from tools.search.fork import fork
from tools.search.rollout import play_position, rollout
from tools._testutil import skip_unless_files

E2E_TIMEOUT = pytest.mark.timeout(1800)


def _mid_position():
    for turn in (6, 8, 10, 12):
        try:
            return play_position(20261010, at_turn=turn)
        except RuntimeError:  # game ended before the requested turn
            continue
    raise AssertionError("no mid-game position reachable")


# ---------------------------------------------------------------- batcher core


class _FakeBc:
    """Just enough BcAsk surface for NetBatcher bookkeeping; the batch
    forward is monkeypatched so no model is ever touched."""

    def __init__(self, tag: int) -> None:
        self.tag = tag


def _pool_run(batcher, n_threads, n_calls):
    """Every thread parks n_calls times through the proper begin/end thread
    registration; answers are row-order dependent so we can prove each
    thread received ITS OWN answer, not a sibling's."""
    results: dict[int, list[int]] = {t: [] for t in range(n_threads)}
    errors: dict[int, BaseException] = {}
    started = threading.Barrier(n_threads)

    def work(t: int) -> None:
        batcher.begin_thread()
        try:
            started.wait(10)  # force true concurrency into the batcher
            for i in range(n_calls):
                results[t].append(batcher.decide(_FakeBc(t), (t, i)))
        except BaseException as e:  # noqa: BLE001
            errors[t] = e
        finally:
            batcher.end_thread()

    ths = [threading.Thread(target=work, args=(t,)) for t in range(n_threads)]
    for th in ths:
        th.start()
    for th in ths:
        th.join(30)
    assert not any(th.is_alive() for th in ths), "NetBatcher deadlocked"
    return results, errors


def test_batcher_lockstep_answers_and_merges(monkeypatch):
    """Every parked thread wakes with ITS OWN answer; no row is lost,
    doubled, or stolen; and at least one forward really carries >1 row."""
    seen: list[int] = []

    def fake(items):
        seen.append(len(items))
        return [bc.tag * 100 + ctx[1] for bc, ctx in items]

    monkeypatch.setattr(batch_net, "batch_decide", fake)
    bn = batch_net.NetBatcher()
    results, errors = _pool_run(bn, 4, 5)
    assert not errors, errors
    for t, got in results.items():
        assert got == [t * 100 + i for i in range(5)]
    assert sum(seen) == 20, "rows lost or double-counted"
    assert max(seen) >= 2, "no batch ever merged: threads ran serially"


def test_batcher_delivers_failure_to_every_parked_seat(monkeypatch):
    boom = RuntimeError("cuda assert")

    def fake(items):
        raise boom

    monkeypatch.setattr(batch_net, "batch_decide", fake)
    bn = batch_net.NetBatcher()
    _results, errors = _pool_run(bn, 3, 1)
    # the forward failure must reach EVERY seat — a silent retry on a corrupt
    # stream is the exact sin this discipline forbids.
    assert len(errors) == 3, f"expected all 3 seats to raise, got {errors}"
    assert all(e is boom for e in errors.values())


def test_batcher_flushes_parked_rows_when_siblings_leave(monkeypatch):
    """A thread may finish its game while another is parked; the LAST one
    standing must run the parked row itself (end_thread flush), or the
    parked seat hangs forever."""
    done: list[list] = []

    def fake(items):
        done.append([bc.tag for bc, _ctx in items])
        return [bc.tag for bc, _ctx in items]

    monkeypatch.setattr(batch_net, "batch_decide", fake)
    bn = batch_net.NetBatcher()
    bn.begin_thread()  # thread A parks one row, never wakes another caller
    got = bn.decide(_FakeBc(9), (9, 0))  # alive==1 -> parks and self-batches
    assert got == 9 and done == [[9]]
    bn.end_thread()


# ------------------------------------------------------------- end-to-end nets


@E2E_TIMEOUT
@skip_unless_files(mcts.NET_SPEC)
def test_batched_rollouts_bit_identical_to_sequential(monkeypatch):
    """3 concurrent net rollouts via rollout_many == 3 sequential rollouts:
    same forks, same seeds, fresh streams — identical fingerprints (and the
    batcher really merged rows on the way)."""
    from tools.training.ab_duel import BcAsk

    pos = _mid_position()
    cap, seed0 = 4, 777

    def specs():
        return [
            {s: BcAsk.fresh(mcts.NET_SPEC, "cpu") for s in (0, 1)} for _ in range(3)
        ]

    seq = [
        rollout(fork(pos.game, pos.supply), sp, seed0 + i, turn_cap=cap)
        for i, sp in enumerate(specs())
    ]
    assert all(r.fingerprint for r in seq), [r.result for r in seq]

    sizes: list[int] = []
    real = batch_net.batch_decide

    def spy(items):
        sizes.append(len(items))
        return real(items)

    monkeypatch.setattr(batch_net, "batch_decide", spy)
    bn = batch_net.NetBatcher()
    batch = batch_net.rollout_many(
        [fork(pos.game, pos.supply) for _ in range(3)],
        specs(),
        [seed0 + i for i in range(3)],
        cap,
        bn,
    )
    assert all(a.fingerprint == b.fingerprint for a, b in zip(seq, batch)), (
        "batched forward diverged from the sequential per-seat path: "
        f"{[(a.result, b.result) for a, b in zip(seq, batch)]}"
    )
    assert sum(sizes) > 0 and max(sizes) >= 2, f"no merge: {sizes}"


# ----------------------------------------------------- gen_games failure plane


def test_aggregate_survives_zero_games():
    """/79 crash: min()/max() on an empty fleet used to raise, hiding the
    fact that NOTHING completed."""
    agg = gen_games._aggregate([], 1.0, 0)
    assert agg["games"] == 0
    assert agg["cost"]["seconds_per_game_min"] == 0.0
    assert agg["n_failed"] == 0


def test_worker_death_surfaces_in_stats(tmp_path):
    """A bad --net kills every worker; the run must still write stats whose
    failed_games list explains the empty fleet (no silent zero-game run)."""
    stats = tmp_path / "stats.json"
    rc = gen_games.main(
        [
            "--games",
            "2",
            "--workers",
            "2",
            "--seeds",
            "1",
            "--budget-min",
            "3",
            "--net",
            str(tmp_path / "no_such_net.pt"),
            "--out-episodes",
            str(tmp_path / "eps.jsonl"),
            "--out-stats",
            str(stats),
        ]
    )
    assert rc == 0
    agg = json.loads(stats.read_text())
    assert agg["games"] == 0 and agg["n_failed"] == 2
    assert all(f["type"] and f["first_frame"] for f in agg["failed_games"])
    assert {f["seed"] for f in agg["failed_games"]} == {1, 2}
