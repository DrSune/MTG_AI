"""Old networks compute what they did (ontology round R12), half 1 (the base): a randomly initialised
network over the base's card table (every card of M21, M20 and FDN as the base compiles it, its card
record applied, verified or not, as half 2 refreshes it), its output layers non-zero, saved as a checkpoint; up to 64 heuristic decisions of the
three FDN and three M21 games of decks.json (old_net_decks.py: cards the round leaves unchanged),
encoded by the base; and the base's tokens, logits and value on them. Half 2 (old_net_branch.py)
loads the checkpoint with the branch's code, refreshes its card table and compares.

    old_net_base.py <base checkout> <decks.json> <out dir>
"""
import json
import sys
from pathlib import Path

ROOT, DECKS, OUT = str(Path(sys.argv[1]).resolve()), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, ROOT)
import MTG_bot

assert MTG_bot.__file__.startswith(ROOT), MTG_bot.__file__
import torch

from MTG_bot.core.executor.games import compile_supply
from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import play_game

assert M.__file__.startswith(ROOT), M.__file__
records = {oid: r.card for code in ("M21", "M20", "FDN")
           for oid, r in compile_supply("all", code, require_verified=False).pool.results.items()}
table = FT.CardTable.from_records(records)
torch.manual_seed(0)
net = M.build(table, d=64, layers=2, heads=4, ff=128).eval()
with torch.no_grad():  # trained heads: the outputs read the tokens (built, they start at zero)
    net.policy_head[-1].weight.normal_(std=0.5)
    net.value_head[-1].weight.normal_(std=0.5)
batches = []
seen = [0]


class Recording(HeuristicAgent):
    """Every fourth decision the network could take, up to 64."""

    def decide(self, ask, obs):
        if len(ask.options) <= FT.MAX_OPTIONS:
            seen[0] += 1
            if seen[0] % 4 == 0 and len(batches) < 64:
                batches.append(FT.encode(obs.executor, ask.seat, ask, table))
        return super().decide(ask, obs)


decks = json.loads(DECKS.read_text())
for code, pairs in decks.items():
    for seed, (a, b) in enumerate(pairs):
        play_game(seed, [Recording(), Recording()], pool_mode="verified", set_code=code,
                  decks=(tuple(a), tuple(b)))
with torch.no_grad():
    b = M.collate(batches, "cpu")
    x, _valid = net.tokens(b)
    logits, value = net(b)
OUT.mkdir(parents=True, exist_ok=True)
M.save(str(OUT / "old.pt"), net, table)
torch.save({"encodings": batches, "x": x, "logits": logits, "value": value}, OUT / "old_outputs.pt")
print("base: cards", len(table.oracle_ids), "| component tokens", len(table.ir_vocab), "| decisions",
      len(batches), "| tokens", tuple(x.shape))
