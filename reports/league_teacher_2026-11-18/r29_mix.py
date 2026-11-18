"""Who r29's learner plays and how fast (docs/DESIGN_LEAGUE.md §1.1), read from a run's iter rows.

Per run: the training win rate per opponent group every 20 updates, the gates and freezes, and
the medians of the collection time, the update time, the refused job requests (``throttled``: a
full batch waiting, so the run is train-bound), games and decisions per second.

    CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 nice -n 19 .venv/bin/python \
        reports/league_teacher_2026-11-18/r29_mix.py runs/selfplay/r29a_pself0 \
        runs/selfplay/r29b_pself055

Read on 2026-11-18 at r29 B's update 174 (the numbers in DESIGN_LEAGUE §1.1).
"""

import json
import statistics as st
import sys


def main(runs: list[str]) -> None:
    for run in runs:
        rows = [json.loads(line) for line in open(f"{run}/metrics.jsonl")]
        iters = [r for r in rows if r.get("event") == "iter"]
        print(run, "updates", len(iters), "last", iters[-1]["it"] if iters else None)
        for r in iters[::20] + iters[-3:]:
            print("  it", r["it"], "win", r.get("win"), "games", r.get("games"),
                  "learner seats", r.get("learner_seats"))
        for r in rows:
            if r.get("event") in ("gate", "freeze"):
                print("  ", {k: r.get(k) for k in ("event", "it", "vs", "score", "ci95", "passed",
                                                   "version")})
        late = [r for r in iters if r["it"] >= 2]
        for key in ("collect_s", "upd_s", "throttled", "steps", "games_s", "dec_s", "games"):
            print(f"  median {key}", st.median(r.get(key, 0) for r in late))


if __name__ == "__main__":
    main(sys.argv[1:])
