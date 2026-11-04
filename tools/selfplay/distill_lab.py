"""Offline distillation recipes: train copies of the network that generated one generation of
search labels (state.pkl) under different targets, score them on held-out games.

    .venv/bin/python -m tools.selfplay.distill_lab --state runs/selfplay/r13_exit/state.pkl \
        --gen 0 1 --prior runs/selfplay/r12_exit/v0.pt runs/selfplay/r12_exit/last.pt \
        --recipes soft hard sharp:0.02

The headline metric is search regret on held-out searched rows: the search's score of its best
candidate minus the score of the network's move (scores recovered from the soft target and the
prior, s_j = tau * ln(t_j / p_j) + c; a move outside the candidates counts as the worst one).
The prior's regret is the baseline; distillation that absorbs the search lowers it.

Recipes (target per row, weight):
  soft            the run's soft target where the search ran, else the recorded move
  hard            the recorded move everywhere (the search's argmax where it ran)
  sharp:TAU       soft targets re-tempered to TAU: t' ~ p^(1 - r) t^r with r = tau / TAU
  margin:M:W      the search's move where its margin over the network's move is >= M (weight W),
                  otherwise the network's own move
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import pickle
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F

from tools.selfplay import model as M
from tools.selfplay.distill_probe import MARGINS, margin, score


def chunks(rows: list, mb: int, tok_budget: int) -> list[np.ndarray]:
    lengths = np.array([r[0]["cards_i"].shape[0] + r[0]["opts_i"].shape[0] for r in rows], float)
    order = np.argsort(lengths + np.random.rand(len(rows)) * 4.0)
    out, cur, cur_max = [], [], 0.0
    for i in order:
        length = lengths[i] + 3.0
        if cur and (len(cur) >= mb or (len(cur) + 1) * max(cur_max, length) > tok_budget):
            out.append(np.array(cur))
            cur, cur_max = [], 0.0
        cur.append(i)
        cur_max = max(cur_max, length)
    if cur:
        out.append(np.array(cur))
    np.random.shuffle(out)
    return out


def cand_scores(soft: list, probs: list, tau: float) -> dict[int, float]:
    """Candidate scores up to a constant from t ~ prior x exp(score / tau)."""
    return {j: tau * math.log(t / probs[j]) for j, t in soft if t > 0 and probs[j] > 0}


def target_fn(recipe: str, tau: float):
    """row, prior-info -> (list of (option, prob), weight)."""
    name, *params = recipe.split(":")

    def fn(row: tuple, info: dict) -> tuple[list, float]:
        idx, wp = row[1], (row[4] if len(row) > 4 else 1.0)
        soft = row[5] if len(row) > 5 else None
        if name == "hard" or not soft:
            return [(idx, 1.0)], wp
        if name == "soft":
            return list(soft), wp
        if name == "sharp":
            r = tau / float(params[0])
            probs = info["probs"]
            w = {j: (probs[j] ** (1 - r)) * (t ** r) for j, t in soft if t > 0 and probs[j] > 0}
            z = sum(w.values()) or 1.0
            return [(j, v / z) for j, v in w.items()] or [(idx, 1.0)], wp
        if name == "margin":
            m0, w_change = float(params[0]), float(params[1])
            a0 = info["a0"]
            if a0 == idx:
                return [(idx, 1.0)], wp
            m = info["margin"]
            if m is not None and m >= m0:
                return [(idx, 1.0)], wp * w_change
            return [(a0, 1.0)], wp
        raise ValueError(recipe)

    return fn


def train(net: torch.nn.Module, rows: list, infos: list, recipe: str, a: argparse.Namespace,
          device: torch.device) -> dict:
    fn = target_fn(recipe, a.tau)
    targets = [fn(r, info) for r, info in zip(rows, infos)]
    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, weight_decay=a.wd)
    steps_total = max(1, a.epochs * math.ceil(len(rows) / a.mb))
    warm = max(1, steps_total // 20)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / warm) * (
        0.05 + 0.95 * 0.5 * (1 + math.cos(math.pi * min(1.0, s / steps_total)))))
    net.train()
    t0, losses = time.time(), []
    for _ in range(a.epochs):
        for ch in chunks(rows, a.mb, a.tok_budget):
            b = M.collate([rows[i][0] for i in ch], device)
            z = torch.tensor([rows[i][2] for i in ch], device=device, dtype=torch.float32)
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits, v = net(b)
            tgt = torch.zeros(logits.shape, device="cpu")
            wts = torch.empty(len(ch))
            for r, i in enumerate(ch):
                pairs, w = targets[i]
                for j, pj in pairs:
                    tgt[r, j] = pj
                wts[r] = w
            tgt, wts = tgt.to(device), wts.to(device)
            ce = -(tgt * torch.log_softmax(logits.float(), -1)).sum(-1)
            loss = (ce * wts).sum() / wts.sum().clamp(min=1.0) + a.vcoef * F.mse_loss(v.float(), z)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
            sched.step()
            losses.append(loss.item())
    return {"loss": round(float(np.mean(losses[-50:])), 4), "secs": round(time.time() - t0, 1)}


def evaluate(net: torch.nn.Module, rows: list, infos: list, device: torch.device) -> dict:
    res = score(net.eval(), rows, device)
    out: dict = {}
    by: dict[str, list] = {}
    regret = []
    for (top, p_label, _ce, _probs), row, info in zip(res, rows, infos):
        by.setdefault(info["kind"], []).append((top == row[1], p_label))
        sc = info["scores"]
        if sc:
            best = max(sc.values())
            regret.append(best - sc.get(top, min(sc.values())))
    for kind, xs in sorted(by.items()):
        out[kind] = {"n": len(xs), "acc": round(sum(x[0] for x in xs) / len(xs), 4),
                     "p_label": round(sum(x[1] for x in xs) / len(xs), 4)}
    out["regret"] = round(float(np.mean(regret)), 5) if regret else None
    return out


def classify(rows: list, net: torch.nn.Module, tau: float, device: torch.device) -> list[dict]:
    """Per row: the generating network's move, probs, the search's margin, bucket and scores."""
    infos = []
    for row, (top, _p, _ce, probs) in zip(rows, score(net.eval(), rows, device)):
        soft = row[5] if len(row) > 5 else None
        m = margin(soft, row[1], top, probs, tau) if soft and top != row[1] else None
        if not soft:
            kind = "plain"
        elif top == row[1]:
            kind = "kept"
        else:
            kind = ("changed?" if m is None else
                    f"changed<{MARGINS[0]}" if m < MARGINS[0] else
                    f"changed<{MARGINS[1]}" if m < MARGINS[1] else f"changed>={MARGINS[1]}")
        infos.append({"a0": top, "probs": probs, "margin": m, "kind": kind,
                      "scores": cand_scores(soft, probs, tau) if soft else {}})
    return infos


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", required=True)
    ap.add_argument("--gen", type=int, nargs="+", default=[0],
                    help="window indices trained on together")
    ap.add_argument("--prior", nargs="+", required=True,
                    help="the network that generated each --gen's labels; the first is trained")
    ap.add_argument("--recipes", nargs="+", default=["soft"])
    ap.add_argument("--holdout-every", type=int, default=5)
    ap.add_argument("--tau", type=float, default=0.05, help="the run's --search-tau")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--wd", type=float, default=0.01)
    ap.add_argument("--vcoef", type=float, default=0.1)
    ap.add_argument("--mb", type=int, default=1024)
    ap.add_argument("--tok-budget", type=int, default=49152)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    assert len(a.gen) == len(a.prior), "one --prior per --gen"
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    with open(a.state, "rb") as fh:
        window = pickle.load(fh)["window"]

    # hashed: game ids are issued in a fixed value/search interleave, so gid % k can select
    # no search games at all (k = 5 with the 4:1 interleave selects none)
    def is_held(gid: int) -> bool:
        h = hashlib.blake2b(str(gid).encode(), digest_size=4).digest()
        return int.from_bytes(h, "little") % a.holdout_every == 0

    init, _, _ = M.load(a.prior[0], device)
    t_rows, t_infos, held = [], [], {}
    for g, path in zip(a.gen, a.prior):
        rows = window[g]
        gen_net = init if path == a.prior[0] else M.load(path, device)[0]
        infos = classify(rows, gen_net, a.tau, device)
        held[g] = ([r for r in rows if is_held(r[3])],
                   [inf for r, inf in zip(rows, infos) if is_held(r[3])])
        t_rows += [r for r in rows if not is_held(r[3])]
        t_infos += [inf for r, inf in zip(rows, infos) if not is_held(r[3])]
    t_eval = [i for i, inf in enumerate(t_infos) if inf["kind"] != "plain"][:6000]
    report = {"state": a.state, "gen": a.gen, "prior": a.prior, "train": len(t_rows),
              "held": {g: len(h[0]) for g, h in held.items()}, "epochs": a.epochs, "lr": a.lr,
              "prior_held": {g: evaluate(init, *h, device) for g, h in held.items()}}
    print(json.dumps(report), flush=True)
    for recipe in a.recipes:
        torch.manual_seed(a.seed)
        np.random.seed(a.seed)
        net = copy.deepcopy(init)
        fit = train(net, t_rows, t_infos, recipe, a, device)
        row = {"recipe": recipe, **fit,
               "held": {g: evaluate(net, *h, device) for g, h in held.items()},
               "train_searched": evaluate(net, [t_rows[i] for i in t_eval],
                                          [t_infos[i] for i in t_eval], device)}
        print(json.dumps(row), flush=True)
        del net
        torch.cuda.empty_cache()
    return 0


if __name__ == "__main__":
    sys.exit(main())
