# MTG AI Central Tasklist

This list tracks bugs, features, and research items. All agents must contribute to and maintain this list.

## 🔴 High Priority (Core Logic & Bugs)
- [x] **Generalized Target Filtering:** Implemented `target_filtering.py` to handle complex criteria (controller, type, status) using structured data.
- [x] **Temporary Effect Manager:** Built `effect_manager.py` to track and expire "until end of turn" effects.
- [x] **CR-Compliant Layer System:** Refactored `layer_system.py` to support all 7 layers and integrate with `TargetFilter` for static/static-like effects.
- [ ] **Advanced Effect Parsing:** Improve the `card_data_parser.py` regex/logic to populate `effects_json` for more complex card text.
- [x] **Dynamic Sequence Gating:** Update `Engine` to allow multiple actions per phase until an explicit `Pass` is chosen.
- [x] **Effect System Extension:** Generalized handlers for "Damage," "Draw," and "Destroy" effects. Robust regex-based parsing for card text.
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
