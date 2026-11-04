"""Old vs new GameWorld.zone_of: identical games (digest + fingerprint) on 20 seeded games.

    .venv/bin/python -m tools.selfplay.zone_identity
"""

import random
import time

from MTG_bot.bench.agents import UniformRandomAgent
from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
from MTG_bot.core import state as S
from MTG_bot.core.executor.games import (
    TURN_CAP,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import SelfplayRouter

new_zone_of = S.GameWorld.zone_of
def old_zone_of(self, card):
    if card not in self.cards:
        raise KeyError(f"unknown card {card}")
    for player in self.player_order:
        for zone in self.players[player].zones.values():
            if zone.contains(card):
                return zone
    raise KeyError(f"card {card} is not in any zone")

supply = get_supply("castable", "M21"); oracle = OracleIndex.for_sets("M21")
def run(seed):
    game = _setup_game(seed, supply, deal_decks(seed, 1409, supply, "stress" if seed % 2 else "coherent"))
    agents = [HeuristicAgent(), UniformRandomAgent(random.Random(seed))] if seed % 3 else [HeuristicAgent(), HeuristicAgent()]
    router = SelfplayRouter(game, agents, [SeatLens(s, oracle, ViewOptions()) for s in (0, 1)], supply=supply)
    try:
        _play(game, router, game.world.player_order, TURN_CAP)
        err = None
    except Exception as e:  # compare crashes too
        err = f"{type(e).__name__}: {e}"
    return ("|".join(game.digest), game.world.fingerprint(), game.reason, err)

out = {}
for name, fn in (("old", old_zone_of), ("new", new_zone_of)):
    S.GameWorld.zone_of = fn
    t0 = time.time(); out[name] = [run(seed) for seed in range(500, 520)]; print(name, round(time.time() - t0, 1), "s")
same = sum(a == b for a, b in zip(out["old"], out["new"]))
print(f"identical games: {same}/20; digests total length {sum(len(x[0]) for x in out['new'])}; crashes {sum(x[3] is not None for x in out['new'])}")
