"""Compare two probe_traces.py runs: the cards whose G1 trace changed, with the trace lines that
differ, and the engine errors on each side.

    .venv/bin/python reports/engine_faults_2026-11-12/probe_compare.py BASE.jsonl HEAD.jsonl
"""

from __future__ import annotations

import difflib
import json
import sys
from pathlib import Path


def load(path: str) -> dict:
    return {(r["set"], r["name"]): r for r in map(json.loads, Path(path).read_text().splitlines())}


base, head = load(sys.argv[1]), load(sys.argv[2])
assert base.keys() == head.keys(), "different cards"
changed = [k for k in sorted(base) if base[k]["sha"] != head[k]["sha"]]
print(f"{len(base)} cards probed; traces changed: {len(changed)}")
print("engine errors:", sum(r["errors"] or 0 for r in base.values()), "->",
      sum(r["errors"] or 0 for r in head.values()))
for key in changed:
    print(f"== {key[0]} {key[1]}")
    diff = difflib.unified_diff(base[key]["text"].splitlines(), head[key]["text"].splitlines(),
                                lineterm="", n=0)
    for line in list(diff)[2:]:
        print("  " + line)
