"""Text side of the reachability census (KNOWLEDGE/2026-11-18/215): wordings a tree cannot show
directly, over the oracle text of the three deal pools (`verified` mode).

    text_census.py <checkout>

- F16: one ability's text holding the same "target <words>" phrase twice (two targets the slot
  query would merge; an anaphora "that creature" is not a second target word);
- F23: state triggers (CR 603.8) by their wording ("When there are", "When you control no");
- F27: damage a card deals to "you" or to "each player" (a lifelink source can hit its own
  controller);
- F44: "Enchant creature you control" (an Aura a control change makes illegal).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT))
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402
from MTG_bot.core.executor import games  # noqa: E402

TARGET = re.compile(r"\btarget ((?:[a-z]+ ){0,3}?(?:creature|player|opponent|permanent|spell|card|artifact|enchantment|land|planeswalker))\b")
STATE = re.compile(r"\bWhen (there are|there is|you control no|you have no|.{0,40} has no)\b")
SELF_DAMAGE = re.compile(r"deals? (\d+|X|that much) damage to (you|each player)\b")
ENCHANT_YOURS = re.compile(r"Enchant creature you control")

for code in ("M21", "M20", "FDN"):
    supply = games.get_supply("verified", code)
    raw = ingest_pool(ROOT / "MTG_bot" / "data" / f"{code}.json")
    for oid in supply.deckable:
        rc = raw[oid]
        name = rc.identity.name
        for s in rc.sentences:
            phrases = TARGET.findall(s)
            dup = {p for p in phrases if phrases.count(p) > 1}
            if dup:
                print(f"F16 {code} | {name} | {sorted(dup)} | {s[:120]}")
            if STATE.search(s):
                print(f"F23 {code} | {name} | {s[:120]}")
            if SELF_DAMAGE.search(s):
                print(f"F27 {code} | {name} | {s[:120]}")
            if ENCHANT_YOURS.search(s):
                print(f"F44 {code} | {name} | {s[:120]}")
