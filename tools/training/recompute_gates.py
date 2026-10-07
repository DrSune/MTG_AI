"""--recompute-gates: rewrite report gate blocks with the honest
card-cluster bootstrap. NO RETRAINING — pure arithmetic on the eval_rows
already persisted in each bc*_report.json.

Per KNOWLEDGE/2026-10-07/26: the iid binomial gate margin is inflated
~30% because items of one card are correlated; the gate must be a
card-cluster bootstrap (resample cards, items grouped, outcomes fixed).

What it does to each report, in place:
  * ``gate_iid``        <- verbatim copy of the old ``gates`` block.
  * ``gates``           <- recomputed: the iid numbers (rebuilt from
    persisted rows and CHECKED against gate_iid's rows/acc) plus the
    cluster-bootstrap numbers (margin_bootstrap_se, p_beats_floor,
    n_clusters, ...) merged into each vs_random / vs_null block. The
    floor is the one recorded in gate_iid, held fixed across resamples
    (per-item floors are not persisted — conservative).
  * ``gate_verdict``    <- PASS requires BOTH iid and bootstrap margin
    > 3 on the eval_families slice; old verdict kept as gate_verdict_iid.

Only the three reconstructable slices are rewritten; ``l1_certified``
(l1_ready is not persisted in eval_rows) rides along unchanged with a
note. The bootstrap seed is the run's training seed, read from the
arm's *_best.pt checkpoint metadata (fallback --seed, printed + recorded
in the gate_verdict, if the checkpoint carries none).

Run::

    .venv/bin/python -m tools.training.recompute_gates            # the 8 shipped reports
    .venv/bin/python -m tools.training.recompute_gates path1.json path2.json --B 4000
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.training.train_bc import cluster_bootstrap_stats

HERE = Path(__file__).resolve().parent
DEFAULT_REPORTS = [f"bc5_{s}" for s in ("S0", "S1", "S2", "S3", "S4")] + [
    "bc3_A",
    "bc3_B",
    "dagger",
]


def ckpt_seed(report_path: Path) -> int | None:
    """Training seed from the arm's *_best.pt metadata (plain dict load)."""
    ckpt = report_path.with_name(report_path.stem.replace("_report", "_best") + ".pt")
    try:
        import torch

        meta = torch.load(ckpt, map_location="cpu", weights_only=True)
        seed = meta.get("seed")
        return int(seed) if isinstance(seed, int) else None
    except Exception:  # noqa: BLE001 - fall back to --seed
        return None


def recompute_report(path: Path, B: int, seed_fallback: int = 1) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    iid = report["gates"]
    rows = report["eval_rows"]
    seed = ckpt_seed(path)
    if seed is None:
        print(
            f"note: {path.name}: no seed in *_best.pt, using fallback seed "
            f"{seed_fallback}"
        )
        seed = seed_fallback

    slices = {
        "gold_lines_all": rows,
        "train_families": [r for r in rows if not r["eval_family"]],
        "eval_families": [r for r in rows if r["eval_family"]],
    }
    out: dict[str, Any] = {}
    for name, slice_rows in slices.items():
        old = iid[name]
        old_vr = old["vs_random"]
        # All persisted eval_rows of these reports are cert-joined; the
        # counts/acc below MUST match the iid block or we bail loudly.
        k = sum(r["correct"] for r in slice_rows)
        n = len(slice_rows)
        if n != old["rows"] or k != old["correct"]:
            raise SystemExit(
                f"{path.name}/{name}: rows {n}/{k} != gate_iid "
                f"{old['rows']}/{old['correct']} — slice not reconstructable"
            )
        by_card: dict[str, list[int]] = {}
        for r in slice_rows:
            by_card.setdefault(r["card"], []).append(1 if r["correct"] else 0)
        block = dict(old)
        block["vs_random"] = old_vr | cluster_bootstrap_stats(
            by_card, old_vr["floor_p0"], B=B, seed=seed
        )
        block["vs_null"] = old["vs_null"] | cluster_bootstrap_stats(
            by_card, old["vs_null"]["floor_p0"], B=B, seed=seed
        )
        out[name] = block
    out["l1_certified"] = {
        **iid["l1_certified"],
        "cluster_bootstrap": "not reconstructable (l1_ready not persisted in eval_rows)",
    }

    g = out["eval_families"]["vs_random"]
    iid_margin = g["beat_margin_se"]
    boot_margin = g["margin_bootstrap_se"]
    report["gate_iid"] = report.get("gate_iid", iid)  # keep the ORIGINAL iid block
    report["gate_verdict_iid"] = report.get("gate_verdict_iid", report["gate_verdict"])
    report["gates"] = out
    report["eval_margin_bootstrap_se"] = boot_margin
    report["gate_verdict"] = {
        "gate": "eval-family gold lines vs random floor, >3 SE one-sided "
        "on BOTH iid binomial AND card-cluster bootstrap (KNOWLEDGE 2026-10-07/26)",
        "beats_random_floor_by_3SE": iid_margin > 3.0,
        "beats_random_floor_by_3SE_bootstrap": boot_margin > 3.0,
        "verdict": "PASS" if iid_margin > 3.0 and boot_margin > 3.0 else "NULL",
        "recomputed_by": "tools/training/recompute_gates.py",
        "bootstrap_B": B,
        "bootstrap_seed": seed,
    }
    path.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("reports", nargs="*", type=Path, help="report json files")
    ap.add_argument("--B", type=int, default=4000, help="bootstrap replicates")
    ap.add_argument(
        "--seed",
        type=int,
        default=1,
        help="fallback seed when the arm checkpoint has none (recorded in output)",
    )
    args = ap.parse_args(argv)
    names = args.reports or [HERE / f"{n}_report.json" for n in DEFAULT_REPORTS]
    print(
        f"{'report':<14} {'acc':>6} {'iid_m':>6} {'clus_m':>7} "
        f"{'p>floor':>8} {'cards':>5}  verdict"
    )
    for path in names:
        rep = recompute_report(
            path if path.parent != Path() else HERE / path, args.B, args.seed
        )
        g = rep["gates"]["eval_families"]["vs_random"]
        print(
            f"{path.name:<14} {g['acc']:>6} {g['beat_margin_se']:>6} "
            f"{g['margin_bootstrap_se']:>7} {g['p_beats_floor']:>8} "
            f"{g['n_clusters']:>5}  {rep['gate_verdict']['verdict']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
