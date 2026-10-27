"""Measurements for the architecture red-team (docs/REVIEW_ARCHITECTURE_2026-10-27.md).

    .venv/bin/python tools/audit/arch_probe.py [--games 40] [--out FILE]
    MTG_REPO=/path/to/worktree .venv/bin/python tools/audit/arch_probe.py   # measure another tree

P1 aliasing    fully compiled cards whose rules text differs but whose compiled abilities and
               keywords are byte-identical: an encoder that reads only the IR cannot tell them
               apart. Each group is listed so a reader can judge synonym (fine) from lossy (not).
P2 vocabulary  how many cards use each atom (verb, filter predicate, keyword, event, quantity form,
               ability kind, combinator) per set; the long tail; atoms the new sets use that the
               training set (M21) never does, and the share of new-set cards made only of M21
               atoms (the ceiling of zero-shot transfer for an IR encoder, even with a perfect
               compiler).
P3 size        IR length per fully compiled card: canonical-JSON characters and node count.
P4 throughput  engine-only games/s and acts/s, RandomPolicy on both seats, one process.
P5 deck mana   (--k3-games N) K3-lite: does the land gap between the two dealt decks predict the
               winner under random play? Win rate of the deck with more lands by gap bucket.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(os.environ.get("MTG_REPO", Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(REPO))

from MTG_bot.core.ability_tree import (
    Atom,
    FAtom,
    KeywordAbility,
    canonical_json,
    to_dict,
    walk,
)
from MTG_bot.core.compiler.compiler import compile_card
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.errors import StateCorruptionError

SETS = ("M21", "ZNR", "M20", "KHM")
COMBINATORS = frozenset(
    {"Seq", "Choose", "OptionalEffect", "Conditional", "Repeat", "EachPlayer", "DelayedTrigger"}
)


def atoms_of(card: Any) -> set[tuple[str, str]]:
    """Every (kind, name) the IR of one card uses."""
    out: set[tuple[str, str]] = set()
    for ability in card.abilities:
        out.add(("ability", type(ability).__name__))
    for node in walk(card):
        cls = type(node).__name__
        if isinstance(node, Atom):
            out.add(("verb", node.verb.name))
        elif isinstance(node, FAtom):
            out.add(("predicate", node.pred.name))
        elif isinstance(node, KeywordAbility):
            out.add(("keyword", node.keyword.name))
        elif cls.endswith("Event"):
            out.add(("event", cls))
        elif cls.startswith("Q") and cls[1:2].isupper():
            out.add(("quantity", cls))
        elif cls in COMBINATORS:
            out.add(("combinator", cls))
    return out


def rules_key(card: Any) -> str:
    return json.dumps(
        {"abilities": [to_dict(a) for a in card.abilities],
         "keywords": [to_dict(k) for k in card.keywords]},
        sort_keys=True,
    )


def text_key(raw: Any) -> str:
    text = " ".join(raw.sentences)
    for name in sorted({raw.identity.name, raw.identity.name.split(",")[0]}, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(name)}(?!\w)", "~", text)
    return text


def compile_set(code: str, registry: Any) -> list[tuple[Any, Any, bool]]:
    rows = []
    for raw in ingest_pool(REPO / "MTG_bot" / "data" / f"{code}.json").values():
        if raw.is_token or raw.is_emblem:
            continue
        try:
            result = compile_card(raw, registry)
        except StateCorruptionError:
            continue
        except Exception:  # noqa: BLE001, S112 - a crash is a gap here; new_set.py counts them
            continue
        full = not (result.unparsed or result.ambiguities or result.back_face_unparsed)
        rows.append((raw, result.card, full))
    return rows


def _k3_game(seed: int) -> dict[str, Any]:
    from MTG_bot.core.executor.games import deal_decks, get_supply, play_game

    supply = get_supply("castable", "M21")
    a, b = deal_decks(seed, 1409, supply)
    lands = [sum(supply.metas[o].is_land for o in deck) for deck in (a, b)]
    reason = play_game(seed, pool_mode="castable", supply=supply).reason
    loser = 0 if "player:0(" in reason else 1 if "player:1(" in reason else None
    return {"seed": seed, "lands": lands, "loser": loser}


def k3_lite(games: int) -> dict[str, Any]:
    from multiprocessing import Pool

    with Pool(8) as pool:
        rows = pool.map(_k3_game, range(1, games + 1))
    decided = [r for r in rows if r["loser"] is not None]
    unequal = [r for r in decided if r["lands"][0] != r["lands"][1]]

    def more_lands_won(r: dict[str, Any]) -> bool:
        return (r["lands"][0] > r["lands"][1]) == (r["loser"] == 1)

    buckets = {}
    for lo, hi in ((1, 2), (3, 5), (6, 60)):
        sub = [r for r in unequal if lo <= abs(r["lands"][0] - r["lands"][1]) <= hi]
        buckets[f"{lo}-{hi}"] = {"n": len(sub), "more_lands_win_rate":
                                 round(sum(map(more_lands_won, sub)) / len(sub), 3) if sub else None}
    return {
        "games": games, "decided": len(decided), "unequal_land_games": len(unequal),
        "more_lands_win_rate": round(sum(map(more_lands_won, unequal)) / len(unequal), 3),
        "by_gap": buckets,
        "seat0_win_rate": round(sum(r["loser"] == 1 for r in decided) / len(decided), 3),
    }


def pct(values: list[int], q: float) -> int:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--games", type=int, default=40)
    ap.add_argument("--out", default=None)
    ap.add_argument("--k3-games", type=int, default=0, help="also run K3-lite over N games")
    args = ap.parse_args(argv)
    registry = build_full_registry()
    compiled = {code: compile_set(code, registry) for code in SETS}
    report: dict[str, Any] = {"repo": str(REPO), "sets": {}}

    usage: dict[str, Counter] = {}
    for code, rows in compiled.items():
        full = [(raw, card) for raw, card, ok in rows if ok and raw.sentences]
        # P1 aliasing among fully compiled cards with rules text
        groups: dict[str, set[str]] = defaultdict(set)
        names: dict[str, list[str]] = defaultdict(list)
        for raw, card in full:
            key = rules_key(card)
            groups[key].add(text_key(raw))
            names[key].append(raw.identity.name)
        aliased = [(sorted(texts), names[k]) for k, texts in groups.items() if len(texts) > 1]
        # P2 vocabulary
        counter: Counter = Counter()
        for _raw, card, _ok in rows:
            for atom in atoms_of(card):
                counter[atom] += 1
        usage[code] = counter
        # P3 size
        chars = [len(canonical_json(card)) for _raw, card in full]
        nodes = [sum(1 for _ in walk(card)) for _raw, card in full]
        report["sets"][code] = {
            "cards_compiled": len(rows),
            "cards_fully_compiled_with_text": len(full),
            "alias_groups": len(aliased),
            "cards_in_alias_groups": sum(len(n) for _t, n in aliased),
            "alias_examples": [{"cards": n[:4], "texts": t[:3]} for t, n in aliased[:12]],
            "atom_types_used": len(counter),
            "ir_chars": {"median": int(statistics.median(chars)), "p90": pct(chars, 0.9),
                         "max": max(chars)} if chars else None,
            "ir_nodes": {"median": int(statistics.median(nodes)), "p90": pct(nodes, 0.9),
                         "max": max(nodes)} if nodes else None,
        }

    m21 = usage["M21"]
    tail = [a for a, n in m21.items() if n <= 2]
    report["m21_long_tail"] = {
        "atom_types": len(m21),
        "used_by_at_most_2_cards": len(tail),
        "share": round(len(tail) / len(m21), 3),
        "by_kind": dict(Counter(kind for kind, _ in tail)),
    }
    for code in ("ZNR", "M20", "KHM"):
        new_atoms = sorted(set(usage[code]) - set(m21))
        full_cards = [card for raw, card, ok in compiled[code] if ok]
        inside = sum(1 for card in full_cards if atoms_of(card) <= set(m21))
        report["sets"][code]["atoms_absent_from_M21"] = [f"{k}:{n}" for k, n in new_atoms]
        report["sets"][code]["fully_compiled_cards_made_only_of_M21_atoms"] = (
            f"{inside}/{len(full_cards)}"
        )

    # P4 throughput (engine only: RandomPolicy both seats)
    from MTG_bot.core.executor.games import get_supply, play_game

    supply = get_supply("castable", "M21")
    started = time.perf_counter()
    acts, turns, crashes = 0, 0, 0
    for seed in range(1, args.games + 1):
        outcome = play_game(seed, pool_mode="castable", supply=supply)
        acts += outcome.acts
        turns += outcome.turns
        crashes += outcome.crash is not None
    seconds = time.perf_counter() - started
    report["throughput_one_process"] = {
        "games": args.games, "seconds": round(seconds, 1),
        "games_per_s": round(args.games / seconds, 2),
        "acts_per_game": round(acts / args.games, 1), "turns_per_game": round(turns / args.games, 1),
        "acts_per_s": round(acts / seconds, 1), "crashes": crashes,
    }
    if args.k3_games:
        report["k3_lite"] = k3_lite(args.k3_games)
    text = json.dumps(report, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
