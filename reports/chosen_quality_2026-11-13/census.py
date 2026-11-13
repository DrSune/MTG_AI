"""The chosen-quality family over the 19 sets, by oracle text: every printing with a sentence that
chooses a colour or a creature type as the permanent enters, or reads "the chosen color|type", its
compile state (the compiler's, no records), and for each such sentence the template or frame that
reads it or "unread"; then the other cards that choose a quality (a card name, a type at
resolution). Run from the repo root:

    .venv/bin/python reports/chosen_quality_2026-11-13/census.py
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import MTG_bot

assert MTG_bot.__file__.startswith(str(REPO)), MTG_bot.__file__
from MTG_bot.core.compiler import frames
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool

SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
FAMILY = re.compile(r"\bAs .+ enters, choose a (?:color|creature type)\b|\bof the chosen (?:color|type)\b")
CHOICE = re.compile(r"\bAs .+ enters, choose a (color|creature type)\b")
OTHER = re.compile(r"\bchoose (?:a|any) (?:card name|nonland card name|nonbasic land card name|"
                   r"creature card name|color|creature type|card type)\b", re.IGNORECASE)
registry = build_full_registry()
choices: Counter = Counter()
cards: dict[str, set] = {}
whole = []
others = []
for code in SETS:
    for raw in ingest_pool(REPO / "MTG_bot" / "data" / f"{code}.json").values():
        faces = [raw.sentences, raw.back_face.sentences if raw.back_face else ()]
        sentences = [s for face in faces for s in face]
        hits = [s for s in sentences if FAMILY.search(s)]
        if not hits:
            if any(OTHER.search(s) for s in sentences):
                others.append(f"{code} | {raw.identity.name} | "
                              + " / ".join(s for s in sentences if OTHER.search(s)))
            continue
        for s in hits:
            m = CHOICE.search(s)
            if m:
                choices[m.group(1)] += 1
                cards.setdefault(m.group(1), set()).add(raw.identity.name)
        try:
            res = compile_card(raw, registry)
            unparsed = len(res.unparsed) + len(res.back_face_unparsed)
            state = "whole" if not unparsed else f"{unparsed} unparsed"
        except Exception as exc:  # noqa: BLE001 - a refusal is a census row
            state = f"refused: {type(exc).__name__}: {str(exc)[:90]}"
        if state == "whole":
            whole.append(f"{code} {raw.identity.name}")
        print(f"{code} | {raw.identity.name} | {state}")
        for s in hits:
            m = registry.match(s) or frames.compose(s, registry)
            print(f"    {'read ' + m[0].template.tid if m else 'unread'}: {s}")
print()
print(f"'As ~ enters, choose a ...' printings: {dict(choices)}; distinct cards: "
      f"{ {k: len(v) for k, v in cards.items()} }")
print(f"now compiling whole ({len(whole)}): {whole}")
print()
print("other choices of a quality (a name, or at resolution):")
for row in others:
    print("  ", row)
print()
# the creature-type menus of the trained pools (Supply.creature_types: cards and creature tokens)
from MTG_bot.core.executor.games import get_supply  # noqa: E402 - the slow part last

for code in ("M21", "M20", "FDN"):
    supply = get_supply("verified", code)
    cards = {t for oid in supply.deckable for t in supply.metas[oid].type_line.partition("—")[2].split()
             if "Creature" in supply.metas[oid].type_line.partition("—")[0]}
    print(f"{code} verified pool: {len(supply.creature_types)} creature types in the menu, "
          f"{sorted(set(supply.creature_types) - cards)} from tokens alone")
