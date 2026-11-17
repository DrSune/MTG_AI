"""The round's nodes in the trees of the 19 sets (records applied, verified or not): the comparison by
compared side (field, quantity kind, who, negated), TARGETS by filter, QDistinct by field; trees
and verified trees.

    census.py <checkout>
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
import MTG_bot

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
from MTG_bot.core import ability_tree as at
from MTG_bot.core.compiler import card_records
from MTG_bot.core.compiler.compiler import compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.errors import StateCorruptionError

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
registry = build_full_registry()
trees: dict[str, set] = defaultdict(set)
verified: dict[str, set] = defaultdict(set)
nodes = Counter()
for code in SETS:
    raw = ingest_pool(ROOT / "MTG_bot" / "data" / f"{code}.json")
    records = card_records.load_records(code)
    for oid, rc in raw.items():
        if rc.is_token or rc.is_emblem:
            continue
        try:
            res = compile_pool({oid: rc}, registry, records=records, require_verified=False).results[oid]
        except (StateCorruptionError, ValueError):
            continue
        ok = card_records.is_verified(res, records.get(oid))
        negated = {id(n.inner) for n in at.walk(res.card) if isinstance(n, at.FNot)}
        keys = []
        for n in at.walk(res.card):
            if isinstance(n, at.FAtom) and n.pred is at.FAtomPred.QTY_GE:
                side = (f"field {n.field.name}" if n.field is not None
                        else f"quantity {type(n.quantity).__name__}"
                        + (f"({n.quantity.field.name}, {n.quantity.agg.name})"
                           if isinstance(n.quantity, at.QProp) else ""))
                keys.append("QTY_GE " + side + (" who " + n.who.name if n.who else "")
                            + (" (negated: N or less)" if id(n) in negated else ""))
            elif isinstance(n, at.FAtom) and n.pred is at.FAtomPred.TARGETS:
                keys.append("TARGETS " + ("IS_SOURCE" if n.inner_filter == at.FAtom(pred=at.FAtomPred.IS_SOURCE)
                                          else "a filter"))
            elif isinstance(n, at.QDistinct):
                keys.append(f"QDistinct {n.field.name}")
        for k in keys:
            nodes[k] += 1
            trees[k].add((code, oid))
            if ok:
                verified[k].add((code, oid))
for k in sorted(nodes):
    print(f"{k}: {nodes[k]} nodes, {len(trees[k])} trees, {len(verified[k])} verified")
alltrees = set().union(*trees.values())
print(f"trees holding a node of the round: {len(alltrees)}; verified {len(set().union(*verified.values()))}")
