"""The examples behind §2's table: every decision of nothing outside the trigger order, and the
redundant-option decisions, grouped by kind and source card, with their options by name.

    .venv/bin/python reports/network_readiness_2026-11-18/examples.py OUT.jsonl [OUT2.jsonl ...]
"""

from __future__ import annotations

import json
import sys
from collections import Counter


def main() -> int:
    rows = [json.loads(line) for p in sys.argv[1:] for line in open(p)]
    nothing, redundant = Counter(), Counter()
    shown = Counter()
    for r in rows:
        cls = [c for c in r.get("cls", []) if c >= 0]
        if len(cls) < 2:
            continue
        key = (r["kind"], r.get("src", ""))
        if len(set(cls)) == 1 and len(cls) == len(r["cls"]):  # every option tested (summarise.py)
            nothing[key] += 1
            if shown[("n",) + key] < 2:
                shown[("n",) + key] += 1
                print("NOTHING", r["kind"], "|", r.get("src"), "|", r["site"], "|", r.get("names"),
                      "|", r.get("status"))
        elif len(set(cls)) < len(cls):
            redundant[key] += 1
    # the trigger order's decisions of nothing: copies of one source's ability (F1's exact case:
    # card:12 and card:12:2 share their source) or triggers of different sources
    same = diff = 0
    for r in rows:
        cls = [c for c in r.get("cls", []) if c >= 0]
        if r["kind"] == "trigger" and len(cls) >= 2 and len(set(cls)) == 1 and len(cls) == len(r["cls"]):
            srcs = {":".join(t.split(":")[:2]) for t in r.get("toks") or []}
            same += len(srcs) == 1
            diff += len(srcs) > 1
    print(f"\ntrigger-order decisions of nothing: one source {same}, several sources {diff}")
    print("\ndecisions of nothing by (kind, source):")
    for k, v in nothing.most_common(60):
        print(f"  {v} {k}")
    print("\nredundant-option decisions by kind:")
    by_kind = Counter()
    for (kind, _), v in redundant.items():
        by_kind[kind] += v
    for k, v in by_kind.most_common():
        print(f"  {v} {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
