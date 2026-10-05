"""Pairwise ELO ladder over policy specs — anchored at random = 0.

Owner charge 2: an ELO-style communication number with the anchor he
proposed — **random play sits at exactly ELO 0**. K=32 iterative pairwise
Elo is the fit (chosen over a Bradley-Terry Newton solve: on a complete
round-robin the iterative fixed point is empirically within noise of the
BT-MLE ordering, it needs no linear algebra per bootstrap replicate, and
K/pass semantics match how the owner already reads ladder numbers). Elo is
shift-invariant, so after fitting we subtract the anchor's rating: the
anchor reads exactly 0.000 BY CONSTRUCTION (unit-pinned), and every other
number is "points above random".

Protocol honoured (KNOWLEDGE/2026-10-05/04): seat-swap inside every pair
(ab_duel's swap alternation), D9 disjoint seed banks per pair (the shared
duel_seeds.json registry), draws score 0.5 for the fit but stay visible in
the duel records. Bootstrap CI: 1000 nonparametric resamples of the raw
per-game outcomes WITHIN each pair (rng seeded — the CI itself is
reproducible), refit, percentile 2.5/97.5.

Run::

    .venv/bin/python -m tools.training.elo random scripted tools/training/bc_s1.pt \\
        --games 400 --workers 4

Output (owner's phone board renders this exact schema):
``reports/monitoring/elo.json``
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.training.ab_duel import (
    SEED_BANK,
    load_bank,
    normalize_spec,
    run_duel,
    save_bank,
)

#: The fit's K per passed game (communication convention, not a rating-system
#: claim); iterations run to fixed point so the result is order-stable.
ELO_K = 32.0
FIT_PASSES = 2000
FIT_TOL = 1e-10
DEFAULT_OUT = REPO / "reports" / "monitoring" / "elo.json"


# ------------------------------------------------------------------ the fit
def fit_elo(
    pair_counts: dict[tuple[int, int], tuple[int, int, int]],
    n: int,
    anchor: int,
    k: float = ELO_K,
) -> list[float]:
    """K=32 iterative Elo to fixed point, then anchored so ``anchor`` is
    exactly 0. ``pair_counts[(i, j)] = (wins_i, wins_j, draws)`` — pair keys
    are i<j, iterated in sorted order every pass (deterministic)."""
    elo = [0.0] * n
    keys = sorted(pair_counts)
    for _ in range(FIT_PASSES):
        delta = 0.0
        for i, j in keys:
            wi, wj, wd = pair_counts[(i, j)]
            expected = 1.0 / (1.0 + 10.0 ** ((elo[j] - elo[i]) / 400.0))
            score = (wi + 0.5 * wd) / (wi + wj + wd)
            step = k * (score - expected)
            elo[i] += step
            elo[j] -= step
            delta = max(delta, abs(step))
        if delta < FIT_TOL:
            break
    return [e - elo[anchor] for e in elo]


def _pair_lists_to_counts(
    pair_results: dict[tuple[int, int], list[str]],
) -> dict[tuple[int, int], tuple[int, int, int]]:
    counts: dict[tuple[int, int], tuple[int, int, int]] = {}
    for key, outcomes in pair_results.items():
        counts[key] = (
            outcomes.count("a"),
            outcomes.count("b"),
            len(outcomes) - outcomes.count("a") - outcomes.count("b"),
        )
    return counts


def bootstrap_ci(
    pair_results: dict[tuple[int, int], list[str]],
    n: int,
    anchor: int,
    reps: int = 1000,
    rng_seed: int = 20261005,
) -> list[tuple[float, float]]:
    """Percentile CI per policy from resampling raw games within each pair
    (draws and crashes ride along as sampled outcomes)."""
    rng = random.Random(rng_seed)
    keys = sorted(pair_results)
    samples: list[list[float]] = []
    for _ in range(reps):
        resampled: dict[tuple[int, int], list[str]] = {}
        for key in keys:
            outcomes = pair_results[key]
            m = len(outcomes)
            resampled[key] = [outcomes[rng.randrange(m)] for _ in range(m)]
        samples.append(fit_elo(_pair_lists_to_counts(resampled), n, anchor))
    ci: list[tuple[float, float]] = []
    for p in range(n):
        col = sorted(s[p] for s in samples)
        lo = col[max(0, int(0.025 * reps) - 1)] if reps >= 40 else col[0]
        hi = col[min(reps - 1, int(0.975 * reps))] if reps >= 40 else col[-1]
        ci.append((lo, hi))
    return ci


# ------------------------------------------------------------ ladder run
def run_ladder(
    specs: list[str],
    games: int,
    workers: int = 10,
    anchor_spec: str = "random",
    device: str = "auto",
    reps: int = 1000,
    pool_mode: str = "all",
    bank_path: Path = SEED_BANK,
) -> dict[str, Any]:
    """Full round-robin (each pair ``games`` seat-swapped, D9-fresh seeds,
    crashes counted inside the pair as draws-half outcomes via the record)
    -> the anchored table + the exact elo.json document."""
    labels = [normalize_spec(s) for s in specs]
    anchor = labels.index(normalize_spec(anchor_spec))
    bank = load_bank(bank_path)
    pair_results: dict[tuple[int, int], list[str]] = {}
    pair_meta: dict[tuple[int, int], dict[str, Any]] = {}
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            result = run_duel(
                specs[i],
                specs[j],
                games,
                workers=workers,
                device=device,
                pool_mode=pool_mode,
                bank=bank,
                persist_bank=False,
                bank_path=bank_path,
            )
            pair_results[(i, j)] = [
                "d"
                if r["outcome"].startswith("draw") or r["outcome"] == "crash"
                else r["outcome"]
                for r in result["records"]
            ]
            pair_meta[(i, j)] = result["summary"]
    save_bank(bank, bank_path)

    counts = _pair_lists_to_counts(pair_results)
    elo = fit_elo(counts, len(labels), anchor)
    ci = bootstrap_ci(pair_results, len(labels), anchor, reps=reps)
    wins = [0] * len(labels)
    score = [0.0] * len(labels)
    games_played = [0] * len(labels)
    for (i, j), (wi, wj, wd) in counts.items():
        wins[i] += wi
        wins[j] += wj
        score[i] += wi + 0.5 * wd
        score[j] += wj + 0.5 * wd
        games_played[i] += wi + wj + wd
        games_played[j] += wi + wj + wd
    ratings = sorted(
        (
            {
                "policy": labels[p],
                "elo": round(elo[p], 1),
                "ci_lo": round(ci[p][0], 1),
                "ci_hi": round(ci[p][1], 1),
                "vs_field_wr": round(score[p] / games_played[p], 4)
                if games_played[p]
                else 0.0,
            }
            for p in range(len(labels))
        ),
        key=lambda r: -r["elo"],
    )
    return {
        "updated": datetime.now(UTC).isoformat(timespec="seconds"),
        "anchor": "random=0",
        "games_per_pair": games,
        "ratings": ratings,
        "games_total": sum(games_played) // 2,
        "details": {
            "fit": f"K={ELO_K} iterative to fixed point, anchored (random=0 by "
            "construction); vs_field_wr = score incl. 0.5*draws; "
            "bootstrap over games within pairs, seed-fixed",
            "pairs": {
                f"{labels[i]} vs {labels[j]}": {
                    "a": meta["a"],
                    "b": meta["b"],
                    "draws": meta["draws"],
                    "crashes": meta["crashes"],
                }
                for (i, j), meta in pair_meta.items()
            },
        },
    }


def emit(doc: dict[str, Any], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8")
    try:
        from tools.training import log_metric  # type: ignore[import-not-found]

        for name in ("log", "record", "emit"):
            fn = getattr(log_metric, name, None)
            if callable(fn):
                fn("elo", doc)
                break
    except Exception:  # noqa: BLE001, S110 - metrics never break the ladder
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Anchored ELO ladder (random=0).")
    parser.add_argument(
        "policies", nargs="+", help="policy specs; must include the anchor (random)"
    )
    parser.add_argument("--games", type=int, default=200, help="games per pair")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--anchor", default="random")
    parser.add_argument("--device", default="auto", choices=("auto", "cpu", "cuda"))
    parser.add_argument("--reps", type=int, default=1000, help="bootstrap replicates")
    parser.add_argument("--pool", default="all", choices=("all", "engine", "castable"))
    parser.add_argument("--seed-file", type=Path, default=SEED_BANK)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    started = time.perf_counter()
    doc = run_ladder(
        args.policies,
        args.games,
        workers=args.workers,
        anchor_spec=args.anchor,
        device=args.device,
        reps=args.reps,
        pool_mode=args.pool,
        bank_path=args.seed_file,
    )
    doc["wall_seconds"] = round(time.perf_counter() - started, 1)
    emit(doc, args.out)
    width = max(len(r["policy"]) for r in doc["ratings"])
    print(
        f"anchor: {doc['anchor']}  games/pair: {doc['games_per_pair']}  "
        f"total: {doc['games_total']}"
    )
    for r in doc["ratings"]:
        print(
            f"  {r['policy']:>{width}}  elo {r['elo']:>8.1f} "
            f"[{r['ci_lo']:>8.1f}, {r['ci_hi']:>8.1f}]  field-wr {r['vs_field_wr']:.3f}"
        )
    print(f"# written {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
