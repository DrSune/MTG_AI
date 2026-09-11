"""Collect the real distribution of position complexity from the engine.

Latency has to be measured over the positions the bot will actually face, not over a
synthetic average. The owner's point is precisely that difficulty varies:

    "some turns will require more reasoning passes than others, due to increased
     complexity of the board and state or number of possible actions to take"

So the harness samples real games and records, at every decision point, the two numbers
that drive network cost: how many tokens the board produces, and how many legal actions
have to be scored. The tail of those distributions is what sets the tail of latency, and
the tail is what loses matches.

This module only touches the engine. It imports no torch, so it is safe to run in an
environment-worker process.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List
from MTG_bot.utils.rng import seed_all

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@dataclass
class PositionSample:
    game: int
    step: int
    turn: int
    n_entities: int          # every entity in the graph, which is what the encoder sees today
    n_visible: int           # entities excluding library contents, i.e. what it SHOULD see
    n_actions: int
    action_classes: dict


def _zone_of(graph, e) -> str:
    p = e.properties
    if p.get("is_on_battlefield"):
        return "battlefield"
    if p.get("is_in_hand"):
        return "hand"
    if p.get("is_in_graveyard"):
        return "graveyard"
    return "other"


def collect(n_games: int = 8, max_steps: int = 400, seed: int = 20260910,
            game_mode: str = "Commander") -> List[PositionSample]:
    from MTG_bot.rule_engine.game_initializer import initialize_game_state
    from MTG_bot.rule_engine.engine import Engine

    rng = random.Random(seed)
    out: List[PositionSample] = []

    for g in range(n_games):
        # Seed every named stream the engine draws from, so a run is repeatable.
        # NOT full determinism: entity ids come from uuid4 and some trigger ordering
        # iterates set differences. See docs/ARCHITECTURE.md and MTG_bot/utils/rng.py.
        seed_all(seed + g, seed_frameworks=False)
        deck_a = [rng.randint(1, 397) for _ in range(100)]
        deck_b = [rng.randint(1, 397) for _ in range(100)]
        graph = initialize_game_state(deck_a, deck_b, game_mode=game_mode)
        engine = Engine(graph)   # recorder defaults to NullRecorder

        for step in range(max_steps):
            if engine.game_over:
                break
            moves = engine.get_legal_moves()
            if not moves:
                break

            classes = Counter(type(m).__name__ for m in moves)
            visible = sum(
                1 for e in graph.entities.values() if _zone_of(graph, e) != "other"
            )
            out.append(PositionSample(
                game=g, step=step, turn=graph.turn_number,
                n_entities=len(graph.entities),
                n_visible=visible,
                n_actions=len(moves),
                action_classes=dict(classes),
            ))
            engine.execute_move(rng.choice(moves))

    return out


def summarise(samples: List[PositionSample]) -> dict:
    def pct(xs, q):
        xs = sorted(xs)
        if not xs:
            return 0
        i = min(len(xs) - 1, max(0, int(round(q * (len(xs) - 1)))))
        return xs[i]

    acts = [s.n_actions for s in samples]
    ents = [s.n_entities for s in samples]
    vis = [s.n_visible for s in samples]
    cls = Counter()
    for s in samples:
        cls.update(s.action_classes)

    def dist(xs):
        return {
            "min": min(xs), "p50": pct(xs, .50), "p90": pct(xs, .90),
            "p99": pct(xs, .99), "p999": pct(xs, .999), "max": max(xs),
            "mean": round(statistics.mean(xs), 1),
        }

    return {
        "n_samples": len(samples),
        "n_games": len({s.game for s in samples}),
        "legal_actions": dist(acts),
        "entities_all": dist(ents),
        "entities_visible": dist(vis),
        "action_class_counts": dict(cls.most_common()),
    }


def main():
    ap = argparse.ArgumentParser(description="Sample real position complexity from the engine.")
    ap.add_argument("--games", type=int, default=8)
    ap.add_argument("--max-steps", type=int, default=400)
    ap.add_argument("--seed", type=int, default=20260910)
    ap.add_argument("--mode", default="Commander")
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args()

    t0 = time.perf_counter()
    samples = collect(a.games, a.max_steps, a.seed, a.mode)
    dt = time.perf_counter() - t0

    summary = summarise(samples)
    summary["collect_seconds"] = round(dt, 2)
    summary["ms_per_step_including_legal_moves"] = round(dt / max(1, len(samples)) * 1000, 3)

    print(json.dumps(summary, indent=2))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(
            {"summary": summary, "samples": [asdict(s) for s in samples]}, indent=1
        ), encoding="utf-8")
        print(f"\nwrote {a.out}")


if __name__ == "__main__":
    main()
