"""Per-kind retention probe for r28's looks (PLAN_CEILING §14.4; KNOWLEDGE/2026-11-12/199).

    PYTHONPATH=. .venv/bin/python reports/r28_2026-11-12/kinds_split.py CKPT BATCH.pkl [--kinds K,...]

BATCH is one on-policy batch of CKPT (``learner --collect``). For the full update and for one
update per kind without that kind's rows (r27's settings, a fresh AdamW, minibatch generator 0,
the code's ``ppo.steps``), it measures on that kind's decisions the alignment of the change in the
taken action's log-probability with the action's normalised advantage:
    align = mean_i(A_i * dlogp_i) / mean_i(A_i^2)
The full update's alignment is the kind's learning; the update without its rows is the drift the
rest of the batch causes on it. A drift whose alignment is negative and comparable to the full
update's own pushes the kind against its own advantages: what eroded r27's mulligan (198).
"""
import argparse
import pickle
import time
from types import SimpleNamespace

import numpy as np
import torch

from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay.ppo import ppo_train

ap = argparse.ArgumentParser()
ap.add_argument("ckpt")
ap.add_argument("batch")
ap.add_argument("--kinds", default="mulligan,mulligan_bottom,priority,act,attack,block,target")
a = ap.parse_args()
dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")  # CPU: a dry run beside a training run
with open(a.batch, "rb") as fh:
    rows = pickle.load(fh)
n = len(rows)
feats = [r[0] for r in rows]
packed = M.pack(feats)
act = np.array([r[1] for r in rows], np.int64)
logp = np.array([r[2] for r in rows], np.float32)
v_old = np.array([r[3] for r in rows], np.float32)
adv = np.array([r[4] for r in rows], np.float32)
ret = np.array([r[5] for r in rows], np.float32)
adv_n = (adv - adv.mean()) / (adv.std() + 1e-8)
kind = packed.ask_i[:, 0].astype(np.int64)
kinds = [k for k in a.kinds.split(",") if (kind == FT.ASK_KINDS.index(k)).any()]
probe = {}
rng0 = np.random.default_rng(0)
for k in kinds:
    ix = np.flatnonzero(kind == FT.ASK_KINDS.index(k))
    probe[k] = ix if len(ix) <= 4000 else np.sort(rng0.choice(ix, 4000, replace=False))


def load():
    return M.load(a.ckpt, dev)[0].float().eval()


@torch.no_grad()
def taken_logp(net, ix):
    out = np.zeros(len(ix))
    for s in range(0, len(ix), 512):
        ch = ix[s:s + 512]
        logits, _ = net(M.collate_packed(packed, ch, dev))
        lp = torch.log_softmax(logits.float(), -1)
        out[s:s + 512] = lp.gather(1, torch.from_numpy(act[ch]).to(dev)[:, None]).squeeze(1).cpu().numpy()
    return out


def update(rows_ix):
    net = load()
    opt = torch.optim.AdamW(net.parameters(), lr=2e-5, betas=(0.9, 0.99), eps=1e-6, weight_decay=0.01)
    args = SimpleNamespace(mb=4096, tok_budget=98304, epochs=1, clip=0.2, vclip=0.5, vcoef=0.5, ent=0.004,
                           max_grad=1.0, target_kl=0.0)
    sub = packed if len(rows_ix) == n else M.pack([feats[i] for i in rows_ix])
    ppo_train(net, opt, packed=sub, act=act[rows_ix], logp=logp[rows_ix], v_old=v_old[rows_ix],
              adv=adv[rows_ix], ret=ret[rows_ix], a=args, device=dev, rng=np.random.default_rng(0),
              release=torch.cuda.empty_cache)
    return net.eval()


def align(ix, d):
    """The alignment and its bootstrap SE over the kind's probe decisions (500 resamples, seed 1:
    the spread over decisions, not over an update's own randomness)."""
    A = adv_n[ix]
    a0 = float((A * d).mean() / max((A * A).mean(), 1e-9))
    b = np.random.default_rng(1).integers(0, len(ix), (500, len(ix)))
    boot = (A[b] * d[b]).mean(1) / np.maximum((A[b] ** 2).mean(1), 1e-9)
    return f"{a0:+.4f} ({boot.std():.4f})"


base = load()
before = {k: taken_logp(base, ix) for k, ix in probe.items()}
del base
t0 = time.time()
full = update(np.arange(n))
after_full = {k: taken_logp(full, ix) for k, ix in probe.items()}
del full
torch.cuda.empty_cache()
print(f"rows {n}; full update {time.time() - t0:.0f} s")
print(f"{'kind':16s} {'n':>6s} {'align full (SE)':>18s} {'align without its rows (SE)':>28s} {'mean |dlogp| full':>18s}")
for k in kinds:
    ix = probe[k]
    keep = np.flatnonzero(kind != FT.ASK_KINDS.index(k))
    net = update(keep)
    d_wo = taken_logp(net, ix) - before[k]
    del net
    torch.cuda.empty_cache()
    d_full = after_full[k] - before[k]
    print(f"{k:16s} {len(ix):6d} {align(ix, d_full):>18s} {align(ix, d_wo):>28s} {np.abs(d_full).mean():18.4f}",
          flush=True)
