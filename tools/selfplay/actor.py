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
from tools.selfplay.features import _handle
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import play_game

SEARCH_SUFFIX = "+search"


def is_net(spec: str) -> bool:
    """Every seat spec except the two scripted players names a network on the learner
    ("learner", "eval", "snap:<k>", a frozen version "v<k>", ...)."""
    return spec.removesuffix(SEARCH_SUFFIX) not in ("heuristic", "random")


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
        spec = job["seats"][seat]
        self.spec = spec.removesuffix(SEARCH_SUFFIX)
        self.greedy = bool(job["greedy"][seat])
        self.record = bool(job["record"][seat])
        self.table = table
        self.fallback = HeuristicAgent()
        self.name = spec
        self.decisions = 0
        self.overflow = 0
        self.searcher = None
        self.attack_plan = None
        self.plan_turn = -1
        # Expert iteration: in a "bc" job a recorded network seat keeps (features, the move it
        # actually played) locally, the search's choice where it searched; the learner trains
        # on them like BC data. The server records nothing for it (that lane is PPO's).
        value_only = bool(job.get("value_seats", [False, False])[seat])
        self.label = job["kind"] == "bc" and (self.record or value_only)
        self.wp = 0.0 if value_only and not self.record else 1.0
        self.samples: list[tuple[dict, int, float]] = []
        if spec.endswith(SEARCH_SUFFIX):
            from tools.selfplay.search import Searcher

            opts = job.get("search", {})
            self.searcher = Searcher(slot, job["gid"], self.spec, table, k=opts.get("k", 4),
                                     d=opts.get("d", 2), skip_p=opts.get("skip_p", 0.97),
                                     seed=job["seed"] * 2 + seat, rollout=opts.get("rollout"),
                                     value=opts.get("value"), tau=opts.get("tau", 0.05))

    def decide(self, ask: Any, obs: Any) -> int:
        n = len(ask.options)
        if n == 1:
            return 0
        if n > FT.MAX_OPTIONS or ask.kind == "name":
            self.overflow += 1
            return self.fallback.decide(ask, obs)
        if (ask.kind == "attack" and self.attack_plan is not None
                and self.plan_turn == obs.executor.world.turn):
            from tools.selfplay.search import plan_answer

            idx = plan_answer(ask, self.attack_plan)
            if idx is not None:
                if self.label:
                    target = None
                    h = _handle(":".join(ask.site.split(":")[1:3]))
                    pa = self.searcher.plan_targets.get(h) if self.searcher else None
                    toks = [o.token for o in ask.options]
                    if pa is not None and "ATTACK" in toks and "DECLINE" in toks:
                        target = [(toks.index("ATTACK"), pa), (toks.index("DECLINE"), 1.0 - pa)]
                    self.samples.append(
                        (FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx), idx,
                         self.wp, target))
                return idx
        feats = FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx)
        self.decisions += 1
        target = None
        if self.searcher is not None and ask.kind == "act":
            idx = self.searcher.choose(ask, obs, feats)
            target = self.searcher.last_target
        else:
            req = (self.job["gid"], self.seat, self.spec, self.greedy,
                   self.record and not self.label, feats)
            idx = int(self.slot.infer(req))
        if self.label:
            self.samples.append((feats, idx, self.wp, target))
        return idx

    def plan_combat(self, game: Any, seat: int) -> None:
        """Called by the rig at the pre-combat boundary (rig.SelfplayRouter.take_acts)."""
        if self.searcher is None or not self.job.get("search", {}).get("combat", True):
            return
        self.attack_plan = self.searcher.plan_attacks(game, seat)
        self.plan_turn = game.world.turn


class RecordingHeuristic:
    """The heuristic, recording (features, action, policy weight) for behaviour cloning. With
    ``value_only`` the policy weight is 0: the decision trains the value head only (an ExIt
    opponent's positions, seen from its own seat)."""

    def __init__(self, seat: int, table: FT.CardTable, value_only: bool = False) -> None:
        self.inner = HeuristicAgent()
        self.seat = seat
        self.table = table
        self.wp = 0.0 if value_only else 1.0
        self.samples: list[tuple[dict, int, float]] = []
        self.name = "heuristic"

    def decide(self, ask: Any, obs: Any) -> int:
        idx = self.inner.decide(ask, obs)
        n = len(ask.options)
        if 1 < n <= FT.MAX_OPTIONS and ask.kind != "name":
            self.samples.append(
                (FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx), idx, self.wp))
        return idx


class ValueSampler:
    """Wraps any seat: with probability ``p`` a decision's position is kept as a value-only
    sample (features, action, policy weight 0). A few positions from many games, not every
    position of few games: consecutive positions of one game share its outcome and are near
    copies, so training on all of them memorises outcomes (AlphaGo's value-net finding; r10:
    held-out value MSE 0.645 -> 0.712 after one epoch on all positions)."""

    def __init__(self, inner: Any, table: FT.CardTable, p: float, seed: int) -> None:
        self.inner_agent = inner
        self.table = table
        self.p = p
        self.rng = random.Random(seed)
        self.vsamples: list[tuple[dict, int, float]] = []
        self.name = getattr(inner, "name", "?")

    def __getattr__(self, key: str) -> Any:  # plan_combat, searcher, decisions, ...
        return getattr(self.inner_agent, key)

    def decide(self, ask: Any, obs: Any) -> int:
        idx = self.inner_agent.decide(ask, obs)
        n = len(ask.options)
        if 1 < n <= FT.MAX_OPTIONS and ask.kind != "name" and self.rng.random() < self.p:
            self.vsamples.append(
                (FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx), idx, 0.0))
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
    def __init__(self, wid: int, conn: Any, n_slots: int, table_json: dict,
                 n_groups: int = 2) -> None:
        self.wid = wid
        self.conn = conn
        self.table = FT.CardTable.from_json(table_json)
        self.jobs: deque = deque()
        self.outbox: list = []
        self.main_wake = threading.Semaphore(0)
        self.slots = [_Slot(self, i) for i in range(n_slots)]
        # Slot groups are pipelined: a group's requests are answered while the others run. More
        # groups hide more round-trip latency (simulated decisions are only ~1-2 ms apart).
        n_groups = max(1, min(n_groups, n_slots))
        self.groups = [self.slots[i::n_groups] for i in range(n_groups)]
        self.need_sent = 0
        self.stopping = False
        self.answers: dict[int, list | None] = {g: None for g in range(len(self.groups))}

    def take_job(self) -> dict | None:
        return self.jobs.popleft() if self.jobs else None

    def play(self, job: dict, slot: _Slot) -> dict:
        agents: list[Any] = []
        for seat in (0, 1):
            spec = job["seats"][seat]
            if is_net(spec):
                agents.append(NetAgent(slot, job, seat, self.table))
            elif spec == "heuristic":
                value_only = bool(job.get("value_seats", [False, False])[seat])
                if job["record"][seat] or value_only:
                    agents.append(RecordingHeuristic(seat, self.table,
                                                     value_only=not job["record"][seat]))
                else:
                    agents.append(HeuristicAgent())
            elif spec == "random":
                agents.append(_UniformRandom(job["seed"] * 7 + seat))
            else:
                raise ValueError(f"unknown seat spec {spec!r}")
        value_p = float(job.get("value_p", 0.0))
        if value_p > 0:
            agents = [ValueSampler(a, self.table, value_p, job["seed"] * 2 + seat)
                      for seat, a in enumerate(agents)]
        res = play_game(job["seed"], agents, deck_mode=job["deck_mode"])
        res["gid"] = job["gid"]
        res["kind"] = job["kind"]
        res["seats"] = job["seats"]
        res["a_seat"] = job.get("a_seat")
        res["opp"] = job.get("opp")
        inner = [getattr(a, "inner_agent", a) for a in agents]
        res["search"] = [dict(a.searcher.stats) if getattr(a, "searcher", None) else None
                         for a in inner]
        res["net_decisions"] = [getattr(a, "decisions", 0) for a in inner]
        res["overflow"] = [getattr(a, "overflow", 0) for a in inner]
        bc = [a.samples if isinstance(a, RecordingHeuristic) or getattr(a, "label", False)
              else None for a in inner]
        if any(s is not None for s in bc):
            res["bc"] = bc
        if value_p > 0:
            res["vs"] = [a.vsamples for a in agents]
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
        outstanding: list[list[_Slot]] = [[] for _ in self.groups]
        while not self.stopping:
            progressed = False
            for g in range(len(self.groups)):
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


def worker_main(wid: int, conn: Any, n_slots: int, table_json: dict, nice: int = 5,
                n_groups: int = 2) -> None:
    try:
        os.nice(nice)
    except OSError:
        pass
    import sys

    sys.setrecursionlimit(20000)
    threading.stack_size(64 * 1024 * 1024)
    Worker(wid, conn, n_slots, table_json, n_groups=n_groups).loop()
