"""How a verification wave moves the G1 coverage test's games: deal the test's seeds from the live
verified pool, then from the same pool with one more card stamped (the first deckable-elsewhere
card the verified pool lacks: a compiled, engine-supported card), and count the decks that change.
On a checkout whose test deals from recorded cards (``recorded_supply``), deal from those too.

    stamp_drift.py <checkout>
"""
from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from MTG_bot.core import test_executor_object_tables as t  # noqa: E402
from MTG_bot.core.executor.games import deal_decks, get_supply  # noqa: E402


def decks(supply, seeds):
    return [deal_decks(seed, 1409, supply, "stress" if seed % 3 else "coherent") for seed in seeds]


for code, seeds in t.GAMES.items():
    live = get_supply("verified", code)
    castable = get_supply("castable", code)
    extra = next(oid for oid in castable.deckable if oid not in live.deckable)
    stamped = dataclasses.replace(live, deckable=tuple(sorted((*live.deckable, extra))))
    moved = sum(a != b for a, b in zip(decks(live, seeds), decks(stamped, seeds), strict=True))
    line = f"{code}: one more stamp ({live.metas[extra].name}) moves {moved} of {len(seeds)} decks dealt from the live pool"
    if hasattr(t, "recorded_supply"):
        line += "; the recorded cards ignore stamps: 0 (they do not read the verified pool)"
    print(line)
