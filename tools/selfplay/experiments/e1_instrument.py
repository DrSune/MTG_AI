"""E1's split-gradient instrument on labels (PLAN_LEARNING §2, §12), the PPO audit's estimator
(ppo_audit/scripts/dup_snr.py, dup_eval.py) applied to the linearised label gradient.

Per label i (alternatives S, mean results q over its surviving futures, pi the generator's
probabilities recomputed from the label's encoding): g_i = grad sum_{a in S} c_a log pi(a) with
c_a = pi(a) (q(a) - qbar_S), qbar_S = sum_S pi q / pi(S): the first-order distillation gradient of
the mirror-descent target (eta cancels in B*). Labels are split into K groups of whole games
(md5 of the game's seed); with mean group gradients m_k: signal S = mean_{k != l} m_k . m_l,
per-label noise sigma^2 = mean_k (|m_k|^2 - S) n_k, B* = sigma^2 / S labels (a batch of B* labels
is half signal, half noise in squared norm). Delete-one-group jackknife for the SEs. The placebo
reruns it with each label's q permuted across its alternatives (search.placebo); B* in forward
passes = B* labels x forward passes per label (every pass the label job served).

    PYTHONPATH=<checkout> PY e1_instrument.py CKPT RUN_DIR [RUN_DIR ...] [--K 16] [--out f.json]
"""

from __future__ import annotations

import hashlib
import json
import pickle
import random
import sys
from pathlib import Path

import numpy as np
import torch

from tools.selfplay import model as M
from tools.selfplay.ppo import chunks
from tools.selfplay.search import placebo


def load(run: Path) -> list[dict]:
    out = []
    with (run / "labels.pkl").open("rb") as fh:
        while True:
            try:
                out += pickle.load(fh)
            except EOFError:
                return out


def coefs(probs: np.ndarray, alts: list[int], q: list[float]) -> np.ndarray:
    p = probs[alts]
    qbar = float((p * np.asarray(q)).sum() / p.sum())
    return p * (np.asarray(q) - qbar)


def group_of(seed: int, K: int) -> int:
    return int(hashlib.md5(str(seed).encode()).hexdigest(), 16) % K


@torch.no_grad()
def probs_of(net, feats: list[dict], dev) -> list[np.ndarray]:
    lengths = np.array([f["cards_i"].shape[0] + f["opts_i"].shape[0] for f in feats])
    out: list = [None] * len(feats)
    for ch in chunks(lengths, 2048, 32768):
        b = M.collate([feats[i] for i in ch], dev)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            logits, _ = net(b)
        pr = torch.softmax(logits.float(), -1).cpu().numpy()
        for j, i in enumerate(ch):
            out[i] = pr[j, : feats[i]["opts_i"].shape[0]]
    return out


def group_grads(net, labels, cs, groups, K, dev) -> tuple[torch.Tensor, np.ndarray]:
    """[K, P] summed gradients and the label count per group."""
    params = [p for p in net.parameters() if p.requires_grad]
    P = sum(p.numel() for p in params)
    G = torch.zeros(K, P, device=dev)
    n = np.zeros(K)
    for k in range(K):
        rows = np.flatnonzero(groups == k)
        n[k] = len(rows)
        if not len(rows):
            continue
        for p in params:
            p.grad = None
        lengths = np.array([labels[i]["feats"]["cards_i"].shape[0] + labels[i]["feats"]["opts_i"].shape[0]
                            for i in rows])
        for ch in chunks(lengths, 2048, 32768):
            idx = rows[ch]
            b = M.collate([labels[i]["feats"] for i in idx], dev)
            with torch.autocast("cuda", dtype=torch.bfloat16):
                logits, _ = net(b)
            lp = torch.log_softmax(logits.float(), -1)
            w = torch.zeros_like(lp)
            for j, i in enumerate(idx):
                w[j, labels[i]["alts"]] = torch.as_tensor(cs[i], dtype=torch.float32, device=dev)
            (w * lp).sum().backward()
        G[k] = torch.cat([(p.grad if p.grad is not None else torch.zeros_like(p)).float().flatten()
                          for p in params])
    return G, n


def stats(gram: np.ndarray, n: np.ndarray, keep: np.ndarray | None = None) -> tuple[float, float]:
    idx = np.flatnonzero(n > 0) if keep is None else keep
    Mx = gram[np.ix_(idx, idx)] / np.outer(n[idx], n[idx])
    off = ~np.eye(len(idx), dtype=bool)
    S = float(Mx[off].mean())
    noise = float(np.mean((np.diag(Mx) - S) * n[idx]))
    return S, noise


def bstar(gram: np.ndarray, n: np.ndarray) -> dict:
    K = len(n)
    S, noise = stats(gram, n)
    jack = [stats(gram, n, np.array([i for i in range(K) if i != j and n[i] > 0])) for j in range(K)]
    jS = np.array([x[0] for x in jack])
    jB = np.array([x[1] / x[0] if x[0] > 0 else np.inf for x in jack])
    seS = float(np.sqrt((K - 1) / K * np.sum((jS - jS.mean()) ** 2)))
    fin = np.isfinite(jB)
    seB = float(np.sqrt((K - 1) / K * np.sum((jB - jB.mean()) ** 2))) if fin.all() else None
    return {"signal": S, "signal_se": seS, "signal_z": S / seS if seS > 0 else None,
            "noise_per_label": noise, "B_star_labels": noise / S if S > 0 else None,
            "B_star_labels_se": seB,
            "B_star_labels_95_lower": noise / (max(S, 0) + 2 * seS) if seS > 0 else None}


def main() -> None:
    argv = sys.argv[1:]
    K = int(argv[argv.index("--K") + 1]) if "--K" in argv else 16
    out_path = argv[argv.index("--out") + 1] if "--out" in argv else None
    pos = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or not argv[i - 1].startswith("--"))]
    ckpt, runs = pos[0], [Path(r) for r in pos[1:]]
    dev = torch.device("cuda")
    net, _, _ = M.load(ckpt, dev)
    net.eval()
    labels, fp, games = [], 0, 0
    for r in runs:
        labels += load(r)
        s = json.loads((r / "summary.json").read_text())
        fp += s["forward_passes"]
        games += s["games"]
    probs = probs_of(net, [lab["feats"] for lab in labels], dev)
    groups = np.array([group_of(lab["seed"], K) for lab in labels])
    real = [coefs(probs[i], lab["alts"], lab["q"]) for i, lab in enumerate(labels)]
    rng = random.Random(5)
    fake = [coefs(probs[i], lab["alts"], placebo(lab["q"], rng)) for i, lab in enumerate(labels)]
    res = {"labels": len(labels), "games": games, "forward_passes": fp,
           "fp_per_label": fp / max(len(labels), 1), "K": K, "runs": [str(r) for r in runs]}
    for name, cs in (("label", real), ("placebo", fake)):
        G, n = group_grads(net, labels, cs, groups, K, dev)
        gram = (G.double() @ G.double().T).cpu().numpy()
        del G
        torch.cuda.empty_cache()
        st = bstar(gram, n)
        if st["B_star_labels"] is not None:
            st["B_star_fp"] = st["B_star_labels"] * res["fp_per_label"]
            st["data_over_B_star"] = len(labels) / st["B_star_labels"]
        res[name] = st
    # the per-future results: their spread and how much the shared future cancels
    d_rows, corr_a, corr_b, dq = [], [], [], []
    for lab in labels:
        for zf in lab["z"]:
            if None not in zf and len(zf) >= 2:
                for i in range(len(zf)):
                    for j in range(i + 1, len(zf)):
                        d_rows.append(zf[i] - zf[j])
                        corr_a.append(zf[i])
                        corr_b.append(zf[j])
        q = lab["q"]
        dq += [q[i] - q[j] for i in range(len(q)) for j in range(i + 1, len(q))]
    a, b = np.array(corr_a), np.array(corr_b)
    res["per_future"] = {"pairs": len(d_rows), "var_diff": float(np.var(d_rows)),
                         "var_single": float(np.var(np.concatenate([a, b]))),
                         "corr": float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 and a.std() > 0 and b.std() > 0 else None,
                         "share_diff_zero": float(np.mean(np.array(d_rows) == 0))}
    res["label_dq"] = {"var": float(np.var(dq)), "share_zero": float(np.mean(np.array(dq) == 0)),
                       "mean_abs": float(np.mean(np.abs(dq)))}
    print(json.dumps(res, indent=1))
    if out_path:
        Path(out_path).write_text(json.dumps(res, indent=1) + "\n")


if __name__ == "__main__":
    main()
