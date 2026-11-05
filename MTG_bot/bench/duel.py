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
| void-forfeit | strikes exhausted on an ask with no do-nothing option |
| refused-leaky | a seat faced a leaky name ask (CHOOSE_NAME enumerates hidden cards; §3.5 neutralization) |

A void voids the whole pair; so does a refused-leaky. A crash is audited, never scored.

The manifest records each llm seat's identity (model, endpoint, settings, usage_missing); a
duel refuses to start when an llm seat has no model identity. If any seat's responses lacked a
usage block, the summary flags ``token_stats: "invalid"`` and token counts are not presented.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from MTG_bot.bench import CANARY
from MTG_bot.bench.agents import AgentError, AgentForfeitError, InfraError
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
SCORE = {
    "win": 1.0,
    "loss": 0.0,
    "draw-mutual": 0.5,
    "draw-stall": 0.5,
    "draw-cap": 0.5,
    "draw-other": 0.5,
}


@dataclass(frozen=True)
class DealSpec:
    seed: int
    set_code: str = "M21"
    pool_mode: str = (
        "castable"  # "all" deals engine-flagged cards and voids games for it
    )
    deck_pairs_seed: int = 1409
    turn_cap: int = TURN_CAP
    deck_mode: str = "stress"  # or "coherent" (two colours, 24 basics; B-45)


#: (deal, game index 0|1, seat 0|1) -> a fresh seat driver for that one game
AgentFactory = Callable[[DealSpec, int, int], Any]


def git_revision() -> dict[str, Any]:
    def run(*args: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=False
        )
        return done.stdout.strip()

    return {
        "rev": run("rev-parse", "--short", "HEAD"),
        "dirty": bool(run("status", "--porcelain", "--untracked-files=no")),
    }


def manifest(
    name_a: str,
    name_b: str,
    deals: Sequence[DealSpec],
    opts: ViewOptions,
    identities: Mapping[str, dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    identities = identities or {}
    return {
        "kind": "manifest",
        "canary": CANARY,
        "argv": sys.argv,
        "master_seed": get_master_seed(),
        "git": git_revision(),
        "agents": [name_a, name_b],
        "identities": {"a": identities.get("a"), "b": identities.get("b")},
        "deals": [d.seed for d in deals],
        "deal_spec": {k: v for k, v in asdict(deals[0]).items() if k != "seed"}
        if deals
        else {},
        "view": asdict(opts),
        "engine_notes": "batch Magic: no priority, one act window per turn, mana pools empty as each step and phase ends",
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
    game = _setup_game(
        deal.seed, supply, deal_decks(deal.seed, deal.deck_pairs_seed, supply, deal.deck_mode)
    )
    setup_fp = game.executor.state_fingerprint()
    router = SeatRouter(
        game, drivers, [SeatLens(s, oracle, opts) for s in (0, 1)], supply=supply
    )
    started = time.monotonic()
    outcome, reason, crash = None, "", None
    try:
        _play(game, router, game.world.player_order, deal.turn_cap)
    except InfraError as error:
        outcome, reason = "void-infra", f"{type(error).__name__}: {error}"
    except AgentForfeitError as error:
        outcome, reason = "void-forfeit", str(error)
    except AgentError as error:
        outcome, reason = "void-agent", str(error)
    except (AskRoutingError, UnknownAskSite) as error:
        outcome, reason = "void-harness", str(error)
    except Exception as error:  # noqa: BLE001 - an engine crash is a finding to audit, never a result
        outcome, reason = "void-crash", f"{type(error).__name__}: {error}"
        crash = _describe_crash(
            game, error, router, f"seed {deal.seed} set {deal.set_code}"
        )
    if outcome is None:
        outcome, reason = _classify(game, a_seat)
    # §3.5 neutralization: a completed game in which any seat faced a leaky name ask (the
    # engine's CHOOSE_NAME vocabulary enumerates hidden cards) is refused, not reported.
    leaky = sum(st.get("leaky_asks", 0) for st in router.stats)
    if leaky > 0:
        outcome = "refused-leaky"
        reason = (
            f"{leaky} leaky ask(s): CHOOSE_NAME enumerated hidden cards; "
            "DESIGN_BENCHMARK §3.5 neutralization"
        )
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
        rows.append(
            play_seated_game(deal, drivers, a_seat=a_seat, oracle=oracle, opts=opts)
        )
    # A void or a refused-leaky game voids the whole pair: deal luck must not paper over either.
    void = any(
        r["outcome"].startswith("void") or r["outcome"] == "refused-leaky" for r in rows
    )
    for r in rows:
        r["pair_void"] = void
    return rows


#: Trailing spaces reserved after the manifest line so the settled ``usage_missing`` count can
#: be written into the line in place, without shifting the game rows written behind it.
MANIFEST_PAD = 128


def run_match(
    make_a: AgentFactory,
    make_b: AgentFactory,
    deals: Sequence[DealSpec],
    *,
    name_a: str,
    name_b: str,
    opts: ViewOptions | None = None,
    out: Path | None = None,
    identities: Mapping[str, dict[str, Any] | None] | None = None,
) -> list[dict[str, Any]]:
    ids = dict(identities or {})
    for key, ident in ids.items():
        if ident is not None and not ident.get("model"):
            raise ValueError(
                f"refusing to start a duel: llm seat {key!r} has no model identity"
            )
    opts = opts or ViewOptions()
    oracle = OracleIndex.for_sets(*sorted({d.set_code for d in deals}))
    rows: list[dict[str, Any]] = [manifest(name_a, name_b, deals, opts, ids)]
    handle = out.open("w", encoding="utf-8") if out is not None else None
    first_line = None
    try:
        if handle is not None:
            first_line = json.dumps(rows[0])
            handle.write(first_line + " " * MANIFEST_PAD + "\n")
        for deal in deals:
            for row in play_duplicate(deal, make_a, make_b, oracle=oracle, opts=opts):
                rows.append(row)
                if handle is not None:
                    handle.write(json.dumps(row, default=str) + "\n")
                    handle.flush()
        _settle_manifest(rows[0], rows)
        if handle is not None:
            settled = json.dumps(rows[0])
            if len(settled) > len(first_line) + MANIFEST_PAD:
                raise ValueError("settled manifest exceeds its reserved line padding")
            handle.seek(0)
            handle.write(settled)
    finally:
        if handle is not None:
            handle.close()
    return rows


def _settle_manifest(
    manifest_row: dict[str, Any], rows: Sequence[dict[str, Any]]
) -> None:
    """Fold each seat's final ``usage_missing`` count into the manifest identity (A3 honesty)."""
    ids = manifest_row.get("identities") or {}
    for key in ("a", "b"):
        ident = ids.get(key)
        if not ident or "usage_missing" not in ident:
            continue
        total = 0
        for r in rows:
            if r.get("kind") != "game":
                continue
            stats = r.get("agent_stats") or []
            seat = r["a_seat"] if key == "a" else 1 - r["a_seat"]
            if seat < len(stats):
                total += stats[seat].get("usage_missing", 0)
        ident["usage_missing"] = int(total)


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
    usage_missing = sum(
        st.get("usage_missing", 0) for r in games for st in r.get("agent_stats") or ()
    )
    return {
        "games": len(games),
        "outcomes": dict(sorted(counts.items())),
        "refused_leaky": counts.get("refused-leaky", 0),
        "usage_missing": usage_missing,
        # With missing usage blocks the endpoint did not report its tokens, so token counts
        # are refused a number; calls/decisions/latency stay reported in the game rows.
        "token_stats": "invalid" if usage_missing else "ok",
        "decisive_rate": round((wins + losses) / len(games), 4) if games else 0.0,
        "winrate_decisive": [
            round(x, 4)
            for x in (
                wins / (wins + losses) if wins + losses else float("nan"),
                *wilson(wins, wins + losses),
            )
        ],
        "pairs": len(pairs),
        "pair_score": [round(x, 4) for x in (mean, lo, hi)],
        "elo_vs_b": [round(elo_from_score(x), 1) for x in (mean, lo, hi)]
        if pairs
        else None,
        "label": "exploratory (no pre-registration file)",
    }
