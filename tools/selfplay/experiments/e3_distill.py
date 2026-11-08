"""E3 (186 §3): distil true-future labels into the generator (expert iteration's apprentice).

Each label's target is search.mmd_target(pi, S, q, se) with pi the generator's probabilities on
the label's encoding, q its mean results and se = sqrt(V / d) (V the pooled per-future variance of
result differences, d the label's surviving futures). The apprentice starts from the generator
and minimises the cross-entropy to the targets over all options; 5% of the games are held out and
the epoch with the lowest held-out KL is kept.

    PYTHONPATH=<checkout> PY e3_distill.py GEN OUT_DIR N[,N...] V RUN_DIR [RUN_DIR ...]
        [--lr 3e-5] [--epochs 4] [--mb 512] [--save-epochs 1]
"""

from __future__ import annotations

import copy
import json
import math
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import torch

from tools.selfplay import model as M
from tools.selfplay.ppo import chunks
from tools.selfplay.search import mmd_target


def load(run: Path) -> list[dict]:
    out = []
    with (run / "labels.pkl").open("rb") as fh:
        while True:
            try:
                out += pickle.load(fh)
            except EOFError:
                return out


@torch.no_grad()
def probs_of(net, feats, dev):
    lengths = np.array([f["cards_i"].shape[0] + f["opts_i"].shape[0] for f in feats])
    out = [None] * len(feats)
    for ch in chunks(lengths, 2048, 32768):
        b = M.collate([feats[i] for i in ch], dev)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            logits, _ = net(b)
        pr = torch.softmax(logits.float(), -1).cpu().numpy()
        for j, i in enumerate(ch):
            out[i] = pr[j, : feats[i]["opts_i"].shape[0]].astype(np.float64)
    return out


def ce_epoch(net, feats, targets, idx, dev, opt=None, mb=512):
    """Mean cross-entropy -sum pi' log pi_theta over labels ``idx`` (training when ``opt``)."""
    lengths = np.array([feats[i]["cards_i"].shape[0] + feats[i]["opts_i"].shape[0] for i in idx])
    order = np.random.default_rng(len(idx)).permutation(len(idx)) if opt else np.arange(len(idx))
    total, n = 0.0, 0
    for ch in chunks(lengths[order], mb, 65536):
        rows = idx[order[ch]]
        b = M.collate([feats[i] for i in rows], dev)
        with torch.set_grad_enabled(opt is not None), torch.autocast("cuda", dtype=torch.bfloat16):
            logits, _ = net(b)
        lp = torch.log_softmax(logits.float(), -1)
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
        n += len(rows)
    return total / max(n, 1)


def main() -> None:
    argv = sys.argv[1:]
    opts = {"--lr": 3e-5, "--epochs": 4, "--mb": 512, "--save-epochs": 0}
    for k in list(opts):
        if k in argv:
            i = argv.index(k)
            opts[k] = type(opts[k])(argv[i + 1])
            del argv[i:i + 2]
    gen, out_dir, sizes, V = argv[0], Path(argv[1]), [int(x) for x in argv[2].split(",")], float(argv[3])
    runs = [Path(r) for r in argv[4:]]
    out_dir.mkdir(parents=True, exist_ok=True)
    dev = torch.device("cuda")
    labels = [lab for r in runs for lab in load(r)]
    base, table, _ = M.load(gen, dev)
    base.eval()
    feats = [lab["feats"] for lab in labels]
    pis = probs_of(base, feats, dev)
    targets, moved = [], 0
    for lab, pi in zip(labels, pis):
        d = sum(1 for zf in lab["z"] if None not in zf)
        t = np.asarray(mmd_target(list(pi), lab["alts"], lab["q"], math.sqrt(V / d)))
        moved += bool(np.abs(t - pi).max() > 1e-6)
        targets.append(t / t.sum())
    gids = [(lab["seed"], lab["gid"]) for lab in labels]
    report = {"labels": len(labels), "V": V, "moved_targets": moved, "opts": opts, "sizes": {}}
    for n in sizes:
        # the first n labels, whole games; every 20th game held out for the epoch choice
        sel, seen = [], []
        for i, g in enumerate(gids):
            if len(sel) >= n and g != seen[-1]:
                break
            sel.append(i)
            if not seen or seen[-1] != g:
                seen.append(g)
        game_no = {g: k for k, g in enumerate(seen)}
        val = np.array([i for i in sel if game_no[gids[i]] % 20 == 0])
        tr = np.array([i for i in sel if game_no[gids[i]] % 20 != 0])
        net = copy.deepcopy(base)
        net.train()
        opt = torch.optim.AdamW(net.parameters(), lr=opts["--lr"], weight_decay=0.01)
        ent = float(np.mean([-(targets[i] * np.log(np.clip(targets[i], 1e-12, 1))).sum() for i in val]))
        net.eval()
        hist = [{"epoch": 0, "val_kl": ce_epoch(net, feats, targets, val, dev) - ent}]
        best = (hist[0]["val_kl"], copy.deepcopy(net.state_dict()))
        for epoch in range(1, opts["--epochs"] + 1):
            t0 = time.time()
            net.train()
            tr_ce = ce_epoch(net, feats, targets, tr, dev, opt, opts["--mb"])
            net.eval()
            vkl = ce_epoch(net, feats, targets, val, dev) - ent
            hist.append({"epoch": epoch, "train_ce": tr_ce, "val_kl": vkl, "secs": round(time.time() - t0, 1)})
            print(json.dumps({"n": n, **hist[-1]}), flush=True)
            if vkl < best[0]:
                best = (vkl, copy.deepcopy(net.state_dict()))
            if opts["--save-epochs"]:  # diagnostic: every epoch's apprentice, beside the kept one
                M.save(str(out_dir / f"app_{n}_ep{epoch}.pt"), net, table,
                       {"distilled_from": gen, "labels": len(sel), "epoch": epoch, "val_kl": vkl})
        net.load_state_dict(best[1])
        M.save(str(out_dir / f"app_{n}.pt"), net, table,
               {"distilled_from": gen, "labels": len(sel), "train": len(tr), "val": len(val),
                "best_val_kl": best[0]})
        report["sizes"][n] = {"labels": len(sel), "train": int(len(tr)), "val": int(len(val)),
                              "games": len(seen), "history": hist, "best_val_kl": best[0]}
        del net, opt
        torch.cuda.empty_cache()
    (out_dir / "distill.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "sizes"}))


if __name__ == "__main__":
    main()
