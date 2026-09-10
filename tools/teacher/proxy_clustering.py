"""Does the per-decision proxy really buy 78x? Not once you cluster by game.

reports/TEACHER_REWARD_FINDINGS.md concluded that a per-decision difficulty proxy beats
win-rate delta by ~78x (SNR 13.22 vs 0.17 at N=100). That number comes from
tools/teacher/reward_noise.py:est_proxy, which draws n_games * 250 INDEPENDENT
observations. docs/METRICS.md Rail D says in terms that decisions inside a game are
"massively autocorrelated through the recurrent state, the deck and the opponent", and
that a naive per-decision CI is several-fold too narrow.

This script puts the intra-game correlation back and re-measures. It also adds the
second confound the original model omits: a WINDOW-LEVEL drift shock, because the Student
is improving against everything at once, so a proxy slope measured in window 1 is not
comparable with one measured in window 2.

    python tools/teacher/proxy_clustering.py
"""
from __future__ import annotations
import argparse, json
import numpy as np

LADDER = [  # same ladder as reward_noise.py
    ("unwinnable", 0.05, 0.005),
    ("too easy", 0.95, 0.005),
    ("even but dull", 0.50, 0.010),
    ("instructive", 0.42, 0.040),
    ("very instructive", 0.38, 0.080),
]


def proxy_slope(lift, n_games, rng, m=250, noise=0.10, icc=0.0, window_sd=0.0):
    """Slope of a per-decision difficulty proxy over a block.

    icc        share of the proxy's noise VARIANCE that is shared within a game.
               icc=0 reproduces reward_noise.py exactly.
    window_sd  a drift shock shared by every decision in the block, standing for the
               Student improving globally between the windows in which two different
               decks were evaluated.
    """
    t_game = (np.arange(n_games) + 0.5) / n_games
    sd_g = noise * np.sqrt(icc)
    sd_d = noise * np.sqrt(1.0 - icc)
    g_eff = rng.normal(0.0, sd_g, size=n_games)                  # one per game
    d_mean = rng.normal(0.0, sd_d / np.sqrt(m), size=n_games)    # mean of m decisions
    drift = rng.normal(0.0, window_sd)                           # one per block
    obs = -lift * t_game + g_eff + d_mean + drift * t_game
    xc = t_game - t_game.mean()
    return float(-(xc * (obs - obs.mean())).sum() / (xc ** 2).sum())


def winrate_slope(p0, lift, n_games, rng):
    t = (np.arange(n_games) + 0.5) / n_games
    p = np.clip(p0 + lift * t, 0.001, 0.999)
    r = rng.binomial(1, p).astype(float)
    xc = t - t.mean()
    return float((xc * (r - r.mean())).sum() / (xc ** 2).sum())


def snr(per_deck):
    means = np.array([v.mean() for v in per_deck.values()])
    within = float(np.mean([v.std() for v in per_deck.values()]))
    return float(means.std()) / within if within > 0 else float("inf")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=100)
    ap.add_argument("--trials", type=int, default=3000)
    ap.add_argument("--decisions", type=int, default=250)
    ap.add_argument("--seed", type=int, default=20260910)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    out = {"n_games": a.games, "decisions_per_game": a.decisions, "trials": a.trials}

    print(f"Block = {a.games} games x {a.decisions} decisions. {a.trials} repeats per deck.\n")

    # baseline: win-rate slope, for scale
    wr = {n: np.array([winrate_slope(p0, l, a.games, rng) for _ in range(a.trials)])
          for n, p0, l in LADDER}
    wr_snr = snr(wr)
    print(f"win-rate slope (game-level, 1 bit/game)          SNR {wr_snr:6.2f}")
    out["winrate_slope_snr"] = round(wr_snr, 3)

    print("\nper-decision proxy slope, by intra-game correlation (ICC):")
    print(f"{'ICC':>6}{'eff. indep. obs':>18}{'SNR':>9}{'x vs win rate':>16}")
    rows = []
    for icc in [0.0, 0.02, 0.05, 0.10, 0.20, 0.30, 0.50, 0.80]:
        per = {n: np.array([proxy_slope(l, a.games, rng, a.decisions, icc=icc)
                            for _ in range(a.trials)]) for n, p0, l in LADDER}
        s = snr(per)
        deff = 1 + (a.decisions - 1) * icc
        ess = a.games * a.decisions / deff
        rows.append({"icc": icc, "ess": round(ess), "snr": round(s, 3),
                     "x_vs_winrate": round(s / wr_snr, 1)})
        print(f"{icc:>6.2f}{ess:>18,.0f}{s:>9.2f}{s/wr_snr:>15.1f}x")
    out["by_icc"] = rows

    print("\nadding a window-level drift shock (Student improving globally between blocks),")
    print("at ICC = 0.20:")
    print(f"{'drift sd':>10}{'SNR':>9}{'x vs win rate':>16}")
    rows2 = []
    for wsd in [0.0, 0.01, 0.02, 0.05, 0.10]:
        per = {n: np.array([proxy_slope(l, a.games, rng, a.decisions, icc=0.20, window_sd=wsd)
                            for _ in range(a.trials)]) for n, p0, l in LADDER}
        s = snr(per)
        rows2.append({"window_sd": wsd, "snr": round(s, 3), "x_vs_winrate": round(s / wr_snr, 1)})
        print(f"{wsd:>10.3f}{s:>9.2f}{s/wr_snr:>15.1f}x")
    out["by_drift"] = rows2

    # the fix: evaluate C decks concurrently in one window and score by within-window
    # deviation from the window mean. The shared drift cancels exactly.
    print("\nfix: C candidate decks per window, scored as (slope - window mean slope).")
    print("     ICC 0.20, drift sd 0.05:")
    print(f"{'C decks/window':>16}{'SNR':>9}{'x vs win rate':>16}")
    rows3 = []
    names = [n for n, _, _ in LADDER]
    for C in [1, 2, 4, 8]:
        acc = {n: [] for n in names}
        for _ in range(a.trials):
            drift = rng.normal(0.0, 0.05)
            picks = rng.choice(len(LADDER), size=C, replace=True)
            sl = []
            for i in picks:
                _, _, l = LADDER[i]
                # inline: same drift for every deck in the window
                t = (np.arange(a.games) + 0.5) / a.games
                g = rng.normal(0.0, 0.10 * np.sqrt(0.20), size=a.games)
                d = rng.normal(0.0, 0.10 * np.sqrt(0.80) / np.sqrt(a.decisions), size=a.games)
                obs = -l * t + g + d + drift * t
                xc = t - t.mean()
                sl.append(float(-(xc * (obs - obs.mean())).sum() / (xc ** 2).sum()))
            sl = np.array(sl)
            centred = sl - sl.mean() if C > 1 else sl
            for j, i in enumerate(picks):
                acc[LADDER[i][0]].append(centred[j])
        per = {k: np.array(v) for k, v in acc.items() if len(v) > 30}
        s = snr(per)
        rows3.append({"decks_per_window": C, "snr": round(s, 3),
                      "x_vs_winrate": round(s / wr_snr, 1)})
        print(f"{C:>16}{s:>9.2f}{s/wr_snr:>15.1f}x")
    out["by_concurrency"] = rows3

    print(json.dumps(out, indent=1)[:0])
    return out


if __name__ == "__main__":
    main()
    revisit_vs_slope()


# ---------------------------------------------------------------------------------------
# The estimator that actually works: don't look for learning INSIDE the block.
# Replay the same deck with a much later checkpoint and difference two block MEANS.
# ---------------------------------------------------------------------------------------

def revisit_vs_slope(n_games=100, m=250, icc=0.20, noise=0.10, trials=4000,
                     gaps=(0, 200, 1000, 5000, 20000), tau=8000.0, seed=7):
    """Signal-to-noise of (mean now - mean at an earlier checkpoint) against the
    within-block slope, for a Student whose competence on a deck saturates as
    L * (1 - exp(-g/tau)) after g games of global training."""
    rng = np.random.default_rng(seed)
    sd_g, sd_d = noise * np.sqrt(icc), noise * np.sqrt(1 - icc)

    def block_mean(level):
        g = rng.normal(0, sd_g, size=n_games)
        d = rng.normal(0, sd_d / np.sqrt(m), size=n_games)
        return float(np.mean(level + g + d))

    def block_slope(L, g0):
        t = (np.arange(n_games) + 0.5) / n_games
        lvl = -L * (1 - np.exp(-(g0 + t * n_games) / tau))
        obs = lvl + rng.normal(0, sd_g, n_games) + rng.normal(0, sd_d / np.sqrt(m), n_games)
        xc = t - t.mean()
        return float(-(xc * (obs - obs.mean())).sum() / (xc ** 2).sum())

    print("\n\nrevisit-difference vs within-block slope")
    print("competence(g) = L*(1-exp(-g/%.0f)); L is the deck's true teaching value" % tau)
    print(f"block = {n_games} games, ICC = {icc}\n")
    print(f"{'estimator':<34}{'SNR':>9}{'x vs slope':>13}")
    res = []
    sl = {n: np.array([block_slope(L, 0.0) for _ in range(trials)]) for n, _, L in LADDER}
    s_sl = snr(sl)
    base = s_sl
    print(f"{'within-block slope (as proposed)':<34}{s_sl:>9.2f}{1.0:>12.1f}x")
    res.append({"estimator": "within-block slope", "snr": round(s_sl, 3), "x": 1.0})
    for gap in gaps[1:]:
        est = {}
        for n, _, L in LADDER:
            v = []
            for _ in range(trials):
                lvl0 = -L * (1 - np.exp(-0.0 / tau))
                lvl1 = -L * (1 - np.exp(-gap / tau))
                v.append(block_mean(lvl0) - block_mean(lvl1))
            est[n] = np.array(v)
        s = snr(est)
        print(f"{'revisit after ' + str(gap) + ' games':<34}{s:>9.2f}{s/base:>12.1f}x")
        res.append({"estimator": f"revisit_gap_{gap}", "snr": round(s, 3),
                    "x": round(s / base, 2)})
    return res

