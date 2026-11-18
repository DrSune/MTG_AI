"""Heuristic games dealing round B12's cards (DESIGN_ATOM_ONTOLOGY §19), records applied verified or
not: M20's castable pool, every deck also holding four of each round card (the Leylines, Rule of
Law, Grafdigger's Cage), so the opening-hand step and the prohibitions run in real games. Per
set: games, crashes (with their class), pregame may asks (opening-hand actions offered), Leylines
begun on the battlefield, casts refused by a prohibition at an act window (a menu without the
row), moves and gains a prohibition stopped, game results by kind.

    soak.py <checkout> <games> <out.json>
"""
from __future__ import annotations

import dataclasses
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__

from MTG_bot.core.executor import games  # noqa: E402
from tools.selfplay import rig  # noqa: E402
from tools.selfplay.heuristic import HeuristicAgent  # noqa: E402

ROUND = ("Leyline of Sanctity", "Leyline of the Void", "Leyline of Anticipation",
         "Leyline of Combustion", "Leyline of Abundance", "Rule of Law", "Grafdigger's Cage")
captured: dict[str, object] = {}
setup = rig._setup_game


def capture(*args, **kwargs):
    captured["game"] = game = setup(*args, **kwargs)
    return game


rig._setup_game = capture


class Counting(HeuristicAgent):
    def __init__(self) -> None:
        super().__init__()
        self.pregame_may = 0
        self.started = False

    def decide(self, ask, obs):
        self.started = self.started or ask.kind in ("act", "priority")
        if ask.kind == "may" and not self.started:
            self.pregame_may += 1
        return super().decide(ask, obs)


n = int(sys.argv[2])
supply = games.compile_supply("castable", "M20", require_verified=False)
ids = {supply.metas[o].name: o for o in supply.metas}
extra = tuple(ids[name] for name in ROUND for _ in range(4))
games._SUPPLY_CACHE["castable:M20"] = supply
stats: Counter = Counter()
crashes: Counter = Counter()
for i in range(n):
    decks = games.deal_decks(930000 + i, 1409, supply, "stress")
    decks = tuple(tuple(list(d[: len(d) - len(extra)]) + list(extra)) for d in decks)
    agents = [Counting(), Counting()]
    res = rig.play_game(930000 + i, agents, pool_mode="castable", set_code="M20", decks=decks)
    game = captured["game"]
    log = game.executor.events  # type: ignore[attr-defined]
    stats["games"] += 1
    stats["pregame_may"] += sum(a.pregame_may for a in agents)
    stats["move_prohibited"] += sum(1 for e in log if len(e) > 1 and e[1] == "MOVE_PROHIBITED")
    stats["gain_prohibited"] += sum(1 for e in log if len(e) > 1 and e[1] == "GAIN_PROHIBITED")
    stats[f"outcome:{res['outcome']}"] += 1
    if res["crash"]:
        crashes[res["crash"][:120]] += 1
out = {"stats": dict(stats), "crashes": dict(crashes)}
Path(sys.argv[3]).write_text(json.dumps(out, indent=1))
print(json.dumps(out, indent=1))
