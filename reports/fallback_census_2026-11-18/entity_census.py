"""Do the network's options point at what they name? For every real decision of heuristic games
over a set's verified pool: the options whose card is not among the encoded entities (the option
then points at nothing), and the visible cards the entity caps leave out.
usage: entity_census.py SET GAMES SEED0 OUT.json"""
import collections
import json
import sys

sys.path.insert(0, "/home/sune/Desktop/MTG_AI")
from MTG_bot.core.executor.games import get_supply  # noqa: E402
from tools.selfplay import features as FT  # noqa: E402
from tools.selfplay.heuristic import HeuristicAgent  # noqa: E402
from tools.selfplay.rig import play_game  # noqa: E402

code, games, seed0, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
supply = get_supply("verified", code)
table = FT.CardTable.from_records({oid: r.card for oid, r in supply.pool.results.items()})
unresolved = collections.Counter()  # (kind, zone of the card) -> options pointing at nothing
asks_unresolved = collections.Counter()  # kind -> asks with one or more such options
dropped = collections.Counter()  # zone -> visible cards left out, summed over decisions
asks_dropped = collections.Counter()  # zone -> decisions leaving one or more out
most = collections.Counter()  # zone -> the most left out at one decision
decisions = 0


class Rec:
    name = "heuristic"

    def __init__(self) -> None:
        self.inner = HeuristicAgent()

    def decide(self, ask, obs):
        global decisions
        n = len(ask.options)
        if 1 < n <= FT.MAX_OPTIONS and ask.kind != "name":
            decisions += 1
            ex = obs.executor
            world = ex.world
            feats = FT.encode(ex, ask.seat, ask, table, obs.ctx)
            bad = 0
            for i, o in enumerate(ask.options):
                p = FT._OPTS[o.token]
                for col, h in ((1, p[1]), (2, p[2])):
                    if h is not None and h.namespace == "card" and feats["opts_i"][i, col] == 0:
                        z = world.zone_of(h).kind if h in world.cards else "gone"
                        unresolved[(ask.kind, z)] += 1
                        bad += 1
            if bad:
                asks_unresolved[ask.kind] += 1
            # the visible cards by zone, against the entities encoded
            me, opp = world.player_order[ask.seat], world.player_order[1 - ask.seat]
            vis = collections.Counter()
            for ph in (me, opp):
                zones = world.players[ph].zones
                for z in (FT.ZONE_BATTLEFIELD, FT.ZONE_GRAVEYARD, FT.ZONE_EXILE) + ((FT.ZONE_HAND,) if ph == me else ()):
                    if z in zones:
                        vis[z] += len(zones[z].entries)
            got = collections.Counter(FT.ZONES[int(zi)] for zi in feats["cards_i"][:, 1])
            for z, v in vis.items():
                miss = max(0, v - got.get(z, 0))
                if miss:
                    dropped[z] += miss
                    asks_dropped[z] += 1
                    most[z] = max(most[z], miss)
        return self.inner.decide(ask, obs)


for seed in range(seed0, seed0 + games):
    play_game(seed, [Rec(), Rec()], deck_mode="coherent", set_code=code, pool_mode="verified")
json.dump({"set": code, "games": games, "decisions": decisions,
           "unresolved_options": {f"{k} | {z}": v for (k, z), v in unresolved.most_common()},
           "asks_with_unresolved": dict(asks_unresolved),
           "dropped_cards": dict(dropped), "decisions_dropping": dict(asks_dropped),
           "most_dropped": dict(most)}, open(out, "w"), indent=1)
print(code, decisions, "decisions; asks with an option pointing at nothing:",
      sum(asks_unresolved.values()), "; decisions dropping cards:", dict(asks_dropped))
