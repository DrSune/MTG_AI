"""ZNR engine-robustness smoke fuzz (2026-10-19 wave; --set since the M21 era run).

Random-policy fuzz over a set's ``engine`` pool (``--set ZNR`` default,
``--set M21`` for the frozen era): N seeded games through the
EXISTING harness (:func:`play_game`, which already owns RandomPolicy, the
deck-draw interface :func:`deal_decks`, and per-game crash capture), plus:

* EVERY exception per game is turned into a ledger row (play_game catches
  BaseException; we additionally guard around play_game itself and around the
  per-game wall-clock alarm).
* full traceback: crashed games are replayed once with ``raise_on_crash`` (the
  engine is deterministic, so the rerun crash IS the crash) to capture the
  whole stack, not just the top frame.
* ledger JSON grouped by exception signature, each group carrying a MINIMAL
  REPRO command that reruns exactly one seed (the harness's own --repro string
  is WRONG for ZNR — games.py main has no --set flag and would rerun M21 — so
  this tool's own repro mode is the repro surface).
* a BackFace reach probe: monkeypatch-counted ``walk`` in every MTG_bot module
  namespace, flagging any walk that DESCENDS a BackFace subtree without
  skip=BackFace (the /106 phantom class), plus a shallow executor-registry
  scan for registered BackFace nodes / face-inner abilities at game end.

This tool REPORTS crashes, it never fixes the engine. Exit code is always 0
unless the tool itself is broken; a crash ledger full of signatures is a
SUCCESS result.

Usage:
    python tools/eval/znr_engine_smoke.py --games 40 --workers 4
    python tools/eval/znr_engine_smoke.py --set M21 --games 500
    python tools/eval/znr_engine_smoke.py --repro SEED [--set S]  # full traceback
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import signal
import statistics
import sys
import time
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

POOL_MODE = "engine"
SET_CODE = "ZNR"
DEFAULT_DECK_PAIRS_SEED = 201019  # separate stream from the game seed, per wave spec
DEFAULT_TURN_CAP = 150
DEFAULT_GAME_TIMEOUT = 45.0  # wall-clock seconds per game (setitimer alarm)


# ------------------------------------------------------------------ repro


def report_prefix(set_code: str) -> str:
    """Ledger filename stem: ``znr_engine_smoke`` / ``m21_engine_smoke``.
    Schema identical across sets; only the stem names the era."""
    return f"{set_code.lower()}_engine_smoke"


def repro_command(
    seed: int,
    deck_pairs_seed: int,
    turn_cap: int,
    set_code: str = SET_CODE,
) -> str:
    """One command, one process, the crash with its FULL traceback.

    Deliberately NOT games.py's own ``--repro``: that path hardcodes SET_CODE
    (M21) and would rerun the wrong pool."""
    return (
        f"python tools/eval/znr_engine_smoke.py --repro {seed} --set {set_code} "
        f"--deck-pairs-seed {deck_pairs_seed} --turn-cap {turn_cap}"
    )


def run_repro(
    seed: int,
    deck_pairs_seed: int,
    turn_cap: int,
    set_code: str = SET_CODE,
) -> int:
    from MTG_bot.core.executor.games import deal_decks, get_supply, play_game

    supply = get_supply(POOL_MODE, set_code)
    decks = deal_decks(seed, deck_pairs_seed, supply)
    names_a = [supply.metas[oid].name for oid in decks[0]]
    names_b = [supply.metas[oid].name for oid in decks[1]]
    print(f"seed {seed} deck A: {names_a}")
    print(f"seed {seed} deck B: {names_b}")
    try:
        outcome = play_game(
            seed,
            POOL_MODE,
            deck_pairs_seed,
            turn_cap,
            supply=supply,
            raise_on_crash=True,
        )
    except BaseException:  # noqa: BLE001 — catch-everything by contract
        traceback.print_exc()
        return 1
    print(
        f"seed {seed}: no crash — {outcome.turns} turns, "
        f"{outcome.acts} acts, {outcome.reason or 'no loser'}"
    )
    return 0


# ------------------------------------------------------- ledger grouping


def crash_signature(crash: dict[str, Any]) -> str:
    return f"{crash.get('exc', '?')}@{crash.get('frame', '?')}"


def group_crashes(
    rows: list[dict[str, Any]],
    *,
    deck_pairs_seed: int,
    turn_cap: int,
    set_code: str = SET_CODE,
) -> dict[str, dict[str, Any]]:
    """Collapse per-game crash rows into one row per root-cause signature.

    Pure function (unit-tested in test_znr_engine_smoke.py): ``rows`` are the
    per-game dicts produced by :func:`play_one`; rows without a ``crash`` are
    ignored. A group is keyed by ``ExcName@file:line`` and carries the count,
    the hitting seeds, the first-seen evidence (message, turn, acts-as-step,
    attempted card, stack, recent acts, full traceback if captured) and the
    MINIMAL REPRO command — the single smallest seed of the group, so the
    reader reruns one game, not fifty.
    """
    groups: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda r: int(r["seed"])):
        crash = row.get("crash")
        if not crash:
            continue
        key = crash_signature(crash)
        group = groups.get(key)
        if group is None:
            groups[key] = {
                "exc": crash.get("exc", "?"),
                "message": str(crash.get("message", ""))[:220],
                "frame": crash.get("frame", "?"),
                "count": 1,
                "seeds": [int(row["seed"])],
                "turn": crash.get("turn", row.get("turns")),
                "step": row.get("acts"),  # acts completed = step index (no finer trace)
                "attempted": crash.get("attempted", ""),
                "stack": crash.get("stack", []),
                "recent_acts": crash.get("recent_acts", []),
                "traceback": row.get("traceback", ""),
                "repro": repro_command(
                    int(row["seed"]), deck_pairs_seed, turn_cap, set_code
                ),
            }
        else:
            group["count"] += 1
            group["seeds"].append(int(row["seed"]))
    return groups


# ------------------------------------------------------------ one game


_SUPPLY: Any = None
_SUPPLY_SET: str = ""


def _warm_supply(set_code: str = SET_CODE) -> None:
    global _SUPPLY, _SUPPLY_SET
    if _SUPPLY is None or _SUPPLY_SET != set_code:
        from MTG_bot.core.executor.games import get_supply

        _SUPPLY = get_supply(POOL_MODE, set_code)
        _SUPPLY_SET = set_code


class _GameAlarm(Exception):
    """Per-game wall-clock cap fired inside the game."""


def _alarm(signum: int, frame: Any) -> None:
    raise _GameAlarm("wall-clock cap exceeded")


def play_one(
    seed: int,
    deck_pairs_seed: int,
    turn_cap: int,
    game_timeout: float,
    set_code: str = SET_CODE,
) -> dict[str, Any]:
    """One fuzz game -> one compact ledger row. NEVER raises.

    The harness's play_game already catches BaseException around the turn
    loop; the guard here additionally catches a raise OUTSIDE that loop
    (setup, deck build, coverage walk) and the setitimer alarm. A timeout
    that play_game's own handler caught shows up as crash exc
    ``_GameAlarm`` — a per-game wall-clock cap, kept as its own signature."""
    _warm_supply(set_code)
    from MTG_bot.core.executor.games import deal_decks, play_game

    row: dict[str, Any] = {
        "seed": seed,
        "turns": 0,
        "acts": 0,
        "survived": False,
        "reason": "",
        "deck": "",
        "crash": None,
        "traceback": "",
        "seconds": 0.0,
    }
    started = time.monotonic()
    try:
        decks = deal_decks(seed, deck_pairs_seed, _SUPPLY)
        row["deck"] = (
            f"{sum(1 for o in decks[0] if _SUPPLY.metas[o].is_land)}L/"
            f"{sum(1 for o in decks[1] if _SUPPLY.metas[o].is_land)}L"
        )
    except BaseException as error:  # noqa: BLE001 — the tool MUST catch every exception
        row["crash"] = {
            "exc": type(error).__name__,
            "message": str(error)[:220],
            "frame": f"deal_decks:{seed}",
            "turn": 0,
        }
        row["traceback"] = traceback.format_exc()
        return row
    old_handler = signal.signal(signal.SIGALRM, _alarm)
    signal.setitimer(signal.ITIMER_REAL, game_timeout)
    try:
        outcome = play_game(seed, POOL_MODE, deck_pairs_seed, turn_cap, supply=_SUPPLY)
    except BaseException as error:  # noqa: BLE001 — the tool MUST catch every exception  # raise landed outside play_game's own net
        row["crash"] = {
            "exc": type(error).__name__,
            "message": str(error)[:220],
            "frame": _top_frame(error),
            "turn": None,
            "attempted": "",
            "stack": [],
            "recent_acts": [],
        }
        row["traceback"] = traceback.format_exc()
        row["reason"] = f"crash:{type(error).__name__}(outside turn loop)"
        return row
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
    row.update(
        turns=outcome.turns,
        acts=outcome.acts,
        survived=outcome.survived,
        reason=outcome.reason,
        crash=outcome.crash,
    )
    if outcome.crash is not None:
        # Deterministic engine: replay with raise to capture the FULL stack.
        try:
            play_game(
                seed,
                POOL_MODE,
                deck_pairs_seed,
                turn_cap,
                supply=_SUPPLY,
                raise_on_crash=True,
            )
        except BaseException:  # noqa: BLE001 — catch-everything by contract
            row["traceback"] = traceback.format_exc()
        else:
            row["traceback"] = "<repro rerun did not reproduce — NONDETERMINISM>"
    row["seconds"] = round(time.monotonic() - started, 2)
    return row


def _top_frame(error: BaseException) -> str:
    tb = error.__traceback__
    while tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    if tb is None:
        return "?"
    frame = traceback.extract_tb(tb)[-1]
    return f"{Path(frame.filename).name}:{frame.lineno} in {frame.name}"


# ------------------------------------------------------- BackFace probe


def backface_probe(
    seeds: list[int],
    deck_pairs_seed: int,
    turn_cap: int,
    game_timeout: float,
    set_code: str = SET_CODE,
) -> dict[str, Any]:
    """/106 phantom defense at runtime: no back-face subtree reaches a verdict,
    a battlefield permanent's registry rows, or the executor registries.

    Mechanism (read-only monkeypatch, probe process only):
    1. wrap ``walk`` in every loaded MTG_bot module namespace. ``skip=BackFace``
       YIELDS the face node but never descends (documented semantics), so a
       violation is a walk that YIELDS a BackFace WITHOUT skip covering it —
       that walk descended the face and leaked face-inner abilities to an
       engine consumer. We intersect the yielded stream with the face's own
       subtree to name exactly what leaked, and record the calling frame.
    2. at game end, shallow-scan the executor's and binder's attribute
       containers for registered BackFace instances or face-inner ability
       instances (the registry half of "battlefield/register" reach).

    A faceless era (M21) still runs the probe: zero carriers is a result."""
    _warm_supply(set_code)
    from MTG_bot.core.ability_tree import BackFace
    from MTG_bot.core.executor.games import (
        RandomPolicy,
        _play,
        _setup_game,
        deal_decks,
    )

    # identity set of every face-inner Ability object in the pool (kept alive
    # by the supply compile cache, so id() is stable)
    inner_ids: dict[int, str] = {}
    for result in _SUPPLY.pool.results.values():
        for node in result.card.abilities:
            if isinstance(node, BackFace):
                inner_ids[id(node)] = f"BackFace<{node.face_name}>"
                for ab in node.abilities:
                    inner_ids[id(ab)] = f"{type(ab).__name__} in {node.face_name}"

    probe = {"walk_calls": 0, "face_yields_skipped_ok": 0, "violations": []}

    def make_wrapper(original: Any, module_name: str) -> Any:
        def wrapped(node: Any, *, skip: Any = ()) -> Any:
            probe["walk_calls"] += 1
            out = list(original(node, skip=skip))
            faces = [n for n in out if isinstance(n, BackFace)]
            if faces:
                covers = isinstance(skip, type) and issubclass(BackFace, skip)
                covers = covers or (
                    isinstance(skip, tuple)
                    and any(
                        isinstance(s, type) and issubclass(BackFace, s) for s in skip
                    )
                )
                if covers:
                    probe["face_yields_skipped_ok"] += 1
                else:
                    leaked = [n for n in out[1:] if id(n) in inner_ids]
                    tb = traceback.extract_stack()
                    caller = next(
                        (
                            f"{Path(f.filename).name}:{f.lineno} in {f.name}"
                            for f in reversed(tb[:-1])
                            if "MTG_bot" in f.filename
                            and "znr_engine_smoke" not in f.filename
                        ),
                        "?",
                    )
                    probe["violations"].append(
                        {
                            "caller": caller,
                            "face": getattr(faces[0], "face_name", "?"),
                            "leaked": sorted({inner_ids[id(n)] for n in leaked})[:8],
                        }
                    )
            return iter(out)

        return wrapped

    patched: list[str] = []
    originals: dict[str, Any] = {}
    for name, module in list(sys.modules.items()):
        if not name.startswith("MTG_bot") or module is None:
            continue
        original = getattr(module, "walk", None)
        if callable(original) and not hasattr(original, "_bf_probe"):
            originals[name] = original
            wrapper = make_wrapper(original, name)
            wrapper._bf_probe = True  # type: ignore[attr-defined]
            module.walk = wrapper
            patched.append(name)

    games: list[dict[str, Any]] = []
    try:
        for seed in seeds:
            record: dict[str, Any] = {"seed": seed, "outcome": "", "registry_hits": []}
            try:
                decks = deal_decks(seed, deck_pairs_seed, _SUPPLY)
                game = _setup_game(seed, _SUPPLY, decks)
                policy = RandomPolicy(seed)
                old = signal.signal(signal.SIGALRM, _alarm)
                signal.setitimer(signal.ITIMER_REAL, game_timeout)
                try:
                    _play(game, policy, game.world.player_order, turn_cap)
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                    signal.signal(signal.SIGALRM, old)
                record["outcome"] = f"ok: {game.reason or 'no loser'}"
            except BaseException as error:  # noqa: BLE001 — probe games may crash; probe still scores
                record["outcome"] = f"crashed: {type(error).__name__}"
            # registry half: shallow scan of executor + binder attribute
            # containers for registered faces / face-inner abilities.
            try:
                holders = {"executor": game.executor}
                binder = getattr(game.executor, "binder", None)
                if binder is not None:
                    holders["binder"] = binder
                for holder_name, holder in holders.items():
                    for attr, value in vars(holder).items():
                        for item in _flatten(value):
                            if id(item) in inner_ids:
                                record["registry_hits"].append(
                                    f"{holder_name}.{attr}: {inner_ids[id(item)]}"
                                )
                # battlefield half: a BACK FACE must never BE a battlefield
                # card; a two-faced permanent's own record may legitimately
                # CARRY a BackFace node (that is the /106 encoding). Count both
                # for the record.
                bf_on_battlefield = 0
                for handle in game.world.cards:
                    if game.world.zone_of(handle).kind != "battlefield":
                        continue
                    card = game.world.cards[handle]
                    rec = game.executor.binder.records.get(card.identity.oracle_id)
                    if rec is not None and any(
                        isinstance(n, BackFace) for n in rec.abilities
                    ):
                        bf_on_battlefield += 1
                record["battlefield_cards_carrying_BackFace"] = bf_on_battlefield
            except BaseException:  # noqa: BLE001 — catch-everything by contract
                record["audit_error"] = traceback.format_exc(limit=3)
            games.append(record)
    finally:
        for name, original in originals.items():
            sys.modules[name].walk = original

    probe["games_probed"] = len(games)
    probe["patched_modules"] = patched
    probe["games"] = games
    probe["registry_hits"] = sum(len(g["registry_hits"]) for g in games)
    probe["unique_violations"] = {
        f"{v['caller']}|{v['face']}": v for v in probe["violations"]
    }
    probe["verdict"] = (
        "PASS" if not probe["violations"] and not probe["registry_hits"] else "FAIL"
    )
    return probe


def _flatten(value: Any, _depth: int = 0) -> Any:
    """Yield the value and, for containers, their items (depth<=2 — the
    registry rows live one container deep at most; deep walk of engine state
    would be an engine walk, not a probe)."""
    yield value
    if _depth >= 2:
        return
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _flatten(item, _depth + 1)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _flatten(item, _depth + 1)


# ------------------------------------------------------------ the batch


def run_batch(
    games: int,
    workers: int,
    turn_cap: int,
    deck_pairs_seed: int,
    game_timeout: float,
    probe_games: int,
    deadline_seconds: float,
    set_code: str = SET_CODE,
) -> dict[str, Any]:
    workers = max(1, min(4, workers))
    started = time.monotonic()
    rows: list[dict[str, Any]] = []
    timed_out_seeds: list[int] = []
    if workers == 1:
        _warm_supply(set_code)
        for seed in range(games):
            if time.monotonic() - started > deadline_seconds:
                timed_out_seeds.extend(range(seed, games))
                break
            rows.append(
                play_one(seed, deck_pairs_seed, turn_cap, game_timeout, set_code)
            )
    else:
        with cf.ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    play_one, seed, deck_pairs_seed, turn_cap, game_timeout, set_code
                ): seed
                for seed in range(games)
            }
            remaining = deadline_seconds
            try:
                for future in cf.as_completed(futures, timeout=remaining):
                    seed = futures[future]
                    try:
                        rows.append(future.result())
                    except BaseException as error:  # noqa: BLE001 — the tool MUST catch every exception  # worker death, cancelled
                        rows.append(
                            {
                                "seed": seed,
                                "turns": 0,
                                "acts": 0,
                                "survived": False,
                                "reason": "worker-failure",
                                "deck": "",
                                "crash": {
                                    "exc": type(error).__name__,
                                    "message": str(error)[:220],
                                    "frame": "worker",
                                    "turn": None,
                                },
                                "traceback": "",
                                "seconds": 0.0,
                            }
                        )
            except TimeoutError:
                # overall deadline: the unfinished games are LEDGERED as
                # not-run, never silently dropped.
                timed_out_seeds = sorted(futures[f] for f in futures if not f.done())
                for seed in timed_out_seeds:
                    rows.append(
                        {
                            "seed": seed,
                            "turns": 0,
                            "acts": 0,
                            "survived": False,
                            "reason": "not-run-at-deadline",
                            "deck": "",
                            "crash": None,
                            "traceback": "",
                            "seconds": 0.0,
                        }
                    )
    rows.sort(key=lambda r: int(r["seed"]))
    groups = group_crashes(
        rows, deck_pairs_seed=deck_pairs_seed, turn_cap=turn_cap, set_code=set_code
    )
    completed = [r for r in rows if r["reason"] != "not-run-at-deadline"]
    crashed = [r for r in completed if r["crash"]]
    acts = [int(r["acts"]) for r in completed]
    summary = {
        "set_code": set_code,
        "pool_mode": POOL_MODE,
        "games_requested": games,
        "games_completed": len(completed),
        "games_crashed": len(crashed),
        "crash_rate": round(len(crashed) / max(len(completed), 1), 3),
        "distinct_signatures": len(groups),
        "turn_cap": turn_cap,
        "deck_pairs_seed": deck_pairs_seed,
        "game_timeout_s": game_timeout,
        "workers": workers,
        "wall_clock_s": round(time.monotonic() - started, 1),
        "acts_median": statistics.median(acts) if acts else 0,
        "turns_median": statistics.median([int(r["turns"]) for r in completed] or [0]),
        "timed_out_seeds": timed_out_seeds,
    }
    result = {
        "summary": summary,
        "signatures": groups,
        "rows": [{k: v for k, v in r.items() if k != "traceback"} for r in completed],
        "full_tracebacks": {
            str(r["seed"]): r["traceback"] for r in crashed if r.get("traceback")
        },
    }
    if probe_games:
        result["backface_probe"] = backface_probe(
            list(range(probe_games)),
            deck_pairs_seed,
            turn_cap,
            game_timeout,
            set_code,
        )
    return result


# ------------------------------------------------------------------ main


def write_markdown(result: dict[str, Any], path: Path) -> None:
    s = result["summary"]
    lines = [
        f"# {s['set_code']} engine smoke fuzz — {time.strftime('%Y-%m-%d')}",
        "",
        (
            f"- games completed: **{s['games_completed']}** / {s['games_requested']}"
            f" (workers={s['workers']}, wall {s['wall_clock_s']}s, cap {s['game_timeout_s']}s/game)"
        ),
        f"- turn cap {s['turn_cap']}, deck-pairs seed {s['deck_pairs_seed']}",
        f"- crashed: **{s['games_crashed']}** (crash rate **{s['crash_rate']:.1%})",
        f"- distinct signatures: **{s['distinct_signatures']}**",
        (
            f"- exploration depth: median {s['acts_median']} acts, "
            f"{s['turns_median']} turns per game"
        ),
        "",
    ]
    probe = result.get("backface_probe")
    if probe:
        lines += [
            "## BackFace reach probe",
            "",
            (
                f"- verdict: **{probe['verdict']}** over {probe['games_probed']} games "
                f"({probe['walk_calls']} intercepted walk calls, "
                f"{probe['face_yields_skipped_ok']} correctly skipped)"
            ),
            (
                f"- walk violations (face subtree descended by an engine consumer): "
                f"{len(probe['violations'])}"
            ),
            (
                f"- registry hits (face object registered on executor/binder): "
                f"{probe['registry_hits']}"
            ),
            (
                f"- battlefield permanents legitimately CARRYING a BackFace node: "
                f"{sum(g.get('battlefield_cards_carrying_BackFace', 0) for g in probe['games'])}"
            ),
            "",
        ]
    if result["signatures"]:
        lines += ["## Signatures", ""]
        for sig, g in sorted(
            result["signatures"].items(), key=lambda kv: -int(kv[1]["count"])
        ):
            lines += [
                f"### `{sig}` — {g['count']} hit(s), seeds {g['seeds'][:12]}",
                f"- message: `{g['message']}`",
                f"- step: turn {g['turn']}, {g['step']} acts completed"
                + (f", attempted: `{g['attempted']}`" if g["attempted"] else ""),
                f"- stack: {g['stack']}",
                f"- recent acts: {g['recent_acts']}",
                f"- **repro**: `{g['repro']}`",
                "",
            ]
    else:
        lines += [
            "## Signatures",
            "",
            (
                "ZERO crashes. Honest coverage note: random walks only reach "
                "legality-adjacent states — this is a robustness smoke, not a "
                "state-space proof."
            ),
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=40)
    parser.add_argument(
        "--set",
        dest="set_code",
        default=SET_CODE,
        help="card pool set code passed to get_supply('engine', SET) (default ZNR)",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--turn-cap", type=int, default=DEFAULT_TURN_CAP)
    parser.add_argument("--deck-pairs-seed", type=int, default=DEFAULT_DECK_PAIRS_SEED)
    parser.add_argument("--game-timeout", type=float, default=DEFAULT_GAME_TIMEOUT)
    parser.add_argument(
        "--probe-games",
        type=int,
        default=6,
        help="games run under the BackFace walk probe",
    )
    parser.add_argument(
        "--deadline",
        type=float,
        default=25 * 60,
        help="overall wall-clock budget in seconds",
    )
    parser.add_argument("--out", default=None, help="ledger JSON path")
    parser.add_argument("--md", default=None, help="markdown summary path")
    parser.add_argument(
        "--repro",
        type=int,
        default=None,
        help="rerun ONE seed with full traceback and exit",
    )
    parser.add_argument(
        "--recheck",
        type=int,
        default=0,
        help="after the batch, rerun this many seeds and compare rows",
    )
    args = parser.parse_args(argv)
    args.set_code = args.set_code.upper()

    if args.repro is not None:
        return run_repro(args.repro, args.deck_pairs_seed, args.turn_cap, args.set_code)

    result = run_batch(
        args.games,
        args.workers,
        args.turn_cap,
        args.deck_pairs_seed,
        args.game_timeout,
        args.probe_games,
        args.deadline,
        args.set_code,
    )

    if args.recheck:
        _warm_supply(args.set_code)
        mismatches = []
        original = {int(r["seed"]): r for r in result["rows"]}
        for seed in sorted(original)[: args.recheck]:
            again = play_one(
                seed,
                args.deck_pairs_seed,
                args.turn_cap,
                args.game_timeout,
                args.set_code,
            )
            keep = ("turns", "acts", "survived", "reason", "deck")
            if any(again[k] != original[seed][k] for k in keep) or bool(
                again["crash"]
            ) != bool(original[seed]["crash"]):
                mismatches.append(seed)
        result["determinism"] = {
            "seeds_rechecked": args.recheck,
            "mismatches": mismatches,
            "verdict": "PASS" if not mismatches else "FAIL",
        }

    stamp = time.strftime("%Y-%m-%d")
    stem = f"{report_prefix(args.set_code)}_{stamp}"
    out = Path(args.out) if args.out else ROOT / "reports" / f"{stem}.json"
    md = Path(args.md) if args.md else ROOT / "reports" / f"{stem}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    write_markdown(result, md)
    s = result["summary"]
    print(
        f"games={s['games_completed']}/{s['games_requested']} "
        f"crashed={s['games_crashed']} ({s['crash_rate']:.1%}) "
        f"signatures={s['distinct_signatures']} "
        f"wall={s['wall_clock_s']}s json={out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
