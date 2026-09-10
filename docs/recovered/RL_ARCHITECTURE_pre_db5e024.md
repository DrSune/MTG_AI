# MTG RL Agent: Data Flow & Encoding Overview

## 1. Database Layer

**Purpose:** Store canonical information about cards and game entities for scalable, reproducible embedding.

| Column / Item | Description | Usage |
|---------------|------------|-------|
| `card_id` | Unique numeric ID for each card | Primary key for indexing and embedding |
| `name` | Human-readable card name | Logging, debugging, board display |
| `stats` | Numeric fields: power, toughness, mana cost, etc. | Entity embeddings |
| `effects_json` | Component-wise parsed abilities (e.g., “Choose 1”, triggers, targets) | Used to construct component-level embeddings |
| Other fields | Type, subtype, keywords, rarity | Optional features for embeddings, predictions |

**Key points:**
- Use numeric IDs for efficiency, human-readable names only for logging/debugging.
- Database lookups occur **once at setup / card load**, not per rollout.
- Effect parsing into **component-wise vectors** allows a compact and scalable representation of complex abilities.

---

## 2. Game-State Creation

**Purpose:** Construct a structured representation of the current game for the policy, value, and opponent-prediction networks.

**Components:**

1. **Entity tokens**
   - One token per **active entity** (creature, artifact, land, spell, etc.)
   - Each token includes:
     - Component-wise embedding (parsed from `effects_json`)
     - Current stats (power, toughness, counters, etc.)
     - Zone (battlefield, hand, graveyard, exile)
     - Controller / ownership info
   - Tokens are **dynamic**, reflecting only entities currently relevant in the game.

2. **Global summary tokens**
   - Aggregate information about zones, counts, or deck composition summaries.
   - Optional: represent entire deck / hand distributions or opponent inferred state.

3. **Optional short history tokens**
   - Last `K` actions/events (compact representation)
   - Encodes:
     - Actor
     - Action type
     - Card ID / class
     - Source/destination zone
     - Turn/time info
   - Useful primarily for opponent inference and hidden-state reasoning.

---

## 3. History Encoding

**Purpose:** Capture information about hidden variables and opponent intentions that are **not fully observable** in the current game state.

**Representation options:**

1. **Belief vector (`b_t`)**
   - Learned via a small network (RNN, GRU, MLP)
   - Input: short history tokens + current visible state
   - Output: fixed-size vector representing **posterior over opponent hand/deck and likely plays**
   - Can encode multiple plausible scenarios via:
     - **Flattened mixture**: concatenation of top-K scenario embeddings weighted by likelihood × impact
     - **Aggregated expectation**: weighted sum or attention over all plausible scenarios
     - **Scenario-aware attention tokens**: each scenario as a separate token for the policy network to attend to

2. **Deterministic bookkeeping**
   - Exact counts for opponent cards in hand, graveyard, deck
   - Maintains mass conservation and allows fast updates per forward simulation step
   - Serves as input for the belief vector

3. **Particle sampling (optional)**
   - Sample `M` plausible opponent states consistent with observed info
   - Used for Monte Carlo rollouts to estimate expected outcomes under uncertainty

**Training:**
- Supervised pretraining: predict opponent state from self-play logs
- Fine-tuned end-to-end with RL: gradients flow from policy/value head to belief predictor, encouraging strategic prioritization

---

## 4. Policy / Value / Action Heads

**Inputs:**
- Entity tokens (battlefield, hands, zones)
- Global summary tokens
- Belief vector `b_t` (distilled opponent state)
- Optional: short history tokens for high-impact recent actions
- `rethink_counter`: An integer token tracking the depth of current reasoning.

### The "System 2" Recursive Reasoning Mechanism
The model uses **Recursive Transformer Reasoning** to simulate deeper thought without the exponential cost of game-tree search.

#### 1. Frozen Board Cross-Attention
*   **Initial Pass:** The transformer encoder processes the raw board state (entities, zones, hand) into a fixed tensor: `Z_board`. This embedding is **frozen** for the rest of the phase.
*   **Reasoning Passes:** In each iteration ($i$), the model generates a "Reasoning Latent" `Z_reason_i`. 
*   **Connection:** During every reasoning pass, the model uses **Cross-Attention** to "look back" at the frozen `Z_board`. This ensures every "thought" is grounded in the factual state without re-encoding the raw data.

#### 2. Iterative Memory & Self-Analysis (The Feedback Loop)
*   **Latent Memory:** The output hidden state of reasoning pass $i$ is fed back into pass $i+1$ as a set of "Memory Tokens."
*   **Action Memory:** The **proposed action sequence** from pass $i$ is embedded and fed back as input to pass $i+1$.
*   **Grounding & Critique:** This allows the model to "critique" its own previous strategy. Pass 2 effectively sees: *"The board state is X (from Frozen Cross-Attention), and my previous plan was Y (from Action Memory). Upon further reflection, Y is risky because of Z."*

#### 3. Autonomous Rethink Gating
*   **The Rethink Token:** The action space includes a `<rethink>` token.
*   **Learning Duration:** During RL training, each rethink pass incurs a small "compute penalty" (negative reward). The model will naturally learn the **Optimal Stopping Point**—rethinking only when the expected value gain ($ \Delta V $) from deeper thought outweighs the compute cost.

#### 4. Final Output Handling
*   **Policy & Value Heads:** Only the **latest iteration's** hidden state is passed to the final Policy and Value heads. This represents the most "refined" version of the model's intent.
*   **Opponent Model:** The Opponent Predictor receives the final distilled belief vector ($b_t$) generated after all reasoning steps are complete.

### Dynamic Action Sequences (Global Phase Optimization)
MTG allows multiple actions per phase. To avoid local optima:
*   The model predicts a sequence of actions.
*   **The Value Function** only provides a reward signal at the *end* of the phase sequence (when `PassPriority` is chosen).
*   This forces the model to evaluate the "Global State Change" of an entire turn's worth of sequencing rather than individual taps or casts.

**Processing:**
- Can use Transformer / attention-based encoder over entity tokens + global tokens
- Attention can be:
  - **Dense local** (within zones)
  - **Sparse / global** (summary tokens, key relationships)
- Policy/value heads act on this representation:
  - `b_t` provides inferred hidden information
  - Network can attend to multiple scenarios or use aggregated belief

---

## 5. Teacher RL (Co-Evolutionary Curriculum)

**Objective:** Automatically generate a diverse set of deck matchups and scenarios to maximize the Student's learning rate and force generalization.

### 1. The Teacher's Role
The Teacher is a separate RL agent whose "game" is to construct matchups. It does not play the matches; it designs them.
*   **Action Space (Intelligent Sequential Selection):** The Teacher builds decks card-by-card using a **Transformer-based Matchup Analyzer**.
    *   For each slot, the model generates a **Query Vector** based on the current deck's synergy and the opponent's strategy.
    *   It performs a **Vector Search** against the card embedding pool to find the optimal card to add.
*   **Input:** The Student's performance on the previous matchup (e.g., win rate, "confidence" gap, or reasoning depth used).
*   **Reward:** The Teacher receives a reward based on the **Student's Learning Progress**. 
    *   **High Reward:** Matches where the Student was initially wrong but "learned" (improved value accuracy) or matches that were closely contested (High Entropy).
    *   **Low Reward:** Matches that were "stomps" (Student wins/loses 100% easily) or impossible counter-matchups.

### 2. Strategy: Breaking the Meta-Cycle
To prevent the Student and Teacher from getting stuck in A > B > C > A "rock-paper-scissors" loops:
*   **Matchup History:** The Teacher maintains a batch-wise history of recent deck matchups and results.
*   **Diversity Bonus:** The Teacher is incentivized to explore "niche" decks or unusual card combinations that the Student hasn't seen recently.
*   **Generalization Pressure:** By strategically rotating decks, the Teacher forces the Student's `BoardEncoder` to learn universal MTG principles (e.g., "mana advantage," "card parity") rather than just memorizing specific card interactions.

### 3. Validation & Legal States
To ensure the Teacher doesn't create "impossible" scenarios:
*   **Engine Verification:** Every matchup or board state proposed by the Teacher is passed through the `Rule Engine`'s validation logic (e.g., deck size, mana constraints, legal card combinations).
*   **Playability Filter:** Only "legal" states are used for training. If the Teacher proposes an illegal state, it receives a penalty.

---

## 6. Handling Multiple Opponent Scenarios

**Objective:** Take into account that multiple plausible opponent states may exist.

**Options:**

| Approach | Description | Pros | Cons |
|----------|------------|------|-----|
| **Top-K scenario embeddings** | Concatenate embeddings of K most likely scenarios, weighted by likelihood × impact | Explicit representation of multiple possibilities | Vector grows linearly with K |
| **Aggregated expectation** | Weighted sum or attention over scenario embeddings to produce fixed-size `b_t` | Fixed-size vector, scalable | Potential loss of fine-grained scenario info |
| **Scenario tokens for attention** | Each scenario is a separate token; policy network attends dynamically | Rich reasoning over scenarios | Slightly higher compute; need masking for variable K |

**Integration:**
- `b_t` or scenario tokens are **fed into the action head** so the policy considers the expected consequences across multiple plausible opponent states.
- Optional: include likelihood × impact weighting directly in the embeddings or as an attention bias.

---

## 7. Role of History vs. Belief Vector

| Item | Purpose | Used by | Integration |
|------|--------|---------|------------|
| Raw history tokens | Capture recent actions/events | Opponent predictor | Feed into RNN/MLP to produce `b_t` |
| Belief vector `b_t` | Encodes posterior over opponent hidden state + likely high-impact scenarios | Policy/action/value heads | Concatenated to global token or fed as extra input; do not embed into every entity token |
| Deterministic card counts | Exact bookkeeping | Opponent predictor, belief updater | Update incrementally per move, lightweight |

> Key principle: history is only **directly used to generate the belief vector**. The action and value heads only see the distilled output (`b_t`), not raw history. This prevents computational bloat while preserving strategic inference.

---

## 8. Optional Efficiency / Sparsity Measures

- **Zone-local dense attention**: dense attention within battlefield, hand, or graveyard zones; inter-zone via summary tokens.
- **Top-K attention / learned focus**: attend only to most relevant entities or scenarios.
- **Low-rank / factorized attention**: approximate full attention with linear cost.
- **Hierarchical pooling**: represent large zones (deck, large graveyard) with summary embeddings; full entity detail only for high-impact entities.
- **Incremental belief updates**: compute `b_t` at root; incrementally update for child nodes in MCTS to reduce repeated computation.

---

## 9. Data Flow Summary

1. **DB → Component embeddings**
   - Each card parsed into component-wise vector
   - Loaded into memory (IDs + embeddings + optional human-readable names)

2. **Game-state construction**
   - Collect all active entities → entity tokens
   - Create global summary tokens
   - Optional: short history tokens

3. **Opponent predictor**
   - Inputs: entity tokens + short history tokens + deterministic counts
   - Outputs: `b_t` (belief vector, scenario embeddings, or particle set)

4. **Policy/value/action heads**
   - Inputs: entity tokens + global tokens + `b_t` (+ optional scenario tokens)
   - Outputs: action probabilities / values
   - Network can consider multiple opponent scenarios via `b_t` or scenario tokens

5. **Rollouts / MCTS**
   - Use `b_t` to sample plausible opponent states or weight rollouts
   - Incrementally update `b_t` along simulation path if desired
   - Compute returns for policy/value updates

---

## ✅ Key Principles

- Keep **raw history limited** and only feed it to opponent predictor.
- `b_t` is the **distilled representation of opponent state**, can encode multiple scenarios and strategic impact.
- Policy/action/value heads condition on `b_t`, not raw history.
- Use sparse/hierarchical attention and/or scenario aggregation to **reduce compute while preserving critical info**.
- Maintain deterministic bookkeeping (counts) for cheap, exact updates.
- Consider short horizon history tokens for rare but high-impact events that are not easily captured in `b_t`.

This structure ensures:
- Scalable representation for up to 300 entities.
- Multiple opponent scenarios can be considered strategically.
- Efficient computation without embedding raw history into every entity token.
- Strong integration of opponent modeling with policy/value decision-making.
