"""Old networks compute what they did, half 2 (the branch): the base's checkpoint loaded with the
branch's code (model.load grows the ask table by the two appended kinds, "exile" and
"remove_counter", each a copy of "other"); the same three FDN games replayed and their decisions
encoded by the branch with the checkpoint's table; then, bitwise against half 1: the encodings,
and the tokens, logits and value.

    old_net_branch.py <worktree> <dir of half 1>
"""
import sys
from pathlib import Path

WT, DIR = sys.argv[1], Path(sys.argv[2])
sys.path.insert(0, WT)
import MTG_bot

assert MTG_bot.__file__.startswith(WT), MTG_bot.__file__
import numpy as np
import torch

from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import play_game

assert M.__file__.startswith(WT), M.__file__
net, table, _ = M.load(str(DIR / "old.pt"))
old = torch.load(DIR / "old_outputs.pt", weights_only=False)
w = net.ask_emb.weight.data
grown = {k: torch.equal(w[FT.ASK_INDEX[k]], w[FT.ASK_INDEX["other"]]) for k in ("exile", "remove_counter")}
batches = []
seen = [0]


class Recording(HeuristicAgent):
    """Half 1's sample: every fourth decision the network could take, up to 64."""

    def decide(self, ask, obs):
        if len(ask.options) <= FT.MAX_OPTIONS:
            seen[0] += 1
            if seen[0] % 4 == 0 and len(batches) < 64:
                batches.append(FT.encode(obs.executor, ask.seat, ask, table))
        return super().decide(ask, obs)


for seed in range(3):
    play_game(seed, [Recording(), Recording()], pool_mode="verified", set_code="FDN")
same_encodings = len(batches) == len(old["encodings"]) and all(
    a.keys() == b.keys() and all(a[k].dtype == b[k].dtype and np.array_equal(a[k], b[k]) for k in a)
    for a, b in zip(batches, old["encodings"], strict=True))
with torch.no_grad():
    b = M.collate(old["encodings"], "cpu")
    x, _valid = net.tokens(b)
    logits, value = net(b)
print("branch: ask rows", len(FT.ASK_KINDS), "(checkpoint", old["n_ask"], ") | grown as other:", grown,
      "| decisions", len(batches), "| encodings equal:", same_encodings,
      "| tokens equal:", torch.equal(x, old["x"]), "| logits equal:", torch.equal(logits, old["logits"]),
      "| value equal:", torch.equal(value, old["value"]))
