"""Paired comparison of two evaluations played on the same deals (``eval_rows.jsonl`` files).

Both runs must have played the same deal seeds with the same seat assignments (the learner's
fixed evaluation deals do). A deal is (set, pool, seed, deck mode): rows pair only when all four
match; rows written before the learner recorded set and pool carry neither and pair only with
each other. A deal pair is used only if neither run voided it. Prints each run's
score on the shared games and the mean per-deal difference with a bootstrap 95% interval over
deals (the deal is the unit: its two seat-swapped games share the deal's luck).

    .venv/bin/python -m tools.selfplay.paired A/eval_rows.jsonl B/eval_rows.jsonl [--tag T]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict


def _score(r: dict) -> float:
    if r["outcome"] == "win":
        return 1.0 if r["winner"] == r["a_seat"] else 0.0
    return 0.5


def _load(path: str, tag: str | None, opp: str | None) -> dict:
    out: dict = defaultdict(dict)
    with open(path) as fh:
        for line in fh:
            r = json.loads(line)
            if tag and r.get("tag") != tag:
                continue
            if opp and r.get("opp") != opp:
                continue
            void = r["outcome"].startswith("void") or r.get("leaky")
            deal = (r["opp"], r.get("set_code"), r.get("pool"), r["seed"], r["deck_mode"])
            out[deal][r["a_seat"]] = None if void else _score(r)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--tag-a", default=None)
    ap.add_argument("--tag-b", default=None)
    ap.add_argument("--opp", default=None)
    ap.add_argument("--boot", type=int, default=10000)
    args = ap.parse_args(argv)
    A = _load(args.a, args.tag_a, args.opp)
    B = _load(args.b, args.tag_b, args.opp)
    diffs, sa, sb = [], [], []
    for key in sorted(set(A) & set(B)):
        pa, pb = A[key], B[key]
        if set(pa) != {0, 1} or set(pb) != {0, 1}:
            continue
        if None in pa.values() or None in pb.values():
            continue
        a_mean = (pa[0] + pa[1]) / 2
        b_mean = (pb[0] + pb[1]) / 2
        sa.append(a_mean)
        sb.append(b_mean)
        diffs.append(b_mean - a_mean)
    n = len(diffs)
    if n == 0:
        print(json.dumps({"deals": 0}))
        return 1
    rng = random.Random(0)
    boots = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(args.boot))
    out = {"deals": n, "games": 2 * n, "a": round(sum(sa) / n, 4), "b": round(sum(sb) / n, 4),
           "b_minus_a": round(sum(diffs) / n, 4),
           "ci95": [round(boots[int(0.025 * args.boot)], 4), round(boots[int(0.975 * args.boot)], 4)],
           "deals_b_better": sum(d > 0 for d in diffs), "deals_a_better": sum(d < 0 for d in diffs)}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
