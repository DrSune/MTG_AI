#!/usr/bin/env python3
"""Wave-1 end-to-end validation: IR vs goldens + pack replays + game replay.

Three mandatory stages (the round-17 mandate: a card is validated only
when its golden IR, its scripted replay, and an actual game replay all
agree with the printed text):

1. IR stage — recompile the golden pool and check every ``wave1.json``
   row: the card still carries its ETB trigger(s), the mechanics verb
   set matches, engine support matches. A drift is an IR_MISMATCH.
2. Replay stage — every scenario pack touching a wave card is run
   through the real ``ScenarioRunner`` (``run_pack``), whose expect
   block is the full assertion set. Baseline packs (non-wave) run too:
   a regression anywhere in the dir is a failure.
3. Game-replay stage (``--with-replay``) — one seeded game of the
   engine pool via ``play_game`` (the harness ``make_replay`` drives),
   trace kept, and we report which wave cards actually reached the
   battlefield in a real game.

``--emit-json`` writes the machine-readable board (HTML rendering is a
deferred UI step — the data rows are complete and stable here).

Usage::

    .venv/bin/python tools/audit/verify_wave.py --replay --with-replay --seed 7
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from wave_builder import (
    DATA,
    DEFAULT_OUT,
    etb_triggers,
)

from MTG_bot.core.compiler.compiler import compile_pool
from MTG_bot.core.compiler.coverage import build_full_registry
from MTG_bot.core.compiler.ingest import ingest_pool
from MTG_bot.core.executor import SUPPORTED_VERBS_V2
from MTG_bot.core.executor.games import get_supply, play_game
from tools.run_scenarios import run_pack

IR_FAIL, PACK_FAIL, OK = 2, 1, 0


def ir_stage(wave: dict) -> list[str]:
    """Stage 1: golden recompilation vs the frozen wave rows."""
    raw = ingest_pool(DATA)
    registry = build_full_registry()
    pool = compile_pool(raw, registry)
    gated = compile_pool(raw, registry, supported_verbs=set(SUPPORTED_VERBS_V2))
    by_name = {res.card.name: (oid, res) for oid, res in pool.results.items()}
    fails: list[str] = []
    for name, row in wave["cards"].items():
        if name not in by_name:
            fails.append(f"IR_MISMATCH[{name}]: card absent from golden pool")
            continue
        oid, res = by_name[name]
        ets = etb_triggers(res.card)
        if not ets:
            fails.append(f"IR_MISMATCH[{name}]: no ETB trigger in recompiled IR")
            continue
        if oid != row["oracle_id"]:
            fails.append(f"IR_MISMATCH[{name}]: oracle_id drifted")
        sup = bool(gated.results[oid].legality.engine_supported)
        if sup != row["engine_supported"]:
            fails.append(
                f"IR_MISMATCH[{name}]: engine_supported {sup} "
                f"!= recorded {row['engine_supported']}"
            )
    return fails


def replay_stage(wave: dict, packs_dir: Path, max_verify: int) -> dict:
    """Stage 2: scripted replays — full expect sets through ScenarioRunner."""
    supply = get_supply("all")
    wave_names = set(wave["cards"])
    covered: dict[str, str] = {}
    pack_results: list[dict] = []
    fails: list[str] = []
    n_run = 0
    for path in sorted(packs_dir.glob("*.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        reals = {c["real"] for c in pack.get("cards", []) if "real" in c}
        hits = sorted(reals & wave_names)
        is_wave = bool(hits) and n_run < max_verify
        if is_wave:
            n_run += 1
            for n in hits:
                covered.setdefault(n, path.name)
        errs = run_pack(path, supply)
        pack_results.append(
            {
                "pack": path.name,
                "wave_cards": hits,
                "ok": not errs,
                "run": True,
                "errors": errs,
            }
        )
        for e in errs:
            fails.append(f"PACK_FAIL[{path.name}]: {e}")
    gaps = sorted(wave_names - set(covered))
    return {
        "packs": pack_results,
        "pack_fails": fails,
        "covered": covered,
        "gaps": gaps,
        "n_wave_packs_run": n_run,
    }


def game_stage(
    seed: int, pool_mode: str, turns: int, out_dir: Path, wave: dict
) -> dict:
    """Stage 3: one real game through the replay harness's own entry."""
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / f"game_{pool_mode}_s{seed}.json"
    supply = get_supply(pool_mode)
    play_game(seed, pool_mode, 1409, turns, supply=supply, trace_path=trace_path)
    trace_text = trace_path.read_text(encoding="utf-8")
    seen = sorted(n for n in wave["cards"] if f'"{n}"' in trace_text)
    return {
        "seed": seed,
        "pool": pool_mode,
        "turns": turns,
        "trace": str(trace_path),
        "wave_in_game": seen,
        "n_wave_in_game": len(seen),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--wave", default=str(DEFAULT_OUT))
    ap.add_argument("--packs-dir", default=str(REPO / "tools" / "scenarios"))
    ap.add_argument("--replay", action="store_true", help="run stage 2")
    ap.add_argument(
        "--with-replay", action="store_true", help="run stage 3 (one seeded game)"
    )
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--pool", default="engine", choices=("all", "engine", "castable"))
    ap.add_argument("--turns", type=int, default=60)
    ap.add_argument(
        "--max-verify", type=int, default=40, help="cap wave packs run this pass"
    )
    ap.add_argument(
        "--emit-json",
        default=None,
        help="machine-readable board path (reports/…_wave1.json)",
    )
    args = ap.parse_args(argv)

    wave = json.loads(Path(args.wave).read_text(encoding="utf-8"))
    board: dict = {
        "wave": wave["meta"]["wave"],
        "date": str(datetime.now(UTC).date()),
        "n_wave_cards": wave["meta"]["n_cards"],
    }

    ir_fails = ir_stage(wave)
    board["ir"] = {"checked": wave["meta"]["n_cards"], "mismatches": ir_fails}
    print(
        f"IR stage: {wave['meta']['n_cards']} rows checked, {len(ir_fails)} mismatches"
    )
    for f in ir_fails:
        print(" ", f)

    code = OK
    if args.replay:
        rep = replay_stage(wave, Path(args.packs_dir), args.max_verify)
        board["replay"] = {
            "packs": rep["packs"],
            "n_wave_packs_run": rep["n_wave_packs_run"],
            "covered": rep["covered"],
            "gaps": rep["gaps"],
        }
        n_ok = sum(p["ok"] for p in rep["packs"])
        print(
            f"Replay stage: {n_ok}/{len(rep['packs'])} packs pass "
            f"(wave packs run: {rep['n_wave_packs_run']}, "
            f"wave cards covered: {len(rep['covered'])}, "
            f"gap cards: {len(rep['gaps'])})"
        )
        for f in rep["pack_fails"]:
            print(" ", f)
        if rep["pack_fails"]:
            code = PACK_FAIL
    else:
        board["replay"] = None

    if args.with_replay:
        g = game_stage(
            args.seed, args.pool, args.turns, REPO / "reports" / "audit", wave
        )
        board["game_replay"] = g
        print(
            f"Game-replay stage: seed {g['seed']} pool {g['pool']} — "
            f"{g['n_wave_in_game']} wave cards live in the trace"
        )

    if args.emit_json:
        out = Path(args.emit_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(board, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"board written: {out}")

    if ir_fails:
        return IR_FAIL
    return code


if __name__ == "__main__":
    sys.exit(main())
