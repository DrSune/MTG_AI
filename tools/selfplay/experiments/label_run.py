"""E1/E3 label generation: self-play games of one network on fresh natural deals, whose act
decisions are labelled by search.Labeller (true futures). Every network forward pass the job
serves is counted (real games and playouts).

    PYTHONPATH=<checkout> PY label_run.py --run DIR --init CKPT --label-k 2 --label-d 2
        --label-greedy 1 --label-fp 10600000 --seed0 30000000 [learner args...]

Writes DIR/labels.pkl (a stream of pickled lists of label dicts), DIR/games.jsonl (one row per
game) and DIR/summary.json (refreshed every 50 games and at the end).
"""

from __future__ import annotations

import json
import pickle
import signal
import sys
import time

from tools.selfplay import learner as L


class LabelRun(L.Learner):
    def __init__(self, args, extra):
        self.extra = extra
        self.issued = 0
        self.done_games = 0
        self.n_labels = 0
        self.pending = []
        self.sums = {"eligible": 0, "playouts": 0, "crashes": 0, "rails": 0, "fp": 0, "void": 0,
                     "leaky": 0}
        super().__init__(args)
        self.phase = "label"
        self.t0 = self.last_flush = time.time()

    def next_job(self):
        if self.phase != "label" or self.infer_items >= self.extra["fp"]:
            return None
        if self.issued >= self.extra["max_games"]:
            return None
        self.issued += 1
        seed = self.extra["seed0"] + self.issued
        job = self._job("label", seed, ["learner", "learner"], [False, False], [False, False],
                        "coherent")
        job["label"] = {"k": self.extra["k"], "d": self.extra["d"], "greedy": self.extra["greedy"]}
        self._mix(job)
        return job

    def on_done(self, results):
        for r in results:
            if r["kind"] != "label":
                continue
            self.done_games += 1
            void = r["outcome"].startswith("void")
            self.sums["void"] += void
            self.sums["leaky"] += bool(r.get("leaky"))
            for k, v in (r.get("label_stats") or {}).items():
                self.sums[k] = self.sums.get(k, 0) + v
            for lab in r.get("labels") or []:
                lab.update(gid=r["gid"], seed=r["seed"], set=r["set_code"], game_void=void,
                           game_outcome=r["outcome"], game_turns=r["turns"])
                self.pending.append(lab)
            with (self.run / "games.jsonl").open("a") as fh:
                fh.write(json.dumps({k: r.get(k) for k in ("gid", "seed", "set_code", "outcome",
                                     "winner", "turns", "crash", "leaky", "label_stats")}) + "\n")
            if self.done_games % 50 == 0 or time.time() - self.last_flush > 60:
                self.flush()

    def flush(self):
        self.last_flush = time.time()
        if self.pending:
            with (self.run / "labels.pkl").open("ab") as fh:
                pickle.dump(self.pending, fh, protocol=pickle.HIGHEST_PROTOCOL)
            self.n_labels += len(self.pending)
            self.pending = []
        summary = {"games": self.done_games, "issued": self.issued, "labels": self.n_labels,
                   "forward_passes": self.infer_items, "infer_batches": self.infer_batches,
                   "secs": round(time.time() - self.t0, 1), **self.sums, "config": self.extra}
        (self.run / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
        self.log({"event": "label_progress", **{k: summary[k] for k in (
            "games", "labels", "forward_passes", "secs", "playouts", "crashes", "rails")}})

    def main(self):
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))  # finally: flush, stop workers
        try:
            self.serve(lambda: self.issued > 0 and self.done_games >= self.issued
                       and self.next_job_blocked())
        finally:
            self.flush()
            self.stop_workers()

    def next_job_blocked(self):
        return self.infer_items >= self.extra["fp"] or self.issued >= self.extra["max_games"]


def main():
    argv = sys.argv[1:]
    extra = {}
    for key, cast in (("--label-k", int), ("--label-d", int), ("--label-greedy", int),
                      ("--label-fp", float), ("--seed0", int), ("--max-games", int)):
        if key in argv:
            i = argv.index(key)
            extra[key[2:].replace("label-", "").replace("-", "_")] = cast(argv[i + 1])
            del argv[i:i + 2]
    extra.setdefault("max_games", 10**9)
    extra["greedy"] = bool(extra["greedy"])
    args = L.parse(argv)
    LabelRun(args, extra).main()


if __name__ == "__main__":
    main()
