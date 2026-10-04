"""BUGCATCH B4b interaction coverage (design §C + §F PC-13) — fully offline.

PC-13 asks whether every collision-class pair is *tested*, and the engine has
never recorded a pair: ``coverage_fired`` is a scalar count of cards that fired
at least once (games.py), not who shared a game.  So co-fire is reconstructed
here from the journal lane, without touching the engine:

* **co-fire (corpus lane)** — a card "fired" in a replay if some row is
  attributable to it (its tag is a row subject/cause, or sits in a row's data
  payload).  Two cards co-fired if they fired in the same replayed game.
* **designed pair (pack lane)** — both printed names appear as ``"real"``
  cards in one pack file.  Read from disk, not from a journal, because a pack
  declares the pairing by construction.

A pair is TESTED if it co-fired in >= 1 corpus game or is designed by >= 1
green pack.  Everything else is a hole, ranked by §C's metric:

    heat = BCS_a x BCS_b x collision-class weight x 1[untested]

Pair gating follows the 2026-10-04 ruling: risk is carried by the §C **class**
(both ends must be able to express the class's two mechanisms), with BCS >= T on
ONE end as the complexity floor — §F's literal "both ends BCS >= T" is vacuous
here, because every flagged card sits at BCS <= 16.

Known limit, stated rather than hidden: co-fire means both cards did something
in one game.  It does NOT mean the two mechanisms resolved *against each other*
in the same layer, replacement window or trigger stack.  A pair can be TESTED by
this metric and still be an untested collision — closing that gap is exactly
what authoring a forced splice pack does, which is why untested pairs are a work
order and tested pairs are not a clean bill of health.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
for _p in (REPO, REPO / "tools", REPO / "tools" / "audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import branch_coverage as BC  # reuses §C class weights + attribution helper
import membership as MEM

BCS_JSON = HERE / "bcs.json"
OUT_DEFAULT = HERE / "pair_coverage.json"
T_DEFAULT = 20

# The six §C collision classes (+ B1's branch-entanglement signature class),
# each as a TWO-mechanism predicate over the §A primitives.  A collision needs
# both sides, so a pair belongs to a class only when BOTH ends satisfy it.
CLASS_PREDICATES: dict[str, Any] = {
    "pt_layers": lambda p: p.get("p7_layers", 0) >= 1,  # counter-fold x static grant
    "replacement_x_replacement": lambda p: p.get("p6_replacement", 0) >= 1,
    "replacement_x_trigger": lambda p: (
        p.get("p6_replacement", 0) >= 1 and p.get("p8_triggers", 0) >= 1
    ),  # self-dies law (22a)
    "grant_x_consumer_missing": lambda p: p.get("p7_layers", 0) >= 1,  # r20a
    "sacrifice_x_dies_token_anthem": lambda p: (
        p.get("p5_token_minting", 0) >= 1 or p.get("p7_layers", 0) >= 1
    ),
    "x_census_x_name": lambda p: p.get("p4_quantifiers", 0) >= 1,  # sanctum NAME_EQ
    "branch_entanglement": lambda p: p.get("p2_branch_slots", 0) >= 1,
}


def pair_key(a: str, b: str) -> str:
    """Order-independent pair key, so (a,b) and (b,a) are one cell."""
    return " + ".join(sorted((a, b)))


def fired_names(game: object) -> set[str]:
    """Cards in this game that a journal row is attributable to."""
    handle_names: dict[str, str] = getattr(game, "handle_names", {})
    seen: set[str] = set()
    for row in getattr(game, "rows", []):
        for tag in (row.subject, row.cause):
            if tag is not None:
                seen.add(str(tag))
        seen.update(BC._handles_in(row.data))
    return {handle_names[t] for t in seen if t in handle_names}


def co_fire(games: list[Any]) -> Counter[str]:
    """pair key -> number of corpus games where both cards fired."""
    counts: Counter[str] = Counter()
    for g in games:
        fired = sorted(fired_names(g))
        for a, b in itertools.combinations(fired, 2):
            counts[pair_key(a, b)] += 1
    return counts


def designed_pairs(packs_dir: Path = MEM.PACKS_DIR) -> dict[str, list[str]]:
    """pair key -> pack files declaring both cards as ``"real"`` cards."""
    out: dict[str, list[str]] = {}
    for path in sorted(packs_dir.glob("*.json")):
        try:
            tree = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        names = sorted(MEM._real_names(tree))
        for a, b in itertools.combinations(names, 2):
            out.setdefault(pair_key(a, b), []).append(path.name)
    return out


def build_payload(
    bcs: dict[str, Any],
    cofire: Mapping[str, int],
    designed: dict[str, list[str]],
    t: int,
    limit: int,
    games_n: int,
) -> dict[str, Any]:
    cards = bcs["cards"]
    prim = {n: (c.get("primitives") or {}) for n, c in cards.items()}
    flagged: dict[str, set[str]] = {
        n: {str(BC.FLAG_TO_CLASS.get(f, f)) for f in c.get("collision_flags", [])}
        for n, c in cards.items()
    }
    universe = [
        (a, b)
        for a, b in itertools.combinations(sorted(cards), 2)
        if max(int(cards[a].get("bcs", 0)), int(cards[b].get("bcs", 0))) >= t
    ]

    per_class: dict[str, Any] = {}
    rows: dict[str, dict[str, Any]] = {}
    for cls, pred in CLASS_PREDICATES.items():
        members = sorted(n for n, p in prim.items() if pred(p))
        member_set = set(members)
        tested = untested = 0
        best: list[dict[str, Any]] = []
        weight = BC.CLASS_WEIGHTS.get(cls, BC.UNKNOWN_CLASS_WEIGHT)
        for a, b in universe:
            if a not in member_set or b not in member_set:
                continue
            key = pair_key(a, b)
            n_co = cofire.get(key, 0)
            packs = designed.get(key, [])
            is_tested = n_co > 0 or bool(packs)
            ba, bb = int(cards[a]["bcs"]), int(cards[b]["bcs"])
            heat = 0.0 if is_tested else round(ba * bb * weight, 2)
            rec = rows.setdefault(
                key,
                {
                    "pair": key,
                    "a": a,
                    "b": b,
                    "bcs_a": ba,
                    "bcs_b": bb,
                    "classes": [],
                    "co_fire_games": n_co,
                    "designed_by_packs": packs,
                    "tested": is_tested,
                    "tested_by": "co-fire" if n_co > 0 else ("pack" if packs else ""),
                    "flagged_ends": sorted(
                        c for c in (a, b) if cls in flagged.get(c, set())
                    ),
                    "heat": 0.0,
                    "pair_heat": {},
                },
            )
            rec["classes"].append(cls)
            rec["pair_heat"][cls] = heat
            rec["heat"] = max(rec["heat"], heat)
            if is_tested:
                tested += 1
            else:
                untested += 1
                best.append({"pair": key, "heat": heat, "a": a, "b": b})
        best.sort(key=lambda e: (-e["heat"], e["pair"]))
        per_class[cls] = {
            "mechanism_members": len(members),
            "candidate_pairs": tested + untested,
            "tested": tested,
            "untested": untested,
            "coverage_pct": round(100.0 * tested / (tested + untested), 2)
            if (tested + untested)
            else None,
            "weight": weight,
            "flagged_members": sorted(n for n in members if flagged.get(n)),
            "top_untested": best[:10],
        }

    ranked = sorted(
        (r for r in rows.values() if not r["tested"]),
        key=lambda r: (-r["heat"], r["a"], r["b"]),
    )
    zero_classes = sorted(c for c, s in per_class.items() if s["tested"] == 0)

    return {
        "meta": {
            "built_by": "BUGCATCH batch B4b — tools/audit/pair_coverage.py",
            "date": datetime.now(UTC).isoformat(timespec="seconds"),
            "command": ".venv/bin/python tools/audit/pair_coverage.py --quiet",
            "design": "KNOWLEDGE/2026-10-02/12-bugcatch-design.md §C + §F PC-13",
            "gating": f"both ends express the class's mechanism; BCS >= {t} on "
            "ONE end as floor (2026-10-04 ruling amending §F's both-ends wording)",
            "co_fire_law": "card fired iff a journal row is attributable to it; "
            "pair co-fired iff both fired in the same replay",
            "co_fire_limit": "co-fire is not collision: it does not prove the "
            "two mechanisms resolved against each other in one layer / "
            "replacement window / trigger stack. Tested by this metric is a "
            "necessary, not sufficient, condition — forced splices close it.",
            "corpus_games": games_n,
            "pair_universe": len(universe),
            "pair_classes_considered": len(CLASS_PREDICATES),
        },
        "totals": {
            "candidate_pairs": len(rows),
            "tested": sum(1 for r in rows.values() if r["tested"]),
            "untested": sum(1 for r in rows.values() if not r["tested"]),
            "classes_with_zero_tested": zero_classes,
            "pairs_co_fired_in_corpus": sum(
                1 for r in rows.values() if r["co_fire_games"]
            ),
            "pairs_designed_in_packs": sum(
                1 for r in rows.values() if r["designed_by_packs"]
            ),
        },
        "per_class": per_class,
        "untested_pairs": ranked[:limit],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BUGCATCH B4b pair coverage (PC-13)")
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--pool", default="all")
    ap.add_argument("--deck-pairs-seed", type=int, default=1409)
    ap.add_argument("--turns", type=int, default=60)
    ap.add_argument("--t", type=int, default=T_DEFAULT)
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    import b4_journal  # deferred: engine-backed replay lane

    bcs = json.loads(BCS_JSON.read_text(encoding="utf-8"))
    t0 = time.perf_counter()
    games = b4_journal.corpus_games(
        args.seeds, args.pool, args.deck_pairs_seed, args.turns, quiet=args.quiet
    )
    cofire = co_fire(games)
    if not args.quiet:
        print(
            f"corpus: {len(games)} games, {len(cofire)} distinct co-fired pairs "
            f"[{time.perf_counter() - t0:.1f}s]",
            flush=True,
        )
    payload = build_payload(
        bcs, cofire, designed_pairs(), args.t, args.limit, len(games)
    )
    Path(args.out).write_text(json.dumps(payload, indent=1), encoding="utf-8")

    tot = payload["totals"]
    print(
        f"candidate pairs {tot['candidate_pairs']}: tested {tot['tested']} / "
        f"untested {tot['untested']}"
    )
    print(
        "classes with ZERO tested coverage:",
        ", ".join(tot["classes_with_zero_tested"]) or "none",
    )
    for cls, s in payload["per_class"].items():
        print(
            f"  {cls:<32} members {s['mechanism_members']:>4}  "
            f"pairs {s['candidate_pairs']:>5}  tested {s['tested']:>4}  "
            f"cov {s['coverage_pct']}%"
        )
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
