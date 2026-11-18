"""G3 as `cardtool verify` runs it, for named cards and their packs: every critical survivor and
whether some pack kills it (tools/cards/cardtool.py uncovered_survivors).

    survivors.py <checkout> <SET> <card name> <pack.json>...
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
for p in (ROOT, ROOT / "tools" / "cards", ROOT / "tools"):
    sys.path.insert(0, str(p))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
import cardtool  # noqa: E402
import gates  # noqa: E402

from MTG_bot.core.executor.games import compile_supply  # noqa: E402

code, name = sys.argv[2], sys.argv[3]
packs = [Path(p) for p in sys.argv[4:]]
supply = compile_supply("all", code, require_verified=False)
oid = next(o for o, m in supply.metas.items() if m.name == name)
g3, uncovered = cardtool.uncovered_survivors(supply, code, oid, packs, 80)
print(f"{name}: {g3['mutants']} mutants, {g3['killed']} killed by the probe, score {g3['score']}")
for op, where in g3["survived"]:
    print(f"  survives the probe: {'CRITICAL ' if gates.is_critical(op) else ''}{op} at {where}")
for op, where, _m in uncovered:
    print(f"  UNCOVERED (no pack kills it): {op} at {where}")
print(f"  {len(uncovered)} uncovered critical survivor(s) with {len(packs)} pack(s)")
