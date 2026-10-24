"""Smoke tests for the gameplay eval (T5-G).

Fast lane: scripted-policy unit checks need NO supply compile; the single
end-to-end test runs TWO games (one per baseline, swap-off) with a tiny
turn cap and asserts the v1 JSON contract plus the engine-gated
illegal-action invariant (must be 0)."""

from __future__ import annotations

import json

from tools.eval.gameplay_eval import (
    REFUSE_TOKENS,
    TeacherAsk,
    main,
    summarize_matchup,
)
from tools.training.ab_duel import wilson
from tools.training.collector import AskContext, RandomAsk
from tools._testutil import skip_unless_files
from tools.eval.gameplay_eval import DEFAULT_POLICY


def _ctx(cands: tuple[str, ...]) -> AskContext:
    return AskContext(vocab="test", candidates=cands, world={})


def test_teacher_takes_action_and_never_refuses_one() -> None:
    t = TeacherAsk()
    # PASS offered first, an action second -> the script plays the action.
    assert t.decide(_ctx(("PASS", "draw-card"))) == 1
    # every candidate is a decline -> forced, take index 0.
    assert t.decide(_ctx(tuple(sorted(REFUSE_TOKENS)))) == 0
    # plain action vocab: first action wins (deterministic golden lane).
    assert t.decide(_ctx(("top", "bottom"))) == 0


def test_policies_stay_inside_the_vocabulary() -> None:
    """The illegal-action gate is the engine's, but a policy that COULD
    emit an out-of-range index would crash every game — assert neither
    scripted lane ever can, over many draws."""
    rnd, teacher = RandomAsk(seed=7), TeacherAsk()
    for size in (1, 2, 5):
        vocab = tuple(f"c{i}" for i in range(size))
        for _ in range(50):
            assert 0 <= rnd.decide(_ctx(vocab)) < size
            assert 0 <= teacher.decide(_ctx(vocab)) < size


def test_summarize_matchup_shape_and_gates() -> None:
    rec = {
        "seed": 1,
        "swap": False,
        "outcome": "a",
        "reason": "lose",
        "turns": 12,
        "crash": None,
        "illegal": 0,
        "journal_total": 30,
        "ask_log_total": 20,
        "auto_resolved": 10,
        "seat_stats": {
            "0": {
                "asks": 20,
                "v0": 5,
                "passes": 2,
                "illegal": 0,
                "model_errors": 0,
                "trunc": 0,
            },
            "1": {
                "asks": 10,
                "v0": 9,
                "passes": 0,
                "illegal": 0,
                "model_errors": 0,
                "trunc": 0,
            },
        },
    }
    m = summarize_matchup([rec], "ckpt.pt", "random")
    assert m["policy_wins"] == 1 and m["policy_losses"] == 0
    assert m["asks_auto_resolved"] == 10
    assert m["policy_asks"]["asks"] == 20  # seat 0 = policy at swap=False
    assert m["baseline_asks"]["v0_rate"] == 0.9
    lo, hi = wilson(1, 1)
    assert m["wilson_decisive"] == [round(lo, 4), round(hi, 4)]


@skip_unless_files(DEFAULT_POLICY)
def test_two_games_end_to_end(tmp_path) -> None:
    """The gate: two REAL games (one per baseline) run to completion and
    the JSON carries every charged metric key."""
    out = tmp_path / "ge_smoke.json"
    rc = main(
        [
            "--games",
            "1",
            "--workers",
            "1",
            "--device",
            "cpu",
            "--pool",
            "engine",
            "--turn-cap",
            "6",
            "--seed-base",
            "900001",
            "--out",
            str(out),
        ]
    )
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert set(data["matchups"]) == {"vs_random", "vs_teacher"}
    for m in data["matchups"].values():
        for key in (
            "policy_wins",
            "draws",
            "policy_losses",
            "avg_turns_played",
            "asks_presented",
            "asks_answered",
            "asks_auto_resolved",
            "illegal_action_attempts",
            "engine_exceptions",
            "policy_asks",
            "baseline_asks",
        ):
            assert key in m, key
        assert m["illegal_action_attempts"] == 0  # engine gate: 0-by-law
        assert m["asks_answered"] <= m["asks_presented"]
    for recs in data["records"].values():
        assert len(recs) == 1
        assert recs[0]["outcome"] in (
            "a",
            "b",
            "draw-stall",
            "draw-cap",
            "draw-other",
            "crash",
        )
