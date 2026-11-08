"""The next library card, given what the seat may know (k = 1), on held-out positions: the
simulator's marginal head (P(next = c) = expected library count of c / its total) against the
yardstick (expected unseen copies of c / unseen cards, under its colour-pair posterior). The next
card is a uniform draw from the true library, so the expected NLL is -sum_c (n_c / l) log P(c).

usage: next_card.py CKPT DATA_DIR
"""
import json
import math
import sys
from collections import Counter

import numpy as np
import torch

from MTG_bot.core.executor.games import get_supply
from tools.selfplay import features as FT
from tools.selfplay import simulator as S

ck = torch.load(sys.argv[1], map_location="cpu", weights_only=False)
table = FT.CardTable.from_json(ck["table"])
dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
net = S.Simulator(table, **ck["config"]).to(dev).eval()
net.load_state_dict(ck["state"])
data = S.Data.load([sys.argv[2]], table)
a = data.a
idx = np.flatnonzero(S.held_out(a["seed"]) & (a["l"] > 0))
yards = {s: S.Yardstick.of(get_supply(S.POOL, s), table.row) for s in np.unique(a["set"])}


def yard_next(y, public):
    """{card: P(next library card = card)} under the yardstick given the public cards."""
    pub = Counter(public)
    ws, dists = [], []
    for (bx, by), spells in y.pairs:
        seen = Counter({o: c for o, c in pub.items() if o not in (bx, by)})
        if any(o not in spells for o in seen):
            continue
        n, m = len(spells), sum(seen.values())
        rx, ry, rs = y.half - pub[bx], y.half - pub[by], y.n_spells - m
        u = rx + ry + rs
        ws.append(-m * math.log(n))
        dists.append({bx: rx / u, by: ry / u, **dict.fromkeys(spells, rs / u / n)})
    z = max(ws)
    tot = sum(math.exp(w - z) for w in ws)
    out = Counter()
    for w, dist in zip(ws, dists):
        for o, p in dist.items():
            out[o] += math.exp(w - z) / tot * p
    return out


sim_nll, yard_nll, turn = [], [], []
with torch.no_grad():
    for ch in np.array_split(idx, max(1, len(idx) // 512)):
        b = data.batch(ch, dev)
        rate = net(b)[3]
        p = (rate / rate.sum(1, keepdim=True)).cpu().numpy()
        lib = b["lib"].cpu().numpy()
        for j, i in enumerate(ch):
            l = int(a["l"][i])
            true = Counter(lib[j, :l].tolist())
            sim_nll.append(-sum(c / l * math.log(max(p[j, r], 1e-12)) for r, c in true.items()))
            pub = a["public"][a["public_off"][i]:a["public_off"][i + 1]].tolist()
            yd = yard_next(yards[a["set"][i]], pub)
            yard_nll.append(-sum(c / l * math.log(max(yd.get(r, 0.0), 1e-12)) for r, c in true.items()))
            turn.append(int(a["turn"][i]))
sim_nll, yard_nll, turn = map(np.array, (sim_nll, yard_nll, turn))
mid = (turn >= 7) & (turn <= 12)
print(json.dumps({"positions": len(idx),
                  "next card NLL, all: sim / yardstick / ratio": [round(float(sim_nll.mean()), 4), round(float(yard_nll.mean()), 4), round(float(sim_nll.mean() / yard_nll.mean()), 4)],
                  "next card NLL, mid-game: sim / yardstick / ratio": [round(float(sim_nll[mid].mean()), 4), round(float(yard_nll[mid].mean()), 4), round(float(sim_nll[mid].mean() / yard_nll[mid].mean()), 4)]}, indent=1))
