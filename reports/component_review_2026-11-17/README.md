# Evidence for KNOWLEDGE/2026-11-17/210 (component sharing review)

`run_all.sh [checkpoint]` regenerates every output from the repository root (CPU only, `nice`), on
main b1d61997 in the review. `dump.py` compiles the 19 sets with card records applied
(`corpus.compile_set`, `cardtool._state`) into `.cache/component_review/dump.pkl` (gitignored), which
the other scripts read through `common.py`. The checkpoint (default r28's v2) is read only, on the CPU.

| Script | Output | Numbers (note section) |
|---|---|---|
| `dump.py` | `.cache/component_review/dump.pkl` | every card: state, tokens, per-ability tokens, tree, unparsed sentences |
| `vocab.py` | `vocab.txt` | vocabulary sizes, tokens per card, the histogram, the rare tokens by kind, the common mass (§0, §1.2) |
| `inventory.py` | `inventory.txt` | every closed-vocabulary member by cards using it, the unused ones (§3) |
| `rare_classify.py` | `rare_classify.txt` | the 208 rare verified tokens: composition, parameter, keep, values (§1.4) |
| `duplicates.py` | `duplicates.txt` | A: the ledger's classes by detector; B: slot-word variants per sentence; C: whole cards with the same text (§2) |
| `network.py` | `network.txt` | Murder/Shatter, field-key mass, exact copies, collisions, numbers, truncation, names, value twins (§4) |
| `remaining.py` | `remaining.txt` | the unverified M21/M20/FDN cards' unparsed sentences classed by need, the pieces, the cover (§5) |
| `proposals.py` | `proposals.txt` | each IR proposal's tokens, trees, stamps, remaining sentences; bundles; the slim stream (§6, §7) |
| `checkpoint_table.py <ck>` | `checkpoint_table.txt` | r28 v2's card table: rows, vocabulary, truncated rows, stale rows, norms by use (§1.3) |
| `pool_check.py <ck>` | `pool_check.txt` | N1: the count-matrix pool against `card_table_emb` on r28 v2 (§6.1) |

`remaining.py`'s classes come from a hand-written lexicon (`RULES`); its default bucket is printed
in full in `remaining.txt` for review.

After N1 and N2 were built (210 §8, `reports/n1n2_2026-11-17/`), `dump.py` writes N2's tokens
(no card names), and `checkpoint_table.py` and `pool_check.py` stop at `CardTable.max_ir`, which
is gone. To reproduce these outputs, run the scripts on a checkout of 32e804ec or earlier.
