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
- **Dynamic Stopping**: Based on a `rethink_prob` (confidence), the model chooses when to stop thinking and act.

## 5. Semantic Pointer Action Selection
The model uses a **Pointer Network** for decision making:
- **Intent Matching**: The reasoning process produces a "Global Intent" vector.
- **Descriptor Matching**: Every legal action is converted into a semantic descriptor (e.g., "Cast a 3/3 for 4").
- **Similarity**: The model calculates the dot-product similarity between its Intent and all legal descriptors, "pointing" to the most appropriate move.
- **Benefit**: This handles variable action spaces and generalizes across thousands of cards by their properties rather than their list position.

## 6. Reward & Urgency Logic
- **Primary Reward**: Win (+1.0) / Loss (-1.0).
- **Efficiency Penalty**: -0.005 per step (1 damage equivalent per 10 steps). This forces the model to seek the fastest path to victory and prevents stalling.
- **Dense Rewards**: Small bonuses for dealing damage, playing permanents, and drawing cards to jumpstart the learning process.
