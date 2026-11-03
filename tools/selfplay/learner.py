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
import json
import math
import multiprocessing as mp
import random
import sys
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
        self.it = 0
        self.counts: Counter = Counter()
        self.train_results: list = []
        self.infer_batches = 0
        self.infer_items = 0
        self.infer_time = 0.0
        self._start_workers()

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
            return self._job("bc", BC_SEED0 + self.bc_issued, ["heuristic", "heuristic"],
                             [False, False], [True, True], self._deck_mode())
        if self.phase == "ppo":
            return self.train_job()
        return None

    def train_job(self) -> dict:
        a = self.args
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
        for key, items in by_key.items():
            model = self.models[key]
            b = M.collate([it[2][5] for it in items], self.device)
            with torch.autocast(self.device.type, dtype=torch.bfloat16, enabled=self.cuda):
                logits, value = model(b)
            greedy = torch.tensor([bool(it[2][3]) for it in items], device=self.device)
            probs = torch.softmax(logits, -1)
            sampled = torch.multinomial(probs, 1).squeeze(1)
            act = torch.where(greedy, logits.argmax(-1), sampled)
            logp = torch.log_softmax(logits, -1).gather(1, act[:, None]).squeeze(1)
            act_np = act.cpu().numpy()
            logp_np = logp.cpu().numpy()
            val_np = value.cpu().numpy()
            for j, (mi, ri, req) in enumerate(items):
                a = int(act_np[j])
                answers[mi][ri] = a
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
            elif kind == "bc":
                self.bc_done += 1
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
        lengths = np.array([key(x) for x in items], dtype=np.float64)
        order = np.argsort(lengths + np.random.rand(len(items)) * 4.0)
        chunks = [order[i:i + mb] for i in range(0, len(order), mb)]
        random.shuffle(chunks)
        return chunks

    def ppo_update(self) -> dict:
        a = self.args
        buf, self.buffer = self.buffer, []
        n = len(buf)
        adv = np.array([b[4] for b in buf], dtype=np.float32)
        adv_n = (adv - adv.mean()) / (adv.std() + 1e-8)
        ret = np.array([b[5] for b in buf], dtype=np.float32)
        old_v = np.array([b[3] for b in buf], dtype=np.float32)
        ev = 1.0 - float(np.var(ret - old_v)) / max(float(np.var(ret)), 1e-8)
        self.model.train()
        stats = defaultdict(list)
        stop = False
        for epoch in range(a.epochs):
            kls = []
            for ch in self._chunks(buf, a.mb, lambda x: x[0]["cards_i"].shape[0]
                                   + 2 * x[0]["opts_i"].shape[0]):
                b = M.collate([buf[i][0] for i in ch], self.device)
                act = torch.tensor([buf[i][1] for i in ch], device=self.device)
                old_logp = torch.tensor([buf[i][2] for i in ch], device=self.device)
                A = torch.from_numpy(adv_n[ch]).to(self.device)
                R = torch.from_numpy(ret[ch]).to(self.device)
                V0 = torch.from_numpy(old_v[ch]).to(self.device)
                with torch.autocast(self.device.type, dtype=torch.bfloat16, enabled=self.cuda):
                    logits, v = self.model(b)
                logp_all = torch.log_softmax(logits, -1)
                logp = logp_all.gather(1, act[:, None]).squeeze(1)
                ent = -(logp_all.exp() * logp_all).sum(-1)
                ratio = torch.exp(logp - old_logp)
                pg = -torch.min(ratio * A, ratio.clamp(1 - a.clip, 1 + a.clip) * A).mean()
                v_clip = V0 + (v - V0).clamp(-a.vclip, a.vclip)
                vloss = torch.max((v - R) ** 2, (v_clip - R) ** 2).mean()
                loss = pg + a.vcoef * vloss - a.ent * ent.mean()
                self.opt.zero_grad(set_to_none=True)
                loss.backward()
                gn = torch.nn.utils.clip_grad_norm_(self.model.parameters(), a.max_grad)
                self.opt.step()
                with torch.no_grad():
                    log_ratio = logp - old_logp
                    kl = ((ratio - 1) - log_ratio).mean().item()
                    kls.append(kl)
                    stats["pg"].append(pg.item())
                    stats["v"].append(vloss.item())
                    stats["ent"].append(ent.mean().item())
                    stats["kl"].append(kl)
                    stats["clip"].append(((ratio - 1).abs() > a.clip).float().mean().item())
                    stats["gn"].append(float(gn))
            stats["epochs"].append(epoch + 1)
            if a.target_kl > 0 and float(np.mean(kls)) > a.target_kl:
                stop = True
                break
        self.model.eval()
        out = {k: round(float(np.mean(v)), 5) for k, v in stats.items() if k != "epochs"}
        out.update({"steps": n, "epochs": stats["epochs"][-1], "kl_stop": stop,
                    "ev": round(ev, 4), "adv_std": round(float(adv.std()), 4)})
        return out

    # ------------------------------------------------------------------ BC

    def bc_train(self) -> dict:
        a = self.args
        data = self.bc
        gids = sorted({x[3] for x in data})
        hold = set(gids[:: max(2, int(1 / max(a.bc_holdout, 1e-3)))])
        train = [x for x in data if x[3] not in hold]
        test = [x for x in data if x[3] in hold]
        self.log({"event": "bc_data", "samples": len(data), "train": len(train),
                  "test": len(test), "games": len(gids)})
        self.model.train()
        opt = torch.optim.AdamW(self.model.parameters(), lr=a.bc_lr, weight_decay=a.wd)
        steps_total = max(1, a.bc_epochs * math.ceil(len(train) / a.mb))
        warm = max(1, steps_total // 20)
        sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / warm) * (
            0.05 + 0.95 * 0.5 * (1 + math.cos(math.pi * min(1.0, s / steps_total)))))
        best = None
        for epoch in range(a.bc_epochs):
            t0 = time.time()
            ls = []
            for ch in self._chunks(train, a.mb, lambda x: x[0]["cards_i"].shape[0]
                                   + 2 * x[0]["opts_i"].shape[0]):
                b = M.collate([train[i][0] for i in ch], self.device)
                act = torch.tensor([train[i][1] for i in ch], device=self.device)
                z = torch.tensor([train[i][2] for i in ch], device=self.device)
                with torch.autocast(self.device.type, dtype=torch.bfloat16, enabled=self.cuda):
                    logits, v = self.model(b)
                loss = F.cross_entropy(logits, act) + a.vcoef * F.mse_loss(v, z)
                opt.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), a.max_grad)
                opt.step()
                sched.step()
                ls.append(loss.item())
            acc, vl = self.bc_eval(test)
            row = {"event": "bc_epoch", "epoch": epoch, "loss": round(float(np.mean(ls)), 5),
                   "test_acc": acc, "test_vloss": vl, "secs": round(time.time() - t0, 1)}
            self.log(row)
            best = row
        self.model.eval()
        self.bc = []
        return best or {}

    @torch.no_grad()
    def bc_eval(self, test: list) -> tuple[float, float]:
        self.model.eval()
        correct = 0
        vls = []
        for i in range(0, len(test), self.args.mb):
            part = test[i:i + self.args.mb]
            b = M.collate([x[0] for x in part], self.device)
            with torch.autocast(self.device.type, dtype=torch.bfloat16, enabled=self.cuda):
                logits, v = self.model(b)
            pred = logits.argmax(-1).cpu().numpy()
            correct += int(sum(int(p == x[1]) for p, x in zip(pred, part, strict=True)))
            z = torch.tensor([x[2] for x in part], device=self.device)
            vls.append(F.mse_loss(v, z).item())
        self.model.train()
        return round(correct / max(len(test), 1), 4), round(float(np.mean(vls or [0])), 4)

    # ------------------------------------------------------------------ eval

    def start_eval(self, tag: str, opponents: list[str] | None = None) -> None:
        a = self.args
        frozen = M.build(self.table, **{k: v for k, v in self.model.config.items()
                                        if k not in ("n_cards", "n_ir")}).to(self.device)
        frozen.load_state_dict(self.model.state_dict())
        frozen.eval()
        self.models["eval"] = frozen
        self.eval_rows = []
        self.eval_meta = {"tag": tag, "it": self.it, "t0": time.time()}
        for opp in opponents or a.eval_opponents.split(","):
            for i in range(a.eval_deals):
                seed = EVAL_SEED0 + i
                mode = "stress" if i % 2 == 0 else "coherent"
                for a_seat in (0, 1):
                    seats = ["eval", opp] if a_seat == 0 else [opp, "eval"]
                    job = self._job("eval", seed, seats, [True, True], [False, False], mode)
                    job["opp"] = opp
                    job["a_seat"] = a_seat
                    self.eval_jobs.append(job)
                    self.eval_pending.add(job["gid"])

    def eval_summary(self) -> dict:
        by_opp: dict[str, list] = defaultdict(list)
        for r in self.eval_rows:
            opp = next(s for s in r["seats"] if s != "eval") if "eval" in r["seats"] else "?"
            by_opp[opp].append(r)
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
                    a_seat = p["seats"].index("eval")
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

    def main(self) -> None:
        a = self.args
        try:
            if a.bc_games > 0 and not a.init:
                self.phase = "bc"
                self.bc_target = a.bc_games
                t0 = time.time()
                last = 0
                def bc_done() -> bool:
                    nonlocal last
                    if self.bc_done - last >= 1000:
                        last = self.bc_done
                        self.log({"event": "bc_gen", "games": self.bc_done,
                                  "samples": len(self.bc), "secs": round(time.time() - t0, 1),
                                  "mem_gib": round(mem_available_gib(), 1)})
                    return self.bc_done >= self.bc_target
                self.serve(bc_done)
                self.phase = "idle"
                self.log({"event": "bc_gen_done", "games": self.bc_done, "samples": len(self.bc),
                          "secs": round(time.time() - t0, 1), "counts": dict(self.counts)})
                self.bc_train()
                self.save("bc.pt")
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
                st = self.ppo_update()
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
    # PPO
    p.add_argument("--iters", type=int, default=100)
    p.add_argument("--steps", type=int, default=65536, help="learner decisions per iteration")
    p.add_argument("--mb", type=int, default=2048)
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
    p.add_argument("--save-every", type=int, default=5)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    Learner(args).main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
