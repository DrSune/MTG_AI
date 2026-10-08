"""Batch-6 pairwise honest winrate + cluster bootstrap CIs (owner charge).

Pairs: S4 vs S0, S3 vs S0, S4 vs S3. Per seed s in {1,2,3}: A = bc6_<big>_s<s>,
B = bc6_<small>_s<s> (A-side winrate reported; D9 fresh seed slices via an
isolated bank copy so the main duel registry is untouched).

Bootstrap: cluster resample over paired game seeds (seed = cluster: the two
swap games of a seed share the deal), 10k draws, percentile 95% CI.
Admissibility law (KNOWLEDGE/2026-10-07/26): claim admissible iff CI excludes 0.5.

Run:  .venv/bin/python tools/training/elo_batch6_run.py --games-per-pair 100
"""
from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.training.ab_duel import SEED_BANK, load_bank, run_duel

PAIRS = [("S4", "S0"), ("S3", "S0"), ("S4", "S3")]
SEEDS = [1, 2, 3]
COUNTERPART = {"S4": "S0", "S3": "S0", "S0": "S3"}  # pool index mapping


def ckpt(arm: str, seed: int) -> str:
    return str(REPO / "tools" / "training" / f"bc6_{arm}_s{seed}_best.pt")


def bootstrap_ci(seeds: list[int], a_win: dict, half: int = 10000, z: float = 0.025):
    """Percentile cluster bootstrap over paired seed clusters.
    a_win[s] = list of per-game outcomes (1.0 A win, 0.5 draw, 0.0 loss) for seed s."""
    import random

    import numpy as np

    clusters = np.array([a_win[s] for s in sorted(seeds)], dtype=float)  # (C, per)
    c = clusters.shape[0]
    rng = np.random.default_rng(1409)
    idx = rng.integers(0, c, size=(half, c))
    means = clusters[idx].mean(axis=(1, 2))
    lo, hi = np.percentile(means, [100 * z, 100 * (1 - z)])
    point = float(clusters.mean())
    return point, [round(float(lo), 4), round(float(hi), 4)], means.std()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games-per-pair", type=int, default=100)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--device", type=str, default="cuda")
    ap.add_argument("--out", type=Path, default=REPO / "tools" / "training" / "elo_batch6.json")
    ap.add_argument("--only", type=str, default="", help="filter e.g. S4_S0_s1")
    args = ap.parse_args()

    bank_path = Path("/tmp/opencode/duel_seeds_batch6.json")
    if not bank_path.exists():
        bank_path.write_text(SEED_BANK.read_text(encoding="utf-8"), encoding="utf-8")

    plan = []
    for big, small in PAIRS:
        for s in SEEDS:
            name = f"{big}_{small}_s{s}"
            if args.only and args.only != name:
                continue
            plan.append((name, ckpt(big, s), ckpt(small, s)))
    # pooled (cross-seed) duels: big s1 vs small s2, s3; etc. -> one pool per pair
    for big, small in PAIRS:
        name = f"{big}_{small}_pooled"
        if args.only and args.only != name:
            continue
        # representative cross-seed matchups: seed-cycling opponents
        plan.append((name, ckpt(big, 1), ckpt(small, 2)))

    out = json.loads(args.out.read_text()) if args.out.exists() else {"pairs": {}}
    for name, spec_a, spec_b in plan:
        if name in out["pairs"] and out["pairs"][name].get("games") == args.games_per_pair:
            print(f"[skip] {name} already done", flush=True)
            continue
        t0 = time.perf_counter()
        res = run_duel(spec_a, spec_b, games=args.games_per_pair, workers=args.workers,
                       device=args.device, bank_path=bank_path)
        recs = res["records"]
        # per-seed clusters: outcome of A per game
        a_win: dict[int, list[float]] = {}
        for r in recs:
            if r["outcome"] == "crash":
                val = 0.5  # honest: crash counted as draw-ish half in score; also tracked raw
            elif r["outcome"] == "a":
                val = 1.0
            elif r["outcome"] == "b":
                val = 0.0
            else:
                val = 0.5
            a_win.setdefault(r["seed"], []).append(val)
        point, ci, sd = bootstrap_ci(list(a_win), a_win)
        summ = res["summary"]
        out["pairs"][name] = {
            "spec_a": Path(spec_a).name, "spec_b": Path(spec_b).name,
            "games": args.games_per_pair,
            "raw": {"wins_a": summ["a"]["wins"], "wins_b": summ["b"]["wins"],
                    "draws": summ["draws"], "crashes": summ["crashes"]},
            "a_winrate_score": round(point, 4),
            "boot_ci95": ci,
            "boot_sd": round(float(sd), 4),
            "wilson_ci": summ["a"]["ci"],
            "seeds_used": [summ["seeds"][0], summ["seeds"][1]],
            "seconds": round(time.perf_counter() - t0, 1),
        }
        admiss = "ABOVE" if ci[0] > 0.5 else ("BELOW" if ci[1] < 0.5 else "INADMISSIBLE")
        out["pairs"][name]["verdict"] = f"A-side {admiss}"
        args.out.write_text(json.dumps(out, indent=1))
        print(f"[done] {name}: score={point:.3f} ci={ci} -> {admiss} "
              f"({out['pairs'][name]['seconds']}s)", flush=True)


if __name__ == "__main__":
    main()
