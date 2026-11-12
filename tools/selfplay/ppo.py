"""The PPO update over a packed buffer (run in trainer.py's process). ``steps`` cuts every
training loop's optimizer steps (PPO, BC, the simulator, distillation); ``chunks`` serves passes
whose order does not matter.

Loss per step: clipped policy gradient on normalised advantages, clipped value loss and an
entropy bonus, the mean over the step's decisions. The net runs in eval() mode (no name
dropout): the ratio must compare the acting policy with the same function. Non-finite steps are
skipped and counted.

Every optimizer step is a sample of the whole batch (KNOWLEDGE 198). Padding is what forces
length-sorted micro-batches (activation memory is system memory on the Spark, capped by ``mb``
decisions and ``tok_budget`` padded tokens), but a length-sorted minibatch is also a game-phase
and ask-kind stratum. Stepping on each one alone gave every short-only kind (the mulligan: all of
its declarations in 2 of 48 minibatches) one impulse per update and let the other steps drag it
between impulses: r27's mulligan ran away while its own gradient pointed back. So a step
accumulates gradients over length-homogeneous micro-batches dealt from every length (``steps``),
and an update takes as many steps over as many tokens as length-sorted minibatches did.

The KL early stop (``target_kl`` > 0) bounds how far THIS update moves: it measures KL from the
policy at the start of the update (one no-grad pass over the batch, a quarter of the update's
time, skipped when the stop is off), not from the behaviour log-probs. Rows played while the
previous update ran (the overlap, ~40% of a batch) were sampled by the previous weights, so
measured against them the first minibatch would already carry the previous update's movement.
The clipped ratio still uses the behaviour log-probs (the data's policy); ``kl`` stays the KL
from them, ``kl_update`` is the stop's measure.

``kinds`` reports each ask kind on its own (DESIGN_PRIORITY §3.5): near-certain passes dilute
the means, so a policy that always passes, or an act menu that moves far, would not show. Per
kind: the decisions, the share that declined to act (PASS, DECLINE, NONE, skip), the mean
advantage, and from each decision's last minibatch the entropy normalised by log |A| over asks
with two options or more (METRICS §17 VAR-1) and the KL from the behaviour policy.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

import numpy as np
import torch

from tools.selfplay import features as FT
from tools.selfplay import model as M

_DECLINE = [FT.OPT_INDEX[t] for t in ("PASS", "DECLINE", "NONE", "skip")]


def _cut(order: np.ndarray, lengths: np.ndarray, mb: int, tok_budget: int) -> list[np.ndarray]:
    """``order`` (ascending length) cut into micro-batches of at most ``mb`` rows and
    ``tok_budget`` padded tokens."""
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
    return out


def chunks(lengths: np.ndarray, mb: int, tok_budget: int,
           rng: np.random.Generator) -> list[np.ndarray]:
    """Length-sorted micro-batches of row indices (jitter from ``rng``), each capped by ``mb``
    rows and ``tok_budget`` padded tokens, in an order drawn from ``rng``. Each is one stratum of
    length, so they serve passes whose order does not matter, never optimizer steps (``steps``).
    The generator is the caller's, so its seed fixes them (no global random state)."""
    out = _cut(np.argsort(lengths + rng.random(len(lengths)) * 4.0), lengths, mb, tok_budget)
    return [out[i] for i in rng.permutation(len(out))]


def steps(lengths: np.ndarray, mb: int, tok_budget: int,
          rng: np.random.Generator) -> list[list[np.ndarray]]:
    """Optimizer steps, each a list of micro-batches of row indices: as many steps as ``chunks``
    would cut, each a sample of every length (KNOWLEDGE 198). The rows in length order (jitter
    from ``rng``) are dealt in blocks of one row per step, each block in a random order, so a
    step holds short and long decisions, and so every ask kind, in their shares of the batch.
    A step's rows, still in length order, are cut like ``chunks``; its micro-batches accumulate
    one gradient (``backward_step``)."""
    order = np.argsort(lengths + rng.random(len(lengths)) * 4.0)
    k = len(_cut(order, lengths, mb, tok_budget))
    deal = np.argsort(rng.random((-(-len(order) // k), k)), axis=1).reshape(-1)[: len(order)]
    out = [_cut(order[deal == j], lengths, mb, tok_budget) for j in range(k)]
    return [out[j] for j in rng.permutation(k)]


def backward_step(step: list[np.ndarray], loss_of: Callable[[np.ndarray], torch.Tensor]) -> float:
    """One optimizer step's gradient, accumulated over its micro-batches: ``loss_of(rows)`` is a
    micro-batch's mean loss, weighted by its share of the step's rows, so the step's gradient is
    the mean over its rows. Returns that mean loss. The caller zeroes, clips and steps."""
    m = sum(len(ch) for ch in step)
    total = 0.0
    for ch in step:
        lo = loss_of(ch)
        (lo * (len(ch) / m)).backward()
        total += float(lo.detach()) * len(ch)
    return total / m


def ppo_train(model: torch.nn.Module, opt: torch.optim.Optimizer,
              packed: M.Packed, act: np.ndarray, logp: np.ndarray, v_old: np.ndarray,
              adv: np.ndarray, ret: np.ndarray, a: Any, device: torch.device,
              rng: np.random.Generator, check: Callable[[], None] | None = None,
              release: Callable[[], None] | None = None) -> dict:
    cuda = device.type == "cuda"
    n = len(packed)
    adv_n = ((adv - adv.mean()) / (adv.std() + 1e-8)).astype(np.float32)
    ev = 1.0 - float(np.var(ret - v_old)) / max(float(np.var(ret)), 1e-8)
    model.eval()
    stats: dict[str, list] = defaultdict(list)
    ent_last = np.full(n, np.nan, dtype=np.float32)  # per decision, its last minibatch's
    kl_last = np.full(n, np.nan, dtype=np.float32)
    stop = False
    t_col = time.perf_counter()
    step_list = steps(packed.lengths(), a.mb, a.tok_budget, rng)
    n_steps = len(step_list)
    micro = [ch for step in step_list for ch in step]
    kl_stop = a.target_kl > 0
    lp0_arr = np.empty(n if kl_stop else 0, dtype=np.float32)
    with torch.no_grad():
        for ch in micro if kl_stop else ():
            if check:
                check()
            b = M.collate_packed(packed, ch, device)
            act_t = torch.from_numpy(act[ch].astype(np.int64)).to(device)
            with torch.autocast(device.type, dtype=torch.bfloat16, enabled=cuda):
                logits0, _ = model(b)
            lp0 = torch.log_softmax(logits0, -1).gather(1, act_t[:, None]).squeeze(1)
            lp0_arr[ch] = lp0.cpu().numpy()
            del b, act_t, logits0, lp0
    if release:
        release()
    collate_s = time.perf_counter() - t_col
    t_train = time.perf_counter()
    for epoch in range(a.epochs):
        kls = []
        for k, j in enumerate(rng.permutation(n_steps)):
            if check:
                check()
            if release and k and k % 16 == 0:
                release()  # every micro-batch has its own shape: bound the allocator cache
            step = step_list[j]
            m = sum(len(ch) for ch in step)
            acc: dict[str, float] = defaultdict(float)  # the step's sums over its decisions
            finite = True
            opt.zero_grad(set_to_none=True)
            for ch in step:
                b = M.collate_packed(packed, ch, device)
                act_t = torch.from_numpy(act[ch].astype(np.int64)).to(device)
                old_logp = torch.from_numpy(logp[ch].astype(np.float32)).to(device)
                A = torch.from_numpy(adv_n[ch]).to(device)
                R = torch.from_numpy(ret[ch].astype(np.float32)).to(device)
                V0 = torch.from_numpy(v_old[ch].astype(np.float32)).to(device)
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
                with torch.no_grad():
                    w = len(ch)
                    kl_each = (ratio - 1) - (lp - old_logp)
                    n_opt = b["opt_mask"].sum(-1).float()
                    ent_n = torch.where(n_opt >= 2, ent / torch.log(n_opt.clamp(min=2)),
                                        torch.full_like(ent, float("nan")))
                    ent_last[ch] = ent_n.float().cpu().numpy()
                    kl_last[ch] = kl_each.float().cpu().numpy()
                    acc["pg"] += pg.item() * w
                    acc["v"] += vloss.item() * w
                    acc["ent"] += ent.mean().item() * w
                    acc["kl"] += kl_each.mean().item() * w
                    acc["clip"] += ((ratio - 1).abs() > a.clip).float().mean().item() * w
                    if kl_stop:
                        d0 = lp - torch.from_numpy(lp0_arr[ch]).to(device)
                        acc["kl_update"] += (torch.exp(d0) - 1 - d0).mean().item() * w
                if torch.isfinite(loss):
                    (loss * (w / m)).backward()  # the step's gradient: the mean over its rows
                else:
                    finite = False
                del b, act_t, old_logp, A, R, V0, logits, v, loss
            kl_upd = acc["kl_update"] / m
            # Stop before a step on rows this update has already moved by 1.5x the target (as
            # SB3 does); a check only between epochs would never act at --epochs 1.
            if kl_stop and kl_upd > 1.5 * a.target_kl:
                opt.zero_grad(set_to_none=True)
                stop = True
                break
            if not finite:
                opt.zero_grad(set_to_none=True)
                stats["nonfinite"].append(1.0)
                continue
            gn = torch.nn.utils.clip_grad_norm_(model.parameters(), a.max_grad)
            if not torch.isfinite(gn):
                opt.zero_grad(set_to_none=True)
                stats["nonfinite"].append(1.0)
                continue
            opt.step()
            if kl_stop:
                kls.append(kl_upd)
                stats["kl_update"].append(kl_upd)
            for key in ("pg", "v", "ent", "kl", "clip"):
                stats[key].append(acc[key] / m)
            stats["gn"].append(float(gn))
        stats["epochs"].append(epoch + 1)
        if stop or (kls and float(np.mean(kls)) > a.target_kl):
            stop = True
            break
    if release:
        release()
    out = {k: round(float(np.mean(v)), 5) for k, v in stats.items()
           if k not in ("epochs", "nonfinite")}
    out.update({"nonfinite": len(stats.get("nonfinite", [])), "collate_s": round(collate_s, 1),
                "train_s": round(time.perf_counter() - t_train, 1), "minibatches": n_steps,
                "micro": len(micro),
                "steps": n, "epochs": stats["epochs"][-1] if stats["epochs"] else 0,
                "kl_stop": stop, "ev": round(ev, 4), "adv_std": round(float(adv.std()), 4),
                "kinds": per_kind(packed, act, adv, ent_last, kl_last)})
    return out


def per_kind(packed: M.Packed, act: np.ndarray, adv: np.ndarray, ent: np.ndarray,
             kl: np.ndarray) -> dict[str, dict]:
    """The update's statistics by ask kind (see the module docstring)."""
    kind = packed.ask_i[:, 0].astype(np.int64)
    chosen = packed.opts_i[packed.o_off[:-1] + act.astype(np.int64), 0]
    declined = np.isin(chosen, _DECLINE)
    out = {}
    for k in np.unique(kind):
        sel = kind == k
        e, d = ent[sel], kl[sel]
        out[FT.ASK_KINDS[k] if k < len(FT.ASK_KINDS) else str(k)] = {
            "n": int(sel.sum()),
            "pass": round(float(declined[sel].mean()), 4),
            "adv": round(float(adv[sel].mean()), 4),
            "ent": round(float(np.nanmean(e)), 4) if np.isfinite(e).any() else None,
            "kl": round(float(np.nanmean(d)), 5) if np.isfinite(d).any() else None,
        }
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
