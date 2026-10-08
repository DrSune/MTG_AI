"""Batch-3 BC arms: capacity A/B and the filtered-DAgger retrain.

Pre-registered design (KNOWLEDGE/2026-10-06 batch-3 mission):

* Arm A  — the batch-2 ``bc_s2`` architecture (~35M): d=512, 8 layers,
  8 heads, ff=3072, dropout 0.0, grad-checkpoint on. Same code path, data,
  seed and schedule as batch 2 — an exact reproduction arm.
* Arm B  — the small arm (~0.5M): d=64, 2 layers, 4 heads, ff=128,
  dropout 0.1, grad-checkpoint off (pointless at this size).
* dagger — whichever arm won the eval margin, retrained with the SAME
  hyperparameters on the 50/50 mix ``episodes_dagger.jsonl`` (original v2
  episodes + filtered-DAgger episodes recorded on model-visited states).
* S0..S4 — the batch-5 size ladder, pre-registered in
  KNOWLEDGE/2026-10-06/21: identical data/seed/gates as A/B; only the
  width/depth knobs move. S0 is exactly arm B, S4 exactly arm A. Every
  report carries the ratio trio (params : gold_lines_train :
  median_seq_len) — small corpora bias the capacity verdict, so the
  model-range-vs-data-volume curve must stay reconstructable.

Laws kept binding (do not silently change):
* EVAL is ALWAYS the binding 44-item family-wise split from
  ``episodes_v2.jsonl`` joined to ``puzzle_corpus.json`` — the dagger file
  reuses pack names, so ``join_corpus`` (which asserts gold-row/item
  alignment per pack) must NEVER see it.
* Best weights are the best TRAIN-loss weights (batch-1 law: no selection
  on the holdout). The per-epoch eval-family accuracy curve is recorded as
  a DIAGNOSTIC only — it never selects the checkpoint.
* Checkpoints save the FULL constructor config so ``ab_duel.BcAsk`` can
  rebuild with ``PointerBC(**config)`` and switch on ``schema == "v2"``.

Run::

    .venv/bin/python -m tools.training.train_bc_v3 --arm A|B|dagger|S0|S1|S2|S3|S3a|S3b|S4 \
        [--episodes FILE] [--prefix bc3_A] [--smoke] [--device auto] \
        [--out-dir DIR] [--fresh]

The nominal ladder labels {0.17M, 0.66M, 2.5M, 10M, 35M} are the owner's
rough estimates; the KNOB SETS above are what is pre-registered. Computed
params are printed per arm and recorded in every report (ratio block), so a
label/actual divergence is visible in the curve, never hidden.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import time
import warnings
from pathlib import Path
from typing import Any

import torch

from tools.training import bc_data_v2
from tools.training.bc_model import PointerBC, collate
from tools.training.train_bc import gate_stats
from tools.training.train_bc_v2 import (
    BCS,
    CORPUS,
    EPISODES,
    SPLIT,
    _head,
    _seq_stats,
    eval_rows,
    is_eval_family,
)

REPO = Path(__file__).resolve().parents[2]
BC2_REPORT = REPO / "tools" / "training" / "bc2_report.json"
MEM_BUDGET_GIB = 4.0
CHECKPOINT_EVERY = 25

#: Pre-registered arm configurations (identical hyperparameters otherwise).
ARMS: dict[str, dict[str, Any]] = {
    "A": {
        "d": 512,
        "layers": 8,
        "heads": 8,
        "ff": 3072,
        "dropout": 0.0,
        "grad_checkpoint": True,
    },
    "B": {
        "d": 64,
        "layers": 2,
        "heads": 4,
        "ff": 128,
        "dropout": 0.1,
        "grad_checkpoint": False,
    },
    # --- batch-5 size ladder (KNOWLEDGE/2026-10-06/21). Knob sets are exactly
    # as pre-registered; nominal labels are the owner's estimates, computed
    # params are printed and reported. grad_checkpoint is a memory knob only
    # (use_reentrant=False recomputes bit-identical forwards), so S3 and every
    # larger arm turn it on to stay under the 4 GiB budget without moving any
    # number.
    "S0": {  # == arm B exactly (~0.17M; computed 169,474 @ vocab 380)
        "d": 64,
        "layers": 2,
        "heads": 4,
        "ff": 128,
        "dropout": 0.1,
        "grad_checkpoint": False,
    },
    "S1": {  # nominal ~0.66M (computed 627,074 @ vocab 380)
        "d": 128,
        "layers": 3,
        "heads": 4,
        "ff": 256,
        "dropout": 0.1,
        "grad_checkpoint": False,
    },
    "S2": {  # nominal ~2.5M (computed 1,766,530 @ vocab 380)
        "d": 192,
        "layers": 4,
        "heads": 6,
        "ff": 512,
        "dropout": 0.1,
        "grad_checkpoint": False,
    },
    "S3": {  # nominal ~10M (computed 5,296,130 @ vocab 380)
        "d": 256,
        "layers": 6,
        "heads": 8,
        "ff": 1024,
        "dropout": 0.1,
        "grad_checkpoint": True,
    },
    # --- batch-7 densification (owner 2026-10-08): the 5.3M->35M rung is too
    # coarse to localise where instability starts. S3a/S3b insert between S3
    # and S4; ONLY size knobs move (dropout stays 0.1 as in S0-S3 — S4's 0.0
    # is inherited verbatim from arm A, an already-known S3->S4 confound).
    "S3a": {  # nominal ~10M (computed 9,963,458 @ vocab 380; 9,980,098 @ 432)
        "d": 320,
        "layers": 7,
        "heads": 8,
        "ff": 1408,
        "dropout": 0.1,
        "grad_checkpoint": True,
    },
    "S3b": {  # nominal ~23M (computed 23,054,082 @ vocab 380; 23,074,050 @ 432)
        "d": 384,
        "layers": 8,
        "heads": 8,
        "ff": 2816,
        "dropout": 0.1,
        "grad_checkpoint": True,
    },
    "S4": {  # == arm A exactly (~35M; computed 35,124,226 @ vocab 380)
        "d": 512,
        "layers": 8,
        "heads": 8,
        "ff": 3072,
        "dropout": 0.0,
        "grad_checkpoint": True,
    },
}
SIZE_LADDER = ("S0", "S1", "S2", "S3", "S3a", "S3b", "S4")
ARM_DATA: dict[str, Path] = {
    "A": EPISODES,
    "B": EPISODES,
    "dagger": REPO / "tools" / "training" / "episodes_dagger.jsonl",
    **{name: EPISODES for name in SIZE_LADDER},
}
DAGGER_ARM = "dagger"  # arch resolved at runtime from --base-arm


def arm_config(arm: str, base_arm: str) -> dict[str, Any]:
    return ARMS[base_arm if arm == DAGGER_ARM else arm]


def ratio_block(
    params: int, mix: dict[str, int], seq: dict[str, Any]
) -> dict[str, Any]:
    """Owner law (KNOWLEDGE/2026-10-06/21): every report carries the ratio
    trio params : gold_lines_train : median_seq_len, so the model-range-vs-
    data-volume curve keeps accumulating across batches. Small corpora bias
    the capacity verdict — a bare accuracy number without the trio is not
    admissible evidence."""
    lines = sum(mix.values())
    return {
        "params": params,
        "gold_lines_train": lines,
        "median_seq_len": seq["median"],
        "params_per_gold_line": round(params / max(lines, 1), 1),
    }


# --------------------------------------------------------------------- data
def load_side(
    train_file: Path,
    eval_families: set[str],
    vocab: dict[str, int],
    smoke: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Train dataset from ``train_file`` (no corpus join — the dagger file
    intentionally breaks that assert); EVAL dataset always from the binding
    ``episodes_v2.jsonl`` WITH the corpus join (attaches cert floors)."""
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    train_eps = bc_data_v2.load_episodes(train_file)
    eval_eps = bc_data_v2.load_episodes(EPISODES)
    if smoke:
        train_eps, eval_eps = train_eps[:8], eval_eps[:8]
    train_ds = bc_data_v2.build_dataset_v2(train_eps, vocab)
    eval_ds = bc_data_v2.build_dataset_v2(eval_eps, vocab)
    joined = bc_data_v2.join_corpus(eval_ds, corpus["items"])
    return train_ds, eval_ds, joined


def data_mix(train_ds: list[dict[str, Any]], eval_families: set[str]) -> dict[str, int]:
    """Gold train rows by episode source (original v2 vs dagger-recorded)."""
    out = {"v2": 0, "dagger": 0}
    for ep in train_ds:
        src = ep.get("source", "v2")
        out[src] = out.get(src, 0) + sum(
            1 for g in ep["gold"] if not is_eval_family(ep["card"], eval_families)
        )
    return out


# --------------------------------------------------------------------- save
def ckpt_config(
    model: PointerBC, vocab_size: int, cfg: dict[str, Any]
) -> dict[str, Any]:
    return {
        "vocab_size": vocab_size,
        "d": cfg["d"],
        "layers": cfg["layers"],
        "heads": cfg["heads"],
        "ff": cfg["ff"],
        "dropout": cfg["dropout"],
        "max_len": model.max_len,
        "grad_checkpoint": cfg["grad_checkpoint"],
    }


def save_ckpt(
    path: Path,
    state: dict[str, Any],
    vocab: dict[str, int],
    config: dict[str, Any],
    seed: int,
    train_info: dict[str, Any],
) -> None:
    torch.save(
        {
            "schema": "v2",  # ab_duel switches on this string to use v2 obs
            "state": state,
            "config": config,
            "vocab": vocab,
            "seed": seed,
            "train_info": train_info,
        },
        path,
    )


# -------------------------------------------------------------------- train
def train_arm(
    cfg: dict[str, Any],
    train_ds: list[dict[str, Any]],
    eval_ds: list[dict[str, Any]],
    vocab: dict[str, int],
    device: torch.device,
    args: argparse.Namespace,
    eval_families: set[str],
    bcs_of: dict[str, int],
    best_path: Path,
    resume: bool,
    quiet: bool = False,
) -> tuple[PointerBC, dict[str, Any]]:
    """Same flat shuffled loop, AdamW/cosine/clip as batch 2 — only the
    architecture is parameterised and an eval-curve diagnostic is added."""
    torch.manual_seed(args.seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(args.seed)
    model = PointerBC(len(vocab), **cfg).to(device)
    if not quiet:
        print(
            f"arm {args.arm}: {sum(p.numel() for p in model.parameters()):,} "
            f"params (d={cfg['d']} layers={cfg['layers']} heads={cfg['heads']} "
            f"ff={cfg['ff']} dropout={cfg['dropout']})"
        )
    # Owner law 2026-10-06 17:25: BPTT shortening must never be silent. Count
    # sequences over the cap BEFORE training and stop with the exact extension
    # instruction (bc_model.encode raises past max_len; we front-run that).
    for ds_name, ds in (("train", train_ds), ("eval", eval_ds)):
        st = _seq_stats(ds, model.max_len)
        if st["over_limit"]:
            raise SystemExit(
                f"{ds_name} dataset has {st['over_limit']} sequences over "
                f"max_len={st['max_len']} (longest {st['max']}). Nothing was "
                f"truncated; extend max_len per KNOWLEDGE/2026-10-06 owner law."
            )
    train_eps = []
    for ep in train_ds:
        kept = [g for g in ep["gold"] if not is_eval_family(ep["card"], eval_families)]
        if kept:
            train_eps.append({**ep, "gold": kept})
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats()
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.epochs)
    rng = torch.Generator().manual_seed(args.seed)
    curve: list[float] = []
    curve_eval: list[float] = []
    best: tuple[float, dict[str, torch.Tensor], int] | None = None
    start_epoch, resumed_from = 0, None
    config = ckpt_config(model, len(vocab), cfg)
    if resume:
        blob = torch.load(best_path, map_location="cpu", weights_only=False)
        if blob.get("schema") != "v2" or blob["config"] != config:
            raise SystemExit(
                f"resume checkpoint {best_path} config mismatch — refusing "
                "(that is the batch-2 silent-clobber trap; use --fresh)"
            )
        model.load_state_dict(blob["state"])
        ti = blob.get("train_info", {})
        start_epoch = int(ti.get("written_at_epoch", 0)) + 1
        curve = list(ti.get("curve", [])) or [float("nan")] * start_epoch
        curve_eval = list(ti.get("curve_eval", []))
        best = (
            float(ti["best_train_loss"]),
            {k: v.detach().clone() for k, v in model.state_dict().items()},
            int(ti["best_epoch"]),
        )
        resumed_from = str(best_path)
        with warnings.catch_warnings():  # fast-forward the cosine schedule
            warnings.simplefilter("ignore")
            for _ in range(start_epoch):
                sched.step()
        if not quiet:
            print(
                f"resumed {best_path}: best {best[0]:.5f} @ {best[2]}, "
                f"continuing at epoch {start_epoch}"
            )
    holdout = [
        {
            **ep,
            "gold": [
                g for g in ep["gold"] if is_eval_family(ep["card"], eval_families)
            ],
        }
        for ep in eval_ds
    ]
    holdout = [h for h in holdout if h["gold"]]
    for epoch in range(start_epoch, args.epochs):
        model.train()
        order = torch.randperm(len(train_eps), generator=rng).tolist()
        losses = []
        for i in range(0, len(order), args.batch):
            eps = [train_eps[j] for j in order[i : i + args.batch]]
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
        # per-epoch 44-item eval diagnostic (never selects the checkpoint)
        rows = eval_rows(model, holdout, device, eval_families, bcs_of)
        cert = [r for r in rows if r["cert"]]
        acc = sum(r["correct"] for r in cert) / max(len(cert), 1)
        curve_eval.append(round(acc, 5))
        if best[2] == epoch or (epoch + 1) % CHECKPOINT_EVERY == 0:
            save_ckpt(
                best_path,
                best[1],
                vocab,
                config,
                args.seed,
                {
                    "best_train_loss": round(best[0], 5),
                    "best_epoch": best[2],
                    "written_at_epoch": epoch,
                    "curve": curve,
                    "curve_eval": curve_eval,
                    "note": "periodic best-train-loss checkpoint (pre-final)",
                },
            )
        if not quiet and (epoch % 20 == 0 or epoch == args.epochs - 1):
            print(f"epoch {epoch:4d} train_loss {e_loss:.5f} eval_acc {acc:.3f}")
        if epoch - best[2] >= args.patience:
            if not quiet:
                print(f"plateau at epoch {epoch} (best {best[0]:.5f} @ {best[2]})")
            break
    assert best is not None
    model.load_state_dict(best[1])
    peak_bytes = torch.cuda.max_memory_allocated() if device.type == "cuda" else 0
    info = {
        "params": sum(p.numel() for p in model.parameters()),
        "train_episodes": len(train_eps),
        "curriculum": "flat (uniform shuffled order; batch-1/2 law)",
        "best_train_loss": round(best[0], 5),
        "best_epoch": best[2],
        "curve": curve,
        "curve_eval": curve_eval,
        "peak_gpu_mib": round(peak_bytes / 2**20, 1),
        "resumed_from": resumed_from,
    }
    return model, info


# ------------------------------------------------------------------------ run
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Batch-3 BC arm trainer.")
    ap.add_argument(
        "--arm",
        required=True,
        choices=("A", "B", "dagger") + SIZE_LADDER,
    )
    ap.add_argument(
        "--base-arm",
        choices=("A", "B"),
        default="B",
        help="architecture for the dagger retrain (the A/B winner)",
    )
    ap.add_argument(
        "--episodes",
        type=Path,
        default=None,
        help="train-episode file (default per arm)",
    )
    ap.add_argument("--prefix", default=None, help="output stem, default bc3_<arm>")
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--device", default="auto", choices=("auto", "cuda", "cpu"))
    ap.add_argument("--epochs", type=int, default=250)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--batch", type=int, default=24)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--patience", type=int, default=60)
    ap.add_argument(
        "--fresh", action="store_true", help="ignore any existing best checkpoint"
    )
    ap.add_argument(
        "--smoke",
        action="store_true",
        help="2 epochs, 8+8 episodes — dry-run law: /tmp only",
    )
    args = ap.parse_args(argv)
    if args.smoke:
        args.epochs = 2
        if args.out_dir is None:
            args.out_dir = Path(
                "/tmp/opencode/b5smoke"
                if args.arm in SIZE_LADDER
                else "/tmp/opencode/b3smoke"
            )

    cfg = arm_config(args.arm, args.base_arm)
    train_file = args.episodes or ARM_DATA[args.arm]
    if args.arm == DAGGER_ARM and not train_file.exists():
        raise SystemExit(f"dagger data {train_file} missing — rollout stage first")
    out_dir = args.out_dir or (REPO / "tools" / "training")
    if args.smoke and REPO in out_dir.resolve().parents:
        raise SystemExit("smoke run must write under /tmp (dry-test law)")
    prefix = args.prefix or (
        f"bc5_{args.arm}" if args.arm in SIZE_LADDER else f"bc3_{args.arm}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    best_path = out_dir / f"{prefix}_best.pt"
    ckpt_path = out_dir / f"{prefix}.pt"
    report_path = out_dir / f"{prefix}_report.json"

    device = torch.device(
        "cuda"
        if args.device == "auto" and torch.cuda.is_available()
        else args.device
        if args.device != "auto"
        else "cpu"
    )
    t0 = time.perf_counter()
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    eval_families = set(split["eval_families"])
    bcs_of = {
        name: m["bcs"] for name, m in json.loads(BCS.read_text())["cards"].items()
    }

    eps_all = bc_data_v2.load_episodes(train_file)
    vocab = bc_data_v2.build_vocab_v2(eps_all[:8] if args.smoke else eps_all)
    train_ds, eval_ds, joined = load_side(train_file, eval_families, vocab, args.smoke)
    for ep in train_ds:
        if len(ep["seq"]) > 1024:
            raise SystemExit(f"{ep['pack']}: seq {len(ep['seq'])} > pos table 1024")
    mix = data_mix(train_ds, eval_families)
    print(
        f"arm={args.arm} episodes={len(train_ds)} vocab={len(vocab)} "
        f"eval_joined={joined} mix={mix}"
    )

    resume = best_path.exists() and not args.fresh
    model, tinfo = train_arm(
        cfg,
        train_ds,
        eval_ds,
        vocab,
        device,
        args,
        eval_families,
        bcs_of,
        best_path,
        resume,
    )
    tinfo["data_mix"] = mix

    rows = eval_rows(model, eval_ds, device, eval_families, bcs_of)
    certified = [r for r in rows if r["cert"]]
    slices = {
        "gold_lines_all": gate_stats(rows, args.seed),
        "train_families": gate_stats(
            [r for r in certified if not r["eval_family"]], args.seed
        ),
        "eval_families": gate_stats(
            [r for r in certified if r["eval_family"]], args.seed
        ),
        "l1_certified": gate_stats(
            [r for r in certified if r["cert"]["l1_ready"]], args.seed
        ),
    }
    g = slices["eval_families"]
    margin = g.get("vs_random", {}).get("beat_margin_se", -99)
    margin_boot = g.get("vs_random", {}).get("margin_bootstrap_se", -99)
    batch2: dict[str, Any] = {"available": False}
    with contextlib.suppress(OSError, KeyError, TypeError):
        b2 = json.loads(BC2_REPORT.read_text())["gates"]["eval_families"]
        batch2 = {
            "available": True,
            "acc": b2.get("acc"),
            "margin_se": b2.get("vs_random", {}).get("beat_margin_se"),
            "delta_margin_se": round(margin - b2["vs_random"]["beat_margin_se"], 2),
        }
    seq_stats = _seq_stats(train_ds, model.max_len)
    report: dict[str, Any] = {
        "produced_by": "tools/training/train_bc_v3.py",
        "arm": args.arm,
        "head": _head(),
        "date": time.strftime("%Y-%m-%d"),
        "schema": "v2 encoder; batch-3 arm (KNOWLEDGE/2026-10-06 pre-registration)",
        "train_file": str(train_file),
        "eval_file": f"{EPISODES} (binding; corpus-joined)",
        "counts": {
            "train_episodes": len(train_ds),
            "eval_joined": joined,
            "eval_family_items": sum(1 for r in certified if r["eval_family"]),
            "train_family_items": sum(1 for r in certified if not r["eval_family"]),
            "data_mix": mix,
        },
        "vocab_size": len(vocab),
        "seq_len": seq_stats,
        "ratio": ratio_block(tinfo["params"], mix, seq_stats),
        "model": {**cfg, "max_len": model.max_len},
        "train": tinfo,
        "device": str(device),
        "gates": slices,
        "eval_margin_se": margin,
        "eval_margin_bootstrap_se": margin_boot,
        "gate_verdict": {
            "gate": "eval-family gold lines vs random floor, >3 SE one-sided "
            "on BOTH iid binomial AND card-cluster bootstrap (KNOWLEDGE 2026-10-07/26)",
            "beats_random_floor_by_3SE": margin > 3.0,
            "beats_random_floor_by_3SE_bootstrap": margin_boot > 3.0,
            "verdict": "PASS" if margin > 3.0 and margin_boot > 3.0 else "NULL",
        },
        "batch2_comparison": batch2,
        "eval_rows": [
            {
                k: r[k]
                for k in (
                    "pack",
                    "card",
                    "ordinal",
                    "gold_idx",
                    "pred_idx",
                    "correct",
                    "eval_family",
                    "quartile",
                )
            }
            for r in rows
        ],
        "gpu_peak_gib": round(tinfo["peak_gpu_mib"] / 1024.0, 2),
        "gpu_budget_gib": MEM_BUDGET_GIB,
        "wall_seconds": round(time.perf_counter() - t0, 1),
    }
    save_ckpt(
        ckpt_path,
        model.state_dict(),
        vocab,
        ckpt_config(model, len(vocab), cfg),
        args.seed,
        {k: v for k, v in tinfo.items() if k != "curve"},
    )
    report_path.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "arm": args.arm,
                "eval_margin_se": margin,
                "verdict": report["gate_verdict"]["verdict"],
                "wall_s": report["wall_seconds"],
            }
        )
    )
    print(f"wrote {report_path} and {ckpt_path}")
    peak_gib = report["gpu_peak_gib"]
    if device.type == "cuda" and peak_gib >= MEM_BUDGET_GIB:
        print(f"MEM BUDGET BREACH: peak {peak_gib:.2f} GiB >= {MEM_BUDGET_GIB}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
