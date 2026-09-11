"""Count MODEL decisions, not human decisions, over whole games.

`positions.py` samples *position complexity* (tokens, menu width). This module answers a
different and, per `reports/LATENCY_FINDINGS.md` Finding 1, more important question:

    how many times must the network be run, SEQUENTIALLY, before a game ends?

Menu width is nearly free at batch 1 (latency is flat in it). The number of sequential
model calls is not: it multiplies straight into the match clock. So the number this file
reports is the one that can actually breach the contract in `docs/DESIGN_LATENCY.md` §1.3.

Everything measured here is a FLOOR, and a very loose one. The current engine has broken
targeting, no real priority, no activated abilities, no triggers on the stack, and two
seats (`docs/ARCHITECTURE.md`). See `--combat-sweep` for the one vector that can be
measured honestly today, because it needs no correct card semantics: the per-pair block
declaration at `engine.py:141-148`.

Three entry points:

  --full-games      decisions per game, per seat, by action class and by phase/step
  --combat-sweep    sequential DeclareBlockerAction decisions as f(attackers, blockers)
  --forced          how much "auto-resolve when exactly one legal option exists" saves

No torch. Engine only.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Dict, Optional
from MTG_bot.utils.rng import seed_all

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# --------------------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------------------

def _pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return 0
    i = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
    return xs[i]


def _dist(xs):
    if not xs:
        return {}
    return {
        "n": len(xs),
        "min": min(xs), "p50": _pct(xs, .50), "p90": _pct(xs, .90),
        "p99": _pct(xs, .99), "max": max(xs),
        "mean": round(statistics.mean(xs), 1),
    }


def _names(id_mapper):
    """phase/step id -> readable name, memoised by the mapper itself."""
    return lambda i: id_mapper.get_name(i, "game_vocabulary")


# --------------------------------------------------------------------------------------
# 1. whole games
# --------------------------------------------------------------------------------------

@dataclass
class Decision:
    game: int
    idx: int                 # sequential index within the game
    turn: int
    phase: str
    step: str
    seat: int                # 0 or 1, the seat that must decide
    n_actions: int
    forced: bool             # exactly one legal option -> a rational agent has no choice
    menu: Dict[str, int]     # class -> count, the menu offered
    chosen: str              # class of the action taken


@dataclass
class GameResult:
    game: int
    n_decisions: int
    per_seat: Dict[int, int]
    turns: int
    termination: str
    forced_decisions: int
    by_class: Dict[str, int]
    by_step: Dict[str, int]
    by_phase: Dict[str, int]


def run_games(n_games: int, max_steps: int, seed: int, mode: str = "Commander",
              keep_decisions: bool = False):
    from MTG_bot.rule_engine.game_initializer import initialize_game_state
    from MTG_bot.rule_engine.engine import Engine

    rng = random.Random(seed)
    results: List[GameResult] = []
    all_decisions: List[Decision] = []

    for g in range(n_games):
        seed_all(seed + g, seed_frameworks=False)
        deck_a = [rng.randint(1, 397) for _ in range(100)]
        deck_b = [rng.randint(1, 397) for _ in range(100)]
        graph = initialize_game_state(deck_a, deck_b, game_mode=mode)
        engine = Engine(graph)
        name = _names(engine.id_mapper)
        seat_of = {pid: i for i, pid in enumerate(graph.players)}

        per_seat = Counter()
        by_class = Counter()
        by_step = Counter()
        by_phase = Counter()
        forced = 0
        n = 0
        termination = "step_cap"

        for step in range(max_steps):
            if engine.game_over:
                termination = "stall" if engine.stall_detected else "win"
                break
            moves = engine.get_legal_moves()
            if not moves:
                termination = "no_legal_moves"
                break

            # Whose decision is this? Mirror engine.get_legal_moves()'s own choice.
            dp = getattr(moves[0], "player_id", graph.active_player_id)
            seat = seat_of.get(dp, -1)
            menu = Counter(type(m).__name__ for m in moves)
            mv = rng.choice(moves)
            cls = type(mv).__name__

            per_seat[seat] += 1
            by_class[cls] += 1
            by_step[name(graph.step)] += 1
            by_phase[name(graph.phase)] += 1
            if len(moves) == 1:
                forced += 1
            if keep_decisions:
                all_decisions.append(Decision(
                    game=g, idx=n, turn=graph.turn_number,
                    phase=name(graph.phase), step=name(graph.step),
                    seat=seat, n_actions=len(moves), forced=len(moves) == 1,
                    menu=dict(menu), chosen=cls,
                ))
            n += 1
            engine.execute_move(mv)

        results.append(GameResult(
            game=g, n_decisions=n, per_seat=dict(per_seat), turns=graph.turn_number,
            termination=termination, forced_decisions=forced,
            by_class=dict(by_class), by_step=dict(by_step), by_phase=dict(by_phase),
        ))

    return results, all_decisions


def summarise_games(results: List[GameResult]) -> dict:
    tot = [r.n_decisions for r in results]
    turns = [r.turns for r in results]
    seat_counts = []
    for r in results:
        seat_counts.extend(r.per_seat.values())
    per_turn = [r.n_decisions / max(1, r.turns) for r in results]

    by_class = Counter()
    by_step = Counter()
    by_phase = Counter()
    forced = 0
    for r in results:
        by_class.update(r.by_class)
        by_step.update(r.by_step)
        by_phase.update(r.by_phase)
        forced += r.forced_decisions

    n_all = sum(tot)
    return {
        "n_games": len(results),
        "terminations": dict(Counter(r.termination for r in results)),
        "decisions_per_game": _dist(tot),
        "decisions_per_seat_per_game": _dist(seat_counts),
        "turns_per_game": _dist(turns),
        "decisions_per_turn": {k: round(v, 2) for k, v in _dist(per_turn).items()},
        "forced_decisions": forced,
        "forced_fraction": round(forced / max(1, n_all), 4),
        "by_chosen_class": dict(by_class.most_common()),
        "by_chosen_class_pct": {k: round(100 * v / max(1, n_all), 1)
                                for k, v in by_class.most_common()},
        "by_step": dict(by_step.most_common()),
        "by_phase": dict(by_phase.most_common()),
    }


# --------------------------------------------------------------------------------------
# 2. the combat sweep: the one explosion vector measurable on today's engine
# --------------------------------------------------------------------------------------

def _creature_ids(limit: int = 40) -> List[int]:
    from MTG_bot.rule_engine.card_database import get_creature_stats
    out = []
    for cid in range(1, 398):
        try:
            if get_creature_stats(cid):
                out.append(cid)
        except Exception:
            pass
        if len(out) >= limit:
            break
    return out


def _plant_board(n_attackers: int, n_blockers: int, seed: int = 7):
    """Build a real graph, put N vanilla creatures on each battlefield, and set up
    the declare-blockers step with all of the attacker's creatures attacking.

    Nothing here is synthetic in the sense that matters: it is the engine's own
    `get_legal_moves()` that is then asked how many decisions it wants.
    """
    from MTG_bot.rule_engine.game_initializer import initialize_game_state
    from MTG_bot.rule_engine.engine import Engine
    from MTG_bot.rule_engine import vocabulary as vocab

    seed_all(seed, seed_frameworks=False)
    cids = _creature_ids(60)
    deck = (cids * 20)[:100]
    graph = initialize_game_state(list(deck), list(deck), game_mode="Commander")
    engine = Engine(graph)

    atk_pid, def_pid = graph.players[0], graph.players[1]
    graph.active_player_id = atk_pid

    def put(pid, count):
        lib = graph.get_entities_in_zone(pid, vocab.ID_ZONE_LIBRARY)
        bz = graph.get_zone(pid, vocab.ID_ZONE_BATTLEFIELD)
        placed = []
        from MTG_bot.rule_engine.card_database import get_creature_stats
        for c in lib:
            if len(placed) >= count:
                break
            if not get_creature_stats(c.type_id):
                continue
            graph._move_card_to_zone(c, bz)
            c.properties["is_on_battlefield"] = True
            c.properties["has_summoning_sickness"] = False
            c.properties["turn_entered"] = 0
            c.properties["tapped"] = False
            placed.append(c)
        return placed

    attackers = put(atk_pid, n_attackers)
    put(def_pid, n_blockers)

    graph.turn_number = 5
    for a in attackers:
        a.properties["is_attacking"] = True
        # attackers tap; that is irrelevant to the blocker menu but keeps state honest
        a.properties["tapped"] = True

    graph.phase = engine.id_mapper.get_id_by_name("Combat Phase", "game_vocabulary")
    graph.step = engine.id_mapper.get_id_by_name("Declare Blockers Step", "game_vocabulary")
    return graph, engine


def combat_sweep(sizes: List[int], seed: int = 7) -> List[dict]:
    """For each (A, B) board, count how many SEQUENTIAL decisions the engine demands
    to reach a fully-committed block assignment, and how wide each menu is.

    'Fully committed' = keep taking DeclareBlockerAction until only PassPriority is
    left. That is the adversarial upper bound the engine's own action space allows:
    an opponent cannot force us to take them, but an agent that wants to block with
    everything must, and every one of them is a separate network forward.
    """
    out = []
    for a in sizes:
        for b in sizes:
            graph, engine = _plant_board(a, b, seed)
            widths = []
            n_seq = 0
            guard = 0
            while True:
                guard += 1
                if guard > 5000:
                    break
                moves = engine.get_legal_moves()
                widths.append(len(moves))
                blocks = [m for m in moves if type(m).__name__ == "DeclareBlockerAction"]
                if not blocks:
                    break
                engine.execute_move(blocks[0])
                n_seq += 1
            out.append({
                "attackers": a,
                "blockers": b,
                "sequential_block_decisions": n_seq,
                "first_menu_width": widths[0] if widths else 0,
                "max_menu_width": max(widths) if widths else 0,
                "predicted_A_times_B": a * b,
            })
    return out


# --------------------------------------------------------------------------------------
# 3. forced-decision accounting
# --------------------------------------------------------------------------------------

def forced_report(results: List[GameResult], decisions: List[Decision]) -> dict:
    """How much does auto-resolving single-option windows save, and where?"""
    by_step_forced = Counter()
    by_step_total = Counter()
    by_class_forced = Counter()
    for d in decisions:
        by_step_total[d.step] += 1
        if d.forced:
            by_step_forced[d.step] += 1
            by_class_forced[d.chosen] += 1
    rows = []
    for step, tot in by_step_total.most_common():
        f = by_step_forced[step]
        rows.append({"step": step, "decisions": tot, "forced": f,
                     "forced_pct": round(100 * f / tot, 1)})
    return {
        "overall_forced_pct": round(100 * sum(by_step_forced.values())
                                    / max(1, len(decisions)), 1),
        "by_step": rows,
        "forced_by_chosen_class": dict(by_class_forced.most_common()),
    }


# --------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Count sequential model decisions per game.")
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--max-steps", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=20260910)
    ap.add_argument("--mode", default="Commander")
    ap.add_argument("--combat-sweep", action="store_true")
    ap.add_argument("--sweep-sizes", default="1,2,4,8,12,16,20")
    ap.add_argument("--no-full-games", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()

    report = {}

    if not a.no_full_games:
        t0 = time.perf_counter()
        results, decisions = run_games(a.games, a.max_steps, a.seed, a.mode,
                                       keep_decisions=True)
        dt = time.perf_counter() - t0
        report["full_games"] = summarise_games(results)
        report["full_games"]["wall_seconds"] = round(dt, 1)
        report["full_games"]["engine_ms_per_decision"] = round(
            dt / max(1, sum(r.n_decisions for r in results)) * 1000, 3)
        report["forced"] = forced_report(results, decisions)
        report["per_game"] = [asdict(r) for r in results]

    if a.combat_sweep:
        sizes = [int(x) for x in a.sweep_sizes.split(",")]
        t0 = time.perf_counter()
        report["combat_sweep"] = combat_sweep(sizes, a.seed)
        report["combat_sweep_seconds"] = round(time.perf_counter() - t0, 1)

    print(json.dumps({k: v for k, v in report.items() if k != "per_game"}, indent=2))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(report, indent=1), encoding="utf-8")
        print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
