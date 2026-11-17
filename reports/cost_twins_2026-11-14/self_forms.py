"""The byte forms of "this <permanent>" as a cost part's object over the 19 sets (records applied):
every cost part whose selector names the source, by class, selector mode, filter and zones, with
the cards (a verified card starred). The new parts take one form (MAPPER_GUIDE's "this creature");
this shows the forms the existing twins hold. Run from the repo root:

    .venv/bin/python reports/cost_twins_2026-11-14/self_forms.py
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "tools" / "cards"):
    sys.path.insert(0, str(p))
import corpus
from cardtool import _state

from MTG_bot.core import ability_tree as at
from MTG_bot.core.executor.selectors import _filter_names_the_source

def short(f) -> str:
    """A filter as its predicates: IS_SOURCE, CONTROLLER_IS(YOU), FAnd(...), FNot(...)."""
    if isinstance(f, at.FAtom):
        return f.pred.name + (f"({f.who.name})" if f.who is not None else "")
    if isinstance(f, (at.FAnd, at.FOr)):
        return f"{type(f).__name__}({', '.join(short(c) for c in f.children)})"
    if isinstance(f, at.FNot):
        return f"FNot({short(f.inner)})"
    return type(f).__name__


forms: dict[tuple, list[str]] = defaultdict(list)
for code in corpus.SETS:
    sc = corpus.compile_set(code)
    for oid, res in sc.results.items():
        for node in at.walk(res.card):
            if not isinstance(node, at.Cost):
                continue
            for part in node.parts:
                sel = getattr(part, "target", None)
                if isinstance(sel, at.Selector) and _filter_names_the_source(sel.filter):
                    zones = ",".join(f"{z.kind.name}/{z.controller.name}" for z in sel.zones)
                    key = (type(part).__name__, sel.mode.name, short(sel.filter), zones)
                    star = "*" if _state(sc, oid) == "verified" else ""
                    forms[key].append(f"{code} {sc.raw[oid].identity.name}{star}")
for (cls, mode, filt, zones), cards in sorted(forms.items()):
    names = sorted(set(cards))
    print(f"{cls} | {mode} | {filt} | {zones} | {len(cards)} parts on {len(names)} cards, "
          f"{sum(n.endswith('*') for n in names)} verified | {', '.join(names)}")
