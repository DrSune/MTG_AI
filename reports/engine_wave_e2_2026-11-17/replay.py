"""Seeded heuristic games on the verified deal pools of one checkout (M21, M20, FDN; stress and
coherent decks, as tools/replay_digest.py plays them): per game the outcome, turns, crash, and a
sha of the journal dump, of the raw event log and of the decisions asked.

    replay.py <checkout> <games per set> <out.json>
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from tools.selfplay import rig  # noqa: E402
from tools.selfplay.heuristic import HeuristicAgent  # noqa: E402

captured: dict[str, object] = {}
setup = rig._setup_game


def capture(*args, **kwargs):
    captured["game"] = game = setup(*args, **kwargs)
    return game


rig._setup_game = capture


def h(obj) -> str:
    return hashlib.sha256(repr(obj).encode()).hexdigest()[:16]


n = int(sys.argv[2])
out = {}
for code in ("M21", "M20", "FDN"):
    rows = []
    for i in range(n):
        res = rig.play_game(930000 + i, [HeuristicAgent(), HeuristicAgent()],
                            deck_mode="stress" if i % 3 else "coherent", pool_mode="verified",
                            set_code=code)
        ex = captured["game"].executor  # type: ignore[attr-defined]
        rows.append({"journal": h(ex.journal.dump()), "events": h(ex.events),
                     "asks": h(ex.decisions.ask_log), "outcome": res["outcome"],
                     "winner": res["winner"], "turns": res["turns"], "crash": res["crash"],
                     "lives": res["lives"]})
    out[code] = rows
    print(code, n, "games;", sum(1 for r in rows if r["crash"]), "crashes", file=sys.stderr)
Path(sys.argv[3]).write_text(json.dumps(out, indent=0))
