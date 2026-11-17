"""The games replay_compare.py lists as differing, replayed as replay.py plays them, each game's
journal rows and decisions written to <out dir>/<set>_<index>.txt (for classify3.py).

    replay_many.py <checkout> <replay_compare.txt> <out dir>
"""
from __future__ import annotations

import re
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
games = re.findall(r"^  (\w+) game (\d+):", Path(sys.argv[2]).read_text(), re.M)
out = Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
for code, i in games:
    i = int(i)
    res = rig.play_game(930000 + i, [HeuristicAgent(), HeuristicAgent()],
                        deck_mode="stress" if i % 3 else "coherent", pool_mode="verified",
                        set_code=code)
    game = captured["game"]
    ex = game.executor  # type: ignore[attr-defined]
    names = {str(hd): c.identity.name for hd, c in game.world.cards.items()}  # type: ignore[attr-defined]
    lines = [f"result {res['outcome']} winner {res['winner']} turns {res['turns']} lives {res['lives']}"]
    lines += ["J " + repr(row) for row in ex.journal.dump()]
    lines += [f"A {what} -> {answer}" for what, answer in ex.decisions.ask_log]
    lines.append("NAMES " + repr(sorted(names.items())))
    (out / f"{code}_{i}.txt").write_text("\n".join(lines) + "\n")
print("replayed", len(games), "games")
