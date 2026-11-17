"""Old networks compute what they did, half 2 (the branch): the base's checkpoint loaded with the
branch's code (the round adds no ask kind and no option type: a permission's row is a cast row
with a second entity); the same games replayed on the same pools and their decisions encoded by
the branch with the checkpoint's table; then, bitwise against half 1: the encodings, and the
tokens, logits and value.

    old_net_branch.py <worktree> <dir of half 1>
"""
import dataclasses
import sys
from pathlib import Path

WT, DIR = sys.argv[1], Path(sys.argv[2])
sys.path.insert(0, WT)
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(WT), MTG_bot.__file__
import numpy as np  # noqa: E402
import torch  # noqa: E402

from MTG_bot.core.executor import games  # noqa: E402
from tools.selfplay import features as FT  # noqa: E402
from tools.selfplay import model as M  # noqa: E402
from tools.selfplay.heuristic import HeuristicAgent  # noqa: E402
from tools.selfplay.rig import play_game  # noqa: E402

assert M.__file__.startswith(WT), M.__file__
SETS, OUT_OF_BOTH = ("M21", "FDN"), {"Idol of Endurance"}
for code in SETS:
    supply = games.get_supply("verified", code)
    kept = tuple(o for o in supply.deckable if supply.metas[o].name not in OUT_OF_BOTH)
    games._SUPPLY_CACHE[f"verified:{code}"] = dataclasses.replace(supply, deckable=kept)
net, table, _ = M.load(str(DIR / "old.pt"))
old = torch.load(DIR / "old_outputs.pt", weights_only=False)
batches: list = []
seen = [0]
limit = [0]


class Recording(HeuristicAgent):
    """Half 1's sample: every fourth decision the network could take, up to 64 per set."""

    def decide(self, ask, obs):
        if len(ask.options) <= FT.MAX_OPTIONS:
            seen[0] += 1
            if seen[0] % 4 == 0 and len(batches) < limit[0]:
                batches.append(FT.encode(obs.executor, ask.seat, ask, table))
        return super().decide(ask, obs)


for code in SETS:
    limit[0] += 64
    for seed in range(3):
        play_game(seed, [Recording(), Recording()], pool_mode="verified", set_code=code)
same_encodings = len(batches) == len(old["encodings"]) and all(
    a.keys() == b.keys() and all(a[k].dtype == b[k].dtype and np.array_equal(a[k], b[k]) for k in a)
    for a, b in zip(batches, old["encodings"], strict=True))
with torch.no_grad():
    b = M.collate(old["encodings"], "cpu")
    x, _valid = net.tokens(b)
    logits, value = net(b)
print("branch: ask rows", len(FT.ASK_KINDS), "(checkpoint", old["n_ask"], ") | decisions", len(batches),
      "| encodings equal:", same_encodings, "| tokens equal:", torch.equal(x, old["x"]),
      "| logits equal:", torch.equal(logits, old["logits"]), "| value equal:", torch.equal(value, old["value"]))
