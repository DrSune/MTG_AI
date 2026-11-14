"""The learner with one counter, for the --p-self smoke: inference per game by opponent group.

    PYTHONPATH=. .venv/bin/python reports/pself_smoke_2026-11-14/counted.py LEARNER-ARGS...

Runs tools.selfplay.learner unchanged, counting every inference request by (game id, seat,
network key, recorded). At the end it writes <run>/requests.json, which read.py joins with the
run's train_rows.jsonl.
"""
import json
import sys
from collections import Counter
from pathlib import Path


def main() -> None:
    from tools.selfplay import learner as L

    counts: Counter = Counter()
    infer = L.Learner.infer

    def counted(self, msgs):
        for _, _, reqs in msgs:
            for req in reqs:
                counts[req[0], req[1], req[2], bool(req[4])] += 1
        return infer(self, msgs)

    L.Learner.infer = counted
    args = L.parse(sys.argv[1:])
    try:
        L.Learner(args).main()
    finally:
        Path(args.run, "requests.json").write_text(json.dumps([[*k, n] for k, n in counts.items()]))


if __name__ == "__main__":  # spawned workers and the trainer import this module: nothing runs
    main()
