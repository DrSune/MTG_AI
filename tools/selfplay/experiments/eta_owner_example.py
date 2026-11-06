"""The owner's 45/30/25 example (PLAN §1.4) under repeated distillation of per-world labels: the
share of R2 within the compared pair after 1,000 rounds, for several eta (search.mmd_target with
se = 0.5 / eta), and for hard labels.

    PYTHONPATH=<checkout> PY eta_owner_example.py
"""

from tools.selfplay.search import mmd_target

WORLDS = [(0.45, (1.0, -1.0)), (0.30, (-1.0, 1.0)), (0.25, (-1.0, 1.0))]


def distil(target, rounds=1000):
    p = [0.4, 0.4, 0.2]
    for _ in range(rounds):
        p = [sum(w * t for w, t in zip((w for w, _ in WORLDS), col))
             for col in zip(*(target(p, q) for _, q in WORLDS))]
    return round(p[1] / (p[0] + p[1]), 4)


for eta in (0.02, 0.05, 0.1, 0.25, 0.5, 1.0, 2.7):
    print("eta", eta, "R2 share", distil(lambda p, q, eta=eta: mmd_target(p, [0, 1], q, se=0.5 / eta)))
print("hard", distil(lambda p, q: [p[0] + p[1], 0.0, p[2]] if q[0] > q[1] else [0.0, p[0] + p[1], p[2]]))
