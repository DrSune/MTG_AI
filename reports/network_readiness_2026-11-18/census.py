"""Which observation gaps and which knowledge events can the verified cards of M21, M20 and FDN
reach? A census of the verified pools (docs/PLAN_NETWORK_READINESS.md §3-§4; CPU, seconds).

Each gap is a pattern over the printed oracle text (MTGJSON, ``OracleIndex``) and, where the
compiled tree names it, its component tokens (``features.card_tokens``). Text patterns over-count
(a reminder, a word in another sense), so every hit list is printed for reading, and the plan cites
cards, not just counts.

    .venv/bin/python reports/network_readiness_2026-11-18/census.py > reports/network_readiness_2026-11-18/census.txt
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from MTG_bot.bench.view import OracleIndex  # noqa: E402
from MTG_bot.core.executor.games import get_supply  # noqa: E402
from tools.selfplay import features as FT  # noqa: E402

SETS = ("M21", "M20", "FDN")

#: (key, what it is, text pattern, token predicate)
GAPS = [
    ("player_kw", "a player's keyword (hexproof, protection, shroud)",
     r"\b(you|each player|players|target player|you and permanents you control|you and other creatures you control)\b[^.]{0,30}\b(have|has|gain|gains)\b[^.]{0,20}\b(hexproof|protection|shroud)", None),
    ("permit", "a card playable from outside the hand (a standing permission)",
     r"you may (play|cast) [^.]{0,80}(from (your|their|a|the) (graveyard|exile)|from among|exiled with|the top card of your library|this turn)|flashback|escape|you may cast [^.]*from exile",
     lambda t: any("PERMIT" in x for x in t)),
    ("num6", "a threshold above 5 (bucketed as num:6+)",
     r"\b([6-9]|\d\d+) or (more|greater)\b|\b([6-9]|\d\d+) or (fewer|less)\b|life total is (at least )?([6-9]|\d\d+)|at least ([6-9]|\d\d+)", None),
    ("x_target", "an X spell or ability that targets (the target ask does not show X)",
     None, None),
    ("delayed", "a delayed or reflexive trigger (ability index -1 on the stack)",
     r"when you do,|whenever you do,|at the beginning of (the|your) next|next end step|at end of combat",
     lambda t: any(x.startswith(("DelayedTrigger", "Reflexive")) for x in t)),
    ("token_ability", "an ability whose source can cease before it resolves (a token's sacrifice "
     "cost or dies trigger; a dies trigger granted to creatures)",
     r"sacrifice (this|it)[^.]*:|token[^.]{0,60}with \"|have \"when this creature dies|has \"when this creature dies|food token|clue token|treasure token", None),
    ("emblem", "an emblem", r"\bemblem\b", None),
    ("phasing", "phasing", r"phases? out|phasing", None),
    ("returns", "a move until an event (a return row)", r"until [^.]{0,40}leaves the battlefield|exile [^.]{0,60} until", None),
    ("event_number", "a trigger whose effect counts its event (that many, that much)",
     r"that many|that much", lambda t: any("THAT_MANY" in x for x in t)),
    ("live_type", "a live type, colour or name change",
     r"becomes? (a|an|the) [^.]{0,40}(creature|artifact|color|colour)|in addition to its other (types|colors)|is every creature type|changeling|loses all (other )?(abilities|card types|creature types|colors)", None),
    ("planeswalker", "a planeswalker (an attack may choose it)", None, None),
    ("multi_target", "two or more targets (the stack shows the first only)",
     r"target[^.]*\btarget\b|two target|up to (two|three|four|x) target", None),
    ("choose_twice", "a 'you choose ... from it' ask (index tokens plus handle aliases)",
     r"you choose [^.]{0,60}from (it|their hand|among)", None),
]
KNOWLEDGE = [
    ("hand_reveal", "a hand revealed or looked at",
     r"reveals? (their|his or her|your|that player's) hand|look at (target (opponent|player)'s|an opponent's|that player's|each opponent's) hand|reveal[s]? a card from (your|their) hand"),
    ("public_to_hand", "a card returned to a hand from a public zone",
     r"return[^.]{0,80}to (its|their|your|his or her) owner'?s? hand|return[^.]{0,80}to your hand|put[^.]{0,60}into (your|its owner's|their owner's) hand"),
    ("public_to_library", "a card put at a known place in a library from a public zone",
     r"on (the )?(top|bottom) of (its|their|your) owner'?s? library|into (its|their) owner'?s? library [^.]{0,30}(top|bottom|second|third)"),
    ("look_top", "the top of a library looked at or scried (the looker knows)",
     r"\bscry\b|look at the top|surveil"),
    ("reveal_top", "the top of a library revealed (every player knows)",
     r"reveal the top|reveals the top|reveal cards from the top|play with the top card"),
    ("tutor_reveal", "a searched card revealed, put into a hand",
     r"search [^.]*library for [^.]*reveal"),
    ("shuffle", "a shuffle (erases library knowledge)", r"\bshuffle"),
]


def main() -> int:
    for set_code in SETS:
        supply = get_supply("verified", set_code)
        oracle = OracleIndex.for_sets(set_code)
        ids = sorted(supply.verified_ids or supply.deckable)
        print(f"\n===== {set_code}: {len(ids)} verified cards (deckable {len(supply.deckable)})")
        hits: dict[str, list[str]] = {k: [] for k, *_ in GAPS + [(k, d, p) for k, d, p in KNOWLEDGE]}
        for oid in ids:
            res = supply.pool.results.get(oid)
            if res is None or res.card is None:
                continue
            rec = res.card
            text = (oracle.text(oid) or "").lower()
            cost = oracle.cost(oid) or ""
            toks = FT.card_tokens(rec)
            for key, _, pat, pred in GAPS:
                hit = False
                if key == "x_target":
                    hit = "{x}" in cost.lower() and "target" in text
                elif key == "planeswalker":
                    hit = "Planeswalker" in rec.type_line
                else:
                    hit = bool(pat and re.search(pat, text)) or bool(pred and pred(toks))
                if hit:
                    hits[key].append(rec.name)
            for key, _, pat in KNOWLEDGE:
                if re.search(pat, text):
                    hits[key].append(rec.name)
        for key, desc, *_ in GAPS + [(k, d, p) for k, d, p in KNOWLEDGE]:
            names = sorted(set(hits[key]))
            print(f"{key} ({desc}): {len(names)}")
            if names:
                print("    " + "; ".join(names[:40]) + (" ..." if len(names) > 40 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
