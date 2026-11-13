"""Did the soak's random games deal and cast the life family's new trees? For each set, the soak's
own games (tools/cards/soak.play_one: the same seeds, modes and decks), and per family card the
number of games it was cast in. Run from the repo root:

    .venv/bin/python reports/life_family_2026-11-13/soak_coverage.py
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

FAMILY = {"Twinblade Paladin", "Angel of Vitality", "Vengeful Warchief", "Serra Ascendant",
          "Cleric of Life's Bond", "Attended Healer", "Cat Collector", "Drogskol Reaver",
          "Archangel of Thune"}
#: M11's compiled pool deals no deck (8 mana sources of the 10 a deck needs): castable there.
RUNS = (("M20", "compiled", True, 200), ("FDN", "compiled", False, 200),
        ("ZNR", "castable", False, 200), ("M11", "castable", False, 100))

for code, mode, unverified, games in RUNS:
    sup = soak._supply(code, mode, unverified)
    # the supply's cards (its metas); a deck is dealt from the deckable ones, so a card here
    # may still never be dealt (FDN Cat Collector in compiled mode)
    names = {oid: meta.name for oid, meta in sup.metas.items() if meta.name in FAMILY}
    cast, crashes, hits = Counter(), 0, 0
    for seed in range(1, games + 1):
        row = soak.play_one((code, mode, unverified, "stress", seed))
        crashes += bool(row["crash"])
        hits += len(row["hits"])
        for oid in row["casts"]:
            if oid in names:
                cast[names[oid]] += 1
    print(f"{code} ({mode}{', unverified records' if unverified else ''}, {games} games, "
          f"{crashes} crashes, {hits} detector hits): dealt {sorted(names.values())}; "
          f"games cast in: {dict(cast)}")
