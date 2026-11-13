"""The lifelink fix's blast radius on one checkout: seeded heuristic games on the verified pools
(M21, M20, FDN), as replay.py plays them, with what the fix can change counted.

    lifelink_replay.py <checkout> <games per set> <out.json>
    lifelink_replay.py <checkout> <games per set> <journals.json> <dump.json>

Per game: the replay digest (outcome, lives, asks: preflight._digest), a sha of the whole journal,
and the combat damage steps in which a dealer with lifelink had two or more recipients (counted at
`Executor._assign_damage`: the fault's combat case; its noncombat case needs a life-gain
replacement, which no verified card has). The fix changes no tree, so both checkouts deal from
the same verified pool. With <dump.json> (a {set: [game index, ...]} map, written by
lifelink_replay_compare.py), only those games are played and their journals written, the
handles named.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__

from MTG_bot.core.ability_tree import Keyword
from MTG_bot.core.executor import Executor, games
from MTG_bot.core.identity import Handle
from tools.selfplay import preflight, rig
from tools.selfplay.heuristic import HeuristicAgent

n = int(sys.argv[2])
only = json.loads(Path(sys.argv[4]).read_text()) if len(sys.argv) > 4 else None

captured: dict[str, object] = {}
setup = rig._setup_game


def capture(*args, **kwargs):
    captured["game"] = game = setup(*args, **kwargs)
    return game


rig._setup_game = capture
assign = Executor._assign_damage
split = [0]


def counting(self, dealer, power, controller):
    plan = assign(self, dealer, power, controller)
    if len(plan) >= 2 and self.layers.keyword_of(dealer, Keyword.LIFELINK):
        split[0] += 1
    return plan


Executor._assign_damage = counting


def named(game, text: str) -> str:
    namespace, _, index = text.partition(":")
    if namespace == "card" and index.isdigit():
        card = game.world.cards.get(Handle("card", int(index)))
        if card is not None:
            return f"{text}={card.identity.name}"
    return text


out: dict[str, dict] = {}
for code in ("M21", "M20", "FDN"):
    rows, journals = [], {}
    for i in range(n):
        if only is not None and i not in only.get(code, ()):
            continue
        split[0] = 0
        res = rig.play_game(910000 + i, [HeuristicAgent(), HeuristicAgent()],
                            deck_mode="stress" if i % 3 else "coherent", pool_mode="verified",
                            set_code=code)
        game = captured["game"]
        journal = game.executor.journal.dump()
        sha = hashlib.sha256(repr(journal).encode()).hexdigest()[:16]
        if only is not None:
            journals[str(i)] = {"journal": sha, "rows": [
                [row[0], row[1], named(game, row[2]), named(game, row[3]), row[4], row[5]]
                for row in journal]}
            continue
        rows.append({"digest": preflight._digest(res)[:16], "journal": sha,
                     "split_steps": split[0], "outcome": res["outcome"], "turns": res["turns"],
                     "lives": res["lives"], "crash": res["crash"]})
    if only is not None:
        out[code] = journals
        continue
    out[code] = {"deckable": len(games.get_supply("verified", code).deckable), "games": rows}
    print(code, out[code]["deckable"], "deckable;", sum(1 for r in rows if r["crash"]), "crashes;",
          sum(r["split_steps"] for r in rows), "split lifelink steps", file=sys.stderr)
Path(sys.argv[3]).write_text(json.dumps(out, indent=None if only is not None else 1))
