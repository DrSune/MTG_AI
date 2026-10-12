"""Score an existing checkpoint against the universal gate WITHOUT retraining.

Use case: mid-train best-loss checkpoints (note 'pre-final') or crash-recovered
runs that never reached train_bc_v3's final gate block. Same machinery as the
trainer's final gate: eval_side dataset from the checkpoint's OWN vocab,
eval_rows + gate_stats (card-cluster bootstrap >3SE law, KNOWLEDGE 2026-10-07/26).

Usage: .venv/bin/python -m tools.training.eval_ckpt tools/training/bsd_S3a_s1_best.pt
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import torch

from tools.training import bc_data_v2
from tools.training.bc_model import PointerBC
from tools.training.train_bc import gate_stats
from tools.training.train_bc_v3 import SPLIT, BCS, eval_rows, eval_side


def score_ckpt(ckpt: Path, device_str: str, seed: int = 1) -> dict[str, Any]:
    blob = torch.load(ckpt, map_location="cpu", weights_only=False)
    model = PointerBC(**blob["config"])
    model.load_state_dict(blob["state"])
    vocab: dict[str, int] = blob["vocab"]
    device = torch.device(device_str)
    split = json.loads(SPLIT.read_text(encoding="utf-8"))
    eval_families = set(split["eval_families"])
    bcs_of = {
        name: m["bcs"] for name, m in json.loads(BCS.read_text())["cards"].items()
    }
    eval_ds, joined = eval_side(vocab, smoke=False)
    rows = eval_rows(model, eval_ds, device, eval_families, bcs_of)
    certified = [r for r in rows if r["cert"]]
    gate = gate_stats(rows, seed)
    return {
        "ckpt": str(ckpt),
        "seed_ckpt": blob.get("seed"),
        "note": str((blob.get("train_info") or {}).get("note", "")),
        "eval_joined": joined,
        "acc": gate["acc"],
        "verdict": gate.get("verdict"),
        "beat_se": gate.get("beat_margin_bootstrap_se", gate.get("beat_margin_se")),
        "n_cert": len(certified),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ckpt", type=Path, nargs="+")
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args(argv)
    for path in args.ckpt:
        print(json.dumps(score_ckpt(path, args.device)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
