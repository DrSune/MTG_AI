"""Old networks compute what they did, half 1 (the base): under the base's code, a randomly
initialised network with non-zero output layers (its ask table the base's 32 rows), saved as a
checkpoint; up to 64 heuristic decisions of three FDN games on the verified pool (identical on both
checkouts), encoded by the base; and the base's tokens, logits and value on them. Half 2
(old_net_branch.py) loads the checkpoint with the branch's code and compares, bitwise.

    old_net_base.py <base checkout> <out dir>
"""
import sys
from pathlib import Path

ROOT, OUT = sys.argv[1], Path(sys.argv[2])
sys.path.insert(0, ROOT)
import MTG_bot

assert MTG_bot.__file__.startswith(ROOT), MTG_bot.__file__
import torch

from MTG_bot.core.executor.games import get_supply
from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import play_game

assert M.__file__.startswith(ROOT), M.__file__
supply = get_supply("verified", "FDN")
table = FT.CardTable.from_records({oid: r.card for oid, r in supply.pool.results.items()})
torch.manual_seed(0)
net = M.build(table, d=64, layers=2, heads=4, ff=128).eval()
with torch.no_grad():  # trained heads: the outputs read the tokens (built, they start at zero)
    net.policy_head[-1].weight.normal_(std=0.5)
    net.value_head[-1].weight.normal_(std=0.5)
batches = []
seen = [0]


class Recording(HeuristicAgent):
    """Every fourth decision the network could take, up to 64: the three games' early and late
    turns."""

    def decide(self, ask, obs):
        if len(ask.options) <= FT.MAX_OPTIONS:
            seen[0] += 1
            if seen[0] % 4 == 0 and len(batches) < 64:
                batches.append(FT.encode(obs.executor, ask.seat, ask, table))
        return super().decide(ask, obs)


for seed in range(3):
    play_game(seed, [Recording(), Recording()], pool_mode="verified", set_code="FDN")
with torch.no_grad():
    b = M.collate(batches, "cpu")
    x, _valid = net.tokens(b)
    logits, value = net(b)
OUT.mkdir(parents=True, exist_ok=True)
M.save(str(OUT / "old.pt"), net, table)
torch.save({"encodings": batches, "x": x, "logits": logits, "value": value,
            "n_ask": len(FT.ASK_KINDS)}, OUT / "old_outputs.pt")
print("base: ask rows", len(FT.ASK_KINDS), "| decisions", len(batches), "| ask kinds seen",
      sorted({FT.ASK_KINDS[int(f["ask_i"][0])] for f in batches}), "| tokens", tuple(x.shape))
