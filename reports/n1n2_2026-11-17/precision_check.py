"""N1's pool on the precision paths the runs use, on r28's v2 (read only), on the CPU (a training
run held the GPU): fp32, a bf16 autocast with a backward (the trainer's, ppo.ppo_train; CPU
autocast casts matmuls to bf16 as CUDA's does) and a bf16 copy (the learner's --infer-bf16). Each
against the old gather-and-mean (width 128, inlined), on recorded decisions ``v2_side.py`` wrote.

    CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 nice -n 19 .venv/bin/python \
        reports/n1n2_2026-11-17/precision_check.py NEW_SIDE.pkl > reports/n1n2_2026-11-17/precision_check.txt
"""
from __future__ import annotations

import pickle
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import torch

from tools.selfplay import model as M

CKPT = "/home/sune/Desktop/MTG_AI/runs/r28_looks/r28_v2.pt"
DEV = "cpu"


def gather_pool(net: torch.nn.Module, rows: list[list[int]]) -> torch.Tensor:
    """card_table_emb before N1: each row's ids (at most 128) gathered and averaged."""
    ids = torch.zeros(len(rows), 128, dtype=torch.long)
    for i, r in enumerate(rows):
        ids[i, :len(r)] = torch.tensor(r, dtype=torch.long)
    emb = net.ir_emb(ids)
    mask = (ids > 0).unsqueeze(-1).to(emb.dtype)
    return (emb * mask).sum(1) / mask.sum(1).clamp(min=1.0)


def main(side: str) -> None:
    torch.set_num_threads(2)
    feats = pickle.loads(Path(side).read_bytes())["saved"]["recorded"]["feats"][:256]
    net, table, _ = M.load(CKPT, DEV)
    b = M.collate(feats, DEV)
    k = [f["opts_i"].shape[0] for f in feats]

    def run(model, batch, old: bool, autocast: bool = False):
        if old:
            model.card_table_emb = lambda: gather_pool(model, table.ir)
        try:
            with torch.autocast(DEV, dtype=torch.bfloat16, enabled=autocast):
                dtype = model.card_table_emb().dtype
                logits, value = model(batch)
        finally:
            model.__dict__.pop("card_table_emb", None)
        return logits.float(), value.float(), dtype

    def report(label: str, lo, vo, ln, vn) -> None:
        dl = max(float((lo[i, :n] - ln[i, :n]).abs().max()) for i, n in enumerate(k))
        same = sum(int(lo[i, :n].argmax()) == int(ln[i, :n].argmax()) for i, n in enumerate(k))
        print(f"{label}: max |dlogit| {dl:.2e}, max |dvalue| {float((vo - vn).abs().max()):.2e}, "
              f"greedy choices equal {same}/{len(feats)}")

    print(f"# {Path(CKPT).name}, {len(feats)} recorded decisions, {DEV}")
    with torch.no_grad():
        lo, vo, _ = run(net, b, old=True)
        ln, vn, _ = run(net, b, old=False)
    report("fp32, old against new", lo, vo, ln, vn)
    f32 = (lo, vo)
    grads, outs = [], []
    for old in (True, False):
        net.zero_grad(set_to_none=True)
        lg, v, dtype = run(net, b, old=old, autocast=True)
        (torch.log_softmax(lg, -1)[:, 0].sum() + v.sum()).backward()  # option 0 is always real
        grads.append(net.ir_emb.weight.grad.detach().clone())
        outs += [lg.detach(), v.detach()]
        print(f"bf16 autocast, {'old gather' if old else 'count matrix'}: the pool in {dtype}; "
              f"ir_emb grad finite {bool(torch.isfinite(grads[-1]).all())}, norm {grads[-1].norm():.4e}")
    report("bf16 autocast, old against new", *outs)
    report("  (bf16's own noise: the old code, autocast against fp32)", *f32, *outs[:2])
    print(f"bf16 autocast: ir_emb grad relative diff {float((grads[0] - grads[1]).norm() / grads[0].norm()):.2e}")
    bf = M.load(CKPT, DEV)[0].to(torch.bfloat16).eval()
    bb = {key: (val.to(torch.bfloat16) if val.is_floating_point() else val) for key, val in b.items()}
    with torch.no_grad():
        lo, vo, _ = run(bf, bb, old=True)
        ln, vn, dtype = run(bf, bb, old=False)
    report(f"bf16 copy (the pool in {dtype}, counts {bf.ir_counts.dtype}), old against new", lo, vo, ln, vn)
    report("  (bf16's own noise: the old code, the bf16 copy against fp32)", *f32, lo, vo)
    # the pool's own time, fp32, 2 threads: the median of 12
    for label, pool in (("old gather", lambda: gather_pool(net, table.ir)), ("count matrix", net.card_table_emb)):
        for grad in (False, True):
            ts = []
            for _ in range(12):
                net.zero_grad(set_to_none=True)
                t = time.perf_counter()
                if grad:
                    pool().sum().backward()
                else:
                    with torch.no_grad():
                        pool()
                ts.append(time.perf_counter() - t)
            print(f"time, {label}, {'forward and backward' if grad else 'forward'}: "
                  f"{1000 * sorted(ts)[6]:.1f} ms")


if __name__ == "__main__":
    main(sys.argv[1])
