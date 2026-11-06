"""Mulligan rate of a checkpoint: mean P(mulligan) at the first mulligan declaration of both seats
on a fixed set of opening hands (coherent decks, M21 verified pool, seeds SEED0..SEED0+N-1), and
the greedy rate (share of hands with P(mulligan) > 0.5).

    PY mull_probe.py CKPT [N] [--watch RUN_DIR]   (--watch: re-probe RUN_DIR/last.pt whenever it
    changes, one JSON row per checkpoint iteration, until killed)
Run from the checkout whose code is measured.
"""

from __future__ import annotations

import json
import os
import sys
import time

import numpy as np
import torch

from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
from MTG_bot.core.executor.games import _play, _setup_game, deal_decks, get_supply
from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay.rig import SelfplayRouter

SEED0 = 7_000_000  # disjoint from training (10M+), eval (900k), gates (2M), preflight (3M)


class _Recorder:
    name = "rec"

    def __init__(self, table, out):
        self.table, self.out = table, out

    def decide(self, ask, obs):
        if ask.kind == "mulligan":
            self.out.append(FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx))
            return [o.token for o in ask.options].index("keep")
        return 0


def hands(table, n):
    supply = get_supply("verified", "M21")
    oracle = OracleIndex.for_sets("M21")
    feats = []
    for seed in range(SEED0, SEED0 + n):
        game = _setup_game(seed, supply, deal_decks(seed, 1409, supply, "coherent"))
        rec = _Recorder(table, feats)
        router = SelfplayRouter(game, [rec, rec], [SeatLens(s, oracle, ViewOptions()) for s in (0, 1)],
                                supply=supply)
        _play(game, router, game.world.player_order, 1,
              stop_after=lambda g, b: b == "turn_top")
    return feats


@torch.no_grad()
def rate(path, feats):
    net, _, extra = M.load(path, "cuda")
    net.eval()
    p = []
    for i in range(0, len(feats), 512):
        b = M.collate(feats[i:i + 512], "cuda")
        with torch.autocast("cuda", dtype=torch.bfloat16):
            logits, _ = net(b)
        probs = torch.softmax(logits.float(), -1)[:, :2].cpu().numpy()
        p.append(probs)
    p = np.concatenate(p)
    keep = FT.OPT_INDEX["keep"]
    col = [int(np.flatnonzero(f["opts_i"][:, 0] == FT.OPT_INDEX["mulligan"])[0]) for f in feats]
    assert all(int(f["opts_i"][1 - c, 0]) == keep for f, c in zip(feats, col))
    pm = p[np.arange(len(p)), col]
    return {"ckpt": path, "it": extra.get("it"), "hands": len(pm),
            "p_mulligan_mean": round(float(pm.mean()), 4),
            "greedy_mulligan_share": round(float((pm > 0.5).mean()), 4),
            "p_mulligan_q10_q50_q90": [round(float(x), 4) for x in np.quantile(pm, [0.1, 0.5, 0.9])]}


def main():
    path = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 1000
    _, table, _ = M.load(path, "cpu")
    feats = hands(table, n)
    if "--watch" not in sys.argv:
        print(json.dumps(rate(path, feats)), flush=True)
        return
    run = sys.argv[sys.argv.index("--watch") + 1]
    last = None
    while True:
        ck = os.path.join(run, "last.pt")
        if os.path.exists(ck) and os.path.getmtime(ck) != last:
            time.sleep(5)  # the save is complete
            last = os.path.getmtime(ck)
            try:
                row = rate(ck, feats)
            except Exception as e:  # noqa: BLE001 - a half-written file: retry next round
                print(json.dumps({"error": str(e)[:200]}), flush=True)
                last = None
                continue
            print(json.dumps({"t": round(time.time(), 1), **row}), flush=True)
        time.sleep(10)


if __name__ == "__main__":
    main()
