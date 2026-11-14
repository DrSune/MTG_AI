"""Did the soak's random games deal and cast round R11's new trees, and pay their new costs? For
each run, the soak's own games (tools/cards/soak.play_one: the same seeds, modes and decks); per
card the number of games it was cast in, and the payments that went through CostExile or
CostRemoveCounter, by the source's name (the new parts' plan and payment lanes); crashes and
detector hits. Run from the repo root:

    .venv/bin/python reports/cost_twins_2026-11-14/soak_coverage.py
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

from MTG_bot.core.executor import legality, stack

FAMILY = {"Hanged Executioner", "Barkhide Troll", "Suspicious Shambler", "Inquisitive Puppet",
          "Steelbane Hydra", "Brittle Effigy", "Soul of Zendikar", "Fungal Plots", "Throne of Makindi",
          "Transmogrifying Wand", "Pentavus", "Tome of Legends"}
#: (set, supply mode, unverified records applied, games). The whole trees are dealt by their
#: compiled pools (M11's and M15's compiled pools hold too few mana sources to build a deck, so
#: their castable pools); the partial ones (Fungal Plots, Throne of Makindi, Transmogrifying Wand,
#: Pentavus, Tome of Legends) only by a castable pool.
RUNS = (("M20", "compiled", True, 200), ("FDN", "compiled", False, 200),
        ("ELD", "compiled", False, 100), ("M11", "castable", False, 100),
        ("M15", "castable", False, 100), ("DOM", "castable", False, 100),
        ("ZNR", "castable", False, 100), ("M19", "castable", False, 100),
        ("M12", "castable", False, 100), ("ELD", "castable", False, 100))

payments: Counter = Counter()
paying = legality.pay_costs


def counting(executor, plan, *, source, controller, **kwargs):
    if plan.exile or plan.remove_counters:
        card = executor.world.cards.get(source)
        payments[card.identity.name if card is not None else str(source)] += 1
    return paying(executor, plan, source=source, controller=controller, **kwargs)


legality.pay_costs = stack.pay_costs = counting

for code, mode, unverified, games in RUNS:
    sup = soak._supply(code, mode, unverified)
    names = {oid: sup.metas[oid].name for oid in sup.deckable if sup.metas[oid].name in FAMILY}
    cast, crashes, hits = Counter(), 0, []
    payments.clear()
    for seed in range(1, games + 1):
        row = soak.play_one((code, mode, unverified, "stress", seed))
        crashes += bool(row["crash"])
        mine = sorted(names[oid] for oid in row["casts"] if oid in names)
        hits += [(seed, h, mine) for h in row["hits"]]
        cast.update(mine)
    print(f"{code} ({mode}{', unverified records' if unverified else ''}, {games} games, "
          f"{crashes} crashes, {len(hits)} detector hits): dealt {sorted(names.values())}; "
          f"games cast in: {dict(cast)}; payments through the new parts: {dict(payments)}")
    for seed, hit, mine in hits:
        print(f"  hit, seed {seed} (the round's cards cast in that game: {mine or 'none'}): "
              f"{hit['detector']}: {hit['detail'][:150]}")
