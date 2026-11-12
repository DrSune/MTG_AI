"""Census: every card of the 19 sets with an ability that works from a zone other than the
battlefield (CR 113.6), from its oracle text and from its compiled tree.

Run from the repo root: .venv/bin/python reports/engine_faults_2026-11-12/functioning_zones.py
Writes functioning_zones.json beside this file. Per card: set, name, its state (verified, mapped
but not verified, compiled, partly compiled, refused), the text that says where an ability works,
and what the compiled tree says: each activated ability's ``legality.activation_zone`` when it is
not the battlefield, each triggered ability the binder files as graveyard-only
(``binding.functions_from_graveyard``).
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in (REPO, REPO / "tools" / "cards"):
    sys.path.insert(0, str(p))

import corpus

from MTG_bot.core.ability_tree import ActivatedAbility, TriggeredAbility
from MTG_bot.core.executor.binding import functions_from_graveyard
from MTG_bot.core.executor.games import compile_supply
from MTG_bot.core.executor.legality import activation_zone
from MTG_bot.core.state import ZONE_BATTLEFIELD

# Keyword abilities that work off the battlefield: the zone they work from.
KEYWORDS = {
    "graveyard": {"Unearth", "Embalm", "Eternalize", "Scavenge", "Flashback", "Escape", "Encore",
                  "Disturb", "Aftermath", "Jump-start", "Retrace", "Dredge"},
    "hand": {"Cycling", "Channel", "Ninjutsu", "Forecast", "Transmute", "Bloodrush", "Reinforce",
             "Madness", "Plainscycling", "Islandcycling", "Swampcycling", "Mountaincycling",
             "Forestcycling", "Landcycling", "Basic landcycling", "Typecycling"},
    "exile": {"Foretell", "Suspend"},
}


def _me(name: str) -> str:
    names = [re.escape(name)]
    short = name.split(",")[0]
    if short != name:
        names.append(re.escape(short))
    return r"(?:this card|this creature|this permanent|this artifact|this enchantment|" + "|".join(names) + ")"


def text_zones(raw) -> dict[str, list[str]]:
    """Zone -> the phrases of the oracle text (or MTGJSON keywords) that put an ability of the
    card itself there."""
    me = _me(raw.identity.name)
    pats = {
        "graveyard": [rf"{me} from your graveyard", rf"{me} is in your graveyard", rf"exile {me} from your graveyard",
                      rf"{me} from a graveyard", rf"{me} is put into (?:a|your) graveyard from anywhere"],
        "hand": [rf"discard {me}", rf"reveal {me} from your hand", rf"{me} is in your hand", rf"{me} from your hand"],
        "exile": [rf"{me} from exile", rf"{me} is in exile", rf"{me} is exiled"],
        "library": [rf"{me} from your library", rf"{me} is in your library", rf"{me} is put into your graveyard from your library"],
    }
    found: dict[str, list[str]] = {}
    for sentence in raw.sentences:
        for zone, ps in pats.items():
            if any(re.search(p, sentence, flags=re.IGNORECASE) for p in ps):
                found.setdefault(zone, []).append(sentence)
    for zone, kws in KEYWORDS.items():
        for kw in sorted(set(raw.keywords) & kws):
            found.setdefault(zone, []).append(f"keyword {kw}")
    if raw.layout == "adventure":
        found.setdefault("exile", []).append("adventure layout (cast from exile, CR 715.4)")
    return found


def main() -> None:
    rows = []
    for code in corpus.SETS:
        sc = corpus.compile_set(code)
        verified = set(compile_supply("all", code).verified_ids)
        for oid, raw in sorted(sc.raw.items(), key=lambda kv: kv[1].identity.name):
            if raw.is_token or raw.is_emblem:
                continue
            res = sc.results.get(oid)
            card = res.card if res is not None else None
            if card is None:
                state = "refused"
            elif oid in verified:
                state = "verified"
            elif res.record is not None:
                state = "mapped"
            elif res.unparsed or res.ambiguities or res.back_face_unparsed:
                state = "partly"
            else:
                state = "compiled"
            tree: list[str] = []
            for idx, ab in enumerate(card.abilities if card is not None else ()):
                if isinstance(ab, ActivatedAbility) and activation_zone(ab) != ZONE_BATTLEFIELD:
                    tree.append(f"[{idx}] activated, works in the {activation_zone(ab)}")
                if isinstance(ab, TriggeredAbility) and functions_from_graveyard(ab):
                    tree.append(f"[{idx}] triggered, bound in the graveyard ({type(ab.event).__name__})")
            text = text_zones(raw)
            if text or tree:
                rows.append({"set": code, "name": raw.identity.name, "state": state, "text": text, "tree": tree})
    by_zone = Counter(zone for row in rows for zone in row["text"])
    summary = {
        "cards": len(rows),
        "by_state": dict(Counter(row["state"] for row in rows)),
        "by_text_zone": dict(by_zone),
        "compiled_trees_off_the_battlefield": [f"{r['set']} {r['name']} [{r['state']}]: {'; '.join(r['tree'])}"
                                               for r in rows if r["tree"]],
    }
    out = HERE / "functioning_zones.json"
    out.write_text(json.dumps({"summary": summary, "cards": rows}, indent=1, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
