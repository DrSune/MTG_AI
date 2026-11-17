"""N1's claim, checked on a live network: the component pool as a count matrix times the embedding
table computes what ``PolicyValueNet.card_table_emb`` computes, row for row, on r28's v2 (CPU, fp32,
read-only). Then the same matrix built from the current, untruncated compile: the rows that change
are exactly the ones past max_ir.

    .venv/bin/python reports/component_review_2026-11-17/pool_check.py <checkpoint> > reports/component_review_2026-11-17/pool_check.txt
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
import common as C
import torch

from tools.selfplay import model as M


def counts_matrix(rows: list[list[int]], n_vocab: int) -> torch.Tensor:
    m = torch.zeros(len(rows), n_vocab)
    for i, ids in enumerate(rows):
        for t in ids:
            if t > 0:
                m[i, t] += 1.0
    return m


def main(path: str) -> None:
    torch.set_num_threads(2)
    net, table, _ = M.load(path, "cpu")
    with torch.no_grad():
        ref = net.card_table_emb()
        emb = net.ir_emb.weight
        m = counts_matrix(table.ir, emb.shape[0])
        pooled = (m @ emb) / m.sum(1, keepdim=True).clamp(min=1.0)
        diff = (pooled - ref).abs().max().item()
        print(f"# {Path(path).name}: {ref.shape[0]} rows, d {ref.shape[1]}")
        print(f"count-matrix pool against card_table_emb, the saved (truncated) rows: max |diff| {diff:.2e} "
              f"(fp32 summation order only)")
        # the untruncated current compile of the same cards, through the table's vocabulary
        rows = C.load()
        current = {}
        for r in rows:
            if "tokens" in r:
                current.setdefault(r["oid"], r)
        full_rows, n_long, n_same_short, n_changed_short = [], 0, 0, 0
        for oid, ids in zip(table.oracle_ids, table.ir):
            r = current.get(oid)
            if r is None:
                full_rows.append(ids)
                continue
            toks = r["tokens"]
            full = [table.ir_index.get(t, 0) for t in toks]
            full_rows.append(full)
            if len(toks) > table.max_ir:
                n_long += 1
            elif full == ids:
                n_same_short += 1
            else:
                n_changed_short += 1
        m2 = counts_matrix(full_rows, emb.shape[0])
        pooled2 = (m2 @ emb) / m2.sum(1, keepdim=True).clamp(min=1.0)
        moved = ((pooled2 - ref).abs().max(1).values > 1e-5).sum().item()
        print(f"rows past max_ir in the current compile: {n_long}; rows within it, unchanged since the save: "
              f"{n_same_short}, recompiled since (a --refresh-table changes them anyway): {n_changed_short}")
        print(f"rows whose pooled vector moves once nothing is cut: {moved} "
              f"(= the long rows plus the recompiled ones)")


if __name__ == "__main__":
    main(sys.argv[1])
