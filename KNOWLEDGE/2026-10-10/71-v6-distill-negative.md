# 71 — v6: search-distillation NEGATIVE on outcome meter (0.18 vs teacher) — 2nd divergence proof; defects enumerated

Date: 2026-10-12 (entry 71 dated by knowledge-order; files 2026-10-10 dir ends at 70 — new dir 2026-10-12 starts at 71 next move).
Command: gameplay_eval_v2, bsd_S3a_s1_best (mid-train e136, acc 0.9045) vs bc10_S4_s2 + teacher, 200g CPU.
- mirror vs bc10_S4_s2 (its own PRUNER net): wr 0.2984 CI[.238,.367] — distilled LOSES to the one-shot that generated its data.
- vs greedy teacher: wr 0.1786 CI[.131,.238] — worse than ALL one-shots (bc9 0.39, bc10_S4_s3 0.31). Illegal 0 (engine fine).
Diagnosis (ranked): (1) checkpoint selection by best-TRAIN-loss (e136, train_loss 0.055 = memorized 219 episodes; no patience/holdout) — the SAME disease as S4 instability, now on the distill path; (2) pi noise: k=3,N=6 visits top1-share 0.475 — imitating visit NOISE; (3) data volume/diversity: 16 games, 219 eps, seeds self-play vs self (distribution collapse); (4) anchor dilution at 1:1 (s2 lost puzzle lanes: acc 0.769).
Fixes queued: bigger wave (deck diversity check + >=64 games), holdout-selection (CE on held-out search rows), fewer epochs + patience, temperature/smoothing on pi, anchor up-weight; MODEL SELECT BY A GAMEPLAY-PROXY, NOT train loss.
Law reaffirmed: puzzle acc is NOT skill (2x proven: v5 0.839->0.31; v6 0.905->0.18). Outcome meter gates every claim.
