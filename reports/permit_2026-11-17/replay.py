"""Seeded heuristic games on the verified pools of one checkout (M21, M20, FDN), the decks dealt only
from the cards verified on BOTH checkouts (a card whose tree or stamp differs between them is taken
out on both sides), as tools/replay_digest.py plays them. Per game: the replay digest (outcome,
lives, asks: preflight._digest), a sha of the whole journal dump, the raw event log's sha, and the
calls into the lanes the round rewrote: effect casts (stack.cast_card), casts and land plays
through a permission (a ``path``; the base has none), and spells a rider moved (stack.exit_zone
answering exile for another destination; the base has no exit_zone).

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

from MTG_bot.core.executor import games, stack  # noqa: E402
from tools.selfplay import preflight, rig  # noqa: E402
from tools.selfplay.heuristic import HeuristicAgent  # noqa: E402

captured: dict[str, object] = {}
setup = rig._setup_game


def capture(*args, **kwargs):
    captured["game"] = game = setup(*args, **kwargs)
    return game


rig._setup_game = capture
calls = {"effect_casts": 0, "path_casts": 0, "path_lands": 0, "riders": 0}
effect_cast, cast, play_land = stack.cast_card, stack.cast, stack.play_land


def counting_effect_cast(*args, **kwargs):
    calls["effect_casts"] += 1
    return effect_cast(*args, **kwargs)


def counting_cast(*args, **kwargs):
    if kwargs.get("path") is not None:
        calls["path_casts"] += 1
    return cast(*args, **kwargs)


stack.cast_card = counting_effect_cast
stack.cast = counting_cast
for module in (sys.modules.get("MTG_bot.core.executor.menu"), sys.modules.get("MTG_bot.core.executor.verbs")):
    if module is not None:
        for name, fn in (("cast_card", counting_effect_cast), ("cast", counting_cast)):
            if hasattr(module, name):
                setattr(module, name, fn)
if hasattr(stack, "exit_zone"):
    exit_zone = stack.exit_zone

    def counting_exit(frame, dest):
        out = exit_zone(frame, dest)
        if out != dest:
            calls["riders"] += 1
        return out

    stack.exit_zone = counting_exit
    from MTG_bot.core.executor import verbs  # noqa: E402

    if hasattr(verbs, "exit_zone"):
        verbs.exit_zone = counting_exit
if hasattr(stack, "permits"):
    pass
try:
    from MTG_bot.core.executor import permits  # noqa: E402

    use = permits.use

    def counting_use(path):
        if path.lands:
            calls["path_lands"] += 1
        return use(path)

    permits.use = counting_use
except ImportError:
    permits = None

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
        for k in calls:
            calls[k] = 0
        res = rig.play_game(920000 + i, [HeuristicAgent(), HeuristicAgent()],
                            deck_mode="stress" if i % 3 else "coherent", pool_mode="verified", set_code=code)
        game = captured["game"]
        journal = repr(game.executor.journal.dump()).encode()  # type: ignore[attr-defined]
        events = repr(game.executor.events).encode()  # type: ignore[attr-defined]
        rows.append({"digest": preflight._digest(res)[:16], "journal": hashlib.sha256(journal).hexdigest()[:16],
                     "events": hashlib.sha256(events).hexdigest()[:16], **calls,
                     "outcome": res["outcome"], "turns": res["turns"], "crash": res["crash"]})
    out[code] = {"deckable": len(kept), "taken_out": sorted(stale & set(supply.deckable)), "games": rows}
    print(code, len(kept), "deckable;", sum(1 for r in rows if r["crash"]), "crashes", file=sys.stderr)
Path(sys.argv[5]).write_text(json.dumps(out, indent=1))
