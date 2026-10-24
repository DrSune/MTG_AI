"""Duplicate-format matches (docs/DESIGN_BENCHMARK.md §6).

Each deal fixes both decks and both library orders: decks depend only on
``(seed, deck_pairs_seed)`` (``games.py:1457``), library order on the engine's seeded shuffle
(``games.py:404``), and setup consults no policy. The deal is played twice with the agents' seats
swapped, and **the pair is the unit**. Deal luck cancels inside a pair. Engine randomness during
play still diverges once the two games diverge; that is inherent, and stated.

Outcomes are classified, never merged (the Goodhart table in the design doc):

| outcome | meaning |
|---|---|
| win / loss | for agent A |
| draw-mutual | both players lost at once |
| draw-stall | the engine's stall rule (3 identical rounds) |
| draw-cap | the turn cap |
| void-crash | the engine raised |
| void-agent | an agent broke the protocol |
| void-infra | the model endpoint failed |
| void-harness | a routing contract failed |

A void voids the whole pair. A crash is audited, never scored.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from MTG_bot.bench import CANARY
from MTG_bot.bench.agents import AgentError
from MTG_bot.bench.protocol import AskRoutingError, UnknownAskSite
from MTG_bot.bench.router import SeatRouter
from MTG_bot.bench.stats import elo_from_score, paired_bootstrap, wilson
from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
from MTG_bot.core.executor.games import (
    TURN_CAP,
    _describe_crash,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)
from MTG_bot.utils.rng import get_master_seed

REPO = Path(__file__).resolve().parents[2]
SCORE = {"win": 1.0, "loss": 0.0, "draw-mutual": 0.5, "draw-stall": 0.5, "draw-cap": 0.5, "draw-other": 0.5}


class InfraError(RuntimeError):
    """Raised by a driver whose backing service failed (``llm.AgentInfraError`` subclasses it)."""


@dataclass(frozen=True)
class DealSpec:
    seed: int
    set_code: str = "M21"
    pool_mode: str = "castable"  # "all" deals engine-flagged cards and voids games for it
    deck_pairs_seed: int = 1409
    turn_cap: int = TURN_CAP


#: (deal, game index 0|1, seat 0|1) -> a fresh seat driver for that one game
AgentFactory = Callable[[DealSpec, int, int], Any]


def git_revision() -> dict[str, Any]:
    def run(*args: str) -> str:
        done = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False)
        return done.stdout.strip()

    return {"rev": run("rev-parse", "--short", "HEAD"), "dirty": bool(run("status", "--porcelain", "--untracked-files=no"))}


def manifest(name_a: str, name_b: str, deals: Sequence[DealSpec], opts: ViewOptions) -> dict[str, Any]:
    return {
        "kind": "manifest",
        "canary": CANARY,
        "argv": sys.argv,
        "master_seed": get_master_seed(),
        "git": git_revision(),
        "agents": [name_a, name_b],
        "deals": [d.seed for d in deals],
        "deal_spec": {k: v for k, v in asdict(deals[0]).items() if k != "seed"} if deals else {},
        "view": asdict(opts),
        "engine_notes": "batch Magic: no priority, one act window per turn, mana pools never empty",
    }


def _classify(game: Any, a_seat: int) -> tuple[str, str]:
    reason = game.reason or ""
    if reason.startswith("STALL"):
        return "draw-stall", reason
    if reason.startswith("turn cap"):
        return "draw-cap", reason
    order = game.world.player_order
    losers = [i for i, seat in enumerate(order) if game.is_loser(seat)]
    if len(losers) == 2:
        return "draw-mutual", reason
    if len(losers) == 1:
        return ("loss" if losers[0] == a_seat else "win"), reason
    return "draw-other", reason


def play_seated_game(
    deal: DealSpec,
    drivers: Sequence[Any],
    *,
    a_seat: int,
    oracle: OracleIndex,
    opts: ViewOptions,
) -> dict[str, Any]:
    supply = get_supply(deal.pool_mode, deal.set_code)
    game = _setup_game(deal.seed, supply, deal_decks(deal.seed, deal.deck_pairs_seed, supply))
    setup_fp = game.executor.state_fingerprint()
    router = SeatRouter(game, drivers, [SeatLens(s, oracle, opts) for s in (0, 1)], supply=supply)
    started = time.monotonic()
    outcome, reason, crash = None, "", None
    try:
        _play(game, router, game.world.player_order, deal.turn_cap)
    except InfraError as error:
        outcome, reason = "void-infra", f"{type(error).__name__}: {error}"
    except AgentError as error:
        outcome, reason = "void-agent", str(error)
    except (AskRoutingError, UnknownAskSite) as error:
        outcome, reason = "void-harness", str(error)
    except Exception as error:  # noqa: BLE001 - an engine crash is a finding to audit, never a result
        outcome, reason = "void-crash", f"{type(error).__name__}: {error}"
        crash = _describe_crash(game, error, router, f"seed {deal.seed} set {deal.set_code}")
    if outcome is None:
        outcome, reason = _classify(game, a_seat)
    row: dict[str, Any] = {
        "kind": "game",
        "deal": deal.seed,
        "set": deal.set_code,
        "pool": deal.pool_mode,
        "a_seat": a_seat,
        "outcome": outcome,
        "score_a": SCORE.get(outcome),
        "reason": reason,
        "turns": game.turns,
        "acts": game.acts,
        "setup_fp": setup_fp,
        "wall_s": round(time.monotonic() - started, 3),
        "seat_stats": [dict(st) for st in router.stats],
        "agent_stats": [dict(getattr(d, "stats", {}) or {}) for d in drivers],
    }
    if crash is not None:
        row["crash"] = crash
    return row


def play_duplicate(
    deal: DealSpec,
    make_a: AgentFactory,
    make_b: AgentFactory,
    *,
    oracle: OracleIndex,
    opts: ViewOptions,
) -> list[dict[str, Any]]:
    rows = []
    for game_index, a_seat in ((0, 0), (1, 1)):
        drivers = [None, None]
        drivers[a_seat] = make_a(deal, game_index, a_seat)
        drivers[1 - a_seat] = make_b(deal, game_index, 1 - a_seat)
        rows.append(play_seated_game(deal, drivers, a_seat=a_seat, oracle=oracle, opts=opts))
    void = any(r["outcome"].startswith("void") for r in rows)
    for r in rows:
        r["pair_void"] = void
    return rows


def run_match(
    make_a: AgentFactory,
    make_b: AgentFactory,
    deals: Sequence[DealSpec],
    *,
    name_a: str,
    name_b: str,
    opts: ViewOptions | None = None,
    out: Path | None = None,
) -> list[dict[str, Any]]:
    opts = opts or ViewOptions()
    oracle = OracleIndex.for_sets(*sorted({d.set_code for d in deals}))
    rows: list[dict[str, Any]] = [manifest(name_a, name_b, deals, opts)]
    handle = out.open("w", encoding="utf-8") if out is not None else None
    try:
        if handle is not None:
            handle.write(json.dumps(rows[0]) + "\n")
        for deal in deals:
            for row in play_duplicate(deal, make_a, make_b, oracle=oracle, opts=opts):
                rows.append(row)
                if handle is not None:
                    handle.write(json.dumps(row, default=str) + "\n")
                    handle.flush()
    finally:
        if handle is not None:
            handle.close()
    return rows


def summarize(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """W/L and draws by cause for agent A, the decisive rate, and the paired score with its CI."""
    games = [r for r in rows if r.get("kind") == "game"]
    counts = Counter(r["outcome"] for r in games)
    by_deal: dict[int, list[float]] = {}
    for r in games:
        if not r["pair_void"]:
            by_deal.setdefault(r["deal"], []).append(r["score_a"])
    pairs = [sum(v) / len(v) for v in by_deal.values() if len(v) == 2]
    mean, lo, hi = paired_bootstrap(pairs) if pairs else (float("nan"),) * 3
    wins, losses = counts["win"], counts["loss"]
    return {
        "games": len(games),
        "outcomes": dict(sorted(counts.items())),
        "decisive_rate": round((wins + losses) / len(games), 4) if games else 0.0,
        "winrate_decisive": [round(x, 4) for x in (wins / (wins + losses) if wins + losses else float("nan"), *wilson(wins, wins + losses))],
        "pairs": len(pairs),
        "pair_score": [round(x, 4) for x in (mean, lo, hi)],
        "elo_vs_b": [round(elo_from_score(x), 1) for x in (mean, lo, hi)] if pairs else None,
        "label": "exploratory (no pre-registration file)",
    }
