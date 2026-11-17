# Evidence for KNOWLEDGE/2026-11-17/210 §8 (N1 and N2 built)

N1: a card is the mean of every component token it has, pooled by a count matrix
(`model.card_table_emb`, `features.CardTable.ir_counts`); the 128-token cut is gone. N2: no card name
is a component token (`features.ir_tokens`: `str:~`, `str:<name>`, no back face's name). The old code
is the base commit's, 32e804ec. r28's v2 (`runs/r28_looks/r28_v2.pt`, sha256 d9f75295…) is read only,
on the CPU (a training run held the GPU).

| Script | Output | What |
|---|---|---|
| `census.py` | `census.txt` | every compiled card of the 19 sets and the 651 verified ones, tokenised by the base commit's `card_tokens` (from git) and by this one's: the cut cards, the name cards by path, no name left, the two tokenisations differing only there |
| `v2_side.py --code-root TREE --out SIDE.pkl` | a pickle (not kept) | what one code tree computes with v2: card vectors, logits and values on 1,027 decisions of 6 seeded heuristic games, 6 seeded games v2 plays greedily; v2's saved table and the table r28's and r29's flags build (refreshed) |
| `compare.py OLD.pkl NEW.pkl` | `compare.txt` | the two sides: encodings, vectors, logits, values, games; the changed rows with the size of the change under v2's weights |
| `precision_check.py NEW.pkl` | `precision_check.txt` | the pool under bf16 autocast (the trainer's) and in a bf16 copy (the learner's inference), against the old pool and against bf16's own noise |

To regenerate, from the repository root:

```
d=reports/n1n2_2026-11-17; s=SCRATCH  # any directory outside the repository
git archive 32e804ec tools | tar -x -C $s/old    # the base commit's tools/ (mkdir $s/old first)
run() { CUDA_VISIBLE_DEVICES= OMP_NUM_THREADS=2 nice -n 19 .venv/bin/python "$@"; }
run $d/census.py > $d/census.txt
run $d/v2_side.py --code-root $s/old --out $s/old.pkl
run $d/v2_side.py --code-root . --out $s/new.pkl
run $d/compare.py $s/old.pkl $s/new.pkl > $d/compare.txt
run $d/precision_check.py $s/new.pkl > $d/precision_check.txt
```
