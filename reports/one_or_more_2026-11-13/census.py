"""The "one or more" zone-change wordings over the 19 sets, by oracle text, with each card's state
and how its sentence compiled (records applied, verified or not). Run from the repo root:

    .venv/bin/python reports/one_or_more_2026-11-13/census.py

1. Zone changes: "Whenever one or more <objects> enter / die / leave / are put into <a zone>" (CR
   603.2c: one event, however many objects it moves; CR 603.10a for the look-back ones).
2. For comparison, the attack and combat-damage "one or more" triggers that round 4 gathers.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in (REPO, REPO / "tools" / "cards", REPO / "tools"):
    sys.path.insert(0, str(p))
import MTG_bot

assert MTG_bot.__file__.startswith(str(REPO)), MTG_bot.__file__

import corpus
from cardtool import _state

from MTG_bot.core.compiler.coverage import build_full_registry

CLASSES = {
    "zone changes": re.compile(
        r"\b(?:when|whenever)\b[^.]*?\bone or more\b[^.,]*?\b(?:enter|enters|die|dies|leave|leaves|"
        r"are put into|is put into)\b", re.IGNORECASE),
    "attack and combat damage (round 4)": re.compile(
        r"\b(?:when|whenever)\b[^.]*?\bone or more\b[^.,]*?\b(?:attack|attacks|deal combat damage)\b",
        re.IGNORECASE),
}

registry = build_full_registry()
rows: dict[str, list[str]] = {k: [] for k in CLASSES}
for code in corpus.SETS:
    sc = corpus.compile_set(code)
    for oid, raw in sc.raw.items():
        res = sc.results.get(oid)
        state = _state(sc, oid)
        for s in (*raw.sentences, *(raw.back_face.sentences if raw.back_face else ())):
            for name, pattern in CLASSES.items():
                if pattern.search(s):
                    status = corpus.sentence_status(raw, res, s, registry) if res else "card refused"
                    rows[name].append(f"{code} | {raw.identity.name} | {state} | {status} | {s}")
for name, found in rows.items():
    cards = {r.split(" | ")[1] for r in found}
    blocked = sum(1 for r in found if "UNPARSED" in r.split(" | ")[3]
                  or r.split(" | ")[2] == "needs-atom")
    print(f"## {name}: {len(found)} sentences on {len(cards)} cards, {blocked} blocked "
          "(unparsed, or a needs-atom record)")
    print("\n".join(found))
    print()
