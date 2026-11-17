"""Old networks compute what they did, half 1 (the base): under the base's code, a randomly
initialised network with non-zero output layers, saved as a checkpoint; every fourth heuristic
decision (up to 64 per set) of three games each on the M21 and FDN verified pools, dealt from the
cards verified on both checkouts (Idol of Endurance, whose tree the round changes, taken out on both
sides), encoded by the base; and the base's tokens, logits and value on them. Half 2
(old_net_branch.py) loads the checkpoint with the branch's code and compares, bitwise. No decision
involves a permission: the verified pools hold no permission card once Idol is out.

    old_net_base.py <base checkout> <out dir>
"""
import dataclasses
import sys
from pathlib import Path

ROOT, OUT = sys.argv[1], Path(sys.argv[2])
sys.path.insert(0, ROOT)
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(ROOT), MTG_bot.__file__
import torch  # noqa: E402

from MTG_bot.core.executor import games  # noqa: E402
from tools.selfplay import features as FT  # noqa: E402
from tools.selfplay import model as M  # noqa: E402
from tools.selfplay.heuristic import HeuristicAgent  # noqa: E402
from tools.selfplay.rig import play_game  # noqa: E402

assert M.__file__.startswith(ROOT), M.__file__
SETS, OUT_OF_BOTH = ("M21", "FDN"), {"Idol of Endurance"}
records = {}
for code in SETS:
    supply = games.get_supply("verified", code)
    kept = tuple(o for o in supply.deckable if supply.metas[o].name not in OUT_OF_BOTH)
    games._SUPPLY_CACHE[f"verified:{code}"] = dataclasses.replace(supply, deckable=kept)
    records.update({oid: r.card for oid, r in supply.pool.results.items()})
table = FT.CardTable.from_records(records)
torch.manual_seed(0)
net = M.build(table, d=64, layers=2, heads=4, ff=128).eval()
with torch.no_grad():  # trained heads: the outputs read the tokens (built, they start at zero)
    net.policy_head[-1].weight.normal_(std=0.5)
    net.value_head[-1].weight.normal_(std=0.5)
batches: list = []
seen = [0]
limit = [0]


class Recording(HeuristicAgent):
    """Every fourth decision the network could take, up to 64 per set."""

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
