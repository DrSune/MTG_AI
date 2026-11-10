"""Scratch (not repo code): play a checkpoint against itself in-process.

    collect_v0.py ppo  CKPT N SEED0 OUT.pkl   both seats sample, both recorded: PPO rows with z
    collect_v0.py temp CKPT N SEED0 OUT.json  greedy seat against sampling seat, seat-swapped deals
"""
import json
import pickle
import random
import sys
import time

import torch

from tools.selfplay import model as M
from tools.selfplay.actor import NetAgent
from tools.selfplay.rig import play_game


class Slot:
    """LocalSlot that samples unless the request is greedy, and keeps recorded rows."""

    def __init__(self, net, seed):
        self.net = net
        self.gen = torch.Generator()
        self.gen.manual_seed(seed)
        self.rows = {}

    @torch.no_grad()
    def infer(self, req):
        gid, seat, _spec, greedy, record, feats = req[:6]
        p = next(self.net.parameters())
        b = {k: (v.to(p.dtype) if v.is_floating_point() else v)
             for k, v in M.collate([feats], p.device).items()}
        logits, value = self.net(b)
        lp = torch.log_softmax(logits[0, : feats["opts_i"].shape[0]].float(), -1).cpu()
        a = int(lp.argmax()) if greedy else int(torch.multinomial(lp.exp(), 1, generator=self.gen))
        if record:
            ent = float(-(lp.exp() * lp).sum())
            self.rows.setdefault((gid, seat), []).append(
                (feats, a, float(lp[a]), float(value.float()[0]), ent))
        return a


def reward(outcome, winner, seat):
    if outcome == "win":
        return 1.0 if winner == seat else -1.0
    return 0.0 if outcome == "draw-mutual" else -1.0


def main():
    mode, ckpt, n, seed0, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
    dev = torch.device("cuda")
    net, table, _ = M.load(ckpt, dev)
    net.eval()
    slot = Slot(net, seed0)
    rng = random.Random(seed0)
    t0 = time.time()
    rows, games = [], []
    for g in range(n):
        seed = seed0 + g
        set_code = "M20" if rng.random() < 0.25 else "M21"
        plays = [([False, False], [True, True])] if mode == "ppo" else [
            ([True, False], [False, False]), ([False, True], [False, False])]
        for k, (greedy, record) in enumerate(plays):
            gid = 2 * g + k
            job = {"gid": gid, "seed": seed, "seats": ["v0", "v0"], "greedy": greedy,
                   "record": record, "pool_mode": "verified", "set_code": set_code}
            agents = [NetAgent(slot, job, s, table) for s in (0, 1)]
            res = play_game(seed, agents, deck_mode="coherent", set_code=set_code,
                            pool_mode="verified")
            void = res["outcome"].startswith("void")
            games.append({"seed": seed, "set": set_code, "outcome": res["outcome"],
                          "winner": res["winner"], "turns": res["turns"],
                          "greedy_seat": greedy.index(True) if any(greedy) else None})
            for seat in (0, 1):
                steps = slot.rows.pop((gid, seat), [])
                if void:
                    continue
                z = reward(res["outcome"], res["winner"], seat)
                for i, (f, a, lp, v, ent) in enumerate(steps):
                    rows.append({"feats": f, "act": a, "logp": lp, "v": v, "ent": ent, "z": z,
                                 "gid": gid, "seat": seat, "i": i, "n": len(steps), "set": set_code})
        if (g + 1) % 25 == 0:
            print(f"{mode} {g + 1}/{n} games-deals, {len(rows)} rows, {time.time() - t0:.0f}s", flush=True)
    if mode == "ppo":
        with open(out, "wb") as fh:
            pickle.dump({"rows": rows, "games": games}, fh)
    else:
        with open(out, "w") as fh:
            json.dump(games, fh)
    print("done", mode, len(games), "games", len(rows), "rows", f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
