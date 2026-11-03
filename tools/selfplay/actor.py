"""Game worker processes: many games per process, decisions batched to the learner's GPU.

A worker owns ``n_slots`` game threads. Only one thread runs at a time (baton passing): a slot
runs its game until its network seat must decide, posts the encoded decision and hands the
baton back. The worker sends the posts of one slot group to the learner in one message and runs
the other group while it waits, so the CPU keeps working during GPU inference. Engine code never
runs concurrently, so there are no data races on the engine's module-level caches.

Workers never import torch.

Messages, worker -> learner: ("infer", wid, group, [req]), ("done", wid, [result]),
("need", wid, n). Learner -> worker: ("ans", group, [(action, logp, value)]), ("jobs", [job]),
("stop",).

A job: {"gid", "kind" ("train"|"eval"|"bc"), "seed", "deck_mode", "seats": [spec, spec],
"greedy": [bool, bool], "record": [bool, bool]}; a seat spec is "learner", "snap:<id>",
"eval", "heuristic" or "random".
"""

from __future__ import annotations

import os
import random
import threading
import traceback
from collections import deque
from typing import Any

from tools.selfplay import features as FT
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import play_game

NET_SPECS = ("learner", "eval")


def is_net(spec: str) -> bool:
    return spec in NET_SPECS or spec.startswith("snap:")


class _UniformRandom:
    name = "random"

    def __init__(self, seed: int) -> None:
        self.rng = random.Random(seed)

    def decide(self, ask: Any, obs: Any) -> int:
        return self.rng.randrange(len(ask.options))


class NetAgent:
    """A seat played by a network on the learner. Single-option asks are not decisions, and
    asks the encoding cannot hold (more than MAX_OPTIONS options, or a ``name`` ask, which
    enumerates hidden cards) go to the fallback agent; both are counted."""

    def __init__(self, slot: _Slot, job: dict, seat: int, table: FT.CardTable) -> None:
        self.slot = slot
        self.job = job
        self.seat = seat
        self.spec = job["seats"][seat]
        self.greedy = bool(job["greedy"][seat])
        self.record = bool(job["record"][seat])
        self.table = table
        self.fallback = HeuristicAgent()
        self.name = self.spec
        self.decisions = 0
        self.overflow = 0

    def decide(self, ask: Any, obs: Any) -> int:
        n = len(ask.options)
        if n == 1:
            return 0
        if n > FT.MAX_OPTIONS or ask.kind == "name":
            self.overflow += 1
            return self.fallback.decide(ask, obs)
        feats = FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx)
        self.decisions += 1
        req = (self.job["gid"], self.seat, self.spec, self.greedy, self.record, feats)
        action = self.slot.infer(req)
        return int(action)


class RecordingHeuristic:
    """The heuristic, recording (features, action) for behaviour cloning."""

    def __init__(self, seat: int, table: FT.CardTable) -> None:
        self.inner = HeuristicAgent()
        self.seat = seat
        self.table = table
        self.samples: list[tuple[dict, int]] = []
        self.name = "heuristic"

    def decide(self, ask: Any, obs: Any) -> int:
        idx = self.inner.decide(ask, obs)
        n = len(ask.options)
        if 1 < n <= FT.MAX_OPTIONS and ask.kind != "name":
            self.samples.append((FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx), idx))
        return idx


class _Slot(threading.Thread):
    def __init__(self, worker: Worker, index: int) -> None:
        super().__init__(daemon=True)
        self.worker = worker
        self.index = index
        self.go = threading.Semaphore(0)
        self.state = "new"  # new | infer | idle | running
        self.req: Any = None
        self.answer: Any = None

    # --- called from the slot thread
    def _yield(self) -> None:
        self.worker.main_wake.release()
        self.go.acquire()

    def infer(self, req: Any) -> Any:
        self.req = req
        self.answer = None
        self.state = "infer"
        self._yield()
        self.state = "running"
        return self.answer

    def run(self) -> None:
        self.go.acquire()
        self.state = "running"
        while True:
            job = self.worker.take_job()
            if job is None:
                self.state = "idle"
                self._yield()
                self.state = "running"
                continue
            try:
                result = self.worker.play(job, self)
            except Exception as error:  # noqa: BLE001 - reported, never hidden
                result = {"gid": job["gid"], "kind": job["kind"], "outcome": "void-worker",
                          "winner": None, "crash": f"{type(error).__name__}: {error}",
                          "trace": traceback.format_exc()[-2000:]}
            self.worker.outbox.append(result)


class Worker:
    def __init__(self, wid: int, conn: Any, n_slots: int, table_json: dict) -> None:
        self.wid = wid
        self.conn = conn
        self.table = FT.CardTable.from_json(table_json)
        self.jobs: deque = deque()
        self.outbox: list = []
        self.main_wake = threading.Semaphore(0)
        self.slots = [_Slot(self, i) for i in range(n_slots)]
        half = max(1, n_slots // 2)
        self.groups = [self.slots[:half], self.slots[half:]] if n_slots > 1 else [self.slots, []]
        self.need_sent = 0
        self.stopping = False
        self.answers: dict[int, list | None] = {0: None, 1: None}

    def take_job(self) -> dict | None:
        return self.jobs.popleft() if self.jobs else None

    def play(self, job: dict, slot: _Slot) -> dict:
        agents: list[Any] = []
        for seat in (0, 1):
            spec = job["seats"][seat]
            if is_net(spec):
                agents.append(NetAgent(slot, job, seat, self.table))
            elif spec == "heuristic":
                agents.append(RecordingHeuristic(seat, self.table) if job["record"][seat]
                              else HeuristicAgent())
            elif spec == "random":
                agents.append(_UniformRandom(job["seed"] * 7 + seat))
            else:
                raise ValueError(f"unknown seat spec {spec!r}")
        res = play_game(job["seed"], agents, deck_mode=job["deck_mode"])
        res["gid"] = job["gid"]
        res["kind"] = job["kind"]
        res["seats"] = job["seats"]
        res["net_decisions"] = [getattr(a, "decisions", 0) for a in agents]
        res["overflow"] = [getattr(a, "overflow", 0) for a in agents]
        bc = [a.samples if isinstance(a, RecordingHeuristic) else None for a in agents]
        if any(s is not None for s in bc):
            res["bc"] = bc
        return res

    # --- main thread
    def _run(self, slot: _Slot) -> None:
        slot.go.release()
        self.main_wake.acquire()

    def _handle(self, msg: tuple) -> Any:
        kind = msg[0]
        if kind == "ans":
            self.answers[msg[1]] = msg[2]
        elif kind == "jobs":
            self.jobs.extend(msg[1])
            self.need_sent = 0
        elif kind == "stop":
            self.stopping = True
        return msg

    def _wait_answers(self, group: int) -> list:
        while self.answers[group] is None and not self.stopping:
            self._handle(self.conn.recv())
        out, self.answers[group] = self.answers[group] or [], None
        return out

    def loop(self) -> None:
        for s in self.slots:
            s.start()
        outstanding: list[list[_Slot]] = [[], []]
        while not self.stopping:
            progressed = False
            for g in (0, 1):
                if outstanding[g]:
                    answers = self._wait_answers(g)
                    if self.stopping:
                        break
                    for s, a in zip(outstanding[g], answers, strict=True):
                        s.answer = a
                    outstanding[g] = []
                posted = []
                for s in self.groups[g]:
                    if s.state == "idle" and not self.jobs:
                        continue
                    self._run(s)
                    progressed = True
                    if s.state == "infer":
                        posted.append(s)
                if posted:
                    self.conn.send(("infer", self.wid, g, [s.req for s in posted]))
                    outstanding[g] = posted
                if self.outbox:
                    out, self.outbox = self.outbox, []
                    self.conn.send(("done", self.wid, out))
                want = 2 * len(self.slots) - len(self.jobs)
                if want > len(self.slots) and not self.need_sent:
                    self.conn.send(("need", self.wid, want))
                    self.need_sent = want
            if not progressed and not any(outstanding):
                self._handle(self.conn.recv())  # nothing to run: block for jobs or stop
            while self.conn.poll():
                self._handle(self.conn.recv())


def worker_main(wid: int, conn: Any, n_slots: int, table_json: dict, nice: int = 5) -> None:
    try:
        os.nice(nice)
    except OSError:
        pass
    import sys

    sys.setrecursionlimit(20000)
    threading.stack_size(64 * 1024 * 1024)
    Worker(wid, conn, n_slots, table_json).loop()
