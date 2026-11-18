"""Is soak's d6 'delayed trigger still pending at game end' an artefact of a game that ended inside
the turn whose end step would have expired the trigger? Replays the soak games of the M21 hits
(seeds 9, 193, 235, 281: soak.py's play_one deals) and prints, per game, the end reason, the final
turn, and the turn each pending 'Eot' delayed trigger's source was last cast or activated in.

    d6_pending_check.py <checkout>
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

for seed in (9, 193, 235, 281):
    sup = soak._supply("M21", "verified", False)
    game = _setup_game(seed, sup, deal_decks(seed, 1409, sup, "stress"))
    turn_of_clock: dict[int, int] = {}

    def stop(g, _boundary):
        turn_of_clock[len(g.executor.journal.events)] = g.world.turn
        return False

    try:
        _play(game, RandomPolicy(seed), game.world.player_order, TURN_CAP, stop_after=stop)
    except GameOver:
        pass
    ex = game.executor
    final_turn = game.world.turn
    pending = [d for d in ex.binder.delayed if d.tag == "Eot"]
    print(f"seed {seed}: reason={game.reason!r} final turn={final_turn} pending Eot delayed={len(pending)}")
    for d in pending:
        name = ex.world.cards[d.source].identity.name if d.source in ex.world.cards else str(d.source)
        rows = [e for e in ex.journal.events if e.subject == d.source and e.kind in ("CAST", "ACTIVATED", "ABILITY_ACTIVATED")]
        made = max((k for k in turn_of_clock if k <= (rows[-1].clock if rows else 0)), default=None)
        print(f"   {name} ({d.source}); its last cast/activation row at clock {rows[-1].clock if rows else None}, "
              f"turn then {turn_of_clock.get(made)}")
