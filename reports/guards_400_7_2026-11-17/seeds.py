"""Pick the games of MTG_bot/core/test_executor_object_tables.py: per (set, seed), the containers
holding a card's handle that one random game fills (the test's own walk, at every point the game
loop stops), and a greedy cover of seeds reaching all of them. Also lists any container the
registry (Executor.OBJECT_TABLES) does not name.

    seeds.py <checkout> <games per set> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
from MTG_bot.core.executor import Executor, GameOver  # noqa: E402
from MTG_bot.core.executor.games import (  # noqa: E402
    TURN_CAP,
    RandomPolicy,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)
from MTG_bot.core.test_executor_object_tables import tables  # noqa: E402

N = int(sys.argv[2])
per: dict[str, list[str]] = {}
for code in ("M21", "M20", "FDN"):
    sup = get_supply("verified", code)
    for seed in range(N):
        found: set[str] = set()
        names: set[str] = set()
        game = _setup_game(seed, sup, deal_decks(seed, 1409, sup, "stress" if seed % 3 else "coherent"))

        def stop(g, _boundary):
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
