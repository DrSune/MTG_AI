"""p(mulligan) by hand for several checkpoints on the same declarations (KNOWLEDGE 198).

    PYTHONPATH=. .venv/bin/python reports/mulligan_runaway_2026-11-12/timeline.py BATCH.pkl CKPT...

BATCH is a ``learner --collect`` file; its mulligan declarations are scored by every CKPT on the
CPU in fp32."""
import pickle
import sys

import numpy as np
import torch

from tools.selfplay import features as FT
from tools.selfplay import model as M

with open(sys.argv[1], "rb") as fh:
    rows = pickle.load(fh)
mk = FT.ASK_KINDS.index("mulligan")
rows = [r for r in rows if int(np.asarray(r[0]["ask_i"]).reshape(-1)[0]) == mk]
hz = FT.ZONE_INDEX[FT.ZONE_HAND]
size = np.array([(np.asarray(r[0]["cards_i"])[:, 1] == hz).sum() for r in rows])
lands = np.array([(np.asarray(r[0]["cards_f"], np.float32)[np.asarray(r[0]["cards_i"])[:, 1] == hz,
                                                           FT.F_TYPE0] > 0.5).sum() for r in rows])
jm = np.array([[FT.OPTION_TYPES[int(t)] for t in np.asarray(r[0]["opts_i"])[:, 0]].index("mulligan")
               for r in rows])
cells = [("7: 0-1 lands", (size == 7) & (lands <= 1)), ("7: 2", (size == 7) & (lands == 2)),
         ("7: 3-4", (size == 7) & (lands >= 3) & (lands <= 4)), ("7: 5+", (size == 7) & (lands >= 5)),
         ("6 cards", size == 6), ("5 or fewer", size <= 5)]
print(f"{len(rows)} declarations; " + ", ".join(f"{n} {s.sum()}" for n, s in cells))
packed = M.pack([r[0] for r in rows])
for path in sys.argv[2:]:
    net = M.load(path, "cpu")[0].float().eval()
    p = np.zeros(len(rows))
    with torch.no_grad():
        for s in range(0, len(rows), 512):
            idx = np.arange(s, min(s + 512, len(rows)))
            logits, _ = net(M.collate_packed(packed, idx, "cpu"))
            p[idx] = torch.softmax(logits.float(), -1).numpy()[np.arange(len(idx)), jm[idx]]
    print(f"{path}: " + "; ".join(f"{n} {p[s].mean():.3f}" for n, s in cells), flush=True)
