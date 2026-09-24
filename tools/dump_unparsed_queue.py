"""Dump the compiler's ACTUAL unparsed queue — the true Phase-1 residual.

Unlike the static ``UNCOVERED`` tuples in the template modules (bookkeeping
that goes stale when compiler built-ins consume shapes — e.g. choose-openers,
search-shuffle), this reads the compiler's own unparsed fragments via
``coverage.measure_pool`` and groups them by normalized shape
(digit-run → "N") with occurrence counts and the card names per shape,
sorted by occurrence count descending. This is the work register for the
next template batch or grammar round.

Usage:
    python tools/dump_unparsed_queue.py [--set M21] [--card NAME] [--out FILE]

With ``--out`` the report is written to FILE and nothing is printed to
stdout. With ``--card`` only unparsed entries for cards whose name
contains the substring are listed (per-card triage).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from MTG_bot.core.compiler.coverage import (
    build_full_registry,
    measure_pool,
)
from MTG_bot.core.compiler.ingest import ingest_pool


def norm(s: str) -> str:
    """Shape key: every digit-run becomes 'N' (bucket-classifier convention)."""
    return re.sub(r"\d+", "N", s)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", default="M21", help="set name (default M21)")
    ap.add_argument("--card", default=None, help="substring card-name filter")
    ap.add_argument(
        "--out", default=None, help="write report to FILE instead of stdout"
    )
    args = ap.parse_args()

    pool = ingest_pool(REPO / "MTG_bot" / "data" / f"{args.set}.json")
    report = measure_pool(pool, build_full_registry(), args.set)

    lines = [
        (
            f"PC-1 card_coverage = {report.pc1_card_coverage:.4f} "
            f"({report.cards_zero_unparsed}/{report.entry_count})"
        ),
        (
            f"PC-2 sentence_coverage = {report.pc2_sentence_coverage:.4f} "
            f"({report.sentences_matched}/{report.sentence_total})"
        ),
        f"unparsed entries = {report.unparsed_count}",
    ]

    by_shape: dict[str, list] = defaultdict(list)
    for e in report.unparsed_queue:
        if args.card and args.card.lower() not in e.name.lower():
            continue
        by_shape[norm(e.sentence)].append(e)

    lines.append(f"\nUNPARSED shapes = {len(by_shape)}")
    for shape, entries in sorted(by_shape.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        lines.append(f"\n[{len(entries):2d}] {shape}")
        seen: set[str] = set()
        for e in entries:
            if e.name in seen:
                continue
            seen.add(e.name)
            lines.append(f"    - {e.name} (hint={e.bucket_hint}) :: {e.sentence[:100]}")

    text = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).write_text(text)
        print(f"report written to {args.out}")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
