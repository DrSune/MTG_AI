# Effect Implementation Mandates

## 1. Composite & Atomic Design
All card effects MUST be implemented as a sequence of reusable "Atomic Components." Hardcoding unique card logic is strictly forbidden.

### Required Atomic Components:
- **Selectors (Choosing):**
    - `Count`: Number of targets to choose.
    - `Filter`: Criteria (Opponent, Creature, Land, Hand, etc.).
    - `Mode`: (Targeted, Choice, Random).
- **Actions (Effects):**
    - `Damage`: Deal X damage.
    - `Destroy`: Destroy target.
    - `Discard`: Discard from hand.
    - `Buff`: +X/+X until [Duration].
- **Costs (Resources):**
    - `Mana`: Specific or Generic.
    - `Energy`: Specific types (Black, Red, etc.).
    - `Sacrifice`: Permanent or specific type.

### Example Construction:
*Card Text:* "Choose 2 creatures an opponent controls to deal 3 damage to."
*Structured Implementation:*
```json
{
  "effect_type": "composite",
  "sub_effects": [
    {
      "type": "selector",
      "count": 2,
      "filter": {"type": "creature", "controller": "opponent"},
      "mode": "targeted"
    },
    {
      "type": "action",
      "action_id": "deal_damage",
      "amount": 3
    }
  ]
}
```

## 2. Rigid Testing & Stress Scenarios
Implementation is NOT complete until it passes a "Chaos Test" suite.

### Standard Stress Scenarios:
- **Illegal Target Mid-Resolution:** What happens if the chosen target leaves the battlefield before the damage is dealt?
- **Zero/Negative Values:** Can a card deal 0 damage? Does it still "trigger" effects?
- **Empty Pools:** What happens if "Choose 2" is played when only 1 valid target exists?
- **Circular Dependencies:** Buffing a creature whose power is currently being set by another static effect.

## 3. Functional Parity Mandate
A card is not considered "implemented" simply because its `effects_json` is populated. The `Engine` and its `handlers` MUST be updated to functionally support the parsed data.

### Implementation Workflow:
1.  **Parse:** Ensure `card_data_parser.py` generates the correct atomic JSON.
2.  **Enforce:** Update `Engine.get_legal_moves` and `Engine.execute_move` to handle new `ability_types` (e.g., `additional_cost`).
3.  **Resolve:** Update `effect_handlers.py` to resolve the atomic actions (e.g., `return_from_graveyard`).
4.  **Listen:** Implement the `TriggerManager` to fire `triggered_ability` effects when conditions are met.

## 4. Scope Tracking & Issue Log
If a specific card mechanic (e.g., "The Stack") is required but not yet in scope, it MUST be documented below:

### Known Engine Limitations:
- [ ] **The Stack:** Triggered abilities and responses are currently resolved immediately (LIFO not yet fully enforced).
- [ ] **Multi-Step Choices:** Spells that require choices during resolution (rather than just targeting during casting).
- [ ] **Replacement Effects:** "If X would happen, Y happens instead" logic is not yet implemented.
