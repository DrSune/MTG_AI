# MTG AI Central Tasklist

This list tracks bugs, features, and research items. All agents must contribute to and maintain this list.

## 🔴 High Priority (Core Logic & Bugs)
- [x] **Generalized Target Filtering:** Implemented `target_filtering.py` to handle complex criteria (controller, type, status) using structured data.
- [x] **Temporary Effect Manager:** Built `effect_manager.py` to track and expire "until end of turn" effects.
- [x] **CR-Compliant Layer System:** Refactored `layer_system.py` to support all 7 layers and integrate with `TargetFilter` for static/static-like effects.
- [x] **Autonomous Rethink Signal:** Refactored System 2 to be determined solely by the model via `RETHINK` tokens (max 8 passes), removing forced thinking loops.
- [x] **Minimized Snag Penalty:** Reduced the plan-inconsistency penalty to `0.0001` to ensure winning remains the primary objective.
- [x] **Action-Aware Intent Sequencing:** Implemented a system where the model evaluates legal moves (Action Menu) *before* constructing its plan, ensuring strategy is grounded in possibility.
- [x] **Sub-action Rethink Integration:** Updated the execution loop to allow the model to re-plan and re-evaluate at every step, including during forced sub-actions like mana activation.
- [x] **Robust Weight Loading:** Implemented shape-matching weight loader in `Student` class to handle architectural mismatches during checkpoint loading.
- [x] **Fix TypeError in Plan Execution:** Resolved `NoneType` subscript error by correctly passing `plan_step_queries` through the `System2Transformer` output.
- [x] **Action Menu Grounding:** The model now constructs its plans by looking at actual legal moves (Action Menu) first, ensuring its strategies are grounded.
- [x] **Dynamic Sequence Gating:** Update `Engine` to allow multiple actions per phase until an explicit `Pass` is chosen.
- [x] **Effect System Extension:** Generalized handlers for "Damage," "Draw," and "Destroy" effects. Robust regex-based parsing for card text.
- [x] **Improved Model Vision:** Added detailed action descriptors (Color, Type, Mana production) and potential mana observation to help the model learn sequencing without virtual mana.
- [x] **Consolidated Training Logs:** Grouped mana actions in `[MENU]` output for clearer debugging of model choices.
- [x] **Explicit Mana Activation:** Removed virtual mana lookahead in `Engine.get_legal_moves`. Spells now require actual mana in the pool.
- [x] **Fix State-Based Action Bug:** Corrected `check_state_based_actions` to only destroy creatures with 0 toughness, preventing land destruction.
- [x] **Basic Land Fallback:** Added name-based fallback for basic land mana abilities in `mana_handlers.py`.
- [x] **Fix NameError in Target Filtering:** Fixed undefined `is_player` and `is_on_battlefield` in `target_filtering.py`.
- [x] **Improved Action Visibility:** Updated `train.py` to always show `PassPriority` and `PassTurn` in the MENU, ensuring actions don't appear forced.
- [x] **Action Space Mapping:** Create a mapper that converts model action tokens back into `rule_engine.actions` objects for execution.
- [x] **Autoregressive Decoder Implementation:** Replace the dummy decoder in `model.py` with a true autoregressive loop for sequence generation.
- [x] **Phase/Step Validation in Engine:** `get_legal_moves` now strictly checks phases (e.g., Lands/Sorceries only in Main Phases).
- [x] **Stable Entity Ordering in Mapper:** `ActionSpaceMapper` now sorts entities by UUID to ensure token consistency.
- [x] **Fix Mock Test Failures:** Restored test suite integrity, updated tests for M21 cards and new phase validation rules.
- [x] **Keyword ID Consistency:** Added keywords to `game_vocabulary` and updated `CardDataLoader` and `combat_handlers` to use them.

## 🟡 Medium Priority (Benchmarking & Tooling)
- [ ] **M21 Synthetic Dataset:** Generate 100,000+ board states from M21 scenarios for pre-training the `BoardEncoder`.
- [ ] **MCTS + System 2 Integration:** Use the model's `value` and `action_logits` to guide a Monte Carlo Tree Search.
- [x] **Procedural Scenario Generator:** Script to auto-generate 1,000+ Level 1 puzzles for M21.
- [ ] **W&B Integration:** Setup the logging pipeline for the learning metrics defined in `BENCHMARKS.md`.

## 🟢 Low Priority (Polish & Future Research)
- [ ] **Architecture Search (Depth vs. Speed):** Run a benchmark comparing 4-layer vs 8-layer `BoardEncoder` on M21 pass rates.
- [ ] **Reward Shaping for Rethink:** Fine-tune the "Compute Penalty" to find the optimal balance between thinking speed and win-rate.
- [ ] **GUI Visualizer:** A simple tool to view the `GameGraph` state visually for debugging.
- [ ] **Self-Play Loop:** Automated training loop script.

## ✅ Completed
- [x] **CR-Compliant Layer System:** Refactored `layer_system.py` to support all 7 layers and integrate with `TargetFilter` for static/static-like effects.
- [x] **Temporary Effect Manager:** Built `effect_manager.py` to track and expire "until end of turn" effects.
- [x] **Generalized Target Filtering:** Implemented `target_filtering.py` to handle complex criteria (controller, type, status) using structured data.
- [x] **Procedural Scenario Generator:** Implemented `procedural_generator.py` with templates for lethal burn and combat, and updated `scenario_runner.py` to handle JSON scenarios.
- [x] **Database-Driven Effect System:** Refactored `CardDataLoader` to use the SQLite database and updated `EffectHandlers` to use structured `effects_json` for targeting and resolution.
- [x] Initial ARC-AGI style benchmark structure.
- [x] Basic Scenario Runner implementation.
- [x] Manual testing Sequencing fix (Land/Mana actions don't auto-skip phase).
- [x] Vocabulary.py integration.
- [x] **System 2 Recursive Reasoning:** Implemented `System2Transformer` with frozen board encoding and iterative refinement.
- [x] **Rethink Counter Implementation:** Added recursive rethink loop in `DecisionMaker` and state tokenization in `StateConverter`.
- [x] **Frozen Board Embedding:** Implemented `BoardEncoder` for factual state caching.
- [x] **Engine Robustness:** Fixed phase progression bugs, improved legal move validation, and generalized effect system.
