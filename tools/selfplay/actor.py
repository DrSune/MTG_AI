"""Game worker processes: many games per process, decisions batched to the learner's GPU.

A worker owns ``n_slots`` game threads. Only one thread runs at a time (baton passing): a slot
runs its game until its network seat must decide, posts the encoded decision and hands the
baton back. The worker sends the posts of one slot group to the learner in one message and runs
the other group while it waits, so the CPU keeps working during GPU inference. Engine code never
runs concurrently, so there are no data races on the engine's module-level caches.

Workers do no torch work (spawn still imports torch in them: it re-imports learner.py as each
worker's main module).

Messages, worker -> learner: ("infer", wid, group, [req]), ("done", wid, [result]),
("need", wid, n). Learner -> worker: ("ans", group, [(action, logp, value)]), ("jobs", [job]),
("stop",).

A job: {"gid", "kind" ("train"|"eval"|"bc"|"capture"|"label"), "seed", "deck_mode", "set_code",
"pool_mode", "seats": [spec, spec], "greedy": [bool, bool], "record": [bool, bool]}; a seat spec is
"learner", "eval", a frozen version "v<k>", "snap:opp", "heuristic" or "random", and a network spec
ending in "+search" searches its decisions (search.py, options in job["search"]). A capture job
(job["capture"] = the share of decisions captured) records the opponent simulator's data (Capture).
A job with "label" ({"k", "d", "greedy"}) labels its network seats' act decisions (search.Labeller);
the labels come back in the result.
"""

from __future__ import annotations

import os
import random
import threading
import traceback
from collections import deque
from typing import Any

import numpy as np

from MTG_bot.core.state import ZONE_HAND, ZONE_LIBRARY
from tools.selfplay import features as FT
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
    asks the encoding cannot hold (more than MAX_OPTIONS options, or a ``name`` ask, which lists
    every card name of the format's pool) go to the fallback agent; both are counted."""

    def __init__(self, slot: _Slot, job: dict, seat: int, table: FT.CardTable,
                 labeller: Any = None) -> None:
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
        self.overflow = 0
        self.searcher = None
        self.attack_plan = None
        self.plan_turn = -1
        self.block_plan = None
        self.block_turn = -1
        self.labeller = labeller
        if spec.endswith(SEARCH_SUFFIX):
            from tools.selfplay.search import Searcher

            opts = {k: v for k, v in job["search"].items() if k != "blocks"}
            # Gumbel noise at the root only where the seat samples its moves (training play)
            self.searcher = Searcher(slot, job["gid"], self.spec, table,
                                     pool_mode=job["pool_mode"], set_code=job["set_code"],
                                     seed=job["seed"] * 2 + seat, noise=not self.greedy, **opts)

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
                return idx
        if (ask.kind == "block" and self.block_plan is not None
                and self.block_turn == obs.executor.world.turn):
            from tools.selfplay.search import block_answer

            idx = block_answer(ask, self.block_plan)
            if idx is not None:
                return idx
        feats = FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx)
        if self.searcher is not None and ask.kind in self.searcher.kinds:
            return self.searcher.choose(ask, obs, feats)
        if self.labeller is not None and ask.kind == "act":
            a, _, probs = self.slot.infer((self.job["gid"], self.seat, self.spec, self.greedy,
                                           self.record, feats, 2))
            self.labeller.offer(obs.game, ask, feats, probs)
            return int(a)
        return int(self.slot.infer((self.job["gid"], self.seat, self.spec, self.greedy,
                                    self.record, feats)))

    def plan_combat(self, game: Any, seat: int) -> None:
        """Called by the rig at the pre-combat boundary (rig.SelfplayRouter.before_attacks)."""
        if self.searcher is None:
            return
        self.attack_plan = self.searcher.plan_attacks(game, seat)
        self.plan_turn = game.world.turn

    def plan_blocks(self, game: Any, seat: int, declared_attackers: frozenset = frozenset()) -> None:
        """Called by the rig at the pre-blocks boundary (rig.SelfplayRouter.before_blocks)."""
        if self.searcher is None or not self.job["search"]["blocks"]:
            return
        self.block_plan = self.searcher.plan_blocks(game, seat, declared_attackers)
        self.block_turn = game.world.turn


class RecordingHeuristic:
    """The heuristic, recording (features, action) at every real decision for behaviour
    cloning (the teacher inter-play stage)."""

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


class Capture:
    """A seat of a capture game, the opponent simulator's data (simulator.py). At a share ``p`` of
    its real decisions it records what this seat may know (features.sim_view) in ``views`` and,
    kept apart in ``truth``, the labels: the opponent's hand and library as sorted card-table rows.
    The wrapped agent decides as it would unwrapped: the capture only reads the game, and draws
    from its own random stream."""

    def __init__(self, inner: Any, seat: int, table: FT.CardTable, p: float, seed: int) -> None:
        self.inner = inner
        self.table = table
        self.p = p
        self.rng = random.Random(f"capture:{seed}:{seat}")
        self.views: list[dict] = []
        self.truth: list[tuple[np.ndarray, np.ndarray]] = []

    def __getattr__(self, name: str) -> Any:  # the seat's own (name, plan_combat, overflow, ...)
        return getattr(self.inner, name)

    def decide(self, ask: Any, obs: Any) -> int:
        if len(ask.options) > 1 and self.rng.random() < self.p:
            ex = obs.executor
            self.views.append(FT.sim_view(ex, ask.seat, ask, self.table, obs.ctx))
            world = ex.world
            zones = world.players[world.player_order[1 - ask.seat]].zones
            self.truth.append(tuple(np.array(sorted(
                self.table.row(world.cards[h].identity.oracle_id) for h in zones[z].entries),
                np.int16) for z in (ZONE_HAND, ZONE_LIBRARY)))
        return self.inner.decide(ask, obs)


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
                          "trace": traceback.format_exc()[-2000:],
                          # the deal, so an eval voids the seat-swapped pair
                          "seed": job.get("seed"), "deck_mode": job.get("deck_mode"),
                          "seats": job.get("seats"), "a_seat": job.get("a_seat"),
                          "opp": job.get("opp"), "set_code": job.get("set_code")}
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
        labeller = None
        if job.get("label"):
            from tools.selfplay.search import Labeller

            o = job["label"]
            labeller = Labeller(slot, job["gid"], job["seats"][0], self.table,
                                pool_mode=job["pool_mode"], set_code=job["set_code"], k=o["k"],
                                d=o["d"], greedy=o["greedy"], seed=job["seed"])
        agents: list[Any] = []
        for seat in (0, 1):
            spec = job["seats"][seat]
            if is_net(spec):
                agents.append(NetAgent(slot, job, seat, self.table, labeller))
            elif spec == "heuristic":
                agents.append(RecordingHeuristic(seat, self.table) if job["record"][seat]
                              else HeuristicAgent())
            elif spec == "random":
                agents.append(_UniformRandom(job["seed"] * 7 + seat))
            else:
                raise ValueError(f"unknown seat spec {spec!r}")
        if job.get("capture"):
            agents = [Capture(a, seat, self.table, job["capture"], job["seed"])
                      for seat, a in enumerate(agents)]
        res = play_game(job["seed"], agents, deck_mode=job["deck_mode"],
                        set_code=job["set_code"], pool_mode=job["pool_mode"])
        res["gid"] = job["gid"]
        res["kind"] = job["kind"]
        res["seats"] = job["seats"]
        res["a_seat"] = job.get("a_seat")
        res["opp"] = job.get("opp")
        res["set_code"] = job["set_code"]
        res["search"] = [dict(a.searcher.stats) if getattr(a, "searcher", None) else None
                         for a in agents]
        res["overflow"] = [getattr(a, "overflow", 0) for a in agents]
        bc = [a.samples if isinstance(a, RecordingHeuristic) else None for a in agents]
        if any(s is not None for s in bc):
            res["bc"] = bc
        if job.get("capture"):
            res["views"] = [v for a in agents for v in a.views]
            res["truth"] = [t for a in agents for t in a.truth]
        if labeller is not None:
            res["labels"] = labeller.labels()
            res["label_stats"] = labeller.stats
        return res

    # --- main thread
    def _run(self, slot: _Slot) -> None:
        slot.go.release()
        self.main_wake.acquire()

    def _handle(self, msg: tuple) -> None:
        kind = msg[0]
        if kind == "ans":
            self.answers[msg[1]] = msg[2]
        elif kind == "jobs":
            self.jobs.extend(msg[1])
            self.need_sent = 0
        elif kind == "stop":
            self.stopping = True

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
