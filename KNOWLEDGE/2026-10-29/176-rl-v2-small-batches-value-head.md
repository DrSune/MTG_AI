# 176: RL v2, make RL work first: small on-policy batches with a value head (owner, 2026-10-29)

For the local agent. The owner reviewed pilot v1's mechanics (/173) and set the next step:
- smaller batches, 20 or 50 games per update;
- a value function;
- no long-run exploration until RL is shown to work.

The plan is in `docs/PLAN_COMPONENT_TRAINING.md`, Step 4, "First make RL work".

Summary:
- **Loop.** Collect G = 50 games with the current policy on fresh seeds, then one PPO update with
  Adam.
- **Credit.** A value head, warm-started on recorded games, gives each decision an advantage
  (GAE, γ = 1, λ = 0.95). The reward stays the outcome.
- **Opponent.** A frozen copy of the starting net.
- **Trainer.** Must batch decisions.
- **Engine.** Debug the loop on today's engine; real runs wait for the corrected engine (era
  boundary).
- **Success** (draft pre-registration): mirror win rate at least 0.55 with the 95% CI above 0.5, at
  n = 400, within 100 iterations.

This replaces the steps ladder after tonight's window (#5, steps 3), which stays as armed. The /173
table already hands the decision to the owner if that point is flat.
