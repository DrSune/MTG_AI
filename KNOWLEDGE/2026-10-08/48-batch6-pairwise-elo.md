# 48 — Batch-6 pairwise honest winrate + CIs (S4/S3/S0, 2400 games)

Command: `.venv/bin/python tools/training/elo_batch6_run.py --games-per-pair 200 --workers 6 --device cuda`
Result file: `tools/training/elo_batch6.json` (2026-10-08).

## Headline (pooled 3 same-seed matchups, 600 games/pair, Wilson 95% CI; swap-paired duels, draws=0.5)
| pair | big winrate | 95% CI | verdict (law §26: admissible iff CI excludes 0.5) |
|---|---|---|---|
| S3 (d256,L6) vs S0 (d64,L2) | **0.554** | [0.514, 0.594] | **ADMISSIBLE: bigger is better** |
| S4 (d512,L8) vs S0 | 0.492 | [0.453, 0.532] | INADMISSIBLE (flat) |
| S4 vs S3 | 0.489 | [0.450, 0.530] | INADMISSIBLE (flat) |

Cross-seed pooled check (opponents seed-cycled, 200g each, cluster bootstrap): S3_S0 0.540 [0.47,0.61];
S4_S0 0.458 [0.39,0.525]; S4_S3 0.463 [0.395,0.53] — consistent direction, underpowered alone.

## Reading
- Capacity pays from d64→d256 (S3>S0, CI excludes 0.5, all 3 per-seed matchups point same way:
  0.552/0.555/0.555). From d256→d512 (S4) it does NOT: S4 is indistinguishable from both S0 and S3.
- Consistent with S4 train-info: eval-accuracy collapsed (~0.76→0.48 mid-run, plateau ~0.60) while
  train loss kept falling → S4 overfit/diverged at this data volume; scale needs more data
  (Protocol A capacity×volume grid — big-model arm is data-starved, not capacity-capped).
- Under-20-set pool (~122-episode eval corpus) supports ONE admissible size claim: mid-size wins.
- Method note: seed=cluster bootstrap over paired swap-games; per-seed CIs all straddled 0.5 at
  n=200 — pooling same-seed matchups (independent seed banks) is what resolves the S3>S0 effect.

## Ops
- GPU (CUDA, shared with vllm engine, workers=6) ~1.5s/game vs CPU ~8s/game; CPU-only was 5x slower
  and unnecessary — `ab_duel.run_duel(device="cuda")` works, models are tiny (174MB).
- Runner: `tools/training/elo_batch6_run.py` (physical file required — multiprocessing spawn breaks
  under heredoc/stdin execution; isolated seed bank /tmp/opencode/duel_seeds_batch6.json).
