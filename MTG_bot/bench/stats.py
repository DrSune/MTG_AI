"""Statistics for comparing agents (docs/DESIGN_BENCHMARK.md §6).

What the review found missing (docs/REVIEW_2026-10-24.md A-2): best-of-k selection quoted as a
result, unpaired seeds, draws and crashes dropped from the denominator, no sequential test. Here:

- ``wilson``: interval for a proportion; ``elo_from_score`` maps a score to an Elo difference.
- ``paired_bootstrap``: CI over **deals**, the unit of a duplicate match. Resampling single
  games would treat the two halves of a pair as independent and understate the interval.
- ``sprt``: a sequential test of "A is at least elo1 stronger" vs "at most elo0", using the normal
  approximation on pair scores as chess-engine testing does. It stops as soon as the evidence
  suffices, which is the main cost lever for expensive LLM games.
- ``bradley_terry``: ratings from any game graph (anchors and LLM-vs-LLM together), by the MM
  algorithm, anchored so a named agent is 0 Elo. If the maximum-likelihood estimate does not
  exist (an agent never lost or never won), it raises rather than regularising silently.

Intervals are always printed. Whether a number is confirmatory is decided by a pre-registration
file, not by a minimum-n refusal, so there is no hidden threshold here.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def elo_from_score(score: float) -> float:
    """Elo difference implied by an expected score; infinite at 0 and 1, never clipped."""
    if score <= 0.0:
        return -math.inf
    if score >= 1.0:
        return math.inf
    return 400.0 * math.log10(score / (1.0 - score))


def score_from_elo(elo: float) -> float:
    return 1.0 / (1.0 + 10.0 ** (-elo / 400.0))


def paired_bootstrap(
    scores: Sequence[float], *, n_boot: int = 2000, seed: int = 0, level: float = 0.95
) -> tuple[float, float, float]:
    """(mean, lo, hi) of per-deal pair scores, by percentile bootstrap over deals."""
    x = np.asarray(scores, dtype=float)
    if x.size == 0:
        return (math.nan, math.nan, math.nan)
    gen = np.random.default_rng(seed)  # explicit seed: a pure function of its inputs
    means = x[gen.integers(0, x.size, size=(n_boot, x.size))].mean(axis=1)
    tail = (1.0 - level) / 2.0
    return (float(x.mean()), float(np.quantile(means, tail)), float(np.quantile(means, 1 - tail)))


@dataclass(frozen=True)
class SprtResult:
    llr: float
    lower: float
    upper: float
    decision: str  # "H1" (A is at least elo1 stronger), "H0" (at most elo0), "continue"
    n: int


def sprt(
    scores: Sequence[float], elo0: float, elo1: float, *, alpha: float = 0.05, beta: float = 0.05
) -> SprtResult:
    x = np.asarray(scores, dtype=float)
    lower, upper = math.log(beta / (1 - alpha)), math.log((1 - beta) / alpha)
    if x.size == 0:
        return SprtResult(0.0, lower, upper, "continue", 0)
    mean, var = float(x.mean()), float(x.var())
    if var == 0.0:  # the normal approximation is undefined; collect more pairs
        return SprtResult(0.0, lower, upper, "continue", int(x.size))
    s0, s1 = score_from_elo(elo0), score_from_elo(elo1)
    llr = x.size * (s1 - s0) * (2 * mean - s0 - s1) / (2 * var)
    decision = "H1" if llr >= upper else "H0" if llr <= lower else "continue"
    return SprtResult(float(llr), lower, upper, decision, int(x.size))


def bradley_terry(
    games: Iterable[tuple[str, str, float]],
    *,
    anchor: str,
    iters: int = 10_000,
    tol: float = 1e-12,
) -> dict[str, float]:
    """Elo ratings from ``(a, b, score_of_a)`` games (draws are 0.5), anchored at ``anchor`` = 0."""
    wins: dict[str, float] = defaultdict(float)
    pairs: dict[tuple[str, str], float] = defaultdict(float)
    players: set[str] = set()
    for a, b, s in games:
        players |= {a, b}
        wins[a] += s
        wins[b] += 1.0 - s
        pairs[(a, b) if a <= b else (b, a)] += 1.0
    if anchor not in players:
        raise ValueError(f"anchor {anchor!r} played no games")
    for p in players:
        played = sum(n for (x, y), n in pairs.items() if p in (x, y))
        if wins[p] <= 0.0 or wins[p] >= played:
            raise ValueError(f"MLE does not exist: {p!r} scored {wins[p]} of {played}; ratings are unbounded")
    strength = dict.fromkeys(players, 1.0)
    for _ in range(iters):
        new = {}
        for p in players:
            den = sum(
                n / (strength[p] + strength[q])
                for (x, y), n in pairs.items()
                if p in (x, y)
                for q in [y if x == p else x]
            )
            new[p] = wins[p] / den
        norm = math.exp(sum(math.log(v) for v in new.values()) / len(new))
        new = {p: v / norm for p, v in new.items()}
        delta = max(abs(math.log(new[p] / strength[p])) for p in players)
        strength = new
        if delta < tol:
            break
    return {p: 400.0 * math.log10(strength[p] / strength[anchor]) for p in sorted(players)}
