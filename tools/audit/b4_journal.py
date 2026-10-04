"""BUGCATCH B4a journal-evidence collector (design §B evidence lanes).

Two lanes, both mirrored from existing tools WITHOUT changing their
behaviour:

* pack lane   — every green pack in ``tools/scenarios/`` re-run in-process
  through :class:`run_scenarios.ScenarioRunner` (imported, never modified).
  A pack's journal counts as evidence ONLY while the pack is green
  (``check()`` empty) — a lane that cannot fail is not evidence (the
  Fabled-Passage law), so failing packs are skipped, not mined.
* corpus lane  — the in-process ``--replay`` lane already built in
  :func:`detectors.replay_game` (``_setup_game`` + ``_play`` +
  ``journal.dump()``), one :class:`Game` per seed.

Each :class:`Game` carries the row list plus a ``handle tag -> card name``
map so a matcher can attribute rows to a card: packs map their declared
``"real"`` cards' handles; replays use the engine's own identity names.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "tools", REPO / "tools" / "audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import detectors as D
from branch_coverage import Game
from run_scenarios import PackError, ScenarioRunner

PACKS_DIR = REPO / "tools" / "scenarios"


def _rows_from_dump(dump: tuple[tuple[object, ...], ...]) -> list[D.Row]:
    """journal.dump() tuples -> detectors.Row shape (same as replay_game)."""
    return [
        D.Row(
            i,
            int(str(r[0])),
            str(r[1]),
            str(r[2]),
            str(r[3]),
            str(r[4]),
            D._parse_data(r[5]),
        )
        for i, r in enumerate(dump)
    ]


def pack_games(
    supply: object, packs_dir: Path = PACKS_DIR
) -> tuple[list[Game], list[str]]:
    """Run every pack; keep the journals of the GREEN ones.

    The step loop mirrors ``run_scenarios.run_pack`` verbatim (including the
    C5 ``expect_raise`` negative lanes) because that function discards its
    runner; only the journal collection is added.
    """
    games: list[Game] = []
    failed: list[str] = []
    for path in sorted(packs_dir.glob("*.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        try:
            runner = ScenarioRunner(pack, supply)
        except PackError as e:
            failed.append(f"{path.name}: setup PackError: {e}")
            continue
        except Exception as e:  # noqa: BLE001 - mirror run_pack robustness lane
            failed.append(f"{path.name}: setup {type(e).__name__}")
            continue
        broken = False
        for step in pack.get("steps", []):
            want = step.get("expect_raise")
            try:
                runner.run_step(step)
            except Exception as e:  # noqa: BLE001 - mirror run_pack
                if want is None or want not in f"{type(e).__name__}: {e}":
                    broken = True
                    break
                continue
            if want is not None:
                broken = True
                break
        if broken or runner.check():
            failed.append(path.name)
            continue
        handle_names = {
            str(runner.handles[c["key"]]): str(c["real"])
            for c in pack.get("cards", [])
            if "real" in c and c.get("key") in runner.handles
        }
        games.append(
            Game(
                f"pack:{path.name}",
                _rows_from_dump(runner.ex.journal.dump()),
                handle_names,
            )
        )
    return games, failed


def corpus_games(
    seeds: int, pool: str, deck_pairs_seed: int, turns: int, quiet: bool = False
) -> list[Game]:
    """The detectors.replay_game lane, one Game per seed."""
    games: list[Game] = []
    for seed in range(seeds):
        t0 = time.perf_counter()
        g = D.replay_game(seed, pool, deck_pairs_seed, turns)
        if not quiet:
            print(
                f"corpus seed {seed}: {len(g.rows)} rows "
                f"[{time.perf_counter() - t0:.1f}s]"
                + (f" CRASH {g.crashed}" if g.crashed else ""),
                flush=True,
            )
        games.append(Game(f"corpus:{seed}", g.rows, dict(g.identity_name)))
    return games


def collect(
    seeds: int = 20,
    pool: str = "all",
    deck_pairs_seed: int = 1409,
    turns: int = 60,
    packs_dir: Path = PACKS_DIR,
    quiet: bool = False,
) -> tuple[list[Game], list[str]]:
    """Both lanes: (green-pack games + corpus games, non-green pack names)."""
    from MTG_bot.core.executor.games import get_supply

    supply = get_supply(pool)
    pack_lane, failed = pack_games(supply, packs_dir)
    if not quiet:
        print(
            f"pack lane: {len(pack_lane)} green journals "
            f"({len(failed)} not-green skipped)",
            flush=True,
        )
    return pack_lane + corpus_games(seeds, pool, deck_pairs_seed, turns, quiet), failed


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="BUGCATCH B4a journal collector")
    ap.add_argument("--seeds", type=int, default=20)
    ap.add_argument("--pool", default="all")
    ap.add_argument("--deck-pairs-seed", type=int, default=1409)
    ap.add_argument("--turns", type=int, default=60)
    args = ap.parse_args(argv)
    games, failed = collect(args.seeds, args.pool, args.deck_pairs_seed, args.turns)
    n_rows = sum(len(g.rows) for g in games)
    tags: set[str] = set()
    for g in games:
        tags.update(r.verb for r in g.rows)
    print(f"games={len(games)} rows={n_rows} not_green={len(failed)}")
    print("observed cause_verb tags:", ", ".join(sorted(tags)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
