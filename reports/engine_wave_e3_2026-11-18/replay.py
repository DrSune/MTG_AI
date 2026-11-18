"""Seeded heuristic games on the verified pools of one checkout (M21, M20, FDN), as C1's replay.py
plays them (seeds 930000 + i, decks dealt only from the cards verified with the same tree on both
checkouts). Per game: the replay digest (outcome, lives, asks: preflight._digest), a sha of the
journal dump and of the raw event log. Given a file of SET:i lines, it plays only those games and
keeps each one's journal rows (repr) and the card names of its handles, for first_diff.py.

    replay.py <checkout> <trees_base.json> <trees_branch.json> <games per set> <out.json> [only.txt]
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
base = json.loads(Path(sys.argv[2]).read_text())
new = json.loads(Path(sys.argv[3]).read_text())
n = int(sys.argv[4])
only = set(Path(sys.argv[6]).read_text().split()) if len(sys.argv) > 6 else None
rows_too = only is not None
out = {}
for code in ("M21", "M20", "FDN"):
    stale = {oid for oid, row in base[code].items()
             if row.get("verified") != new[code][oid].get("verified") or row["tree"] != new[code][oid]["tree"]}
    supply = games.get_supply("verified", code)
    kept = tuple(oid for oid in supply.deckable if oid not in stale)
    games._SUPPLY_CACHE[f"verified:{code}"] = dataclasses.replace(supply, deckable=kept)
    played = []
    for i in range(n):
        if only is not None and f"{code}:{i}" not in only:
            continue
        res = rig.play_game(930000 + i, [HeuristicAgent(), HeuristicAgent()],
                            deck_mode="stress" if i % 3 else "coherent", pool_mode="verified", set_code=code)
        ex = captured["game"].executor  # type: ignore[attr-defined]
        dump = ex.journal.dump()
        row = {"game": i, "digest": preflight._digest(res)[:16],
               "journal": hashlib.sha256(repr(dump).encode()).hexdigest()[:16],
               "events": hashlib.sha256(repr(ex.events).encode()).hexdigest()[:16],
               "outcome": res["outcome"], "turns": res["turns"], "crash": res["crash"]}
        if rows_too:
            names = {str(h): c.identity.name for h, c in ex.world.cards.items()}
            for h, lki in ex.departed_lki.items():
                if getattr(lki, "identity", None) is not None:
                    names.setdefault(str(h), lki.identity.name)
            row["rows"] = [repr(r) for r in dump]
            row["names"] = names
        played.append(row)
    out[code] = {"deckable": len(kept), "taken_out": sorted(stale & set(supply.deckable)), "games": played}
    print(code, len(kept), "deckable;", sum(1 for r in played if r["crash"]), "crashes", file=sys.stderr)
Path(sys.argv[5]).write_text(json.dumps(out))
