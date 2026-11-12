"""The two trigger-timing classes over the 19 sets, by oracle text, with each card's state and how
its sentence compiled (records applied, verified or not). Run from the repo root:

    .venv/bin/python reports/trigger_timing_2026-11-12/census.py

1. Reflexive triggers (CR 603.12): "When you do", "when ... this way" and kin. THB Pharika's
   Spawn's "When it enters this way" matches the wording but is not one: it is the card's own
   enters trigger, linked to its escape, not created by a resolving spell or ability.
2. Trigger-event qualifiers (CR 603.4 reads only an intervening "if" again): a trigger whose
   event clause, before its first comma, carries a count, a turn, "while", "alone", an ordinal
   or "there are", with no intervening "if" after it.

The compiled trees' side of both classes is ``tools/audit/ontology_conformance.check_trigger_timing``
(a card with more trigger conditions than intervening "if"s; a compiled "When you do" that is
not a reflexive trigger)."""
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

REFLEXIVE = re.compile(r"\bwhen (?:you do|you don't|they do|they don't|that player does|that player "
                       r"doesn't|he or she does)\b|\bwhen [^.]*\bthis way\b", re.IGNORECASE)
TRIGGER = re.compile(r"^(?:[A-Z][a-z]+(?: [a-z]+)? — )?(When|Whenever|At)\b(?P<event>[^,]*),(?P<rest>.*)$")
QUALIFIER = re.compile(r"\b(?:two|three|four|five|six|seven|eight|nine|ten|\d+) or more\b|\bat least\b|"
                       r"\bduring (?:an opponent's|your|each) turn\b|\bthere are\b|\bwhile\b|"
                       r"\bfor the first time\b|\bsecond\b|\bthird\b|\balone\b", re.IGNORECASE)

registry = build_full_registry()
reflexive, qualified = [], []
for code in corpus.SETS:
    sc = corpus.compile_set(code)
    for oid, raw in sc.raw.items():
        res = sc.results.get(oid)
        state = _state(sc, oid)
        for s in (*raw.sentences, *(raw.back_face.sentences if raw.back_face else ())):
            status = corpus.sentence_status(raw, res, s, registry) if res else "card refused"
            if REFLEXIVE.search(s):
                reflexive.append(f"{code} | {raw.identity.name} | {state} | {status} | {s}")
            m = TRIGGER.match(s)
            if m and QUALIFIER.search(m.group("event")) and not m.group("rest").lstrip().startswith("if "):
                qualified.append(f"{code} | {raw.identity.name} | {state} | {status} | {s}")
print(f"## Reflexive sentences: {len(reflexive)} in {len({r.split(' | ')[1] for r in reflexive})} cards")
print("\n".join(reflexive))
print(f"\n## Trigger-event qualifiers (no intervening 'if'): {len(qualified)} sentences")
print("\n".join(sorted(qualified, key=lambda r: r.split(" | ")[4])))
