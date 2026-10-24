"""Known values for the benchmark statistics."""

from __future__ import annotations

import math

import pytest

from MTG_bot.bench.stats import (
    bradley_terry,
    elo_from_score,
    paired_bootstrap,
    score_from_elo,
    sprt,
    wilson,
)


def test_wilson_known_values() -> None:
    lo, hi = wilson(5, 10)
    assert lo == pytest.approx(0.2366, abs=1e-4)
    assert hi == pytest.approx(0.7634, abs=1e-4)
    assert wilson(0, 0) == (0.0, 1.0)
    # the review's own anchor number: 157 wins in 157+242 decisive games
    lo, hi = wilson(157, 399)
    assert (round(lo, 3), round(hi, 3)) == (0.347, 0.442)  # = KNOWLEDGE/NUMBERS.md:3904


def test_elo_score_round_trip() -> None:
    assert elo_from_score(0.75) == pytest.approx(190.85, abs=0.01)  # 3:1 odds
    assert score_from_elo(elo_from_score(0.6)) == pytest.approx(0.6)
    assert elo_from_score(1.0) == math.inf and elo_from_score(0.0) == -math.inf


def test_paired_bootstrap_is_deterministic_and_brackets_the_mean() -> None:
    scores = [1.0, 0.5, 0.5, 1.0, 0.0, 0.5, 1.0, 1.0]
    mean, lo, hi = paired_bootstrap(scores, seed=3)
    assert mean == pytest.approx(0.6875)
    assert lo < mean < hi
    assert paired_bootstrap(scores, seed=3) == (mean, lo, hi)


def test_sprt_accepts_a_clear_edge_and_waits_on_no_variance() -> None:
    # 60 wins, 20 draws, 20 losses: mean 0.7, variance 0.16; LLR = 100*0.0715*0.3285/0.32
    result = sprt([1.0] * 60 + [0.5] * 20 + [0.0] * 20, 0, 50)
    assert result.llr == pytest.approx(7.34, abs=0.02)
    assert result.decision == "H1"
    assert sprt([0.5] * 50, 0, 50).decision == "continue"
    # an even record: LLR -1.70 after 100 games is not yet past ln(0.05/0.95) = -2.94; 200 is
    assert sprt([0.0] * 30 + [0.5] * 40 + [1.0] * 30, 0, 50).decision == "continue"
    assert sprt([0.0] * 60 + [0.5] * 80 + [1.0] * 60, 0, 50).decision == "H0"


def test_bradley_terry_recovers_a_three_to_one_record() -> None:
    games = [("a", "b", 1.0)] * 3 + [("a", "b", 0.0)]
    ratings = bradley_terry(games, anchor="b")
    assert ratings["b"] == 0.0
    assert ratings["a"] == pytest.approx(190.85, abs=0.01)


def test_bradley_terry_refuses_an_unbounded_rating() -> None:
    with pytest.raises(ValueError, match="MLE does not exist"):
        bradley_terry([("a", "b", 1.0)] * 5, anchor="b")
