"""Seeded heuristic games on the verified pools of one checkout (M21, M20, FDN), the decks dealt only
from the cards verified on BOTH checkouts (a card whose tree or stamp differs between them is taken
out on both sides), as round 13's replay.py plays them. Per game: the replay digest (outcome,
lives, asks: preflight._digest), a sha of the whole journal dump, the raw event log's sha, and the
rows of the lanes the copy round rewrote or added, counted in the raw event log: tokens made
(CREATE_TOKEN: verbs._v_create_token, its spec half moved), spells and abilities countered (their
frames leave through SpellStack.remove), copies (COPY, BECOME_COPY: the base has none).

    replay.py <checkout> <trees_base.json> <trees_branch.json> <games per set> <out.json>
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__

from MTG_bot.core.executor import games  # noqa: E402
from tools.selfplay import preflight, rig  # noqa: E402
from tools.selfplay.heuristic import HeuristicAgent  # noqa: E402

captured: dict[str, object] = {}
setup = rig._setup_game


def capture(*args, **kwargs):
    captured["game"] = game = setup(*args, **kwargs)
    return game


rig._setup_game = capture
LANES = {"tokens": ("CREATE_TOKEN",), "counters": ("COUNTER",), "copies": ("COPY", "BECOME_COPY")}

base = json.loads(Path(sys.argv[2]).read_text())
new = json.loads(Path(sys.argv[3]).read_text())
n = int(sys.argv[4])
out = {}
for code in ("M21", "M20", "FDN"):
    stale = {oid for oid, row in base[code].items()
             if row.get("verified") != new[code][oid].get("verified") or row["tree"] != new[code][oid]["tree"]}
    supply = games.get_supply("verified", code)
    kept = tuple(oid for oid in supply.deckable if oid not in stale)
    games._SUPPLY_CACHE[f"verified:{code}"] = dataclasses.replace(supply, deckable=kept)
    rows = []
    for i in range(n):
        res = rig.play_game(920000 + i, [HeuristicAgent(), HeuristicAgent()],
                            deck_mode="stress" if i % 3 else "coherent", pool_mode="verified", set_code=code)
        game = captured["game"]
        journal = repr(game.executor.journal.dump()).encode()  # type: ignore[attr-defined]
        log = game.executor.events  # type: ignore[attr-defined]
        lanes = {k: sum(1 for e in log if len(e) > 1 and e[1] in kinds) for k, kinds in LANES.items()}
        rows.append({"digest": preflight._digest(res)[:16], "journal": hashlib.sha256(journal).hexdigest()[:16],
                     "events": hashlib.sha256(repr(log).encode()).hexdigest()[:16], **lanes,
                     "outcome": res["outcome"], "turns": res["turns"], "crash": res["crash"]})
    out[code] = {"deckable": len(kept), "taken_out": sorted(stale & set(supply.deckable)), "games": rows}
    print(code, len(kept), "deckable;", sum(1 for r in rows if r["crash"]), "crashes", file=sys.stderr)
Path(sys.argv[5]).write_text(json.dumps(out, indent=1))
