"""Episode-collector gates: determinism pin, reward-lane presence pin, schema.

Kept cheap on purpose: ``engine`` pool, short turn caps, few seeds. The
throughput measurement (batch-0) lives in ``collector.py --bench``, not here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.training.collector import (
    REWARD_KINDS,
    AskContext,
    EpisodeCollector,
    FirstAsk,
    PassFirstAsk,
)

COLLECTOR = EpisodeCollector(pool_mode="engine", turn_cap=15)


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def episode() -> dict:
    return COLLECTOR.run_episode(1)


@pytest.fixture(scope="module")
def batch() -> list[dict]:
    return COLLECTOR.collect([1, 2, 3, 4, 5])


# -------------------------------------------------------------------- schema
def test_schema_keys(episode: dict) -> None:
    for key in (
        "seed",
        "pool",
        "deck_pairs_seed",
        "turn_cap",
        "policy",
        "seats",
        "steps",
        "terminal",
        "rewards",
    ):
        assert key in episode
    assert episode["seats"] == ["player:0", "player:1"]
    assert set(episode["terminal"]) == {"winner", "reason", "turns", "lives", "crash"}
    assert set(episode["terminal"]["lives"]) == {"player:0", "player:1"}


def test_step_rows_canonical(episode: dict) -> None:
    assert episode["steps"], "a 15-turn engine game answers at least one ask"
    for row in episode["steps"]:
        assert set(row) == {
            "ask_id",
            "vocab",
            "candidates",
            "chosen_idx",
            "clock",
            "seat",
        }
        assert row["ask_id"] >= 0
        assert 0 <= row["chosen_idx"] < len(row["candidates"])
        assert len(set(row["candidates"])) == len(row["candidates"])
    # ask_ids are a dense 0..n-1 sequence in ask order, clocks monotone
    assert [r["ask_id"] for r in episode["steps"]] == list(range(len(episode["steps"])))
    clocks = [r["clock"] for r in episode["steps"]]
    assert clocks == sorted(clocks)


# ------------------------------------------------------- determinism gate pin
def test_determinism_pin() -> None:
    """Same seed -> byte-identical trajectory line: the collector adds no
    nondeterminism (D9 attribution is only sound if this holds)."""
    a = json.dumps(COLLECTOR.run_episode(7), sort_keys=True)
    b = json.dumps(COLLECTOR.run_episode(7), sort_keys=True)
    assert a == b


# ------------------------------------------------------ reward-lane presence
def test_reward_lane_presence(batch: list[dict]) -> None:
    """The offline reward signal is PRESENT and typed: every recorded row is
    a reward-kind journal row, and across a 5-seed batch the lane is
    non-empty (a lane that never fills is a silent schema failure)."""
    for episode in batch:
        for row in episode["rewards"]:
            assert set(row) == {"clock", "kind", "subject", "cause", "data"}
            assert row["kind"] in REWARD_KINDS
    assert any(episode["rewards"] for episode in batch), (
        "reward lane must carry rows over 5 seeds"
    )


def test_no_crash_in_batch(batch: list[dict]) -> None:
    assert [ep["seed"] for ep in batch if ep["terminal"]["crash"]] == []


def test_seed_isolation() -> None:
    """D9 seed discipline: distinct seeds yield distinct trajectories."""
    a = json.dumps(COLLECTOR.run_episode(11), sort_keys=True)
    b = json.dumps(COLLECTOR.run_episode(12), sort_keys=True)
    assert a != b


# ------------------------------------------------------------------ policies
def test_scripted_floors() -> None:
    ctx_pass = AskContext(vocab="may:x", candidates=("PAY", "PASS"), world={})
    ctx_plain = AskContext(vocab="scry:0:1", candidates=("top", "bottom"), world={})
    assert FirstAsk().decide(ctx_pass) == 0
    assert PassFirstAsk().decide(ctx_pass) == 1
    assert PassFirstAsk().decide(ctx_plain) == 0


@pytest.mark.parametrize("policy", ["first", "pass-floor"])
def test_policy_pluggable_smoke(policy: str) -> None:
    collector = EpisodeCollector(pool_mode="engine", turn_cap=10, policy=policy)
    episode = collector.run_episode(3)
    assert episode["policy"] == policy
    assert episode["steps"]
    assert episode["terminal"]["reason"]


# --------------------------------------------------------------------- jsonl
def test_jsonl_write_and_parallel(tmp_path: Path) -> None:
    out = tmp_path / "episodes.jsonl"
    episodes = COLLECTOR.collect([1, 2], out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)["seed"] in (1, 2) for line in lines)
    assert lines == [json.dumps(ep, sort_keys=True) for ep in episodes]

    par = tmp_path / "parallel.jsonl"
    got = COLLECTOR.collect_parallel([1, 2], workers=2, out_path=par)
    assert [ep["seed"] for ep in got] == [1, 2]
    # spawn-workers replay the same seeds -> identical lines to sequential
    assert par.read_text(encoding="utf-8").splitlines() == lines
