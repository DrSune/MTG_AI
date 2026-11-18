"""One soak game's journal rows about one card: its zone changes, deaths and counter placements.

    one_game.py <checkout> <SET> <seed> <card handle, e.g. card:113>
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
for p in (ROOT, ROOT / "tools" / "cards", ROOT / "tools" / "audit"):
    sys.path.insert(0, str(p))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from MTG_bot.core.executor import GameOver  # noqa: E402
from MTG_bot.core.executor.games import TURN_CAP, RandomPolicy, _play, _setup_game, deal_decks  # noqa: E402

import soak  # noqa: E402

code, seed, card = sys.argv[2], int(sys.argv[3]), sys.argv[4]
sup = soak._supply(code, "verified", False)
game = _setup_game(seed, sup, deal_decks(seed, 1409, sup, "stress"))
try:
    _play(game, RandomPolicy(seed), game.world.player_order, TURN_CAP)
except GameOver:
    pass
ex = game.executor
names = {str(h): c.identity.name for h, c in ex.world.cards.items()}
print(card, names.get(card))
for e in ex.journal.events:
    if str(e.subject) == card and e.kind in ("ZONE_CHANGE", "CREATURE_DIES", "COUNTER_PLACED"):
        print(e.clock, e.kind, e.cause and names.get(str(e.cause), str(e.cause)), e.cause_verb, e.data[:4])
