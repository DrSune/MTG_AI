"""Old networks compute what they did (ontology round R12), half 2 (the branch): the base's
checkpoint loaded with the branch's code; its card table refreshed from the branch's compile of
every card of M21, M20 and FDN, records applied (CardTable.refresh), and the network grown to it
(model.extend_cards); then:
- the rows the refresh rebuilt (the cards whose tree the round changed) and the component tokens it
  appended, which start at zero;
- the old tokens no row reads any more (the folded predicates, members and nodes);
- the same games replayed (decks.json) and their decisions encoded by the branch, and the
  checkpoint's tokens, logits and value on half 1's decisions, bitwise against half 1.

    old_net_branch.py <worktree> <decks.json> <dir of half 1>
"""
import json
import sys
from pathlib import Path

WT, DECKS, DIR = str(Path(sys.argv[1]).resolve()), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, WT)
import MTG_bot

assert MTG_bot.__file__.startswith(WT), MTG_bot.__file__
import numpy as np
import torch

from MTG_bot.core.executor.games import compile_supply
from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import play_game

assert M.__file__.startswith(WT), M.__file__
net, table, _ = M.load(str(DIR / "old.pt"))
old = torch.load(DIR / "old_outputs.pt", weights_only=False)
records = {oid: r.card for code in ("M21", "M20", "FDN")
           for oid, r in compile_supply("all", code, require_verified=False).pool.results.items()}
fresh, stats = table.refresh(records)
before = net.ir_emb.weight.data.clone()
net = M.extend_cards(net, fresh)
after = net.ir_emb.weight.data
rows = [table.names[i] for i in range(len(table.oracle_ids)) if table.ir[i] != fresh.ir[i]]
read = {t for row in fresh.ir for t in row}
unused = sorted(table.ir_vocab[i] for i in range(1, len(table.ir_vocab))
                if i not in read and any(i in row for row in table.ir))
print(f"refresh: {stats['rows_changed']} rows rebuilt: {sorted(rows)}")
print(f"component tokens appended ({stats['tokens_added']}): {stats['new_tokens']}")
print("appended rows all zero:", bool(torch.all(after[before.shape[0]:] == 0)),
      "| old rows kept:", torch.equal(after[: before.shape[0]], before))
print(f"old tokens no row reads any more ({len(unused)}): {unused}")
batches = []
seen = [0]


class Recording(HeuristicAgent):
    """Half 1's sample: every fourth decision the network could take, up to 64."""

    def decide(self, ask, obs):
        if len(ask.options) <= FT.MAX_OPTIONS:
            seen[0] += 1
            if seen[0] % 4 == 0 and len(batches) < 64:
                batches.append(FT.encode(obs.executor, ask.seat, ask, fresh))
        return super().decide(ask, obs)


decks = json.loads(DECKS.read_text())
for code, pairs in decks.items():
    for seed, (a, b) in enumerate(pairs):
        play_game(seed, [Recording(), Recording()], pool_mode="verified", set_code=code,
                  decks=(tuple(a), tuple(b)))
same_encodings = len(batches) == len(old["encodings"]) and all(
    a.keys() == b.keys() and all(a[k].dtype == b[k].dtype and np.array_equal(a[k], b[k]) for k in a)
    for a, b in zip(batches, old["encodings"], strict=True))
with torch.no_grad():
    b = M.collate(old["encodings"], "cpu")
    x, _valid = net.tokens(b)
    logits, value = net(b)
print("branch: decisions", len(batches), "| encodings equal:", same_encodings,
      "| tokens equal:", torch.equal(x, old["x"]), "| logits equal:", torch.equal(logits, old["logits"]),
      "| value equal:", torch.equal(value, old["value"]))
