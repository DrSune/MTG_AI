"""Pick the games of MTG_bot/core/test_executor_object_tables.py on the recorded cards (its CARDS):
per (set, seed), the containers holding a card's handle that one random game fills (the test's
own walk, wherever the game loop stops after something happened), and a greedy cover of seeds
reaching all of them. Also lists any container the registry (Executor.OBJECT_TABLES) does not name.

    seeds.py <checkout> <games per set> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from MTG_bot.core.executor import Executor, GameOver  # noqa: E402
from MTG_bot.core.executor.games import TURN_CAP, RandomPolicy, _play, _setup_game, deal_decks  # noqa: E402
from MTG_bot.core.test_executor_object_tables import recorded_supply, tables  # noqa: E402

N = int(sys.argv[2])
per: dict[str, list[str]] = {}
for code in ("M21", "M20", "FDN"):
    sup = recorded_supply(code)
    for seed in range(N):
        found: set[str] = set()
        names: set[str] = set()
        last = [(-1, -1)]
        game = _setup_game(seed, sup, deal_decks(seed, 1409, sup, "stress" if seed % 3 else "coherent"))

        def stop(g, _boundary):
            now = (len(g.executor.journal.events), len(g.executor.stack.frames))
            if now != last[0]:
                last[0] = now
                tables(g.executor, found, names)
            return False

        try:
            _play(game, RandomPolicy(seed), game.world.player_order, TURN_CAP, stop_after=stop)
        except GameOver:
            pass
        tables(game.executor, found, names)
        per[f"{code}:{seed}"] = sorted(found)
    print(code, "done", file=sys.stderr)
Path(sys.argv[3]).write_text(json.dumps(per))
universe = set().union(*map(set, per.values()))
print(len(universe), "containers; not in the registry:", sorted(universe - set(Executor.OBJECT_TABLES)))
print("registry entries no game filled:", sorted(set(Executor.OBJECT_TABLES) - universe))
cover, left = [], set(universe)
while left:
    best = max(per, key=lambda k: len(left & set(per[k])))
    cover.append(best)
    left -= set(per[best])
print("cover:", cover)
got: set[str] = set()
for k in cover:
    print(k, len(per[k]), "adds", sorted(set(per[k]) - got))
    got |= set(per[k])
test_games = {"M21": (9, 2, 16), "M20": (7, 18), "FDN": (22,)}
now = set().union(*(set(per[f"{c}:{s}"]) for c, seeds in test_games.items() for s in seeds if f"{c}:{s}" in per))
print("the test's current games fill", len(now), "; missing:", sorted(universe - now))
