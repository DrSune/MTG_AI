"""Census for ontology round R5 (docs/DESIGN_ATOM_ONTOLOGY.md section 10): how many cards in the
19 set files use each wording, by regex over oracle text (card name replaced by "~").

Counts are unique card names, with the sets they appear in. Regex counts are an upper-bound
screen, not a parse: every number quoted in the design comes from this script.

    python3 tools/audit/r5_census.py [--out reports/r5_census_2026-10-29.json]
"""

from __future__ import annotations

import argparse
import glob
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

PATTERNS = {
    "exile_until_leaves": r"exile [^.]*until [^.]*leaves the battlefield",
    "permission_with_duration": r"(until end of turn, you may (play|cast)|you may (play|cast) [^.]*"
    r"(this turn|until end of turn|until the end of your next turn))",
    "play_from_zone": r"you may play (lands|that card|those cards|cards exiled|it|them)",
    "without_paying_mana_cost": r"without paying (its|their) mana costs?",
    "for_as_long_as_remains_exiled": r"for as long as (it|they|that card) remains? exiled",
    "until_end_of_your_next_turn": r"until the end of your next turn",
    "colored_token": r"create [^.]*\b(white|blue|black|red|green)\b[^.]*token",
    "multicolored_token": r"create [^.]*\b(white|blue|black|red|green) and (white|blue|black|red|green)\b[^.]*token",
    "copy_spell": r"copy (target|that|it|the next)[^.]*(spell|ability)|copy that spell|copy it\b",
    "token_copy": r"token that's a copy of",
    "enters_as_copy": r"(enter|enters) (the battlefield )?as a copy of",
    "targeted_by_opponent_trigger": r"becomes the target of a spell or ability an opponent controls",
    # R5-7 (gate round 3): "activated abilities OF <sources> can't be activated" counts too
    # (Pithing Needle, Sorcerous Spyglass, Karn, the Great Creator, Phyrexian Revoker).
    "activation_lock_unless_mana": r"activated abilities (of [^.]*?)?can't be activated unless they're mana abilities",
    "activation_lock_all": r"activated abilities (of [^.]*?)?can't be activated(?! unless)",
    # R5-7: the AbilityActivatedEvent trigger family (kind LOYALTY: Keral Keep Disciples;
    # NON_MANA: Runic Armasaur, Kurkesh; ANY: Sarkhan's Whelp; boast: Frenzied Raider).
    "activation_trigger": r"whenever (you|an opponent|a player|another player) activates? [^.]*abilit",
    "linked_exile": r"(exiled with ~|cards? exiled with|the exiled cards?|exile [^.]* with (this|~)|until you exile another)",
    "resolving_exile_instead": r"if (that|the|it|target)[^.]*would (die|be put into [^.]*graveyard)[^.]*exile it instead",
    "counter_target_spell": r"counter target (\w+ )?spell",
    "counter_target_ability": r"counter target (activated|triggered) (or (activated|triggered) )?ability",
    "choose_one_or_more": r"choose one or more",
    "phasing": r"phases? (out|in)|phasing",
    "extra_turn": r"extra turns?",
    "random_order": r"in a random order",
    "has_all_activated_abilities": r"has all activated abilities",
}


def census() -> dict[str, dict[str, object]]:
    seen: dict[str, dict[str, set[str]]] = {k: {} for k in PATTERNS}
    for path in sorted(glob.glob(str(REPO / "MTG_bot" / "data" / "*.json"))):
        code = Path(path).stem
        data = json.loads(Path(path).read_text())
        cards = data["data"]["cards"] if "data" in data else data.get("cards", [])
        for card in cards:
            text = (card.get("text") or "").lower().replace(card["name"].lower(), "~")
            for key, pattern in PATTERNS.items():
                if re.search(pattern, text):
                    seen[key].setdefault(card["name"], set()).add(code)
    return {
        key: {
            "cards": len(names),
            "sets": len({s for sets in names.values() for s in sets}),
            "names": sorted(names),
        }
        for key, names in seen.items()
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    result = census()
    for key, row in result.items():
        print(f"{row['cards']:4d} cards {row['sets']:3d} sets  {key}")
    if args.out:
        args.out.write_text(json.dumps(result, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
