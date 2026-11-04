"""Is bf16 inference safe for PPO? KL between the trainer's numerics (fp32 weights under bf16
autocast) and the --infer-bf16 serving copy (bf16 weights, no autocast), on saved positions.

    .venv/bin/python -m tools.selfplay.bf16_logp
"""
import copy
import pickle
import random

import numpy as np
import torch

from tools.selfplay import model as M

dev = torch.device("cuda")
with open("runs/selfplay/r13_exit/state.pkl", "rb") as fh:
    rows = pickle.load(fh)["window"][-1]
random.seed(0); rows = random.sample(rows, 4096)
net, _, _ = M.load("runs/selfplay/r15_ppo/last.pt", dev); net.eval()
bnet = copy.deepcopy(net).to(torch.bfloat16).eval()
d_all, d_top, kl = [], [], []
with torch.no_grad():
    for s in range(0, len(rows), 256):
        feats = [r[0] for r in rows[s:s+256]]
        b = M.collate(feats, dev)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            la, _ = net(b)
        bb = {k: (v.to(torch.bfloat16) if v.dtype == torch.float32 else v) for k, v in b.items()}
        lb, _ = bnet(bb)
        pa = torch.log_softmax(la.float(), -1); pb = torch.log_softmax(lb.float(), -1)
        mask = b["opt_mask"]
        p = pa.exp()
        kl.append(((p * (pa - pb)).masked_fill(~mask, 0).sum(-1)).cpu().numpy())
        top = pa.argmax(-1)
        d_top.append((pa.gather(1, top[:, None]) - pb.gather(1, top[:, None])).abs().squeeze(1).cpu().numpy())
kl = np.concatenate(kl); d_top = np.concatenate(d_top)
print(f"KL(fp32-autocast || bf16 copy): mean {kl.mean():.5f}, p99 {np.quantile(kl, 0.99):.5f}; |dlogp(top)| mean {d_top.mean():.5f}, p99 {np.quantile(d_top, 0.99):.5f}")
