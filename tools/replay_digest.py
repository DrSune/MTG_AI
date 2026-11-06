"""Per-game digests of N seeded heuristic games on each verified pool: proves a change leaves play
unchanged. Run it from two checkouts (cwd first on sys.path, so each imports its own code) and
compare the outputs:

    cd <checkout> && /home/sune/Desktop/MTG_AI/.venv/bin/python -m tools.replay_digest 100 > a.json
"""

from __future__ import annotations

import json
import sys

from tools.selfplay import preflight
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import play_game


def main(argv: list[str]) -> None:
    n = int(argv[0]) if argv else 100
    out = {code: [preflight._digest(play_game(910000 + i, [HeuristicAgent(), HeuristicAgent()],
                                              deck_mode="stress" if i % 3 else "coherent",
                                              pool_mode="verified", set_code=code))[:12]
                  for i in range(n)]
           for code in ("M21", "M20")}
    print(json.dumps(out))


if __name__ == "__main__":
    main(sys.argv[1:])
