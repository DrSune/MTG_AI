"""Ontology gate round 8's two censuses over the 19 sets, every record applied:

- m5 (divergence D22): the statics whose effect atoms carry a DurationWhileCondition ("as long as"
  on the atom), against the statics with a `condition` (with the card's printed sentence when it
  says "as long as");
- m6 (divergence D23): the statics granting two or more keywords, in printed or sorted order.

Output: gate8_census.txt. Run from the repo root:

    .venv/bin/python reports/life_family_2026-11-13/gate8_census.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import MTG_bot

assert MTG_bot.__file__.startswith(str(REPO)), MTG_bot.__file__

from MTG_bot.core import ability_tree as at
from MTG_bot.core.compiler import card_records
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.executor.games import compile_supply

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
with_condition: list[str] = []
on_atom: list[str] = []
grants: list[str] = []
for code in SETS:
    supply = compile_supply("all", code, require_verified=False)
    records = card_records.load_records(code)
    raw = ingest_pool(REPO / "MTG_bot" / "data" / f"{code}.json")
    for oid, result in supply.pool.results.items():
        verified = card_records.is_verified(result, records.get(oid))
        for node in at.walk(result.card):
            if not isinstance(node, at.StaticAbility):
                continue
            if node.condition is not None:
                said = [s for s in raw[oid].sentences if "as long as" in s.lower()]
                with_condition.append(f"{code} {result.card.name}: "
                                      + (repr(said[0]) if said else "(no 'as long as')"))
            atoms = [n for n in at.walk(node.effect) if isinstance(n, at.Atom)]
            if any(isinstance(a.args.get("duration"), at.DurationWhileCondition) for a in atoms):
                on_atom.append(f"{code} {result.card.name} "
                               f"({'verified' if verified else 'unverified'})")
            keywords = [a.args.get("ability").keyword.name for a in atoms
                        if a.verb is at.Verb.GRANT_ABILITY
                        and isinstance(a.args.get("ability"), at.KeywordAbility)]
            if len(keywords) >= 2:
                order = "sorted" if keywords == sorted(keywords) else "printed order"
                grants.append(f"{code} {result.card.name} {keywords} {order}")
SAID = sum("(no 'as long as')" not in line for line in with_condition)
print(f"statics with a condition: {len(with_condition)}, {SAID} on cards printing 'as long as'")
for line in with_condition:
    print("  ", line)
print(f"statics with a DurationWhileCondition on an atom: {len(on_atom)}")
for line in on_atom:
    print("  ", line)
print(f"statics granting two or more keywords: {len(grants)}")
for line in grants:
    print("  ", line)
