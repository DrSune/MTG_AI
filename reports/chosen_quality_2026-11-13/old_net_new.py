"""M2 exactness, half 1 (the branch): a randomly initialised net (its ir_emb padding row random,
as _init leaves it and as every checkpoint holds it), the batches of up to 64 heuristic decisions
of FDN castable games taken while no chosen value is on the board and no quality ask is open (what
the base can encode), and the branch's tokens and outputs on them. Saved for half 2, which
computes the base's on the same weights and the same batches cut to the base's widths (CI 7,
OI 4).

    old_net_new.py <worktree> <out.pt>
"""
import sys

WT, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, WT)
import MTG_bot

assert MTG_bot.__file__.startswith(WT), MTG_bot.__file__
import torch

from MTG_bot.core.executor.games import get_supply
from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import play_game

supply = get_supply("castable", "FDN")
table = FT.CardTable.from_records({oid: r.card for oid, r in supply.pool.results.items()})
torch.manual_seed(0)
net = M.build(table, d=64, layers=2, heads=4, ff=128).eval()
assert net.ir_emb.weight[0].abs().max() > 0  # the padding row is random, as on r28
with torch.no_grad():  # trained heads: the outputs read the tokens (built, they start at zero)
    net.policy_head[-1].weight.normal_(std=0.5)
    net.value_head[-1].weight.normal_(std=0.5)

batches = []


class Recording(HeuristicAgent):
    """The heuristic, encoding the asks it answers while no chosen value is on the board."""

    def decide(self, ask, obs):
        ex = obs.executor
        if (ask.kind != "quality" and not any(q for (_s, q) in ex.name_choices)
                and len(batches) < 64):
            f = FT.encode(ex, ask.seat, ask, table)
            if f["opts_i"].shape[0] <= FT.MAX_OPTIONS:
                batches.append(f)
        return super().decide(ask, obs)


for seed in range(3):
    play_game(seed, [Recording(), Recording()], pool_mode="castable", set_code="FDN")
assert batches, "no decision recorded"
with torch.no_grad():
    b = M.collate(batches, "cpu")
    x, valid = net.tokens(b)
    logits, value = net(b)
torch.save({"state": net.state_dict(), "config": net.config, "ir_table": net.ir_table.clone(),
            "batch": {k: v.clone() for k, v in b.items()}, "x": x, "logits": logits,
            "value": value, "n_ask": len(FT.ASK_KINDS)}, OUT)
print("decisions", len(batches), "tokens", tuple(x.shape), "C_CHOSEN any",
      bool(b["cards_i"][..., FT.C_CHOSEN].any()), "O_VALUE any",
      bool(b["opts_i"][..., FT.O_VALUE].any()))
