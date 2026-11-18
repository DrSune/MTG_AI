"""Gate round B12's MINOR 2, its reach: compile every card of the 19 sets (the compiler alone, then
with card records, verified or not) and print each refusal that names a prohibition's placement
(ability_tree.prohibition_placement_fault), and the cards holding a prohibition
(ability_tree.is_prohibition) in a static and elsewhere (a resolving effect). Run from the
checkout: placement_census.py > placement_census.txt"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, ".")
from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.compiler import card_records  # noqa: E402
from MTG_bot.core.compiler.compiler import compile_pool  # noqa: E402
from MTG_bot.core.compiler.coverage import build_full_registry  # noqa: E402
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402
from MTG_bot.core.errors import StateCorruptionError  # noqa: E402

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
registry = build_full_registry()
refused, static, resolving = [], set(), set()
for code in SETS:
    raw = ingest_pool(Path("MTG_bot/data") / f"{code}.json")
    records = card_records.load_records(code)
    for oid, rc in raw.items():
        if rc.is_token or rc.is_emblem:
            continue
        for label, recs in (("compiler", None), ("records", records)):
            try:
                res = compile_pool({oid: rc}, registry, records=recs,
                                   require_verified=False).results[oid]
            except (StateCorruptionError, ValueError) as exc:
                if "prohibition" in str(exc):
                    refused.append((code, rc.identity.name, label, str(exc)[:200]))
                continue
            for ability in res.card.abilities:
                if any(at.is_prohibition(n) for n in at.walk(ability)):
                    (static if isinstance(ability, at.StaticAbility) else resolving).add(
                        (code, rc.identity.name))
for row in refused:
    print("REFUSED", *row)
print("refused:", len(refused))
print("cards with a static prohibition:", len(static))
print("cards with a prohibition elsewhere:", len(resolving), sorted(resolving))
