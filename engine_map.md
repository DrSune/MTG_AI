# Engine Map

## actions.py
This file defines data structures for representing game actions (moves):
- **PlayLandAction**: Playing a land card from hand
- **CastSpellAction**: Casting a spell from hand (with optional target)
- **ActivateManaAbilityAction**: Activating a mana ability
- **DeclareAttackerAction**: Declaring a creature as an attacker
- **DeclareBlockerAction**: Declaring a creature to block an attacker
- **PassPriorityAction**: Passing priority to advance step/phase
- **PassTurnAction**: Passing the turn

## card_database.py
This file provides utility functions to retrieve card costs, creature stats, and abilities from the card data loader:
- **get_card_cost**: Returns mana cost for a card ID
- **get_creature_stats**: Returns power and toughness for creatures
- **get_card_abilities**: Returns keywords and mana abilities

## card_data_loader.py
This class loads and processes card data from the SQLite database, parsing mana costs, type lines, and extracting keyword abilities.

## card_data_parser.py
This module downloads MTGJSON data, sets up the SQLite database schema, and parses card text into structured effect dictionaries.

## effect_manager.py
This file manages active continuous effects and their life cycles. It handles:
- Adding continuous effects with source, duration, and layer
- Expiring effects based on duration type
- Retrieving effects for specific layers
- Removing effects from a source

## engine.py
This is the main game engine that:
- Determines all legal moves for the current player
- Executes chosen moves and updates game state
- Handles phase/step progression through the turn structure, including automatic logic:
    - **Untap Step**: Untaps all permanents and resets Summoning Sickness.
    - **Draw Step**: Automatic card draw for the active player.
    - **Combat Damage Step**: Automatically triggers `assign_combat_damage`.
    - **Cleanup Step**: Expires "until end of turn" effects and resets combat flags/damage.
- Manages effects and layer system
- Checks win/loss conditions
- Supports manual mode for interactive play

## game_graph.py
This file defines the foundational data structures for the entire rule engine:
- **Entity**: Generic container for any object, property, or concept in the game
- **Relationship**: Directed, typed edge linking two entities
- **GameGraph**: Complete graph-based representation of game state with methods for:
  - Initialization and game state management
  - Entity and relationship CRUD operations
  - Card zone movement and deck management
  - Controller lookup for entities

## game_initializer.py
This module initializes game state with:
- Two players with health, mana pools, and properties
- Deck creation and shuffling from decklists
- Opening hand drawing (with support for chosen cards)
- Game settings retrieval from database (hand size, deck size, starting life)

## game_state.py
This file defines data structures for the game state (board representation):
- **Card**: Machine-readable card representation with name, mana cost, type, text, power, toughness
- **Player**: Player with zones (hand, library, graveyard, battlefield, exile) and mana pool
- **GameState**: Complete game state with players, turn number, active player, phase, and stack
- Includes placeholder methods for game manipulation

## handlers/
This directory contains handler modules for specific game mechanics:
- **activated_ability_handlers.py**: Activated ability resolution
- **card_specific_handlers.py**: Card-specific effect handling
- **combat_handlers.py**: Attacker/blocker declaration and combat damage
- **continuous_effect_handlers.py**: Continuous effect application
- **effect_handlers.py**: Spell effect resolution and continuous effect application
- **graveyard_handlers.py**: Graveyard-related effects
- **keyword_handlers.py**: Keyword ability resolution (Flying, Trample, etc.)
- **mana_handlers.py**: Mana ability activation and mana pool management
- **triggered_ability_handlers.py**: Triggered ability resolution

## layer_system.py
This file implements the layer system for applying continuous effects in the correct order (layers 1-7):
- Applies effects in layer order (copy, control, text, type, color, ability, power/toughness)
- Hydrates static effects from permanents on battlefield
- Resets permanents to base characteristics before applying layers

## rulebook.py
This file contains the rulebook data structures and logic for MTG rules implementation.

## state_recorder.py
This file records `GameGraph` states to JSON for visualization. It handles:
- Creating timestamped session folders in `logs/history/`
- Saving full snapshots of entities and relationships
- Exporting a `latest.json` for live polling by the visualizer
- Mapping internal IDs to readable names for UI independence

## deck_generator.py
Intelligent deck construction for the Teacher.
- Supports 40-card (Limited) and 100-card (Commander) formats.
- Implements deterministic archetype selection (Life Gain, Ramp, etc.).
- Enforces Commander rules: Singleton and Color Identity.

## state_converter.py
The bridge between the Rule Engine and the Strategic Brain (AI).
- Converts `GameGraph` and Stack into comprehensive tensors/arrays.
- Encodes entity stats, keywords (bitmask), zones, and relative controller IDs.
- Robust handling of missing or `None` card properties.
- `torch`-agnostic: returns `numpy` arrays if `torch` is not installed.

## strategic_brain/action_mapper.py
- **Semantic Descriptor Mapping**: Converts Engine actions into feature-rich vectors (Type, Power, Toughness, CMC).
- **Pointer-Ready Logic**: Enables the model to choose actions by meaning rather than index.

## strategic_brain/model.py (Pro-Scale Architecture)
- **CardEmbedder**: Fuses Atomic Learned Embeddings with Component Fact-Vectors.
- **BoardEncoder**: 16-layer Relational Transformer for global game state.
- **OpponentPredictor**: Latent belief generator for hidden information.
- **System2ReasoningHead**: Dynamic recursive refinement of intent.
- **ActionPointerHead**: Matches Intent vectors to Action Descriptors using attention.

## strategic_brain/state_converter.py
- **Omni-Zone Visibility**: Maps Hand, Battlefield, Graveyard, and known Deck info into tensors.
- **32-dim Component Features**: Robust property extraction for generalization.

## main_train.py
The primary entry point for large-scale training.
- Orchestrates the generations of Teacher-led curriculum.
- Alternates between self-play training and benchmarking.
- Manages WandB logging and model checkpointing.

## rule_engine/target_filtering.py
Handles target filtering for spells and abilities, including target legality checks.
- Uses structured criteria (controller, type, status) for filtering.
- Integrated into `CastSpellAction` and `ActivatedAbilityHandler`.

## rule_engine/layer_system.py
Implements the 7-layer system for applying continuous effects in the correct order:
- 1: Copy, 2: Control, 3: Text, 4: Type, 5: Color, 6: Ability, 7: P/T.
- Recalculates state after any change to permanents or active effects.
