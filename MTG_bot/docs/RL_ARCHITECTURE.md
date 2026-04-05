# RL Architecture: Pro-Scale Hybrid Intelligence

This document defines the high-complexity architecture used for the MTG AI foundation.

## 1. Fusion Embeddings (Hybrid Card Representation)
We use a dual-path embedding strategy to balance memorization and generalization:
- **Atomic Embedding**: A learned lookup table for every unique card ID. This allows the model to learn specific card "personalities" and power levels.
- **Component Features**: A 32-dimensional vector of raw card data (P/T, CMC, Type, Keywords). This allows the model to reason about cards it has never seen before based on their mathematical properties.
- **Fusion**: These are combined into a 1024-dim "Intelligence Vector" per card.

## 2. Relational State Representation
The `StateConverter` feeds the model a comprehensive view of the game:
- **Private Info (Self)**: Hand, Battlefield, Graveyard, and the current Deck List (known sequence).
- **Public Info (Opponent)**: Battlefield and Graveyard.
- **Relational Context**: A 16-layer Transformer processes all these entities simultaneously to understand complex relationships (e.g., "This card in my hand can target that creature in the opponent's graveyard").

## 3. Opponent Belief (Predictor)
Since the opponent's Hand and Deck are hidden, the model includes a dedicated **Opponent Predictor**. It analyzes public state and previous moves to "hallucinate" a latent **Belief Vector** representing the opponent's likely resources and strategy.

## 4. System 2 Reasoning (Recursive Planning)
The model does not just react. It uses a **Reasoning Head** to iteratively refine its internal plan:
- **Recursion**: The model proposes a "draft intent," feeds it back into itself, and refines it (up to 8 times).
- **Plan Feedback**: The reasoning head receives the **Plan Embedding** from the previous pass, allowing it to evaluate and refine its own proposed sequence of actions.
- **Autonomous Rethink Signal**: 
    - Thinking is never forced. The number of reasoning passes is controlled by the model itself.
    - If the model predicts a `RETHINK` (9) token in its action plan, it triggers another reasoning pass.
    - If no `RETHINK` is requested, it stops after the first pass (Pass 1) and executes.
    - This allows the model to learn when it needs to "stop and think" versus when it can act purely on intuition.

## 5. Grounded Predictive Intent Sequencing
Instead of a single reactive move, the model generates a **Predictive Intent Sequence** (The Plan) using an autoregressive transformer decoder:
- **Autoregressive Intent Generation**: The model predicts a sequence of "Semantic Queries." Each query represents an intended action type and the desired properties of its source/target.
- **Semantic Alignment Gatekeeper**: 
    - At each execution step, the model evaluates all **actual legal moves** from the Rule Engine.
    - It calculates the alignment (dot-product similarity) between its current "Intent Query" and the legal action descriptors.
    - This ensures that every action taken is **100% legal** while being guided by long-term strategy.
- **Plan Continuity & Snags**:
    - If an intended action becomes illegal (a "snag"), the model receives a small **Plan-Consistency Penalty**.
    - It then immediately triggers a "Rethink" to generate a new grounded plan from the updated board state.
- **Sub-action Awareness**: This architecture naturally handles forced sub-actions (mana tapping, targeting) because the model learns that these intents are prerequisites for high-reward terminal actions (casting spells).
- **Special Gating Tokens**:
    - `END_PLAN` (0): Signals the sequence is complete.
    - `RETHINK` (9): Signals the model wants to re-evaluate the board before the next step.

## 6. Reward & Urgency Logic
- **Primary Reward**: Win (+1.0) / Loss (-1.0).
- **Efficiency Penalty**: -0.005 per step (1 damage equivalent per 10 steps). This forces the model to seek the fastest path to victory and prevents stalling.
- **Dense Rewards**: Small bonuses for dealing damage, playing permanents, and drawing cards to jumpstart the learning process.
