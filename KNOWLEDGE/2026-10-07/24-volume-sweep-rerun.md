# 24 — Sweep rerun on 153-line corpus: volume erased the capacity penalty (2026-10-07 01:38)

Command: run_full_memory -- batch5_sweep.sh (fresh best.pt after archive-set fix; cause
complete 469.69; fresh bc5_S*_report.json + batch5_curve.json, old set in archive_batch5/).

| arm | params | params/line | acc (50 items) | margin | gate | old gate (75 lines) |
|---|---|---|---|---|---|---|
| S0 | 0.17M | 1,660 | 0.68 | +4.22 | PASS | PASS |
| S1 | 0.63M | 6,118 | 0.70 | +4.51 | PASS | PASS |
| S2 | 1.77M | 17,196 | 0.68 | +4.22 | PASS | PASS |
| S3 | 5.30M | 51,478 | 0.68 | +4.22 | **PASS** | FAIL |
| S4 | 35.1M | 341,131 | 0.70 | +4.51 | **PASS** | FAIL |

1. **The overfit penalty of big models vanished** with corpus 75->153: S3/S4 went FAIL->PASS,
   now within 1 item (1/50 resolution) of the small arms. Crossover moved BEYOND 35M at this
   volume — /21's "do not write off big models" confirmed, and the params/line danger zone
   shifted from ~24-71k to >340k. Absolute margins also improved (+3.21 -> +4.22/+4.51).
   Arms differ by <=1 item => no ranking possible inside the plateau at this resolution.
2. **Persistent core**: 10 items failed by EVERY arm; 9 are the ORIGINAL blind spots (all but
   Meteorite/Read the Tides/Waker of Waves fixed) + new eval family Havoc Jester #1. The 9
   survivors are exactly where the ask-kind grammar law bites: their train-side mechanic twins
   fire NO certifiable ask (cw: shocks, modal resolves, cultivate picks, single-candidate), so
   NO amount of twin scripting can teach them — the ceiling is now the engine's decision
   observability, not data volume or model size.
3. Twin scorecard: 3/12 blind spots fixed by the /23 volume batch; 7 twin attempts were
   honestly item-less (dropped); the rest remain hard for all sizes.
4. Ops: first launch crashed 4.4s (archive-set law, PITFALLS); trainer's config-mismatch guard
   refused the stale best.pt instead of clobbering — guard earned keep.
5. Decision point for owner (validation-campaign level): extend the ask grammar in the engine
   (may/target asks for cw windows, modal modes, search picks) to make those 9 mechanics
   trainable, vs honestly reclassify those eval items. C15 froze the engine for training;
   this is observability, but it is an engine change -> owner ruling required.
