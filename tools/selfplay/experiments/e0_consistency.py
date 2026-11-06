"""The marginal head against the hand decoder's sampled frequencies (PLAN_LEARNING §8: "checked
against the decoder's sampled frequencies"), on held-out positions.

usage: consistency.py CKPT N_POSITIONS N_SAMPLES DATA_DIR...
"""
import json
import sys

import numpy as np
import torch

from tools.selfplay import features as FT
from tools.selfplay import simulator as S

ckpt, n_pos, n_samp, dirs = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4:]
ck = torch.load(ckpt, map_location="cpu", weights_only=False)
table = FT.CardTable.from_json(ck["table"])
dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
net = S.Simulator(table, **ck["config"]).to(dev).eval()
net.load_state_dict(ck["state"])
data = S.Data.load(dirs, table)
idx = np.flatnonzero(S.held_out(data.a["seed"]))
idx = np.sort(np.random.default_rng(186).permutation(idx)[:n_pos])
torch.manual_seed(186)
head, samp, truth = [], [], []
with torch.no_grad():
    for ch in np.array_split(idx, max(1, len(idx) // 32)):
        b = data.batch(ch, dev)
        marg = torch.sigmoid(net(b)[2])
        rep = {k: v.repeat_interleave(n_samp, 0) for k, v in b.items()}
        hands = net.sample_hands(rep)
        real = torch.arange(hands.shape[1], device=dev)[None] < rep["h"][:, None]
        held = S.counts(hands, rep["h"], marg.shape[1]) > 0
        freq = held.float().view(len(ch), n_samp, -1).mean(1)
        ok = b["cap"] > 0
        in_hand = S.counts(b["hand"], b["h"], marg.shape[1]) > 0
        head.append(marg[ok].cpu().numpy())
        samp.append(freq[ok].cpu().numpy())
        truth.append(in_hand[ok].cpu().numpy())
        assert bool((~real | (hands > 1)).all())  # every sampled step is a real card
head, samp, truth = map(np.concatenate, (head, samp, truth))
live = np.maximum(head, samp) >= 0.01
print(json.dumps({
    "positions": len(idx), "samples per position": n_samp, "pairs": len(head),
    "mean |head - sampled| (pairs where either >= 0.01)": round(float(np.abs(head - samp)[live].mean()), 4),
    "pairs where either >= 0.01": int(live.sum()),
    "max |head - sampled|": round(float(np.abs(head - samp).max()), 4),
    "corr(head, sampled)": round(float(np.corrcoef(head, samp)[0, 1]), 4),
    "sampling noise floor of that mean": round(float(np.sqrt(2 / np.pi * samp * (1 - samp) / n_samp)[live].mean()), 4),
    "mean head / sampled / truth": [round(float(x.mean()), 5) for x in (head, samp, truth)],
}, indent=1))
