"""Measure 1: the vocabulary as the network sees it (``features.card_tokens``), over the verified
cards of M21, M20 and FDN (one row per oracle id) and over every compiled tree of the 19 sets.

    .venv/bin/python reports/component_review_2026-11-17/vocab.py > reports/component_review_2026-11-17/vocab.txt

Sections: sizes; tokens per card (and the cards past ``max_ir`` = 128); how many cards use each
token, as a histogram; the tokens 1-2 verified cards use, by kind, with their cards; the same
over the 19 sets; how much of a card's mean the near-universal tokens take.
"""
from __future__ import annotations

import statistics as stats
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C

MAX_IR = 128
BUCKETS = ((1, 1), (2, 2), (3, 5), (6, 10), (11, 20), (21, 50), (51, 100), (101, 500), (501, 10**9))


def hist(df: Counter) -> list[str]:
    out = []
    for lo, hi in BUCKETS:
        n = sum(1 for v in df.values() if lo <= v <= hi)
        label = f"{lo}" if lo == hi else (f"{lo}-{hi}" if hi < 10**9 else f"{lo}+")
        out.append(f"  used by {label:>8} cards: {n:5d} tokens")
    return out


def lengths(pop: list[dict]) -> list[str]:
    ls = sorted(len(r["tokens"]) for r in pop)
    over = [r for r in pop if len(r["tokens"]) > MAX_IR]
    q = lambda p: ls[min(len(ls) - 1, int(p * len(ls)))]
    out = [f"  cards {len(ls)}; tokens per card mean {stats.mean(ls):.1f}, median {q(.5)}, p90 {q(.9)}, "
           f"p99 {q(.99)}, max {ls[-1]}",
           f"  past max_ir {MAX_IR}: {len(over)} cards ({100 * len(over) / len(ls):.1f}%), "
           f"{sum(len(r['tokens']) - MAX_IR for r in over)} tokens cut"]
    return out


def section(title: str, pop: list[dict]) -> Counter:
    print(f"\n## {title}")
    df = C.doc_freq(pop)
    total = Counter(t for r in pop for t in r["tokens"])
    print(f"  vocabulary: {len(df)} distinct tokens; {sum(total.values())} token uses")
    by_kind = Counter(C.kind(t) for t in df)
    print("  by kind: " + ", ".join(f"{k} {v}" for k, v in by_kind.most_common()))
    for line in lengths(pop):
        print(line)
    print("  cards per token:")
    for line in hist(df):
        print(line)
    rare = [t for t, v in df.items() if v <= 2]
    print(f"  tokens used by 1-2 cards: {len(rare)} ({100 * len(rare) / len(df):.0f}% of the vocabulary), "
          f"{sum(total[t] for t in rare)} uses ({100 * sum(total[t] for t in rare) / sum(total.values()):.2f}% of all uses)")
    print("    by kind: " + ", ".join(f"{k} {v}" for k, v in Counter(C.kind(t) for t in rare).most_common()))
    cards_with_rare = sum(1 for r in pop if any(df[t] <= 2 for t in set(r["tokens"])))
    print(f"    cards holding at least one such token: {cards_with_rare}")
    return df


def mass(pop: list[dict], df: Counter) -> None:
    """The share of a card's mean pool taken by tokens that most cards carry."""
    n = len(pop)
    for frac in (0.5, 0.25, 0.1):
        common_tokens = {t for t, v in df.items() if v >= frac * n}
        shares = [sum(1 for t in r["tokens"][:MAX_IR] if t in common_tokens) / max(1, len(r["tokens"][:MAX_IR]))
                  for r in pop]
        print(f"  tokens on >= {int(frac * 100)}% of cards: {len(common_tokens)}; their share of a card's "
              f"(truncated) bag: mean {stats.mean(shares):.2f}, median {stats.median(shares):.2f}")
    print("  the 25 most widespread tokens (cards): " + ", ".join(f"{t} {v}" for t, v in df.most_common(25)))


def main() -> None:
    rows = C.load()
    ver = C.verified_home(rows)
    allc = C.compiled_all(rows)
    print("# The vocabulary as the network sees it (features.card_tokens, untruncated unless said)")
    print(f"populations: verified M21+M20+FDN {len(ver)} distinct cards; compiled trees of the 19 sets "
          f"{len(allc)} distinct cards (refused cards have no tree)")
    df_v = section("Verified cards of M21, M20 and FDN", ver)
    mass(ver, df_v)
    df_a = section("Every compiled tree of the 19 sets", allc)
    mass(allc, df_a)
    v_only = set(df_v)
    print(f"\n  tokens of the 19 sets not in the verified vocabulary: {len(set(df_a) - v_only)}; "
          f"cards holding one: {sum(1 for r in allc if set(r['tokens']) - v_only)} of {len(allc)}")
    print("    by kind: " + ", ".join(f"{k} {v}" for k, v in Counter(C.kind(t) for t in set(df_a) - v_only).most_common()))

    # the rare verified tokens, listed
    owners = defaultdict(list)
    for r in ver:
        for t in set(r["tokens"]):
            if df_v[t] <= 2:
                owners[t].append(f"{r['set']} {r['name']}")
    print("\n## Tokens used by 1-2 verified cards, by kind (cards; uses over the 19 sets' compiled trees)")
    by = defaultdict(list)
    for t in owners:
        by[C.kind(t)].append(t)
    for k in sorted(by, key=lambda k: -len(by[k])):
        print(f"\n### {k} ({len(by[k])})")
        for t in sorted(by[k]):
            print(f"  {t:45s} {df_v[t]}  [19 sets: {df_a.get(t, 0)}]  " + "; ".join(sorted(owners[t])))

    print("\n## Over the 19 sets: tokens used by 1-2 compiled trees, by kind")
    rare_a = [t for t, v in df_a.items() if v <= 2]
    by = defaultdict(list)
    for t in rare_a:
        by[C.kind(t)].append(t)
    for k in sorted(by, key=lambda k: -len(by[k])):
        print(f"  {k} ({len(by[k])}): " + ", ".join(sorted(by[k])[:400]))


if __name__ == "__main__":
    main()
