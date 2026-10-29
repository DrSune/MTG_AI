"""Gate G5: soak a set's pool in many random games, and screen its cards for abuse.
docs/PLAN_CARD_ONBOARDING.md.

    PY=/home/sune/Desktop/MTG_AI/.venv/bin/python
    $PY tools/cards/soak.py FDN --games 400 --mode compiled [--unverified] [--workers 8] --out soak.json

- Plays seeded random games (``RandomPolicy`` both seats, the engine's own turn loop ``_play``) on
  the chosen supply mode. ``--unverified`` applies mapped card records that are not yet verified
  (the soak that comes before verification); without it, games see what real games see.
- **Engine health:** crashes, grouped by exception and the card being played when it happened;
  and the oracle-free anomaly detectors D1-D6 (``tools/audit/detectors.py``) on every game's
  journal: life ledger, mana, counters, tokens, P/T recompute, lifecycle.
- **Abuse screen** (review candidates, not failures):
  - a card's win rate when cast, against the cards of the same mana value (z > 3 over at least
    20 casts);
  - abilities activated many times in one turn (a free repeatable ability is the classic missing
    cost);
  - cards that trip the trigger-loop quarantine.

The win rate under random play is a weak signal: strong cards win more, as they should. The screen
only ranks what a human or a verifier looks at first.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _p in (REPO, REPO / "tools" / "audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_SUPPLY: Any = None
_CFG: tuple = ()


def _supply(set_code: str, mode: str, unverified: bool) -> Any:
    global _SUPPLY, _CFG
    if _SUPPLY is None or _CFG != (set_code, mode, unverified):
        from MTG_bot.core.executor.games import compile_supply

        _SUPPLY = compile_supply(mode, set_code, require_verified=not unverified)
        _CFG = (set_code, mode, unverified)
    return _SUPPLY


def play_one(job: tuple[str, str, bool, str, int]) -> dict[str, Any]:
    set_code, mode, unverified, deck_mode, seed = job
    import detectors as det

    from MTG_bot.core.executor.games import (
        TURN_CAP,
        RandomPolicy,
        _play,
        _setup_game,
        deal_decks,
    )

    sup = _supply(set_code, mode, unverified)
    decks = deal_decks(seed, 1409, sup, deck_mode)
    game = _setup_game(seed, sup, decks)
    start_life = {str(h): int(p.life) for h, p in game.world.players.items()}
    crash = None
    try:
        _play(game, RandomPolicy(seed), game.world.player_order, TURN_CAP)
    except BaseException as error:  # noqa: BLE001 — a crash is the finding
        crash = {"error": f"{type(error).__name__}: {error}"[:200],
                 "attempted": getattr(game, "attempted", "")}
    world, ex = game.world, game.executor
    loser = None
    m = re.search(r"(player:\d+)\(", game.reason or "")
    if m:
        loser = m.group(1)
    casts: dict[str, list[str]] = defaultdict(list)  # oracle id -> casting seats
    for e in ex.journal.events:
        if e.kind == "CAST" and e.subject in world.cards:
            casts[world.cards[e.subject].identity.oracle_id].append(str(e.data[0]))
    per_turn = Counter(d.split(".", 1)[0] + "|" + d.split(":", 1)[1] for d in game.digest if ".act:" in d)
    loops = sorted(str(x) for x in getattr(ex, "trigger_loops", []) or [])
    rows = [det.Row(i, int(str(r[0])), str(r[1]), str(r[2]), str(r[3]), str(r[4]), det._parse_data(r[5]))
            for i, r in enumerate(ex.journal.dump())]
    final_zone, names = {}, {}
    for handle, record in world.cards.items():
        try:
            final_zone[str(handle)] = str(world.zone_of(handle).kind)
        except (KeyError, ValueError):
            pass
        names[str(handle)] = str(record.identity.name)
    binder: dict[str, list[Any]] = {}
    for group in ex.binder.dump():
        if isinstance(group, tuple) and len(group) == 2 and isinstance(group[1], (list, tuple)):
            binder[str(group[0])] = list(group[1])
    data = det.ReplayData(seed=str(seed), rows=rows, start_life=start_life,
                          final_life={str(h): int(p.life) for h, p in world.players.items()},
                          final_zone=final_zone, identity_name=names,
                          layers_rows=[tuple(r) for r in ex.layers.dump()],
                          repl_rows=[tuple(r) for r in ex.replacements.dump()],
                          binder_dump=binder, crashed=crash["error"] if crash else None)
    hits = []
    for fn in (det.d1_life, det.d2_mana, det.d3_counters, det.d4_tokens, det.d5_pt_recompute, det.d6_lifecycle):
        try:
            verdict = fn(data)
        except Exception as exc:  # noqa: BLE001 — a detector that cannot read the game is reported
            hits.append({"detector": fn.__name__, "detail": f"detector error {type(exc).__name__}: {exc}"[:160]})
            continue
        for hit in getattr(verdict, "hits", []) or []:
            hits.append({"detector": fn.__name__, "detail": str(getattr(hit, "detail", hit))[:160]})
    return {"seed": seed, "turns": game.turns, "reason": game.reason, "loser": loser, "crash": crash,
            "casts": casts, "max_acts_per_turn": per_turn.most_common(3), "loops": loops, "hits": hits}


def summarize(results: list[dict[str, Any]], supply: Any) -> dict[str, Any]:
    crashes = Counter((r["crash"]["error"][:90], r["crash"]["attempted"]) for r in results if r["crash"])
    hits = Counter((h["detector"], h["detail"][:90]) for r in results for h in r["hits"])
    cast_games: Counter = Counter()
    cast_wins: Counter = Counter()
    for r in results:
        if r["crash"] or r["loser"] is None:
            continue
        for oid, seats in r["casts"].items():
            for seat in set(seats):
                cast_games[oid] += 1
                cast_wins[oid] += seat != r["loser"]
    by_mv: dict[int, list[str]] = defaultdict(list)
    for oid in cast_games:
        meta = supply.metas.get(oid)
        if meta is not None:
            by_mv[meta.mana_value].append(oid)
    outliers = []
    for oids in by_mv.values():
        games = sum(cast_games[o] for o in oids)
        wins = sum(cast_wins[o] for o in oids)
        for oid in oids:
            n, k = cast_games[oid], cast_wins[oid]
            if n < 20:
                continue
            rest_n, rest_k = games - n, wins - k
            if rest_n < 20:
                continue
            p = (k + rest_k) / (n + rest_n)
            se = math.sqrt(p * (1 - p) * (1 / n + 1 / rest_n)) or 1e-9
            z = (k / n - rest_k / rest_n) / se
            if abs(z) > 3:
                outliers.append({"card": supply.metas[oid].name, "mana_value": supply.metas[oid].mana_value,
                                 "cast_games": n, "win_rate": round(k / n, 3),
                                 "same_mv_win_rate": round(rest_k / rest_n, 3), "z": round(z, 2)})
    acts = Counter()
    for r in results:
        for key, n in r["max_acts_per_turn"]:
            name = key.split("|", 1)[1]
            acts[name] = max(acts[name], n)
    repeatable = [{"ability": k, "max_per_turn": v} for k, v in acts.most_common() if v >= 6]
    loops = Counter(x for r in results for x in r["loops"])
    return {
        "games": len(results), "crashed": sum(bool(r["crash"]) for r in results),
        "crashes": [{"error": e, "attempted": a, "games": n} for (e, a), n in crashes.most_common()],
        "detector_hits": [{"detector": d, "detail": t, "games": n} for (d, t), n in hits.most_common()],
        "outliers": sorted(outliers, key=lambda o: -abs(o["z"])),
        "repeatable_activations": repeatable,
        "trigger_loops": [{"source": s, "games": n} for s, n in loops.most_common()],
        "cards_cast": len(cast_games),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("set")
    ap.add_argument("--games", type=int, default=200)
    ap.add_argument("--mode", default="compiled", choices=("castable", "compiled", "verified"))
    ap.add_argument("--unverified", action="store_true")
    ap.add_argument("--deck-mode", default="stress")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--first-seed", type=int, default=1)
    ap.add_argument("--out")
    args = ap.parse_args(argv)
    jobs = [(args.set, args.mode, args.unverified, args.deck_mode, s)
            for s in range(args.first_seed, args.first_seed + args.games)]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(play_one, jobs, chunksize=4))
    summary = summarize(results, _supply(args.set, args.mode, args.unverified))
    summary.update({"set": args.set, "mode": args.mode, "unverified_records": args.unverified,
                    "deck_mode": args.deck_mode, "seeds": [args.first_seed, args.first_seed + args.games - 1]})
    text = json.dumps(summary, indent=1)
    if args.out:
        Path(args.out).write_text(text + "\n")
    print(json.dumps({k: (v if not isinstance(v, list) else v[:8]) for k, v in summary.items()}, indent=1))
    return 1 if summary["crashed"] or summary["detector_hits"] else 0


if __name__ == "__main__":
    sys.exit(main())
