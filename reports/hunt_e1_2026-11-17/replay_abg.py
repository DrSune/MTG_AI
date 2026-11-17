"""Seeded heuristic games on the verified pools of one checkout (M21, M20, FDN), as
tools/replay_digest.py plays them: per game the replay digest (outcome, lives, asks:
preflight._digest), a sha of the whole journal dump and of the raw event log, and one short hash
per journal row, so a game that differs between two checkouts can be located at its first
differing row (replay_compare_abg.py). With ``--show SET:SEED`` it prints that game's journal rows.

    replay_abg.py <checkout> <games per set> <out.json>
    replay_abg.py <checkout> --show SET:SEED [<first row> <last row>]
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

from tools.selfplay import preflight, rig  # noqa: E402
from tools.selfplay.heuristic import HeuristicAgent  # noqa: E402

captured: dict[str, object] = {}
setup = rig._setup_game


def capture(*args, **kwargs):
    captured["game"] = game = setup(*args, **kwargs)
    return game


rig._setup_game = capture


def play(code: str, i: int):
    res = rig.play_game(920000 + i, [HeuristicAgent(), HeuristicAgent()],
                        deck_mode="stress" if i % 3 else "coherent", pool_mode="verified",
                        set_code=code)
    return res, captured["game"]


if sys.argv[2] == "--show":
    code, seed = sys.argv[3].split(":")
    res, game = play(code, int(seed) - 920000)
    rows = game.executor.journal.dump()  # type: ignore[attr-defined]
    lo, hi = (int(sys.argv[4]), int(sys.argv[5])) if len(sys.argv) > 5 else (0, len(rows))
    for k in range(lo, min(hi, len(rows))):
        print(k, rows[k])
    print("result:", {k: res[k] for k in ("outcome", "winner", "turns", "lives", "crash")})
    sys.exit(0)

n = int(sys.argv[2])
out = {}
for code in ("M21", "M20", "FDN"):
    games = []
    for i in range(n):
        res, game = play(code, i)
        dump = game.executor.journal.dump()  # type: ignore[attr-defined]
        events = repr(game.executor.events).encode()  # type: ignore[attr-defined]
        games.append({
            "seed": 920000 + i,
            "digest": preflight._digest(res)[:16],
            "journal": hashlib.sha256(repr(dump).encode()).hexdigest()[:16],
            "events": hashlib.sha256(events).hexdigest()[:16],
            "rows": [hashlib.sha256(repr(r).encode()).hexdigest()[:8] for r in dump],
            "outcome": res["outcome"], "winner": res["winner"], "turns": res["turns"],
            "lives": res["lives"], "crash": res["crash"],
        })
    out[code] = games
    print(code, n, "games;", sum(1 for g in games if g["crash"]), "crashes", file=sys.stderr)
Path(sys.argv[3]).write_text(json.dumps(out))
