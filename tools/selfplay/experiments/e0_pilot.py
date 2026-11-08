"""E0 tuning pilot (KNOWLEDGE 186 §1 allowance): train on training games only (seed % 25 not in
{0, 1}), validate on seed % 25 == 1. The held-out games (seed % 25 == 0) are never loaded.

usage: pilot.py LR EPOCHS WINDOW(0|1) SHARD_DIR [MAX_SHARD]
"""
import json
import math
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import torch

from tools.selfplay import features as FT
from tools.selfplay import simulator as S
from tools.selfplay.ppo import chunks

lr, epochs, window, src = float(sys.argv[1]), int(sys.argv[2]), bool(int(sys.argv[3])), Path(sys.argv[4])
max_shard = int(sys.argv[5]) if len(sys.argv) > 5 else 3
tmp = Path(tempfile.mkdtemp())
for k in range(max_shard + 1):
    for kind in ("views", "truth"):
        shutil.copy(src / f"{kind}_{k}.npz", tmp / f"{kind}_{k}.npz")
table = FT.CardTable.from_json(json.loads((src / "table.json").read_text()))
data = S.Data.load([str(tmp)], table)
shutil.rmtree(tmp)
mod = data.a["seed"] % S.HOLDOUT
tr, va = np.flatnonzero(mod > 1), np.flatnonzero(mod == 1)
dev = torch.device("cuda")
torch.manual_seed(1)
np.random.seed(1)
random.seed(1)
net = S.Simulator(table, window=window).to(dev)
opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=0.01)
lengths = data.lengths()[tr]
total = epochs * len(chunks(lengths, 512, 131072))
sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / 200) * (
    0.05 + 0.95 * 0.5 * (1 + math.cos(math.pi * min(1.0, s / total)))))
print(json.dumps({"train": len(tr), "val": len(va), "steps": total, "lr": lr, "window": window}), flush=True)


@torch.no_grad()
def val():
    net.eval()
    hs, ls = [], []
    for ch in np.array_split(va, max(1, len(va) // 512)):
        b = data.batch(ch, dev)
        h, l, _, _ = net(b)
        hs.append(-h.cpu().numpy())
        ls.append(-l.cpu().numpy())
    net.train()
    hs, ls = np.concatenate(hs), np.concatenate(ls)
    t = data.a["turn"][va]
    mid = (t >= 7) & (t <= 12)
    return round(float(hs.mean()), 4), round(float(hs[mid].mean()), 4), round(float(ls.mean()), 3)


for epoch in range(epochs):
    net.train()
    t0, losses = time.time(), []
    for ch in chunks(lengths, 512, 131072):
        b = data.batch(tr[ch], dev)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            lo = S.loss(net, b)
        opt.zero_grad(set_to_none=True)
        lo.backward()
        torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
        opt.step()
        sched.step()
        losses.append(lo.item())
    h_all, h_mid, lib = val()
    print(json.dumps({"epoch": epoch, "loss": round(float(np.mean(losses)), 3), "val_hand": h_all,
                      "val_hand_mid": h_mid, "val_lib": lib, "secs": round(time.time() - t0, 1)}), flush=True)
