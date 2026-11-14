"""G3 on the round's two M20 records, and whether the round's packs kill what the probe cannot: per
card, gates.g3's mutants and survivors, then each survivor swapped into the supply and the card's
packs (tools/scenarios/mapped/M20/<card>_*.json) run against it, as `cardtool verify` runs a
verifier's packs. Run from the repo root:

    .venv/bin/python reports/cost_twins_2026-11-14/g3_packs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "tools" / "cards", REPO / "tools"):
    sys.path.insert(0, str(p))
import gates

from MTG_bot.core.executor.games import compile_supply
from tools.run_scenarios import run_pack

supply = compile_supply("all", "M20", require_verified=False)
for name, prefix in (("Hanged Executioner", "hanged_executioner"), ("Barkhide Troll", "barkhide_troll")):
    oid = next(o for o, m in supply.metas.items() if m.name == name)
    packs = sorted((REPO / "tools" / "scenarios" / "mapped" / "M20").glob(f"{prefix}_*.json"))
    assert all(not run_pack(p, supply) for p in packs), name  # the card's own tree passes them
    res = gates.g3(supply, "M20", oid)
    print(f"{name}: {res['mutants']} mutants, {res['killed']} killed by the probe; "
          f"{len(res['survived'])} survive it; {len(packs)} packs")
    card = supply.pool.results[oid].card
    by_where = {(op, where): m for op, where, m in gates.mutants(card)}
    for op, where in res["survived"]:
        with gates.swapped(supply, oid, by_where[(op, where.replace("/", "/"))]):
            failing = [p.stem for p in packs if run_pack(p, supply)]
        tag = " (critical)" if gates.is_critical(op) else ""
        print(f"  {op} at {where}{tag}: {'killed by ' + ', '.join(failing) if failing else 'SURVIVES the packs'}")
