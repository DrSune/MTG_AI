"""Play one game of replay.py on a checkout and dump its journal rows, its decision log and the
card names, for first_diff.py.

    game_dump.py <checkout> <SET> <game index> <out.json>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__

from tools.selfplay import rig
from tools.selfplay.heuristic import HeuristicAgent

captured: dict[str, object] = {}
setup = rig._setup_game


def capture(*args, **kwargs):
    captured["game"] = game = setup(*args, **kwargs)
    return game


rig._setup_game = capture
code, i = sys.argv[2], int(sys.argv[3])
res = rig.play_game(910000 + i, [HeuristicAgent(), HeuristicAgent()],
                    deck_mode="stress" if i % 3 else "coherent", pool_mode="verified", set_code=code)
ex = captured["game"].executor  # type: ignore[attr-defined]
names = {str(h): c.identity.name for h, c in ex.world.cards.items()}
for h, rec in ex.binder.handle_record.items():
    names.setdefault(str(h), rec.name)
Path(sys.argv[4]).write_text(json.dumps({
    "journal": [list(map(str, row)) for row in ex.journal.dump()],
    "asks": [list(map(str, a)) for a in ex.decisions.journal],
    "names": names, "outcome": res["outcome"], "winner": str(res["winner"]),
    "turns": res["turns"], "lives": res.get("lives")}, indent=0))
