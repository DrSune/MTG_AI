#!/usr/bin/env python3
"""R16-2 trace-diff catalog (doc 2026-09-30/11 §R16-2 — BINDING).

The owner's compounding-risk answer for shared-verb changes: every game in
the pinned baseline batch (10 engine seeds, deck-pairs 1409, cap 60 — the
same games as ``--seeds 10 --pool engine``) is replayed here and its
executor EVENT JOURNAL is pinned entry-by-entry. Journal rows are already
canonical dumps (12b ``dump()``: clock, kind, subject, cause, cause_verb,
data), so one sha256 per row fingerprints the full atomic-semantics
sequence. A shared-verb change (damage, SBA, FIGHT, combat…) MUST ship with
a ``compare`` run whose every divergence is located (first-divergence entry
+ surrounding cards/handles/actions), explained, and re-pinned with a
reason in the knowledge note — the reconciliation IS the proof.

The replay mirrors ``games.play_game`` exactly (same supply, decks, policy,
turn loop, no trace recorder), so the journals are byte-identical to the
CLI's games. A crashed game pins the journal as-of-death (the state it
died in is still deterministic).

Subcommands:
    build   --out tools/traces/catalog.json   (pin the CURRENT semantics)
    compare                                 (diff current vs pinned; exit 1 on divergence)
    repin   (rebuild in place — ONLY after the divergences were reconciled)

Options: --pool --seeds --deck-pairs-seed --turns --seed (single seed).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from MTG_bot.core.executor.games import (  # noqa: E402 - repo bootstrap above
    RandomPolicy,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)

CATALOG = REPO / "tools" / "traces" / "catalog.json"
SCHEMA = 1


def _entry(row: tuple[object, ...]) -> list[str]:
    """One journalled row -> [hash16, label]. The hash covers the FULL row
    (repr — the canonical dump form); the label (kind|subject|cause|verb)
    is the human locator for diffs — it names the cards/handles/actions."""
    h = hashlib.sha256(repr(row).encode()).hexdigest()[:16]
    _clock, kind, subject, cause, cause_verb, _data = row
    label = f"{kind}|{subject}|{cause}|{cause_verb}"
    return [h, label]


def run_seed(
    seed: int, pool: str, deck_pairs_seed: int, turn_cap: int, supply: Any
) -> dict[str, Any]:
    """One game, mirroring play_game's crash-tolerant path; returns the
    pinned entry stream + outcome meta for the seed."""
    decks = deal_decks(seed, deck_pairs_seed, supply)
    game = _setup_game(seed, supply, decks)
    policy = RandomPolicy(seed)
    crash = None
    try:
        _play(game, policy, game.world.player_order, turn_cap)
    except BaseException as error:  # noqa: BLE001 - pinned, not swallowed
        crash = f"{type(error).__name__}: {error}"
    rows = game.executor.journal.dump()
    return {
        "turns": game.turns,
        "survived": game.turns >= turn_cap and crash is None,
        "reason": crash if crash is not None else game.reason,
        "crash": crash,
        "fingerprint": game.executor.state_fingerprint(),
        "n": len(rows),
        "entries": [_entry(row) for row in rows],
    }


def build(pool: str, n_seeds: int, deck_pairs_seed: int, turn_cap: int) -> dict:
    supply = get_supply(pool)
    games = {}
    for seed in range(n_seeds):
        t0 = time.perf_counter()
        games[str(seed)] = run_seed(seed, pool, deck_pairs_seed, turn_cap, supply)
        print(
            f"seed {seed}: {games[str(seed)]['n']} journal entries, "
            f"{games[str(seed)]['turns']} turns, "
            f"{'crash: ' + str(games[str(seed)]['crash'])[:90] if games[str(seed)]['crash'] else games[str(seed)]['reason'][:60]}"
            f"  [{time.perf_counter() - t0:.1f}s]"
        )
    return {
        "schema": SCHEMA,
        "built": datetime.now(UTC).isoformat(timespec="seconds"),
        "pool": pool,
        "deck_pairs_seed": deck_pairs_seed,
        "turn_cap": turn_cap,
        "semantics_note": "journal fingerprints at build time — see the "
        "knowledge note dated with 'built' for the pinned semantics",
        "games": games,
    }


def first_divergence(old: list, new: list) -> int | None:
    for i, (o, n) in enumerate(zip(old, new, strict=False)):
        if o[0] != n[0]:
            return i
    if len(old) != len(new):
        return min(len(old), len(new))
    return None


def show_context(old: list, new: list, idx: int, window: int = 4) -> list[str]:
    lines = []
    lo = max(0, idx - window)
    for i in range(lo, min(max(len(old), len(new)), idx + window + 1)):
        o = old[i] if i < len(old) else None
        n = new[i] if i < len(new) else None
        mark = "SAME" if o is not None and n is not None and o[0] == n[0] else "DIFF"
        lines.append(
            f"    {mark} [{i}] old={o[1] if o else '-'} {o[0][:8] if o else ''}"
            f" | new={n[1] if n else '-'} {n[0][:8] if n else ''}"
        )
    return lines


def compare(
    catalog: dict, pool: str, deck_pairs_seed: int, turn_cap: int, only: int | None
) -> int:
    supply = get_supply(catalog["pool"])
    diverged = 0
    for seed_str, pin in sorted(catalog["games"].items(), key=lambda kv: int(kv[0])):
        seed = int(seed_str)
        if only is not None and seed != only:
            continue
        fresh = run_seed(seed, catalog["pool"], deck_pairs_seed, turn_cap, supply)
        idx = first_divergence(pin["entries"], fresh["entries"])
        if idx is None:
            print(f"seed {seed}: IDENTICAL ({fresh['n']} entries)")
            continue
        diverged += 1
        print(f"seed {seed}: FIRST DIVERGENCE at entry {idx} of {pin['n']}")
        for line in show_context(pin["entries"], fresh["entries"], idx):
            print(line)
        print(f"    old outcome: {pin['reason'][:80]} (n={pin['n']})")
        print(f"    new outcome: {fresh['reason'][:80]} (n={fresh['n']})")
    print(
        f"\ncatalog vs current: {diverged} diverging seed(s) "
        f"of {len(catalog['games']) if only is None else 1}"
    )
    return 1 if diverged else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="R16-2 trace-diff catalog: build/compare/repin journal fingerprints"
    )
    ap.add_argument("mode", choices=("build", "compare", "repin"))
    ap.add_argument("--pool", default="engine")
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--deck-pairs-seed", type=int, default=1409)
    ap.add_argument("--turns", type=int, default=60)
    ap.add_argument("--catalog", default=str(CATALOG))
    ap.add_argument("--seed", type=int, default=None, help="compare one seed")
    args = ap.parse_args(argv)

    if args.mode in ("build", "repin"):
        payload = build(args.pool, args.seeds, args.deck_pairs_seed, args.turns)
        out = Path(args.catalog)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload), encoding="utf-8")
        total = sum(g["n"] for g in payload["games"].values())
        print(
            f"{args.mode}: {len(payload['games'])} games, {total} entries, "
            f"{out} ({out.stat().st_size / 1e6:.1f} MB)"
        )
        return 0
    catalog = json.loads(Path(args.catalog).read_text(encoding="utf-8"))
    return compare(catalog, args.pool, args.deck_pairs_seed, args.turns, args.seed)


if __name__ == "__main__":
    raise SystemExit(main())
