"""Gate B's GB2 (KNOWLEDGE/2026-11-12/196 §2): agreement with the search's pick on the held-out
targets of the larger distillation, which no distilled network trained on.

    PYTHONPATH=. .venv/bin/python reports/gate_b_2026-11-12/agreement.py OUT.json G.pt \\
        NET100.pt NET300.pt SIZE RUN...

RUN... are the generation's chunk runs in order, as distill.py was given them; the held-out
targets are distill.split's for SIZE, the larger distillation's size (300,000 as registered;
the queue passes its own, so the two never disagree). For each network it reports the share of
those targets where its top option is the search's pick, and the share where its top option
differs from G's.
GB2 is NET300 - NET100, paired by target, with a 95% interval from 2,000 bootstrap resamples of
deals.
"""

import json
import sys

import numpy as np
import torch

from tools.selfplay import model as M
from tools.selfplay.distill import load_targets, policy, split

out, g_path, n100, n300, size, *runs = sys.argv[1:]
recs = load_targets(runs)
if len(recs) < int(size):
    raise SystemExit(f"{len(recs)} targets, fewer than the size {size} the networks were named for")
_, val, _ = split([r.get("seed") for r in recs], int(size))
held = [recs[i] for i in val]
del recs
dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
tops = {}
for name, path in (("G", g_path), ("100k", n100), ("300k", n300)):
    net, _, _ = M.load(path, dev)
    tops[name] = np.array([int(np.argmax(p)) for p in policy(net.eval(), [r["feats"] for r in held],
                                                               dev)])
    del net
pick = np.array([r["pick"] for r in held])
agree = {k: (v == pick).astype(float) for k, v in tops.items()}
diff = agree["300k"] - agree["100k"]
deals, inv = np.unique(np.array([r["seed"] for r in held]), return_inverse=True)
rng = np.random.default_rng(196)
boots = []
for _ in range(2000):
    w = np.bincount(rng.integers(0, len(deals), len(deals)), minlength=len(deals))[inv]
    boots.append(float((w * diff).sum() / w.sum()))
lo, hi = np.percentile(boots, [2.5, 97.5])
report = {"targets": len(held), "deals": len(deals), "networks": [g_path, n100, n300],
          "agreement": {k: round(float(v.mean()), 4) for k, v in agree.items()},
          "changed_from_G": {k: round(float((tops[k] != tops["G"]).mean()), 4)
                             for k in ("100k", "300k")},
          "gb2": round(float(diff.mean()), 4), "gb2_ci95": [round(float(lo), 4), round(float(hi), 4)]}
with open(out, "w") as fh:
    fh.write(json.dumps(report, indent=1) + "\n")
print(json.dumps(report))
