"""Replay the named games (SET:SEED, as replay_abg.py plays them) on one checkout and write each
game's journal rows (repr) to a JSON file, for first_diff.py.

    dump_journals.py <checkout> <games file: one SET:SEED per line> <out.json>
"""
from __future__ import annotations

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
out = {}
for line in Path(sys.argv[2]).read_text().split():
    code, seed = line.split(":")
    i = int(seed) - 920000
    rig.play_game(920000 + i, [HeuristicAgent(), HeuristicAgent()],
                  deck_mode="stress" if i % 3 else "coherent", pool_mode="verified", set_code=code)
    game = captured["game"]
    ex = game.executor  # type: ignore[attr-defined]
    names = {str(h): c.identity.name for h, c in ex.world.cards.items()}
    for h, lki in ex.departed_lki.items():
        if lki.__class__.__name__ == "LastKnown" and getattr(lki, "identity", None) is not None:
            names.setdefault(str(h), lki.identity.name)
    out[line] = {"rows": [repr(r) for r in ex.journal.dump()], "names": names}
Path(sys.argv[3]).write_text(json.dumps(out))
