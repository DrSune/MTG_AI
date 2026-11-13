"""Random-play soaks that deal the round's new trees (tools/cards/soak.play_one: random answers, so
every colour and creature type is chosen sometimes), with each family card's number of games it
was cast in. Run from the repo root:

    .venv/bin/python reports/chosen_quality_2026-11-13/soak_coverage.py
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

FAMILY = {"Diamond Knight", "Icon of Ancestry", "Diamond Mare", "Prism Ring", "Rally the Ranks",
          "Heraldic Banner", "Adaptive Automaton", "Banner of Kinship", "Secluded Courtyard",
          "Obelisk of Urd", "Door of Destinies", "Reflections of Littjara", "Shimmerdrift Vale",
          "Bloodline Pretender", "Realmwalker", "Story Circle", "Voice of All"}
#: compiled pools deal the whole new trees; castable ones the partly compiled ones too (their
#: unparsed sentences silently missing, games.compile_supply)
RUNS = (("M20", "compiled", True, 200), ("FDN", "compiled", False, 200),
        ("FDN", "castable", False, 100), ("KHM", "castable", False, 100),
        ("ORI", "castable", False, 100), ("M19", "castable", False, 100))

for code, mode, unverified, games in RUNS:
    sup = soak._supply(code, mode, unverified)
    names = {oid: meta.name for oid, meta in sup.metas.items()
             if meta.name in FAMILY and oid in sup.deckable}
    cast, crashes, hits = Counter(), [], 0
    for seed in range(1, games + 1):
        row = soak.play_one((code, mode, unverified, "stress", seed))
        if row["crash"]:
            crashes.append((seed, row["crash"]["error"]))
        hits += len(row["hits"])
        for oid in row["casts"]:
            if oid in names:
                cast[names[oid]] += 1
    print(f"{code} ({mode}{', unverified records' if unverified else ''}, {games} games, "
          f"{len(crashes)} crashes, {hits} detector hits): dealt {sorted(names.values())}; "
          f"games cast in: {dict(cast)}")
    for seed, error in crashes:
        print(f"    crash seed {seed}: {error}")
