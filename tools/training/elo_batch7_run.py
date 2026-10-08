"""Batch-7 pairwise honest winrate duels (unified 180-item corpus) — capacity closure.

Pairs (seed-matched; A = candidate arm, B = S0 baseline): S3a/S3/S3b/S4 vs S0.
Per training seed s in {1,2,3}: A = bc7_<arm>_s<s>_best.pt,
B = bc7_S0_s<s>_best.pt; --games-per-pair swap-paired games (seat balance
enforced + checked by ab_duel.summarize, E7 law).
Eval corpus is the frozen 'eval_file' binding of the bc7_*_report.json files
(episodes_v2.jsonl, corpus-joined, 180 items) — verified identical across all
reports at start; nothing here regenerates corpus data.

Statistics (law KNOWLEDGE/2026-10-07/26: admissible iff 95% CI excludes 0.5):
  - per-seed rows: Wilson 95% CI on A-decisive winrate (wins/(wins+losses);
    draws/crashes non-decisive, reported raw) and on the swap-paired score.
  - pooled per pair: cluster bootstrap 95% CI over swap-paired score clusters
    (cluster = game seed; the two swap games of a seed share the deal;
    win=1, draw/crash=0.5, loss=0), 10k draws, percentile — batch6 recipe —
    plus Wilson on pooled decisive games.

Run:  .venv/bin/python tools/training/elo_batch7_run.py --games-per-pair 200
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.training.ab_duel import SEED_BANK, run_duel, wilson

PAIRS = [("S3a", "S0"), ("S3", "S0"), ("S3b", "S0"), ("S4", "S0")]
SEEDS = [1, 2, 3]
EVAL_BINDING = "/home/sune/Desktop/MTG_AI/tools/training/episodes_v2.jsonl (binding; corpus-joined)"


def ckpt(arm: str, seed: int) -> str:
    return str(REPO / "tools" / "training" / f"bc7_{arm}_s{seed}_best.pt")


def verify_eval_binding() -> None:
    bindings: set[str] = set()
    for big, small in PAIRS:
        for arm in (big, small):
            for s in SEEDS:
                rpt = REPO / "tools" / "training" / f"bc7_{arm}_s{s}_report.json"
                bindings.add(json.loads(rpt.read_text())["eval_file"])
    if bindings != {EVAL_BINDING}:
        raise SystemExit(f"eval_file bindings disagree: {bindings}")


def save(path: Path, payload: dict) -> None:
    """Exclusive-lock write so a duplicate runner can never silently share the file."""
    with open(path.with_suffix(".lock"), "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=1))
        tmp.replace(path)


def cluster_bootstrap(clusters: list[list[float]], half: int = 10000):
    import numpy as np

    per = max(len(c) for c in clusters)
    mat = np.full((len(clusters), per), np.nan)
    for i, c in enumerate(clusters):
        mat[i, : len(c)] = c
    n = mat.shape[0]
    rng = np.random.default_rng(1409)
    idx = rng.integers(0, n, size=(half, n))
    means = np.nanmean(mat[idx], axis=(1, 2))
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(np.nanmean(mat)), [round(float(lo), 4), round(float(hi), 4)]


def verdict_ci(ci: list[float], a: str, b: str) -> str:
    if ci[0] > 0.5:
        return f"ADMISSIBLE ({a} > {b})"
    if ci[1] < 0.5:
        return f"ADMISSIBLE ({b} > {a})"
    return "INADMISSIBLE"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games-per-pair", type=int, default=200)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--device", type=str, default="cuda")
    ap.add_argument("--out", type=Path, default=REPO / "tools" / "training" / "elo_batch7.json")
    ap.add_argument("--only", type=str, default="", help="pair filter, e.g. S3a_S0")
    args = ap.parse_args()

    verify_eval_binding()
    if args.out.exists() and args.out.read_text().strip():
        first = json.loads(args.out.read_text())
        if first.get("schema") != "batch7-cluster-bootstrap-v1":
            raise SystemExit(f"{args.out} has foreign schema {first.get('schema')!r}; "
                             "refusing to write. Delete it or pass --out elsewhere.")

    # PID-unique seed bank: a crashed/stale process can never target our runs.
    bank_path = Path(f"/tmp/opencode/duel_seeds_batch7.{os.getpid()}.json")
    bank_path.write_text(SEED_BANK.read_text(encoding="utf-8"), encoding="utf-8")

    out: dict[str, Any] = {"schema": "batch7-cluster-bootstrap-v1", "pairs": {}}
    if args.out.exists():
        out = json.loads(args.out.read_text())
    save(args.out, out)

    for big, small in PAIRS:
        name = f"{big}_{small}"
        if args.only and args.only != name:
            continue
        entry = out["pairs"].setdefault(name, {"big": big, "small": small,
                                               "eval_file_binding": EVAL_BINDING,
                                               "per_seed": {}})
        clusters: list[list[float]] = []
        wins = losses = draws = crashes = 0
        t_pair = time.perf_counter()
        complete = True
        for s in SEEDS:
            tag = f"s{s}"
            cached = entry["per_seed"].get(tag)
            if cached and cached.get("games") == args.games_per_pair:
                print(f"[skip] {name} {tag}", flush=True)
                scores = cached.get("_scores")
                if scores is None:
                    complete = False
                    continue
                clusters.append(scores)
                wins += cached["wins_a"]; losses += cached["wins_b"]
                draws += cached["draws"]; crashes += cached["crashes"]
                continue
            t0 = time.perf_counter()
            res = run_duel(ckpt(big, s), ckpt(small, s), games=args.games_per_pair,
                           workers=args.workers, device=args.device, bank_path=bank_path)
            summ = res["summary"]
            w, l = summ["a"]["wins"], summ["b"]["wins"]
            d = sum(summ["draws"].values())
            cr = summ["crashes"]
            dec = w + l
            scores = [1.0 if r["outcome"] == "a" else 0.0 if r["outcome"] == "b" else 0.5
                      for r in res["records"]]
            clusters.append(scores)
            wins += w; losses += l; draws += d; crashes += cr
            lo, hi = wilson(w, dec) if dec else (0.0, 1.0)
            slo, shi = wilson(w + 0.5 * d, summ["games"])
            entry["per_seed"][tag] = {
                "spec_a": Path(ckpt(big, s)).name, "spec_b": Path(ckpt(small, s)).name,
                "games": summ["games"], "wins_a": w, "wins_b": l,
                "draws": d, "crashes": cr,
                "seat_balance_ok": summ["seat_balance_ok"],
                "a_winrate_decisive": round(w / dec, 4) if dec else None,
                "wilson_ci95_decisive": [round(lo, 4), round(hi, 4)],
                "a_score": round((w + 0.5 * d) / summ["games"], 4),
                "wilson_ci95_score": [round(slo, 4), round(shi, 4)],
                "seconds": round(time.perf_counter() - t0, 1),
                "_scores": scores,
            }
            print(f"[done] {name} {tag}: w/l/d/c={w}/{l}/{d}/{cr} "
                  f"dec_wr={entry['per_seed'][tag]['a_winrate_decisive']} "
                  f"wilson=[{lo:.3f},{hi:.3f}] ({entry['per_seed'][tag]['seconds']}s)",
                  flush=True)
            save(args.out, out)

        if len(clusters) == len(SEEDS) and complete:
            point, boot = cluster_bootstrap(clusters)
        else:
            point, boot = None, None
        dec = wins + losses
        wlo, whi = wilson(wins, dec) if dec else (0.0, 1.0)
        entry["raw"] = {"wins_a": wins, "wins_b": losses, "draws": draws, "crashes": crashes}
        entry["games_total"] = dec + draws + crashes
        entry["a_winrate_decisive"] = round(wins / dec, 4) if dec else None
        entry["wilson_ci95_decisive"] = [round(wlo, 4), round(whi, 4)]
        entry["a_score_swap_paired"] = round(point, 4) if point is not None else None
        entry["boot_ci95_score"] = boot
        entry["verdict"] = verdict_ci(boot, big, small) if boot else "PARTIAL"
        entry["verdict_wilson_decisive"] = verdict_ci([round(wlo, 4), round(whi, 4)], big, small)
        entry["pair_seconds"] = round(time.perf_counter() - t_pair, 1)
        save(args.out, out)
        print(f"[pool] {name}: dec_wr={entry['a_winrate_decisive']} "
              f"wilson={entry['wilson_ci95_decisive']} score={point} boot={boot} "
              f"-> {entry['verdict']}", flush=True)

    for entry in out["pairs"].values():  # drop transient bookkeeping
        for row in entry.get("per_seed", {}).values():
            row.pop("_scores", None)
    out["meta"] = {
        "pairs": [f"{a}_vs_{b}" for a, b in PAIRS], "training_seeds": SEEDS,
        "games_per_seed_run": args.games_per_pair,
        "law": "admissible iff 95% CI excludes 0.5 (KNOWLEDGE/2026-10-07/26)",
        "ci_methods": {"per_seed": "Wilson (decisive + score)",
                       "pooled": "cluster bootstrap on swap-paired scores + Wilson decisive"},
    }
    save(args.out, out)
    print("[all done]", flush=True)


if __name__ == "__main__":
    main()
