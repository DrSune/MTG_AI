# Benchmarking Intelligence

This document outlines the specific metrics and scenarios used to follow along with the MTG AI's learning progress.

## 📈 Learning Metrics (W&B)

We use **Weights & Biases (wandb)** to track the following:

| Metric | Description | Interpretation |
|--------|-------------|----------------|
| `win_rate_vs_random` | % wins against a RandomAgent | Base-level competency. |
| `win_rate_vs_greedy` | % wins against a GreedyAgent | Strategic depth. |
| `scenario_pass_rate_l1` | % of Level 1 (Tactical) puzzles solved. | Immediate board state comprehension. |
| `scenario_pass_rate_l2` | % of Level 2 (Sequencing) puzzles solved. | Resource and action ordering mastery. |
| `scenario_pass_rate_l3` | % of Level 3 (Strategic) puzzles solved. | Opponent modeling and long-term planning. |
| `avg_mana_efficiency` | `mana_spent / mana_available` per turn. | Optimization of resources. |
| `card_advantage_avg` | `(hand + battlefield)_p1 - (hand + battlefield)_p2` | Resource management. |
| `mean_reward` | Average cumulative reward. | Standard RL metric. |

## 🧩 Scenario Framework (ARC-AGI Style)

We use a 3-tiered difficulty system to accurately gauge the intelligence of the model. Because we need thousands of tests to measure gradual RL improvements, these are procedurally generated.

See [Procedural Scenario Generation](PROCEDURAL_SCENARIOS.md) for details on how we build thousands of tests.

### Level 1: Immediate Tactical (Perfect Info)
- Single-action or short-sequence solutions.
- Example: **Lethal Seek** (Opponent at 2 life, Player has Shock and mana).

### Level 2: Sequencing & Resource Management
- Full turn optimization, order of operations.
- Example: **Play Land and Cast** (Must sequence land drops before casting).

### Level 3: Probabilistic & Long-term Strategy
- Requires hidden state inference and multi-turn planning.
- Example: **Hold up Mana** (Recognizing opponent is likely to attack, so keep mana open for a combat trick instead of playing a creature).

## 🛠️ Scenario Runner Usage

```bash
python -m MTG_bot.scenarios.scenario_runner
```
