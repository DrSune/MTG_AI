"""r28's v2 computes what it did, half 2 (the branch): the checkpoint loaded with the branch's code
(model.load grows the ask table by the kinds appended since it, "divide" among them, each a copy
of "other"); half 1's decisions run through it, fp32 and bf16, compared bitwise with main's
outputs; and the same games replayed and encoded by the branch, compared where they coincide.

    r28_half2.py <worktree> <checkpoint> <dir of half 1>
"""
import sys
from pathlib import Path

WT, CK, DIR = sys.argv[1], sys.argv[2], Path(sys.argv[3])
sys.path.insert(0, WT)
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(WT), MTG_bot.__file__
import numpy as np  # noqa: E402
import torch  # noqa: E402

from tools.selfplay import features as FT  # noqa: E402
from tools.selfplay import model as M  # noqa: E402
from tools.selfplay.heuristic import HeuristicAgent  # noqa: E402
from tools.selfplay.rig import play_game  # noqa: E402

assert M.__file__.startswith(WT), M.__file__
torch.set_num_threads(2)
old = torch.load(DIR / "r28_main_outputs.pt", weights_only=False)
net, table, _ = M.load(CK)
w = net.ask_emb.weight.data
n_old = old["ask_emb"].shape[0]
rows_kept = torch.equal(w[:n_old], old["ask_emb"])
grown = {k: torch.equal(w[FT.ASK_INDEX[k]], w[FT.ASK_INDEX["other"]]) for k in FT.ASK_KINDS[n_old:]}
with torch.no_grad():
    b = M.collate(old["encodings"], "cpu")
    x, _valid = net.tokens(b)
    logits, value = net(b)
    half = net.to(torch.bfloat16)
    bb = {k: (v.to(torch.bfloat16) if v.is_floating_point() else v) for k, v in b.items()}
    x16, _valid = half.tokens(bb)
    logits16, value16 = half(bb)
print("branch: ask rows", len(FT.ASK_KINDS), "(main", old["n_ask"], ") | rows kept:", rows_kept,
      "| grown as other:", grown)
print("on main's", len(old["encodings"]), "decisions (kinds", sorted(set(old["kinds"])), "):",
      "fp32 tokens", torch.equal(x, old["x"]), "logits", torch.equal(logits, old["logits"]),
      "value", torch.equal(value, old["value"]), "| bf16 tokens", torch.equal(x16, old["x_bf16"]),
      "logits", torch.equal(logits16, old["logits_bf16"]), "value", torch.equal(value16, old["value_bf16"]))

net, table, _ = M.load(CK)
batches, kinds = [], []
seen = [0]
LIMIT = [0]


class Recording(HeuristicAgent):
    def decide(self, ask, obs):
        if len(ask.options) <= FT.MAX_OPTIONS:
            seen[0] += 1
            if seen[0] % 4 == 0 and len(batches) < LIMIT[0]:
                batches.append(FT.encode(obs.executor, ask.seat, ask, table))
                kinds.append(ask.kind)
        return super().decide(ask, obs)


for i, code in enumerate(("M21", "M20", "FDN")):
    LIMIT[0] = 64 * (i + 1)
    for seed in range(2):
        play_game(seed, [Recording(), Recording()], pool_mode="verified", set_code=code)
same = [a.keys() == c.keys() and all(a[k].dtype == c[k].dtype and np.array_equal(a[k], c[k]) for k in a)
        for a, c in zip(batches, old["encodings"])]
first_diff = next((i for i, s in enumerate(same) if not s), None)
print("replayed on the branch:", len(batches), "decisions | equal encodings", sum(same), "of",
      min(len(batches), len(old["encodings"])), "| first different at", first_diff,
      "| divide asks recorded", kinds.count("divide"))
