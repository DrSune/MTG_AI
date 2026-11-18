"""Who puts a counter on a card that is off the battlefield (the soak's d3 class)? Plays random games
(the soak's way: RandomPolicy both seats, the verified pool) on one checkout and records, at every
PUT_COUNTER placement on a card not on the battlefield, the recipient, its zone, the source and
the source's zone, the referent the atom names it by, and the ability's origin clock. Also every
battlefield entry of a card that carried counters from its previous zone.

    trace_d3.py <checkout> <games per set> <out.txt>
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from MTG_bot.core.executor import Executor, GameOver, verbs  # noqa: E402
from MTG_bot.core.executor.games import TURN_CAP, RandomPolicy, _play, _setup_game, deal_decks, get_supply  # noqa: E402
from MTG_bot.core.state import ZONE_BATTLEFIELD  # noqa: E402

hits: Counter = Counter()
examples: dict[str, str] = {}
where = {"game": ""}
orig_put = verbs._v_put_counter


def put(ctx, atom):
    """Observe, never resolve: the off-battlefield cards' counters before and after the verb."""
    world = ctx.world
    off = {h: dict(c.counters) for h, c in world.cards.items() if world.zone_of(h).kind != ZONE_BATTLEFIELD}
    orig_put(ctx, atom)
    for card, was in off.items():
        if card in world.cards and world.cards[card].counters != was:
            sel = atom.args.get("target")
            how = getattr(sel, "referent", None) or getattr(getattr(sel, "mode", None), "name", "?")
            src = ctx.source
            sname = world.cards[src].identity.name if src in world.cards else str(src)
            szone = world.zone_of(src).kind if src in world.cards else "-"
            key = (f"{world.cards[card].identity.name} in {world.zone_of(card).kind} <- {sname} ({szone}) "
                   f"by {how}{' [self]' if card == src else ''}")
            hits[key] += 1
            examples.setdefault(key, f"{where['game']} origin={ctx.origin_clock}")


verbs.HANDLERS[verbs.Verb.PUT_COUNTER] = put
orig_hook = Executor._on_zone_changes


def hook(self, events):
    for e in events:
        if e.kind == "ZONE_CHANGE" and e.subject in self.world.cards and e.zone_move[1] == ZONE_BATTLEFIELD \
                and e.zone_move[0] not in (None, ZONE_BATTLEFIELD) and self.world.cards[e.subject].counters:
            c = dict(self.world.cards[e.subject].counters)
            key = f"ENTERS WITH old counters: {self.world.cards[e.subject].identity.name} from {e.zone_move[0]} {c}"
            hits[key] += 1
            examples.setdefault(key, where["game"])
    return orig_hook(self, events)


Executor._on_zone_changes = hook
n = int(sys.argv[2])
for code in ("M21", "M20", "FDN"):
    sup = get_supply("verified", code)
    for seed in range(n):
        where["game"] = f"{code}:{seed}"
        game = _setup_game(seed, sup, deal_decks(seed, 1409, sup, "stress" if seed % 3 else "coherent"))
        try:
            _play(game, RandomPolicy(seed), game.world.player_order, TURN_CAP)
        except GameOver:
            pass
        except Exception as exc:  # noqa: BLE001
            hits[f"CRASH {type(exc).__name__}: {str(exc)[:100]}"] += 1
    print(code, file=sys.stderr)
with open(sys.argv[3], "w") as out:
    for key, count in hits.most_common():
        print(f"{count:4d}  {key}   e.g. {examples.get(key, '')}", file=out)
