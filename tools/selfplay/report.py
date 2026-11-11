"""One-screen status of a self-play run from its metrics.jsonl.

    .venv/bin/python -m tools.selfplay.report runs/selfplay/NAME [--iters 8]

Prints the frozen versions (when, which stage), the latest Elo ladder (uniform random = 0),
the gate and teacher-gate results, the greedy evaluations against the heuristic, the
training-game win rates in blocks of 10 iterations, the most recent iterations, and the last
one's statistics by ask kind (when it reports them). An iteration redone after a resume is
shown once (its last run).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--iters", type=int, default=8)
    args = ap.parse_args(argv)
    rows = [json.loads(line) for line in (Path(args.run) / "metrics.jsonl").open()]
    t0 = rows[0]["t"]

    def ago(t: float) -> str:
        return f"{(t - t0) / 3600:5.2f} h"

    print(f"run {args.run}: {len(rows)} rows, last {(time.time() - rows[-1]['t']) / 60:.1f} min ago")
    freezes = [r for r in rows if r.get("event") == "freeze"]
    print("\nversions:")
    for r in freezes:
        print(f"  {r['version']:>4}  it {r['it']:>4}  {ago(r['t'])}  stage {r.get('stage') or '-'}")
    elo = [r for r in rows if r.get("event") == "elo"]
    if elo:
        last = elo[-1]
        print(f"\nElo (uniform random = 0; {last['games']} games):")
        for name, rating in sorted(last["ratings"].items(), key=lambda kv: -kv[1]):
            print(f"  {name:>10}  {rating:8.1f}")
    gates = [r for r in rows if r.get("event") in ("gate", "teacher_gate")]
    if gates:
        print("\ngates (last 10):")
        for r in gates[-10:]:
            vs = r.get("vs", "heuristic")
            print(f"  it {r['it']:>4} {r['event']:<12} vs {vs:<9} score {r.get('score')} "
                  f"ci {r.get('ci95')} {'PASS' if r.get('passed') else '-'}")
    evals = [r for r in rows if r.get("event") == "eval" and "heuristic" in r
             and r.get("kind") in ("teacher", "ladder", None)]
    if evals:
        print("\nvs heuristic (greedy evals, last 10):")
        for r in evals[-10:]:
            h = r["heuristic"]
            print(f"  {r.get('tag', '?'):<18} score {h.get('score')} ci {h.get('ci95')} "
                  f"n {h.get('n')}")
    by_it: dict = {}
    for r in rows:
        if r.get("event") == "iter":
            by_it[r["it"]] = r
    iters = [by_it[k] for k in sorted(by_it)]
    if iters:
        print("\ntraining-game win rate by 10 iterations (sampled play):")
        for start in range(0, len(iters), 10):
            block = iters[start:start + 10]
            groups: dict = {}
            for r in block:
                for k, v in (r.get("win") or {}).items():
                    groups.setdefault(k, []).append(v)
            means = {k: round(sum(v) / len(v), 3) for k, v in sorted(groups.items())}
            print(f"  it {block[0]['it']:>4}-{block[-1]['it']:<4} {block[-1].get('stage', ''):<8} "
                  f"{means}")
        print(f"\nlast {args.iters} iterations:")
        for r in iters[-args.iters:]:
            print(f"  it {r['it']:>4} {r.get('stage', ''):<8} win {r.get('win', r.get('vs'))} "
                  f"kl {r.get('kl')} ent {r.get('ent')} ev {r.get('ev')} games/s {r.get('games_s')} "
                  f"upd {r.get('upd_s')}s mem {r.get('mem_gib')}G")
        kinds = iters[-1].get("kinds")
        if kinds:
            print(f"\nby ask kind, iteration {iters[-1]['it']} (pass = declined to act; ent / log|A|):")
            for name, k in sorted(kinds.items(), key=lambda kv: -kv[1]["n"]):
                print(f"  {name:<16} n {k['n']:>6}  pass {k['pass']:.3f}  adv {k['adv']:+.3f}  "
                      f"ent {k['ent']}  kl {k['kl']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
