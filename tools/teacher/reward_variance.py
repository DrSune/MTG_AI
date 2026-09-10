"""Teacher reward variance, done with the clustering correction.

This SUPERSEDES tools/teacher/reward_noise.py. That script asked the right question and
got one number badly wrong: it treated the per-decision proxy observations inside a game
as independent. docs/METRICS.md Rail D (line 122) forbids exactly that:

    "Cluster by game. Decisions inside a game are massively autocorrelated through the
     recurrent state, the deck and the opponent. At a measured p50 of 2,173 decisions per
     game a naive per-decision CI is several-fold too narrow. This is the single most
     common way an RL dashboard lies."

Correcting it costs the per-decision proxy roughly an order of magnitude of its apparent
advantage. It is still better than the win-rate family; it is not 78x better.

This file adds four things the earlier study did not have:

  1. A cluster-correct proxy model: a per-game random effect plus AR(1) within the game.
  2. Two estimators the earlier study did not consider, one of which wins:
       - frozen-probe paired loss delta (the update's alignment with a global objective)
       - raw gradient magnitude (included to show it loses, and why)
  3. A GAMEABILITY test. Every estimator is scored twice: once on decks that differ in
     true teaching value, once on decks that differ only in a nuisance the Teacher can
     move for free (board width / decision count / chaos). The ratio is what a reward
     hacker gets paid.
  4. A POOLING calculation. The Teacher never has to consume one block's reward on its
     own. Per-block SNR is the wrong requirement; per-CARD SNR after pooling across
     blocks is the right one, and it is sqrt(blocks-containing-that-card) larger.

    python tools/teacher/reward_variance.py
    python tools/teacher/reward_variance.py --icc 0.2 --decisions 41
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------------------
# Measured constants. Sources named so they can be re-derived.
# ---------------------------------------------------------------------------------------

# reports/decision_counts_devbox.json, 24 games, random policy, current engine.
DECISIONS_PER_GAME_P50 = 2173
# Same file: PlayLand 0.8% + CastSpell 0.6% + DeclareAttacker 0.4% + DeclareBlocker 0.1%.
# Everything else is PassPriority (55.0%), mana taps (37.1%) and PassTurn (6.1%).
NONTRIVIAL_FRACTION = 0.019
NONTRIVIAL_PER_GAME = int(round(DECISIONS_PER_GAME_P50 * NONTRIVIAL_FRACTION))  # 41


@dataclass(frozen=True)
class Deck:
    """A matchup the Teacher proposed.

    tau    true teaching value: how much the Student's win rate rises over the block.
    kappa  nuisance the Teacher controls for free: board width, decision count, chaos.
           Moves every "the Student is thinking hard" proxy WITHOUT teaching anything.
    """
    name: str
    p0: float
    tau: float
    kappa: float = 0.0


# tau values are deliberately generous. Real within-block learning at a few hundred games
# in a mature run is smaller than the smallest of these.
LADDER = [
    Deck("unwinnable", 0.05, 0.004),
    Deck("too easy", 0.95, 0.008),
    Deck("even but dull", 0.50, 0.010),
    Deck("instructive", 0.42, 0.040),
    Deck("very instructive", 0.38, 0.080),
]

# Same true teaching value, different amounts of free nuisance. Any estimator that
# separates these is payable for doing nothing.
ATTACK = [
    Deck("plain", 0.50, 0.020, kappa=0.0),
    Deck("wide boards", 0.50, 0.020, kappa=0.5),
    Deck("wide + chaotic", 0.50, 0.020, kappa=1.0),
]


# ---------------------------------------------------------------------------------------
# Outcome model
# ---------------------------------------------------------------------------------------

def block_outcomes(d: Deck, n: int, rng, *, paired: bool, shared_frac: float) -> np.ndarray:
    """Per-game results in [0,1] for one block of n games.

    paired=True is the owner's "play both sides" with common random numbers on the
    shuffle: each game is played twice with seats swapped and the SAME shuffle, and the
    pair is averaged. shared_frac is the fraction of single-game outcome variance that is
    common to the mirrored pair (draw luck, mana screw, opening hands) and therefore
    cancels. Without common random numbers on the shuffle, shared_frac is ~0 and pairing
    buys nothing for a DELTA estimator, because a constant deck advantage differences out
    on its own.
    """
    t = (np.arange(n) + 0.5) / n
    p = np.clip(d.p0 + d.tau * t, 1e-3, 1 - 1e-3)
    if not paired:
        return rng.binomial(1, p).astype(float)
    z = np.log(p / (1 - p))
    # A shared latent that helps one seat exactly as much as it hurts the other.
    lam = np.sqrt(shared_frac / max(1e-9, 1 - shared_frac)) * 1.8
    s = rng.normal(0.0, 1.0, size=n)
    a = rng.binomial(1, 1 / (1 + np.exp(-(z + lam * s))))
    b = rng.binomial(1, 1 / (1 + np.exp(-(z - lam * s))))
    return (a + b) / 2.0


def est_halves(y: np.ndarray) -> float:
    """Second half minus first half, doubled so it estimates the change over the whole
    block and is therefore directly comparable with the slope."""
    h = len(y) // 2
    return 2.0 * float(y[h:].mean() - y[:h].mean())


def est_slope(y: np.ndarray) -> float:
    n = len(y)
    x = (np.arange(n) + 0.5) / n
    xc = x - x.mean()
    return float((xc * (y - y.mean())).sum() / (xc ** 2).sum())


def est_closeness(y: np.ndarray) -> float:
    return float(1.0 - 2.0 * abs(y.mean() - 0.5))


# ---------------------------------------------------------------------------------------
# Per-decision proxy, WITH the cluster structure
# ---------------------------------------------------------------------------------------

def proxy_game_means(d: Deck, n: int, rng, *, decisions: int, icc: float,
                     ar1: float, kappa_gain: float) -> np.ndarray:
    """Mean per-decision difficulty proxy for each of n games.

    z_gd = kappa_gain*kappa  -  tau*t_g  +  u_g  +  e_gd
      u_g ~ N(0, icc)                       per-GAME random effect: this deck, this
                                            game's draw, this game's board. Does NOT
                                            average away over decisions, only over games.
      e_gd AR(1) with coefficient ar1       within-game autocorrelation.

    Total per-decision variance is normalised to 1, so effects read as per-decision
    standard deviations.

    Effective independent decisions in a game: D_eff = decisions * (1-ar1)/(1+ar1).
    Variance of the game mean: icc + (1-icc)/D_eff.
    """
    d_eff = max(1.0, decisions * (1.0 - ar1) / (1.0 + ar1))
    var_game_mean = icc + (1.0 - icc) / d_eff
    t = (np.arange(n) + 0.5) / n
    mu = kappa_gain * d.kappa - d.tau * t
    return mu + rng.normal(0.0, np.sqrt(var_game_mean), size=n)


def design_effect(decisions: int, icc: float, ar1: float) -> float:
    d_eff = max(1.0, decisions * (1.0 - ar1) / (1.0 + ar1))
    naive = 1.0 / decisions
    true = icc + (1.0 - icc) / d_eff
    return true / naive


# ---------------------------------------------------------------------------------------
# Frozen-probe paired loss delta, and its degenerate cousin
# ---------------------------------------------------------------------------------------

def probe_delta(d: Deck, n: int, rng, *, gamma: float, kappa_gain: float) -> float:
    """R = eta * <grad L_probe(theta), grad L_block(theta)>, estimated over n games.

    To first order in the learning rate, the drop in loss on a FROZEN probe set caused by
    training on this block equals the inner product of the block's gradient with the
    probe's gradient. Two properties follow, and they are the reason this wins:

      * It is PAIRED on identical states, so state-sampling variance cancels by
        construction rather than in expectation. That is what removes the design effect.
      * It is an inner product, not a norm. A gradient made of pure noise has a large
        norm and zero expected alignment, so chaos is paid nothing.

    gamma is the per-GAME alignment signal-to-noise: (spread of mean alignment across
    decks of different teaching value) / (sd of one game's alignment). It is the one
    number here that must be MEASURED rather than assumed.
    """
    tau_spread = 0.03   # roughly the sd of tau across the ladder
    per_game = rng.normal(d.tau / tau_spread * gamma, 1.0, size=n)
    _ = kappa_gain      # nuisance is orthogonal to the probe direction: pays nothing
    return float(per_game.mean())


def grad_norm(d: Deck, n: int, rng, *, kappa_gain: float) -> float:
    """||g||^2 of the block's update. Included in order to be rejected.

    Magnitude is inflated by aleatoric noise, and the Teacher can manufacture aleatoric
    noise for free. This is the noisy-TV failure from curiosity-driven RL in a Magic hat.
    """
    base = 1.0 + 0.6 * d.tau / 0.03 + 2.0 * kappa_gain * d.kappa
    return float(rng.normal(base, 1.0, size=n).mean())


# ---------------------------------------------------------------------------------------

EST_NAMES = [
    "A win-rate halves (as proposed)",
    "B win-rate slope",
    "C slope + mirrored/CRN",
    "D closeness to 50%",
    "E per-decision proxy slope (clustered)",
    "F per-decision proxy slope (naive, WRONG)",
    "G frozen-probe paired delta",
    "H raw gradient magnitude",
]


def run_ladder(decks, n_games, trials, cfg, rng):
    ests = {k: {} for k in EST_NAMES}
    for d in decks:
        buf = {k: [] for k in ests}
        for _ in range(trials):
            y = block_outcomes(d, n_games, rng, paired=False, shared_frac=0.0)
            # EQUAL GAME BUDGET. A mirrored pair is two games, so n_games games buys
            # n_games/2 pairs. tools/teacher/reward_noise.py compared n pairs against n
            # single games, i.e. it gave the paired arm twice the games, and that
            # sqrt(2) is the whole of the "pairing helps" result it reported.
            yp = block_outcomes(d, max(2, n_games // 2), rng, paired=True,
                                shared_frac=cfg["shared_frac"])
            buf["A win-rate halves (as proposed)"].append(est_halves(y))
            buf["B win-rate slope"].append(est_slope(y))
            buf["C slope + mirrored/CRN"].append(est_slope(yp))
            buf["D closeness to 50%"].append(est_closeness(y))
            buf["E per-decision proxy slope (clustered)"].append(
                -est_slope(proxy_game_means(d, n_games, rng, decisions=cfg["decisions"],
                                            icc=cfg["icc"], ar1=cfg["ar1"],
                                            kappa_gain=cfg["kappa_gain"])))
            buf["F per-decision proxy slope (naive, WRONG)"].append(
                -est_slope(proxy_game_means(d, n_games, rng, decisions=cfg["decisions"],
                                            icc=0.0, ar1=0.0,
                                            kappa_gain=cfg["kappa_gain"])))
            buf["G frozen-probe paired delta"].append(
                probe_delta(d, n_games, rng, gamma=cfg["gamma"], kappa_gain=cfg["kappa_gain"]))
            buf["H raw gradient magnitude"].append(
                grad_norm(d, n_games, rng, kappa_gain=cfg["kappa_gain"]))
        for k, v in buf.items():
            ests[k][d.name] = np.array(v)
    return ests


def snr(per_deck):
    means = np.array([v.mean() for v in per_deck.values()])
    between = float(means.std())
    within = float(np.mean([v.std() for v in per_deck.values()]))
    return between, within, (between / within if within > 0 else float("inf"))


def rank_accuracy(per_deck, decks) -> float:
    """Spearman between the estimator's expected value and the true teaching value.

    SNR without this is worthless: an estimator can be very precise about the wrong
    quantity. "closeness to 50%" is exactly that failure and this column exposes it.
    """
    names = [d.name for d in decks]
    est = np.array([per_deck[n].mean() for n in names])
    true = np.array([d.tau for d in decks])

    def rk(v):
        order = np.argsort(np.argsort(v))
        return order.astype(float)

    a, b = rk(est), rk(true)
    a, b = a - a.mean(), b - b.mean()
    den = np.sqrt((a ** 2).sum() * (b ** 2).sum())
    return float((a * b).sum() / den) if den > 0 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, nargs="*", default=[20, 100, 400, 1000])
    ap.add_argument("--trials", type=int, default=2000)
    ap.add_argument("--decisions", type=int, default=DECISIONS_PER_GAME_P50)
    ap.add_argument("--icc", type=float, default=0.05,
                    help="per-game random effect share of per-decision variance")
    ap.add_argument("--ar1", type=float, default=0.9,
                    help="within-game autocorrelation of the proxy")
    ap.add_argument("--shared-frac", type=float, default=0.5,
                    help="fraction of outcome variance shared by a mirrored pair under CRN")
    ap.add_argument("--gamma", type=float, default=0.15,
                    help="[guess] per-game gradient-alignment SNR. MEASURE THIS.")
    ap.add_argument("--kappa-gain", type=float, default=0.4,
                    help="how strongly free nuisance moves a difficulty proxy")
    ap.add_argument("--seed", type=int, default=20260910)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()

    cfg = dict(decisions=a.decisions, icc=a.icc, ar1=a.ar1, shared_frac=a.shared_frac,
               gamma=a.gamma, kappa_gain=a.kappa_gain)
    rng = np.random.default_rng(a.seed)

    de = design_effect(a.decisions, a.icc, a.ar1)
    d_eff = a.decisions * (1 - a.ar1) / (1 + a.ar1)
    print("Teacher reward: variance, gameability, and how many games it takes.")
    print("")
    print(f"Per-decision clustering, at the measured {a.decisions} decisions/game:")
    print(f"  AR(1) rho = {a.ar1}  ->  effective independent decisions per game = {d_eff:.0f}")
    print(f"  per-game random effect ICC = {a.icc}")
    print(f"  DESIGN EFFECT = {de:.0f}x  ->  a game is worth "
          f"{a.decisions/de:.0f} independent decisions, not {a.decisions}")
    print(f"  any naive per-decision SNR is inflated by sqrt({de:.0f}) = {np.sqrt(de):.1f}x")
    print("")

    rows = {g: run_ladder(LADDER, g, a.trials, cfg, rng) for g in a.games}

    hdr = (f"{'estimator':<44}" + "".join(f"{'N=' + str(g):>9}" for g in a.games)
           + f"{'games@SNR3':>12}{'rank rho':>10}")
    print(hdr)
    print("-" * len(hdr))
    snr_table, rho_table = {}, {}
    for nm in EST_NAMES:
        line = f"{nm:<44}"
        ref = None
        for g in a.games:
            s = snr(rows[g][nm])[2]
            snr_table.setdefault(nm, {})[g] = s
            if g == 100:
                ref = s
            line += f"{s:>9.2f}"
        need = 100 * (3.0 / ref) ** 2 if ref and ref > 0 else float("inf")
        line += f"{need:>12,.0f}" if need < 1e9 else f"{'>1e9':>12}"
        rho = rank_accuracy(rows[max(a.games)][nm], LADDER)
        rho_table[nm] = rho
        line += f"{rho:>10.2f}"
        print(line)
    print("rank rho: Spearman(estimator, TRUE teaching value) at the largest N.")
    print("          A high SNR with a low rho is a precise measurement of the wrong thing.")

    print("")
    print("GAMEABILITY: same true teaching value, only the free nuisance varied.")
    print("payout ratio = spread the estimator gives for free nuisance")
    print("               / spread it gives for real teaching value, both at N=100.")
    print("")
    atk = run_ladder(ATTACK, 100, a.trials, cfg, rng)
    print(f"{'estimator':<44}{'free-nuisance payout ratio':>30}")
    print("-" * 74)
    game_ratio = {}
    for nm in EST_NAMES:
        b_att = snr(atk[nm])[0]
        b_real = snr(rows[100][nm])[0]
        r = b_att / b_real if b_real > 0 else float("inf")
        game_ratio[nm] = r
        flag = "   <-- reward hacking channel" if r > 0.5 else ""
        print(f"{nm:<44}{r:>30.2f}{flag}")

    print("")
    print("POOLING: the Teacher does not have to consume one block at a time.")
    print("Fit a critic (deck features -> reward) over a buffer of blocks. A card in a")
    print("100-card deck drawn from a pool of P appears in ~100*B/P blocks, and its")
    print("coefficient is estimated from all of them.")
    print("")
    P = 350
    print(f"{'blocks in buffer B':>20}{'blocks per card':>18}{'SNR multiplier':>17}"
          f"{'req. per-block SNR':>21}")
    print("-" * 76)
    for B in [100, 500, 2000, 10000]:
        per_card = 100 * B / P
        mult = np.sqrt(per_card)
        print(f"{B:>20,}{per_card:>18,.0f}{mult:>17.1f}{3.0 / mult:>21.3f}")

    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps({
            "config": {**cfg, "trials": a.trials, "seed": a.seed},
            "design_effect": de,
            "effective_decisions_per_game": d_eff,
            "snr": {k: {str(g): v for g, v in d.items()} for k, d in snr_table.items()},
            "gameability_payout_ratio": game_ratio,
            "rank_rho": rho_table,
            "ladder": [asdict(d) for d in LADDER],
        }, indent=1), encoding="utf-8")
        print("")
        print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
