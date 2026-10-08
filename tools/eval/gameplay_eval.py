"""Gameplay-level eval (T5-G): a trained BC checkpoint plays FULL games vs
scripted baselines — the number between per-ask accuracy and gameplay.

HONEST DENOMINATOR (finding #1, executed 2026-10-08): the 386 scenario packs
in ``tools/scenarios/*.json`` are scripted puzzle rigs — ``cards``/``steps``
(cast|enter|combat|activate|...)/``expect`` state assertions. ZERO of them
run a 2-seat win/lose game loop, so no pack-vs-pack gameplay denominator
exists. The campaign's ONLY full-game runner is the ``games.py`` rig
(get_supply -> deal_decks -> _setup_game -> _play, TURN_CAP 60, CR 104.4b
stall rule) that produced the batch-6/7 ELO numbers. This tool runs THAT
rig: N seeded deck-pair games per matchup, seat-swap (E7), deterministic
seeds, engine-off CPU torch (the 2026-10-08 18:35 GPU-contention lesson).

PROVIDER-LANE CAVEAT (finding #2): like every duel the campaign has ever
run, the policy seat answers the engine's ASK-SITE vocabulary (may-fires,
scry, choices, PASS offers) through ``DecisionStream.provider``; WHICH
spell to cast / whom to attack stays on the shared ``RandomPolicy`` act
driver (identical seed -> identical act skeleton for both seats and both
matchups). Winrates therefore measure the ask-decision contribution inside
an otherwise shared random skeleton — symmetric, paired, but NOT a
full-agency policy. Reported, not hidden.

Seats & metrics (owner charge):
  * policy seat = a bc7 checkpoint (default bc7_S3_s1_best.pt), plays BOTH
    seats across the seat-swap of every matchup;
  * baselines: RANDOM = ``RandomAsk`` (uniform over the legal presented
    vocabulary); TEACHER = the golden-script seat: the full-game analogue
    of a pack's ``expect`` lane — pack steps are scripted ACTIONS, so the
    script ALWAYS takes the first offered non-refuse candidate and never
    passes when an action exists (deterministic, no RNG);
  * per matchup: win/draw/loss (engine win-condition: ``Game.over_reason``
    losers = life<=0 | LOSE_GAME | CR 121.3 draw-from-empty; draws split
    STALL / turn-cap / other; crashes separate), avg turns, asks answered
    (``ask_log``) vs auto-resolved (``journal`` minus ``ask_log``, T5-F1
    forced-autopick), illegal-action attempts (engine re-validates every
    answer, C15: must be 0 — a nonzero IS the finding), engine/model
    exceptions, and the vocab[0] laziness rate per side vs TEACHER's.

Run::

    .venv/bin/python tools/eval/gameplay_eval.py --games 40
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from MTG_bot.core.executor.games import (
    TURN_CAP,
    RandomPolicy,
    Supply,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)
from tools.training.ab_duel import (
    BcAsk,
    classify_outcome,
    seat_swaps,
    snapshot_obs,
    wilson,
)
from tools.training.collector import AskContext, RandomAsk

DEFAULT_POLICY = REPO / "tools" / "training" / "bc7_S3_s1_best.pt"
DEFAULT_OUT = Path(__file__).resolve().parent / "gameplay_eval_v1.json"

#: Tokens that MEAN "decline the offer" on the ask vocabulary (PASS on the
#: may/trigger surface, skip on fire/skip sites). Everything else offered
#: is an ACTION word, a choice value (top/bottom, colours, names).
REFUSE_TOKENS = frozenset({"PASS", "pass", "skip", "SKIP", "dont", "no"})


class TeacherAsk:
    """The golden-script seat (TEACHER). A pack's scripted lane is nothing
    but actions (``steps`` carry no pass), so the script takes the FIRST
    non-refuse candidate whenever one is offered, and only declines when
    the surface carries no action. Deterministic — fully inspectable, and
    its vocab[0] rate is the natural ceiling anchor for the policy's
    laziness comparison."""

    def decide(self, ctx: AskContext) -> int:
        for i, cand in enumerate(ctx.candidates):
            if cand not in REFUSE_TOKENS:
                return i
        return 0


def make_eval_policy(spec: str, seat_seed: int, device: str) -> Any:
    """Fresh per-seat policy instance: floors by name, checkpoints by path."""
    if spec == "random":
        return RandomAsk(seed=seat_seed)
    if spec == "teacher":
        return TeacherAsk()
    return BcAsk.fresh(spec, device)


def run_eval_game(
    seed: int,
    swap: bool,
    spec_a: str,
    spec_b: str,
    supply: Supply,
    deck_pairs_seed: int = 1409,
    turn_cap: int = TURN_CAP,
    device: str = "auto",
) -> dict[str, Any]:
    """One seeded game, policy = spec_a in seat (1 if swap else 0), exactly
    mirroring ``ab_duel.run_duel_game``'s provider installation, with the
    per-ask instrumentation added."""
    decks = deal_decks(seed, deck_pairs_seed, supply)
    game = _setup_game(seed, supply, decks)
    world = game.world
    seats = [str(s) for s in world.player_order]
    a_seat = 1 if swap else 0
    specs = {a_seat: spec_a, 1 - a_seat: spec_b}
    policies = {
        seat: make_eval_policy(specs[seat], seed * 2 + seat, device) for seat in (0, 1)
    }
    # per-seat instrumentation; survives the crash path because the record
    # is assembled in this scope.
    stats = {
        seat: {"asks": 0, "v0": 0, "passes": 0, "illegal": 0, "model_errors": 0}
        for seat in (0, 1)
    }

    def provider(vocab: tuple[str, ...], what: str) -> str:
        seat = seats.index(str(world.active_player))
        st = stats[seat]
        ctx = AskContext(
            vocab=what,
            candidates=tuple(vocab),
            world=snapshot_obs(world, world.active_player),
        )
        try:
            idx = policies[seat].decide(ctx)
        except Exception:
            st["model_errors"] += 1
            raise
        if not 0 <= idx < len(vocab):
            # engine gate: out-of-vocabulary answers must NEVER pass —
            # counted loudly, then raised exactly like ab_duel does.
            st["illegal"] += 1
            raise ValueError(f"gameplay_eval: policy index {idx} out of {vocab}")
        st["asks"] += 1
        if idx == 0:
            st["v0"] += 1
        if vocab[idx] in REFUSE_TOKENS:
            st["passes"] += 1
        return vocab[idx]

    driver = RandomPolicy(seed)  # act-side driver: plays the query surface
    driver.answer = provider  # type: ignore[method-assign]
    crash = ""
    try:
        _play(game, driver, list(world.player_order), turn_cap)
        reason = game.reason
    except BaseException as error:  # noqa: BLE001 - recorded, never hidden
        reason = f"crash:{type(error).__name__}: {error}"
        crash = type(error).__name__

    stream = game.executor.decisions
    journal_total, asked_total = len(stream.journal), len(stream.ask_log)
    losers = [
        s for s, h in zip(seats, world.player_order, strict=True) if game.is_loser(h)
    ]
    winner = (
        next((s for s in seats if s not in losers), None) if len(losers) == 1 else None
    )
    return {
        "seed": seed,
        "swap": swap,
        "outcome": classify_outcome(reason, winner, seats, a_seat),
        "reason": reason,
        "turns": game.turns,
        "crash": crash or None,
        "illegal": sum(s["illegal"] for s in stats.values()),
        "journal_total": journal_total,
        "ask_log_total": asked_total,
        "auto_resolved": journal_total - asked_total,
        "seat_stats": {
            str(seat): {
                **stats[seat],
                "trunc": getattr(policies[seat], "truncations", 0),
            }
            for seat in (0, 1)
        },
    }


# --------------------------------------------------------------- batch mode
_G: dict[str, Any] = {}


def _init_worker(pool_mode: str, policy: str, device: str) -> None:
    # spawn children (fork + torch OpenMP deadlocks: verified 2026-10-08);
    # each worker compiles its supply once and caches the checkpoint.
    import torch

    torch.set_num_threads(1)
    _G["supply"] = get_supply(pool_mode)
    if policy.endswith(".pt"):
        BcAsk.fresh(policy, device)


def _worker(job: dict[str, Any]) -> dict[str, Any]:
    return run_eval_game(
        job["seed"],
        job["swap"],
        job["spec_a"],
        job["spec_b"],
        supply=_G["supply"],
        deck_pairs_seed=job["deck_pairs_seed"],
        turn_cap=job["turn_cap"],
        device=job["device"],
    )


def _side_view(records: list[dict], side: str) -> dict[str, Any]:
    """Aggregate one side's (policy or baseline) seat-instrumented asks."""
    agg: dict[str, float] = {
        "asks": 0,
        "v0": 0,
        "passes": 0,
        "illegal": 0,
        "model_errors": 0,
        "trunc": 0,
    }
    for r in records:
        for seat in ("0", "1"):
            if (r["swap"] and seat == "1") or (not r["swap"] and seat == "0"):
                owner = "policy"
            else:
                owner = "baseline"
            key = "a" if owner == "policy" else "b"
            if key != side:
                continue
            for k in agg:
                agg[k] += r["seat_stats"][seat][k]
    n = agg["asks"]
    agg["v0_rate"] = round(agg["v0"] / n, 4) if n else 0.0
    agg["pass_rate"] = round(agg["passes"] / n, 4) if n else 0.0
    return agg


def summarize_matchup(
    records: list[dict[str, Any]], spec_a: str, spec_b: str
) -> dict[str, Any]:
    n = len(records)
    wins = sum(1 for r in records if r["outcome"] == "a")
    losses = sum(1 for r in records if r["outcome"] == "b")
    draws = {
        kind.split("-", 1)[1]: sum(1 for r in records if r["outcome"] == kind)
        for kind in ("draw-stall", "draw-cap", "draw-other")
    }
    crashes = sum(1 for r in records if r["outcome"] == "crash")
    decisive = wins + losses
    played = [r for r in records if r["outcome"] != "crash"]
    lo, hi = wilson(wins, decisive) if decisive else (0.0, 1.0)
    return {
        "games": n,
        "policy": spec_a,
        "baseline": spec_b,
        "policy_wins": wins,
        "policy_losses": losses,
        "draws": draws,
        "crashes": crashes,
        "decisive_rate": round(decisive / n, 4) if n else 0.0,
        "winrate_decisive": round(wins / decisive, 4) if decisive else 0.0,
        "wilson_decisive": [round(lo, 4), round(hi, 4)],
        "avg_turns_played": round(sum(r["turns"] for r in played) / len(played), 2)
        if played
        else 0.0,
        "illegal_action_attempts": sum(r["illegal"] for r in records),
        "engine_exceptions": crashes,
        "exception_types": sorted(
            {r["crash"] for r in records if r["crash"]},
        ),
        "model_errors": sum(
            s["model_errors"] for r in records for s in r["seat_stats"].values()
        ),
        "asks_presented": sum(r["journal_total"] for r in records),
        "asks_answered": sum(r["ask_log_total"] for r in records),
        "asks_auto_resolved": sum(r["auto_resolved"] for r in records),
        "seat_swap_games": sum(1 for r in records if r["swap"]),
        "policy_asks": _side_view(records, "a"),
        "baseline_asks": _side_view(records, "b"),
    }


def _print_table(out: dict[str, Any]) -> None:
    head = (
        f"{'matchup':<26}{'G':>4}{'W':>4}{'D':>4}{'L':>4}{'X':>3}"
        f"{'wr':>7}{'ci95 (decisive)':>18}{'turns':>7}"
        f"{'ask/pol':>9}{'v0pol':>7}{'v0base':>8}{'ill':>5}{'auto%':>7}"
    )
    print(head)
    print("-" * len(head))
    for name, m in out["matchups"].items():
        draws = sum(m["draws"].values())
        auto_pct = (
            100.0 * m["asks_auto_resolved"] / m["asks_presented"]
            if m["asks_presented"]
            else 0.0
        )
        ci = f"[{m['wilson_decisive'][0]:.3f},{m['wilson_decisive'][1]:.3f}]"
        print(
            f"{name:<26}{m['games']:>4}{m['policy_wins']:>4}{draws:>4}"
            f"{m['policy_losses']:>4}{m['crashes']:>3}"
            f"{m['winrate_decisive']:>7.3f}{ci:>18}"
            f"{m['avg_turns_played']:>7.1f}{m['policy_asks']['asks']:>9}"
            f"{m['policy_asks']['v0_rate']:>7.3f}{m['baseline_asks']['v0_rate']:>8.3f}"
            f"{m['illegal_action_attempts']:>5}{auto_pct:>6.1f}%"
        )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Full-game BC vs scripted baselines.")
    ap.add_argument("--policy", default=str(DEFAULT_POLICY))
    ap.add_argument("--baselines", default="random,teacher")
    ap.add_argument(
        "--games", type=int, default=40, help="games PER matchup (seat-swapped)"
    )
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--pool", default="engine", choices=("all", "engine", "castable"))
    ap.add_argument("--deck-pairs-seed", type=int, default=1409)
    ap.add_argument("--turn-cap", type=int, default=TURN_CAP)
    ap.add_argument(
        "--seed-base",
        type=int,
        default=0,
        help="games use seeds seed_base+1..+N (deterministic)",
    )
    ap.add_argument("--device", default="auto", choices=("auto", "cpu", "cuda"))
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    policy = str(Path(args.policy).resolve())
    baselines = [b.strip() for b in args.baselines.split(",") if b.strip()]
    seeds = list(range(args.seed_base + 1, args.seed_base + 1 + args.games))
    swaps = seat_swaps(args.games)

    # parent compiles the supply only for the pool card-count meta;
    # workers warm their own (spawn context, see _init_worker).
    supply = get_supply(args.pool)
    if args.device in ("auto", "cuda"):
        import torch

        dev = "cuda" if args.device == "cuda" and torch.cuda.is_available() else "cpu"
    else:
        dev = "cpu"

    jobs = [
        {
            "seed": s,
            "swap": sw,
            "spec_a": policy,
            "spec_b": base,
            "deck_pairs_seed": args.deck_pairs_seed,
            "turn_cap": args.turn_cap,
            "device": dev,
        }
        for base in baselines
        for s, sw in zip(seeds, swaps, strict=True)
    ]
    started = time.perf_counter()
    if args.workers <= 1:
        _init_worker(args.pool, policy, dev)
        records = [_worker(j) for j in jobs]
    else:
        ctx = multiprocessing.get_context("spawn")
        with ctx.Pool(
            args.workers, initializer=_init_worker, initargs=(args.pool, policy, dev)
        ) as pool:
            records = pool.map(_worker, jobs, chunksize=1)
    elapsed = time.perf_counter() - started

    matchups: dict[str, Any] = {}
    for i, base in enumerate(baselines):
        recs = sorted(
            records[i * args.games : (i + 1) * args.games], key=lambda r: r["seed"]
        )
        matchups[f"vs_{base}"] = summarize_matchup(recs, Path(policy).name, base)
    out: dict[str, Any] = {
        "meta": {
            "date": time.strftime("%Y-%m-%d %H:%M"),
            "policy": policy,
            "pool_mode": args.pool,
            "pool_cards": len(supply.metas),
            "turn_cap": args.turn_cap,
            "games_per_matchup": args.games,
            "seeds": [seeds[0], seeds[-1]] if seeds else [],
            "deck_pairs_seed": args.deck_pairs_seed,
            "device": dev,
            "workers": args.workers,
            "seconds": round(elapsed, 1),
            "pack_denominator": (
                "0/386 scenario packs support 2-seat full games (all are "
                "steps/expect puzzle rigs); games = seeded deck-pair games "
                "of the games.py campaign rig, round-robin seeds"
            ),
            "provider_lane_caveat": (
                "policy answers engine ask-sites only; the act side (cast/"
                "attack choices) is the shared seeded RandomPolicy driver, "
                "identical for both seats and matchups (paired design)"
            ),
        },
        "matchups": matchups,
        "records": {
            f"vs_{base}": records[i * args.games : (i + 1) * args.games]
            for i, base in enumerate(baselines)
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    _print_table(out)
    print(
        f"\npolicy={Path(policy).name} pool={args.pool} "
        f"games={args.games}/matchup {elapsed:.0f}s -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
