"""Hash of 30 seeded games (digest, world fingerprint, end reason): run it before and after an
engine change; an optimisation must leave the hash unchanged.

    .venv/bin/python -m tools.selfplay.games_hash
"""

import hashlib
import random
import time

from MTG_bot.bench.agents import UniformRandomAgent
from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
from MTG_bot.core.executor.games import (
    TURN_CAP,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import SelfplayRouter

supply = get_supply("castable", "M21"); oracle = OracleIndex.for_sets("M21")
h = hashlib.sha256(); t0 = time.time(); n_ev = 0
for seed in range(700, 730):
    game = _setup_game(seed, supply, deal_decks(seed, 1409, supply, "stress" if seed % 2 else "coherent"))
    agents = [HeuristicAgent(), UniformRandomAgent(random.Random(seed))] if seed % 3 else [HeuristicAgent(), HeuristicAgent()]
    router = SelfplayRouter(game, agents, [SeatLens(s, oracle, ViewOptions()) for s in (0, 1)], supply=supply)
    try:
        _play(game, router, game.world.player_order, TURN_CAP); err = ""
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"
    n_ev += len(game.executor.journal.events)
    h.update("|".join(game.digest).encode()); h.update(game.world.fingerprint().encode()); h.update(f"{game.reason}{err}".encode())
print(f"hash {h.hexdigest()[:16]} events {n_ev} secs {time.time() - t0:.1f}")
