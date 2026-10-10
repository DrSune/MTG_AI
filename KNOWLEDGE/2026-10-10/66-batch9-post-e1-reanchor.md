# 66 — batch9 re-anchor: post-E1 + act-sense corpus, 21/21 PASS — S4 breaks the plateau

Date: 2026-10-10. Command: `run_full_memory.sh -- bash tools/training/batch9_sweep.sh` (engine-off), prefix bc10_*.
Corpus: 199 gold lines (act-sense +12 packs), E1-unified encoding (episodes re-encoded), vocab 455.

| arm | params | mean acc (n=3) | spread | vs batch8 |
|---|---|---|---|---|
| S0 | 0.17M | 0.759 | 0.010 | -0.017 |
| S1 | — | 0.759 | 0.010 | — |
| S2 | — | 0.759 | 0.015 | — |
| S3 | 5.3M | 0.764 | 0.020 | +0.005 |
| S3a | 10.0M | 0.766 | 0.020 | +0.002 |
| S3b | 23.1M | 0.757 | 0.010 | +0.039 |
| **S4** | **35.0M** | **0.827** (0.784/0.859/0.839) | 0.075 | **+0.097** |

- FIRST sweep where 35M separates (+0.068 over S0; S4-S0 gap ~2.6 SE of the mean-difference — SUGGESTIVE, not yet the >3SE admissibility bar; spread 0.075 = engine-off training instability at 35M, same class as batch8-era).
- Consistent with owner position (plateau is regime-scoped, expected to RISE with complexity): richer corpus + orthogonalized encoding shifted the ceiling upward for the biggest arm. Volume/capacity confound remains at this eval size — needs harder eval items or more seeds if it must be made ADMISSIBLE.
- Gameplay v5 (bc10_S4_s3, 200 games, teacher+random, engine-ON CPU) appended on completion.
