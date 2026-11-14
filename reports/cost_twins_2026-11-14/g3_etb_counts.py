"""G3 mutant counts on cards with an "As this enters" node that only taps or puts counters, per
checkout: gates._without_unread_choices built EtBState(effect=None) for every such node, which the
IR refuses, so every mutant was stillborn (fixed in round R11). Also counts, over the verified
trees of M21, M20 and FDN, how many hold such a node (each had no G3 mutant while the bug lived).

    g3_etb_counts.py <checkout>
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
for p in (ROOT, ROOT / "tools" / "cards"):
    sys.path.insert(0, str(p))
import MTG_bot

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
import gates

from MTG_bot.core import ability_tree as at
from MTG_bot.core.compiler import card_records
from MTG_bot.core.executor.games import compile_supply

for code, names in (("M21", ("Malefic Scythe", "Temple of Malady", "Wildwood Scourge")),
                    ("M20", ("Barkhide Troll", "Squad Captain"))):
    sup = compile_supply("all", code, require_verified=False)
    for name in names:
        oid = next(o for o, m in sup.metas.items() if m.name == name)
        print(code, name, "mutants:", sum(1 for _ in gates.mutants(sup.pool.results[oid].card)))
for code in ("M21", "M20", "FDN"):
    sup = compile_supply("all", code, require_verified=False)
    records = card_records.load_records(code)
    plain = [sup.metas[oid].name for oid, res in sup.pool.results.items()
             if card_records.is_verified(res, records.get(oid))
             and any(isinstance(a, at.EtBState) and a.effect is None for a in res.card.abilities)]
    print(code, "verified trees with an EtBState of no effect:", len(plain))
