"""Scratch: KNOWLEDGE/2026-11-11/191 §7's mulligan read (M1-M3) from window 2's collect.

    PYTHONPATH=. .venv/bin/python mulligan_read.py COLLECT.pkl V0.pt LATEST.pt

The collect's rows are learner.py --collect tuples (feats, act, logp, v, adv, ret, gid, step,
steps) of v0 playing under r27's flags. A mulligan declaration's hand is the own-hand entities in
cards_i (zone column) and their Land flag in cards_f. v0's p(mulligan) is the logged behaviour
probability; both checkpoints are also run on CPU in fp32 (v0's as a check of the path, the
latest's as the comparison). Intervals: 2,000 bootstrap resamples of games.
"""
import pickle
import sys

import numpy as np
import torch

from tools.selfplay import features as FT
from tools.selfplay import model as M

collect, v0_path, latest_path = sys.argv[1:4]
with open(collect, "rb") as fh:
    rows = pickle.load(fh)
mk = FT.ASK_KINDS.index("mulligan")
rows = [r for r in rows if int(np.asarray(r[0]["ask_i"]).reshape(-1)[0]) == mk]
n = len(rows)
hz = FT.ZONE_INDEX[FT.ZONE_HAND]
size, lands, play, jm, pm, took, win, gid, void = (np.zeros(n, t) for t in
                                                   (int, int, bool, int, float, bool, bool,
                                                    np.int64, bool))
for i, r in enumerate(rows):
    f = r[0]
    ci, cf = np.asarray(f["cards_i"]), np.asarray(f["cards_f"], np.float32)
    hand = ci[:, 1] == hz
    size[i], lands[i] = hand.sum(), (cf[hand, FT.F_TYPE0] > 0.5).sum()
    play[i] = float(np.asarray(f["glob_f"], np.float32)[1]) > 0.5
    types = [FT.OPTION_TYPES[int(t)] for t in np.asarray(f["opts_i"])[:, 0]]
    assert sorted(types) == ["keep", "mulligan"], types
    jm[i] = types.index("mulligan")
    p = float(np.exp(r[2]))
    took[i] = r[1] == jm[i]
    pm[i] = p if took[i] else 1.0 - p
    win[i], gid[i] = r[5] > 0, r[6]
    # with gamma = lambda = 1 a decided game's return is its outcome, +-1 (0 for a mutual loss);
    # a void game's is the bootstrap value (learner._finish_train): not a win or a loss
    void[i] = r[5] not in (-1.0, 0.0, 1.0)


def forward(path: str) -> tuple[np.ndarray, dict]:
    net, table, _ = M.load(path, "cpu")
    net.eval()
    packed = M.pack([r[0] for r in rows])
    out = np.zeros(n)
    with torch.no_grad():
        for s in range(0, n, 1024):
            idx = np.arange(s, min(s + 1024, n))
            logits, _ = net(M.collate_packed(packed, idx, "cpu"))
            out[idx] = torch.softmax(logits, -1).numpy()[np.arange(len(idx)), jm[idx]]
    return out, table.to_json()


pm_v0, t_v0 = forward(v0_path)
pm_new, t_new = forward(latest_path)
assert t_v0 == t_new, "the two checkpoints' card tables differ"
d = np.abs(pm_v0 - pm)
print(f"mulligan declarations {n} in {len(np.unique(gid))} games; taken {took.mean():.4f}")
print(f"path check, v0 fp32 CPU against the logged bf16 p(mulligan): mean |diff| {d.mean():.4f},"
      f" max {d.max():.4f}")

ug, inv = np.unique(gid, return_inverse=True)
rng = np.random.default_rng(191)
W = np.stack([np.bincount(rng.integers(0, len(ug), len(ug)), minlength=len(ug))[inv]
              for _ in range(2000)]).astype(float)  # [B, n] row weights


def mean_ci(x: np.ndarray, sel: np.ndarray) -> str:
    if not sel.any():
        return "      —"
    w = W[:, sel]
    ws = w.sum(1)
    bs = np.where(ws > 0, (w * x[sel]).sum(1) / np.maximum(ws, 1e-9), np.nan)  # empty: skipped
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    return f"{x[sel].mean():.3f} [{lo:.3f}, {hi:.3f}]"


print(f"\n{'cell':14s} {'n':>6s} {'p(mull) v0 logged':>24s} {'latest':>24s} {'taken':>6s}"
      f" {'won':>6s}")
cells = [(f"7 cards, {k} lands", (size == 7) & (lands == k)) for k in range(8)]
cells += [(f"{s} cards", size == s) for s in (6, 5)] + [("4 or fewer", size <= 4)]
for name, sel in cells:
    if sel.any():
        print(f"{name:14s} {sel.sum():6d} {mean_ci(pm, sel):>24s} {mean_ci(pm_new, sel):>24s}"
              f" {took[sel].mean():6.3f} {win[sel].mean():6.3f}")
for k in (2, 5):
    for pl in (True, False):
        sel = (size == 7) & (lands == k) & (play == pl)
        print(f"7 cards, {k} lands, on the {'play' if pl else 'draw'}: n {sel.sum()}, v0"
              f" {mean_ci(pm, sel)}, latest {mean_ci(pm_new, sel)}")

seven = size == 7
print(f"\nM1 v0 p(mulligan), 7 cards with 3-4 lands: {mean_ci(pm, seven & (lands >= 3) & (lands <= 4))}")
print(f"M2 v0 p(mulligan), 7 cards with 0-1 land:  {mean_ci(pm, seven & (lands <= 1))}")


def auc_boot(score: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """Weighted Mann-Whitney AUC (ties count half) for each row of weights w [B, n]."""
    order = np.argsort(score, kind="mergesort")
    s, yy, ww = score[order], y[order].astype(float), w[:, order]
    grp = np.searchsorted(np.unique(s), s)
    g = grp.max() + 1
    out = np.zeros(len(ww))
    for b in range(len(ww)):
        wp = np.bincount(grp, weights=ww[b] * yy, minlength=g)
        wn = np.bincount(grp, weights=ww[b] * (1 - yy), minlength=g)
        below = np.cumsum(wn) - wn
        den = wp.sum() * wn.sum()
        out[b] = (wp * (below + 0.5 * wn)).sum() / den if den > 0 else np.nan
    return out


m3 = seven & ~void  # M3 reads results: a void game has none
print(f"   M3 declarations: {m3.sum()} (void games left out: {int((seven & void).sum())})")
one = np.ones((1, m3.sum()))
a = auc_boot(1 - pm[m3], win[m3], one)[0]
bs = auc_boot(1 - pm[m3], win[m3], W[:, m3])
print(f"M3 ROC-AUC of v0's p(keep) against the result, 7 cards: {a:.4f}"
      f" [{np.nanpercentile(bs, 2.5):.4f}, {np.nanpercentile(bs, 97.5):.4f}]")
a2 = auc_boot(1 - pm_new[m3], win[m3], one)[0]
print(f"   the latest network's p(keep), same declarations (games played by v0): {a2:.4f}")
