"""Replay FDN soak seeds 50 and 64 and print the live mandate_block layers: source, targets, where
each ended, and the game's end turn. (W1, D6(iv).)

    d6iv_probe.py <checkout>
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
for p in (ROOT, ROOT / "tools" / "cards", ROOT / "tools" / "audit"):
    sys.path.insert(0, str(p))
from MTG_bot.core.executor import GameOver  # noqa: E402
from MTG_bot.core.executor.games import TURN_CAP, RandomPolicy, _play, _setup_game, deal_decks  # noqa: E402

import soak  # noqa: E402

for seed in (50, 64):
    sup = soak._supply("FDN", "verified", False)
    game = _setup_game(seed, sup, deal_decks(seed, 1409, sup, "stress"))
    turn_at: dict[int, int] = {}

    def stop(g, _boundary):
        turn_at[len(g.executor.journal.events)] = g.world.turn
        return False

    try:
        _play(game, RandomPolicy(seed), game.world.player_order, TURN_CAP, stop_after=stop)
    except GameOver:
        pass
    casts = [e for e in game.executor.journal.events
             if e.kind == "CAST" and game.executor.world.cards.get(e.subject)
             and game.executor.world.cards[e.subject].identity.name == "Joraga Invocation"]
    for e in casts:
        made = max((k for k in turn_at if k <= e.clock), default=None)
        print(f"   Joraga cast at clock {e.clock}, turn {turn_at.get(made)}")
    ex = game.executor
    w = ex.world
    print(f"seed {seed}: reason={game.reason!r} final turn={w.turn}")
    for layer in ex.layers._resolved:
        if layer.kind != "mandate_block":
            continue
        def where(h):
            if h not in w.cards:
                return "gone"
            return f"{w.cards[h].identity.name}@{w.zone_of(h).kind}"
        print(f"   #{layer.seq} status={layer.status} source={layer.source} {where(layer.source)} "
              f"targets={[(str(t), where(t)) for t in layer.targets]}")
        rows = [e for e in ex.journal.events if e.subject in layer.targets and e.kind == "ZONE_CHANGE"]
        for e in rows[-4:]:
            print(f"      {e.clock} {e.subject} {e.zone_move} {e.cause_verb}")
