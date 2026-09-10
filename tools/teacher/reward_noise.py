"""How noisy is the Teacher's reward, really?

The Teacher is meant to be rewarded for building a deck the Student LEARNED from. The
natural signal is "how much did the Student's win rate rise over the games played against
this deck". The owner flagged the problem themselves:

    "I just think its quite a few games and it will be a noisy estimate that will then be
     noisy reward for the teacher."

This settles that with numbers instead of argument. It simulates a Student with a KNOWN
learning curve, runs each candidate reward estimator against it, and reports the
signal-to-noise ratio each one achieves.

Signal-to-noise here is the ratio that matters for training a Teacher:

    SNR = (spread of the estimator across decks of genuinely different teaching value)
          -------------------------------------------------------------------------
          (spread of the estimator across repeats of the SAME deck)

An SNR below 1 means the Teacher cannot tell a good deck from a bad one at all: the noise
between repeats of one deck exceeds the real difference between decks. Anything under
about 2 will train very slowly.

Nothing here touches the engine. It is a pure statistical model of the estimators, which
is the right level: the question is about estimator variance, not about Magic.

    python tools/teacher/reward_noise.py
    python tools/teacher/reward_noise.py --games 200 --trials 4000
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np


# --------------------------------------------------------------------------------------
# The model of a matchup
# --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Matchup:
    """One deck the Teacher built, described by what it does to the Student.

    p0     Student's win rate against this deck at the start of the block.
    lift   How much that win rate rises over the block. THIS is what the Teacher should
           be rewarded for: it is the amount the Student learned.
    """
    name: str
    p0: float
    lift: float

    def win_prob(self, t: float) -> float:
        """Win probability at fraction t through the block. Linear is fine; the estimators
        below are not sensitive to the shape, only to the total change."""
        return float(np.clip(self.p0 + self.lift * t, 0.001, 0.999))


# A realistic spread of what a Teacher might produce. The lift values are deliberately
# generous: real within-block learning over a few hundred games is small.
LADDER = [
    Matchup("unwinnable   (student crushed)", 0.05, 0.005),
    Matchup("too easy     (student crushes)", 0.95, 0.005),
    Matchup("even but dull", 0.50, 0.010),
    Matchup("instructive  (modest lift)", 0.42, 0.040),
    Matchup("very instructive", 0.38, 0.080),
]


def play_block(m: Matchup, n_games: int, rng: np.random.Generator,
               paired: bool = False) -> np.ndarray:
    """Simulate one block of n_games, returning per-game results in [0,1].

    paired=True models the owner's "play both sides" proposal: each deck pair is played
    twice with seats swapped and common random numbers, and the two results are averaged.
    That cancels the seat and draw luck the two games share, which is why it reduces
    variance without changing the mean.
    """
    t = (np.arange(n_games) + 0.5) / n_games
    p = np.array([m.win_prob(x) for x in t])
    if not paired:
        return rng.binomial(1, p).astype(float)

    # A shared latent per pair (deck/draw luck) that affects both seats in opposite
    # directions, plus independent noise. Averaging the mirrored pair removes the shared
    # part. rho is how much of the outcome variance is shared, i.e. cancellable.
    rho = 0.55
    shared = rng.normal(0.0, 1.0, size=n_games)
    z = np.log(p / (1 - p))
    a = rng.binomial(1, 1 / (1 + np.exp(-(z + rho * shared))))
    b = rng.binomial(1, 1 / (1 + np.exp(-(z - rho * shared))))
    return (a + b) / 2.0


# --------------------------------------------------------------------------------------
# Candidate estimators of "how much did the Student learn from this deck"
# --------------------------------------------------------------------------------------

def est_halves(results: np.ndarray) -> float:
    """The literal proposal: second-half win rate minus first-half."""
    h = len(results) // 2
    return float(results[h:].mean() - results[:h].mean())


def est_slope(results: np.ndarray) -> float:
    """Least-squares slope over the whole block, scaled to a per-block change.

    Uses every game rather than collapsing to two means, so it throws away far less
    information. This is the standard fix in the learning-progress literature.
    """
    n = len(results)
    x = (np.arange(n) + 0.5) / n
    xc = x - x.mean()
    denom = float((xc ** 2).sum())
    if denom == 0:
        return 0.0
    return float((xc * (results - results.mean())).sum() / denom)


def est_closeness(results: np.ndarray) -> float:
    """The owner's first instinct: reward decks that sit near a 50% win rate.

    Cheap and low variance, but it is a LEVEL not a CHANGE, so it cannot distinguish an
    instructive even matchup from a boring one. Included to quantify that trade.
    """
    return float(1.0 - 2.0 * abs(results.mean() - 0.5))


def est_proxy(m: Matchup, n_games: int, rng: np.random.Generator,
              per_game_decisions: int = 250, proxy_noise: float = 1.0) -> float:
    """The owner's own escape hatch, and the important one.

    "measurements like speed of action / confidence / reasoning passes can be proxies for
    how well it plays"

    These are PER-DECISION signals, so a single game yields hundreds of samples instead of
    one bit. Modelled here as: the Student's mean difficulty signal (reasoning passes, or
    policy entropy, or value spread) falls as it learns the matchup, and the estimator is
    the slope of that signal over the block.

    proxy_noise is the per-decision noise relative to the effect size, and 1.0 is a
    deliberately pessimistic setting: it assumes the signal is as noisy as it is large.
    """
    n_obs = n_games * per_game_decisions
    t = (np.arange(n_obs) + 0.5) / n_obs
    # Difficulty falls in proportion to what was learned.
    signal = -m.lift * t
    obs = signal + rng.normal(0.0, proxy_noise * 0.10, size=n_obs)
    xc = t - t.mean()
    return float(-(xc * (obs - obs.mean())).sum() / (xc ** 2).sum())


# --------------------------------------------------------------------------------------

def snr(per_deck: dict[str, np.ndarray]) -> tuple[float, float, float]:
    """Between-deck spread over within-deck spread."""
    means = np.array([v.mean() for v in per_deck.values()])
    between = float(means.std())
    within = float(np.mean([v.std() for v in per_deck.values()]))
    return between, within, (between / within if within > 0 else float("inf"))


def run(n_games: int, trials: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    ests: dict[str, dict[str, np.ndarray]] = {
        "halves (as proposed)": {}, "halves + paired": {},
        "slope": {}, "slope + paired": {},
        "closeness to 50%": {},
        "per-decision proxy slope": {},
    }
    for m in LADDER:
        buf = {k: [] for k in ests}
        for _ in range(trials):
            r = play_block(m, n_games, rng, paired=False)
            rp = play_block(m, n_games, rng, paired=True)
            buf["halves (as proposed)"].append(est_halves(r))
            buf["halves + paired"].append(est_halves(rp))
            buf["slope"].append(est_slope(r))
            buf["slope + paired"].append(est_slope(rp))
            buf["closeness to 50%"].append(est_closeness(r))
            buf["per-decision proxy slope"].append(est_proxy(m, n_games, rng))
        for k, v in buf.items():
            ests[k][m.name] = np.array(v)

    out = {"n_games": n_games, "trials": trials, "estimators": {}}
    for name, per_deck in ests.items():
        between, within, ratio = snr(per_deck)
        out["estimators"][name] = {
            "between_deck_spread": round(between, 5),
            "within_deck_noise": round(within, 5),
            "snr": round(ratio, 3),
            "per_deck_mean": {k: round(float(v.mean()), 4) for k, v in per_deck.items()},
        }
    return out


def main():
    ap = argparse.ArgumentParser(description="Teacher reward estimator noise study.")
    ap.add_argument("--games", type=int, nargs="*", default=[20, 100, 400],
                    help="block sizes to test (games per deck the Teacher proposes)")
    ap.add_argument("--trials", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=20260910)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()

    print("Teacher reward: can it tell a good deck from a bad one?")
    print("SNR = between-deck spread / within-deck noise. Below 1.0 the reward is useless.\n")
    hdr = f"{'estimator':<28}" + "".join(f"{'N=' + str(g):>12}" for g in a.games)
    print(hdr)
    print("-" * len(hdr))

    runs = {g: run(g, a.trials, a.seed) for g in a.games}
    names = list(runs[a.games[0]]["estimators"].keys())
    for nm in names:
        row = f"{nm:<28}"
        for g in a.games:
            row += f"{runs[g]['estimators'][nm]['snr']:>12.2f}"
        print(row)

    print("\nReading it:")
    print("  < 1.0   the Teacher cannot distinguish decks; the reward is noise")
    print("  1 - 2   trainable in principle, very slowly")
    print("  > 3     a usable training signal")
    print("\n'per-decision proxy slope' is the owner's own suggestion: reasoning passes,")
    print("confidence and action speed are emitted hundreds of times per game rather than")
    print("once, so the same block of games carries far more information about difficulty.")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps({"ladder": [asdict(m) for m in LADDER], "runs": runs},
                                    indent=1), encoding="utf-8")
        print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
