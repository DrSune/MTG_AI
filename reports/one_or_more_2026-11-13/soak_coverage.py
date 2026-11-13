"""Did the soak's random games deal and cast round R10's new trees, and did their gathered triggers
fire? For each set, the soak's own games (tools/cards/soak.play_one: the same seeds, modes and
decks), per card the number of games it was cast in, and the gathered firings (a flagged trigger
on a declaration or a zone change queued with the objects it gathered), by how many objects. Run
from the repo root:

    .venv/bin/python reports/one_or_more_2026-11-13/soak_coverage.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "tools" / "cards", REPO / "tools" / "audit"):
    sys.path.insert(0, str(p))
import MTG_bot

assert MTG_bot.__file__.startswith(str(REPO)), MTG_bot.__file__
import soak

from MTG_bot.core.executor.binding import TriggerBinder

FAMILY = {"Woodland Champion", "Angelic Guardian", "Desecrated Tomb", "Elvish Warmaster"}
#: KHM's Elvish Warmaster stays partly compiled, so only a castable pool deals it.
RUNS = (("M20", "compiled", True, 200), ("M19", "compiled", False, 200),
        ("KHM", "castable", False, 100))

firings: Counter = Counter()
init = TriggerBinder.__init__


def counting_init(self, executor):
    init(self, executor)
    queue = self._queue

    def counted(source, controller, node, event, *args, **kwargs):
        before = len(self.firings)
        queue(source, controller, node, event, *args, **kwargs)
        for payload in list(self.firings.values())[before:]:
            if payload.gathered is not None and not kwargs.get("additional"):
                record = self.handle_record.get(payload.source)
                name = record.name if record is not None else str(payload.source)
                firings[(name, len(payload.gathered))] += 1

    self._queue = counted


TriggerBinder.__init__ = counting_init

for code, mode, unverified, games in RUNS:
    sup = soak._supply(code, mode, unverified)
    names = {oid: meta.name for oid, meta in sup.metas.items() if meta.name in FAMILY}
    cast, crashes, hits = Counter(), 0, 0
    firings.clear()
    for seed in range(1, games + 1):
        row = soak.play_one((code, mode, unverified, "stress", seed))
        crashes += bool(row["crash"])
        hits += len(row["hits"])
        for oid in row["casts"]:
            if oid in names:
                cast[names[oid]] += 1
    mine = {f"{name} x{n}": k for (name, n), k in sorted(firings.items()) if name in FAMILY}
    print(f"{code} ({mode}{', unverified records' if unverified else ''}, {games} games, "
          f"{crashes} crashes, {hits} detector hits): dealt {sorted(names.values())}; "
          f"games cast in: {dict(cast)}; gathered firings (card x objects: count): {mine}")
