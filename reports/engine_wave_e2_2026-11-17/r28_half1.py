"""r28's v2 computes what it did, half 1 (main): the checkpoint loaded with main's code; heuristic
decisions of seeded games on the verified pools (every fourth decision the network could take,
up to 64 a set), encoded with the checkpoint's card table; its tokens, logits and value, fp32 and
bf16. Half 2 (r28_half2.py) loads the checkpoint with the branch's code and compares, bitwise.

    r28_half1.py <main checkout> <checkpoint> <out dir>
"""
import sys
from pathlib import Path

ROOT, CK, OUT = sys.argv[1], sys.argv[2], Path(sys.argv[3])
sys.path.insert(0, ROOT)
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(ROOT), MTG_bot.__file__
import torch  # noqa: E402

from tools.selfplay import features as FT  # noqa: E402
from tools.selfplay import model as M  # noqa: E402
from tools.selfplay.heuristic import HeuristicAgent  # noqa: E402
from tools.selfplay.rig import play_game  # noqa: E402

assert M.__file__.startswith(ROOT), M.__file__
torch.set_num_threads(2)
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
out = {"encodings": batches, "kinds": kinds, "n_ask": len(FT.ASK_KINDS),
       "ask_emb": net.ask_emb.weight.detach().clone()}
with torch.no_grad():
    b = M.collate(batches, "cpu")
    out["x"], _valid = net.tokens(b)
    out["logits"], out["value"] = net(b)
    half = net.to(torch.bfloat16)
    bb = {k: (v.to(torch.bfloat16) if v.is_floating_point() else v) for k, v in b.items()}
    out["x_bf16"], _valid = half.tokens(bb)
    out["logits_bf16"], out["value_bf16"] = half(bb)
OUT.mkdir(parents=True, exist_ok=True)
torch.save(out, OUT / "r28_main_outputs.pt")
print("main: ask rows", len(FT.ASK_KINDS), "| decisions", len(batches), "| kinds",
      sorted(set(kinds)), "| tokens", tuple(out["x"].shape))
