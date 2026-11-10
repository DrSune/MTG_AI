"""Scratch (not repo code): which loss term lowers the policy entropy in one PPO update at v0?

    ent_ablation.py SET CKPT TRAIN_A.pkl TRAIN_B.pkl HELDOUT.pkl      (SET: 1 or 2)

One real ``ppo_train`` update (r25's settings, fresh AdamW as trainer.py builds it) on the train
rows, per variant, each from the same checkpoint and (but for A2) the same minibatch order.
Measured on fixed states before and after: mean policy entropy, KL(before || after), share of
decisions whose top choice changed, value bias and explained variance. Held-out rows are games
the update never saw. Set 2 adds the controls: advantages permuted over the rows (no link left
between action and outcome), two more bonus sizes, and the update split into two calls on one
optimizer (what the first 11 steps of a fresh AdamW do against the next 11).
"""
import pickle
import random
import sys
import time
from types import SimpleNamespace

import numpy as np
import torch

from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay.ppo import ppo_train

which, ckpt, files = sys.argv[1], sys.argv[2], sys.argv[3:]
dev = torch.device("cuda")
rows, n_train, n_first = [], 0, 0
for j, f in enumerate(files):
    with open(f, "rb") as fh:
        rows += pickle.load(fh)["rows"]
    if j == 0:
        n_first = len(rows)
    if j < len(files) - 1:
        n_train = len(rows)
n = len(rows)
feats = [{k: np.asarray(v) for k, v in r["feats"].items()} for r in rows]
packed_all = M.pack(feats)
z = np.array([r["z"] for r in rows], dtype=np.float32)
v0 = np.array([r["v"] for r in rows], dtype=np.float32)
logp = np.array([r["logp"] for r in rows], dtype=np.float32)
act = np.array([r["act"] for r in rows], dtype=np.int64)
kind = packed_all.ask_i.reshape(n, -1)[:, 0].astype(np.int64)
held = np.arange(n) >= n_train
print(f"rows {n}: train {n_train}, held-out {n - n_train}", flush=True)

L = packed_all.lengths() + 3
order = np.argsort(L, kind="stable")
ev_chunks, cur, cur_max = [], [], 0
for i in order:
    if cur and (len(cur) >= 4096 or (len(cur) + 1) * max(cur_max, int(L[i])) > 98304):
        ev_chunks.append(np.array(cur))
        cur, cur_max = [], 0
    cur.append(i)
    cur_max = max(cur_max, int(L[i]))
ev_chunks.append(np.array(cur))


@torch.no_grad()
def measure(net):
    """Per row: entropy, top choice, value; per chunk: the log-probabilities (CPU)."""
    H = np.empty(n, np.float32)
    top = np.empty(n, np.int64)
    val = np.empty(n, np.float32)
    lps = []
    for ch in ev_chunks:
        b = M.collate_packed(packed_all, ch, dev)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            logits, v = net(b)
        lp = torch.log_softmax(logits.float(), -1)
        ok = b["opt_mask"]
        lp = torch.where(ok, lp, torch.full_like(lp, -1e9))
        H[ch] = -(lp.exp() * torch.where(ok, lp, torch.zeros_like(lp))).sum(-1).cpu().numpy()
        top[ch] = lp.argmax(-1).cpu().numpy()
        val[ch] = v.float().cpu().numpy()
        lps.append(lp.cpu())
        del b, logits, v
    return H, top, val, lps


def kl_rows(lps0, lps1):
    out = np.empty(n, np.float32)
    for ch, a0, a1 in zip(ev_chunks, lps0, lps1):
        p0 = a0.exp()
        d = torch.where(a0 > -1e8, a0 - a1, torch.zeros_like(a0))
        out[ch] = (p0 * d).sum(-1).numpy()
    return out


def ev_of(val, m):
    return 1 - np.var(z[m] - val[m]) / np.var(z[m])


net, _table, _ = M.load(ckpt, dev)
net.eval()
H0, top0, val0, lps0 = measure(net)
del net
torch.cuda.empty_cache()
print(f"before: entropy train {H0[~held].mean():.5f} held-out {H0[held].mean():.5f}; "
      f"value bias held-out {np.mean(val0[held] - z[held]):+.4f}, ev {ev_of(val0, held):.4f}", flush=True)

KINDS = ("act", "attack", "block", "target", "act_second_main", "one_of", "choose", "discard")
ALL = np.arange(n_train)
FIRST, SECOND = np.arange(n_first), np.arange(n_first, n_train)
# name, value coefficient, bonus, advantages (real | zero | perm), minibatch-order seed, calls
SETS = {
    "1": [
        ("A  r25: value 0.5, bonus 0", 0.5, 0.0, "real", 0, [ALL]),
        ("A2 same, other minibatch order", 0.5, 0.0, "real", 1, [ALL]),
        ("B  bonus 0.002", 0.5, 0.002, "real", 0, [ALL]),
        ("C  policy term only (value 0)", 0.0, 0.0, "real", 0, [ALL]),
        ("D  value term only (adv = 0)", 0.5, 0.0, "zero", 0, [ALL]),
        ("E  value 0.05, bonus 0", 0.05, 0.0, "real", 0, [ALL]),
        ("F  bonus 0.02", 0.5, 0.02, "real", 0, [ALL]),
    ],
    "2": [
        ("G  policy term only, advantages permuted", 0.0, 0.0, "perm", 0, [ALL]),
        ("H5 bonus 0.005", 0.5, 0.005, "real", 0, [ALL]),
        ("H10 bonus 0.01", 0.5, 0.01, "real", 0, [ALL]),
        ("W  r25's loss in two calls: first file, then second", 0.5, 0.0, "real", 0, [FIRST, SECOND]),
        ("W2 r25's loss in two calls: second file, then first", 0.5, 0.0, "real", 0, [SECOND, FIRST]),
    ],
}
for name, vcoef, entc, adv_mode, seed, calls in SETS[which]:
    t0 = time.time()
    net, _table, _ = M.load(ckpt, dev)
    net.eval()
    opt = torch.optim.AdamW(net.parameters(), lr=2e-5, betas=(0.9, 0.99), eps=1e-6, weight_decay=0.01)
    a = SimpleNamespace(mb=4096, tok_budget=98304, epochs=1, clip=0.2, vclip=0.5, vcoef=vcoef,
                        ent=entc, max_grad=1.0, target_kl=0.0)
    np.random.seed(seed)
    random.seed(seed)
    Hp, topp, lpsp = H0, top0, lps0
    for c, idx in enumerate(calls):
        adv = z[idx] - v0[idx]
        if adv_mode == "zero":
            adv = np.zeros(len(idx), np.float32)
        elif adv_mode == "perm":
            adv = np.random.default_rng(123).permutation(adv)
        st = ppo_train(net, opt, packed=M.pack([feats[i] for i in idx]), act=act[idx], logp=logp[idx],
                       v_old=v0[idx], adv=adv, ret=z[idx], a=a, device=dev,
                       release=torch.cuda.empty_cache)
        H1, top1, val1, lps1 = measure(net)
        kl = kl_rows(lpsp, lps1)
        dH = H1 - Hp
        call = f" call {c + 1}" if len(calls) > 1 else ""
        print(f"\n{name}{call}  [{st['minibatches']} steps, gn {st['gn']}, logged kl {st['kl']}, {time.time() - t0:.0f}s]")
        print(f"  entropy change: held-out {dH[held].mean():+.5f}  train {dH[~held].mean():+.5f}")
        print(f"  KL(before||after): held-out {kl[held].mean():.5f}  train {kl[~held].mean():.5f}")
        print(f"  top choice changed: held-out {np.mean(top1[held] != topp[held]):.4f}  train {np.mean(top1[~held] != topp[~held]):.4f}")
        print(f"  value held-out: bias {np.mean(val1[held] - z[held]):+.4f}  ev {ev_of(val1, held):.4f}")
        print("  held-out entropy change by ask kind: " + "  ".join(
            f"{k} {dH[held & (kind == FT.ASK_KINDS.index(k))].mean():+.4f}" for k in KINDS), flush=True)
        Hp, topp, lpsp = H1, top1, lps1
    del net, opt
    torch.cuda.empty_cache()
