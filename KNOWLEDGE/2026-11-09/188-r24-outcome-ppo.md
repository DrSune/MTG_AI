# 188 — r24 outcome PPO learner: γ = λ = 1 at batch size B* (2.65M decisions)

2026-11-09. Main branch. Pre-registration written before launch.

## 1. Context and Problem

Phase 0 completed on 2026-11-09:
- E0 (opponent simulator): passed (hand NLL / yardstick 0.889 overall, ECE 0.0004).
- E1 (true-future label signal): passed on configuration A (B*_FP 2.17M, 2.4x cheaper than outcome PPO's bound).
- E3 (distillation): failed (distillation kept the generator; trained epochs reduced regret by only 2–4% with zero measurable win rate gain over 900 games).

Per owner instruction (DECISIONS [D21](../../docs/DECISIONS.md#L644-L663)):
1. Distillation from playout labels is parked in [`docs/BACKLOG.md`](../../docs/BACKLOG.md).
2. Decision-time search on opponent simulator futures is kept for play time (Phase 2 / E2).
3. The learner path falls back to outcome PPO under [OWNER_PREFERENCES.md #6](../../KNOWLEDGE/OWNER_PREFERENCES.md#L30-L37) (full outcome credit: $\gamma = \lambda = 1$).

In `r22`, training updates of 98,304 decisions contained $<1\%$ gradient signal under $\lambda = 1$ because single-game deal luck dominated the variance ([KNOWLEDGE /184 §25-§26](../2026-11-05/184-bug-hunt-verified-pool-cleanup.md#L476-L525)). The PPO audit measured that reaching a signal-to-noise ratio $\ge 1$ with outcome credit requires batch sizes of at least **$B^* \ge 2.65\text{M}$ decisions** (~58k games, ~40–50 minutes of self-play generation per update).

## 2. Configuration & Changes vs r22

- **Run name:** `r24_outcome_ppo`
- **Starting weights (`--init`):** `runs/selfplay/r23_mulligan/gen.pt` (starts from `r20 v2` with 31 PPO updates learning the London mulligan, keep rate >99%, avoiding 50/50 mulligan noise)
- **Credit:** `--gamma 1.0 --lam 1.0` (pure Monte-Carlo outcome credit)
- **Batch size:** `--steps 2650000` (~2.65M decisions per update, $\ge B^*$)
- **Optimization:** `--epochs 1 --lr 1.5e-4 --wd 0.01 --clip 0.2 --vclip 0.5 --vcoef 0.5 --ent 0.002 --max-grad 1.0`
- **KL guard:** `--target-kl 0.03` (measures KL from the start-of-update policy, using the audit's fix in `ppo.py`)
- **Minibatches:** `--mb 4096 --tok-budget 98304 --infer-bf16`
- **Schedule cadence:**
  - `--eval-every 1` (evaluates against heuristic anchor every update, ~200 deals)
  - `--gate-every 1` (evaluates against current frozen version every update, ~300 deals)
  - `--ladder-deals 150`
  - `--save-every 1` (saves `last.pt` and atomic `state.pkl` every update)
  - `--progress-every 300.0` (progress logs every 5 minutes during collection)
- **Curriculum:** `--teacher-iters 5 --teacher-gate 0.65` (verifies anchor score on iteration 1 and transitions to selfplay)
- **Opponent mix:** `--p-heuristic 0.15 --p-past 0.15 --coherent-share 1.0 --mix-sets M20 --mix-share 0.25 --extend-sets M20 --refresh-table --pool verified`
- **Safety rail:** `--mem-floor-gib 15.0` (guards unified memory on the DGX Spark)
- **Hardware setup:** 18 workers, 16 slots, 4 groups (~1,100–1,400 dec/s)

## 3. Pre-registered Predictions

1. **Gradient Signal:** With batch size $B^* = 2.65\text{M}$ decisions and $\gamma = \lambda = 1$, the gradient is at least 50% signal ($\text{SNR} \ge 1$), avoiding the random-walk behavior observed in `r22`.
2. **Exploitation Slope:** The win rate against the first frozen version ($v1$) exhibits a positive exploitation slope $\ge +0.03$ per 100 updates over iterations 1–20 (falsified by $\le 0.0$).
3. **Anchor Stability:** Evaluation win rate against the heuristic anchor remains $\ge 0.65$ across self-play training.
4. **Explained Variance:** Critic explained variance ($\text{ev}$) remains stable ($>0.60$).
5. **Stability:** Per-minibatch KL stop does not fire on $>50\%$ of updates, and no non-finite gradients occur.

## 4. Kill Criteria

- **K1:** Any rules engine crash or unhandled exception.
- **K4:** Critic explained variance $\text{ev} < 0$ for 3 consecutive updates.
- **K7:** Sustained throughput drops below 10 games/s.
- **Memory floor:** Run trips `--mem-floor-gib 15.0` twice.

## 5. Pre-flight & Launch

- P1, P8, P9, P12 verified via `tools.selfplay.preflight`.
- Code executed from the pinned run worktree `../MTG_AI-run` detached at this commit.
