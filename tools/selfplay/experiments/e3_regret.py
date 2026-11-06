"""E3's regret (186 §3): held-out positions relabelled on fresh true futures (k = 8, so every option
of a menu of at most 8; d = 4). A network's regret at a position is the best compared option's
mean result minus the mean result of its own greedy option (the bf16 network, as served).
Positions where some network's greedy option was not compared are left out. The ratio of each
apprentice's mean regret to the generator's, with a bootstrap over games (2,000 resamples): its
one-sided 95% upper bound.

    PYTHONPATH=<checkout> PY e3_regret.py RUN_DIR GEN APP [APP ...] [--out f.json]
"""

from __future__ import annotations

import json
import pickle
import sys
from pathlib import Path

import numpy as np
import torch

from tools.selfplay import model as M
from tools.selfplay.ppo import chunks


def load(run: Path) -> list[dict]:
    out = []
    with (run / "labels.pkl").open("rb") as fh:
        while True:
            try:
                out += pickle.load(fh)
            except EOFError:
                return out


@torch.no_grad()
def greedy(path: str, feats: list[dict]) -> np.ndarray:
    net, _, _ = M.load(path, "cuda")
    net = net.to(torch.bfloat16).eval()
    lengths = np.array([f["cards_i"].shape[0] + f["opts_i"].shape[0] for f in feats])
    out = np.zeros(len(feats), dtype=np.int64)
    for ch in chunks(lengths, 2048, 32768):
        b = M.collate([feats[i] for i in ch], "cuda")
        b = {k: (v.to(torch.bfloat16) if v.dtype == torch.float32 else v) for k, v in b.items()}
        logits, _ = net(b)
        out[ch] = logits.float().argmax(-1).cpu().numpy()
    return out


def main() -> None:
    argv = sys.argv[1:]
    out_path = argv[argv.index("--out") + 1] if "--out" in argv else None
    argv = [a for i, a in enumerate(argv) if a != "--out" and (i == 0 or argv[i - 1] != "--out")]
    run, nets = Path(argv[0]), argv[1:]
    labels = load(run)
    feats = [lab["feats"] for lab in labels]
    choices = {p: greedy(p, feats) for p in nets}
    keep, regret = [], {p: [] for p in nets}
    for i, lab in enumerate(labels):
        alts = lab["alts"]
        if not all(int(choices[p][i]) in alts for p in nets):
            continue
        keep.append(i)
        best = max(lab["q"])
        for p in nets:
            regret[p].append(best - lab["q"][alts.index(int(choices[p][i]))])
    games = np.array([labels[i]["seed"] for i in keep])
    uniq = np.unique(games)
    rows = {g: np.flatnonzero(games == g) for g in uniq}
    R = {p: np.array(v) for p, v in regret.items()}
    gen = nets[0]
    res = {"positions": len(labels), "compared": len(keep), "games": len(uniq),
           "mean_regret": {p: float(R[p].mean()) for p in nets},
           "share_regret_positive": {p: float((R[p] > 0).mean()) for p in nets},
           "changed_vs_generator": {p: float(np.mean(choices[p][keep] != choices[gen][keep]))
                                    for p in nets[1:]}}
    rng = np.random.default_rng(0)
    boots = {p: [] for p in nets[1:]}
    for _ in range(2000):
        pick = np.concatenate([rows[g] for g in rng.choice(uniq, len(uniq))])
        den = R[gen][pick].mean()
        for p in nets[1:]:
            boots[p].append(R[p][pick].mean() / den if den > 0 else np.inf)
    res["ratio"] = {p: {"point": float(R[p].mean() / R[gen].mean()) if R[gen].mean() > 0 else None,
                        "upper95_one_sided": float(np.percentile(boots[p], 95)),
                        "ci95": [float(np.percentile(boots[p], 2.5)), float(np.percentile(boots[p], 97.5))]}
                    for p in nets[1:]}
    print(json.dumps(res, indent=1))
    if out_path:
        Path(out_path).write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    main()
