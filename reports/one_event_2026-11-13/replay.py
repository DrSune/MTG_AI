"""Seeded heuristic games on the verified pools of one checkout (M21, M20, FDN), as
reports/one_or_more_2026-11-13/replay.py plays them (seeds 910000+i, every third deck coherent, the
rest stress). Per game: the replay digest (preflight._digest: outcome, lives, asks), a sha of the
whole journal dump, the number of journal rows, and the engine seconds. No tree changes between
the checkouts compared, so the decks are the same on both.

    replay.py <checkout> <games per set> <out.json> [SET...]
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__

from tools.selfplay import preflight, rig
from tools.selfplay.heuristic import HeuristicAgent

captured: dict[str, object] = {}
setup = rig._setup_game


def capture(*args, **kwargs):
    captured["game"] = game = setup(*args, **kwargs)
    return game


rig._setup_game = capture
n = int(sys.argv[2])
sets = sys.argv[4:] or ["M21", "M20", "FDN"]
out = {}
for code in sets:
    rows = []
    for i in range(n):
        t0 = time.perf_counter()
        res = rig.play_game(910000 + i, [HeuristicAgent(), HeuristicAgent()],
                            deck_mode="stress" if i % 3 else "coherent", pool_mode="verified",
                            set_code=code)
        seconds = time.perf_counter() - t0
        journal = captured["game"].executor.journal.dump()  # type: ignore[attr-defined]
        rows.append({"digest": preflight._digest(res)[:16],
                     "journal": hashlib.sha256(repr(journal).encode()).hexdigest()[:16],
                     "rows": len(journal), "outcome": res["outcome"], "turns": res["turns"],
                     "crash": res["crash"], "seconds": round(seconds, 4)})
    out[code] = rows
    print(code, n, "games;", sum(1 for r in rows if r["crash"]), "crashes;",
          round(sum(r["seconds"] for r in rows), 1), "s", file=sys.stderr)
Path(sys.argv[3]).write_text(json.dumps(out, indent=1))
