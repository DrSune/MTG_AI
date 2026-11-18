"""Which asks would the network not answer (more than MAX_OPTIONS options, or a name ask)?
Heuristic against heuristic over a set's verified pool, coherent decks (r29's training deals).
usage: overflow_census.py SET GAMES SEED0 OUT.json"""
import collections
import json
import re
import sys
import time

sys.path.insert(0, "/home/sune/Desktop/MTG_AI")
from MTG_bot.core.identity import Handle  # noqa: E402
from tools.selfplay import features as FT  # noqa: E402
from tools.selfplay.heuristic import HeuristicAgent  # noqa: E402
from tools.selfplay.rig import play_game  # noqa: E402

CARD = re.compile(r"card:(\d+)")
code, games, seed0, out = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
over = collections.Counter()  # (kind, source name) -> asks
sizes = collections.defaultdict(collections.Counter)  # kind -> size bin -> asks
examples: dict = {}
decisions = 0


class Rec:
    name = "heuristic"

    def __init__(self) -> None:
        self.inner = HeuristicAgent()

    def decide(self, ask, obs):
        global decisions
        n = len(ask.options)
        if n > 1:
            decisions += 1
            sizes[ask.kind][min(n, 400) // 16 * 16] += 1
        if n > FT.MAX_OPTIONS or ask.kind == "name":
            m = CARD.search(ask.site)
            src = "?"
            if m:
                c = obs.executor.world.cards.get(Handle("card", int(m.group(1))))
                src = c.identity.name if c is not None else "gone"
            key = (ask.kind, src)
            over[key] += 1
            examples.setdefault(f"{ask.kind} | {src}", (n, ask.site, ask.prompt[:160],
                                                         [o.label for o in ask.options[:6]]))
        return self.inner.decide(ask, obs)


t0 = time.monotonic()
voids = 0
for seed in range(seed0, seed0 + games):
    r = play_game(seed, [Rec(), Rec()], deck_mode="coherent", set_code=code, pool_mode="verified")
    voids += r["outcome"].startswith("void")
json.dump({"set": code, "games": games, "voids": voids, "decisions": decisions,
           "wall_s": round(time.monotonic() - t0, 1),
           "overflow": {f"{k} | {s}": v for (k, s), v in over.most_common()},
           "examples": examples,
           "sizes": {k: dict(sorted(v.items())) for k, v in sizes.items()}},
          open(out, "w"), indent=1)
print(code, games, "games", round(time.monotonic() - t0, 1), "s; overflow asks", sum(over.values()),
      "of", decisions, "decisions")
