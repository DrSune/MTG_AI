"""Replay one detector game exactly (the same seeds and sampling), and print the state at the asks
of one kind: the step, the stack, and the asking seat's library top and size. To read a decision
of nothing the signature cannot explain by itself (§2.1).

    .venv/bin/python reports/network_readiness_2026-11-18/inspect_game.py CKPT SEED KIND
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402
import torch  # noqa: E402

from MTG_bot.core.state import ZONE_LIBRARY  # noqa: E402
from tools.selfplay import features as FT  # noqa: E402
from tools.selfplay import model as M  # noqa: E402
from tools.selfplay.rig import play_game  # noqa: E402


class Driver:
    def __init__(self, net, table, rng, kind):
        self.net, self.table, self.rng, self.kind = net, table, rng, kind
        self.name = "net"

    @torch.no_grad()
    def decide(self, ask, obs):
        if len(ask.options) == 1:
            return 0
        feats = FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx)
        logits, value = self.net(M.collate([feats], "cpu"))
        probs = torch.softmax(logits[0, : len(ask.options)].float(), -1).numpy().astype(np.float64)
        probs /= probs.sum()
        pick = int(self.rng.choice(len(probs), p=probs))
        if ask.kind == self.kind:
            ex = obs.executor
            w = ex.world
            me = w.player_order[ask.seat]
            lib = w.players[me].zone(ZONE_LIBRARY).entries
            top = [w.cards[h].identity.name for h in reversed(lib[-4:])]
            stack = [w.cards[f.source if f.spell_kind in ("ACTIVATED", "TRIGGERED") else f.handle].identity.name
                     for f in reversed(ex.stack.frames) if (f.source if f.spell_kind in ("ACTIVATED", "TRIGGERED") else f.handle) in w.cards]
            print(f"turn {w.turn} {ex.phase} seat {ask.seat} {ask.site} library {len(lib)} top {top} "
                  f"stack {stack} options {[o.token for o in ask.options]} pick {pick}", flush=True)
        return pick


def main() -> int:
    ckpt, seed, kind = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    torch.set_num_threads(1)
    net, table, _ = M.load(ckpt, "cpu")
    rng = np.random.default_rng(seed)
    set_code = "M20" if rng.random() < 0.25 else "M21"
    drivers = [Driver(net, table, np.random.default_rng(seed * 2 + s), kind) for s in (0, 1)]
    res = play_game(seed, drivers, deck_mode="coherent", pool_mode="verified", set_code=set_code)
    print(set_code, res["outcome"], res["turns"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
