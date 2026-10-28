"""Recover the source card of K2 rows that gen.py recorded without one (fixed in gen.py since).

    MTG_REPO=<tree> .venv/bin/python tools/k2/repair_sources.py --data DIR --out DIR/fixed

gen.py first took the source from the tag's first handle, so engine asks dropped their card. Those
tags read "<kind>:player:N:card:M:<digest>" (legality.py:1505), and the first handle is the deciding
player. That lost 945 target, 157 sacrifice and 334 discard asks. A card's handle is fixed when the
game is dealt. So rebuilding each game's setup (same set, seed and decks) maps ``card:M`` to its
oracle id without replaying anything. Cards created later in the game (tokens) are not in the setup;
those rows keep ``source: null`` and are counted.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

_GEN = importlib.util.spec_from_file_location("k2_gen", Path(__file__).resolve().parent / "gen.py")
assert _GEN is not None and _GEN.loader is not None
gen = importlib.util.module_from_spec(_GEN)
_GEN.loader.exec_module(gen)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    tally: Counter = Counter()
    for path in sorted(Path(args.data).glob("k2_*.jsonl")):
        lines = [json.loads(line) for line in path.open(encoding="utf-8")]
        setups: dict[tuple[str, int], dict] = {}
        for row in lines:
            if row.get("kind") == "manifest" or row.get("source") is not None:
                continue
            handle = gen.source_handle(row["site"])
            if handle is None:
                tally["no card in tag"] += 1
                continue
            key = (row["set"], row["seed"])
            if key not in setups:
                supply = gen.get_supply("castable", row["set"])
                game = gen._setup_game(row["seed"], supply,
                                       gen.deal_decks(row["seed"], 1409, supply))
                setups[key] = {h: c.identity.oracle_id for h, c in game.world.cards.items()}
            oid = setups[key].get(handle)
            if oid is None:
                tally["card created after setup"] += 1
                continue
            row["source"] = oid
            tally[f"recovered {row['kind']}"] += 1
        with (out_dir / path.name).open("w", encoding="utf-8") as fh:
            for row in lines:
                fh.write(json.dumps(row) + "\n")
    print(json.dumps(dict(tally), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
