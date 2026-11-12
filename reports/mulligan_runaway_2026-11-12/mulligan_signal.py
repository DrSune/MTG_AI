"""Diagnostic (2026-11-12, r27's mulligan runaway): on v0's own on-policy collect, which way does
PPO's policy gradient push the mulligan, per hand cell? Per cell: declarations, mulligan share,
win rate after keep and after mulligan, mean raw advantage (R - V) by action, the value's mean,
and the PG direction on the mulligan logit, sum_i A_i (1[mull_i] - p_i) per declaration, with
the raw and the batch-normalised advantage (PPO's adv_n over every collected decision).
Run on the w2 tree: PYTHONPATH=. python mulligan_signal.py COLLECT.pkl"""
import pickle
import sys

import numpy as np

from tools.selfplay import features as FT

with open(sys.argv[1], "rb") as fh:
    rows = pickle.load(fh)
adv_all = np.array([r[4] for r in rows], np.float64)
mu, sd = adv_all.mean(), adv_all.std()
print(f"all decisions {len(rows)}: raw advantage mean {mu:+.4f} std {sd:.4f}")
mk = FT.ASK_KINDS.index("mulligan")
rows = [r for r in rows if int(np.asarray(r[0]["ask_i"]).reshape(-1)[0]) == mk]
hz = FT.ZONE_INDEX[FT.ZONE_HAND]
n = len(rows)
size, lands, took, ret, adv, val, pm = (np.zeros(n) for _ in range(7))
for i, r in enumerate(rows):
    f = r[0]
    ci, cf = np.asarray(f["cards_i"]), np.asarray(f["cards_f"], np.float32)
    hand = ci[:, 1] == hz
    size[i], lands[i] = hand.sum(), (cf[hand, FT.F_TYPE0] > 0.5).sum()
    types = [FT.OPTION_TYPES[int(t)] for t in np.asarray(f["opts_i"])[:, 0]]
    jm = types.index("mulligan")
    p = float(np.exp(r[2]))
    took[i] = r[1] == jm
    pm[i] = p if took[i] else 1 - p
    ret[i], adv[i], val[i] = r[5], r[4], r[3]
ok = np.isin(ret, (-1.0, 0.0, 1.0))
print(f"mulligan declarations {n} (void {int((~ok).sum())} left out)")
cells = [(f"7 cards, {k} lands", (size == 7) & (lands == k)) for k in range(8)]
cells += [(f"{s} cards", size == s) for s in (6, 5)] + [("4 or fewer", size <= 4)]
print(f"{'cell':14s} {'n':>6s} {'mull':>6s} {'win|keep':>9s} {'win|mull':>9s} {'A|keep':>8s} {'A|mull':>8s}"
      f" {'V':>7s} {'PG raw/n':>9s} {'PG norm/n':>10s} {'se':>7s}")
for name, sel in cells:
    sel = sel & ok
    if sel.sum() < 5:
        continue
    k, m = sel & (took == 0), sel & (took == 1)
    g_raw = adv[sel] * (took[sel] - pm[sel])
    g_n = ((adv[sel] - mu) / sd) * (took[sel] - pm[sel])
    wk = (ret[k] > 0).mean() if k.any() else np.nan
    wm = (ret[m] > 0).mean() if m.any() else np.nan
    print(f"{name:14s} {sel.sum():6d} {took[sel].mean():6.3f} {wk:9.3f} {wm:9.3f} "
          f"{adv[k].mean() if k.any() else np.nan:+8.3f} {adv[m].mean() if m.any() else np.nan:+8.3f} "
          f"{val[sel].mean():+7.3f} {g_raw.mean():+9.4f} {g_n.mean():+10.4f} {g_n.std() / np.sqrt(sel.sum()):7.4f}")
sel = ok
g_n = ((adv[sel] - mu) / sd) * (took[sel] - pm[sel])
print(f"all declarations: PG norm/n {g_n.mean():+.4f} (se {g_n.std() / np.sqrt(sel.sum()):.4f}); "
      "positive pushes the mulligan logit up")
