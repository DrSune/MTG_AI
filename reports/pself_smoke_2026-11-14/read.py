"""The --p-self smoke's numbers from a run of counted.py: per opponent group, trained decisions and
inference requests per training game; the iter rows; the guard on them.

    PYTHONPATH=. .venv/bin/python reports/pself_smoke_2026-11-14/read.py RUN_DIR

A game is a finished training game (train_rows.jsonl). Its inference requests are every seat's
(requests.json, by game id); its trained decisions are the learner's recorded requests, which
are the rows its seats put in the batch. Means carry their standard error over games.
"""
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

from tools.selfplay.guard import breach, last_rows

run = Path(sys.argv[1])
asked: dict[int, int] = defaultdict(int)
trained: dict[int, int] = defaultdict(int)
for gid, _seat, key, record, n in json.loads((run / "requests.json").read_text()):
    asked[gid] += n
    if key == "learner" and record:
        trained[gid] += n
games = [json.loads(x) for x in (run / "train_rows.jsonl").read_text().splitlines()]


def group(seats: list[str]) -> str:
    if seats == ["learner", "learner"]:
        return "self"
    return "heuristic" if "heuristic" in seats else "frozen"


def mean_se(xs: list[float]) -> str:
    se = st.stdev(xs) / len(xs) ** 0.5 if len(xs) > 1 else float("nan")
    return f"{st.mean(xs):7.1f} ± {se:5.1f}"


by: dict[str, list[dict]] = defaultdict(list)
for g in games:
    if g["gid"] in asked and not g["outcome"].startswith("void"):
        by[group(g["seats"])].append(g)
by["all"] = [g for k in list(by) for g in by[k]]
print(f"{run}: {len(games)} training games logged")
print(f"{'group':10s} {'games':>5s} {'trained / game':>16s} {'trained / seat':>16s} "
      f"{'requests / game':>16s} {'requests / trained':>18s} {'turns':>6s}")
for k in ("self", "frozen", "heuristic", "all"):
    gs = by.get(k)
    if not gs:
        continue
    t = [trained[g["gid"]] for g in gs]
    a = [asked[g["gid"]] for g in gs]
    seats = [g["seats"].count("learner") for g in gs]
    print(f"{k:10s} {len(gs):5d} {mean_se(t):>16s} {mean_se([x / s for x, s in zip(t, seats)]):>16s} "
          f"{mean_se(a):>16s} {sum(a) / sum(t):18.3f} {st.mean(g['turns'] for g in gs):6.1f}")

rows = last_rows(run / "metrics.jsonl")
print("\niter rows (the last row per update)")
for r in rows:
    m = r.get("kinds", {}).get("mulligan", {}).get("n", 0)
    print(f"  it {r['it']}: steps {r['steps']} games {r['games']} learner_seats {r.get('learner_seats')}"
          f" win {r['win']} mulligan {m} (per seat {m / max(r.get('learner_seats', r['games']), 1):.2f},"
          f" per game {m / max(r['games'], 1):.2f}) train_s {r['train_s']} upd_s {r['upd_s']}"
          f" collect_s {r['collect_s']} overlap {r['overlap_steps']} turns {r['turns']}")
m = sum(r.get("kinds", {}).get("mulligan", {}).get("n", 0) for r in rows)
seats, n_games = sum(r.get("learner_seats", r["games"]) for r in rows), sum(r["games"] for r in rows)
print(f"pooled over {len(rows)} updates: mulligan declarations {m}, per learner seat "
      f"{m / max(seats, 1):.3f}, per game {m / max(n_games, 1):.3f}")
print(f"guard.breach on these rows: {breach(rows)!r}")
if rows:
    print(f"medians: train_s {st.median(r['train_s'] for r in rows):.1f}, "
          f"upd_s {st.median(r['upd_s'] for r in rows):.1f}, "
          f"collect_s {st.median(r['collect_s'] for r in rows):.1f}, "
          f"games per update {st.median(r['games'] for r in rows)}")
