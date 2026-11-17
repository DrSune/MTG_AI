"""The card table a live network reads: r28's v2 (runs/r28_looks/r28_v2.pt), loaded read-only on the
CPU, against the current compile of the cards it holds.

    .venv/bin/python reports/component_review_2026-11-17/checkpoint_table.py <checkpoint> > reports/component_review_2026-11-17/checkpoint_table.txt

Its rows and component vocabulary; how many rows sit at max_ir; the rows whose current compile
differs (stale rows a --refresh-table rebuilds); the vocabulary rows no current card uses; the
norm of each component embedding by how many rows use it (does a rarely used token stay near
its initialisation?).
"""
from __future__ import annotations

import statistics as stats
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import common as C
import torch

from tools.selfplay import features as FT


def main(path: str) -> None:
    ck = torch.load(path, map_location="cpu", weights_only=False)
    table = FT.CardTable.from_json(ck["table"])
    emb = ck["state"]["ir_emb.weight"].float()
    print(f"# The card table of {Path(path).name}")
    print(f"rows {len(table.oracle_ids)} (2 are pad/unknown); component vocabulary {len(table.ir_vocab)}; "
          f"max_ir {table.max_ir}; ir_emb {tuple(emb.shape)}; config {ck['config']}")
    lens = [len(r) for r in table.ir[2:]]
    print(f"tokens per row: mean {stats.mean(lens):.1f}, median {stats.median(lens)}, max {max(lens)}; "
          f"rows at max_ir (truncated): {sum(1 for n in lens if n >= table.max_ir)}")
    rows = C.load()
    current = {}
    for r in rows:
        if "tokens" in r:
            current.setdefault(r["oid"], r)
    stale = trunc_stale = 0
    for oid, ids in zip(table.oracle_ids[2:], table.ir[2:]):
        r = current.get(oid)
        if r is None:
            continue
        toks = [table.ir_vocab[i] for i in ids]
        if toks != r["tokens"][: table.max_ir]:
            stale += 1
    print(f"rows whose current compile differs from the saved row: {stale} of {len(table.ir) - 2}")
    used = Counter()
    for ids in table.ir[2:]:
        used.update(set(ids))
    unused = [t for i, t in enumerate(table.ir_vocab) if i and not used[i]]
    print(f"vocabulary rows no table row uses: {len(unused)}")
    # embedding norm against how many rows carry the token
    buckets = ((1, 1), (2, 2), (3, 5), (6, 20), (21, 100), (101, 10**9))
    norms = emb.norm(dim=1)
    init = 0.02 * (emb.shape[1] ** 0.5)
    print(f"component embedding norms (an untrained N(0, 0.02) row has norm about {init:.2f}; a row "
          f"added at zero by extend_cards has 0):")
    for lo, hi in buckets:
        sel = [norms[i].item() for i in range(1, len(table.ir_vocab)) if lo <= used[i] <= hi]
        if sel:
            label = f"{lo}" if lo == hi else (f"{lo}-{hi}" if hi < 10**9 else f"{lo}+")
            print(f"  tokens on {label:>7} rows: {len(sel):4d} tokens, norm median {stats.median(sel):.3f}, "
                  f"mean {stats.mean(sel):.3f}")
    zero = [table.ir_vocab[i] for i in range(1, len(table.ir_vocab)) if norms[i].item() == 0.0]
    print(f"rows still exactly zero (added after the start, never trained): {len(zero)}: {', '.join(zero[:30])}")


if __name__ == "__main__":
    main(sys.argv[1])
