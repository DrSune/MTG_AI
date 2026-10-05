"""Episode collector: engine games -> offline-derivable RL trajectories.

Round-19 batch-0 (design plan ``08-experiment-backlog`` tier A): the training
loop needs (episode, reward) pairs WITHOUT re-simulating, so the collector
wraps the existing harness the way ``games.py``'s 14g trace recorder does —
a provider installed at the :class:`DecisionStream` ask sites (the B-4 lane:
``executor.decisions.provider`` registered by ``_play`` from the driver
policy's ``answer`` attribute) and a post-game read of the journal. The
engine is NOT edited: every hook rides a public attribute or the exact
registration point ``play_game`` already uses (the recorder's transparent
``policy.answer = wrap(policy.answer)`` masking is the in-tree precedent,
as is ``tools/run_scenarios.py``'s PASS-fallback provider).

Trajectory schema (JSONL, one episode per line, everything a reward model
needs OFFLINE):

* header: ``seed`` / ``deck_pairs_seed`` / ``turn_cap`` / ``pool`` /
  ``policy`` — a seed + seat record so the D9/D10 eval gates (rulings doc
  04: rotate eval seeds, masked-observation ablation) can attribute every
  trajectory to exactly one policy × seed × seat perspective;
* ``steps``: one row per answered ask — ``{ask_id, vocab (the site tag the
  engine asked with), candidates (the vocabulary tuple in CANONICAL
  presented order), chosen_idx, clock (the journal's monotonic clock at
  the ask), seat}``. The chosen token is ``candidates[chosen_idx]``; the
  stream still re-validates it (C15: no default, ever);
* ``terminal``: ``{winner, reason, turns, lives}``;
* ``rewards``: the journal's reward-relevant rows (DAMAGE / LIFE_LOST /
  COMBAT_DAMAGE / COUNTER / KICKBACK / WINDOW_* ) with minimal fields, so
  reward shaping is derivable without a re-simulation.

Determinism (gate-tested): the policy consumes ONLY its own seeded
``random.Random`` and the engine asks in a deterministic order, so one seed
identifies the whole trajectory — the collector adds no nondeterminism
(its clock is the journal's own, its index→token map is positional).

Policies: the pluggable :class:`AskPolicy` protocol gets an
:class:`AskContext` and returns an index into the canonical candidate list.
Built-ins: ``random`` (uniform, the collector-compatible RandomPolicy
mirror), ``first`` (scripted floor: always index 0) and ``pass-floor``
(the rig's disciplined floor — answer ``PASS`` when the vocab carries it,
else index 0).

Run the batch-0 throughput measurement::

    .venv/bin/python -m tools.training.collector --bench --games 20 --pool all
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from MTG_bot.core.executor.games import (
    TURN_CAP,
    RandomPolicy,
    Supply,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)

#: Journal kinds the collector copies into every episode's reward lane.
#: ``COUNTER`` is the engine's tag for a countered spell (rulings doc 06);
#: ``WINDOW_*``/``KICKBACK`` ride along because response-window play is a
#: reward-relevant decision (rung-2 backlog), not engine trivia.
REWARD_KINDS = frozenset(
    {
        "DAMAGE",
        "LIFE_LOST",
        "LIFE_GAINED",
        "COMBAT_DAMAGE",
        "COUNTER",
        "KICKBACK",
        "WINDOW_OPEN",
        "WINDOW_PASS",
    }
)


# --------------------------------------------------------------- the protocol
@dataclass(frozen=True)
class AskContext:
    """What a policy is SHOWN at one ask: the engine's own vocabulary in
    canonical presented order, the site tag it was asked with, and a
    minimal public-world summary (turn, active seat, lives)."""

    vocab: str  # the (vocab, what) site tag the producer asked with
    candidates: tuple[str, ...]  # canonical presented order (the vocab tuple)
    world: dict[str, Any]


@runtime_checkable
class AskPolicy(Protocol):
    """Pluggable answerer: sees an ask, returns the CANDIDATE INDEX.

    The collector maps the index onto the canonical token and hands the
    token to the stream, which re-validates it — an out-of-vocabulary
    policy (index out of range) raises instead of silently defaulting,
    exactly the C15 contract."""

    def decide(self, ctx: AskContext) -> int: ...


@dataclass
class RandomAsk:
    """Uniform over the given vocabulary, one seeded stream (the collector-
    compatible mirror of :class:`RandomPolicy.answer`)."""

    seed: int
    rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)

    def decide(self, ctx: AskContext) -> int:
        return self.rng.randrange(len(ctx.candidates))


class FirstAsk:
    """Scripted floor: always take the first legal candidate (index 0)."""

    def decide(self, ctx: AskContext) -> int:
        return 0


class PassFirstAsk:
    """The rig's disciplined floor (``run_scenarios`` precedent): answer
    ``PASS`` whenever the vocabulary carries it, else the first candidate."""

    def decide(self, ctx: AskContext) -> int:
        try:
            return ctx.candidates.index("PASS")
        except ValueError:
            return 0


POLICIES: dict[str, type] = {
    "random": RandomAsk,
    "first": FirstAsk,
    "pass-floor": PassFirstAsk,
}


# ----------------------------------------------------------------- collector
class EpisodeCollector:
    """Runs seeded executor games through the existing turn loop and writes
    one JSONL trajectory per game. No engine edit: the ask hook rides the
    ``policy.answer`` masking and the reward lane reads the journal."""

    def __init__(
        self,
        pool_mode: str = "all",
        deck_pairs_seed: int = 1409,
        turn_cap: int = TURN_CAP,
        policy: str = "random",
        supply: Supply | None = None,
    ) -> None:
        if policy not in POLICIES:
            raise ValueError(f"unknown policy {policy!r} (have {sorted(POLICIES)})")
        self.pool_mode = pool_mode
        self.deck_pairs_seed = deck_pairs_seed
        self.turn_cap = turn_cap
        self.policy_name = policy
        self.supply = supply if supply is not None else get_supply(pool_mode)

    # ------------------------------------------------------------ one game
    def run_episode(self, seed: int) -> dict[str, Any]:
        """One seeded game -> the trajectory dict (JSON-safe)."""
        supply = self.supply
        decks = deal_decks(seed, self.deck_pairs_seed, supply)
        game = _setup_game(seed, supply, decks)
        executor = game.executor
        driver = RandomPolicy(seed)  # act-side driver: plays the query surface
        ask = (
            POLICIES[self.policy_name](seed)
            if self.policy_name == "random"
            else POLICIES[self.policy_name]()
        )
        steps: list[dict[str, Any]] = []
        seats = [str(seat) for seat in game.world.player_order]

        def provider(vocab: tuple[str, ...], what: str) -> str:
            world = game.world
            ctx = AskContext(
                vocab=what,
                candidates=tuple(vocab),
                world={
                    "turn": world.turn,
                    "seat": seats.index(str(world.active_player)),
                    "lives": [world.players[s].life for s in world.player_order],
                },
            )
            idx = ask.decide(ctx)
            if not 0 <= idx < len(vocab):
                raise ValueError(f"collector: policy index {idx} out of {vocab}")
            steps.append(
                {
                    "ask_id": len(steps),
                    "vocab": what,
                    "candidates": list(vocab),
                    "chosen_idx": idx,
                    "clock": executor.journal.clock,
                    "seat": ctx.world["seat"],
                }
            )
            return vocab[idx]

        # The games.py masking precedent: _play registers the driver's
        # ``answer`` attribute as the stream's ask-time provider, so
        # shadowing the instance attribute with our recording closure IS the
        # installation at the ask sites — the engine file never changes.
        driver.answer = provider  # type: ignore[method-assign]
        crash = ""
        try:
            _play(game, driver, list(game.world.player_order), self.turn_cap)
            reason = game.reason
        except BaseException as error:  # noqa: BLE001 - recorded, never hidden
            reason = f"crash:{type(error).__name__}: {error}"
            crash = type(error).__name__

        lives = {
            seat: game.world.players[handle].life
            for seat, handle in zip(seats, game.world.player_order, strict=True)
        }
        losers = [
            s
            for s, h in zip(seats, game.world.player_order, strict=True)
            if game.is_loser(h)
        ]
        winner = (
            next((s for s in seats if s not in losers), None)
            if len(losers) == 1
            else None
        )
        rewards: list[dict[str, Any]] = []
        for clock, kind, subject, cause, _verb, payload in executor.journal.dump():
            if kind in REWARD_KINDS:
                data: Any = payload  # dump() rows are object-tuples
                rewards.append(
                    {
                        "clock": clock,
                        "kind": kind,
                        "subject": subject,
                        "cause": cause,
                        "data": [str(item) for item in data],
                    }
                )
        return {
            "seed": seed,
            "pool": self.pool_mode,
            "deck_pairs_seed": self.deck_pairs_seed,
            "turn_cap": self.turn_cap,
            "policy": self.policy_name,
            "seats": seats,
            "steps": steps,
            "terminal": {
                "winner": winner,
                "reason": reason,
                "turns": game.turns,
                "lives": lives,
                "crash": crash or None,
            },
            "rewards": rewards,
        }

    # ------------------------------------------------------------- a batch
    def collect(
        self, seeds: list[int], out_path: Path | None = None
    ) -> list[dict[str, Any]]:
        """Sequential collection; writes JSONL when given a path."""
        episodes = [self.run_episode(seed) for seed in seeds]
        if out_path is not None:
            _write_jsonl(episodes, out_path)
        return episodes

    def collect_parallel(
        self, seeds: list[int], workers: int, out_path: Path | None = None
    ) -> list[dict[str, Any]]:
        """Multiprocessing collection (one supply compile per worker); lines
        are seed-sorted so the output file is order-identical to sequential."""
        jobs = [
            {
                "seed": seed,
                "pool_mode": self.pool_mode,
                "deck_pairs_seed": self.deck_pairs_seed,
                "turn_cap": self.turn_cap,
                "policy": self.policy_name,
            }
            for seed in seeds
        ]
        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(
            workers, initializer=_warm_supply, initargs=(self.pool_mode,)
        ) as pool:
            episodes = pool.map(_worker_episode, jobs, chunksize=1)
        episodes.sort(key=lambda ep: ep["seed"])
        if out_path is not None:
            _write_jsonl(episodes, out_path)
        return episodes


# module-level helpers: picklable across the spawn boundary
_POOL_MODE = "all"


def _warm_supply(pool_mode: str) -> None:
    global _POOL_MODE
    _POOL_MODE = pool_mode
    get_supply(pool_mode)  # one 305-card compile per worker, before timing


def _worker_episode(job: dict[str, Any]) -> dict[str, Any]:
    collector = EpisodeCollector(
        pool_mode=job["pool_mode"],
        deck_pairs_seed=job["deck_pairs_seed"],
        turn_cap=job["turn_cap"],
        policy=job["policy"],
    )
    return collector.run_episode(job["seed"])


def _write_jsonl(episodes: list[dict[str, Any]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for episode in episodes:
            fh.write(json.dumps(episode, sort_keys=True) + "\n")


def _count_rows(episodes: list[dict[str, Any]]) -> tuple[int, int]:
    decisions = sum(len(ep["steps"]) for ep in episodes)
    journal_rows = sum(len(ep["rewards"]) for ep in episodes)
    return decisions, journal_rows


def bench(games: int, pool_mode: str, workers_list: list[int]) -> dict[str, Any]:
    """Batch-0 throughput: N games, single process and each worker count."""
    report: dict[str, Any] = {"games": games, "pool": pool_mode}
    base = list(range(1, games + 1))
    for workers in workers_list:
        started = time.perf_counter()
        if workers == 1:
            collector = EpisodeCollector(pool_mode=pool_mode)
            supply_seconds = collector.supply.pool_seconds
            episodes = collector.collect(base)
        else:
            warm = get_supply(pool_mode)  # parent compile (not counted)
            supply_seconds = warm.pool_seconds
            episodes = EpisodeCollector(pool_mode=pool_mode).collect_parallel(
                base, workers
            )
        elapsed = time.perf_counter() - started
        decisions, reward_rows = _count_rows(episodes)
        turns = sum(ep["terminal"]["turns"] for ep in episodes)
        crashes = [ep["seed"] for ep in episodes if ep["terminal"]["crash"]]
        report[f"workers_{workers}"] = {
            "wall_seconds": round(elapsed, 2),
            "games_per_sec": round(games / elapsed, 3),
            "turns_per_sec": round(turns / elapsed, 2),
            "decisions_per_sec": round(decisions / elapsed, 2),
            "decisions": decisions,
            "turns": turns,
            "reward_rows": reward_rows,
            "compile_seconds": round(supply_seconds, 2),
            "crashes": crashes,
        }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Episode collector (training batch-0)."
    )
    parser.add_argument("--bench", action="store_true", help="throughput measurement")
    parser.add_argument("--games", type=int, default=20)
    parser.add_argument("--pool", default="all", choices=("all", "engine", "castable"))
    parser.add_argument("--policy", default="random", choices=sorted(POLICIES))
    parser.add_argument("--turn-cap", type=int, default=TURN_CAP)
    parser.add_argument("--seeds", type=int, nargs="+", default=None)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.bench:
        workers_list = [1] if args.workers == 1 else [1, args.workers]
        print(json.dumps(bench(args.games, args.pool, workers_list), indent=2))
        return 0
    seeds = args.seeds if args.seeds else list(range(1, 4))
    collector = EpisodeCollector(
        pool_mode=args.pool, policy=args.policy, turn_cap=args.turn_cap
    )
    episodes = (
        collector.collect(seeds, args.out)
        if args.workers <= 1
        else collector.collect_parallel(seeds, args.workers, args.out)
    )
    for episode in episodes:
        print(
            f"seed {episode['seed']}: turns={episode['terminal']['turns']} "
            f"decisions={len(episode['steps'])} rewards={len(episode['rewards'])} "
            f"reason={episode['terminal']['reason']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
