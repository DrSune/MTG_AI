"""Can anything give the round's partial trees the counters their new costs need? Every compiled
tree of the 19 sets (records applied) that puts a CHARGE or PAGE counter on a permanent (a
PUT_COUNTER atom, an EtBState, a CostPutCounter), and whether it puts it on its own source. ZNR
Throne of Makindi and M19 Transmogrifying Wand remove charge counters, ELD Tome of Legends page
counters, and each one's own counter sentences are unparsed. Run from the repo root:

    .venv/bin/python reports/cost_twins_2026-11-14/charge_sources.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "tools" / "cards"):
    sys.path.insert(0, str(p))
import corpus  # noqa: E402

from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.executor.selectors import _filter_names_the_source  # noqa: E402

KINDS = (at.CounterKind.CHARGE, at.CounterKind.PAGE)
for code in corpus.SETS:
    sc = corpus.compile_set(code)
    for oid, res in sc.results.items():
        hits = set()
        for n in at.walk(res.card):
            if isinstance(n, at.Atom) and n.verb is at.Verb.PUT_COUNTER and n.args.get("counter_kind") in KINDS:
                sel = n.args.get("target")
                own = isinstance(sel, at.Selector) and _filter_names_the_source(sel.filter)
                hits.add(f"PUT_COUNTER {n.args.get('counter_kind').name} on {'its source' if own else 'another'}")
            if isinstance(n, at.EtBState):
                hits |= {f"EtBState {k.name} (its own)" for k, _ in n.initial_counters if k in KINDS}
            if isinstance(n, at.CostPutCounter) and n.counter_kind in KINDS:
                own = _filter_names_the_source(n.target.filter)
                hits.add(f"CostPutCounter {n.counter_kind.name} on {'its source' if own else 'another'}")
        if hits:
            print(code, sc.raw[oid].identity.name, "|", "; ".join(sorted(hits)))
