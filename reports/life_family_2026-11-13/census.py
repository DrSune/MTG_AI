"""The life family's wordings over the 19 sets, by oracle text, with each card's state and how its
sentence compiled (records applied, verified or not). Run from the repo root:

    .venv/bin/python reports/life_family_2026-11-13/census.py

1. Life-total thresholds: "you have N or more|less life", "less than N life", "your life total
   is ...". The absolute ones read ``FAtomPred.LIFE_TOTAL_GE``; the ones relative to the starting
   life total read ``LIFE_LEAD_OVER_START_GE``.
2. "For the first time" on a life event: ``LifeGainedEvent``/``LifeLostEvent`` ``ordinal=1``.
3. Life-gain replacements: "If <a player> would gain life, ...".
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
    "life-total thresholds": re.compile(
        r"\b(?:have|has) \w+ or (?:more|less) life\b|\bat least \w+ life more\b|"
        r"\bless than \w+ life\b|\blife total is\b", re.IGNORECASE),
    "first time, on a life event": re.compile(
        r"\b(?:gain|gains|lose|loses) life for the first time\b", re.IGNORECASE),
    "life-gain replacements": re.compile(r"\bwould gain life\b", re.IGNORECASE),
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
    unparsed = sum(1 for r in found if "UNPARSED" in r.split(" | ")[3])
    print(f"## {name}: {len(found)} sentences on {len(cards)} cards, {unparsed} unparsed")
    print("\n".join(found))
    print()
