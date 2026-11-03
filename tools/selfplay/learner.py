"""The learner: GPU inference server for the workers, BC warm start, PPO self-play, evaluation.

Run::

    .venv/bin/python -m tools.selfplay.learner --run runs/selfplay/NAME --workers 18 \
        --bc-games 20000 --iters 400

Phases:
1. BC (skipped with --init): heuristic-vs-heuristic games record (features, action) for both
   seats; the network learns the action (cross-entropy) and the outcome (value MSE).
2. PPO: workers play the learner against itself, frozen snapshots of itself (the league) and
   the heuristic. Every learner decision is recorded with its log-probability and value; when
   a game ends its seats get +1 (win), -1 (loss), ``--draw-reward`` (turn cap or stall) or 0
   (both lose at once), and GAE turns that into per-decision advantages.
3. Evaluation (every --eval-every iterations): a frozen copy of the learner plays the heuristic
   greedily on fixed deals, each deal twice with the seats swapped (duplicate format). Score =
   wins + draws/2 over decided-or-drawn games; voided games void their pair.

Every number goes to ``<run>/metrics.jsonl``; checkpoints to ``<run>/*.pt``.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import math
import multiprocessing as mp
import random
import sys
import threading
import time
from collections import Counter, defaultdict, deque
from multiprocessing.connection import wait
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F

from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay.actor import worker_main
from tools.selfplay.ppo import pack_buffer, ppo_train
from tools.selfplay.trainer import trainer_main

EVAL_SEED0 = 900_000
TRAIN_SEED0 = 10_000_000
BC_SEED0 = 5_000_000


def wilson(wins: float, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (round(c - h, 4), round(c + h, 4))


def length_buckets(items: list, ratio: float = 1.4, min_n: int = 8) -> list[list]:
    """Split one model's inference requests into length-sorted buckets, so a batch is not padded
    to its single longest decision (measured: a 128-request batch with one 114-token outlier
    against a mean of 25 took 78 ms as one batch, 43 ms as 5 buckets; no loss without outliers).
    ``items`` are (message index, request index, request); the request's features are req[5]."""
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


class Learner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.run = Path(args.run)
        self.run.mkdir(parents=True, exist_ok=True)
        self.device = torch.device("cuda" if torch.cuda.is_available() and args.device != "cpu"
                                   else "cpu")
        self.cuda = self.device.type == "cuda"
        torch.manual_seed(args.seed)
        np.random.seed(args.seed)
        self.rng = random.Random(args.seed)
        if args.init:
            self.model, self.table, extra = M.load(args.init, self.device)
            self.log({"event": "init", "from": args.init, "extra": extra})
        else:
            from MTG_bot.core.executor.games import get_supply

            supply = get_supply("castable")
            self.table = FT.CardTable.from_records(
                {oid: r.card for oid, r in supply.pool.results.items()})
            self.model = M.build(self.table, d=args.d, layers=args.layers, heads=args.heads,
                                 ff=args.ff, name_dropout=args.name_dropout).to(self.device)
        self.model.eval()
        self.models: dict[str, torch.nn.Module] = {"learner": self.model}
        if args.rollout_init:
            # A small fast network plays the moves inside search simulations (the big one picks
            # the candidates and scores the leaves); trained on the same labels each generation.
            rollout, rtable, _ = M.load(args.rollout_init, self.device)
            if rtable.oracle_ids != self.table.oracle_ids:
                raise ValueError("--rollout-init: card table differs from the learner's")
            self.models["rollout"] = rollout.eval()
        self.infer_stream = None
        self.trainer = None
        self.tconn = None
        self.sent_anchor: str | None = None
        if args.trainer_proc and args.async_update:
            raise ValueError("--trainer-proc and --async-update are alternatives")
        if args.async_update:
            # Workers keep playing on this copy while the GPU trains self.model (sync_actor).
            self.actor = self._copy(self.model)
            self.models["learner"] = self.actor
            # Inference stays on the default stream: with its own stream, concurrent training
            # and inference kernels hit a device-side assert after ~5 iterations that never
            # reproduced with CUDA_LAUNCH_BLOCKING=1 (2026-11-03). One stream serialises the GPU
            # work; the gain kept is that workers keep playing while the update runs.
        self.snaps: list[str] = []
        self.opt = torch.optim.AdamW(self.model.parameters(), lr=args.lr, betas=(0.9, 0.99),
                                     eps=1e-6, weight_decay=args.wd)
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
        self.bc_seats = ["heuristic", "heuristic"]
        self.exit_opps: list[str] = []
        self.gen_search: Counter = Counter()  # search stats of the current ExIt generation
        self.stage = ""  # curriculum: "teacher" | "selfplay"
        self.versions: list[str] = []
        self.elo_games: list[tuple[str, str, float]] = []
        self.eval_queue: deque = deque()
        self.eval_kind: dict = {}
        self.bc_seed0 = BC_SEED0
        self.it = 0
        self.counts: Counter = Counter()
        self.train_results: list = []
        self.infer_batches = 0
        self.infer_items = 0
        self.infer_time = 0.0
        self._mem_checked = 0.0
        self._start_workers()

    def _copy(self, src: torch.nn.Module) -> torch.nn.Module:
        cfg = {k: v for k, v in self.model.config.items() if k not in ("n_cards", "n_ir")}
        net = M.build(self.table, **cfg).to(self.device)
        net.load_state_dict(src.state_dict())
        net.eval()
        if self.cuda:
            torch.cuda.synchronize()  # the copy is complete before any stream reads it
        return net

    def sync_actor(self) -> None:
        if self.args.async_update:
            self.actor.load_state_dict(self.model.state_dict())
            if self.cuda:
                torch.cuda.synchronize()

    def _update_remote(self) -> dict:
        """--trainer-proc: hand the batch to the trainer process and keep serving the workers
        on the current weights until the new ones come back."""
        a = self.args
        if self.trainer is None:
            ctx = mp.get_context("spawn")
            self.tconn, child = ctx.Pipe(duplex=True)
            ckpt = {"config": self.model.config, "table": self.table.to_json(),
                    "state": {k: v.detach().cpu() for k, v in self.model.state_dict().items()}}
            self.trainer = ctx.Process(target=trainer_main, args=(child, ckpt, vars(a)),
                                       daemon=True)
            self.trainer.start()
        anchor = self.versions[-1] if self.versions and a.kl_anchor > 0 else None
        if anchor is not None and anchor != self.sent_anchor:
            state = {k: v.detach().cpu() for k, v in self.models[anchor].state_dict().items()}
            self.tconn.send(("anchor", anchor, state))
            self.sent_anchor = anchor
        buf, self.buffer = self.buffer, []
        t0 = time.perf_counter()
        self.tconn.send(("update", pack_buffer(buf), anchor))
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
        if self.cuda:
            torch.cuda.synchronize()
        stats["send_s"] = round(send_s, 2)
        stats["overlap_steps"] = len(self.buffer)
        return stats

    def update(self) -> dict:
        """One PPO update. With --async-update it runs in a thread while this thread keeps
        serving the workers on the actor copy (they otherwise sit idle for the whole update);
        the next batch then starts with data from the previous weights, which the PPO ratio
        and clipping account for."""
        if self.args.trainer_proc:
            return self._update_remote()
        if not self.args.async_update:
            return self.ppo_update()
        buf, self.buffer = self.buffer, []
        out: dict = {}

        def work() -> None:
            try:
                out.update(self.ppo_update(buf))
            except BaseException as error:  # noqa: BLE001 - re-raised in the main thread
                out["error"] = error

        th = threading.Thread(target=work, daemon=True)
        th.start()
        self.serve(lambda: not th.is_alive())
        th.join()
        if "error" in out:
            raise out["error"]
        self.sync_actor()
        out["overlap_steps"] = len(self.buffer)
        return out

    # ------------------------------------------------------------------ memory

    def check_memory(self) -> None:
        """Unified memory: host RAM and GPU memory are one pool, and exhausting it froze this
        machine twice (INCIDENT_REPORT_2026-11-02). Below ``--mem-floor-gib`` the run saves an
        emergency checkpoint, stops its own workers and exits. A safety rail, not a tuning knob."""
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
            p = ctx.Process(target=worker_main, args=(wid, b, self.args.slots, table_json),
                            daemon=True)
            p.start()
            self.conns.append(a)
            self.procs.append(p)
        self.wid_of = {id(c): i for i, c in enumerate(self.conns)}

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
                "record": record, "deck_mode": deck_mode}

    def _deck_mode(self) -> str:
        p = self.args.coherent_share
        return "coherent" if self.rng.random() < p else "stress"

    def next_job(self) -> dict | None:
        if self.eval_jobs:
            return self.eval_jobs.popleft()
        if self.phase == "bc" and self.bc_issued < self.bc_target:
            self.bc_issued += 1
            seats = list(self.bc_seats)
            if self.stage and seats[0].endswith("+search"):
                seats[1] = self.curriculum_opponent()
            elif self.exit_opps:
                seats[1] = self.rng.choice(self.exit_opps)
            if seats[0] != seats[1] and self.rng.random() < 0.5:
                seats.reverse()  # the recorded seat plays both sides of the table
            # what is trained on: the searching seats if any (ExIt never trains on the
            # opponent's or the unsearched network's moves), else every heuristic seat (BC)
            record = [s.endswith("+search") for s in seats]
            if not any(record):
                record = [s == "heuristic" for s in seats]
            job = self._job("bc", self.bc_seed0 + self.bc_issued, seats, [True, True], record,
                            self._deck_mode())
            job["search"] = self.search_opts()
            return job
        if self.phase == "ppo":
            return self.train_job()
        return None

    def train_job(self) -> dict:
        a = self.args
        if self.stage:
            return self.curriculum_job()
        r = self.rng.random()
        seed = TRAIN_SEED0 + self.gid + 1
        if r < a.p_self:
            return self._job("train", seed, ["learner", "learner"], [False, False],
                             [True, True], self._deck_mode())
        if r < a.p_self + a.p_heuristic:
            opp = "heuristic"
        elif r < a.p_self + a.p_heuristic + a.p_random:
            opp = "random"
        elif self.snaps:
            opp = self.rng.choice(self.snaps[-a.max_snaps:])
        else:
            opp = "heuristic"
        seat = self.rng.randrange(2)
        seats = ["learner", opp] if seat == 0 else [opp, "learner"]
        record = [s == "learner" for s in seats]
        return self._job("train", seed, seats, [False, False], record, self._deck_mode())

    def search_opts(self) -> dict:
        a = self.args
        return {"k": a.search_k, "d": a.search_d, "skip_p": a.search_skip_p,
                "rollout": "rollout" if "rollout" in self.models else None}

    def curriculum_opponent(self) -> str:
        a = self.args
        if self.stage == "teacher":
            return "heuristic"
        r = self.rng.random()
        if r < a.p_heuristic:
            return "heuristic"
        if r < a.p_heuristic + a.p_past and len(self.versions) > 1:
            return self.rng.choice(self.versions[:-1])
        return self.versions[-1]

    def curriculum_job(self) -> dict:
        """Stage "teacher": the learner plays the heuristic. Stage "selfplay": the learner plays
        the newest frozen version (most games), older versions and the heuristic (a few, so it
        does not forget how to beat them). Only the learner's seat is trained on."""
        a = self.args
        seed = TRAIN_SEED0 + self.gid + 1
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
        return self._job("train", seed, seats, [False, False], [x == "learner" for x in seats],
                         self._deck_mode())

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

    def serve(self, until: Any, max_wait: float = 0.002) -> None:
        """Answer workers until ``until()`` is true."""
        while not until():
            self.check_memory()
            self._flush_needs()
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
        t0 = time.perf_counter()
        answers = [[0] * len(reqs) for (_, _, reqs) in msgs]
        by_key: dict[str, list] = defaultdict(list)
        for mi, (_, _, reqs) in enumerate(msgs):
            for ri, req in enumerate(reqs):
                by_key[req[2]].append((mi, ri, req))
        stream_ctx = (torch.cuda.stream(self.infer_stream) if self.infer_stream is not None
                      else contextlib.nullcontext())
        groups = []
        for key, items in by_key.items():
            for bucket in length_buckets(items):
                groups.append((key, bucket))
        for key, items in groups:
            model = self.models[key]
            with stream_ctx:
                b = M.collate([it[2][5] for it in items], self.device)
                with torch.autocast(self.device.type, dtype=torch.bfloat16, enabled=self.cuda):
                    logits, value = model(b)
            with stream_ctx:
                greedy = torch.tensor([bool(it[2][3]) for it in items], device=self.device)
                probs = torch.softmax(logits, -1)
                sampled = torch.multinomial(probs, 1).squeeze(1)
                act = torch.where(greedy, logits.argmax(-1), sampled)
                logp = torch.log_softmax(logits, -1).gather(1, act[:, None]).squeeze(1)
                # read back on the SAME stream: a copy on the default stream would not wait for
                # these kernels (with --async-update that race corrupted recorded logps -> NaN)
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
        self.infer_time += time.perf_counter() - t0

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
                                              "outcome", "winner", "turns", "leaky", "crash")}
                row["tag"] = self.eval_meta.get("tag")
                with (self.run / "eval_rows.jsonl").open("a") as fh:
                    fh.write(json.dumps(row) + "\n")
            elif kind == "bc":
                self.bc_done += 1
                for st in r.get("search") or []:
                    if st:
                        self.gen_search.update(st)
                if not void:
                    seats = r.get("seats") or []
                    for seat, spec in enumerate(seats):
                        if spec.endswith("+search") and not seats[1 - seat].endswith("+search"):
                            self.train_results.append((seats[1 - seat], self.reward(
                                r["outcome"], r["winner"], seat), r["turns"]))
                if not void and r.get("bc"):
                    for seat in (0, 1):
                        z = self.reward(r["outcome"], r["winner"], seat)
                        for feats, idx in r["bc"][seat] or []:
                            self.bc.append((feats, idx, z, r["gid"]))

    def _finish_train(self, r: dict, void: bool) -> None:
        a = self.args
        self.counts["overflow"] += sum(r.get("overflow", [0, 0]))
        for seat in (0, 1):
            steps = self.traj.pop((r["gid"], seat), None)
            if not steps or void:
                continue
            z = self.reward(r["outcome"], r["winner"], seat)
            vals = [s[3] for s in steps]
            n = len(steps)
            adv = [0.0] * n
            last = 0.0
            for t in range(n - 1, -1, -1):
                next_v = vals[t + 1] if t + 1 < n else 0.0
                rew = z if t == n - 1 else 0.0
                delta = rew + a.gamma * next_v - vals[t]
                last = delta + a.gamma * a.lam * last
                adv[t] = last
            for t in range(n):
                f, act, logp, v = steps[t]
                self.buffer.append((f, act, logp, v, adv[t], adv[t] + v))
        if not void:
            seats = r["seats"]
            for seat in (0, 1):
                if seats[seat] == "learner" and seats[1 - seat] != "learner":
                    self.train_results.append((seats[1 - seat], self.reward(
                        r["outcome"], r["winner"], seat), r["turns"]))
            if seats == ["learner", "learner"]:
                self.train_results.append(("self", 0.0, r["turns"]))

    # ------------------------------------------------------------------ PPO

    def _chunks(self, items: list, mb: int, key) -> list[np.ndarray]:
        """Length-sorted minibatches of at most ``mb`` decisions and at most ``--tok-budget``
        padded tokens (decisions x longest sequence). The token cap bounds activation memory,
        which on this machine is system memory: a 1024-decision chunk of the longest
        sequences took ~15 GB and tripped the memory floor (2026-11-03)."""
        lengths = np.array([key(x) for x in items], dtype=np.float64)
        order = np.argsort(lengths + np.random.rand(len(items)) * 4.0)
        budget = self.args.tok_budget
        chunks, cur, cur_max = [], [], 0.0
        for i in order:
            length = lengths[i] + 3.0
            if cur and (len(cur) >= mb or (len(cur) + 1) * max(cur_max, length) > budget):
                chunks.append(np.array(cur))
                cur, cur_max = [], 0.0
            cur.append(i)
            cur_max = max(cur_max, length)
        if cur:
            chunks.append(np.array(cur))
        random.shuffle(chunks)
        return chunks

    def ppo_update(self, buf: list | None = None) -> dict:
        if buf is None:
            buf, self.buffer = self.buffer, []
        payload = pack_buffer(buf)
        del buf
        anchor = self.models.get(self.versions[-1]) if self.versions else None
        return ppo_train(self.model, self.opt, anchor, a=self.args, device=self.device,
                         check=self.check_memory, release=self.release_cache, **payload)

    # ------------------------------------------------------------------ BC

    def bc_train(self, epochs: int | None = None, lr: float | None = None,
                 model: torch.nn.Module | None = None, keep: bool = False,
                 tag: str = "bc") -> dict:
        """Supervised training on self.bc: cross-entropy on the recorded move + value MSE on the
        outcome. ``model`` defaults to the learner; ``keep`` leaves self.bc for another model."""
        a = self.args
        epochs = a.bc_epochs if epochs is None else epochs
        lr = a.bc_lr if lr is None else lr
        net = self.model if model is None else model
        data = self.bc
        gids = sorted({x[3] for x in data})
        hold = set(gids[:: max(2, int(1 / max(a.bc_holdout, 1e-3)))])
        train = [x for x in data if x[3] not in hold]
        test = [x for x in data if x[3] in hold]
        self.log({"event": "bc_data", "model": tag, "samples": len(data), "train": len(train),
                  "test": len(test), "games": len(gids)})
        net.train()
        opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=a.wd)
        steps_total = max(1, epochs * math.ceil(len(train) / a.mb))
        warm = max(1, steps_total // 20)
        sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / warm) * (
            0.05 + 0.95 * 0.5 * (1 + math.cos(math.pi * min(1.0, s / steps_total)))))
        best = None
        for epoch in range(epochs):
            t0 = time.time()
            ls = []
            for ch in self._chunks(train, a.mb, lambda x: x[0]["cards_i"].shape[0]
                                   + x[0]["opts_i"].shape[0]):
                self.check_memory()
                b = M.collate([train[i][0] for i in ch], self.device)
                act = torch.tensor([train[i][1] for i in ch], device=self.device)
                z = torch.tensor([train[i][2] for i in ch], device=self.device)
                with torch.autocast(self.device.type, dtype=torch.bfloat16, enabled=self.cuda):
                    logits, v = net(b)
                loss = F.cross_entropy(logits, act) + a.bc_vcoef * F.mse_loss(v, z)
                opt.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), a.max_grad)
                opt.step()
                sched.step()
                ls.append(loss.item())
            acc, vl = self.bc_eval(test, net)
            row = {"event": "bc_epoch", "model": tag, "epoch": epoch,
                   "loss": round(float(np.mean(ls)), 5),
                   "test_acc": acc, "test_vloss": vl, "secs": round(time.time() - t0, 1)}
            self.log(row)
            best = row
        net.eval()
        if not keep:
            self.bc = []
        self.release_cache()
        return best or {}

    @torch.no_grad()
    def bc_eval(self, test: list, net: torch.nn.Module | None = None) -> tuple[float, float]:
        net = self.model if net is None else net
        net.eval()
        correct = 0
        vls = []
        for i in range(0, len(test), self.args.mb):
            part = test[i:i + self.args.mb]
            b = M.collate([x[0] for x in part], self.device)
            with torch.autocast(self.device.type, dtype=torch.bfloat16, enabled=self.cuda):
                logits, v = net(b)
            pred = logits.argmax(-1).cpu().numpy()
            correct += int(sum(int(p == x[1]) for p, x in zip(pred, part, strict=True)))
            z = torch.tensor([x[2] for x in part], device=self.device)
            vls.append(F.mse_loss(v, z).item())
        net.train()
        return round(correct / max(len(test), 1), 4), round(float(np.mean(vls or [0])), 4)

    # ------------------------------------------------------------------ eval

    def start_eval(self, tag: str, opponents: list[str] | None = None,
                   seat: str | None = None, deals: int | None = None) -> None:
        a = self.args
        self.models["eval"] = self._copy(self.model)
        self.eval_rows = []
        self.eval_meta = {"tag": tag, "it": self.it, "t0": time.time()}
        me = seat or a.eval_seat
        self.eval_meta["eval_seat"] = me
        search = self.search_opts()
        for opp in opponents or a.eval_opponents.split(","):
            for i in range(deals or a.eval_deals):
                seed = EVAL_SEED0 + i
                mode = "stress" if i % 2 == 0 else "coherent"
                for a_seat in (0, 1):
                    seats = [me, opp] if a_seat == 0 else [opp, me]
                    job = self._job("eval", seed, seats, [True, True], [False, False], mode)
                    job["opp"] = opp
                    job["a_seat"] = a_seat
                    job["search"] = search
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
            for prs in pairs.values():
                if any(p["outcome"].startswith("void") or p.get("leaky", 0) for p in prs):
                    voids += len(prs)
                    continue
                for p in prs:
                    a_seat = p["a_seat"]
                    if p["outcome"] == "win":
                        s = 1.0 if p["winner"] == a_seat else 0.0
                    else:
                        s = 0.5
                    score += s
                    n += 1
                    by_mode[p["deck_mode"]][0] += s
                    by_mode[p["deck_mode"]][1] += 1
                    turns.append(p["turns"])
            out[opp] = {"score": round(score / max(n, 1), 4), "n": int(n),
                        "ci95": wilson(score, int(n)), "voids": voids,
                        "by_mode": {m: round(v[0] / max(v[1], 1), 4) for m, v in by_mode.items()},
                        "turns": round(float(np.mean(turns)) if turns else 0.0, 1)}
        if search_stats:
            out["search"] = dict(search_stats)
        return out

    # ------------------------------------------------------------------ league

    def add_snapshot(self) -> str:
        key = f"snap:{self.it}"
        snap = M.build(self.table, **{k: v for k, v in self.model.config.items()
                                      if k not in ("n_cards", "n_ir")}).to(self.device)
        snap.load_state_dict(self.model.state_dict())
        snap.eval()
        self.models[key] = snap
        self.snaps.append(key)
        # keep only max_snaps on the GPU; games in flight against a dropped one finish on
        # the newest snapshot instead
        while len(self.snaps) > self.args.max_snaps:
            old = self.snaps.pop(0)
            self.models[old] = self.models[self.snaps[-1]]
        return key

    def save(self, name: str, extra: dict | None = None) -> None:
        M.save(str(self.run / name), self.model, self.table,
               {"it": self.it, **(extra or {})})

    # ------------------------------------------------------------------ main

    def throughput(self, t0: float, games0: int, dec0: int) -> dict:
        dt = max(time.time() - t0, 1e-6)
        games = self.counts["train:games"] + self.counts["eval:games"] + self.counts["bc:games"]
        return {"games_s": round((games - games0) / dt, 2),
                "dec_s": round((self.infer_items - dec0) / dt, 1)}

    def eval_only(self) -> None:
        """Evaluate --init (as the "eval" seat, optionally with search) and exit."""
        a = self.args
        self.models["eval"] = self.model
        if a.opp_ckpt:
            opp, _, _ = M.load(a.opp_ckpt, self.device)
            self.models["snap:opp"] = opp.eval()
        self.eval_rows = []
        self.eval_meta = {"tag": "eval-only", "it": 0, "t0": time.time(), "init": a.init}
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
        self.eval_queue.append((kind, tag, seat, opponents, deals))

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
                    self.elo_games += self._eval_rows_as_games(name)
                    self.stage = "selfplay"
                    self.log({"event": "stage", "stage": "selfplay", "it": self.it,
                              "frozen": name, "forced": not passed})
                    self.queue_eval("ladder", f"ladder:{name}", name, ["random"], a.ladder_deals)
            elif kind == "gate":
                res = ev.get(opps[0], {})
                passed = res.get("score", 0) >= a.gate_score and res.get("ci95", [0])[0] > 0.5
                self.log({"event": "gate", "it": self.it, "vs": opps[0], "score": res.get("score"),
                          "ci95": res.get("ci95"), "passed": passed})
                if passed:
                    name = self.freeze(self.models["eval"])
                    self.elo_games += self._eval_rows_as_games(name)
                    self.queue_eval("ladder", f"ladder:{name}", name, ["random", "heuristic"],
                                    a.ladder_deals)
                    self.save("best.pt", {"version": name, "gate": res})
            self.eval_meta = {}
            self.eval_kind = {}
        if not self.eval_pending and not self.eval_meta and self.eval_queue:
            kind, tag, seat, opps, deals = self.eval_queue.popleft()
            self.eval_kind = {"kind": kind, "seat": seat, "opps": opps}
            self.start_eval(tag, opponents=opps, seat=seat, deals=deals)

    def curriculum(self) -> None:
        """Teacher inter-play (BC) -> PPO against the teacher -> PPO against a frozen version of
        itself, re-frozen whenever it beats that version on the gate deals."""
        a = self.args
        v0 = self.freeze(self.model)  # the starting policy (BC or --init)
        self.queue_eval("ladder", "ladder:heuristic", "heuristic", ["random"], a.ladder_deals)
        self.queue_eval("ladder", f"ladder:{v0}", v0, ["random", "heuristic"], a.ladder_deals)
        self.stage = "teacher" if a.teacher_iters > 0 else "selfplay"
        self.phase = "ppo"
        for self.it in range(1, a.iters + 1):
            t0, d0 = time.time(), self.infer_items
            g0 = sum(self.counts[k] for k in ("train:games", "eval:games", "bc:games"))
            self.serve(lambda: len(self.buffer) >= a.steps)
            tp = self.throughput(t0, g0, d0)
            t1 = time.time()
            st = self.update()
            res, self.train_results = self.train_results, []
            wr: dict[str, list] = defaultdict(list)
            for opp, z, _ in res:
                wr["frozen" if opp == (self.versions[-1] if self.versions else "") else
                   ("past" if opp.startswith("v") else opp)].append(z)
            self.log({"event": "iter", "it": self.it, "stage": self.stage, **st, **tp,
                      "upd_s": round(time.time() - t1, 1), "collect_s": round(t1 - t0, 1),
                      # training-game win rate per opponent group (sampled play, not the eval)
                      "win": {k: round(float(np.mean([z > 0 for z in v])), 3)
                              for k, v in wr.items()},
                      "frozen": self.versions[-1] if self.versions else None,
                      "turns": round(float(np.mean([x[2] for x in res])) if res else 0, 1),
                      "games": len(res), "mem_gib": round(mem_available_gib(), 1),
                      "mem_min_gib": round(getattr(self, "mem_min", float("nan")), 1),
                      "infer_bs": round(self.infer_items / max(self.infer_batches, 1), 1),
                      "voids": self.counts["train:void"], "overflow": self.counts["overflow"]})
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
        self.save("last.pt", {"versions": self.versions, "stage": self.stage})

    def _drain_evals(self) -> None:
        """Run every queued evaluation to completion (gates may queue ladders)."""
        while True:
            self._eval_tick()
            if not self.eval_pending and not self.eval_meta and not self.eval_queue:
                return
            prev, self.phase = self.phase, "idle"
            self.serve(lambda: not self.eval_pending)
            self.phase = prev

    def curriculum_exit(self) -> None:
        """The same curriculum and gates, with expert iteration as the adaptation step: each
        generation the searching learner plays --exit-games against the stage's opponents
        (teacher stage: the heuristic; selfplay: the newest frozen version, plus --p-past and
        --p-heuristic), the network is trained on the moves the search chose and the outcomes
        (a window of --exit-keep generations), then the stage's gate runs."""
        a = self.args
        v0 = self.freeze(self.model)
        self.queue_eval("ladder", "ladder:heuristic", "heuristic", ["random"], a.ladder_deals)
        self.queue_eval("ladder", f"ladder:{v0}", v0, ["random", "heuristic"], a.ladder_deals)
        self._drain_evals()
        self.stage = "teacher" if a.teacher_iters > 0 else "selfplay"
        self.bc_seats = [a.exit_seat, a.exit_seat]
        window: deque = deque(maxlen=a.exit_keep)
        for self.it in range(1, a.iters + 1):
            t0 = time.time()
            self.bc, self.phase = [], "bc"
            self.bc_target, self.bc_issued, self.bc_done = a.exit_games, 0, 0
            self.bc_seed0 = BC_SEED0 + 1_000_000 * self.it
            self.serve(lambda: self.bc_done >= self.bc_target)
            self.phase = "idle"
            play_s = time.time() - t0
            window.append(self.bc)
            res, self.train_results = self.train_results, []
            wr: dict[str, list] = defaultdict(list)
            for opp, z, _ in res:
                wr["frozen" if opp == self.versions[-1] else
                   ("past" if opp.startswith("v") else opp)].append(z)
            self.bc = [x for part in window for x in part]
            n_window = len(self.bc)
            t1 = time.time()
            fit = self.bc_train(epochs=a.exit_epochs, lr=a.exit_lr, keep=True)
            rfit: dict = {}
            if "rollout" in self.models:
                rfit = self.bc_train(epochs=a.rollout_epochs, lr=a.rollout_lr,
                                     model=self.models["rollout"], keep=True, tag="rollout")
                M.save(str(self.run / "rollout.pt"), self.models["rollout"], self.table,
                       {"it": self.it})
            self.bc = []
            self.log({"event": "iter", "it": self.it, "stage": self.stage, "adapt": "exit",
                      "rollout_acc": rfit.get("test_acc"),
                      "samples": len(window[-1]), "window": n_window,
                      "label_acc": fit.get("test_acc"), "value_mse": fit.get("test_vloss"),
                      "win": {k: round(float(np.mean([z > 0 for z in v])), 3)
                              for k, v in wr.items()},
                      "games": len(res), "play_s": round(play_s, 1),
                      "train_s": round(time.time() - t1, 1),
                      "games_s": round(self.bc_done / max(play_s, 1e-6), 2),
                      "frozen": self.versions[-1], "mem_gib": round(mem_available_gib(), 1),
                      "search": dict(self.gen_search),
                      "games_void": self.counts["bc:void"], "games_leaky": self.counts["bc:leaky"]})
            self.gen_search = Counter()
            self.bc = []
            if self.stage == "teacher" and self.it % a.eval_every == 0:
                self.queue_eval("teacher", f"teacher:it{self.it}", "eval", ["heuristic"],
                                a.eval_deals)
            if self.stage == "selfplay" and self.it % a.gate_every == 0:
                self.queue_eval("gate", f"gate:it{self.it}", "eval", [self.versions[-1]],
                                a.gate_deals)
            self._drain_evals()
            self.save("last.pt", {"versions": self.versions, "stage": self.stage})

    def run_eval(self, tag: str, seat: str) -> dict:
        self.start_eval(tag, seat=seat)
        prev, self.phase = self.phase, "idle"
        self.serve(lambda: not self.eval_pending)
        self.phase = prev
        ev = self.eval_summary()
        self.log(ev)
        self.eval_meta = {}
        return ev

    def expert_iteration(self) -> None:
        """Generations of: play --exit-games with the searching network, train the network on
        the moves the search chose (and the outcomes), evaluate with and without search."""
        a = self.args
        window: deque = deque(maxlen=a.exit_keep)
        self.bc_seats = [a.exit_seat, a.exit_seat]
        self.exit_opps = a.exit_opps.split(",")
        for gen in range(1, a.exit_gens + 1):
            self.it = gen
            self.bc, self.phase = [], "bc"
            self.bc_target, self.bc_issued, self.bc_done = a.exit_games, 0, 0
            self.bc_seed0 = BC_SEED0 + 1_000_000 * gen
            t0 = time.time()
            self.serve(lambda: self.bc_done >= self.bc_target)
            self.phase = "idle"
            window.append(self.bc)
            self.log({"event": "exit_gen", "gen": gen, "games": self.bc_done,
                      "samples": len(self.bc), "secs": round(time.time() - t0, 1),
                      "counts": {k: v for k, v in self.counts.items() if k.startswith("bc")}})
            self.bc = [x for part in window for x in part]
            self.bc_train(epochs=a.exit_epochs, lr=a.exit_lr)
            self.sync_actor()
            self.save(f"exit_gen{gen}.pt")
            for seat in a.exit_eval_seats.split(","):
                self.run_eval(f"gen{gen}:{seat}", seat)

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
        self.sync_actor()
        self.save("bc.pt")

    def main(self) -> None:
        a = self.args
        try:
            if a.eval_only:
                self.eval_only()
                return
            if a.curriculum:
                if a.bc_games > 0 and not a.init:
                    self.bc_phase()
                if a.adapt == "exit":
                    self.curriculum_exit()
                else:
                    self.curriculum()
                return
            if a.exit_gens > 0:
                self.add_snapshot()
                self.models["snap:base"] = self.models[self.snaps[-1]]
                for seat in a.exit_eval_seats.split(","):
                    self.run_eval(f"gen0:{seat}", seat)
                self.expert_iteration()
                return
            if a.bc_games > 0 and not a.init:
                self.bc_phase()
            self.add_snapshot()  # the starting policy is the league's first member
            self.models["snap:base"] = self.models[self.snaps[-1]]
            self.start_eval("start")
            self.phase = "ppo"
            best = -1.0
            for self.it in range(1, a.iters + 1):
                t0, g0, d0 = time.time(), sum(self.counts[k] for k in
                                              ("train:games", "eval:games", "bc:games")), self.infer_items
                self.serve(lambda: len(self.buffer) >= a.steps)
                tp = self.throughput(t0, g0, d0)
                t1 = time.time()
                st = self.update()
                upd = round(time.time() - t1, 1)
                res = self.train_results
                self.train_results = []
                wr: dict[str, list] = defaultdict(list)
                for opp, z, _ in res:
                    if opp != "self":
                        wr[opp.split(":")[0]].append(z)
                row = {"event": "iter", "it": self.it, **st, **tp, "upd_s": upd,
                       "collect_s": round(t1 - t0, 1),
                       "vs": {k: round(float(np.mean(v)), 3) for k, v in wr.items()},
                       "turns": round(float(np.mean([x[2] for x in res])) if res else 0, 1),
                       "games": len(res), "mem_gib": round(mem_available_gib(), 1),
                       "infer_bs": round(self.infer_items / max(self.infer_batches, 1), 1),
                       "voids": self.counts["train:void"], "overflow": self.counts["overflow"]}
                self.log(row)
                if self.it % a.snap_every == 0:
                    self.add_snapshot()
                if self.eval_meta and not self.eval_pending and self.eval_rows:
                    ev = self.eval_summary()
                    self.log(ev)
                    score = ev.get("heuristic", {}).get("score", -1)
                    if score > best and ev.get("tag") != "start":
                        best = score
                        self.save("best.pt", {"eval": ev})
                    self.eval_meta = {}
                if self.it % a.eval_every == 0 and not self.eval_pending:
                    self.start_eval(f"it{self.it}")
                if self.it % a.save_every == 0:
                    self.save("last.pt")
            self.save("last.pt")
            # final evaluation, waited for
            if not self.eval_pending:
                self.start_eval("final")
            self.phase = "idle"
            self.serve(lambda: not self.eval_pending)
            self.log(self.eval_summary())
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
    p.add_argument("--p-self", type=float, default=0.5)
    p.add_argument("--p-heuristic", type=float, default=0.25)
    p.add_argument("--p-random", type=float, default=0.0)
    p.add_argument("--snap-every", type=int, default=5)
    p.add_argument("--max-snaps", type=int, default=10)
    p.add_argument("--coherent-share", type=float, default=0.5)
    # eval
    p.add_argument("--eval-every", type=int, default=10)
    p.add_argument("--eval-deals", type=int, default=200)
    p.add_argument("--eval-opponents", default="heuristic")
    p.add_argument("--eval-seat", default="eval", help="'eval' or 'eval+search'")
    p.add_argument("--eval-only", action="store_true", help="evaluate --init and exit")
    p.add_argument("--opp-ckpt", default="", help="eval-only: checkpoint to play as 'snap:opp'")
    # curriculum (teacher inter-play -> vs teacher -> gated frozen self-play)
    p.add_argument("--curriculum", action="store_true")
    p.add_argument("--adapt", default="ppo", choices=("ppo", "exit"),
                   help="how the learner adapts in each stage: PPO, or expert iteration (search "
                        "distillation, generations of --exit-games)")
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
    p.add_argument("--kl-anchor", type=float, default=0.0,
                   help="weight of KL(learner || newest frozen version) in the PPO loss")
    p.add_argument("--exit-gens", type=int, default=0, help="expert-iteration generations")
    p.add_argument("--exit-games", type=int, default=2000)
    p.add_argument("--exit-seat", default="learner+search", help="the seat whose moves are learned")
    p.add_argument("--exit-opps", default="heuristic,learner",
                   help="opponents, one drawn per game (learner = the network, unsearched)")
    p.add_argument("--exit-epochs", type=int, default=2)
    p.add_argument("--exit-lr", type=float, default=2e-4)
    p.add_argument("--exit-keep", type=int, default=3, help="generations of data trained on")
    p.add_argument("--exit-eval-seats", default="eval,eval+search")
    p.add_argument("--rollout-init", default="",
                   help="checkpoint of a small network that plays the moves inside simulations")
    p.add_argument("--rollout-epochs", type=int, default=3)
    p.add_argument("--rollout-lr", type=float, default=3e-4)
    p.add_argument("--search-k", type=int, default=4, help="options simulated per searched ask")
    p.add_argument("--search-d", type=int, default=2, help="sampled worlds per option")
    p.add_argument("--search-skip-p", type=float, default=0.97,
                   help="no search when the network's top option has at least this probability")
    p.add_argument("--save-every", type=int, default=5)
    p.add_argument("--trainer-proc", action="store_true",
                   help="PPO updates in a separate process; the workers never wait for one")
    p.add_argument("--async-update", action="store_true",
                   help="train in a thread while the workers keep playing on an actor copy")
    p.add_argument("--mem-floor-gib", type=float, default=8.0,
                   help="stop the run (emergency checkpoint) below this much MemAvailable")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    Learner(args).main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
