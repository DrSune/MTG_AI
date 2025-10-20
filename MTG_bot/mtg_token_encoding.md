# Handling Token Creatures in MTG RL Agents
The "Mini Entity-Encoding" Refinement
The idea of a "mini entity-encoding/embedding" on individual tokens before combining them into the composite is an excellent way to mitigate the loss of granularity trade-off:
You cannot achieve a 100% fixed-size game-state encoding while guaranteeing the model fully captures and reasons over every creature token as a truly individual entity that can participate in all actions, especially when the number of tokens is unbounded, using only the Composite Entity approach for the encoder input.The Composite Creature / Super-Token Encoding is designed to achieve a fixed-size entity array for the Transformer encoder input by sacrificing individual token granularity at the encoding stage.Here's a breakdown of the trade-off and what you can achieve:What the Composite Approach AchievesGoalResult with Composite EncodingFixed Encoding SizeYES ✅. The game-state encoder input is fixed because only one composite entity slot is used per token type, regardless of the token count.Capture Full InformationYES (Internally) / NO (In Encoder). Full per-token state is kept in the internal JSON for simulation, but the encoder only sees aggregate statistics.Treat Tokens as IndividualPARTIALLY ⚠️. The policy network only reasons over the aggregate (sum/average) stats. The MCTS/rollout phase treats them individually via the internal JSON.Why Individual Reasoning is Limited in the EncoderIf the model's Actor Head and Value Head are downstream of the Transformer encoder, they are operating on the aggregate representation.Loss of Input Granularity: The fixed-size entity array must compress the dynamic, individual information (like 20 tokens with different counter distributions) into a small, fixed-size vector (the composite entity embedding). The policy network cannot distinguish subtle differences between individual tokens because they are lost in the aggregation (sum/average).Action Space Constraint: An action that requires choosing specific individual tokens (e.g., "target token 3 with a removal spell" or "block this 3/3 attacker with tokens 1 and 7, but not 2") cannot be output directly by the policy head, as it doesn't have the individual IDs or features as input. The action must be simplified (e.g., "Attack with 2 tokens from the Composite") and then mapped to individuals by a separate, deterministic logic.How to Maximize Individual TreatmentTo allow the model to learn the dynamics of individual tokens while keeping a fixed-size encoder input, focus on enriching the aggregate embedding and designing a smart action space:Enriched Aggregation (The "Mini-Encoding" Idea):As discussed, use a pooling mechanism (e.g., attention or max/min/median pooling) over the individual token feature vectors to generate the composite entity embedding. This makes the fixed-size aggregate vector much more sensitive to the distribution and extremes of individual token properties (like the highest P/T token or the median number of counters).Hierarchical Action Space:Level 1 (Policy Output): The policy network outputs actions for the Composite Entity (e.g., "Attack with 3 tokens," "Put a counter on 1 token," "Block with 2 tokens").Level 2 (Action Mapping): A separate, deterministic system uses the full individual state (internal JSON) to select the optimal individual tokens to execute the policy's chosen action. This offloads the combinatorial token-selection problem from the neural network to the game engine/MCTS logic, which is where the individual treatment happens.
## 1. Problem

Token creatures in MTG present a challenge for RL-based agents because:

- **Dynamic creation**: Cards or abilities can generate many token creatures during a game.
- **Independent actions**: Each token can attack, block, or use abilities individually.
- **Combinatorial explosion**: Representing each token as a separate entity in the game-state encoder increases input size linearly with the number of tokens.
- **Action flexibility**: Aggregating tokens incorrectly can reduce the agent’s ability to explore strategic choices, such as splitting attacks or blocking optimally.
- **Counters and buffs**: Tokens may be individually modified, e.g., +1/+1 counters, buffs, or temporary effects, requiring per-token information.

**Current naive solution**: pre-allocate a large number of entity slots for tokens.  
**Drawbacks**:  
- Large fixed buffer is often underutilized.  
- Wasteful computation when many token slots are empty.  
- Still susceptible to combinatorial action explosion during rollouts.

---

## 2. Proposed Solution: “Composite Creature” / Super-Token Encoding

**Idea**: Represent multiple identical tokens of the same type as a single **composite entity**, while maintaining **internal structure** for individuality.

### Structure

1. **Composite entity**
   - Represents all tokens of the same type for a given player.
   - Encodes **aggregate statistics**:
     - Total attack potential (`number of tokens × base power` or weighted)
     - Total toughness / effective HP
     - Count of tokens
     - Aggregate counters or buffs (average or sum)
   - Treated as a single entity in the encoder (reduces input size).

2. **Internal token JSON**
   - Nested structure storing **individual token attributes**:
     - Buffs, counters, status effects
     - Turn-based modifiers
   - Allows precise bookkeeping when tokens are affected differently
   - Can update internal states per token without changing the encoder input size

3. **Action interpretation**
   - During rollout or MCTS:
     - The network outputs actions for the composite entity
     - Actions are **mapped to individual tokens** using the internal JSON
     - Example:
       - “Attack with composite entity X” → select the required number of individual tokens in internal JSON
       - Damage or effects are applied to individual tokens based on counters and buffs

---

### Benefits

| Aspect | Benefit |
|--------|---------|
| Input size | Fixed-size entity array, fewer slots needed |
| Memory | Avoids pre-allocating hundreds of token slots |
| Scalability | Handles token floods gracefully |
| Flexibility | Internal JSON preserves individual differences for counters, buffs, and effects |
| Action reasoning | Allows policy network to reason at aggregate level, while still permitting individual token actions to be executed |

---

### Trade-offs / Considerations

1. **Loss of granularity in the encoder**  
   - Aggregate stats (sum or average) may lose subtle per-token differences
   - Mitigation: internal JSON retains full per-token state for rollout simulation

2. **Action mapping complexity**  
   - Composite actions need to be translated into individual token actions
   - Requires deterministic rules or heuristics for distribution of actions among tokens

3. **Counters and effects**  
   - Must ensure that per-token modifiers (buffs, turn-based effects) are consistently updated in internal JSON
   - Encoder sees **aggregate representation**, but MCTS applies effects per token

4. **Edge cases**  
   - Large numbers of partially modified tokens (e.g., 20 tokens with different +1/+1 counters) may require careful aggregation strategy:
     - Use **weighted averages** or **group similar states** within the composite

---

### Example (Pseudo-JSON Structure)

```json
{
  "composite_entity_id": 101,
  "type": "1/1 Goblin Token",
  "player": "PlayerA",
  "aggregate_stats": {
    "count": 20,
    "total_power": 20,
    "average_toughness": 1,
    "counters_sum": 5
  },
  "tokens": [
    {"id": 1, "power": 1, "toughness": 1, "counters": 1, "effects": []},
    {"id": 2, "power": 1, "toughness": 1, "counters": 0, "effects": []},
    ...
  ]
}
```

- The encoder sees `aggregate_stats` as the entity embedding.
- MCTS / rollout maps actions to the `tokens` list to simulate individual behavior.

---

## 3. Summary

- The **composite entity approach** reduces the number of slots needed for token creatures.
- Each player has one composite entity per token type, preserving aggregate stats in the encoder.
- An **internal JSON** stores per-token information to allow individual actions and effects during simulation.
- This approach balances **scalability** with **strategic fidelity**, allowing large token floods without exploding the encoder input size.

---

✅ **Takeaway**:  
By combining **aggregate embeddings** for the network input with **internal token bookkeeping**, you can maintain both efficiency and precise action reasoning, keeping the game-state encoder static while handling complex, dynamic entity creation.

