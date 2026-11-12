"""Which loss term moves the mulligan in one PPO update? (KNOWLEDGE 198; r27's mulligan runaway)

    PYTHONPATH=. .venv/bin/python reports/mulligan_runaway_2026-11-12/ablate.py CKPT BATCH.pkl [IDS]

IDS (optional, e.g. A,A1,A2,B) runs only those variants. ``ppo_train`` is the code's: before
the fix (KNOWLEDGE 198) its minibatches were length-sorted, after it every step is stratified.

BATCH is one on-policy batch of CKPT written by ``learner --collect`` (collect165.sh). Each
variant is one real ``ppo_train`` update from CKPT on the batch, with r27's settings and a fresh
AdamW as trainer.py builds it; every variant but the A repeats uses minibatch generator 0.
Measured before and after, in fp32: the mulligan option's logit minus keep's (the mulligan
"logit") at every mulligan declaration of the batch, by hand, and the KL(before || after) per ask
kind on up to 4,000 decisions of each kind.
"""
import pickle
import sys
import time
from types import SimpleNamespace

import numpy as np
import torch

from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay.ppo import ppo_train

ckpt, batch = sys.argv[1], sys.argv[2]
only = set(sys.argv[3].split(",")) if len(sys.argv) > 3 else None
dev = torch.device("cuda")
with open(batch, "rb") as fh:
    rows = pickle.load(fh)
n = len(rows)
feats = [r[0] for r in rows]
packed = M.pack(feats)
act = np.array([r[1] for r in rows], np.int64)
logp = np.array([r[2] for r in rows], np.float32)
v_old = np.array([r[3] for r in rows], np.float32)
adv = np.array([r[4] for r in rows], np.float32)
ret = np.array([r[5] for r in rows], np.float32)
kind = packed.ask_i.reshape(n, -1)[:, 0].astype(np.int64)
MK = FT.ASK_KINDS.index("mulligan")
mull = np.flatnonzero(kind == MK)
hz = FT.ZONE_INDEX[FT.ZONE_HAND]
size = np.zeros(len(mull), int)
lands = np.zeros(len(mull), int)
jm = np.zeros(len(mull), int)
for j, i in enumerate(mull):
    f = feats[i]
    ci, cf = np.asarray(f["cards_i"]), np.asarray(f["cards_f"], np.float32)
    hand = ci[:, 1] == hz
    size[j], lands[j] = hand.sum(), (cf[hand, FT.F_TYPE0] > 0.5).sum()
    jm[j] = [FT.OPTION_TYPES[int(t)] for t in np.asarray(f["opts_i"])[:, 0]].index("mulligan")
took = act[mull] == jm
print(f"rows {n}; mulligan declarations {len(mull)} in {len({r[6] for r in rows})} games, "
      f"taken {took.mean():.3f}; raw advantage mean {adv.mean():+.4f} std {adv.std():.4f}",
      flush=True)
CELLS = [("7 cards, 0-1 lands", (size == 7) & (lands <= 1)), ("7 cards, 2 lands", (size == 7) & (lands == 2)),
         ("7 cards, 3-4 lands", (size == 7) & (lands >= 3) & (lands <= 4)),
         ("7 cards, 5+ lands", (size == 7) & (lands >= 5)), ("6 cards", size == 6), ("5 or fewer", size <= 5)]
KINDS = ("mulligan", "mulligan_bottom", "priority", "act", "attack", "block", "target")
rng0 = np.random.default_rng(0)
probe = {k: np.flatnonzero(kind == FT.ASK_KINDS.index(k)) for k in KINDS}
probe = {k: (ix if len(ix) <= 4000 else np.sort(rng0.choice(ix, 4000, replace=False)))
         for k, ix in probe.items()}
probe["mulligan"] = mull


@torch.no_grad()
def logprobs(net, idx):
    out = []
    for s in range(0, len(idx), 512):
        ch = idx[s:s + 512]
        logits, _ = net(M.collate_packed(packed, ch, dev))
        lp = torch.log_softmax(logits.float(), -1)
        out.append(lp.cpu())
    width = max(t.shape[1] for t in out)
    return torch.cat([torch.nn.functional.pad(t, (0, width - t.shape[1]), value=-1e9) for t in out])


def mull_logit(lp):
    keep = 1 - jm  # two options: keep and mulligan
    r = torch.arange(len(mull))
    return (lp[r, torch.from_numpy(jm)] - lp[r, torch.from_numpy(keep)]).numpy()


def kl(lp0, lp1):
    p0 = lp0.exp()
    d = torch.where(lp0 > -1e8, lp0 - lp1, torch.zeros_like(lp0))
    return float((p0 * d).sum(-1).mean())


def load():
    return M.load(ckpt, dev)[0].float().eval()


net = load()
before = {k: logprobs(net, ix) for k, ix in probe.items()}
z0 = mull_logit(before["mulligan"])
p0 = 1 / (1 + np.exp(-z0))
print("before: p(mulligan) " + "; ".join(f"{name} {p0[sel].mean():.3f} (n {sel.sum()})"
                                         for name, sel in CELLS), flush=True)
del net
torch.cuda.empty_cache()
perm = adv.copy()
perm[mull] = np.random.default_rng(1).permutation(adv[mull])
not_mull = np.flatnonzero(kind != MK)
MB, PR = FT.ASK_KINDS.index("mulligan_bottom"), FT.ASK_KINDS.index("priority")
no_mull_prio = np.flatnonzero((kind != MK) & (kind != PR))
no_mull_bottom = np.flatnonzero((kind != MK) & (kind != MB))
# name, value coefficient, bonus, advantages, rows, minibatch generator seed
VARIANTS = [
    ("A  r27's loss", 0.5, 0.004, adv, None, 0),
    ("A1 r27's loss, minibatch order 1", 0.5, 0.004, adv, None, 1),
    ("A2 r27's loss, minibatch order 2", 0.5, 0.004, adv, None, 2),
    ("B  policy term only", 0.0, 0.0, adv, None, 0),
    ("C  value term only (advantages 0)", 0.5, 0.0, np.zeros_like(adv), None, 0),
    ("D  bonus only (advantages 0, value 0)", 0.0, 0.004, np.zeros_like(adv), None, 0),
    ("E  r27's loss without the mulligan declarations", 0.5, 0.004, adv, not_mull, 0),
    ("F  policy term only, mulligan advantages permuted among themselves", 0.0, 0.0, perm, None, 0),
    ("E1 as E, minibatch order 1", 0.5, 0.004, adv, not_mull, 1),
    ("E4 as E, without the priority asks too", 0.5, 0.004, adv, no_mull_prio, 0),
    ("E5 as E, without the bottom choices too", 0.5, 0.004, adv, no_mull_bottom, 0),
]
for name, vcoef, ent, A, idx, seed in VARIANTS:
    if only and name.split()[0] not in only:
        continue
    t0 = time.time()
    net = load()
    opt = torch.optim.AdamW(net.parameters(), lr=2e-5, betas=(0.9, 0.99), eps=1e-6, weight_decay=0.01)
    a = SimpleNamespace(mb=4096, tok_budget=98304, epochs=1, clip=0.2, vclip=0.5, vcoef=vcoef, ent=ent,
                        max_grad=1.0, target_kl=0.0)
    ix = np.arange(n) if idx is None else idx
    sub = packed if idx is None else M.pack([feats[i] for i in ix])
    st = ppo_train(net, opt, packed=sub, act=act[ix], logp=logp[ix], v_old=v_old[ix], adv=A[ix],
                   ret=ret[ix], a=a, device=dev, rng=np.random.default_rng(seed),
                   release=torch.cuda.empty_cache)
    net.eval()
    after = {k: logprobs(net, ix2) for k, ix2 in probe.items()}
    dz = mull_logit(after["mulligan"]) - z0
    p1 = 1 / (1 + np.exp(-(z0 + dz)))
    print(f"\n{name}  [{st['minibatches']} steps, {st.get('micro', st['minibatches'])} micro-batches, gn {st['gn']}, logged kl {st['kl']}, "
          f"{time.time() - t0:.0f} s]")
    print(f"  mulligan logit change: mean {dz.mean():+.4f} (sd {dz.std():.4f}); by hand: "
          + "; ".join(f"{nm} {dz[sel].mean():+.3f}" for nm, sel in CELLS))
    print("  p(mulligan) after: " + "; ".join(f"{nm} {p1[sel].mean():.3f}" for nm, sel in CELLS))
    print("  KL(before || after) by kind: " + "  ".join(
        f"{k} {kl(before[k], after[k]):.5f}" for k in KINDS), flush=True)
    del net, opt
    torch.cuda.empty_cache()
