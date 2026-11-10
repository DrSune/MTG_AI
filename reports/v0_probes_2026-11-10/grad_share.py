"""Scratch (not repo code): what v0's own on-policy rows say.

    grad_share.py CKPT ppo_0.pkl ppo_1.pkl ...

1. Decision statistics: entropy by ask kind, option types offered and chosen at act asks,
   the advantage of off-choice samples (the "sharpen" signal), mulligan choices.
2. Gradients at v0 of the three loss terms (policy, 0.5 x value, 0.002 x entropy) with respect to
   the shared trunk: norms per minibatch, norms of the whole-buffer mean, cosines.
"""
import pickle
import sys
from collections import Counter, defaultdict

import numpy as np
import torch

from tools.selfplay import features as FT
from tools.selfplay import model as M

ckpt, files = sys.argv[1], sys.argv[2:]
rows, n_games = [], 0
for f in files:
    with open(f, "rb") as fh:
        part = pickle.load(fh)["rows"]
    n_games += len({r["gid"] for r in part})
    rows += part
n = len(rows)
z = np.array([r["z"] for r in rows], dtype=np.float32)
v = np.array([r["v"] for r in rows], dtype=np.float32)
logp = np.array([r["logp"] for r in rows], dtype=np.float32)
ent = np.array([r["ent"] for r in rows], dtype=np.float32)
adv = z - v
adv_n = (adv - adv.mean()) / (adv.std() + 1e-8)
print(f"rows {n}  games {n_games}  mean ent {ent.mean():.4f}  "
      f"ev {1 - np.var(z - v) / np.var(z):.3f}  adv std {adv.std():.3f}  mean z {z.mean():+.3f}")

# ---- 1. decision statistics
kind = np.array([int(np.asarray(r["feats"]["ask_i"]).reshape(-1)[0]) for r in rows])
p_chosen = np.exp(logp)
print("\nask kind: share, mean options, mean entropy, share of samples off the top choice (p < 0.5), "
      "mean advantage on / off the top choice")
for k, c in Counter(kind.tolist()).most_common():
    m = kind == k
    nopt = np.mean([rows[i]["feats"]["opts_i"].shape[0] for i in np.flatnonzero(m)[:4000]])
    off = m & (p_chosen < 0.5)
    on = m & (p_chosen >= 0.5)
    print(f"  {FT.ASK_KINDS[k]:16s} {c / n:6.3f}  opts {nopt:5.1f}  ent {ent[m].mean():.3f}  off {off.sum() / max(m.sum(), 1):.3f}  "
          f"adv on {adv[on].mean() if on.any() else float('nan'):+.4f}  off {adv[off].mean() if off.any() else float('nan'):+.4f}")
off = p_chosen < 0.5
print(f"all kinds: off-choice share {off.mean():.4f}; mean advantage on {adv[~off].mean():+.4f} "
      f"(se {adv[~off].std() / np.sqrt((~off).sum()):.4f}), off {adv[off].mean():+.4f} "
      f"(se {adv[off].std() / np.sqrt(off.sum()):.4f})")
# by position in the game
pos = np.array([r["i"] / max(r["n"] - 1, 1) for r in rows])
for lo, hi in ((0, 0.25), (0.25, 0.5), (0.5, 0.75), (0.75, 1.01)):
    m = (pos >= lo) & (pos < hi)
    print(f"  game quarter {lo:.2f}-{hi:.2f}: ent {ent[m].mean():.3f}  |adv| {np.abs(adv[m]).mean():.3f}  ev {1 - np.var(z[m] - v[m]) / np.var(z[m]):.3f}")

act_kinds = {i for i, k in enumerate(FT.ASK_KINDS) if k in ("act", "act_second_main")}
offered, chosen, asks = Counter(), Counter(), 0
for r in rows:
    if int(np.asarray(r["feats"]["ask_i"]).reshape(-1)[0]) not in act_kinds:
        continue
    asks += 1
    types = np.asarray(r["feats"]["opts_i"])[:, 0]
    for t in set(types.tolist()):
        offered[FT.OPTION_TYPES[t]] += 1
    chosen[FT.OPTION_TYPES[int(types[r["act"]])]] += 1
print(f"\nact asks {asks}: option type, share of asks offering it, share of asks choosing it, chosen when offered")
for t, c in offered.most_common():
    print(f"  {t:14s} offered {c / asks:.3f}  chosen {chosen[t] / asks:.3f}  chosen|offered {chosen[t] / c:.3f}")
mull = [r for r in rows if FT.ASK_KINDS[int(np.asarray(r["feats"]["ask_i"]).reshape(-1)[0])] == "mulligan"]
if mull:
    took = Counter(FT.OPTION_TYPES[int(np.asarray(r["feats"]["opts_i"])[r["act"], 0])] for r in mull)
    print(f"mulligan asks {len(mull)}: {dict(took)}; mean p(chosen) {np.mean([np.exp(r['logp']) for r in mull]):.3f}")

# ---- 2. gradients at v0
dev = torch.device("cuda")
net, _table, _ = M.load(ckpt, dev)
net.eval()
names = [k for k, p in net.named_parameters() if p.requires_grad]
params = [p for _, p in net.named_parameters() if p.requires_grad]
trunk = [not (k.startswith("policy_head") or k.startswith("value_head")) for k in names]
print(f"\nparameters {sum(p.numel() for p in params):,}; trunk {sum(p.numel() for p, t in zip(params, trunk) if t):,}")


def flat(gs):
    return torch.cat([(g if g is not None else torch.zeros_like(p)).reshape(-1).float()
                      for g, p, t in zip(gs, params, trunk) if t])


lengths = np.array([r["feats"]["cards_i"].shape[0] + r["feats"]["opts_i"].shape[0] + 3 for r in rows])
order = np.argsort(lengths + np.random.default_rng(0).random(n) * 4.0)
batches, cur, cur_max = [], [], 0
for i in order:
    L = int(lengths[i])
    if cur and (len(cur) >= 4096 or (len(cur) + 1) * max(cur_max, L) > 98304):
        batches.append(np.array(cur))
        cur, cur_max = [], 0
    cur.append(i)
    cur_max = max(cur_max, L)
if cur:
    batches.append(np.array(cur))
print(f"minibatches {len(batches)} (sizes {min(map(len, batches))}-{max(map(len, batches))})")

tot = defaultdict(lambda: 0)
per = defaultdict(list)
for ch in batches:
    feats = [rows[i]["feats"] for i in ch]
    b = M.collate(feats, dev)
    act_t = torch.tensor([rows[i]["act"] for i in ch], device=dev)
    old = torch.from_numpy(logp[ch]).to(dev)
    A = torch.from_numpy(adv_n[ch].astype(np.float32)).to(dev)
    R = torch.from_numpy(z[ch]).to(dev)
    with torch.autocast("cuda", dtype=torch.bfloat16):
        logits, val = net(b)
    lp_all = torch.log_softmax(logits.float(), -1)
    lp = lp_all.gather(1, act_t[:, None]).squeeze(1)
    e = -(lp_all.exp() * torch.where(torch.isfinite(lp_all), lp_all, torch.zeros_like(lp_all))).sum(-1)
    ratio = torch.exp((lp - old).clamp(-20, 20))
    terms = {
        "pg": -torch.min(ratio * A, ratio.clamp(0.8, 1.2) * A).mean(),
        "value": 0.5 * ((val.float() - R) ** 2).mean(),
        "entropy": -0.002 * e.mean(),
    }
    g = {k: flat(torch.autograd.grad(t, params, retain_graph=True, allow_unused=True)) for k, t in terms.items()}
    w = len(ch) / n
    for k in g:
        per[k].append(g[k].norm().item())
        tot[k] = tot[k] + w * g[k]
    per["cos pg,value"].append(torch.nn.functional.cosine_similarity(g["pg"], g["value"], dim=0).item())
    per["cos pg,entropy"].append(torch.nn.functional.cosine_similarity(g["pg"], g["entropy"], dim=0).item())
    per["ratio_dev"].append((ratio - 1).abs().mean().item())
    del b, logits, val, g
print("\ntrunk gradient norms per minibatch (mean) and of the whole-buffer mean:")
for k in ("pg", "value", "entropy"):
    print(f"  {k:8s} per-minibatch {np.mean(per[k]):.4f}   whole buffer {tot[k].norm().item():.4f}   "
          f"ratio {tot[k].norm().item() / np.mean(per[k]):.3f}  (pure noise would give {1 / np.sqrt(len(batches)):.3f})")
cos = torch.nn.functional.cosine_similarity
print(f"  cosines per minibatch: pg,value {np.mean(per['cos pg,value']):+.4f}  pg,entropy {np.mean(per['cos pg,entropy']):+.4f}")
print(f"  cosines of whole-buffer means: pg,value {cos(tot['pg'], tot['value'], dim=0).item():+.4f}  "
      f"pg,entropy {cos(tot['pg'], tot['entropy'], dim=0).item():+.4f}  value,entropy {cos(tot['value'], tot['entropy'], dim=0).item():+.4f}")
print(f"  mean |ratio - 1| at v0 (bf16 against the recorded fp32 log-prob): {np.mean(per['ratio_dev']):.5f}")
