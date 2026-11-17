"""Seeded heuristic games on the verified pools of one checkout (M21, M20, FDN), the decks dealt only
from the cards verified on BOTH checkouts (a card whose tree or stamp differs between them is taken
out on both sides), as tools/replay_digest.py plays them. Per game: the replay digest (outcome,
lives, asks: preflight._digest), a sha of the whole journal dump, the raw event log's sha, and how
many payments the game made through the two new cost parts (0 expected: no verified tree holds
one).

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
import MTG_bot

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__

from MTG_bot.core.executor import games, legality, stack
from tools.selfplay import preflight, rig
from tools.selfplay.heuristic import HeuristicAgent

captured: dict[str, object] = {}
setup = rig._setup_game


def capture(*args, **kwargs):
    captured["game"] = game = setup(*args, **kwargs)
    return game


rig._setup_game = capture
paying = legality.pay_costs
new_parts = [0]


def counting(executor, plan, **kwargs):
    if getattr(plan, "exile", ()) or getattr(plan, "remove_counters", ()):
        new_parts[0] += 1
    return paying(executor, plan, **kwargs)


legality.pay_costs = stack.pay_costs = counting  # activations, casts and PAY (stack imports it)

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
        new_parts[0] = 0
        res = rig.play_game(920000 + i, [HeuristicAgent(), HeuristicAgent()],
                            deck_mode="stress" if i % 3 else "coherent", pool_mode="verified", set_code=code)
        game = captured["game"]
        journal = repr(game.executor.journal.dump()).encode()  # type: ignore[attr-defined]
        events = repr(game.executor.events).encode()  # type: ignore[attr-defined]
        rows.append({"digest": preflight._digest(res)[:16], "journal": hashlib.sha256(journal).hexdigest()[:16],
                     "events": hashlib.sha256(events).hexdigest()[:16], "new_part_payments": new_parts[0],
                     "outcome": res["outcome"], "turns": res["turns"], "crash": res["crash"]})
    out[code] = {"deckable": len(kept), "taken_out": sorted(stale & set(supply.deckable)), "games": rows}
    print(code, len(kept), "deckable;", sum(1 for r in rows if r["crash"]), "crashes", file=sys.stderr)
Path(sys.argv[5]).write_text(json.dumps(out, indent=1))
