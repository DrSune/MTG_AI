"""Batch-7 pairwise honest winrates on the unified 180-item frozen corpus.

Pairs (seed-matched; A = candidate arm, B = S0 baseline): S3a vs S0, S3 vs S0,
S3b vs S0, S4 vs S0. Per seed s in {1,2,3}: A = bc7_<arm>_s<s>_best.pt,
B = bc7_S0_s<s>_best.pt. Eval data is the frozen per-report 'eval_file' field
of bc7_*_report.json (episodes_v2.jsonl corpus-joined, 180 items) -- the duel
harness scores policies in-engine; nothing here regenerates corpus data.

CI: Wilson score interval, 95%, on the A-side score (win=1, draw/crash=0.5)
and on decisive-only winrate (wins/(wins+losses)). Admissible iff the score
Wilson CI excludes 0.5 (KNOWLEDGE/2026-10-07/26 law).

Run:  .venv/bin/python tools/training/elo_batch7_run.py --games-per-pair 200
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.training.ab_duel import SEED_BANK, run_duel

def _save(path: Path, payload: dict) -> None:
    """Exclusive-lock write so a duplicate runner can never silently share the file."""
    import fcntl
    with open(path.with_suffix(path.suffix + ".lock"), "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=1))
        tmp.replace(path)


PAIRS = [("S3a", "S0"), ("S3", "S0"), ("S3b", "S0"), ("S4", "S0")]
SEEDS = [1, 2, 3]


def ckpt(arm: str, seed: int) -> str:
    return str(REPO / "tools" / "training" / f"bc7_{arm}_s{seed}_best.pt")


def wilson(num: float, n: float, z: float = 1.959963984540054) -> list[float]:
    """Wilson interval on a count/total pair (also for score means via 2*num/2n)."""
    if n <= 0:
        return [0.0, 1.0]
    p = num / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def verdict(ci: list[float]) -> str:
    return "ABOVE" if ci[0] > 0.5 else ("BELOW" if ci[1] < 0.5 else "INADMISSIBLE")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games-per-pair", type=int, default=200)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--device", type=str, default="cuda")
    ap.add_argument("--out", type=Path, default=REPO / "tools" / "training" / "elo_batch7.json")
    ap.add_argument("--only", type=str, default="", help="filter e.g. S3a_S0_s1")
    args = ap.parse_args()

    bank_path = Path("/tmp/opencode/duel_seeds_batch7_v3.json")
    if not bank_path.exists():
        bank_path.write_text(SEED_BANK.read_text(encoding="utf-8"), encoding="utf-8")

    plan = []
    for big, small in PAIRS:
        for s in SEEDS:
            name = f"{big}_{small}_s{s}"
            if args.only and args.only != name:
                continue
            plan.append((name, big, small, s))

    out = json.loads(args.out.read_text()) if args.out.exists() else {"pairs": {}}
    for name, big, small, s in plan:
        if name in out["pairs"] and out["pairs"][name].get("games") == args.games_per_pair:
            print(f"[skip] {name} already done", flush=True)
            continue
        t0 = time.perf_counter()
        res = run_duel(ckpt(big, s), ckpt(small, s), games=args.games_per_pair,
                       workers=args.workers, device=args.device, bank_path=bank_path)
        summ = res["summary"]
        n = float(summ["games"])
        wa, wb = summ["a"]["wins"], summ["b"]["wins"]
        draws = sum(summ["draws"].values())
        score_sum = wa + 0.5 * draws
        ci = wilson(score_sum, n)                       # score Wilson (law metric)
        ci_dec = wilson(wa, wa + wb)                    # decisive-only
        rec = {
            "spec_a": Path(ckpt(big, s)).name, "spec_b": Path(ckpt(small, s)).name,
            "games": summ["games"], "seed": s,
            "wins_a": wa, "wins_b": wb, "draws": draws, "crashes": summ["crashes"],
            "seat_balance_ok": summ["seat_balance_ok"],
            "a_score": round(score_sum / n, 4),
            "wilson_ci95_score": ci,
            "a_winrate_decisive": round(wa / (wa + wb), 4) if wa + wb else None,
            "wilson_ci95_decisive": ci_dec,
            "verdict": f"A-side {verdict(ci)}",
            "seconds": round(time.perf_counter() - t0, 1),
        }
        out["pairs"][name] = rec
        _save(args.out, out)
        print(f"[done] {name}: w/l/d/c={wa}/{wb}/{draws}/{summ['crashes']} "
              f"score={rec['a_score']} wilson={ci} -> {rec['verdict']} ({rec['seconds']}s)",
              flush=True)

    # pooled per pair: aggregate raw counts over the 3 seed-matched runs
    for big, small in PAIRS:
        name = f"{big}_{small}_pooled"
        if name in out["pairs"]:
            continue
        rows = [out["pairs"].get(f"{big}_{small}_s{s}") for s in SEEDS]
        if any(r is None for r in rows):
            continue
        n = float(sum(r["games"] for r in rows))
        wa = sum(r["wins_a"] for r in rows)
        wb = sum(r["wins_b"] for r in rows)
        dr = sum(r["draws"] for r in rows)
        ci = wilson(wa + 0.5 * dr, n)
        ci_dec = wilson(wa, wa + wb)
        out["pairs"][name] = {
            "spec_a": f"pooled {big}", "spec_b": "pooled S0 (all 3 seeds)",
            "games": int(n),
            "wins_a": wa, "wins_b": wb, "draws": dr,
            "crashes": sum(r["crashes"] for r in rows),
            "a_score": round((wa + 0.5 * dr) / n, 4),
            "wilson_ci95_score": ci,
            "a_winrate_decisive": round(wa / (wa + wb), 4) if wa + wb else None,
            "wilson_ci95_decisive": ci_dec,
            "per_seed_scores": {f"s{s}": out["pairs"][f"{big}_{small}_s{s}"]["a_score"]
                                for s in SEEDS},
            "verdict": f"A-side {verdict(ci)}",
        }
        _save(args.out, out)
        print(f"[pool] {name}: score={out['pairs'][name]['a_score']} wilson={ci} "
              f"-> {out['pairs'][name]['verdict']}", flush=True)


if __name__ == "__main__":
    main()
