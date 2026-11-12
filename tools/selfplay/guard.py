"""A run's kill criteria while nobody watches (KNOWLEDGE 199 §3): a safety rail, not a knob.

    .venv/bin/python -m tools.selfplay.guard RUN_DIR UNIT [--every 600]

Every ``--every`` seconds it reads the last row per update of ``RUN_DIR/metrics.jsonl``. On a
breach it writes the reason to ``RUN_DIR/guard.log`` and stops the systemd user unit ``UNIT``,
then exits. A paused run (gate B's pause) is no breach: the guard waits for new updates.
- The learner's mulligan declarations per game above ``--mull-max`` (1.80: r27's runaway, 198)
  in a mean of 10 updates.
- The training win rate against the heuristic, in a mean of 50 updates, more than 0.05 below its
  mean over updates 1-50 (191 §5).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path


def last_rows(path: Path) -> list[dict]:
    """The last ``iter`` row of every update, in update order (a resume replays updates)."""
    rows: dict[int, dict] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if '"event": "iter"' in line:
                r = json.loads(line)
                rows[r["it"]] = r
    return [rows[k] for k in sorted(rows)]


def breach(rows: list[dict], mull_max: float = 1.8) -> str | None:
    """The first kill criterion the rows meet, as a reason, or None."""
    def mull(r: dict) -> float:
        k = r.get("kinds", {}).get("mulligan")
        return k["n"] / max(r["games"], 1) if k else 0.0

    if len(rows) >= 10:
        m = sum(mull(r) for r in rows[-10:]) / 10
        if m > mull_max:
            return f"mulligan declarations per game {m:.3f} over updates {rows[-10]['it']}-{rows[-1]['it']} > {mull_max}"
    first = [r["win"]["heuristic"] for r in rows if r["it"] <= 50 and "heuristic" in r.get("win", {})]
    recent = [r["win"]["heuristic"] for r in rows[-50:] if "heuristic" in r.get("win", {})]
    if len(first) >= 50 and len(rows) >= 100 and len(recent) >= 50:
        base, now = sum(first) / len(first), sum(recent) / len(recent)
        if now < base - 0.05:
            return f"win rate against the heuristic {now:.4f} over the last 50 updates < {base:.4f} - 0.05"
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("unit")
    ap.add_argument("--every", type=float, default=600.0)
    ap.add_argument("--mull-max", type=float, default=1.8)
    a = ap.parse_args(argv)
    run = Path(a.run)
    seen = -1
    while True:
        rows = last_rows(run / "metrics.jsonl")
        if rows and rows[-1]["it"] != seen:
            seen = rows[-1]["it"]
            why = breach(rows, a.mull_max)
            if why:
                with (run / "guard.log").open("a") as fh:
                    fh.write(json.dumps({"t": time.time(), "it": seen, "stop": a.unit, "why": why}) + "\n")
                subprocess.run(["systemctl", "--user", "stop", a.unit], check=False)
                return 0
        time.sleep(a.every)


if __name__ == "__main__":
    raise SystemExit(main())
