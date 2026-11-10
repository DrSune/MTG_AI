"""The learner: GPU inference server for the workers, the training curriculum, evaluation.

Run (full commands in README.md here)::

    .venv/bin/python -m tools.selfplay.learner --run runs/selfplay/NAME --init CKPT ...
    .venv/bin/python -m tools.selfplay.learner --run runs/selfplay/NAME --init CKPT --eval-only

The curriculum; the network it starts from is frozen as v0:
1. Teacher inter-play, only for a network trained from scratch (--bc-games, no --init):
   heuristic-vs-heuristic games record (features, action) for both seats; the network learns
   the action (cross-entropy) and the outcome (value MSE).
2. Teacher stage: PPO against the heuristic until a frozen copy of the learner scores
   --teacher-gate against it (Wilson lower bound above 0.5) or --teacher-iters pass.
3. Self-play stage: PPO against the newest frozen version, older versions (--p-past) and the
   heuristic (--p-heuristic). Every --gate-every iterations a gate match on fresh deals freezes
   the learner as the next version when it scores --gate-score with the lower bound above 0.5.

PPO: every learner decision is recorded with its log-probability and value; when a game ends
its seats get +1 (win), -1 (loss), --draw-reward (turn cap or stall) or 0 (both lose at once),
and GAE turns that into per-decision advantages. Each update runs in the trainer process
(trainer.py) while this process keeps serving the workers on the current weights.

Evaluation: greedy play on fixed deals, each deal twice with the seats swapped (duplicate
format); score = (wins + draws/2) / games, a voided game voids its pair. Ratings: Elo by
Bradley-Terry over the ladder games, uniform random = 0.

Every number goes to <run>/metrics.jsonl; checkpoints to <run>/*.pt. Each start of the learner
(a resume too) appends what ran, from which code, where and when to <run>/manifest.json.
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import platform
import random
import signal
import socket
import subprocess
import sys
import time
from collections import Counter, defaultdict, deque
from datetime import datetime
from multiprocessing.connection import wait
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F

from MTG_bot.core.executor.games import get_supply
from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay import simulator as S
from tools.selfplay.actor import is_net, worker_main
from tools.selfplay.ppo import chunks, pack_buffer
from tools.selfplay.trainer import trainer_main

REPO = Path(__file__).resolve().parents[2]
TRAIN_SET = "M21"  # the set training games are dealt from (--mix-sets adds others)
EVAL_SEED0 = 900_000
# Gates draw a fresh block of deals each time (GATE_SEED0 + 1000 * gate number): re-testing a
# learner on the same deals until one snapshot clears the bar selects luck on those deals.
GATE_SEED0 = 2_000_000
TRAIN_SEED0 = 10_000_000
BC_SEED0 = 5_000_000
CAPTURE_SEED0 = 30_000_000  # + 1,000,000 x --seed: each capture run deals its own games


def deal_interval(deal_scores: list[float], z: float = 1.96) -> tuple[float, float]:
    """95% interval of the mean score over deals, each deal the mean of its two seat-swapped
    games. The two games of a deal are anti-correlated, so an interval over games as if
    independent (Wilson) would be about twice as wide; the deal is the independent unit."""
    n = len(deal_scores)
    if n < 2:
        return (0.0, 1.0)
    mean = sum(deal_scores) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in deal_scores) / (n - 1))
    h = z * sd / math.sqrt(n)
    return (round(max(0.0, mean - h), 4), round(min(1.0, mean + h), 4))


def length_buckets(items: list, ratio: float = 1.4, min_n: int = 8) -> list[list]:
    """Split one model's inference requests into length-sorted buckets, so a batch is not padded
    to its single longest decision. ``items`` are (message index, request index, request); the
    request's features are req[5]."""
    def length(it: tuple) -> int:
        f = it[2][5]
        return f["cards_i"].shape[0] + f["opts_i"].shape[0]

    out: list[list] = []
    cur: list = []
    for it in sorted(items, key=length):
        if cur and len(cur) >= min_n and length(it) > ratio * max(length(cur[0]), 4):
            out.append(cur)
            cur = []
        cur.append(it)
    if cur:
        out.append(cur)
    return out


def fit_elo(games: list[tuple[str, str, float]], anchor: str = "random",
            prior: float = 1.0, iters: int = 2000) -> dict[str, float]:
    """Bradley-Terry ratings in Elo points from ``(a, b, score_of_a)`` games, ``anchor`` = 0.

    ``prior`` adds that many virtual drawn games to every pair that met, so a 200-0 result
    gives a large but finite gap (the bench's ``bradley_terry`` refuses such data). Ratings far
    from every opponent a player actually met are extrapolations: read the gaps between
    neighbours on the ladder, not across it."""
    wins: dict[str, float] = defaultdict(float)
    pairs: dict[tuple[str, str], float] = defaultdict(float)
    for a, b, sc in games:
        key = (a, b) if a <= b else (b, a)
        pairs[key] += 1.0
        wins[a] += sc
        wins[b] += 1.0 - sc
    for (a, b) in list(pairs):
        pairs[(a, b)] += prior
        wins[a] += prior / 2
        wins[b] += prior / 2
    players = sorted({x for k in pairs for x in k})
    if anchor not in players:
        return {}
    strength = dict.fromkeys(players, 1.0)
    for _ in range(iters):
        new = {}
        for pl in players:
            den = sum(n / (strength[x] + strength[y]) for (x, y), n in pairs.items() if pl in (x, y))
            new[pl] = wins[pl] / den
        norm = new[anchor]
        delta = max(abs(math.log(new[pl] / norm / strength[pl])) for pl in players)
        strength = {pl: v / norm for pl, v in new.items()}
        if delta < 1e-10:
            break
    return {pl: round(400.0 * math.log10(strength[pl]), 1) for pl in players}


def mem_available_gib() -> float:
    with open("/proc/meminfo") as fh:
        for line in fh:
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 1048576
    return float("nan")


def write_manifest(run: Path, args: argparse.Namespace) -> dict:
    """Append this start of the learner to ``<run>/manifest.json``, a list with one entry per
    start (a resume or a restart adds an entry, never overwrites one): the parsed arguments, the
    git commit and whether the tree differs from it, the host, the Python and torch versions and
    the start time."""
    def git(*cmd: str) -> str | None:
        try:
            out = subprocess.run(["git", *cmd], cwd=REPO, capture_output=True, text=True,
                                 timeout=60)
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout if out.returncode == 0 else None

    commit = git("rev-parse", "HEAD")
    # untracked files count as dirty: card records on disk change what the pools deal. No
    # optional locks: a status that refreshes the index would hold index.lock against the
    # commits of other agents working in the same checkout.
    status = git("--no-optional-locks", "status", "--porcelain")
    entry = {
        "started": datetime.now().astimezone().isoformat(timespec="seconds"),
        "t": round(time.time(), 1),  # the clock of the metrics.jsonl rows
        "host": socket.gethostname(),
        "git_commit": commit.strip() if commit else None,
        "git_dirty": bool(status.strip()) if status is not None else None,
        "git_status": status.splitlines() if status else [],
        "python": platform.python_version(),
        "torch": torch.__version__,
        "args": vars(args),
    }
    path = run / "manifest.json"
    entries = json.loads(path.read_text()) if path.exists() else []
    entries.append(entry)
    tmp = path.with_name("manifest.json.tmp")
    tmp.write_text(json.dumps(entries, indent=1, default=str) + "\n")
    tmp.replace(path)
    return entry


def gae(vals: list[float], z: float, gamma: float, lam: float) -> list[float]:
    """Generalised advantage estimates for one seat's decisions in one game, whose end pays
    ``z`` after the last decision. A game cut off before its end passes ``z = vals[-1]``: the
    truncated-episode bootstrap (Pardo et al. 2018, "Time Limits in Reinforcement Learning"),
    with the last decision's own value standing in for the unobserved cut-off state, so the
    decision that ran into the failure gets zero advantage."""
    adv = [0.0] * len(vals)
    last = 0.0
    for t in range(len(vals) - 1, -1, -1):
        next_v = vals[t + 1] if t + 1 < len(vals) else 0.0
        delta = (z if t == len(vals) - 1 else 0.0) + gamma * next_v - vals[t]
        last = delta + gamma * lam * last
        adv[t] = last
    return adv


class Learner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.run = Path(args.run)
        self.run.mkdir(parents=True, exist_ok=True)
        write_manifest(self.run, args)
        self.device = torch.device("cuda" if torch.cuda.is_available() and args.device != "cpu"
                                   else "cpu")
        self.cuda = self.device.type == "cuda"
        torch.manual_seed(args.seed)
        np.random.seed(args.seed)
        self.rng = random.Random(args.seed)
        if args.init:
            self.model, self.table, extra = M.load(args.init, self.device)
            self.log({"event": "init", "from": args.init, "extra": extra})
            if args.refresh_table:
                # the saved table describes the trees as compiled when it was built; rebuild
                # its rows from the current compile (FT.CardTable.refresh)
                records = {oid: r.card for oid, r in
                           get_supply("castable", "M21").pool.results.items()}
                self.table, ref = self.table.refresh(records)
                M.extend_cards(self.model, self.table)
                self.log({"event": "refresh_table", **ref})
            if args.extend_sets:
                # cards of other sets the network never trained on: rows in its component
                # vocabulary, names unknown (FT.CardTable.extend, M.extend_cards); when it will
                # train on them (--mix-sets), their unseen components become learnable tokens
                records = {}
                for code in args.extend_sets.split(","):
                    records.update({oid: r.card for oid, r in
                                    get_supply("castable", code).pool.results.items()})
                self.table, ext = self.table.extend(records, add_tokens=bool(args.mix_sets))
                M.extend_cards(self.model, self.table)
                self.log({"event": "extend_sets", "sets": args.extend_sets, **ext})
            if args.mask_names:
                self.model.mask_names = True
        else:
            supply = get_supply("castable")
            self.table = FT.CardTable.from_records(
                {oid: r.card for oid, r in supply.pool.results.items()})
            self.model = M.build(self.table, d=args.d, layers=args.layers, heads=args.heads,
                                 ff=args.ff, name_dropout=args.name_dropout).to(self.device)
        if args.mix_sets:
            missing = set(args.mix_sets.split(",")) - set(args.extend_sets.split(","))
            if missing:
                raise ValueError(f"--mix-sets {sorted(missing)} must also be in --extend-sets")
            self.log({"event": "mix", "sets": args.mix_sets, "share": args.mix_share,
                      "pool": args.pool})
        # Every game deals from --pool. A set with no deckable card in it (e.g. 'verified' for a
        # set whose cards nobody verified yet) fails here, not in every worker game it voids.
        for code in sorted({TRAIN_SET, args.eval_set, *filter(None, args.mix_sets.split(","))}):
            get_supply(args.pool, code)
        self.model.eval()
        self.models: dict[str, torch.nn.Module] = {"learner": self.model}
        self.infer_models: dict[str, tuple] = {}
        self.trainer = None  # the PPO trainer process, started at the first update
        self.tconn = None
        n_params = sum(p.numel() for p in self.model.parameters())
        self.log({"event": "model", "params": n_params, "config": self.model.config,
                  "device": str(self.device), "args": vars(args)})
        self.traj: dict[tuple[int, int], list] = {}
        self.buffer: list = []
        self.bc: list = []
        self.eval_jobs: deque = deque()
        self.eval_pending: set[int] = set()
        self.eval_rows: list = []
        self.eval_meta: dict = {}
        self.pending_need: dict[int, int] = {}
        self.gid = 0
        self.phase = "idle"
        self.bc_target = 0
        self.bc_issued = 0
        self.bc_done = 0
        self.stage = ""  # curriculum: "teacher" | "selfplay"
        self.versions: list[str] = []
        self.elo_games: list[tuple[str, str, float]] = []
        self.eval_queue: deque = deque()
        self.eval_kind: dict = {}
        self.it = 0
        self.counts: Counter = Counter()
        self.n_gates = 0
        self.train_results: list = []
        self.infer_batches = 0
        self.infer_items = 0
        self._mem_checked = 0.0
        self._start_workers()

    def weights_changed(self, net: torch.nn.Module) -> None:
        """Bump a model's weight version: its bf16 inference copy is rebuilt on next use."""
        net._wver = getattr(net, "_wver", 0) + 1

    def _infer_net(self, key: str) -> torch.nn.Module:
        """The network answering inference for ``key``: a bf16 copy of models[key] (autocast over
        fp32 weights would re-cast every weight on every forward), rebuilt whenever the source's
        weights changed (weight-version counter) or the key now names another model."""
        src = self.models[key]
        if not (self.args.infer_bf16 and self.cuda):
            return src
        cached = self.infer_models.get(key)
        ver = getattr(src, "_wver", 0)
        if cached is None or cached[0] is not src or cached[1] != ver:
            cfg = {k: v for k, v in src.config.items() if k not in ("n_cards", "n_ir")}
            net = M.build(self.table, **cfg).to(self.device)
            net.load_state_dict(src.state_dict())
            net.mask_names = src.mask_names
            net = net.to(torch.bfloat16).eval()
            torch.cuda.synchronize()
            self.infer_models[key] = (src, ver, net)
            return net
        return cached[2]

    def _copy(self, src: torch.nn.Module) -> torch.nn.Module:
        cfg = {k: v for k, v in self.model.config.items() if k not in ("n_cards", "n_ir")}
        net = M.build(self.table, **cfg).to(self.device)
        net.load_state_dict(src.state_dict())
        net.mask_names = src.mask_names
        net.eval()
        if self.cuda:
            torch.cuda.synchronize()  # the copy is complete before any stream reads it
        return net

    def update(self) -> dict:
        """One PPO update: hand the batch to the trainer process (its own CUDA context) and keep
        serving the workers on the current weights until the new ones come back. The workers
        play the next batch meanwhile; the PPO ratio and clipping account for its slightly
        older weights."""
        a = self.args
        if self.trainer is None:
            ctx = mp.get_context("spawn")
            self.tconn, child = ctx.Pipe(duplex=True)
            ckpt = {"config": self.model.config, "table": self.table.to_json(),
                    "state": {k: v.detach().cpu() for k, v in self.model.state_dict().items()}}
            self.trainer = ctx.Process(target=trainer_main, args=(child, ckpt, vars(a)),
                                       daemon=True)
            self.trainer.start()
        buf, self.buffer = self.buffer, []
        t0 = time.perf_counter()
        self.tconn.send(("update", pack_buffer(buf)))
        send_s = time.perf_counter() - t0
        del buf
        self.serve(lambda: self.tconn.poll() or not self.trainer.is_alive())
        if not self.tconn.poll():
            raise RuntimeError("trainer process died without a reply")
        msg = self.tconn.recv()
        if msg[0] == "error":
            self.log({"event": "trainer_error", "error": msg[1]})
            raise SystemExit(4)
        _, state, stats = msg
        self.model.load_state_dict(state)
        self.weights_changed(self.model)
        if self.cuda:
            torch.cuda.synchronize()
        stats["send_s"] = round(send_s, 2)
        stats["overlap_steps"] = len(self.buffer)
        return stats

    # ------------------------------------------------------------------ memory

    def check_memory(self) -> None:
        """Unified memory: host RAM and GPU memory are one pool, and exhausting it freezes the
        machine. Below ``--mem-floor-gib`` the run saves an emergency checkpoint, stops its own
        workers and exits. A safety rail, not a tuning knob."""
        now = time.monotonic()
        if now - self._mem_checked < 1.0:
            return
        self._mem_checked = now
        avail = mem_available_gib()
        self.mem_min = min(getattr(self, "mem_min", avail), avail)
        if avail >= self.args.mem_floor_gib:
            return
        self.log({"event": "mem_floor", "avail_gib": round(avail, 2),
                  "floor_gib": self.args.mem_floor_gib, "it": self.it})
        self.buffer, self.bc, self.traj = [], [], {}
        try:
            self.save("emergency.pt")
        finally:
            self.stop_workers()
        raise SystemExit(3)

    def release_cache(self) -> None:
        if self.cuda:
            torch.cuda.empty_cache()

    # ------------------------------------------------------------------ logging

    def log(self, row: dict) -> None:
        row = {"t": round(time.time(), 1), **row}
        with (self.run / "metrics.jsonl").open("a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
        if row.get("event") not in ("model",):
            print(json.dumps(row, default=str)[:600], flush=True)

    # ------------------------------------------------------------------ workers

    def _start_workers(self) -> None:
        ctx = mp.get_context("spawn")
        self.conns = []
        self.procs = []
        table_json = self.table.to_json()
        for wid in range(self.args.workers):
            a, b = ctx.Pipe(duplex=True)
            p = ctx.Process(target=worker_main, args=(wid, b, self.args.slots, table_json, 5,
                                                      self.args.groups), daemon=True)
            p.start()
            self.conns.append(a)
            self.procs.append(p)

    def stop_workers(self) -> None:
        if self.trainer is not None:
            try:
                self.tconn.send(("stop",))
            except (BrokenPipeError, OSError):
                pass
            self.trainer.join(timeout=20)
            if self.trainer.is_alive():
                self.trainer.terminate()
            self.trainer = None
        for c in self.conns:
            try:
                c.send(("stop",))
            except (BrokenPipeError, OSError):
                pass
        for p in self.procs:
            p.join(timeout=10)
            if p.is_alive():
                p.terminate()

    # ------------------------------------------------------------------ jobs

    def _job(self, kind: str, seed: int, seats: list[str], greedy: list[bool],
             record: list[bool], deck_mode: str) -> dict:
        self.gid += 1
        return {"gid": self.gid, "kind": kind, "seed": seed, "seats": seats, "greedy": greedy,
                "record": record, "deck_mode": deck_mode, "set_code": TRAIN_SET,
                "pool_mode": self.args.pool}

    def _deck_mode(self) -> str:
        p = self.args.coherent_share
        return "coherent" if self.rng.random() < p else "stress"

    def next_job(self) -> dict | None:
        if self.eval_jobs:
            return self.eval_jobs.popleft()
        if self.phase == "bc" and self.bc_issued < self.bc_target:
            # teacher inter-play: heuristic vs heuristic, both seats' decisions recorded
            self.bc_issued += 1
            return self._job("bc", BC_SEED0 + self.bc_issued, ["heuristic", "heuristic"],
                             [True, True], [True, True], self._deck_mode())
        if self.phase == "ppo":
            # PPO wants on-policy batches. Workers keep playing during an update; once a full
            # next batch is waiting they get no new training games until the update takes it,
            # else a trainer slower than the workers makes every batch larger than the last.
            if len(self.buffer) >= self.args.steps:
                self.counts["throttled"] += 1
                return None
            return self.curriculum_job()
        return None

    def search_opts(self) -> dict:
        a = self.args
        return {"k": a.search_k, "d": a.search_d, "skip_p": a.search_skip_p,
                "blocks": a.search_blocks}

    def curriculum_job(self) -> dict:
        """Stage "teacher": the learner plays the heuristic. Stage "selfplay": the learner plays
        the newest frozen version (most games), older versions and the heuristic (a few, so it
        does not forget how to beat them). Only the learner's seat is trained on."""
        a = self.args
        # --seed moves the deals: a run started from another run's checkpoint must not train
        # again on the decks and shuffles its ancestors trained on
        seed = TRAIN_SEED0 + 1_000_000_000 * a.seed + self.gid + 1
        if self.stage == "teacher":
            opp = "heuristic"
        else:
            r = self.rng.random()
            if r < a.p_heuristic:
                opp = "heuristic"
            elif r < a.p_heuristic + a.p_past and len(self.versions) > 1:
                opp = self.rng.choice(self.versions[:-1])
            else:
                opp = self.versions[-1]
        seat = self.rng.randrange(2)
        seats = ["learner", opp] if seat == 0 else [opp, "learner"]
        job = self._job("train", seed, seats, [False, False], [x == "learner" for x in seats],
                        self._deck_mode())
        self._mix(job)
        return job

    def _mix(self, job: dict) -> None:
        """--mix-sets: a --mix-share of training games is dealt from another set (from the same
        --pool), the rest from TRAIN_SET. Evaluations and ladders deal from --eval-set."""
        a = self.args
        if not a.mix_sets or self.rng.random() >= a.mix_share:
            return
        job["set_code"] = self.rng.choice(a.mix_sets.split(","))

    def _serve_need(self, wid: int, n: int) -> None:
        jobs = []
        for _ in range(n):
            j = self.next_job()
            if j is None:
                break
            jobs.append(j)
        if jobs:
            self.conns[wid].send(("jobs", jobs))
            self.pending_need.pop(wid, None)
        else:
            self.pending_need[wid] = n

    def _flush_needs(self) -> None:
        for wid, n in list(self.pending_need.items()):
            self._serve_need(wid, n)

    # ------------------------------------------------------------------ serving

    def serve(self, until: Any, max_wait: float | None = None) -> None:
        """Answer workers until ``until()`` is true. Requests arriving within ``--serve-wait`` ms
        are answered together: each forward launches ~150 kernels from Python (~1-1.5 ms of
        this thread), so fewer, larger forwards keep the serving thread from saturating."""
        if max_wait is None:
            max_wait = self.args.serve_wait / 1000.0
        last_log = time.monotonic()
        while not until():
            self.check_memory()
            self._flush_needs()
            if time.monotonic() - last_log >= self.args.progress_every > 0:
                last_log = time.monotonic()
                self.log({"event": "progress", "phase": self.phase, "it": self.it,
                          "buffer": len(self.buffer), "target": self.args.steps,
                          "bc_done": self.bc_done, "bc_target": self.bc_target,
                          "mem_gib": round(mem_available_gib(), 1)})
            ready = wait(self.conns, timeout=0.05)
            if not ready:
                continue
            msgs = []
            deadline = time.monotonic() + max_wait
            while True:
                for c in ready:
                    while c.poll():
                        msg = c.recv()
                        if msg[0] == "infer":
                            msgs.append((c, msg[2], msg[3]))
                        elif msg[0] == "done":
                            self.on_done(msg[2])
                        elif msg[0] == "need":
                            self._serve_need(msg[1], msg[2])
                if time.monotonic() >= deadline or len(msgs) >= len(self.conns):
                    break
                ready = wait(self.conns, timeout=max(0.0, deadline - time.monotonic()))
                if not ready:
                    break
            if msgs:
                self.infer(msgs)

    @torch.no_grad()
    def infer(self, msgs: list) -> None:
        answers = [[0] * len(reqs) for (_, _, reqs) in msgs]
        by_key: dict[str, list] = defaultdict(list)
        for mi, (_, _, reqs) in enumerate(msgs):
            for ri, req in enumerate(reqs):
                by_key[req[2]].append((mi, ri, req))
        groups = []
        for key, items in by_key.items():
            for bucket in length_buckets(items, self.args.bucket_ratio, self.args.bucket_min):
                groups.append((key, bucket))
        for key, items in groups:
            model = self._infer_net(key)
            bf16 = next(model.parameters()).dtype == torch.bfloat16
            b = M.collate([it[2][5] for it in items], self.device)
            if bf16:
                b = {k: (v.to(torch.bfloat16) if v.dtype == torch.float32 else v)
                     for k, v in b.items()}
            with torch.autocast(self.device.type, dtype=torch.bfloat16,
                                enabled=self.cuda and not bf16):
                logits, value = model(b)
            logits, value = logits.float(), value.float()
            greedy = torch.tensor([bool(it[2][3]) for it in items], device=self.device)
            probs = torch.softmax(logits, -1)
            bad = ~torch.isfinite(probs).all(-1)
            if bool(bad.any()):  # one bad row kills the whole batch's multinomial: keep the evidence
                rows = bad.nonzero().flatten().tolist()
                dump = self.run / f"nonfinite_infer_it{self.it}.pt"
                torch.save({"batch": {k: v.cpu() for k, v in b.items()}, "rows": rows, "key": key,
                            "logits": logits.cpu()}, dump)
                detail = [{"ask_i": int(b["ask_i"][r]),
                           "options": int(b["opt_mask"][r].sum()),
                           "logits_nan": bool(torch.isnan(logits[r]).any()),
                           "all_neg_inf": bool(torch.isneginf(logits[r]).all())} for r in rows[:8]]
                raise RuntimeError(f"non-finite policy probabilities in {len(rows)} of {len(items)} rows "
                                   f"(net {key}): {detail}; batch saved to {dump}")
            sampled = torch.multinomial(probs, 1).squeeze(1)
            act = torch.where(greedy, logits.argmax(-1), sampled)
            logp = torch.log_softmax(logits, -1).gather(1, act[:, None]).squeeze(1)
            act_np = act.cpu().numpy()
            logp_np = logp.cpu().numpy()
            val_np = value.cpu().numpy()
            probs_np = probs.float().cpu().numpy() if any(
                len(it[2]) > 6 and it[2][6] >= 2 for it in items) else None
            for j, (mi, ri, req) in enumerate(items):
                a = int(act_np[j])
                # req[6] ("want"): 0/absent -> the action; 1 -> (action, value);
                # 2 -> (action, value, option probabilities) for decision-time search
                want = req[6] if len(req) > 6 else 0
                if want == 0:
                    answers[mi][ri] = a
                elif want == 1:
                    answers[mi][ri] = (a, float(val_np[j]))
                else:
                    k = req[5]["opts_i"].shape[0]
                    answers[mi][ri] = (a, float(val_np[j]),
                                       [round(float(x), 5) for x in probs_np[j, :k]])
                if req[4] and key == "learner":
                    self.traj.setdefault((req[0], req[1]), []).append(
                        (req[5], a, float(logp_np[j]), float(val_np[j])))
            self.infer_items += len(items)
        for (conn, group, _), ans in zip(msgs, answers, strict=True):
            conn.send(("ans", group, ans))
        self.infer_batches += 1

    # ------------------------------------------------------------------ results

    def reward(self, outcome: str, winner: int | None, seat: int) -> float:
        if outcome == "win":
            return 1.0 if winner == seat else -1.0
        if outcome in ("draw-cap", "draw-stall", "draw-other"):
            return self.args.draw_reward
        return 0.0  # draw-mutual

    def on_done(self, results: list) -> None:
        for r in results:
            kind = r["kind"]
            # A leaky ask (CHOOSE_NAME lists hidden cards) voids an EVALUATION pair (bench rule,
            # DESIGN_BENCHMARK 3.5). Training keeps the game: the network never sees that list,
            # the fallback answers it and that decision is not trained on.
            void = r["outcome"].startswith("void") or (kind == "eval" and r.get("leaky", 0) > 0)
            if r.get("leaky", 0):
                self.counts[f"{kind}:leaky"] += 1
            self.counts[f"{kind}:games"] += 1
            if void:
                self.counts[f"{kind}:void"] += 1
                if r.get("crash"):
                    self.counts[f"crash:{str(r['crash'])[:60]}"] += 1
            if kind == "train":
                self._finish_train(r, void)
            elif kind == "eval":
                self.eval_rows.append(r)
                self.eval_pending.discard(r["gid"])
                row = {k: r.get(k) for k in ("gid", "seed", "deck_mode", "seats", "a_seat", "opp",
                                              "outcome", "winner", "turns", "leaky", "crash",
                                              "set_code")}
                # the deal is (set, pool, seed, deck mode): paired.py pairs only equal deals
                row["pool"] = self.args.pool
                row["tag"] = self.eval_meta.get("tag")
                with (self.run / "eval_rows.jsonl").open("a") as fh:
                    fh.write(json.dumps(row) + "\n")
            elif kind == "capture":
                self.eval_pending.discard(r["gid"])
                if not void:
                    self.captured.append(r)
                if len(self.captured) >= 1000:
                    self._save_capture()
            elif kind == "bc":
                self.bc_done += 1
                if not void and r.get("bc"):
                    for seat in (0, 1):
                        z = self.reward(r["outcome"], r["winner"], seat)
                        for feats, act in r["bc"][seat] or []:
                            self.bc.append((feats, act, z, r["gid"]))

    def _finish_train(self, r: dict, void: bool) -> None:
        a = self.args
        self.counts["overflow"] += sum(r.get("overflow", [0, 0]))
        for seat in (0, 1):
            steps = self.traj.pop((r["gid"], seat), None)
            if not steps:
                continue
            vals = [s[3] for s in steps]
            # A void game was cut off by an engine, agent or worker failure. Dropping it would
            # make the failure an escape from a lost position (a policy learns to reach it);
            # bootstrapping makes reaching it worth what the position was worth.
            z = vals[-1] if void else self.reward(r["outcome"], r["winner"], seat)
            adv = gae(vals, z, a.gamma, a.lam)
            for (f, act, logp, v), ad in zip(steps, adv, strict=True):
                self.buffer.append((f, act, logp, v, ad, ad + v))
        if not void:
            seats = r["seats"]
            for seat in (0, 1):
                if seats[seat] == "learner" and seats[1 - seat] != "learner":
                    self.train_results.append((seats[1 - seat], self.reward(
                        r["outcome"], r["winner"], seat), r["turns"], r["set_code"]))

    # ------------------------------------------------------------------ BC

    def bc_train(self) -> None:
        """Behaviour cloning on self.bc (teacher inter-play): cross-entropy on the teacher's move
        plus --bc-vcoef x value MSE on the game's outcome; linear warmup, then cosine decay."""
        a = self.args
        net = self.model
        data, self.bc = self.bc, []
        gids = sorted({x[3] for x in data})
        # whole games are held out (by id): positions of one game share its outcome and are
        # near copies, so a split by position would leak the test set into training
        every = max(2, int(1 / max(a.bc_holdout, 1e-3)))
        hold = {g for g in gids if g % every == 0}
        train = [x for x in data if x[3] not in hold]
        test = [x for x in data if x[3] in hold]
        self.log({"event": "bc_data", "samples": len(data), "train": len(train),
                  "test": len(test), "games": len(gids)})
        net.train()
        opt = torch.optim.AdamW(net.parameters(), lr=a.bc_lr, weight_decay=a.wd)
        steps_total = max(1, a.bc_epochs * math.ceil(len(train) / a.mb))
        warm = max(1, steps_total // 20)
        sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / warm) * (
            0.05 + 0.95 * 0.5 * (1 + math.cos(math.pi * min(1.0, s / steps_total)))))
        lengths = np.array([x[0]["cards_i"].shape[0] + x[0]["opts_i"].shape[0] for x in train],
                           dtype=np.float64)
        for epoch in range(a.bc_epochs):
            t0 = time.time()
            ls = []
            batches = chunks(lengths, a.mb, a.tok_budget)
            for ch in batches:
                self.check_memory()
                b = M.collate([train[i][0] for i in ch], self.device)
                act = torch.tensor([train[i][1] for i in ch], device=self.device)
                z = torch.tensor([train[i][2] for i in ch], device=self.device)
                with torch.autocast(self.device.type, dtype=torch.bfloat16, enabled=self.cuda):
                    logits, v = net(b)
                loss = F.cross_entropy(logits.float(), act) + a.bc_vcoef * F.mse_loss(v, z)
                # equal weight per decision across length-sorted, token-capped chunks
                loss = loss * (len(ch) * len(batches) / max(len(train), 1))
                opt.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), a.max_grad)
                opt.step()
                sched.step()
                ls.append(loss.item())
            acc, vl = self.bc_eval(test)
            self.log({"event": "bc_epoch", "epoch": epoch, "loss": round(float(np.mean(ls)), 5),
                      "test_acc": acc, "test_vloss": vl, "secs": round(time.time() - t0, 1)})
        net.eval()
        self.weights_changed(net)
        self.release_cache()

    @torch.no_grad()
    def bc_eval(self, test: list) -> tuple[float, float]:
        """Held-out agreement with the teacher's moves and value MSE."""
        net = self.model
        net.eval()
        correct = 0
        vls = []
        for i in range(0, len(test), self.args.mb):
            part = test[i:i + self.args.mb]
            b = M.collate([x[0] for x in part], self.device)
            with torch.autocast(self.device.type, dtype=torch.bfloat16, enabled=self.cuda):
                logits, v = net(b)
            pred = logits.argmax(-1).cpu().numpy()
            correct += sum(int(p == x[1]) for p, x in zip(pred, part, strict=True))
            z = torch.tensor([x[2] for x in part], device=self.device)
            vls.append(F.mse_loss(v, z).item())
        net.train()
        return round(correct / max(len(test), 1), 4), round(float(np.mean(vls or [0])), 4)

    # ------------------------------------------------------------------ eval

    def start_eval(self, tag: str, opponents: list[str] | None = None,
                   seat: str | None = None, deals: int | None = None,
                   seed0: int = EVAL_SEED0) -> None:
        a = self.args
        self.models["eval"] = self._copy(self.model)
        self.eval_rows = []
        self.eval_meta = {"tag": tag, "it": self.it, "t0": time.time()}
        me = seat or a.eval_seat
        self.eval_meta["eval_seat"] = me
        search = self.search_opts()
        for opp in opponents or a.eval_opponents.split(","):
            for i in range(deals or a.eval_deals):
                seed = seed0 + i
                mode = "coherent"  # random piles are not the game being learned (190 §3.1)
                for a_seat in (0, 1):
                    seats = [me, opp] if a_seat == 0 else [opp, me]
                    job = self._job("eval", seed, seats, [True, True], [False, False], mode)
                    job["opp"] = opp
                    job["a_seat"] = a_seat
                    job["search"] = search
                    job["set_code"] = a.eval_set
                    self.eval_jobs.append(job)
                    self.eval_pending.add(job["gid"])

    def eval_summary(self) -> dict:
        by_opp: dict[str, list] = defaultdict(list)
        search_stats: Counter = Counter()
        for r in self.eval_rows:
            by_opp[r.get("opp") or "?"].append(r)
            for st in r.get("search") or []:
                if st:
                    search_stats.update(st)
        out = {"event": "eval", **self.eval_meta, "secs": round(time.time() - self.eval_meta["t0"], 1)}
        for opp, rows in by_opp.items():
            pairs: dict[tuple, list] = defaultdict(list)
            for r in rows:
                pairs[(r["seed"], r["deck_mode"])].append(r)
            score = n = 0.0
            voids = 0
            by_mode: dict[str, list] = defaultdict(lambda: [0.0, 0])
            turns = []
            deal_scores = []
            for prs in pairs.values():
                if any(p["outcome"].startswith("void") or p.get("leaky", 0) for p in prs):
                    voids += len(prs)
                    continue
                deal = 0.0
                for p in prs:
                    a_seat = p["a_seat"]
                    if p["outcome"] == "win":
                        s = 1.0 if p["winner"] == a_seat else 0.0
                    else:
                        s = 0.5
                    score += s
                    deal += s
                    n += 1
                    by_mode[p["deck_mode"]][0] += s
                    by_mode[p["deck_mode"]][1] += 1
                    turns.append(p["turns"])
                deal_scores.append(deal / len(prs))
            out[opp] = {"score": round(score / max(n, 1), 4), "n": int(n),
                        "ci95": deal_interval(deal_scores), "voids": voids,
                        "by_mode": {m: round(v[0] / max(v[1], 1), 4) for m, v in by_mode.items()},
                        "turns": round(float(np.mean(turns)) if turns else 0.0, 1)}
        if search_stats:
            out["search"] = dict(search_stats)
        return out

    def save(self, name: str, extra: dict | None = None) -> None:
        M.save(str(self.run / name), self.model, self.table,
               {"it": self.it, **(extra or {})})

    # ------------------------------------------------------------------ main

    def throughput(self, t0: float, games0: int, dec0: int) -> dict:
        dt = max(time.time() - t0, 1e-6)
        games = self.counts["train:games"] + self.counts["eval:games"] + self.counts["bc:games"]
        return {"games_s": round((games - games0) / dt, 2),
                "dec_s": round((self.infer_items - dec0) / dt, 1)}

    def capture(self) -> None:
        """--capture: play that many games, half the --init network against itself and half
        against the heuristic (seats drawn at random), dealt like training games
        (--coherent-share, --mix-sets). Their seats record the opponent simulator's data
        (actor.Capture) into <run>/capture: views_<k>.npz, truth_<k>.npz and the card table."""
        a = self.args
        if a.pool != S.POOL:
            raise ValueError(f"the simulator's candidates are the {S.POOL!r} pool, not {a.pool!r}")
        (self.run / "capture").mkdir(exist_ok=True)
        (self.run / "capture" / "table.json").write_text(json.dumps(self.table.to_json()))
        self.captured, self.shards = [], 0
        for i in range(a.capture):
            opp = "learner" if i % 2 else "heuristic"
            seats = ["learner", opp] if self.rng.random() < 0.5 else [opp, "learner"]
            job = self._job("capture", CAPTURE_SEED0 + 1_000_000 * a.seed + i, seats,
                            [False, False], [False, False], self._deck_mode())
            self._mix(job)
            job["capture"] = a.capture_p
            self.eval_jobs.append(job)
            self.eval_pending.add(job["gid"])
        self.serve(lambda: not self.eval_pending)
        self._save_capture()

    def _save_capture(self) -> None:
        games, self.captured = self.captured, []
        rows = [(r, v, t) for r in games for v, t in zip(r["views"], r["truth"], strict=True)]
        if rows:
            S.Data.from_records(
                [v for _, v, _ in rows], [t for _, _, t in rows],
                [r["set_code"] for r, _, _ in rows], self.table,
                seed=np.array([r["seed"] for r, _, _ in rows]),
                net=np.array([[is_net(r["seats"][v["seat"]]), is_net(r["seats"][1 - v["seat"]])]
                              for r, v, _ in rows])).save(self.run / "capture", self.shards)
            self.shards += 1
        self.log({"event": "capture", "shards": self.shards, "games": len(games),
                  "positions": len(rows), "counts": dict(self.counts)})

    def eval_only(self) -> None:
        """Evaluate --init (as the "eval" seat, optionally with search) and exit."""
        a = self.args
        if a.opp_ckpt:
            opp, _, _ = M.load(a.opp_ckpt, self.device)
            self.models["snap:opp"] = opp.eval()
        self.start_eval("eval-only")
        self.models["eval"] = self.model  # start_eval made a frozen copy; same weights
        self.phase = "idle"
        self.serve(lambda: not self.eval_pending)
        self.log(self.eval_summary())

    # ------------------------------------------------------------------ curriculum

    def freeze(self, src: torch.nn.Module) -> str:
        """A new frozen version from ``src``'s weights (saved as <run>/v<k>.pt)."""
        name = f"v{len(self.versions)}"
        net = self._copy(src)
        self.models[name] = net
        self.versions.append(name)
        M.save(str(self.run / f"{name}.pt"), net, self.table, {"it": self.it, "stage": self.stage})
        self.log({"event": "freeze", "version": name, "it": self.it, "stage": self.stage})
        return name

    def queue_eval(self, kind: str, tag: str, seat: str, opponents: list[str],
                   deals: int) -> None:
        seed0 = EVAL_SEED0
        if kind in ("gate", "teacher"):  # both decide a freeze: never on the ladder's deals
            seed0 = GATE_SEED0 + 1000 * self.n_gates
            self.n_gates += 1
        self.eval_queue.append((kind, tag, seat, opponents, deals, seed0))

    def _eval_rows_as_games(self, player: str) -> list[tuple[str, str, float]]:
        """The finished evaluation's games as (player, opponent, score), voided pairs dropped."""
        pairs: dict[tuple, list] = defaultdict(list)
        for r in self.eval_rows:
            pairs[(r.get("opp"), r["seed"], r["deck_mode"])].append(r)
        out = []
        for prs in pairs.values():
            if any(p["outcome"].startswith("void") or p.get("leaky", 0) for p in prs):
                continue
            for p in prs:
                sc = 0.5 if p["outcome"] != "win" else (1.0 if p["winner"] == p["a_seat"] else 0.0)
                out.append((player, p["opp"], sc))
        return out

    def _log_elo(self) -> None:
        elo = fit_elo(self.elo_games, anchor="random")
        if elo:
            self.log({"event": "elo", "it": self.it, "ratings": elo,
                      "games": len(self.elo_games), "versions": list(self.versions)})

    def _ladder_opponents(self, name: str) -> list[str]:
        """A new version's rating games: random, the heuristic and its predecessor, on the
        fixed ladder deals. Gate games never enter the ratings: a freeze is selected on them
        (the first of many noisy re-tests to clear the bar), so they overstate the step."""
        prev = self.versions[self.versions.index(name) - 1] if self.versions.index(name) else None
        return ["random", "heuristic"] + ([prev] if prev else [])

    def _eval_tick(self) -> None:
        """Called once per iteration: finish a completed evaluation, start the next one."""
        a = self.args
        if self.eval_meta and not self.eval_pending and self.eval_rows:
            ev = self.eval_summary()
            kind, seat, opps = self.eval_kind["kind"], self.eval_kind["seat"], self.eval_kind["opps"]
            ev["kind"] = kind
            self.log(ev)
            if kind == "ladder":
                self.elo_games += self._eval_rows_as_games(seat)
                self._log_elo()
            elif kind == "teacher":
                res = ev.get("heuristic", {})
                passed = res.get("score", 0) >= a.teacher_gate and res.get("ci95", [0])[0] > 0.5
                self.log({"event": "teacher_gate", "it": self.it, "score": res.get("score"),
                          "ci95": res.get("ci95"), "passed": passed})
                if passed or self.it >= a.teacher_iters:
                    name = self.freeze(self.models["eval"])
                    self.stage = "selfplay"
                    self.log({"event": "stage", "stage": "selfplay", "it": self.it,
                              "frozen": name, "forced": not passed})
                    self.queue_eval("ladder", f"ladder:{name}", name,
                                    self._ladder_opponents(name), a.ladder_deals)
            elif kind == "gate":
                res = ev.get(opps[0], {})
                passed = res.get("score", 0) >= a.gate_score and res.get("ci95", [0])[0] > 0.5
                self.log({"event": "gate", "it": self.it, "vs": opps[0], "score": res.get("score"),
                          "ci95": res.get("ci95"), "passed": passed})
                if passed:
                    name = self.freeze(self.models["eval"])
                    self.queue_eval("ladder", f"ladder:{name}", name,
                                    self._ladder_opponents(name), a.ladder_deals)
                    self.save("best.pt", {"version": name, "gate": res})
            self.eval_meta = {}
            self.eval_kind = {}
        if not self.eval_pending and not self.eval_meta and self.eval_queue:
            kind, tag, seat, opps, deals, *rest = self.eval_queue.popleft()
            self.eval_kind = {"kind": kind, "seat": seat, "opps": opps}
            self.start_eval(tag, opponents=opps, seat=seat, deals=deals,
                            seed0=rest[0] if rest else EVAL_SEED0)

    def curriculum(self) -> None:
        """Teacher inter-play (BC) -> PPO against the teacher -> PPO against a frozen version of
        itself, re-frozen whenever it beats that version on the gate deals."""
        a = self.args
        start = 1
        if a.resume:  # the optimiser moments are not saved: the trainer restarts them
            st = self.load_state(a.resume)
            start = st["it"] + 1
            self.log({"event": "resume", "from": a.resume, "it": st["it"], "stage": self.stage,
                      "versions": self.versions})
        else:
            v0 = self.freeze(self.model)  # the starting policy (BC or --init)
            self.queue_eval("ladder", "ladder:heuristic", "heuristic", ["random"],
                            a.ladder_deals)
            self.queue_eval("ladder", f"ladder:{v0}", v0, ["random", "heuristic"],
                            a.ladder_deals)
            self.stage = "teacher" if a.teacher_iters > 0 else "selfplay"
        self.phase = "ppo"
        for self.it in range(start, a.iters + 1):
            t0, d0 = time.time(), self.infer_items
            g0 = sum(self.counts[k] for k in ("train:games", "eval:games", "bc:games"))
            self.serve(lambda: len(self.buffer) >= a.steps)
            t1 = time.time()
            st = self.update()
            # over the whole iteration: the workers also play while the update runs
            tp = self.throughput(t0, g0, d0)
            res, self.train_results = self.train_results, []
            wr: dict[str, list] = defaultdict(list)
            for opp, z, *_ in res:
                wr["frozen" if opp == (self.versions[-1] if self.versions else "") else
                   ("past" if opp.startswith("v") else opp)].append(z)
            by_set: dict[str, list] = defaultdict(list)
            for row in res:
                by_set[row[3]].append(row[1])
            self.log({"event": "iter", "it": self.it, "stage": self.stage, **st, **tp,
                      "upd_s": round(time.time() - t1, 1), "collect_s": round(t1 - t0, 1),
                      # with --mix-sets: the training-game win rate per dealing set
                      **({"win_set": {k: round(float(np.mean([z > 0 for z in v])), 3)
                                      for k, v in by_set.items()}} if len(by_set) > 1 else {}),
                      # training-game win rate per opponent group (sampled play, not the eval)
                      "win": {k: round(float(np.mean([z > 0 for z in v])), 3)
                              for k, v in wr.items()},
                      "frozen": self.versions[-1] if self.versions else None,
                      "turns": round(float(np.mean([x[2] for x in res])) if res else 0, 1),
                      "games": len(res), "mem_gib": round(mem_available_gib(), 1),
                      "mem_min_gib": round(getattr(self, "mem_min", float("nan")), 1),
                      "infer_bs": round(self.infer_items / max(self.infer_batches, 1), 1),
                      "voids": self.counts["train:void"], "overflow": self.counts["overflow"],
                      "throttled": self.counts["throttled"]})
            self.mem_min = float("inf")
            queued = {q[0] for q in self.eval_queue} | {self.eval_kind.get("kind")}
            if self.stage == "teacher" and self.it % a.eval_every == 0 and "teacher" not in queued:
                self.queue_eval("teacher", f"teacher:it{self.it}", "eval", ["heuristic"],
                                a.eval_deals)
            if self.stage == "selfplay" and self.it % a.gate_every == 0 and "gate" not in queued:
                self.queue_eval("gate", f"gate:it{self.it}", "eval", [self.versions[-1]],
                                a.gate_deals)
            self._eval_tick()
            if self.it % a.save_every == 0:
                self.save("last.pt", {"versions": self.versions, "stage": self.stage})
                self.save_state()
        self.save("last.pt", {"versions": self.versions, "stage": self.stage})
        self.save_state()

    def save_state(self) -> None:
        """Everything --resume needs besides the checkpoints: the stage, the version list and the
        rating games (written atomically with every save of last.pt)."""
        import pickle

        state = {"it": self.it, "stage": self.stage, "versions": self.versions,
                 "elo_games": self.elo_games, "pool": self.args.pool,
                 # a resume continues the job ids (training seeds), the opponent draws, the gate
                 # deal blocks and any queued evaluation (a freeze's ladder)
                 "gid": self.gid, "rng": self.rng.getstate(), "n_gates": self.n_gates,
                 "eval_queue": list(self.eval_queue)}
        tmp = self.run / "state.pkl.tmp"
        with tmp.open("wb") as fh:
            pickle.dump(state, fh, protocol=pickle.HIGHEST_PROTOCOL)
        tmp.replace(self.run / "state.pkl")

    def load_state(self, run_dir: str) -> dict:
        """Restore a run saved by save_state: learner weights (last.pt), every frozen version
        (v<k>.pt), stage, ratings, job ids, opponent draws and queued evaluations."""
        import pickle

        src = Path(run_dir)
        with (src / "state.pkl").open("rb") as fh:
            st = pickle.load(fh)
        # A run deals from one pool: its ratings and evaluations compare games dealt from it.
        # State files from before --pool existed were written by runs that dealt castable cards.
        pool = st.get("pool", "castable")
        if pool != self.args.pool:
            raise ValueError(f"--resume {run_dir}: that run dealt from the {pool!r} pool, not "
                             f"{self.args.pool!r}; resume it with --pool {pool}, or start a new "
                             f"run from its weights with --init {src / 'last.pt'}")
        model, _, _ = M.load(str(src / "last.pt"), self.device)
        self.model.load_state_dict(model.state_dict())
        self.weights_changed(self.model)
        for name in st["versions"]:
            net, _, _ = M.load(str(src / f"{name}.pt"), self.device)
            self.models[name] = net.eval()
            if src != self.run:
                M.save(str(self.run / f"{name}.pt"), net, self.table, {"resumed_from": run_dir})
        self.versions = list(st["versions"])
        self.stage = st["stage"]
        self.elo_games = list(st["elo_games"])
        self.gid = st.get("gid", self.gid)
        if "rng" in st:
            self.rng.setstate(st["rng"])
        self.n_gates = st.get("n_gates", 0)
        self.eval_queue.extend(st.get("eval_queue", []))
        return st

    def bc_phase(self) -> None:
        """Teacher inter-play: heuristic-vs-heuristic games, then behaviour cloning."""
        a = self.args
        self.phase = "bc"
        self.bc_target = a.bc_games
        t0 = time.time()
        last = 0

        def bc_done() -> bool:
            nonlocal last
            if self.bc_done - last >= 2000:
                last = self.bc_done
                self.log({"event": "bc_gen", "games": self.bc_done, "samples": len(self.bc),
                          "secs": round(time.time() - t0, 1),
                          "mem_gib": round(mem_available_gib(), 1)})
            return self.bc_done >= self.bc_target

        self.serve(bc_done)
        self.phase = "idle"
        self.log({"event": "bc_gen_done", "games": self.bc_done, "samples": len(self.bc),
                  "secs": round(time.time() - t0, 1), "counts": dict(self.counts)})
        self.bc_train()
        self.save("bc.pt")

    def main(self) -> None:
        a = self.args
        # SIGTERM as an exception, so the finally below stops the trainer and the workers (the
        # default action kills the learner at once and orphans its trainer process)
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
        try:
            if a.eval_only:
                self.eval_only()
                return
            if a.capture:
                self.capture()
                return
            # teacher inter-play only for a network trained from scratch; a resume restores
            # the network from its run instead
            if a.bc_games > 0 and not (a.init or a.resume):
                self.bc_phase()
            self.curriculum()
        finally:
            self.stop_workers()


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--run", required=True)
    p.add_argument("--init", default="")
    p.add_argument("--device", default="auto")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--slots", type=int, default=8)
    p.add_argument("--groups", type=int, default=2,
                   help="pipelined slot groups per worker (more hide more round-trip latency)")
    # model
    p.add_argument("--d", type=int, default=256)
    p.add_argument("--layers", type=int, default=6)
    p.add_argument("--heads", type=int, default=8)
    p.add_argument("--ff", type=int, default=1024)
    p.add_argument("--name-dropout", type=float, default=0.1)
    # BC
    p.add_argument("--bc-games", type=int, default=0)
    p.add_argument("--bc-epochs", type=int, default=4)
    p.add_argument("--bc-lr", type=float, default=1e-3)
    p.add_argument("--bc-holdout", type=float, default=0.03)
    p.add_argument("--bc-vcoef", type=float, default=0.25)
    # PPO
    p.add_argument("--iters", type=int, default=100)
    p.add_argument("--steps", type=int, default=65536, help="learner decisions per iteration")
    p.add_argument("--mb", type=int, default=2048)
    p.add_argument("--tok-budget", type=int, default=65536,
                   help="max padded tokens per training minibatch (bounds activation memory)")
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--wd", type=float, default=0.01)
    p.add_argument("--gamma", type=float, default=1.0)
    p.add_argument("--lam", type=float, default=0.95)
    p.add_argument("--clip", type=float, default=0.2)
    p.add_argument("--vclip", type=float, default=0.5)
    p.add_argument("--vcoef", type=float, default=0.5)
    p.add_argument("--ent", type=float, default=0.01)
    p.add_argument("--max-grad", type=float, default=1.0)
    p.add_argument("--target-kl", type=float, default=0.03)
    p.add_argument("--draw-reward", type=float, default=-1.0)
    # opponents
    p.add_argument("--p-heuristic", type=float, default=0.25)
    p.add_argument("--coherent-share", type=float, default=0.5)
    # eval
    p.add_argument("--eval-every", type=int, default=10)
    p.add_argument("--eval-deals", type=int, default=200)
    p.add_argument("--eval-opponents", default="heuristic")
    p.add_argument("--eval-seat", default="eval", help="'eval' or 'eval+search'")
    p.add_argument("--eval-only", action="store_true", help="evaluate --init and exit")
    p.add_argument("--capture", type=int, default=0,
                   help="play this many games recording the opponent simulator's data, and exit")
    p.add_argument("--capture-p", type=float, default=0.4,
                   help="the share of each seat's decisions a capture game records")
    p.add_argument("--opp-ckpt", default="", help="eval-only: checkpoint to play as 'snap:opp'")
    # curriculum (teacher inter-play -> vs teacher -> gated frozen self-play)
    p.add_argument("--refresh-table", action="store_true",
                   help="rebuild the --init card table's rows from the current compile (after "
                        "an engine/compiler change re-compiled cards); new components learnable")
    p.add_argument("--extend-sets", default="",
                   help="comma list of sets whose castable cards join the card table (names "
                        "unknown, components in the trained vocabulary)")
    p.add_argument("--eval-set", default="M21", help="the set evaluation decks are dealt from")
    p.add_argument("--pool", default="verified", choices=("verified", "compiled", "castable"),
                   help="the cards every game deals from (training, mixed sets, evaluation; "
                        "games.compile_supply): 'verified' = whose current compiled tree passed "
                        "play-time verification; 'compiled' = whole text compiled; 'castable' "
                        "also deals partly parsed cards with the rest of their text missing")
    p.add_argument("--mix-sets", default="",
                   help="comma list of sets some training games are dealt from (must also be "
                        "in --extend-sets)")
    p.add_argument("--mix-share", type=float, default=0.25,
                   help="share of training games dealt from --mix-sets")
    p.add_argument("--mask-names", action="store_true",
                   help="the --init network reads every card name as the unknown card")
    p.add_argument("--resume", default="",
                   help="continue the run saved in this directory (state.pkl, last.pt, "
                        "v<k>.pt)")
    p.add_argument("--teacher-iters", type=int, default=60,
                   help="max PPO iterations against the heuristic before frozen self-play")
    p.add_argument("--teacher-gate", type=float, default=0.65,
                   help="leave the teacher stage once the learner scores this vs the heuristic")
    p.add_argument("--gate-every", type=int, default=5)
    p.add_argument("--gate-deals", type=int, default=200)
    p.add_argument("--gate-score", type=float, default=0.55,
                   help="re-freeze when the learner scores this vs the frozen version "
                        "(and the 95%% interval is above 0.5)")
    p.add_argument("--ladder-deals", type=int, default=100)
    p.add_argument("--p-past", type=float, default=0.1, help="selfplay games vs older versions")
    p.add_argument("--search-blocks", action="store_true",
                   help="searching seats also plan their blocks at the pre-blocks boundary")
    p.add_argument("--search-k", type=int, default=4, help="options simulated per searched ask")
    p.add_argument("--search-d", type=int, default=2, help="sampled worlds per option")
    p.add_argument("--search-skip-p", type=float, default=0.97,
                   help="no search when the network's top option has at least this probability")
    p.add_argument("--save-every", type=int, default=5)
    p.add_argument("--progress-every", type=float, default=300.0,
                   help="seconds between progress events while serving (0: off)")
    p.add_argument("--serve-wait", type=float, default=2.0,
                   help="ms to gather requests into one inference call")
    p.add_argument("--bucket-ratio", type=float, default=1.4,
                   help="new length bucket when a request is this much longer than its shortest")
    p.add_argument("--bucket-min", type=int, default=8, help="minimum requests per length bucket")
    p.add_argument("--infer-bf16", action="store_true",
                   help="answer inference from bf16 copies of the models (1.6-1.9x faster)")
    p.add_argument("--mem-floor-gib", type=float, default=8.0,
                   help="stop the run (emergency checkpoint) below this much MemAvailable")
    args = p.parse_args(argv)
    needs_init = [f for f in ("refresh_table", "extend_sets", "mask_names") if getattr(args, f)]
    if needs_init and not args.init:  # they act on the --init checkpoint; never ignore them
        p.error(", ".join("--" + f.replace("_", "-") for f in needs_init) + " require --init")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    Learner(args).main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
