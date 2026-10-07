"""Batch-1 BC floor run: train the S1 pointer model on gold lines, evaluate
against the certified null/random floors, write checkpoint + bc_report.json.

Honesty law (design doc 09): this batch validates the SCHEMA and the LOOP.
Data is 119 gold asks over 96 packs — overfitting is fine; the honesty
number is the BY-ITEM holdout (packs whose sha256 % 5 == 0 never
contribute gold targets to training). The gate is the cert corpus:
gold-line accuracy must beat the measured null and random floors by >3 SE
(binomial over items). A null result says the observation schema or the
extraction is broken — it is reported, not papered over.

Run::

    .venv/bin/python -m tools.training.train_bc [--device cuda|cpu|auto]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import time
from pathlib import Path
from typing import Any

import torch

from tools.training import bc_data
from tools.training.bc_model import PointerBC, collate

REPO = Path(__file__).resolve().parents[2]
EPISODES = REPO / "tools" / "training" / "episodes.jsonl"
CORPUS = REPO / "tools" / "audit" / "puzzle_corpus.json"
CKPT = REPO / "tools" / "training" / "bc_s1.pt"
REPORT = REPO / "tools" / "training" / "bc_report.json"
MEM_BUDGET_GIB = 4.0


def is_holdout_pack(pack: str) -> bool:
    """Deterministic ITEM-level split: whole packs (all their asks) held out."""
    return int.from_bytes(hashlib.sha256(pack.encode()).digest()[:8], "big") % 5 == 0


# ------------------------------------------------------------------ evaluation
@torch.no_grad()
def eval_rows(
    model: PointerBC, dataset: list[dict[str, Any]], device: torch.device
) -> list[dict[str, Any]]:
    """Argmax-vs-gold on every gold row, dataset order (pack-sorted, ask
    order). Deterministic given (checkpoint, episodes): pure forward."""
    model.eval()
    out: list[dict[str, Any]] = []
    for ep in dataset:  # per-episode: tiny data, no cross-episode padding noise
        batch = collate([ep], len(model.tok_emb.weight), device)
        if batch["n_rows"] == 0:
            continue
        logits = model.forward(
            batch["tokens"],
            batch["pad_mask"],
            batch["gold_batch"],
            batch["gold_pos"],
            batch["cand_ids"],
            batch["cand_mask"],
            batch["is_pass"],
        )
        pred = logits.argmax(-1)
        for i, g in enumerate(ep["gold"]):
            out.append(
                {
                    "pack": ep["pack"],
                    "card": ep["card"],
                    "ordinal": g["ordinal"],
                    "what": g["what"],
                    "candidates": g["candidates"],
                    "gold_idx": g["gold_idx"],
                    "pred_idx": int(pred[i]),
                    "correct": bool(int(pred[i]) == g["gold_idx"]),
                    "holdout": is_holdout_pack(ep["pack"]),
                    "cert": g.get("cert"),
                }
            )
    return out


def binomial_stats(k: int, n: int, p0: float) -> dict[str, float]:
    """z-score + exact one-sided binomial tail P(X>=k) against floor p0."""
    if n == 0:
        return {"n": 0, "k": 0}
    acc = k / n
    p = min(max(p0, 1.0 / (2 * n)), 1.0 - 1.0 / (2 * n))  # continuity clamp
    se = math.sqrt(p * (1.0 - p) / n)
    z = (acc - p0) / se
    tail = 0.0
    if p0 <= 0.0:
        tail = 1.0 if k >= 0 else 0.0  # floor 0: any k is ">= floor", vacuous
    elif p0 >= 1.0:
        tail = 1.0 if k >= n else 0.0
    else:
        for i in range(k, n + 1):
            tail += math.comb(n, i) * p0**i * (1.0 - p0) ** (n - i)
    return {
        "n": n,
        "k": k,
        "acc": round(acc, 4),
        "floor_p0": round(p0, 4),
        "se": round(se, 4),
        "beat_margin_se": round(z, 2),
        "binom_p_one_sided": float(f"{min(tail, 1.0):.3e}"),
    }


def cluster_bootstrap_stats(
    by_card: dict[str, list[int]],
    p0: float,
    B: int = 4000,
    seed: int = 1,
) -> dict[str, Any]:
    """Card-cluster bootstrap of accuracy against a FIXED floor p0.

    KNOWLEDGE/2026-10-07/26 falsification: items of one card are strongly
    correlated (50 eval items = 32 cards), so the binomial SE is the wrong
    model and inflates the margin ~30%. Resample CARDS with replacement
    (items stay grouped, outcomes fixed within card). Each resample's
    correct count is normalised by the ORIGINAL item count — denominator
    size jitter is kept in the SE, never divided out (the conservative
    choice; reproduces the /26 spot-check margins 3.0-3.5 within 0.06).
    The floor is held fixed across resamples — per-item floors are not in
    the persisted rows, so this is conservative there too.
    ``margin_bootstrap_se`` is (acc - p0) / stdev(bootstrap accs);
    ``p_beats_floor`` is the share of resamples whose acc exceeds p0.
    Degenerate all-equal samples give SE 0 and a +/-inf margin (never
    happens against a real floor).
    """
    cards = sorted(by_card)
    groups = [by_card[c] for c in cards]
    n_clusters = len(groups)
    n_items = sum(len(g) for g in groups)
    acc = sum(sum(g) for g in groups) / n_items
    rng = random.Random(seed)
    accs: list[float] = []
    above = 0
    for _ in range(B):
        picks = [groups[rng.randrange(n_clusters)] for _ in range(n_clusters)]
        a = sum(sum(p) for p in picks) / n_items
        accs.append(a)
        if a > p0:
            above += 1
    mean = sum(accs) / B
    boot_se = math.sqrt(sum((a - mean) ** 2 for a in accs) / (B - 1))
    margin = float("inf") if boot_se == 0.0 else (acc - p0) / boot_se
    return {
        "n_clusters": n_clusters,
        "bootstrap_se": round(boot_se, 4),
        "margin_bootstrap_se": round(margin, 2),
        "p_beats_floor": above / B,
        "bootstrap_B": B,
        "bootstrap_seed": seed,
    }


def gate_stats(rows: list[dict[str, Any]], boot_seed: int = 1) -> dict[str, Any]:
    """Accuracy vs the measured floors for one slice of gold rows.

    Each floor block carries the iid binomial numbers AND the honest
    card-cluster bootstrap numbers side by side (see
    cluster_bootstrap_stats).
    """
    certified = [r for r in rows if r["cert"]]
    k = sum(r["correct"] for r in certified)
    n = len(certified)
    mean_rand = sum(r["cert"]["random"] for r in certified) / n if n else 0.0
    mean_null = sum(r["cert"]["null"] for r in certified) / n if n else 0.0
    res: dict[str, Any] = {"rows": n, "correct": k}
    if n:
        res["acc"] = round(k / n, 4)
        by_card: dict[str, list[int]] = {}
        for r in certified:
            by_card.setdefault(r["card"], []).append(1 if r["correct"] else 0)
        res["vs_random"] = binomial_stats(k, n, mean_rand) | cluster_bootstrap_stats(
            by_card, mean_rand, seed=boot_seed
        )
        res["vs_null"] = binomial_stats(k, n, mean_null) | cluster_bootstrap_stats(
            by_card, mean_null, seed=boot_seed
        )
    return res


# ---------------------------------------------------------------------- train
def train(
    dataset: list[dict[str, Any]],
    vocab: dict[str, int],
    device: torch.device,
    epochs: int,
    lr: float,
    batch: int,
    seed: int,
    patience: int,
    quiet: bool = False,
) -> tuple[PointerBC, dict[str, Any]]:
    torch.manual_seed(seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(seed)
    model = PointerBC(len(vocab)).to(device)
    train_eps = []
    for ep in dataset:
        kept = [g for g in ep["gold"] if not is_holdout_pack(ep["pack"])]
        if kept:
            train_eps.append({**ep, "gold": kept})
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    rng = torch.Generator().manual_seed(seed)
    curve: list[float] = []
    best: tuple[float, dict[str, torch.Tensor], int] | None = None
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats()
    for epoch in range(epochs):
        model.train()
        order = torch.randperm(len(train_eps), generator=rng).tolist()
        losses = []
        for i in range(0, len(order), batch):
            eps = [train_eps[j] for j in order[i : i + batch]]
            b = collate(eps, len(vocab), device)
            with torch.autocast(
                device_type=device.type,
                dtype=torch.bfloat16,
                enabled=device.type == "cuda",
            ):
                loss = model.loss(
                    b["tokens"],
                    b["pad_mask"],
                    b["gold_batch"],
                    b["gold_pos"],
                    b["cand_ids"],
                    b["cand_mask"],
                    b["is_pass"],
                    b["gold_idx"],
                )
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            losses.append(float(loss.detach()))
        e_loss = sum(losses) / len(losses)
        curve.append(round(e_loss, 5))
        sched.step()
        if best is None or e_loss < best[0]:
            best = (
                e_loss,
                {k: v.detach().clone() for k, v in model.state_dict().items()},
                epoch,
            )
        if not quiet and (epoch % 20 == 0 or epoch == epochs - 1):
            print(f"epoch {epoch:4d} train_loss {e_loss:.5f}")
        if epoch - best[2] >= patience:
            # patience full epochs without a NEW best. The old window rule
            # (min(curve[-patience:]) > best-1e-3) always fired at
            # len(curve)==patience because best itself sat inside the window.
            if not quiet:
                print(f"plateau at epoch {epoch} (best {best[0]:.5f} @ {best[2]})")
            break
    assert best is not None
    model.load_state_dict(best[1])
    peak_bytes = torch.cuda.max_memory_allocated() if device.type == "cuda" else 0
    info = {
        "params": sum(p.numel() for p in model.parameters()),
        "train_episodes": len(train_eps),
        "curve": curve,
        "best_train_loss": round(best[0], 5),
        "best_epoch": best[2],
        "peak_gpu_mib": round(peak_bytes / 2**20, 1),
    }
    return model, info


# ------------------------------------------------------------------------ run
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--device", default="auto", choices=("auto", "cuda", "cpu"))
    ap.add_argument("--epochs", type=int, default=250)
    # 1e-3 bounced the loss (0.53->0.67) and plateau-fired before the
    # cosine cycle annealed; 3e-4 over a full 250-epoch cycle converges.
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--batch", type=int, default=24)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--patience", type=int, default=60)
    ap.add_argument("--record", action="store_true", help="force re-recording")
    args = ap.parse_args(argv)

    device = torch.device(
        "cuda"
        if args.device == "auto" and torch.cuda.is_available()
        else args.device
        if args.device != "auto"
        else "cpu"
    )
    t0 = time.perf_counter()
    if args.record or not EPISODES.exists():
        from tools.training import packrec

        packrec.main(["--out", str(EPISODES)])
    episodes = bc_data.load_episodes(EPISODES)
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    vocab = bc_data.build_vocab(episodes)
    dataset = bc_data.build_dataset(episodes, vocab)
    joined = bc_data.join_corpus(dataset, corpus["items"])
    print(f"episodes={len(dataset)} vocab={len(vocab)} gold_joined={joined}")

    model, tinfo = train(
        dataset,
        vocab,
        device,
        args.epochs,
        args.lr,
        args.batch,
        args.seed,
        args.patience,
    )
    rows = eval_rows(model, dataset, device)
    certified = [r for r in rows if r["cert"]]
    slices = {
        "gold_lines_all": gate_stats(rows, args.seed),
        "holdout_items": gate_stats([r for r in certified if r["holdout"]], args.seed),
        "train_items": gate_stats(
            [r for r in certified if not r["holdout"]], args.seed
        ),
        "l1_certified": gate_stats(
            [r for r in certified if r["cert"]["l1_ready"]], args.seed
        ),
    }
    peak_gib = tinfo["peak_gpu_mib"] / 1024.0
    report: dict[str, Any] = {
        "produced_by": "tools/training/train_bc.py",
        "head": "f58675c",
        "date": "2026-10-05",
        "counts": {
            "packs_with_decisions": 133,
            "packs_with_menu_asks": len(dataset),
            "gold_lines": len(rows),
            "gold_joined_to_corpus": joined,
            "l1_ready": sum(r["cert"]["l1_ready"] for r in certified),
            "holdout_items": sum(1 for r in certified if r["holdout"]),
        },
        "vocab_size": len(vocab),
        "model": {
            "d": 512,
            "layers": 8,
            "heads": 8,
            "ff": 3072,
            "grad_checkpoint": True,
            "dropout": 0.0,
        },
        "train": tinfo,
        "device": str(device),
        "eval_rows": [
            {
                k: r[k]
                for k in (
                    "pack",
                    "ordinal",
                    "gold_idx",
                    "pred_idx",
                    "correct",
                    "holdout",
                )
            }
            for r in rows
        ],
        "gates": slices,
        "gpu_peak_gib": round(peak_gib, 2),
        "gpu_budget_gib": MEM_BUDGET_GIB,
        "wall_seconds": round(time.perf_counter() - t0, 1),
    }
    g = slices["gold_lines_all"]
    # /26: the iid binomial margin is inflated ~30% by intra-card
    # correlation — PASS requires BOTH the iid and the cluster margin > 3.
    beat_rand = (
        g["vs_random"]["beat_margin_se"] > 3.0
        and g["vs_random"]["margin_bootstrap_se"] > 3.0
    )
    beat_null = (
        g["vs_null"]["beat_margin_se"] > 3.0
        and g["vs_null"]["margin_bootstrap_se"] > 3.0
    )
    verdict = "PASS" if beat_rand and beat_null else "NULL"
    report["gate_verdict"] = {
        "beats_random_floor_by_3SE": beat_rand,
        "beats_null_floor_by_3SE": beat_null,
        "gate": "gold lines vs floors, >3 SE one-sided on BOTH iid AND card-cluster bootstrap",
        "verdict": verdict,
        "reading": (
            "BC on the cert schema clears every measured floor: schema + "
            "loop validated, proceed to batch 2."
            if verdict == "PASS"
            else "BC cannot beat the certified floors: the observation "
            "schema or extraction is broken — do NOT scale; fix C2/extractor."
        ),
    }
    CKPT.write_bytes(_save_bytes(model, vocab, tinfo, args))
    REPORT.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "gates": slices,
                "gpu_peak_gib": report["gpu_peak_gib"],
                "verdict": verdict,
            },
            indent=1,
        )
    )
    print(f"wrote {REPORT} and {CKPT}")
    if device.type == "cuda" and peak_gib >= MEM_BUDGET_GIB:
        print(f"MEM BUDGET BREACH: peak {peak_gib:.2f} GiB >= {MEM_BUDGET_GIB}")
        return 1
    return 0


def _save_bytes(
    model: PointerBC, vocab: dict[str, int], tinfo: dict, args: argparse.Namespace
) -> bytes:
    import io

    buf = io.BytesIO()
    torch.save(
        {
            "state": model.state_dict(),
            "config": {
                "vocab_size": len(vocab),
                "d": model.d,
                "max_len": model.max_len,
            },
            "vocab": vocab,
            "train_info": {k: v for k, v in tinfo.items() if k != "curve"},
            "seed": args.seed,
        },
        buf,
    )
    return buf.getvalue()


if __name__ == "__main__":
    raise SystemExit(main())
