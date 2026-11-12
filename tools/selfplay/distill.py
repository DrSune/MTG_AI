"""Distil recorded search targets into a network (docs/PLAN_CEILING.md §6.2: gate B, then F1).

Reads the target shards an evaluation with --search-record writes (search.target_record: an
encoding, the generating network's probabilities and value, and per compared option its mean
result, worlds and variance) and trains a copy of ``--init`` toward each decision's improved
policy pi' by cross-entropy over all options. The rule that turns a record into pi' is a setting:

- ``se`` (default): search.mmd_target's mirror-descent step over the compared options, scaled so
  one standard error of their means moves the log-odds by at most search.LOGODDS_PER_SE. A
  comparison in which every option had the same result leaves the policy as it was: in 92% of
  E3's comparisons both moves had the same result, and a fixed step made those noise.
- ``sigma``: Gumbel MuZero's pi' = softmax(log pi + sigma(completed q)) with the paper's
  constants (search.C_VISIT, C_SCALE); options not compared take v_mix (its eq. 33).

pi is ``--init``'s own probabilities, recomputed: the step starts from the network being trained.
Whole games are the unit: every 20th game (by seed) is held out, for the epoch choice and for the
agreement with the search's pick. The epoch kept is the one with the lowest held-out KL, epoch 0
(the network unchanged) included. E3 kept epoch 0 at every size, which hid its trained epochs'
small gain (KNOWLEDGE/2026-11-06/186 §5), so ``--save-epochs`` also saves every trained epoch.

    .venv/bin/python -m tools.selfplay.distill --init CKPT --out DIR --sizes 100000,300000 RUN...
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import pickle
import time
from pathlib import Path

import numpy as np
import torch

from tools.selfplay import model as M
from tools.selfplay.ppo import chunks
from tools.selfplay.search import C_SCALE, C_VISIT, mmd_target

RULES = ("se", "sigma")
#: A floor under a record's pooled variance (on the +-1 scale): with every world agreeing the
#: variance is 0 and the step would be unbounded. A rail, not a tuning knob.
VAR_FLOOR = 0.01


def load_targets(runs: list[str]) -> list[dict]:
    out = []
    for run in runs:
        for shard in sorted(Path(run, "targets").glob("shard_*.pkl")):
            with shard.open("rb") as fh:
                out += pickle.load(fh)
    return out


def improved(rec: dict, pi: np.ndarray, rule: str) -> np.ndarray:
    """pi' for one record, from the policy ``pi`` being improved."""
    alts, q, n = rec["alts"], np.asarray(rec["q"]), np.asarray(rec["n"], float)
    if not alts:
        return pi
    if rule == "se":
        pooled = float(np.dot(n, rec["var"]) / n.sum())
        se = math.sqrt(max(pooled, VAR_FLOOR) / n.mean())
        t = np.asarray(mmd_target(list(pi), alts, list(q), se))
        return t / t.sum()
    qh = (q + 1) / 2  # [0, 1], as the paper's sigma reads it
    p_alts = pi[alts].sum()
    v_mix = ((rec["v"] + 1) / 2 + n.sum() / max(p_alts, 1e-12) * float(np.dot(pi[alts], qh))) \
        / (1 + n.sum())
    completed = np.full(len(pi), v_mix)
    completed[alts] = qh
    logits = np.log(np.clip(pi, 1e-12, 1)) + (C_VISIT + n.max()) * C_SCALE * completed
    e = np.exp(logits - logits.max())
    return e / e.sum()


@torch.no_grad()
def policy(net: torch.nn.Module, feats: list[dict], dev: torch.device) -> list[np.ndarray]:
    lengths = np.array([f["cards_i"].shape[0] + f["opts_i"].shape[0] for f in feats])
    out: list = [None] * len(feats)
    for ch in chunks(lengths, 2048, 32768):
        b = M.collate([feats[i] for i in ch], dev)
        with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
            logits, _ = net(b)
        pr = torch.softmax(logits.float(), -1).cpu().numpy()
        for j, i in enumerate(ch):
            out[i] = pr[j, : feats[i]["opts_i"].shape[0]].astype(np.float64)
    return out


def ce_epoch(net, feats, targets, idx, dev, opt=None, mb: int = 512) -> float:
    """Mean cross-entropy -sum pi' log pi_theta over records ``idx`` (training when ``opt``)."""
    lengths = np.array([feats[i]["cards_i"].shape[0] + feats[i]["opts_i"].shape[0] for i in idx])
    order = np.random.default_rng(len(idx)).permutation(len(idx)) if opt else np.arange(len(idx))
    total, count = 0.0, 0
    for ch in chunks(lengths[order], mb, 65536):
        rows = idx[order[ch]]
        b = M.collate([feats[i] for i in rows], dev)
        with torch.set_grad_enabled(opt is not None), \
                torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
            logits, _ = net(b)
        lp = torch.log_softmax(logits.float(), -1).clamp(min=-1e4)  # padded options: -inf
        t = torch.zeros_like(lp)
        for j, i in enumerate(rows):
            t[j, : len(targets[i])] = torch.as_tensor(targets[i], dtype=torch.float32, device=dev)
        loss = -(t * lp).sum(1).mean()
        if opt is not None:
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
        total += float(loss.detach()) * len(rows)
        count += len(rows)
    return total / max(count, 1)


def distil(base: torch.nn.Module, recs: list[dict], rule: str, sizes: list[int], dev,
           lr: float = 3e-5, epochs: int = 4, mb: int = 512, on_epoch=None) -> dict:
    """For each size n: a copy of ``base`` trained on the first n records (whole games), the
    epoch with the lowest held-out KL kept; ``on_epoch(n, epoch, net)`` sees every trained epoch.
    Returns {n: (network, report)}."""
    feats = [r["feats"] for r in recs]
    base.eval()
    pis = policy(base, feats, dev)
    targets = [improved(r, pi, rule) for r, pi in zip(recs, pis, strict=True)]
    games = [r.get("seed") for r in recs]
    out = {}
    for n in sizes:
        sel = list(range(min(n, len(recs))))
        while sel and len(sel) < len(recs) and games[len(sel)] == games[sel[-1]]:
            sel.append(len(sel))  # whole games only
        order = {g: k for k, g in enumerate(dict.fromkeys(games[i] for i in sel))}
        val = np.array([i for i in sel if order[games[i]] % 20 == 0], np.int64)
        tr = np.array([i for i in sel if order[games[i]] % 20 != 0], np.int64)
        net = copy.deepcopy(base)
        opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=0.01)
        ent = float(np.mean([-(targets[i] * np.log(np.clip(targets[i], 1e-12, 1))).sum()
                             for i in val])) if len(val) else 0.0
        net.eval()
        hist = [{"epoch": 0, "val_kl": ce_epoch(net, feats, targets, val, dev) - ent}]
        best = (hist[0]["val_kl"], copy.deepcopy(net.state_dict()))
        for epoch in range(1, epochs + 1):
            t0 = time.time()
            net.train()
            tr_ce = ce_epoch(net, feats, targets, tr, dev, opt, mb)
            net.eval()
            vkl = ce_epoch(net, feats, targets, val, dev) - ent
            hist.append({"epoch": epoch, "train_ce": tr_ce, "val_kl": vkl,
                         "secs": round(time.time() - t0, 1)})
            if on_epoch is not None:
                on_epoch(n, epoch, net)
            if vkl < best[0]:
                best = (vkl, copy.deepcopy(net.state_dict()))
        net.load_state_dict(best[1])
        net.eval()
        held = policy(net, [feats[i] for i in val], dev)
        agree = float(np.mean([int(np.argmax(p) == recs[i]["pick"]) for p, i in zip(held, val)])) \
            if len(val) else None
        before = float(np.mean([int(np.argmax(pis[i]) == recs[i]["pick"]) for i in val])) \
            if len(val) else None
        out[n] = (net, {"records": len(sel), "train": len(tr), "val": len(val),
                        "games": len(order), "history": hist, "best_val_kl": best[0],
                        "held_out_agreement": agree, "agreement_before": before})
    return out


def describe(recs: list[dict], rule: str, base, dev) -> dict:
    """The records' share with no difference in result (every compared option's mean equal)
    and the share whose target moves the policy at all."""
    pis = policy(base, [r["feats"] for r in recs], dev)
    ties = moved = 0
    for r, pi in zip(recs, pis, strict=True):
        ties += len(r["q"]) < 2 or max(r["q"]) - min(r["q"]) < 1e-9
        moved += bool(np.abs(improved(r, pi, rule) - pi).max() > 1e-6)
    return {"records": len(recs), "no_difference": round(ties / max(len(recs), 1), 4),
            "moved": round(moved / max(len(recs), 1), 4)}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("runs", nargs="+", help="evaluation runs with --search-record")
    ap.add_argument("--init", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--sizes", default="100000,300000")
    ap.add_argument("--rule", choices=RULES, default="se")
    ap.add_argument("--lr", type=float, default=3e-5)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--mb", type=int, default=512)
    ap.add_argument("--save-epochs", action="store_true",
                    help="also save each trained epoch's network as distilled_N_eE.pt")
    a = ap.parse_args(argv)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    base, table, _ = M.load(a.init, dev)
    recs = load_targets(a.runs)
    report = {"init": a.init, "rule": a.rule, "runs": a.runs, **describe(recs, a.rule, base, dev),
              "sizes": {}}
    def save_epoch(n: int, epoch: int, net: torch.nn.Module) -> None:
        M.save(str(out / f"distilled_{n}_e{epoch}.pt"), net, table,
               {"distilled_from": a.init, "epoch": epoch})

    for n, (net, rep) in distil(base, recs, a.rule, [int(x) for x in a.sizes.split(",")], dev,
                                a.lr, a.epochs, a.mb,
                                save_epoch if a.save_epochs else None).items():
        M.save(str(out / f"distilled_{n}.pt"), net, table, {"distilled_from": a.init, **rep})
        report["sizes"][n] = rep
        print(json.dumps({"n": n, **{k: v for k, v in rep.items() if k != "history"}}), flush=True)
    (out / "distill.json").write_text(json.dumps(report, indent=1) + "\n")


if __name__ == "__main__":
    main()
