"""Held-out hand and library NLL after each epoch (the owner's 'time to convergence'), scored after
the gate on the final checkpoint.

usage: epoch_curve.py DATA_DIR CKPT...
"""
import json
import sys

import numpy as np
import torch

from tools.selfplay import features as FT
from tools.selfplay import simulator as S

dev = torch.device("cuda")
data = None
for path in sys.argv[2:]:
    ck = torch.load(path, map_location="cpu", weights_only=False)
    table = FT.CardTable.from_json(ck["table"])
    if data is None:
        data = S.Data.load([sys.argv[1]], table)
        idx = np.flatnonzero(S.held_out(data.a["seed"]))
        t = data.a["turn"][idx]
        mid = (t >= 7) & (t <= 12)
    net = S.Simulator(table, **ck["config"]).to(dev).eval()
    net.load_state_dict(ck["state"])
    hs, ls = [], []
    with torch.no_grad():
        for ch in np.array_split(idx, max(1, len(idx) // 512)):
            h, l, _, _ = net(data.batch(ch, dev))
            hs.append(-h.cpu().numpy())
            ls.append(-l.cpu().numpy())
    hs, ls = np.concatenate(hs), np.concatenate(ls)
    print(json.dumps({"ckpt": path.rsplit("/", 1)[-1], "epoch": ck.get("epoch"), "hand": round(float(hs.mean()), 4),
                      "hand mid": round(float(hs[mid].mean()), 4), "library": round(float(ls.mean()), 3)}), flush=True)
