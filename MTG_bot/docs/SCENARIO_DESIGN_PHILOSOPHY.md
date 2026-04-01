# Scenario Design Philosophy

This document outlines the theoretical framework for the MTG AI intelligence benchmarks. These benchmarks are designed to measure cognitive growth across three complexity tiers (ARC-AGI style).

## 🚀 Intelligence Levels

### Level 1: Immediate Tactical (Perfect Information)
*   **Focus:** Direct board interaction and immediate lethality.
*   **Cognitive Task:** Identifying the winning line among 1-5 possible actions.
*   **Requirement:** Correct mapping of factual board state to the Rule Engine.

### Level 2: Sequencing & Resource Management (Turn Optimization)
*   **Focus:** Efficient use of mana, lands, and phase-specific actions.
*   **Cognitive Task:** Ordering actions over a multi-step sequence to achieve a global phase goal.
*   **Requirement:** Solving the "Global Optimization" problem (avoiding local optima).

### Level 3: Probabilistic & Strategic (Hidden Information)
*   **Focus:** Opponent modeling and multi-turn consequences.
*   **Cognitive Task:** Inferring opponent hand/intent and choosing lines that maximize win-probability across multiple plausible scenarios.
*   **Requirement:** Full use of the "System 2" Recursive Reasoning loops.

---

## 📂 Challenge Categories

To ensure a balanced skill set, each level contains the following categories:

1.  **Lethal (`lethal`):** Reducing the opponent to 0 life.
2.  **Board Clear (`board_clear`):** Neutralizing an overwhelming opponent threat.
3.  **Setup (`setup`):** Maximizing value (mana, card draw, board presence) for the next turn.
4.  **Combat (`combat`):** Finding optimal blocks or attacks to trade resources favorably.

---

## 🏗️ Structural Integrity

*   **Set Isolation:** Scenarios are grouped by cardset (e.g., `M21`) to ensure the AI's "intelligence" is grounded in specific, set-accurate rule implementations.
*   **Mass Generation:** Each category is designed to support 1,000+ procedurally generated variations to provide statistically significant learning curves for the RL model.
