"""Paired comparison of two evaluations played on the same deals (``eval_rows.jsonl`` files).

Both runs must have played the same deal seeds with the same seat assignments (the learner's
fixed evaluation deals do). Rows are read by evalrows: a deal is (opponent, set, pool, seed, deck
mode), and rows pair only when all five match (rows written before the learner recorded set and
pool carry neither and pair only with each other); a deal counts only when each run has both of
its games and neither run voided it; a re-written row replaces the earlier one. Prints each run's
score on the shared deals and the mean per-deal difference with a bootstrap 95% interval over
deals (the deal is the unit: its two seat-swapped games share the deal's luck).

    .venv/bin/python -m tools.selfplay.paired A/eval_rows.jsonl B/eval_rows.jsonl \
        [--tag-a TAG] [--tag-b TAG] [--opp OPP]

A file holding more than one evaluation tag (a run's eval_rows.jsonl usually does) needs its
--tag-a/--tag-b: rows of different evaluations would otherwise replace each other per deal.
"""

from __future__ import annotations

import argparse
import json
import random
import sys

from tools.selfplay import evalrows as ER


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--tag-a", default=None)
    ap.add_argument("--tag-b", default=None)
    ap.add_argument("--opp", default=None)
    ap.add_argument("--boot", type=int, default=10000)
    args = ap.parse_args(argv)
    try:
        A = ER.deal_scores(ER.read(args.a, args.tag_a, args.opp))
        B = ER.deal_scores(ER.read(args.b, args.tag_b, args.opp))
    except ValueError as e:
        raise SystemExit(str(e)) from e
    diffs, sa, sb = [], [], []
    # rows written before set and pool were recorded hold None there: sort None as ""
    for key in sorted(set(A) & set(B), key=lambda k: tuple("" if x is None else x for x in k)):
        sa.append(A[key])
        sb.append(B[key])
        diffs.append(B[key] - A[key])
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
