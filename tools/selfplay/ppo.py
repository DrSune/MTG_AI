"""The PPO update over a packed buffer: shared by the learner (in-process) and trainer.py.

Loss per minibatch: clipped policy gradient on normalised advantages, clipped value loss and
an entropy bonus, scaled by the minibatch's share of the decisions so every decision weighs the
same. The net runs in eval() mode (no name dropout): the ratio must compare the acting policy with the same
function. Minibatches are length-sorted, capped by ``mb`` decisions and ``tok_budget`` padded
tokens (activation memory is system memory on the Spark), collated once and reused by every
epoch. Non-finite steps are skipped and counted.
"""

from __future__ import annotations

import random
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

import numpy as np
import torch

from tools.selfplay import model as M


def chunks(lengths: np.ndarray, mb: int, tok_budget: int) -> list[np.ndarray]:
    order = np.argsort(lengths + np.random.rand(len(lengths)) * 4.0)
    out, cur, cur_max = [], [], 0.0
    for i in order:
        length = float(lengths[i]) + 3.0
        if cur and (len(cur) >= mb or (len(cur) + 1) * max(cur_max, length) > tok_budget):
            out.append(np.array(cur))
            cur, cur_max = [], 0.0
        cur.append(i)
        cur_max = max(cur_max, length)
    if cur:
        out.append(np.array(cur))
    random.shuffle(out)
    return out


def ppo_train(model: torch.nn.Module, opt: torch.optim.Optimizer,
              packed: M.Packed, act: np.ndarray, logp: np.ndarray, v_old: np.ndarray,
              adv: np.ndarray, ret: np.ndarray, a: Any, device: torch.device,
              check: Callable[[], None] | None = None,
              release: Callable[[], None] | None = None) -> dict:
    cuda = device.type == "cuda"
    n = len(packed)
    adv_n = ((adv - adv.mean()) / (adv.std() + 1e-8)).astype(np.float32)
    ev = 1.0 - float(np.var(ret - v_old)) / max(float(np.var(ret)), 1e-8)
    model.eval()
    stats: dict[str, list] = defaultdict(list)
    stop = False
    t_col = time.perf_counter()
    batches = []
    for ch in chunks(packed.lengths(), a.mb, a.tok_budget):
        if check:
            check()
        batches.append((
            M.collate_packed(packed, ch, device),
            torch.from_numpy(act[ch].astype(np.int64)).to(device),
            torch.from_numpy(logp[ch].astype(np.float32)).to(device),
            torch.from_numpy(adv_n[ch]).to(device),
            torch.from_numpy(ret[ch].astype(np.float32)).to(device),
            torch.from_numpy(v_old[ch].astype(np.float32)).to(device),
        ))
    collate_s = time.perf_counter() - t_col
    t_train = time.perf_counter()
    for epoch in range(a.epochs):
        kls = []
        random.shuffle(batches)
        for step, (b, act_t, old_logp, A, R, V0) in enumerate(batches):
            if check:
                check()
            if release and step and step % 16 == 0:
                release()  # every minibatch has its own shape: bound the allocator cache
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=cuda):
                logits, v = model(b)
            logp_all = torch.log_softmax(logits, -1)
            lp = logp_all.gather(1, act_t[:, None]).squeeze(1)
            ent = -(logp_all.exp() * logp_all).sum(-1)
            ratio = torch.exp((lp - old_logp).clamp(-20.0, 20.0))  # overflow rail
            pg = -torch.min(ratio * A, ratio.clamp(1 - a.clip, 1 + a.clip) * A).mean()
            v_clip = V0 + (v - V0).clamp(-a.vclip, a.vclip)
            vloss = torch.max((v - R) ** 2, (v_clip - R) ** 2).mean()
            loss = pg + a.vcoef * vloss - a.ent * ent.mean()
            # Minibatches are length-sorted and token-capped, so they hold 190-4096 decisions;
            # a mean loss per minibatch gave a long decision ~15x the weight of a short one.
            # Scale so every decision weighs the same (2026-11-05 review).
            loss = loss * (len(act_t) * len(batches) / max(n, 1))
            opt.zero_grad(set_to_none=True)
            if not torch.isfinite(loss):
                stats["nonfinite"].append(1.0)
                continue
            loss.backward()
            gn = torch.nn.utils.clip_grad_norm_(model.parameters(), a.max_grad)
            if not torch.isfinite(gn):
                opt.zero_grad(set_to_none=True)
                stats["nonfinite"].append(1.0)
                continue
            opt.step()
            with torch.no_grad():
                kl = ((ratio - 1) - (lp - old_logp)).mean().item()
                kls.append(kl)
                stats["pg"].append(pg.item())
                stats["v"].append(vloss.item())
                stats["ent"].append(ent.mean().item())
                stats["kl"].append(kl)
                stats["clip"].append(((ratio - 1).abs() > a.clip).float().mean().item())
                stats["gn"].append(float(gn))
        stats["epochs"].append(epoch + 1)
        if a.target_kl > 0 and kls and float(np.mean(kls)) > a.target_kl:
            stop = True
            break
    n_batches = len(batches)
    del batches
    if release:
        release()
    out = {k: round(float(np.mean(v)), 5) for k, v in stats.items()
           if k not in ("epochs", "nonfinite")}
    out.update({"nonfinite": len(stats.get("nonfinite", [])), "collate_s": round(collate_s, 1),
                "train_s": round(time.perf_counter() - t_train, 1), "minibatches": n_batches,
                "steps": n, "epochs": stats["epochs"][-1] if stats["epochs"] else 0,
                "kl_stop": stop, "ev": round(ev, 4), "adv_std": round(float(adv.std()), 4)})
    return out


def pack_buffer(buf: list) -> dict:
    """Learner buffer rows (feats, action, logp, value, adv, return) -> ppo_train kwargs."""
    return {
        "packed": M.pack([b[0] for b in buf]),
        "act": np.array([b[1] for b in buf], dtype=np.int64),
        "logp": np.array([b[2] for b in buf], dtype=np.float32),
        "v_old": np.array([b[3] for b in buf], dtype=np.float32),
        "adv": np.array([b[4] for b in buf], dtype=np.float32),
        "ret": np.array([b[5] for b in buf], dtype=np.float32),
    }
