"""The n-curve (docs/PLAN_CEILING.md §3.3): a searcher's strength against the number of
simulations n, read from evaluation runs of one network.

Each run directory is one point: ``learner.py --eval-only --init CKPT --eval-seat eval+search
--eval-opponents snap:opp --opp-ckpt CKPT --search-root gumbel --search-n N ...``. Per point: the
paired score against the opponent with its deal-level standard error, the searched decisions,
changes and clear corrections per game, and a searched decision's milliseconds. Then the score is
regressed on log2 n over the points that differ only in n (weighted by 1 / SE^2): one doubling's
gain is smaller than a point's standard error, so the slope over all points is the result, not a
knee read from neighbours.

    .venv/bin/python -m tools.selfplay.ncurve RUN_DIR...
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

#: The settings that make two points comparable apart from n (the learner's flags).
SAME = ("search_root", "search_m", "search_continuation", "search_horizon", "search_kinds",
        "search_skip_p", "search_blocks", "search_k", "search_d", "init", "opp_ckpt", "pool",
        "eval_set", "eval_opponents", "eval_seed0")


def point(run: Path) -> dict:
    args = json.loads((run / "manifest.json").read_text())[-1]["args"]
    summary = [json.loads(line) for line in (run / "metrics.jsonl").read_text().splitlines()
               if '"event": "eval"' in line][-1]
    deals: dict = defaultdict(list)
    for line in (run / "eval_rows.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r["outcome"].startswith("void") or r.get("leaky"):
            continue
        s = 0.5 if r["outcome"] != "win" else float(r["winner"] == r["a_seat"])
        deals[(r["seed"], r["deck_mode"])].append(s)
    scores = [sum(v) / len(v) for v in deals.values()]
    mean = sum(scores) / len(scores)
    se = math.sqrt(sum((x - mean) ** 2 for x in scores) / (len(scores) - 1) / len(scores))
    st = summary.get("search", {})
    games = 2 * len(scores)
    return {"run": run.name, "n": args["search_n"], "args": args, "score": mean, "se": se,
            "deals": len(scores),
            "searched_per_game": round(st.get("searched", 0) / games, 2),
            "changed": round(st.get("changed", 0) / max(st.get("searched", 0), 1), 3),
            "clear_per_game": round(st.get("clear", 0) / games, 3),
            "ms": summary.get("search_ms", {})}


def fit(points: list[dict]) -> tuple[float, float, float]:
    """Weighted least squares of score on log2 n: (slope per doubling, its SE, intercept)."""
    w = [1 / p["se"] ** 2 for p in points]
    x = [math.log2(p["n"]) for p in points]
    y = [p["score"] for p in points]
    sw = sum(w)
    mx = sum(wi * xi for wi, xi in zip(w, x)) / sw
    my = sum(wi * yi for wi, yi in zip(w, y)) / sw
    sxx = sum(wi * (xi - mx) ** 2 for wi, xi in zip(w, x))
    slope = sum(wi * (xi - mx) * (yi - my) for wi, xi, yi in zip(w, x, y)) / sxx
    return slope, math.sqrt(1 / sxx), my - slope * mx


def main(argv: list[str]) -> None:
    pts = [point(Path(r)) for r in argv]
    groups: dict = defaultdict(list)
    for p in pts:
        groups[tuple(str(p["args"].get(k)) for k in SAME)].append(p)
        ms = p["ms"]
        print(f"{p['run']:<28} n {p['n']:>4}  score {p['score']:.4f} +- {p['se']:.4f} "
              f"({p['deals']} deals)  searched/game {p['searched_per_game']}  changed "
              f"{p['changed']}  clear/game {p['clear_per_game']}  ms p50 {ms.get('p50')} "
              f"p99 {ms.get('p99')}")
    for key, group in groups.items():
        if len({p["n"] for p in group}) < 2:
            continue
        slope, se, icpt = fit(group)
        print(f"fit over {len(group)} points ({dict(zip(SAME[:5], key[:5]))}): "
              f"{slope:+.4f} per doubling of n, 95% [{slope - 1.96 * se:+.4f}, "
              f"{slope + 1.96 * se:+.4f}], score {icpt:.4f} at n = 1")


if __name__ == "__main__":
    main(sys.argv[1:])
