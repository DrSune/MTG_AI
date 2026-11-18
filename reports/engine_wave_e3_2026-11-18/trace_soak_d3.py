"""The soak's d3 hits, game by game, against what really happened. Plays the soak's own games
(tools/cards/soak.py play_one: stress decks, seeds first..first+n-1, the verified pool) on one
checkout and prints, for each game with a d3 hit, the hit and every real counter placement on a
card off the battlefield (observed around the PUT_COUNTER verb and the entry hook), so a hit can be
told from a detector artefact.

    trace_soak_d3.py <checkout> <SET> <first seed> <n> <out.txt>
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
for p in (ROOT, ROOT / "tools" / "cards", ROOT / "tools" / "audit"):
    sys.path.insert(0, str(p))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
import soak  # noqa: E402

from MTG_bot.core.executor import verbs  # noqa: E402
from MTG_bot.core.state import ZONE_BATTLEFIELD  # noqa: E402

real: list[str] = []
orig_put = verbs._v_put_counter


def put(ctx, atom):
    world = ctx.world
    off = {h: dict(c.counters) for h, c in world.cards.items() if world.zone_of(h).kind != ZONE_BATTLEFIELD}
    orig_put(ctx, atom)
    for card, was in off.items():
        if card in world.cards and world.cards[card].counters != was:
            src = ctx.source
            sname = world.cards[src].identity.name if src in world.cards else str(src)
            real.append(f"{card} {world.cards[card].identity.name} in {world.zone_of(card).kind} <- {sname}")


verbs.HANDLERS[verbs.Verb.PUT_COUNTER] = put
code, first, n = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
lines = []
for seed in range(first, first + n):
    real.clear()
    res = soak.play_one((code, "verified", False, "stress", seed))
    d3 = [h["detail"] for h in res["hits"] if h["detector"] == "d3_counters"]
    if d3 or real:
        lines.append(f"seed {seed}: d3 {d3[:4]}{' ...' if len(d3) > 4 else ''}; real off-battlefield placements {real[:4]}")
Path(sys.argv[5]).write_text("\n".join(lines) + "\n")
print(len(lines), "games with a d3 hit or a real placement", file=sys.stderr)
