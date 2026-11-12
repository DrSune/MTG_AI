"""PLAN_CEILING §4.1's capacity probe: does a bigger network fit what r27 has to learn?

Input: a batch written by ``learner.py --collect`` (rows: features, action, log-prob, value,
advantage, return, game id, step, steps) of r27's v0 playing as r27 trains. Every 25th game is
held out (``--holdout``). Arms, all from one checkpoint (``model.grow`` keeps its function):
- ``base``: the network as it is;
- ``deep``: twice the layers (identity layers inserted);
- ``wide``: twice the feed-forward width (new units with zero outgoing weights).
Each arm is fine-tuned on the same training rows, in the same minibatches (``ppo.chunks``, PPO's
token budget), for the same optimizer steps: cross-entropy on the action taken plus ``vcoef`` x the
squared error of the value against the return, AdamW, bf16 autocast, the network in eval mode as
PPO runs it. Every ``--eval-every`` steps the held-out rows give the value's explained variance by
game phase (the step's third of its game) and the policy's NLL; the step time and the peak memory
are logged.

    PYTHONPATH=. .venv/bin/python reports/capacity_probe_2026-11-12/probe.py COLLECT.pkl CKPT \\
        OUT.jsonl [--steps 450] [--lr 1e-4] [--arms base,deep,wide]
"""

from __future__ import annotations

import argparse
import json
import pickle
import time

import numpy as np
import torch

from tools.selfplay import model as M
from tools.selfplay.ppo import chunks

def load(path: str, holdout: int) -> tuple:
    with open(path, "rb") as fh:
        rows = pickle.load(fh)
    packed = M.pack([r[0] for r in rows])
    act = np.array([r[1] for r in rows], np.int64)
    ret = np.array([r[5] for r in rows], np.float32)
    held = np.array([r[6] % holdout == 0 for r in rows])
    phase = np.minimum((3 * np.array([r[7] for r in rows]) // np.array([r[8] for r in rows])), 2)
    return packed, act, ret, held, phase


def evaluate(net: torch.nn.Module, packed: M.Packed, act: np.ndarray, ret: np.ndarray,
             idx: np.ndarray, phase: np.ndarray, device: torch.device, a: argparse.Namespace
             ) -> dict:
    v_all, nll = np.zeros(len(idx), np.float32), np.zeros(len(idx), np.float32)
    with torch.no_grad():
        for ch in chunks(packed.lengths()[idx], a.mb, a.tok_budget):  # positions in idx
            b = M.collate_packed(packed, idx[ch], device)
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits, v = net(b)
            lp = torch.log_softmax(logits.float(), -1)
            at = torch.from_numpy(act[idx[ch]]).to(device)
            nll[ch] = (-lp.gather(1, at[:, None]).squeeze(1)).cpu().numpy()
            v_all[ch] = v.float().cpu().numpy()
    out = {"policy_nll": round(float(nll.mean()), 5)}
    for p, name in enumerate(("early", "mid", "late")):
        sel = phase[idx] == p
        r = ret[idx][sel]
        out[f"ev_{name}"] = round(1 - float(np.var(r - v_all[sel])) / max(float(np.var(r)), 1e-8),
                                  5)
    r = ret[idx]
    out["ev_all"] = round(1 - float(np.var(r - v_all)) / max(float(np.var(r)), 1e-8), 5)
    return out


def run_arm(name: str, a: argparse.Namespace, data: tuple, out) -> None:
    packed, act, ret, held, phase = data
    device = torch.device("cuda" if torch.cuda.is_available() and a.device != "cpu" else "cpu")
    net, table, _ = M.load(a.ckpt)
    cfg = net.config
    if name == "deep":
        net = M.grow(net, table, layers=2 * cfg["layers"])
    elif name == "wide":
        net = M.grow(net, table, ff=2 * cfg["ff"])
    net = net.to(device).eval()
    opt = torch.optim.AdamW(net.parameters(), lr=a.lr, betas=(0.9, 0.99), eps=1e-6,
                            weight_decay=a.wd)
    train, test = np.flatnonzero(~held), np.flatnonzero(held)
    rng = np.random.default_rng(a.seed)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats()

    def log(step: int, extra: dict) -> None:
        row = {"arm": name, "step": step, "params": sum(p.numel() for p in net.parameters()),
               **evaluate(net, packed, act, ret, test, phase, device, a), **extra}
        if device.type == "cuda":
            row["peak_gib"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)
        out.write(json.dumps(row) + "\n")
        out.flush()
        print(json.dumps(row), flush=True)

    log(0, {"train_rows": len(train), "test_rows": len(test)})
    step, t_train = 0, 0.0
    while step < a.steps:
        mbs = chunks(packed.lengths()[train], a.mb, a.tok_budget)
        for k in rng.permutation(len(mbs)):
            rows = train[mbs[k]]
            t0 = time.perf_counter()
            b = M.collate_packed(packed, rows, device)
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=device.type == "cuda"):
                logits, v = net(b)
            lp = torch.log_softmax(logits.float(), -1)
            at = torch.from_numpy(act[rows]).to(device)
            rt = torch.from_numpy(ret[rows]).to(device)
            loss = (-lp.gather(1, at[:, None]).squeeze(1)).mean() + a.vcoef * (
                (v.float() - rt) ** 2).mean()
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), a.max_grad)
            opt.step()
            if device.type == "cuda":
                torch.cuda.synchronize()
            t_train += time.perf_counter() - t0
            step += 1
            if step % a.eval_every == 0 or step == a.steps:
                log(step, {"s_per_step": round(t_train / step, 3)})
            if step == a.steps:
                break


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("collect")
    ap.add_argument("ckpt")
    ap.add_argument("out")
    ap.add_argument("--arms", default="base,deep,wide")
    ap.add_argument("--steps", type=int, default=450)
    ap.add_argument("--eval-every", type=int, default=50)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--wd", type=float, default=0.01)
    ap.add_argument("--vcoef", type=float, default=0.5)
    ap.add_argument("--max-grad", type=float, default=1.0)
    ap.add_argument("--mb", type=int, default=4096)
    ap.add_argument("--tok-budget", type=int, default=98304)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="auto")
    ap.add_argument("--holdout", type=int, default=25)
    a = ap.parse_args(argv)
    torch.manual_seed(a.seed)
    np.random.seed(a.seed)  # ppo.chunks' order
    data = load(a.collect, a.holdout)
    with open(a.out, "a") as out:
        for name in a.arms.split(","):
            run_arm(name, a, data, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
