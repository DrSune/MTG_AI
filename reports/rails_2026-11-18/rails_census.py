"""How the game-length and action rails bind: heuristic games with both rails lifted far out of
reach (turn cap 300, 1000 actions a step). Per game: turns, how it ended, the most actions one
player took in one step (casts and non-mana activations), quarantined trigger sources.
usage: rails_census.py SET GAMES SEED0 OUT.json"""
import collections
import json
import sys

sys.path.insert(0, "/home/sune/Desktop/MTG_AI")
from MTG_bot.core.executor import games as G  # noqa: E402
from MTG_bot.core.executor.events import KIND_ABILITY_ACTIVATED, KIND_CAST, KIND_TURN_PHASE  # noqa: E402
from tools.selfplay.heuristic import HeuristicAgent  # noqa: E402
from tools.selfplay import rig  # noqa: E402

code, games, seed0, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
G.MAX_ACTS_PER_STEP = 1000
rows = []
keep = {}


class Keep(HeuristicAgent):
    """Remembers the live game so its journal can be read after play_game returns."""
    def decide(self, ask, obs):
        keep["ex"] = obs.executor
        return super().decide(ask, obs)


for seed in range(seed0, seed0 + games):
    r = rig.play_game(seed, [Keep(), Keep()], deck_mode="coherent", set_code=code,
                      pool_mode="verified", turn_cap=300)
    ex = keep.pop("ex", None)
    most, quarantined = 0, 0
    if ex is not None:
        per = collections.Counter()
        step = 0
        for e in ex.journal.events:
            if e.kind == KIND_TURN_PHASE:
                step += 1
            elif e.kind == KIND_CAST:
                per[(step, e.data[0])] += 1
            elif e.kind == KIND_ABILITY_ACTIVATED and not e.data[1]:
                per[(step, e.cause)] += 1
        most = max(per.values(), default=0)
        quarantined = len(ex.binder.quarantined)
    rows.append({"seed": seed, "turns": r["turns"], "outcome": r["outcome"], "reason": r["reason"],
                 "most_acts": most, "quarantined": quarantined})
turns = [x["turns"] for x in rows]
print(code, len(rows), "games; turns > 60:", sum(t > 60 for t in turns), "max", max(turns),
      "; reasons of the long ones:", collections.Counter(x["reason"] for x in rows if x["turns"] > 60).most_common(4),
      "; most acts in a step: max", max(x["most_acts"] for x in rows),
      ">= 10:", sum(x["most_acts"] >= 10 for x in rows), "; quarantines:", sum(x["quarantined"] > 0 for x in rows),
      "; outcomes:", collections.Counter(x["outcome"] for x in rows).most_common(4))
json.dump(rows, open(out, "w"))
