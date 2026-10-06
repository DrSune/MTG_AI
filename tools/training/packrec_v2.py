"""Pack-episode recorder v2: v1 gold lines + grounded observation.

Batch 2 (KNOWLEDGE doc 10's fix list). Replays the SAME packs on the SAME
gold lines through the batch-1 chain — ``import tools.training.packrec``
installs the recording hook over puzzle_cert's lane, and this module adds
one OUTWARD layer that (a) swaps in the v2 observation snapshot (library
top-6 / graveyard / exile rows appended, bc_data_v2 §1) and (b) attaches
a ``ground`` field: per-candidate referent card rows (handles via
``world.cards``, ``choose`` indices via the digest stash — bc_data_v2
requires ``install_choose_stash()``, a PURE memo on
``query.verb_choose_options``).

INVARIANTS (unit-pinned in test_bc_v2.py):
* gold ordinals / candidates / answers are BYTE-IDENTICAL to v1 — only
  obs keys and the additive ``ground`` field differ;
* the engine never observes the memo (the wrapper returns the original
  object untouched);
* no engine edit: the hooks ride the same choke points batch 1 used.

Run::

    .venv/bin/python -m tools.training.packrec_v2 \
        --out tools/training/episodes_v2.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Importing packrec installs its take_decision chain (over puzzle_cert's);
# we then rebind the module-global snapshot fn (the hook resolves it by
# GLOBAL name at call time) and wrap the hook one layer outward.
import tools.training.packrec as packrec  # noqa: E402
from MTG_bot.core.executor.games import get_supply  # noqa: E402
from MTG_bot.core.executor.quantity import ExecCtx  # noqa: E402
from MTG_bot.core.state import (  # noqa: E402
    ZONE_EXILE,
    ZONE_GRAVEYARD,
    ZONE_LIBRARY,
)
from tools.training import bc_data_v2  # noqa: E402

bc_data_v2.install_choose_stash()

#: batch-1 snapshot kept as the untouched prefix of the v2 snapshot
_V1_OBS = packrec._obs_snapshot


def _obs_v2(ctx: ExecCtx) -> dict[str, Any]:
    """v1 snapshot, then per-seat library (top-first, real draw order),
    graveyard and exile rows appended. Degrades like v1: a failing lane
    annotates ``obs_error`` and never derails the gold line."""
    obs = _V1_OBS(ctx)
    world = getattr(ctx, "world", None)
    if world is None or "obs_error" in obs:
        return obs
    try:
        order = list(world.player_order)

        def card_row(handle: Any) -> list[str]:
            state = world.cards[handle]
            row = [str(handle), str(state.identity.name)]
            if state.tapped:
                row.append("tapped")
            for k, v in sorted(state.counters.items()):
                row.append(f"{k}={v}")
            return row

        def capped(handles: Any, cap: int, newest_first: bool) -> list[list[str]]:
            seq = list(handles)
            if newest_first:
                seq.reverse()  # entries APPEND: the tail IS the top / newest
            return [card_row(h) for h in seq[:cap]]

        libs, gys, exls = [], [], []
        for h in order:
            zones = world.players[h].zones
            lib = zones.get(ZONE_LIBRARY)
            gy = zones.get(ZONE_GRAVEYARD)
            ex = zones.get(ZONE_EXILE)
            libs.append(capped(lib.entries, bc_data_v2.LIB_CAP, True) if lib else [])
            gys.append(capped(gy.entries, bc_data_v2.GY_CAP, True) if gy else [])
            exls.append(capped(ex.entries, bc_data_v2.EXILE_CAP, True) if ex else [])
        obs["library"] = libs
        obs["graveyard_rows"] = gys
        obs["exile"] = exls
    except Exception as exc:  # noqa: BLE001 - degrade, never derail the replay
        obs["obs_error"] = f"{type(exc).__name__}: {exc}"
    return obs


packrec._obs_snapshot = _obs_v2  # type: ignore[attr-defined]

#: batch-1 outer hook (now snapshots v2 obs through the rebound name)
_REC = packrec._take_recorded


def _take_recorded_v2(self: ExecCtx, vocab: tuple, what: str) -> str:
    """v1 hook, then attach ``ground`` to the row it just mirrored. The
    digest stash was filled during the ask's own pool enumeration (before
    take_decision), so post-hoc recovery is exact."""
    answer = _REC(self, vocab, what)
    rec = packrec._records
    if rec is not None:
        row = rec[-1]
        row["ground"] = bc_data_v2.ground_candidates(
            getattr(self, "world", None), what, row["candidates"]
        )
    return answer


if ExecCtx.take_decision is not _take_recorded_v2:
    ExecCtx.take_decision = _take_recorded_v2  # type: ignore[method-assign]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--dir", default=str(REPO / "tools" / "scenarios"))
    ap.add_argument(
        "--out", default=str(REPO / "tools" / "training" / "episodes_v2.jsonl")
    )
    args = ap.parse_args(argv)
    supply = get_supply("all")
    episodes = packrec.record_dir(Path(args.dir), supply)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for ep in episodes:
            fh.write(json.dumps(ep, sort_keys=True) + "\n")
    asks = sum(len(ep["asks"]) for ep in episodes)
    gold = sum(sum(1 for r in ep["asks"] if r["gold"]) for ep in episodes)
    grounded = sum(
        1
        for ep in episodes
        for r in ep["asks"]
        if r["gold"] and any(r.get("ground", ()))
    )
    gold_cands = sum(
        len(r["candidates"]) for ep in episodes for r in ep["asks"] if r["gold"]
    )
    gnd_cands = sum(
        1
        for ep in episodes
        for r in ep["asks"]
        if r["gold"]
        for g in r.get("ground", ())
        if g
    )
    print(
        f"episodes={len(episodes)} asks={asks} gold_lines={gold} "
        f"gold_rows_with_ground={grounded} candidate_ground={gnd_cands}/{gold_cands} -> {out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
