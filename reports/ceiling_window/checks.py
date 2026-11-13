"""Two CPU checks behind the ceiling window's registration (REGISTRATION_DRAFT.md §1, §5).

    env PYTHONPATH=. .venv/bin/python reports/ceiling_window/checks.py members CKPT...
    env PYTHONPATH=. .venv/bin/python reports/ceiling_window/checks.py newcards PIN SEED0 N

- members: each checkpoint's file hash and update, then every pair that is one network once
  model.load has built both (every tensor equal), with whether their card tables are equal too.
  Such a pair is one player in the held-out pool L.
- newcards: the M21 cards verified here but not at commit PIN, which a network trained at PIN never
  met, and their copies in each deal shape's decks over the seeds SEED0 .. SEED0 + N - 1.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from itertools import combinations
from pathlib import Path

CRITIC = "/home/sune/Desktop/MTG_AI/runs/window2/critic_r27.json"


def members(paths: list[str]) -> None:
    import torch

    from tools.selfplay import model as M

    nets = {}
    for p in paths:
        net, table, extra = M.load(p, "cpu")
        nets[p] = (net.state_dict(), table.to_json())
        sha = hashlib.sha256(Path(p).read_bytes()).hexdigest()[:16]
        print(json.dumps({"ckpt": p, "sha256": sha, "it": extra.get("it")}))
    for a, b in combinations(paths, 2):
        (sa, ta), (sb, tb) = nets[a], nets[b]
        if sa.keys() == sb.keys() and all(sa[k].shape == sb[k].shape and torch.equal(sa[k], sb[k])
                                          for k in sa):
            print(json.dumps({"one_network": [a, b], "tables_equal": ta == tb}))


def newcards(pin: str, seed0: int, n: int) -> None:
    from MTG_bot.core.executor.games import deal_decks, get_supply
    from tools.selfplay import decks as DK
    from tools.selfplay import packages as PK

    tree = DK.extract(pin)  # the pin's MTG_bot, imported alone in a child process (-P)
    code = ("import json; from MTG_bot.core.executor.games import get_supply; "
            "print(json.dumps(sorted(get_supply('verified', 'M21').deckable)))")
    out = subprocess.run([sys.executable, "-P", "-c", code], cwd=tree, check=True, text=True,
                         capture_output=True, env={**os.environ, "PYTHONPATH": str(tree)}).stdout
    sup, pinned = get_supply("verified", "M21"), set(json.loads(out.splitlines()[-1]))
    new = set(sup.deckable) - pinned
    gone = pinned - set(sup.deckable)  # verified at PIN, not here: names from the castable pool
    names = get_supply("castable", "M21").metas
    print(json.dumps({"verified_here": len(sup.deckable), "verified_at_pin": len(pinned),
                      "new": sorted(sup.metas[c].name for c in new),
                      "gone": sorted(names[c].name if c in names else c for c in gone)}))
    critic = json.loads(Path(CRITIC).read_text())
    deal = {"coherent": lambda s: deal_decks(s, DK.DEAL_SEED, sup, "coherent"),
            "package": lambda s: PK.package_decks(s, sup),
            "drafted": lambda s: DK.drafted_decks(s, f"drafted:8:{critic['sha256'][:8]}", None, sup,
                                                  critic, "M21")}
    for shape, decks_of in deal.items():
        copies = spells = deals_with = 0
        for seed in range(seed0, seed0 + n):
            pair = decks_of(seed)
            hit = [c for deck in pair for c in deck if c in new]
            copies += len(hit)
            spells += sum(not sup.metas[c].is_land for deck in pair for c in deck)
            deals_with += bool(hit)
        print(json.dumps({"shape": shape, "deals": n,
                          "new_copies_per_deck": round(copies / (2 * n), 3),
                          "share_of_spells": round(copies / spells, 4),
                          "deals_with_one": round(deals_with / n, 3)}))


if __name__ == "__main__":
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "members":
        members(rest)
    elif cmd == "newcards":
        newcards(rest[0], int(rest[1]), int(rest[2]))
    else:
        raise SystemExit(f"unknown check {cmd!r}: members or newcards")
