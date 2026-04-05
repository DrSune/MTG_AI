# Training Stability & Performance

This document describes how to manage training duration and prevent the system from getting "stuck" in long or infinite game loops.

## 1. Controlling Episode Length
The primary mechanism for preventing indefinite runs is the `steps_per_episode` parameter in `MTG_bot/strategic_brain/config_rl.py`.

*   **Production Training:** `steps_per_episode = 10000` (Allows for long, complex games in formats like Commander).
*   **Testing/CI:** `steps_per_episode = 200` (Quickly terminates games that stall or loop).

If a game reaches this limit, it is treated as a "Stall/Draw" and the environment is reset.

## 2. Preventing Rule Engine Loops
The `Engine` class in `MTG_bot/rule_engine/engine.py` has a safety valve:
*   `MAX_MOVES_PER_STEP = 500`: If more than 500 actions are taken in a single phase/step (e.g., an infinite loop of triggered abilities), the engine sets `game_over = True` and records a stall.

## 3. Fast Testing Mode
To verify changes without waiting for a full training cycle, you can run a limited test using the `Scenario Runner`:
```bash
python -m MTG_bot.scenarios.scenario_runner
```
Or use a custom test script with a small `steps_per_episode` override.

## 4. Manual Verification
Always test new card logic or engine changes with a small reproduction script (like `repro_mana.py` used in development) before committing to a full training run. This ensures that "obvious" failures are caught before the model spends hours trying to learn from a broken state.
