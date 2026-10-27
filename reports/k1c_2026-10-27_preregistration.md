# K1c reading rules, written 2026-10-27 23:33:38 CET BEFORE any K1c result was seen

Question: does a transformer over the IR token sequence (ir-seq, "structure") catch up with the bag
of IR tokens (ir-bag) when training covers 1 -> 16 real sets? At ~200 cards (K1, /165) ir-seq was
below ir-bag, read as overfitting at small data. The owner's architecture bet (atoms + learned
encodings + a relational network / transformer) needs structure to pay off at some volume.

## Setting
- K1b's run B exactly: fully compiled cards only, the same data, steps, row cap and tests. The
  compiler is K1b's, 9ee6966.
- Encoders: state, ir-bag and ir-seq. They run on the GPU (the 21:54–23:59 free slot) and all at
  batch 256, so ir-seq no longer gets K1's batch-1024 handicap. Same seed and epochs.
- Metric: median per-card skill on held-out effect cards, with paired gaps (1000 card resamples).
- Hard stop at 23:52 so the 23:59 RL window starts clean. A step that does not finish is reported
  as not run.

## Rules
1. **Device sanity (descriptive).** K1c's ir-bag median at each step, next to K1b run B's CPU value.
2. **Structure at volume.** ir-seq − ir-bag at 16 sets, paired 95% interval:
   - above 0: structure pays at this volume;
   - below 0: the bag is still better;
   - contains 0: no evidence.
3. **Trend.** Compare the per-card gap d = skill(ir-seq) − skill(ir-bag) at 16 sets with the same
   gap at 1 set: the median of d(16) minus the median of d(1), with a paired card-resampling
   interval. The gap closes with volume if the interval is above 0.
4. **M20 (16 cards).** Reported. Read only together with held-out.
