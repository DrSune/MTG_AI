## Progress: Pro-Scale Hybrid Intelligence (Phase 2 Enhanced)

### Completed:
- **Semantic Pointer Network**: Replaced menu-index selection with Intent-Descriptor matching.
    - Model now reasons about card properties (P/T, CMC) rather than positional memory.
- **Fusion Card Embeddings**: Implemented Atomic + Component embedding path.
- **Full Zone Visibility**: `StateConverter` now processes Hand, Battlefield, Graveyard, and known Deck info into the relational context.
- **Discovery Reward Structure**: Implemented explicit rewards for casting spells (+0.1), playing lands (+0.05), and tapping for mana (+0.01).
- **Fairness & Stability**: Randomized starting player and fixed winner determination logic.
- **Opponent Predictor**: Implemented "Belief Vector" hallucination for hidden opponent info.
- **Dynamic Reasoning Loop**: Truly autonomous System 2 thinking with `rethink_prob` stopping.
- **Urgency Reward Structure**: Implemented efficiency penalty (-0.005/step) to force decisive play.
- **Autonomous Teacher**: Reward aligned with Student Progress Delta (Learning Rate Optimization).
- **Temporal State Encoding**: Added card timestamps and zone-priority sorting to transformer tokens for CR-compliant ordering.
- **Dynamic Choice Resolution**: Implemented `MakeChoiceAction` and Engine-pausing for "As enters" effects (e.g. Runed Halo).
- **Card Learning Rate Schedule**: Integrated CMC-based curriculum (Phase 1: CMC <= 3) into Teacher's archetype selection.

### In Progress:
- **Phase 3 (Universal Generalization)**: Scaling training to include all M21 mechanics and beyond.
- **WandB Integration**: Monitoring the "Intelligence Gap" between Student and Frozen versions.

### Next:
- Execute 1,000 game Foundation Run using `run_train.ps1`.
- Analyze Teacher's "Deck Bias" to see if it discovers the 40/60 land-to-spell meta independently.
- Fine-tune Pointer matching weights if specific card types (e.g., global board clears) are being ignored.
- **Deep analysis of potential speedups for training**:
    - Investigate KV Cache for saving board state/analysis to avoid recomputation during action sequence generation.
    - Optimize learning by addressing "vocabulary" (atomic modular abilities) and context window.
    - Explore TurboQuant methods for card embedding vector database speedups (if embeddings are used rather than atomic encodings).
