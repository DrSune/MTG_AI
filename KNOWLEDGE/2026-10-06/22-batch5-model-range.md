# 22 — Batch 5: the model-range curve vs data volume (2026-10-06, engine-off, 5.3 min)

Command: `bash tools/training/run_full_memory.sh -- bash tools/training/batch5_sweep.sh`
(ledger complete rc 0, cause complete 315.44; artifacts tools/training/bc5_S*_report.json,
batch5_curve.json). Same data (75 gold lines), seed 1, all hyperparams equal.

| arm | params | params/gold-line | eval acc | margin | gate | best_loss |
|---|---|---|---|---|---|---|
| S0 | 0.17M | 2,260 | 0.6591 | +3.21 | PASS | 0.226 |
| S1 | 0.63M | 8,361 | 0.6591 | +3.21 | PASS | 0.204 |
| S2 | 1.77M | 23,554 | 0.6591 | +3.21 | PASS | 0.209 |
| S3 | 5.30M | 70,615 | 0.6136 | +2.60 | FAIL | 0.181 |
| S4 | 35.1M | 468,323 | 0.6136 | +2.60 | FAIL | 0.184 |

## What the curve says (owner ruling /21 answered, current volume)
1. **PLATEAU then DEGRADATION**: eval margin flat from 0.17M to 1.77M, drops between 1.77M
   and 5.30M. Capacity-to-data crossover at current volume ≈ **2-5M params** (~24k-71k
   params per gold line). Below it: free scaling; above: overfit eats generalization.
2. **DATA-LIMITED plateau, proven**: S0/S1/S2 fail the **identical 12 eval items** (bit-exact
   same blind spots across 10x size range) — the ceiling IS the 75-line training corpus, not
   any architecture choice. Big arms fail 13 items with 11 overlapping (different + worse).
   best_loss falls monotonically with size (0.226→0.184): big models fit train better and
   generalize worse — classic small-n regime.
3. **REPRODUCIBILITY**: S4 == batch-3 arm A to the digit (acc 0.6136, +2.60, loss 0.18425)
   and S0 == batch-3 B exactly — cross-run determinism holds (same seed/data/config).
4. Honest resolution caveat (owner's granularity law): n=44 binary items → steps of 1/44;
   "identical" plateau = indistinguishable at this resolution, not proven equal. The 12-item
   fail-set identity is the stronger evidence.
5. cap_headroom = 16 tokens across every arm (max seq 1008 vs 1024) — /21 BPTT law live,
   no over_limit trips.

## Standing consequences
- Future BC arms: **≤ 2M params until data volume moves the crossover**; rerun the sweep
  (new output prefix bc5b_, resume-guards mean same-prefix = skip-all) after every material
  corpus growth — the crossover location IS the measurement.
- The 12 shared blind items = the exact shopping list for VOLUME work: inspect what mechanics
  they need, script gold points for those mechanics into TRAIN families (next batch).

## Ops note
Dispatch envelope died with the engine-stop again (expected; disk-check law applied: full
work found on disk, nothing lost, no double-driver — flock held). Engine-off batch wall time
5.3 min + restore ~11 min; cost of a batch-5-style rerun is now trivial.
