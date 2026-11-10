"""Scratch: how much more does the logged (per-minibatch mean) entropy weigh each ask kind than a per-row mean?"""
import pickle, sys
import numpy as np
from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay.ppo import chunks
rows = []
for f in sys.argv[1:]:
    with open(f, "rb") as fh:
        rows += pickle.load(fh)["rows"]
n = len(rows)
packed = M.pack([{k: np.asarray(v) for k, v in r["feats"].items()} for r in rows])
kind = packed.ask_i.reshape(n, -1)[:, 0].astype(np.int64)
L = packed.lengths()
np.random.seed(0)
import random; random.seed(0)
ch = chunks(L, 4096, 98304)
w = np.zeros(n)
for c in ch:
    w[c] = 1.0 / (len(c) * len(ch))
print("rows", n, "minibatches", len(ch), "sizes min/median/max", min(map(len, ch)), int(np.median(list(map(len, ch)))), max(map(len, ch)))
KINDS = ("act", "attack", "block", "target", "act_second_main", "one_of", "choose", "discard")
dA = dict(zip(KINDS, (-0.0021, -0.0049, -0.0004, -0.0082, -0.0012, -0.0122, +0.0010, -0.0117)))
dA2 = dict(zip(KINDS, (-0.0048, -0.0082, -0.0019, -0.0116, -0.0085, -0.0191, -0.0025, -0.0254)))
tot_row = tot_w = tot_row2 = tot_w2 = 0.0
for k in KINDS:
    m = kind == FT.ASK_KINDS.index(k)
    sr, sw = m.mean(), w[m].sum()
    print(f"{k:16s} row share {sr:.4f}  minibatch-weighted share {sw:.4f}  ratio {sw / sr:.2f}  mean length {L[m].mean():.1f}")
    tot_row += sr * dA[k]; tot_w += sw * dA[k]; tot_row2 += sr * dA2[k]; tot_w2 += sw * dA2[k]
print(f"A's by-kind falls: per-row {tot_row:+.5f}, minibatch-weighted {tot_w:+.5f}, ratio {tot_w / tot_row:.2f}")
print(f"A2's by-kind falls: per-row {tot_row2:+.5f}, minibatch-weighted {tot_w2:+.5f}, ratio {tot_w2 / tot_row2:.2f}")
