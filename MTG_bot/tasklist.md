# MTG Bot Task List

## 🤖 Agent Instructions
1.  **Update Documentation:** Always update relevant `.md` files (`engine_map.md`, `thought_checkpoint.md`) to reflect codebase changes.
2.  **Generalization First:** Prioritize reusable components (selectors, actions) over card-specific hardcoding.
3.  **Rigid Testing:** Implementation is incomplete until verified via automated test or the Visualizer.
4.  **Verify Script Execution:** Always verify that the main scripts (`main_train.py`, etc.) run without bugs after making structural changes.
5. **Update the tasklist.md file with the current status of the project.** Always note things that are out of scope or should be done in the future here, so we can come back to them later, without disturbing you in finishing whatever you are currently working on. (This is a meta instruction list for the agent)

---

## ✅ Phase 1: Completed (Rule Engine & AI Infrastructure)
- **100% Set Coverage (M21):** Every card in the set is parsed and functionally supported.
- **Rules Hardening:** Verified Stack (LIFO), State-Based Actions, Priority, and complex interactions (Protection, Indestructible, etc.).
- **Multi-Format Deck Generation:** Teacher can produce valid 40-card (Limited) and 100-card (Commander) singleton decks.
- **AI Observation Bridge:** `StateConverter` maps 300 tokens (Zones, Stack, Cards) into multi-channel tensors.
- **Training Pipeline:** Fully functional loop with PPO logic, loop safety, and high-visibility telemetry.
- **Benchmarking:** Scaled validation to 100+ generalized puzzles across Aggro, Defense, and Value archetypes.

---

## 📋 Current Phase: Large-Scale Learning (Phase 2)

### 🔄 Active Tasks
- [x] **State Observation Update:** Added Zone information (Battlefield, Hand, Graveyard) to card features to help the model distinguish locations.
- [x] **Reward Shaping:** Increased damage-based rewards and added Discovery Rewards (Lands, Spells, Mana) to incentivize active play.
- [x] **Training Stability:** Fixed IndexError and double-counting in plan execution loop.
- [x] **Fairness Update:** Randomized starting player during game initialization.
- [x] **Temporal State Encoding:** Implemented time-indexing and graveyard ordering for the relational transformer.
- [x] **Dynamic Choice Resolution:** Replaced hardcoded "as enters" choices with model-driven decisions (MakeChoiceAction).
- [x] **Card Learning Rate Schedule:** Implemented CMC-based curriculum filter in Teacher.
- [x] **Proactive Hooking:** Added `proactivity_bias` and action masking to force exploration of active moves (Spells, Combat) during Phase 0.
- [x] **General Repetition Safeguard:** Global `step_action_history` cap (max 5 per step) to prevent infinite loops in all scenarios.
- [x] **GPU Acceleration:** Automatic CUDA detection and model migration for 10x training speed.
- [ ] **Initial Training Run:** Execute long-term training session using `main_train.py`.

---

## 🚫 OUT OF SCOPE - Long-Term Roadmap

### Card Recognition (Vision)
- [ ] **YouTube Extraction:** Bounding box and OCR for cards in videos.
- [ ] **Similarity Search:** Vector database for fast card identity matching.

### Advanced AI (Phase 3+)
- [ ] **ISMCTS:** Information Set Monte Carlo Tree Search for dealing with hidden info.
- [ ] **Reward Shaping:** Weighted auxiliary loss for mid-game "win-probability" estimation.
- [ ] **Dynamic Teacher:** Implement RL for the Teacher to generate "weakness-targeted" matchups.

---
*Last updated: Friday, 10 April 2026*
