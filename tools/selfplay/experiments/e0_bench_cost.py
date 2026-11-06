"""E0 time costs of the opponent simulator on the GPU (the owner's request, 2026-11-06):
- one belief (the marginal head: P(card in hand), expected library counts) for one decision;
- sampling whole hands (h autoregressive steps);
- sampling a hand, then the library contents (l steps), then the next k cards as draws from them;
- one training step at the training minibatch, with peak GPU memory;
- the CPU side: features.sim_view per decision.
Positions are real mid-game held-out views; timings are medians of synchronised wall clock.

usage: bench_cost.py CKPT DATA_DIR
"""
import json
import statistics
import sys
import time

import numpy as np
import torch

from tools.selfplay import features as FT
from tools.selfplay import simulator as S
from tools.selfplay.ppo import chunks

ckpt, d = sys.argv[1], sys.argv[2]
ck = torch.load(ckpt, map_location="cpu", weights_only=False)
table = FT.CardTable.from_json(ck["table"])
dev = torch.device("cuda")
net = S.Simulator(table, **ck["config"]).to(dev).eval()
net.load_state_dict(ck["state"])
data = S.Data.load([d], table)
a = data.a
mid = np.flatnonzero(S.held_out(a["seed"]) & (a["turn"] >= 7) & (a["turn"] <= 12) & (a["h"] > 0))
rng = np.random.default_rng(186)
out = {"config": ck["config"], "window": ck["config"]["window"]}


def timed(fn, reps):
    fn()
    torch.cuda.synchronize()
    ts = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        torch.cuda.synchronize()
        ts.append((time.perf_counter() - t0) * 1000)
    return round(statistics.median(ts), 2)


@torch.no_grad()
def belief(b):
    o, p, cards = net.run(b, [])
    mh, ml = net.marg(o[:, 0]).chunk(2, -1)
    return torch.sigmoid(mh @ cards.T), torch.nn.functional.softplus(ml @ cards.T)


@torch.no_grad()
def world(b, k):
    """A hand, then the library contents given it, then the next k cards drawn from them."""
    hand = net.sample_hands(b)
    h, l, cap = b["h"], b["l"], b["cap"]
    lib_cap = cap - S.counts(hand, h, cap.shape[1]).long()
    lib = torch.zeros(len(h), max(1, int(l.max())), dtype=torch.long, device=dev)
    for t in range(lib.shape[1]):
        o, p, cards = net.run(b, [(hand, h, 0), (lib, l, 1)])
        logits = (net.lib_q(o[:, p + hand.shape[1] + t]) @ cards.T).float()
        logits = logits.masked_fill(~S.allowed(lib, l, lib_cap)[:, t], float("-inf"))
        lib[:, t] = torch.where(l > t, torch.multinomial(torch.softmax(logits, -1), 1)[:, 0], 0)
    pad = torch.arange(lib.shape[1], device=dev)[None] >= l[:, None]
    order = torch.rand(lib.shape, device=dev).masked_fill(pad, 2.0).argsort(1)
    return hand, lib.gather(1, order[:, :k])


def rep(b, n):
    return {k: v.repeat_interleave(n, 0) for k, v in b.items()}


one = data.batch(rng.choice(mid, 1), dev)
many = data.batch(rng.choice(mid, 128), dev)
out["batch-1 position: h, l"] = [int(one["h"][0]), int(one["l"][0])]
out["batch-128 positions: mean h, mean l"] = [round(float(many["h"].float().mean()), 2),
                                              round(float(many["l"].float().mean()), 2)]
out["belief (marginals), batch 1, ms"] = timed(lambda: belief(one), 50)
out["belief (marginals), batch 128 decisions, ms"] = timed(lambda: belief(many), 20)
for n in (1, 2, 32):
    b = rep(one, n)
    out[f"sample {n} hand(s) for one decision, ms"] = timed(lambda b=b: net.sample_hands(b), 10)
    for k in (3, 5):
        out[f"sample {n} hand(s) + library contents + next {k}, one decision, ms"] = timed(
            lambda b=b, k=k: world(b, k), 3)


@torch.no_grad()
def cheap(b, k):
    """A hand from the decoder, then k next cards drawn from the marginal head's expected library
    counts (an approximation: not conditioned on the sampled hand, draws independent)."""
    _, rate = belief(b)
    return net.sample_hands(b), torch.multinomial(rate.clamp(min=1e-9), k, replacement=True)


for n in (1, 32):
    b = rep(one, n)
    for k in (3, 5):
        out[f"sample {n} hand(s) + next {k} from the marginal head's counts, ms"] = timed(
            lambda b=b, k=k: cheap(b, k), 10)
torch.cuda.reset_peak_memory_stats()
w = world(rep(one, 32), 5)
out["peak GPU memory, 32 worlds of hand + library, MB"] = round(torch.cuda.max_memory_allocated() / 2**20, 1)

# one training step at the training minibatch (<= 512 positions, <= 131k tokens), bf16 autocast
net.train()
opt = torch.optim.AdamW(net.parameters(), lr=1e-9)
train_idx = np.flatnonzero(~S.held_out(a["seed"]))
lengths = data.lengths()[train_idx]
chunk = max(chunks(lengths, 512, 131072), key=len)
tb = data.batch(train_idx[chunk], dev)


def step():
    with torch.autocast("cuda", dtype=torch.bfloat16):
        lo = S.loss(net, tb)
    opt.zero_grad(set_to_none=True)
    lo.backward()
    opt.step()


torch.cuda.reset_peak_memory_stats()
out["training step, ms (positions in the batch)"] = [timed(step, 10), len(chunk)]
out["peak GPU memory, training step, MB"] = round(torch.cuda.max_memory_allocated() / 2**20, 1)
t0 = time.perf_counter()
for _ in range(20):
    data.batch(train_idx[chunk], dev)
out["CPU batch build for that step, ms"] = round((time.perf_counter() - t0) / 20 * 1000, 1)

# the CPU side at play time: features.sim_view at every real decision of a heuristic game
from tools.selfplay.heuristic import HeuristicAgent  # noqa: E402
from tools.selfplay.rig import play_game  # noqa: E402


class Timed(HeuristicAgent):
    ts: list = []

    def decide(self, ask, obs):
        if len(ask.options) > 1:
            t0 = time.perf_counter()
            FT.sim_view(obs.executor, ask.seat, ask, table, obs.ctx)
            self.ts.append((time.perf_counter() - t0) * 1000)
        return super().decide(ask, obs)


for seed in (7, 8, 9):
    play_game(seed, [Timed(), Timed()], deck_mode="coherent")
out["features.sim_view per decision, ms (median, p90, n)"] = [
    round(statistics.median(Timed.ts), 3), round(float(np.percentile(Timed.ts, 90)), 3), len(Timed.ts)]
print(json.dumps(out, indent=1))
