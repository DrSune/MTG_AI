"""Every sentence of the 19 sets that matches one of the round's wordings (opening hand, game
results, "can't" prohibitions on casting, entering and life), with its card, set and type line."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
SETS = ("M21", "ZNR", "M20", "KHM", "10E", "M10", "M11", "M12", "M13", "M14", "M15", "ORI", "M19",
        "DOM", "WAR", "FDN", "ELD", "THB", "IKO")
PATTERNS = {
    "opening": re.compile(r"opening hand", re.I),
    "lose": re.compile(r"lose[s]? the game", re.I),
    "win": re.compile(r"wins? the game", re.I),
    "cant-cast": re.compile(r"can't cast|cannot cast", re.I),
    "cant-enter": re.compile(r"can't enter", re.I),
    "cant-gain": re.compile(r"can't gain life", re.I),
    "cant-play": re.compile(r"can't play", re.I),
}
SPLIT = re.compile(r"(?<=[.!])\s+(?=[A-Z(\"'])|\n")

seen = set()
for code in SETS:
    data = json.loads((ROOT / "MTG_bot" / "data" / f"{code}.json").read_text())
    cards = data["data"]["cards"] if "data" in data else data["cards"]
    for card in cards:
        text = card.get("text") or ""
        for sentence in SPLIT.split(text):
            for tag, pat in PATTERNS.items():
                if pat.search(sentence):
                    key = (code, card["name"], sentence, tag)
                    if key in seen:
                        continue
                    seen.add(key)
                    print(f"{tag:11} {code:4} {card['name']} [{card.get('type')}] :: {sentence}")
