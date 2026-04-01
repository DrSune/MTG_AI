# Testing & Validation Strategy

To ensure both the Rule Engine is correct and the AI Model is "intelligent," we use a multi-tiered testing approach.

## 1. Rule Engine Tests (Behavioral Correctness)
**Goal:** Verify that the MTG rules are implemented correctly.
- **Unit Tests:** `MTG_bot/rule_engine/test_*.py`
- **Integrations:** Full game simulations (MCTS) with random agents to find crashes or rule-breaking states.

## 2. Model Benchmarks (Intelligence)
**Goal:** Quantify how "smart" the model is.
- **Scenario Benchmarks:** Hand-crafted MTG "puzzles" in `MTG_bot/scenarios/`. 
    - *Example:* Can the model find a lethal attack in one turn? 
    - *Example:* Does the model know when to hold mana for a response?
- **Elo System:** Track win rates against baseline agents:
    - `RandomAgent`: Picks a random legal move.
    - `GreedyAgent`: Picks the move that maximizes immediate life total difference.
    - `RuleBasedAgent`: Uses simple heuristics (e.g., "play lands first").

## 3. Manual Testing (PvE)
**Goal:** Allow humans to play against the model to catch subtle "un-fun" or "stupid" behaviors that metrics might miss.
- Interface: `MTG_bot/main.py`
- Mode: `Manual` vs `Model` vs `Mixed`.

## 4. Regression Testing
- Every major code change should run the **Scenario Runner** to ensure the model hasn't "unlearned" basic MTG concepts.
