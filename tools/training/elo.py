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

/135 T-G5 fairness audit (binding; KNOWLEDGE/2026-10-20/135):
- item 1: the ladder is set-scoped (--set plumbs into ab_duel's supply;
  the old code was M21-locked and could not host a ZNR matrix).
- item 2: a pair whose bootstrap winrate CI straddles 0.5 is INADMISSIBLE
  and is EXCLUDED from the fit (the /26 fabricated-ratings hole: fitting
  under-powered pairs mints numbers that look like skill). A policy is
  rated only if it lies in the anchor's admissible-pair connected
  component; every other policy is reported UNRATED — never a number.
- item 3: --pool defaults to "engine" (aligned with the rig; "all" mixes
  in uncompiled cards and shifts every supply); the table stamps the
  engine BUILD (git head + MTG_bot dirty count) + set + pool, not just
  the date.
- item 4: every ladder run re-plays the frozen era-parity SENTINEL cell
  (bsh_S3a_s3_best vs random, M21, pool=engine, pinned 0.575 from /123);
  a measurement outside the 95% binomial band flags the run era-invalid
  (harness/engine drift) — the numbers print, but no claim rides them.

Run::

    .venv/bin/python -m tools.training.elo random scripted tools/training/bc_s1.pt \\
        --games 400 --workers 4 --set M21

Output (owner's phone board renders this exact schema):
``reports/monitoring/elo.json``
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from MTG_bot.core.executor.games import SET_CODE
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

# -------------------------------------------------- /135 T-G5 item 4: sentinel
#: The era-parity control cell, pinned from /123 (2026-10-19 shadow 2x2 grid,
#: M21 engine-pool control: bsh_S3a_s3_best vs random = 23/40 = 0.575 score,
#: 0 crashes, seed-base 777001). The frozen M21-era champion vs random in
#: its OWN era must keep reading ~0.575 in every matrix run; if it does not,
#: something in the harness/engine drifted and the run's era comparisons are
#: confounded — the table prints, flagged era_invalid, but no claim rides it.
SENTINEL: dict[str, Any] = {
    "policy": "tools/training/bsh_S3a_s3_best.pt",
    "opponent": "random",
    "set": "M21",
    "pool": "engine",
    "games": 40,
    "ref_score": 0.575,
    # 95% binomial band: 0.575 +/- 1.96*sqrt(0.575*0.425/40) = [0.422, 0.728]
    "band": [0.422, 0.728],
    "provenance": "KNOWLEDGE/2026-10-19/123 (shadow 2x2 grid, M21 control cell)",
}


def sentinel_status(measured: float) -> bool:
    """True iff the measured sentinel score is inside the pinned band."""
    return SENTINEL["band"][0] <= measured <= SENTINEL["band"][1]


def _engine_stamp(set_code: str, pool_mode: str) -> dict[str, Any]:
    """/135 item 3: the table stamps the ENGINE BUILD, not just the date —
    git HEAD + how many MTG_bot files are dirty (the export/overlay path can
    add to HEAD, so dirty is part of the identity, not noise)."""
    head = "unknown"
    dirty = None
    try:
        head = (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=REPO,
                capture_output=True,
                text=True,
                timeout=10,
            ).stdout.strip()
            or "unknown"
        )
        out = subprocess.run(
            ["git", "status", "--porcelain", "--", "MTG_bot"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
        dirty = len([line for line in out.splitlines() if line.strip()])
    except Exception:  # noqa: BLE001, S110 - the stamp never breaks the ladder
        pass
    return {
        "git_head": head,
        "mtgbot_dirty_files": dirty,
        "set": set_code,
        "pool": pool_mode,
    }


# ------------------------------------------------ /135 T-G5 item 2: the fit
def ladder_ratings(
    pair_results: dict[tuple[int, int], list[str]],
    labels: list[str],
    anchor: int,
    reps: int = 1000,
) -> dict[str, Any]:
    """Per-pair admissibility drives the fit (the /26 fabricated-ratings
    hole, closed): a pair whose bootstrap winrate CI straddles 0.5 is
    under-powered and is EXCLUDED from both the fit and the bootstrap CI.
    A policy is rated iff it lies in the anchor's connected component in
    the admissible-pair graph; every other policy is UNRATED — no number
    is printed for it. (The anchor itself is rated 0 by construction even
    with zero admissible pairs: it is the reference, not a claim.)"""
    adm = pair_winrate_admissibility(pair_results, reps=reps)
    admissible_pairs = {k for k in pair_results if adm[k]["admissible"]}

    # connected components over the admissible-pair graph
    comp: dict[int, int] = {}
    for cid, start in enumerate(range(len(labels))):
        if start in comp:
            continue
        stack = [start]
        while stack:
            x = stack.pop()
            if x in comp:
                continue
            comp[x] = cid
            for i, j in admissible_pairs:
                if i == x and j not in comp:
                    stack.append(j)
                elif j == x and i not in comp:
                    stack.append(i)
    anchor_c = comp[anchor]
    fitted_pairs = {
        k: pair_results[k] for k in admissible_pairs if comp[k[0]] == anchor_c
    }
    unrated = [p for p in range(len(labels)) if comp[p] != anchor_c]
    if fitted_pairs:
        elo = fit_elo(_pair_lists_to_counts(fitted_pairs), len(labels), anchor)
        ci = bootstrap_ci(fitted_pairs, len(labels), anchor, reps=reps)
    else:
        elo = [0.0] * len(labels)
        ci = [(0.0, 0.0)] * len(labels)
    return {
        "adm": adm,
        "fitted_pairs": fitted_pairs,
        "excluded_pairs": sorted(set(pair_results) - set(fitted_pairs)),
        "elo": elo,
        "ci": ci,
        "unrated": unrated,
    }


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


def pair_winrate_admissibility(
    pair_results: dict[tuple[int, int], list[str]],
    reps: int = 1000,
    rng_seed: int = 20261005,
) -> dict[tuple[int, int], dict[str, Any]]:
    """Bootstrap winrate CI per pair; a pair's rating delta is
    INADMISSIBLE unless its CI excludes 0.5 (KNOWLEDGE 2026-10-07/26:
    under-powered games fabricate ratings — elo_s3_sanity CIs straddled
    0.5 yet the ladder still printed positive Elo).

    Winrate = (wins_a + 0.5*draws)/m from resampled raw games (crashes
    ride along as draws, as in the fit); percentile 2.5/97.5 CI."""
    rng = random.Random(rng_seed)
    out: dict[tuple[int, int], dict[str, Any]] = {}
    for key in sorted(pair_results):
        outcomes = pair_results[key]
        m = len(outcomes)

        def score(seq: list[str]) -> float:
            return (seq.count("a") + 0.5 * seq.count("d")) / m

        wrs = sorted(
            score([outcomes[rng.randrange(m)] for _ in range(m)]) for _ in range(reps)
        )
        lo = wrs[max(0, int(0.025 * reps) - 1)]
        hi = wrs[min(reps - 1, int(0.975 * reps))]
        out[key] = {
            "winrate_a": round(score(outcomes), 4),
            "wr_ci": [round(lo, 4), round(hi, 4)],
            "admissible": bool(hi < 0.5 or lo > 0.5),
        }
    return out


# ------------------------------------------------------------ ladder run
def run_ladder(
    specs: list[str],
    games: int,
    workers: int = 10,
    anchor_spec: str = "random",
    device: str = "auto",
    reps: int = 1000,
    pool_mode: str = "engine",
    bank_path: Path = SEED_BANK,
    seeds: list[int] | None = None,
    set_code: str = SET_CODE,
    sentinel: bool = True,
) -> dict[str, Any]:
    """Full round-robin (each pair ``games`` seat-swapped, D9-fresh seeds,
    crashes counted inside the pair as draws-half outcomes via the record)
    -> the anchored table + the exact elo.json document.

    /135 T-G5: ``pool_mode`` defaults to "engine" (item 3, rig-aligned);
    ``set_code`` scopes the dealt supply (item 1); the fit uses only
    admissible pairs (item 2, via ladder_ratings); the frozen era-parity
    sentinel cell is re-played and the table is stamped with the engine
    build (items 3+4)."""
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
                set_code=set_code,
                bank=bank,
                persist_bank=False,
                bank_path=bank_path,
                seeds=seeds,
            )
            pair_results[(i, j)] = [
                "d"
                if r["outcome"].startswith("draw") or r["outcome"] == "crash"
                else r["outcome"]
                for r in result["records"]
            ]
            pair_meta[(i, j)] = result["summary"]
    save_bank(bank, bank_path)

    info = ladder_ratings(pair_results, labels, anchor, reps=reps)
    adm = info["adm"]
    elo, ci, unrated = info["elo"], info["ci"], info["unrated"]
    counts = _pair_lists_to_counts(pair_results)
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
    rated = [p for p in range(len(labels)) if p not in unrated]
    ratings = sorted(
        (
            {
                "policy": labels[p],
                "elo": round(elo[p], 1),
                "ci_lo": round(ci[p][0], 1),
                "ci_hi": round(ci[p][1], 1),
                # vs_field_wr is DESCRIPTIVE (all games played, any pool
                # state); the claim-carrying fields are elo + admissible.
                "vs_field_wr": round(score[p] / games_played[p], 4)
                if games_played[p]
                else 0.0,
                # /135 item 2: admissible = rated = in the anchor's
                # admissible-pair connected component (the per-pair
                # composition; replaces the old vs-anchor-only shortcut).
                "admissible": True,
            }
            for p in rated
        ),
        key=lambda r: -r["elo"],
    )
    doc = {
        "updated": datetime.now(UTC).isoformat(timespec="seconds"),
        "anchor": f"random=0 (set={set_code}, pool={pool_mode})",
        "engine": _engine_stamp(set_code, pool_mode),
        "games_per_pair": games,
        "ratings": ratings,
        # /135 item 2: policies with no admissible path to the anchor get NO
        # number — the fabricated-rating hole.
        "unrated": [
            {
                "policy": labels[p],
                "reason": "no admissible path to the anchor (every pair's "
                "bootstrap winrate CI straddles 0.5)",
            }
            for p in unrated
        ],
        # Headline claims: rated, non-anchor policies. Their rating is built
        # from admissible pairs only (CI of each fitted pair excludes 0.5).
        "headline_claims": [
            {"policy": r["policy"], "elo": r["elo"]}
            for r in ratings
            if r["policy"] != labels[anchor]
        ],
        "games_total": sum(games_played) // 2,
        "fit_excluded_pairs": [
            {"pair": f"{labels[i]} vs {labels[j]}", **adm[(i, j)]}
            for (i, j) in info["excluded_pairs"]
        ],
        "details": {
            "fit": f"K={ELO_K} iterative to fixed point, anchored (random=0 by "
            "construction); ADMISSIBLE PAIRS ONLY (a pair's bootstrap winrate "
            "CI must exclude 0.5; /26 + /135 item 2); vs_field_wr is "
            "descriptive over all games; bootstrap over games within the "
            "fitted pairs, seed-fixed; a policy is rated only if it lies in "
            "the anchor's admissible-pair component, else it is UNRATED",
            "pairs": {
                f"{labels[i]} vs {labels[j]}": {
                    "a": meta["a"],
                    "b": meta["b"],
                    "draws": meta["draws"],
                    "crashes": meta["crashes"],
                    "boot": adm[(i, j)],
                    "in_fit": (i, j) in info["fitted_pairs"],
                }
                for (i, j), meta in pair_meta.items()
            },
        },
    }

    # /135 item 4: the frozen era-parity sentinel cell (fresh D9 seeds, but
    # the cell itself is pinned — same policy/opponent/set/pool/games as
    # the /123 reference).
    if sentinel:
        sres = run_duel(
            SENTINEL["policy"],
            SENTINEL["opponent"],
            SENTINEL["games"],
            workers=workers,
            device=device,
            pool_mode=SENTINEL["pool"],
            set_code=SENTINEL["set"],
            bank=bank,
            persist_bank=False,
            bank_path=bank_path,
        )
        save_bank(bank, bank_path)
        s = sres["summary"]
        doc["sentinel"] = {
            "cell": f"{SENTINEL['policy']} vs {SENTINEL['opponent']} "
            f"(set={SENTINEL['set']}, pool={SENTINEL['pool']}, n={SENTINEL['games']})",
            "measured_score": s["a"]["score"],
            "ref_score": SENTINEL["ref_score"],
            "band": SENTINEL["band"],
            "crashes": s["crashes"],
            "seeds": s["seeds"],
            "ok": sentinel_status(s["a"]["score"]),
            "provenance": SENTINEL["provenance"],
        }
        doc["era_invalid"] = not doc["sentinel"]["ok"]
    return doc


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
    parser.add_argument(
        "--pool",
        default="engine",
        choices=("all", "engine", "castable"),
        help="dealt supply (/135 item 3: default aligned with the rig)",
    )
    parser.add_argument(
        "--set",
        default=SET_CODE,
        help="set code for the supply (/135 item 1; default M21)",
    )
    parser.add_argument(
        "--sentinel",
        choices=("on", "off"),
        default="on",
        help="re-play the frozen era-parity control cell (/135 item 4)",
    )
    parser.add_argument("--seed-file", type=Path, default=SEED_BANK)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--seed-start",
        type=int,
        default=None,
        help="explicit fresh seed block [start, start+games) per pair "
        "(batch-3 D9 law: disjoint from every previously used seed)",
    )
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
        set_code=args.set,
        sentinel=args.sentinel == "on",
        bank_path=args.seed_file,
        seeds=(
            list(range(args.seed_start, args.seed_start + args.games))
            if args.seed_start is not None
            else None
        ),
    )
    doc["wall_seconds"] = round(time.perf_counter() - started, 1)
    emit(doc, args.out)
    eng = doc["engine"]
    print(
        f"anchor: {doc['anchor']}  games/pair: {doc['games_per_pair']}  "
        f"total: {doc['games_total']}  engine: {eng['git_head']} "
        f"(dirty={eng['mtgbot_dirty_files']})"
    )
    if "sentinel" in doc:
        s = doc["sentinel"]
        flag = "OK" if s["ok"] else "OUT OF BAND — ERA-INVALID"
        print(
            f"sentinel: {s['cell']} measured {s['measured_score']:.3f} "
            f"(ref {s['ref_score']:.3f}, band {s['band']}) {flag}  [{s['provenance']}]"
        )
    width = max((len(r["policy"]) for r in doc["ratings"]), default=0)
    for r in doc["ratings"]:
        print(
            f"  {r['policy']:>{width}}  elo {r['elo']:>8.1f} "
            f"[{r['ci_lo']:>8.1f}, {r['ci_hi']:>8.1f}]  field-wr {r['vs_field_wr']:.3f}"
        )
    for u in doc["unrated"]:
        print(f"  {u['policy']:>{width}}  UNRATED  ({u['reason']})")
    excluded = [e["pair"] for e in doc.get("fit_excluded_pairs", [])]
    if excluded:
        print(f"# fit-excluded pairs (wr CI straddles 0.5): {', '.join(excluded)}")
    claims = ", ".join(f"{c['policy']} {c['elo']:+.1f}" for c in doc["headline_claims"])
    print(f"# headline claims (rated only): {claims or 'NONE'}", file=sys.stderr)
    if doc.get("era_invalid"):
        print(
            "# WARNING: sentinel cell OUT OF BAND — this table is ERA-INVALID; "
            "no claim may ride these numbers (/135 item 4).",
            file=sys.stderr,
        )
    print(f"# written {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
