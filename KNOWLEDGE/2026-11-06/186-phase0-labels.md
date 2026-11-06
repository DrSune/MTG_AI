# 186 — Phase 0, labels: the generator, E1 (true-future label signal) and E3 (distillation)

2026-11-06. Branch `phase0/labels`. The plan is docs/PLAN_LEARNING.md §1.1-1.4, §2, §3, §12, §13.
Each section below is written and committed before the run it describes; results are appended
under it, and every number goes to NUMBERS.md with its command and commit.

## 1. The generator: a short PPO stage teaches r20 v2 the mulligan (pre-registration)

**Why.** runs/selfplay/r20_ppo/v2.pt predates the London mulligan: its `keep` and `mulligan` rows
were grown from "other", so it samples them 50/50 (NUMBERS 2026-11-06: p(keep) = p(mulligan)
exactly). E1's generator should not mulligan at random. It learns the decision by PPO, not by a
rule: the PPO audit measured a strong gradient on this ask (/184 §25: group cosine 0.55 at 4k
decisions, half signal at ~3.4k rows).

**Run.** `r23_mulligan`: the learner from current main's code (a pinned run worktree at this
note's commit; no code change), `--init runs/selfplay/r20_ppo/v2.pt`, the teacher stage only
(the heuristic is the only opponent: `--teacher-gate 2.0` never passes), r22's settings otherwise
(`--refresh-table --extend-sets M20 --mix-sets M20 --mix-share 0.25 --coherent-share 1.0 --pool
verified --lr 1.5e-4 --ent 0.002 --target-kl 0.03 --epochs 1 --mb 4096 --tok-budget 98304
--infer-bf16`), `--steps 32768` per update, `--lam 1.0` (OWNER_PREFERENCES #6: the full result
reaches every decision), 10 workers, `--save-every 1`, `--mem-floor-gib 15`, nice 10, at most 40
updates.

**Metric.** The mulligan rate: mean p(mulligan) at the first declaration, over 2,000 fixed opening
hands (1,000 coherent M21 verified deals, seeds 7,000,000+, both seats), read from every update's
`last.pt` (scratch `labels/mull_probe.py`); also the greedy share (p(mulligan) > 0.5).

**Stop rule ("until stable").** Stop after the first update t >= 6 at which the last four probes
(t-3..t) span less than 0.02. That update's `last.pt` becomes the E1 generator (copied to
`runs/selfplay/r23_mulligan/gen.pt` and pinned in reports/LARGE_FILES.sha256). No stability by
update 40: stop there, record it, and use update 40.

**Predictions.**
- The rate moves off 0.50 within 3 updates and settles between 0.05 and 0.35 (the heuristic's
  rule mulligans 12 of 66 coherent seats, /NUMBERS 2026-11-06).
- Training win rate against the heuristic (sampled play) rises from about 0.56 (the audit's first
  update) to at least 0.62.
- No damage: on the same 300 evaluation deals against the heuristic (greedy, seeds 900,000+, half
  coherent, half stress), the generator scores at least r20 v2's score on this code minus 0.03
  (paired, `tools/selfplay/paired.py`). Falsified by a drop below that.

**Pre-flight.** `tools.selfplay.preflight` (P1, P8, P9, P12) on the run worktree before launch.
