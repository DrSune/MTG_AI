"""M2 exactness, half 2 (the base): the same weights in the base's network (its ask table one row
shorter: "quality" is the appended row), the same batches cut to the base's widths, and a bitwise
comparison of tokens, logits and value with half 1's.

    old_net_base.py <base export> <in.pt>
"""
import sys

ROOT, IN = sys.argv[1], sys.argv[2]
sys.path.insert(0, ROOT)
import MTG_bot

assert MTG_bot.__file__.startswith(ROOT), MTG_bot.__file__
import torch

from tools.selfplay import features as FT
from tools.selfplay import model as M

assert M.__file__.startswith(ROOT), M.__file__
saved = torch.load(IN, weights_only=False)
cfg = dict(saved["config"])
net = M.PolicyValueNet(cfg.pop("n_cards"), cfg.pop("n_ir"), saved["ir_table"].numpy(), **cfg).eval()
state = dict(saved["state"])
n_base = len(FT.ASK_KINDS)
assert saved["n_ask"] == n_base + 1, (saved["n_ask"], n_base)
state["ask_emb.weight"] = state["ask_emb.weight"][:n_base]
net.load_state_dict(state)
b = dict(saved["batch"])
assert b["cards_i"].shape[-1] == FT.CI + 1 and b["opts_i"].shape[-1] == 4 + 1
b["cards_i"] = b["cards_i"][..., :FT.CI].contiguous()
b["opts_i"] = b["opts_i"][..., :4].contiguous()
with torch.no_grad():
    x, _valid = net.tokens(b)
    logits, value = net(b)
print("base widths", FT.CI, 4, "| tokens equal:", torch.equal(x, saved["x"]),
      "| logits equal:", torch.equal(logits, saved["logits"]),
      "| value equal:", torch.equal(value, saved["value"]),
      "| max |dx|:", float((x - saved["x"]).abs().max()))
