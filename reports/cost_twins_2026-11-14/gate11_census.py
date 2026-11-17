"""Gate round 11's conditions M2, M3 and M5 on one checkout (the trees of the 19 sets, records
applied, verified or not): (1) every CostExile and CostRemoveCounter selector form, which the
tightened IR check must all still accept; (2) every Cost holding two parts of one designation lane
(exile, a removal of one kind, sacrifice, discard, tap of another permanent: divergence D26's
population); (3) every tree that gives a CHARGE counter (the M5 tripwire's population).

    .venv/bin/python reports/cost_twins_2026-11-14/gate11_census.py <checkout>
"""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
for p in (ROOT, ROOT / "tools" / "cards"):
    sys.path.insert(0, str(p))
import MTG_bot  # noqa: E402

assert MTG_bot.__file__.startswith(str(ROOT)), MTG_bot.__file__
import corpus  # noqa: E402

from MTG_bot.core import ability_tree as at  # noqa: E402

forms: dict[str, list[str]] = defaultdict(list)
twins: list[str] = []
charge: list[str] = []


def lane(part):
    if isinstance(part, at.CostExile):
        return "exile"
    if isinstance(part, at.CostRemoveCounter):
        return f"remove:{part.counter_kind.name}"
    if isinstance(part, at.CostSacrifice):
        return "sacrifice"
    if isinstance(part, at.CostDiscard):
        return "discard"
    if isinstance(part, at.CostTap) and part.target is not None:
        return "tap-other"
    return None


for code in corpus.SETS:
    sc = corpus.compile_set(code)
    for _oid, res in sorted(sc.results.items()):
        name = res.card.name
        for node in at.walk(res.card):
            if isinstance(node, (at.CostExile, at.CostRemoveCounter)):
                s = node.target
                key = (f"{type(node).__name__} count={s.count!r} zones={s.zones!r} filter={s.filter!r}"
                       + (f" n={node.count!r}" if isinstance(node, at.CostRemoveCounter) else ""))
                forms[key].append(f"{code} {name}")
            if isinstance(node, at.Cost):
                lanes = Counter(lane(p) for p in node.parts if lane(p))
                for ln, n in lanes.items():
                    if n > 1:
                        twins.append(f"{code} | {name} | {ln} x{n}")
            if isinstance(node, at.Atom) and (node.verb.name == "PUT_COUNTER" or "PROLIF" in node.verb.name):
                kind = node.args.get("counter_kind")
                if node.verb.name != "PUT_COUNTER" or kind is at.CounterKind.CHARGE or kind is None:
                    charge.append(f"{code} | {name} | {node.verb.name} | {getattr(kind, 'name', kind)}")
            if isinstance(node, at.CostPutCounter) and node.counter_kind is at.CounterKind.CHARGE:
                charge.append(f"{code} | {name} | CostPutCounter | CHARGE")
            if isinstance(node, at.EtBState) and "CHARGE" in repr(node.initial_counters):
                charge.append(f"{code} | {name} | EtBState initial_counters | {node.initial_counters!r}")

print("== (1) CostExile / CostRemoveCounter selector forms")
for key, cards in sorted(forms.items()):
    print(f"{len(cards):3d} | {key}")
    print("      " + "; ".join(sorted(set(cards))))
print("== (2) one Cost, two parts of one lane:", len(twins))
for t in sorted(set(twins)):
    print("  ", t)
print("== (3) trees that give a CHARGE counter or proliferate:", len(set(charge)))
for c in sorted(set(charge)):
    print("  ", c)
