"""Batch-2 BC run: observation-schema v2 (grounded candidates + fuller
zones), FAMILY-WISE split, trained gold lines, honest gate.

Batch 1 (train_bc.py) was a certified NULL on its item holdout: 0.2857 vs a
re-measured random floor of 0.4517 (bc_report.json). The diagnosis
(KNOWLEDGE/2026-10-05/10-batch1-bc-floor.md) was an observation gap — 155/357
candidate surfaces had zero tokens in the stream. v2 (bc_data_v2) grounds
every gold candidate and lists the hidden zones, observation-only.

The split law changed too. The batch-1 pack-sha item split let a CARD train
on one pack's asks and be tested on another's — same decision policy, so the
holdout leaked. ``tools/audit/eval_split.json`` is BINDING: whole card
FAMILIES (2 of every 5 by sorted-name index) never contribute a single gold
target. The gate is the EVAL-family slice beating its own binomial random
AND null floors by > 3 SE one-sided.

Curriculum note (honesty): BCS-quartile bands were planned, but 44 eval
families / 75 train items is far too thin to bend a training ORDER into
capability bands and still attribute anything to them — training is FLAT
(uniform shuffled order, identical to batch 1). BCS quartiles appear in the
report only as a secondary READ of where the model stands, never as a lever.

Run::

    .venv/bin/python -m tools.training.train_bc_v2 [--device cuda|cpu|auto]
                                                   [--record]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import warnings
from pathlib import Path
from typing import Any

import torch

from tools.training import bc_data_v2
from tools.training.bc_model import PointerBC, collate
from tools.training.train_bc import binomial_stats, gate_stats

REPO = Path(__file__).resolve().parents[2]
EPISODES = REPO / "tools" / "training" / "episodes_v2.jsonl"
CORPUS = REPO / "tools" / "audit" / "puzzle_corpus.json"
SPLIT = REPO / "tools" / "audit" / "eval_split.json"
BCS = REPO / "tools" / "audit" / "bcs.json"
BATCH1_REPORT = REPO / "tools" / "training" / "bc_report.json"
CKPT = REPO / "tools" / "training" / "bc_s2.pt"
CKPT_BEST = REPO / "tools" / "training" / "bc_s2_best.pt"
REPORT = REPO / "tools" / "training" / "bc2_report.json"
MEM_BUDGET_GIB = 4.0
CHECKPOINT_EVERY = 25  # epochs between forced best-ckpt writes (crash insurance)


def load_split() -> dict[str, Any]:
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    return split


def is_eval_family(card: str, eval_families: set[str]) -> bool:
    """Family-wise law: a card's WHOLE family sits on one side."""
    return card in eval_families


# ------------------------------------------------------------------ evaluation
@torch.no_grad()
def eval_rows(
    model: PointerBC,
    dataset: list[dict[str, Any]],
    device: torch.device,
    eval_families: set[str],
    bcs_of: dict[str, int],
) -> list[dict[str, Any]]:
    """Argmax-vs-gold on every gold row, deterministic pure forward."""
    model.eval()
    out: list[dict[str, Any]] = []
    for ep in dataset:
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
                    "eval_family": is_eval_family(ep["card"], eval_families),
                    "bcs": bcs_of.get(ep["card"]),
                    "cert": g.get("cert"),
                }
            )
    return rows_with_quartiles(out)


def rows_with_quartiles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach a BCS quartile (1=easiest) computed from the gold-row bcs
    values themselves; ties go to the LOWER quartile. Missing bcs -> None."""
    vals = sorted(r["bcs"] for r in rows if r["bcs"] is not None)
    cuts = [vals[len(vals) // 4], vals[len(vals) // 2], vals[3 * len(vals) // 4]]
    for r in rows:
        b = r["bcs"]
        r["quartile"] = None if b is None else 1 + sum(b > c for c in cuts)
    return rows


def _save_bytes(
    model: PointerBC, vocab: dict[str, int], tinfo: dict, args: argparse.Namespace
) -> bytes:
    import io

    buf = io.BytesIO()
    torch.save(
        {
            "schema": "v2",
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


def _save_best_ckpt(
    state: dict[str, Any],
    vocab: dict[str, int],
    model: PointerBC,
    seed: int,
    best_loss: float,
    best_epoch: int,
    epoch: int,
    curve: list[float],
) -> None:
    """Crash insurance: inference-loadable snapshot of the BEST weights so
    far, rewritten on every improvement and at least every CHECKPOINT_EVERY
    epochs. Same blob schema as the final CKPT (extra epoch bookkeeping is
    ignored by loaders)."""
    torch.save(
        {
            "schema": "v2",
            "state": state,
            "config": {
                "vocab_size": len(vocab),
                "d": model.d,
                "max_len": model.max_len,
            },
            "vocab": vocab,
            "seed": seed,
            "train_info": {
                "best_train_loss": round(best_loss, 5),
                "best_epoch": best_epoch,
                "written_at_epoch": epoch,
                "curve": curve,
                "note": "periodic best-model checkpoint (pre-final)",
            },
        },
        CKPT_BEST,
    )


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
    eval_families: set[str],
    quiet: bool = False,
    resume: str | None = None,
) -> tuple[PointerBC, dict[str, Any]]:
    """Identical loop to batch 1 (flat uniform order — see module docstring),
    except the holdout filter is FAMILY-wise via eval_split.json."""
    torch.manual_seed(seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(seed)
    model = PointerBC(len(vocab)).to(device)
    train_eps = []
    for ep in dataset:
        kept = [g for g in ep["gold"] if not is_eval_family(ep["card"], eval_families)]
        if kept:
            train_eps.append({**ep, "gold": kept})
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)
    rng = torch.Generator().manual_seed(seed)
    curve: list[float] = []
    best: tuple[float, dict[str, torch.Tensor], int] | None = None
    start_epoch = 0
    resumed_from: str | None = None
    if resume:
        blob = torch.load(resume, map_location="cpu", weights_only=False)
        if blob.get("schema") != "v2" or blob["config"]["vocab_size"] != len(vocab):
            raise SystemExit(
                f"resume checkpoint {resume} incompatible with vocab={len(vocab)}"
            )
        model.load_state_dict(blob["state"])
        ti = blob.get("train_info", {})
        start_epoch = int(ti.get("written_at_epoch", 0)) + 1
        curve = list(ti.get("curve", []))
        if not curve:
            curve = [float("nan")] * start_epoch  # older ckpt: no curve saved
        best = (
            float(ti["best_train_loss"]),
            {k: v.detach().clone() for k, v in model.state_dict().items()},
            int(ti["best_epoch"]),
        )
        resumed_from = resume
        with warnings.catch_warnings():  # fast-forward the cosine schedule
            warnings.simplefilter("ignore")
            for _ in range(start_epoch):
                sched.step()
        if not quiet:
            print(
                f"resumed from {resume}: best {best[0]:.5f} @ epoch {best[2]}, "
                f"continuing at epoch {start_epoch} (batch order not bit-exact)"
            )
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats()
    for epoch in range(start_epoch, epochs):
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
        # crash insurance (this exact run died at ep~100 with no artifact):
        # write the best-so-far blob on every improvement and at least every
        # CHECKPOINT_EVERY epochs. The loop scores TRAIN loss per epoch (no
        # per-epoch holdout pass exists here); best-train weights are what
        # the final model loads anyway (batch-1 law), so this is the same
        # artifact the run would end with if it survived.
        if best[2] == epoch or (epoch + 1) % CHECKPOINT_EVERY == 0:
            _save_best_ckpt(best[1], vocab, model, seed, best[0], best[2], epoch, curve)
        if not quiet and (epoch % 20 == 0 or epoch == epochs - 1):
            print(f"epoch {epoch:4d} train_loss {e_loss:.5f}")
        if epoch - best[2] >= patience:
            if not quiet:
                print(f"plateau at epoch {epoch} (best {best[0]:.5f} @ {best[2]})")
            break
    assert best is not None
    model.load_state_dict(best[1])
    peak_bytes = torch.cuda.max_memory_allocated() if device.type == "cuda" else 0
    info = {
        "params": sum(p.numel() for p in model.parameters()),
        "train_episodes": len(train_eps),
        "curriculum": "flat (uniform shuffled order; see module docstring)",
        "curve": curve,
        "best_train_loss": round(best[0], 5),
        "best_epoch": best[2],
        "peak_gpu_mib": round(peak_bytes / 2**20, 1),
        "resumed_from": resumed_from,
    }
    return model, info


# ------------------------------------------------------------------------ run
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--device", default="auto", choices=("auto", "cuda", "cpu"))
    ap.add_argument("--epochs", type=int, default=250)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--batch", type=int, default=24)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--patience", type=int, default=60)
    ap.add_argument(
        "--resume",
        default=None,
        help="resume weights/epoch from a bc_s2_best.pt checkpoint",
    )
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
        from tools.training import packrec_v2

        packrec_v2.main(["--out", str(EPISODES)])
    episodes = bc_data_v2.load_episodes(EPISODES)
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    split = load_split()
    eval_families = set(split["eval_families"])
    bcs_of = {
        name: meta["bcs"] for name, meta in json.loads(BCS.read_text())["cards"].items()
    }
    vocab = bc_data_v2.build_vocab_v2(episodes)
    dataset = bc_data_v2.build_dataset_v2(episodes, vocab)
    joined = bc_data_v2.join_corpus(dataset, corpus["items"])
    seq_len_stats = _seq_stats(dataset)
    print(
        f"episodes={len(dataset)} vocab={len(vocab)} gold_joined={joined} "
        f"seq={seq_len_stats}"
    )

    model, tinfo = train(
        dataset,
        vocab,
        device,
        args.epochs,
        args.lr,
        args.batch,
        args.seed,
        args.patience,
        eval_families,
        resume=args.resume,
    )
    rows = eval_rows(model, dataset, device, eval_families, bcs_of)
    certified = [r for r in rows if r["cert"]]
    slices = {
        "gold_lines_all": gate_stats(rows),
        "train_families": gate_stats([r for r in certified if not r["eval_family"]]),
        "eval_families": gate_stats([r for r in certified if r["eval_family"]]),
        "l1_certified": gate_stats([r for r in certified if r["cert"]["l1_ready"]]),
    }
    slices["eval_family_quartiles"] = {
        f"q{q}": gate_stats(
            [r for r in certified if r["eval_family"] and r["quartile"] == q]
        )
        for q in (1, 2, 3, 4)
    }
    slices["all_quartiles"] = {
        f"q{q}": gate_stats([r for r in certified if r["quartile"] == q])
        for q in (1, 2, 3, 4)
    }

    peak_gib = tinfo["peak_gpu_mib"] / 1024.0
    report: dict[str, Any] = {
        "produced_by": "tools/training/train_bc_v2.py",
        "head": _head(),
        "date": "2026-10-06",
        "schema": "v2 (bc_data_v2: grounded candidates + library/gyr/exl zones)",
        "counts": {
            "episodes": len(dataset),
            "gold_lines": len(rows),
            "gold_joined_to_corpus": joined,
            "l1_ready": sum(r["cert"]["l1_ready"] for r in certified),
            "eval_family_items": sum(1 for r in certified if r["eval_family"]),
            "train_family_items": sum(1 for r in certified if not r["eval_family"]),
            "grounded_candidates": sum(
                1 for ep in episodes for row in ep["asks"] if row.get("ground")
            ),
        },
        "split": {
            "file": "tools/audit/eval_split.json",
            "rule": split["rule"],
            "n_families": split["n_families"],
            "eval_families": len(eval_families),
            "train_families": len(split["train_families"]),
            "train_items": split["train_items"],
            "eval_items": split["eval_items"],
        },
        "vocab_size": len(vocab),
        "seq_len": seq_len_stats,
        "model": {
            "d": 512,
            "layers": 8,
            "heads": 8,
            "ff": 3072,
            "grad_checkpoint": True,
            "dropout": 0.0,
            "max_len": model.max_len,
        },
        "train": tinfo,
        "device": str(device),
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
        "gates": slices,
        "batch1_comparison": _batch1_comparison(slices),
        "gpu_peak_gib": round(peak_gib, 2),
        "gpu_budget_gib": MEM_BUDGET_GIB,
        "wall_seconds": round(time.perf_counter() - t0, 1),
    }
    g = slices["eval_families"]
    beat_rand = g.get("vs_random", {}).get("beat_margin_se", -99) > 3.0
    beat_null = g.get("vs_null", {}).get("beat_margin_se", -99) > 3.0
    verdict = "PASS" if beat_rand and beat_null else "NULL"
    report["gate_verdict"] = {
        "gate": "eval-family gold lines vs their own floors, >3 SE one-sided",
        "beats_random_floor_by_3SE": beat_rand,
        "beats_null_floor_by_3SE": beat_null,
        "verdict": verdict,
        "reading": (
            "The v2 observation schema generalizes to unseen card families: "
            "grounding closed the batch-1 gap; proceed to the Elo sanity."
            if verdict == "PASS"
            else "Even with grounded candidates the eval families do not beat "
            "their floors: the gap is NOT (only) observation coverage — do "
            "NOT scale; re-diagnose before batch 3."
        ),
    }
    CKPT.write_bytes(_save_bytes(model, vocab, tinfo, args))
    REPORT.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"gates": slices, "verdict": verdict}, indent=1))
    print(f"wrote {REPORT} and {CKPT}")
    if device.type == "cuda" and peak_gib >= MEM_BUDGET_GIB:
        print(f"MEM BUDGET BREACH: peak {peak_gib:.2f} GiB >= {MEM_BUDGET_GIB}")
        return 1
    return 0


def _seq_stats(dataset: list[dict[str, Any]]) -> dict[str, int]:
    ls = sorted(len(ep["seq"]) for ep in dataset)
    return {
        "min": ls[0],
        "median": ls[len(ls) // 2],
        "max": ls[-1],
        "max_len": 1024,
    }


def _head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(REPO),
        ).stdout.strip()
    except Exception:
        return "unknown"


def _batch1_comparison(slices: dict[str, Any]) -> dict[str, Any]:
    """Batch-1's honest holdout number vs this run's eval-family number, with
    each slice measured against ITS OWN re-measured floor. Not an apples-to-
    apples acc/acc: the populations differ (21 pack-holdout items, 44
    family-eval items); the comparable quantity is the SE margin over floor."""
    try:
        b1 = json.loads(BATCH1_REPORT.read_text())["gates"]["holdout_items"]
    except Exception:
        return {"available": False}
    out: dict[str, Any] = {
        "available": True,
        "batch1_holdout_items": {
            "n": b1["rows"],
            "acc": b1.get("acc"),
            "random_floor": b1.get("vs_random", {}).get("floor_p0"),
            "margin_se": b1.get("vs_random", {}).get("beat_margin_se"),
        },
        "batch2_eval_families": {
            "n": slices["eval_families"]["rows"],
            "acc": slices["eval_families"].get("acc"),
            "random_floor": slices["eval_families"]
            .get("vs_random", {})
            .get("floor_p0"),
            "margin_se": slices["eval_families"]
            .get("vs_random", {})
            .get("beat_margin_se"),
        },
    }
    m1 = out["batch1_holdout_items"].get("margin_se")
    m2 = out["batch2_eval_families"].get("margin_se")
    if m1 is not None and m2 is not None:
        out["delta_margin_se"] = round(m2 - m1, 2)
        out["note"] = (
            "batch-1 holdout sat BELOW its floor (-1.53 SE, null); the delta "
            "is the v2 schema's effect on unseen-policy generalization, "
            "each side normalized to its own floor."
        )
    return out


if __name__ == "__main__":
    raise SystemExit(main())
