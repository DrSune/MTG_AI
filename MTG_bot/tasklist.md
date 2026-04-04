# MTG Bot Task List

## 🤖 Agent Instructions
1.  **Update Documentation:** Always update relevant `.md` files (`engine_map.md`, `thought_checkpoint.md`) to reflect codebase changes.
2.  **Generalization First:** Prioritize reusable components (selectors, actions) over card-specific hardcoding.
3.  **Rigid Testing:** Implementation is incomplete until verified via automated test or the Visualizer.

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
- [ ] **Initial Training Run:** Execute long-term training session using `main_train.py`.
- [ ] **Self-Play League:** Implement the `OpponentPool` to prevent strategy collapse.
- [ ] **State Observation Update:** Ensure the AI's "Latent Memory" correctly tracks hidden information (opponents' hands) probabilistically.
- [ ] **Temporal State Encoding:** Implement time-indexing and graveyard ordering for the relational transformer.
- [ ] **Dynamic Choice Resolution:** Replace hardcoded "as enters" choices (like Runed Halo naming) with model-driven decisions.

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
*Last updated: Friday, 3 April 2026*
