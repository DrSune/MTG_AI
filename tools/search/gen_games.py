"""Batch runner for the AlphaZero-style generator (KNOWLEDGE/2026-10-10/67).

    .venv/bin/python tools/search/gen_games.py --games 32 --workers 20

Smoke mode (default --games 0 --smoke) runs 2 games serially and asserts
they complete clean, else exits non-zero WITHOUT writing anything. Full
mode spreads the games over a worker pool (fresh BcAsk nets per game,
torch pinned to 1 thread per worker), enforces a wall-clock budget (a game
in flight is allowed to finish; the pool is cut at deadline + grace), and
writes ONLY tools/training/episodes_search.jsonl (fresh) plus per-run stats
to tools/search/gen_stats_v1.json.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT_EPISODES = REPO / "tools" / "training" / "episodes_search.jsonl"
OUT_STATS = Path(__file__).resolve().parent / "gen_stats_v1.json"
BUDGET_MIN_DEFAULT = 90.0
GRACE_MIN = 3.0  # an in-flight game may land after the deadline


def _worker(seed: int, k: int, n: int, cap: int, cheap: bool) -> dict:
    """Run one game in a worker process; returns JSON-safe per-game stats.

    Episodes are streamed to disk by the parent, so only aggregate numbers
    and the episode COUNT cross the process boundary."""
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    import torch

    torch.set_num_threads(1)
    from tools.search import mcts

    t0 = time.time()
    r = mcts.gen_game(seed, k=k, n_rollouts=n, turn_cap=cap, cheap_rollout=cheap)
    s = r["stats"]
    return {
        "seed": seed,
        "result": r["result"],
        "reason": r["reason"],
        "crash": r["crash"],
        "turns": r["turns"],
        "seconds": round(time.time() - t0, 1),
        "asks_searched": s.asks_searched,
        "rollouts": s.rollouts,
        "swallowed": s.swallowed,
        "setup_asks": s.setup_asks,
        "arm_crash": s.arm_crash,
        "buckets": dict(s.buckets),
        "top1_visit_sum": s.top1_visit_sum,
        "abs_value_dev_sum": s.abs_value_dev_sum,
        "net_disagree": s.net_disagree,
        "by_kind": {k: dict(v) for k, v in s.by_kind.items()},
        "kind_top1": s.kind_top1,
        "kind_dev": s.kind_dev,
        "probes": s.probes,
        "probe_cache_hits": s.probe_cache_hits,
        "probe_ms": round(s.probe_ms, 1),
        "apply_ms": round(s.apply_ms, 1),
        "rollout_ms": round(s.rollout_ms, 1),
        "net_fwd": s.net_fwd,
        "net_fwd_ms": round(s.net_fwd_ms, 1),
        "policy_mix": dict(s.policy_mix),
        "n_eps": sum(len(v) for v in r["episodes"].values()),
        "episodes": r["episodes"],  # parent writes then drops
    }


def _flush(episodes_path: Path, games: list[dict]) -> int:
    """Write every episode of the completed games; strips the in-memory
    asks-row extras only where required (pi/value/net_idx/heur_idx STAY —
    they are the point of this dataset)."""
    n = 0
    with episodes_path.open("w") as fh:
        for g in games:
            for seat, eps in g.pop("episodes", {}).items():
                for ep in eps:
                    ep["game_seed"] = g["seed"]
                    fh.write(json.dumps(ep) + "\n")
                    n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    # deferred: torch must stay un-imported in the parent until workers pin
    # their own thread counts (see _worker)
    import os as _os

    _os.environ.setdefault("OMP_NUM_THREADS", "1")
    from tools.search import mcts

    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=32)
    ap.add_argument("--workers", type=int, default=20)
    ap.add_argument("--smoke", action="store_true", help="2 serial games, no write")
    ap.add_argument("--budget-min", type=float, default=BUDGET_MIN_DEFAULT)
    ap.add_argument("--seeds", type=int, default=9100, help="first game seed")
    ap.add_argument("--k", type=int, default=mcts.K_DEFAULT)
    ap.add_argument("--n", type=int, default=mcts.N_ROLLOUTS_DEFAULT)
    ap.add_argument(
        "--cap",
        type=int,
        default=mcts.ROLL_CAP_DEFAULT,
        help="rollout turn cap (/69 cost wave: 25)",
    )
    ap.add_argument(
        "--cheap-rollout",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="rollout seats greedy/random only; "
        "net used for root menu_probs pruning alone",
    )
    ap.add_argument("--out-episodes", type=Path, default=OUT_EPISODES)
    ap.add_argument("--out-stats", type=Path, default=OUT_STATS)
    args = ap.parse_args(argv)
    knobs = (args.k, args.n, args.cap, args.cheap_rollout)
    t0 = time.time()

    if args.smoke:
        for seed in (args.seeds, args.seeds + 1):
            g = _worker(seed, *knobs)
            assert g["crash"] is None, f"smoke crash {seed}: {g['reason']}"
            assert g["asks_searched"] >= 3, f"smoke degenerate {seed}"
            print(
                f"smoke seed={seed} {g['seconds']}s result={g['result']} "
                f"asks={g['asks_searched']} rollouts={g['rollouts']} "
                f"swallow={g['swallowed']} crash_buckets={g['buckets'].get('crash', 0)} "
                f"eps={g['n_eps']}"
            )
        print("SMOKE OK")
        return 0

    deadline = t0 + args.budget_min * 60.0
    seeds = list(range(args.seeds, args.seeds + args.games))
    done: list[dict] = []
    with cf.ProcessPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(_worker, s, *knobs): s for s in seeds}
        pending = set(futs)
        try:
            # cf.wait, NOT as_completed: the budget must fire even when ZERO
            # games finish (as_completed's body can only run on a completion).
            while pending:
                left = deadline + GRACE_MIN * 60.0 - time.time()
                if left <= 0:
                    print(
                        f"BUDGET exceeded; cutting pool at {len(done)}/{len(seeds)}",
                        flush=True,
                    )
                    break
                fin, pending = cf.wait(pending, timeout=min(30.0, max(1.0, left)))
                for fut in fin:
                    pending.discard(fut)
                    try:
                        g = fut.result()
                        done.append(g)
                        print(
                            f"[{time.strftime('%H:%M:%S')}] game seed={g['seed']} "
                            f"{g['seconds']}s {g['result']} asks={g['asks_searched']} "
                            f"eps={g['n_eps']} done={len(done)}/{len(seeds)}",
                            flush=True,
                        )
                    except BaseException as e:  # noqa: BLE001
                        print(
                            f"worker died seed={futs[fut]}: {type(e).__name__}: {e}",
                            flush=True,
                        )
        finally:
            # shutdown() never kills RUNNING children; terminate them or they
            # outlive the budget (measured: 16 workers kept burning cores).
            for p in list(pool._processes.values()):
                p.terminate()
            pool.shutdown(wait=False, cancel_futures=True)

    n_eps = _flush(args.out_episodes, done)
    agg = _aggregate(done, time.time() - t0, n_eps)
    args.out_stats.write_text(json.dumps(agg, indent=1))
    print(json.dumps(agg["headline"], indent=1))
    print(f"wrote {n_eps} episodes -> {args.out_episodes.name}; stats -> {args.out_stats.name}")
    return 0


def _mix_total(games: list[dict]) -> Counter:
    """Sum the per-game greedy/random/net seat-draw counters."""
    total: Counter = Counter()
    for g in games:
        total.update(g["policy_mix"])
    return total


def _aggregate(games: list[dict], wall: float, n_eps: int) -> dict:
    n = len(games)
    asks = sum(g["asks_searched"] for g in games)
    rolls = sum(g["rollouts"] for g in games)
    buck: Counter = Counter()
    kinds: dict[str, Counter] = {}
    for g in games:
        buck.update(g["buckets"])
        for k, v in g["by_kind"].items():
            kinds.setdefault(k, Counter()).update(v)
    dev_shaping = buck["shaping"] / max(1, rolls)
    return {
        "wall_seconds": round(wall, 1),
        "seconds_per_game_serialised": round(
            sum(g["seconds"] for g in games) / max(1, n), 1
        ),
        "games": n,
        "results": dict(Counter(g["result"] for g in games)),
        "crashes": [g["seed"] for g in games if g["crash"]],
        "episodes": n_eps,
        "asks_searched": asks,
        "asks_per_game": round(asks / max(1, n), 1),
        "rollouts": rolls,
        "rollouts_per_ask": round(rolls / max(1, asks), 2),
        "rollout_fail_rate": round(buck["crash"] / max(1, rolls), 4),
        "headline": {
            "top1_visit_share": round(
                sum(g["top1_visit_sum"] for g in games) / max(1, asks), 3
            ),
            "mean_abs_value_dev": round(
                sum(g["abs_value_dev_sum"] for g in games) / max(1, asks), 3
            ),
            "shaping_share": round(dev_shaping, 3),
            "decided_share": round(buck["decided"] / max(1, rolls), 3),
            "swallowed_asks": sum(g["swallowed"] for g in games),
            "net_disagree_rate": round(
                sum(g["net_disagree"] for g in games) / max(1, asks), 3
            ),
        },
        "buckets": dict(buck),
        "by_kind": {k: dict(v) for k, v in sorted(kinds.items())},
        "cost": {
            # cost ledger (breakdown gate): where the CPU actually went
            "probes": sum(g["probes"] for g in games),
            "probe_cache_hits": sum(g["probe_cache_hits"] for g in games),
            "probe_ms": round(sum(g["probe_ms"] for g in games), 1),
            "apply_ms": round(sum(g["apply_ms"] for g in games), 1),
            "rollout_ms": round(sum(g["rollout_ms"] for g in games), 1),
            "net_fwd": sum(g["net_fwd"] for g in games),
            "net_fwd_ms": round(sum(g["net_fwd_ms"] for g in games), 1),
            "policy_mix": dict(_mix_total(games)),
            "seconds_per_game_min": round(min(g["seconds"] for g in games), 1),
            "seconds_per_game_max": round(max(g["seconds"] for g in games), 1),
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
