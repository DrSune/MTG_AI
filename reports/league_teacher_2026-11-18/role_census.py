"""How often today's deals hold what the planning puzzles test (docs/DESIGN_LEAGUE.md §4.1).

Roles are read off the compiled ability trees (as packages.py reads its families), never off
names: a counterspell is a card with a COUNTER_SPELL atom; a sweeper an Atom that destroys,
damages, exiles, bounces or shrinks (MODIFY_PT, toughness DECREASE) every battlefield object a
Selector of mode ALL picks, whose filter names creatures or permanents. Approximate by design:
a census, not a rule.

Per set (the verified pool at this commit), per deal shape (coherent; package, packages.py), over
N deals: the share of decks holding at least one card of a role, the mean copies, and the chance
that at least one copy is in the first 12 cards (on the play, by turn 6) or 14 (turn 8), by the
hypergeometric law over the 60-card deck.

    CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 nice -n 19 env PYTHONPATH=. .venv/bin/python \
        reports/league_teacher_2026-11-18/role_census.py M21 M20 FDN --deals 2000
"""

from __future__ import annotations

import argparse
import json
from math import comb

from MTG_bot.core.ability_tree import (
    ActivatedAbility,
    Atom,
    BackFace,
    FAtom,
    FAtomPred,
    PtDelta,
    PtDirection,
    Selector,
    SelectorMode,
    SpellAbility,
    TriggeredAbility,
    Verb,
    ZoneKind,
    walk,
)
from MTG_bot.core.executor.games import deal_decks, get_supply
from tools.selfplay import packages as PK

DEAL_SEED = 1409
SEED0 = 70_000_000  # far from every training, gate and evaluation block (learner.py)
REMOVAL_VERBS = (Verb.DESTROY, Verb.DEAL_DAMAGE, Verb.MOVE_ZONE, Verb.SACRIFICE)


def _names_creatures(f) -> bool:
    return any(isinstance(n, FAtom) and (
        (n.pred is FAtomPred.TYPE_EQ and n.string_value == "Creature")
        or n.pred is FAtomPred.IS_PERMANENT) for n in walk(f)) if f is not None else False


def _shrinks(atom: Atom) -> bool:
    t = atom.args.get("toughness")
    return isinstance(t, PtDelta) and t.direction is PtDirection.DECREASE


def _on_battlefield(sel: Selector) -> bool:
    return any(z.kind is ZoneKind.BATTLEFIELD for z in sel.zones)


def roles(rec) -> set[str]:
    out = set()
    for ab in walk(rec, skip=BackFace):
        if not isinstance(ab, (SpellAbility, TriggeredAbility, ActivatedAbility)):
            continue
        for n in walk(ab):
            if not isinstance(n, Atom):
                continue
            if n.verb is Verb.COUNTER_SPELL:
                out.add("counter")
            sel = n.args.get("target")
            if (not isinstance(sel, Selector) or not _names_creatures(sel.filter)
                    or not _on_battlefield(sel)):
                continue
            if n.verb in REMOVAL_VERBS or (n.verb is Verb.MODIFY_PT and _shrinks(n)):
                out.add("sweeper" if sel.mode is SelectorMode.ALL else "removal")
    obj = PK.card_obj(rec)
    if "Instant" in obj.words or any(k.name == "FLASH" for k in obj.keywords):
        out.add("instant_speed")
    return out


def p_drawn(copies: int, seen: int, deck: int = 60) -> float:
    return 1.0 - comb(deck - copies, seen) / comb(deck, seen) if copies else 0.0


def census(set_code: str, deals: int) -> dict:
    sup = get_supply("verified", set_code)
    role_of = {c: roles(sup.pool.results[c].card) for c in sup.deckable
               if not sup.metas[c].is_land}
    pool = {r: sorted(sup.metas[c].name for c, rs in role_of.items() if r in rs)
            for r in ("counter", "sweeper", "removal", "instant_speed")}
    kept, dropped = PK.derive(sup)
    out = {"set": set_code, "spells": len(role_of),
           "pool": {r: {"cards": len(v), "names": v} for r, v in pool.items()},
           "packages": {"kept": len(kept), "dropped": len(dropped),
                        "labels": sorted(PK.label(p) for p in kept)}}
    for shape in ("coherent", "package"):
        acc = {r: {"any": 0, "copies": 0, "t6": 0.0, "t8": 0.0}
               for r in ("counter", "sweeper", "removal", "instant_speed")}
        both_counter_or_sweeper = 0
        n = 0
        for i in range(deals):
            seed = SEED0 + i
            decks = (deal_decks(seed, DEAL_SEED, sup, "coherent") if shape == "coherent"
                     else PK.package_decks(seed, sup))
            holds_cs = []
            for deck in decks:
                n += 1
                cnt = {r: sum(r in role_of.get(c, ()) for c in deck) for r in acc}
                for r, k in cnt.items():
                    acc[r]["any"] += k > 0
                    acc[r]["copies"] += k
                    acc[r]["t6"] += p_drawn(k, 12)
                    acc[r]["t8"] += p_drawn(k, 14)
                holds_cs.append(cnt["counter"] > 0 or cnt["sweeper"] > 0)
            both_counter_or_sweeper += any(holds_cs)
        out[shape] = {r: {"deck_share": round(v["any"] / n, 4),
                          "copies": round(v["copies"] / n, 3),
                          "drawn_by_t6": round(v["t6"] / n, 4),
                          "drawn_by_t8": round(v["t8"] / n, 4)} for r, v in acc.items()}
        out[shape]["deals_with_a_counter_or_sweeper"] = round(both_counter_or_sweeper / deals, 4)
        out[shape]["decks"] = n
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sets", nargs="+")
    ap.add_argument("--deals", type=int, default=2000)
    a = ap.parse_args()
    res = [census(s, a.deals) for s in a.sets]
    for r in res:
        print(json.dumps({k: v for k, v in r.items() if k != "pool"}))
        print(json.dumps({k: {"cards": v["cards"], "names": v["names"][:25]}
                          for k, v in r["pool"].items()}))
    with open("reports/league_teacher_2026-11-18/role_census.json", "w") as fh:
        json.dump(res, fh, indent=1)


if __name__ == "__main__":
    main()
