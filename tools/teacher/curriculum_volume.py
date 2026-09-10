"""How much volume does each kind of Teacher need? Curator vs bandit vs policy gradient.

The Teacher's job is to pick, each block, a deck for the Student to be trained against.
Its reward is a NOISY estimate of how much the Student learned. The question this settles
is not "which reward" (see proxy_clustering.py) but "which SEARCH ALGORITHM over deck
space", and how many blocks each needs before it beats picking at random.

Model of the world, deliberately simple and deliberately hostile:

  deck x in {0,1}^d            d structural knobs (colours, curve, interaction, threats)
  difficulty(x) = w . x        one fixed random projection
  V(x) = exp(-(difficulty(x) - frontier)^2 / 2s^2)      zone of proximal development
  mastery m_x rises each time x is trained on, and V_eff = V(x) * (1 - m_x)
  frontier advances in proportion to the learning actually delivered

So: repeating one good deck stops paying (mastery), an impossible or trivial deck never
paid (ZPD), and the target MOVES as the Student improves (non-stationarity). That is the
whole difficulty of automatic curriculum learning in eleven lines.

    python tools/teacher/curriculum_volume.py
"""
from __future__ import annotations
import argparse
import numpy as np

D = 16
CAND = 256


class World:
    def __init__(self, rng, s=0.9, adv=0.55, mast=0.34):
        self.rng = rng
        self.w = rng.normal(0, 1, D)
        self.w /= np.abs(self.w).sum() / D * 2.0
        self.frontier = float(self.w[self.w < 0].sum())      # start easy
        self.span = float(self.w[self.w > 0].sum()) - self.frontier
        self.frontier += 0.15 * self.span
        self.s = s * (self.span / 8)
        self.adv, self.mast = adv, mast
        self.mastery = {}

    def value(self, x):
        d = float(self.w @ x)
        return float(np.exp(-((d - self.frontier) ** 2) / (2 * self.s ** 2)))

    def train_on(self, x):
        key = x.tobytes()
        m = self.mastery.get(key, 0.0)
        v_eff = self.value(x) * (1.0 - m)
        self.mastery[key] = m + self.mast * (1.0 - m)
        self.frontier += self.adv * self.s * v_eff
        return v_eff


def observe(v_eff, snr, rng, spread=0.22):
    """A noisy estimate of the block's teaching value. `snr` is the estimator's
    between-deck spread over within-deck noise, i.e. the number proxy_clustering.py
    reports for each candidate reward."""
    return v_eff + rng.normal(0.0, spread / max(snr, 1e-6))


# ---------------------------------------------------------------------------- teachers

def t_uniform(w, T, snr, rng):
    return [w.train_on(rng.integers(0, 2, D)) for _ in range(T)]


def t_curator(w, T, snr, rng, B=24, p_mut=0.75, k=2):
    """PLR / ACCEL: keep an archive of high-scoring decks, replay-and-EDIT them
    (flip k knobs), re-score, evict the worst. No gradients, no model."""
    arch = []
    tot = []
    for _ in range(T):
        if arch and rng.random() < p_mut:
            pri = np.array([1.0 / (i + 1) for i in range(len(arch))])
            i = rng.choice(len(arch), p=pri / pri.sum())
            x = arch[i][1].copy()
            for j in rng.choice(D, size=k, replace=False):
                x[j] ^= 1
        else:
            x = rng.integers(0, 2, D)
        v = w.train_on(x)
        arch.append((observe(v, snr, rng), x))
        arch.sort(key=lambda r: -r[0])
        del arch[B:]
        arch = [(sc * 0.97, xx) for sc, xx in arch]   # staleness decay
        tot.append(v)
    return tot


def t_lints(w, T, snr, rng, lam=0.15):
    """Linear Thompson sampling over the knobs: a bandit that GENERALISES across
    decks instead of treating each deck as its own arm."""
    A = np.eye(D + 1)
    b = np.zeros(D + 1)
    tot = []
    for _ in range(T):
        Ainv = np.linalg.inv(A)
        th = rng.multivariate_normal(Ainv @ b, lam * lam * Ainv)
        C = rng.integers(0, 2, (CAND, D))
        Cf = np.hstack([C, np.ones((CAND, 1))])
        x = C[int(np.argmax(Cf @ th))]
        v = w.train_on(x)
        f = np.append(x, 1.0)
        A += np.outer(f, f)
        b += observe(v, snr, rng) * f
        tot.append(v)
    return tot


def t_reinforce(w, T, snr, rng, lr=0.25, quantile=False):
    """The Teacher as a full RL agent: a factored Bernoulli policy over the knobs,
    updated by REINFORCE with a moving baseline. `quantile=True` adds Graves 2017
    adaptive quantile rescaling, the standard fix for a drifting reward scale."""
    th = np.zeros(D)
    base = 0.0
    res = []
    tot = []
    for _ in range(T):
        p = 1 / (1 + np.exp(-th))
        x = (rng.random(D) < p).astype(np.int64)
        v = w.train_on(x)
        r = observe(v, snr, rng)
        if quantile:
            res.append(r)
            res = res[-200:]
            adv = 2.0 * (np.searchsorted(np.sort(res), r) / len(res)) - 1.0
        else:
            base = 0.9 * base + 0.1 * r
            adv = r - base
        th = np.clip(th + lr * adv * (x - p), -4, 4)
        tot.append(v)
    return tot


TEACHERS = {
    "uniform (null teacher)": t_uniform,
    "curator: archive + edit (PLR/ACCEL)": t_curator,
    "linear Thompson bandit": t_lints,
    "REINFORCE (teacher as RL agent)": t_reinforce,
    "REINFORCE + quantile rescale": lambda w, T, s, r: t_reinforce(w, T, s, r, quantile=True),
}


def oracle_total(seed, reps, T):
    out = []
    for r in range(reps):
        rng = np.random.default_rng(seed + r)
        w = World(rng)
        tot = 0.0
        for _ in range(T):
            C = rng.integers(0, 2, (CAND, D))
            best = max(range(CAND), key=lambda i: w.value(C[i]) *
                       (1 - w.mastery.get(C[i].tobytes(), 0.0)))
            tot += w.train_on(C[best])
        out.append(tot)
    return float(np.mean(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", type=int, default=300)
    ap.add_argument("--reps", type=int, default=120)
    ap.add_argument("--games-per-block", type=int, default=100)
    ap.add_argument("--seed", type=int, default=11)
    a = ap.parse_args()

    print("Cumulative teaching value delivered to the Student, by Teacher and by how")
    print("precise its reward estimator is. 1.00 = what an ORACLE teacher delivers.\n")
    print(f"{a.blocks} blocks x {a.games_per_block} games = "
          f"{a.blocks * a.games_per_block:,} games per run, {a.reps} runs averaged.\n")

    snrs = [0.29, 1.8, 4.2, 13.0]
    hdr = f"{'teacher':<38}" + "".join(f"{('SNR ' + str(s)):>13}" for s in snrs)
    print(hdr)
    print("-" * len(hdr))

    orc = oracle_total(a.seed, a.reps, a.blocks)
    for name, fn in TEACHERS.items():
        row = f"{name:<38}"
        for s in snrs:
            vals = []
            for r in range(a.reps):
                rng = np.random.default_rng(a.seed + r)
                vals.append(sum(fn(World(rng), a.blocks, s, rng)))
            row += f"{float(np.mean(vals)) / orc:>13.3f}"
        print(row)
    print("\nestimator legend: 0.29 = win-rate slope + paired both sides (measured);")
    print("1.8 = per-decision proxy slope once clustered by game; 4.2 = revisit-difference")
    print("across a 20k-game checkpoint gap; 13.0 = the unclustered proxy claim.")

    print("\n\nBlocks needed before the Teacher beats picking at random (SNR 1.8)\n")
    pts = [25, 50, 100, 200, 400]
    hdr2 = f"{'teacher':<38}" + "".join(f"{str(p) + ' blk':>12}" for p in pts)
    print(hdr2)
    print("-" * len(hdr2))
    for name in ["uniform (null teacher)", "curator: archive + edit (PLR/ACCEL)",
                 "linear Thompson bandit", "REINFORCE (teacher as RL agent)"]:
        fn = TEACHERS[name]
        row = f"{name:<38}"
        for T in pts:
            o = oracle_total(a.seed, a.reps, T)
            v = []
            for r in range(a.reps):
                rng = np.random.default_rng(a.seed + r)
                v.append(sum(fn(World(rng), T, 1.8, rng)))
            row += f"{float(np.mean(v)) / o:>12.3f}"
        print(row)
    print(f"\n1 block = {a.games_per_block} games. 400 blocks = "
          f"{400 * a.games_per_block:,} games.")


if __name__ == "__main__":
    main()
