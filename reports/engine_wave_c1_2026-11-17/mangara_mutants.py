"""Does the S5 pack tell M21 Mangara from its G3 mutants? Runs the pack with the card's tree and with
each "controller YOU->OPPONENT" mutant cardtool's G3 makes (gates.mutants), and reports whether
the pack's expectations hold.

    mangara_mutants.py <checkout> <pack.json>
"""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
for p in (ROOT, ROOT / "tools" / "cards", ROOT / "tools"):
    sys.path.insert(0, str(p))
import gates
import MTG_bot

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from run_scenarios import _run_pack

from MTG_bot.core.executor.games import get_supply

pack = json.loads(Path(sys.argv[2]).read_text())
sup = get_supply("all", "M21")
oid = next(o for o, m in sup.metas.items() if m.name == "Mangara, the Diplomat")
card = sup.pool.results[oid].card
print("card:", _run_pack(pack, sup) or "PASS")
for op, where, mutant in gates.mutants(card):
    if not op.startswith("controller"):
        continue
    with gates.swapped(sup, oid, mutant):
        fails = _run_pack(pack, sup)
    print(f"{op} at {where}: {'KILLED: ' + '; '.join(fails) if fails else 'survives'}")
