## Project-Specific Context for MTG_bot

This document outlines key architectural and data handling details specific to the MTG_bot project. This information should be considered when performing any tasks related to code modification, feature implementation, or debugging.

### Data Initialization and Card Abilities

*   **Game Initialization**: All game initialization is currently based on the data stored in the `mtg_cards.db` SQLite database.
*   **Card Abilities (`effects_json`)**: The `effects_json` column in the `cards` table is crucial. It stores structured representations of card abilities, allowing for their breakdown into individual components. This component-based structuring is essential for creating entity-embeddings that support generalization to new or unseen cards.

### Game State Encoding and AI Architecture

The AI architecture for the MTG_bot follows a specific sequence for decision-making:

1.  **Encoder Initialization**: An encoder is initialized at the start of every game.
2.  **Turn/Phase Cycle**: At the beginning of every game, and potentially every phase or round (decision pending), the following steps occur:
    *   **First Encoding**: The game state is encoded based on the *visible game-state*.
    *   **Opponent Hidden Prediction**: An "opponent-hidden-predictor" is run. This component predicts hidden information about the opponent (e.g., cards in hand, deck contents, potential strategies).
    *   **Second Encoding**: The game state is encoded *again*. This second encoding incorporates the visible game-state *and* the latest output from the "opponent-hidden-predictor" (if available).
3.  **Value Function (`V`)**: A value function/network `V` takes this encoded game-state and estimates its value.
4.  **MCTS Refinement**: Monte Carlo Tree Search (MCTS) is used to refine the estimated value. This involves PUCT (Polynomial Upper Confidence Trees) simulation on `N` leaf nodes to derive an estimated "Q" value, which forms the basis for action selection.
5.  **Decoder for Action Generation**: A decoder then generates a sequence of `K` action tokens. Each token corresponds to a sub-choice within an action (e.g., choosing a card, selecting an ability, picking a target).
    *   **Action Sequence Length**: The logic for determining the number of actions in a round (when to "pass") is not yet decided.
    *   **Exploration of Sequence Length**: Sufficient exploration of the choice of decoding sequence length is crucial. It must be optimal while allowing for a low probability of requiring future re-construction to support new cards.

### Learning and Generalization

*   **Learning Mechanism**: Full rollouts and Backpropagation Through Time (BPTT) will be employed to ensure effective learning.
*   **Generalization**: A core challenge is ensuring generalization to new/unseen cards. This necessitates that card components and their interactions are effectively encoded.
*   **Encoding Complexity**: The size of entity-embedding vectors and the game-state encoding size are important considerations. They must be sufficiently complex to handle the scope of Magic: The Gathering, both current and future.

### Development Practices

*   **Utility Tools**: The `utils` folder contains a logger and useful decorators for human-readable output.
*   **Quality Assurance**: Testing and logging everything is of utmost importance at all times.
