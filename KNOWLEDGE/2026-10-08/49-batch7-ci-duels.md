# 49 — Batch-7 CI-grade pairwise duels vs S0 (capacity closure)

Command: `.venv/bin/python tools/training/elo_batch7_run.py --games-per-pair 200`
Out: `tools/training/elo_batch7.json` (schema `batch7-cluster-bootstrap-v1`).
Headline numbers are in NUMBERS.md (2026-10-08, batch-7 section).

## Design
- 4 pairs (S3a/S3/S3b/S4 vs S0) x 3 seed-matched training seeds x 200 swap-paired
  duels = 2400 games. Frozen unified 180-item corpus (eval_file binding
  episodes_v2.jsonl; runner verifies identical binding across all 20 bc7 reports
  before dueling; no corpus data regenerated).
- CI: per-seed Wilson (decisive + score); pooled = cluster bootstrap (cluster =
  game seed, 10k draws, percentile) on swap-paired scores + Wilson on pooled
  decisive. Law /26: admissible iff 95% CI excludes 0.5.

## Result (all four ADMISSIBLE, both CI methods agree)
decisive winrates: S3a 0.5426 [0.5025,0.5821] | S3 0.5442 [0.5042,0.5837] |
S3b 0.5417 [0.5017,0.5811] | S4 0.5453 [0.5052,0.5849].
Boot CIs all inside [0.5275,0.5575]. Arms INDISTINGUISHABLE from each other
(spread 0.0036 << CI width ~0.08).

## Execution provenance (why the log looks messy)
- Two runner variants raced on the same output file 15:25-16:40: a flat-Wilson
  schema and the cluster-bootstrap schema, both with resume/`[skip]` logic; each
  completed seed runs the other had not. Final file = union; 2 orphan flat-schema
  rows (S3a s1/s2) cross-verified identical to the final rows, then merged/removed.
- 12/12 seed runs seat_balance_ok, counts sum to 200; bootstrap independently
  recomputed with a fresh RNG seed — agrees to 4 decimal places.
- Checkpoint sha256(16) s1 set: S0 831693e9d7f75455, S3a 6444cfe37842b02c,
  S3 096a8882e3a74593, S3b ab478920fee54aaf, S4 e23477555d4ede52.

## Read
Capacity 9.98M->35M adds NOTHING over the baseline uplift; confirms batch6
plateau on the unified corpus and supersedes batch6's era-confounded
S4-vs-S0 0.492. Next lever is data/breadth, not parameters.

> SUPERSEDED by 55-batch7b-adjudicated.md (2026-10-08 19:2x): the /54
> engine-ON retraction does not overturn the plateau — see contamination audit.
