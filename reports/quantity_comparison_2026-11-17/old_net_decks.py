"""Old networks compute what they did (ontology round R12), half 0 (the branch): the decks of three
FDN and three M21 games, dealt from the branch's verified pools. The round only takes cards out of
the verified pools (tree_diff.py: 58 leave, none join), so these cards are verified with the same
tree on both checkouts, and the two halves play the same games.

    old_net_decks.py <worktree> <decks.json>
"""
import json
import sys
from pathlib import Path

WT = str(Path(sys.argv[1]).resolve())
sys.path.insert(0, WT)
import MTG_bot

assert MTG_bot.__file__.startswith(WT), MTG_bot.__file__
from MTG_bot.core.executor.games import deal_decks, get_supply

decks = {code: [deal_decks(seed, 1409, get_supply("verified", code), "stress") for seed in range(3)]
         for code in ("FDN", "M21")}
Path(sys.argv[2]).write_text(json.dumps(decks))
print({code: [len(d[0]) for d in pairs] for code, pairs in decks.items()})
