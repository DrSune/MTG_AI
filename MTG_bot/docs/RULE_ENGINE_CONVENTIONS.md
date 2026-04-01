# Rule Engine Conventions

This document outlines the conventions used in the MTG AI Rule Engine for consistency across the codebase.

## 1. Game Vocabulary & IDs

The `game_vocabulary` table in `mtg_bot.db` is the source of truth for all game-related constants.

### ID Ranges
- **0-9:** Core Entities (Player, Creature)
- **10-19:** Game Phases (Beginning Phase, Pre-Combat Main Phase, etc.)
- **20-39:** Game Steps (Untap Step, Declare Attackers Step, etc.)
- **200-299:** Status and Relationships (Controlled By, Tapped, Is In Zone)
- **300-310:** Mana Types (Green Mana, Generic Mana, etc.)
- **320-330:** Special Game Actions (Take Mulligan Action)
- **400-499:** **Keyword Abilities** (Flying, Vigilance, Lifelink, etc.)

### Keyword IDs
Current mapping:
- 400: Flying
- 401: Vigilance
- 402: Lifelink
- 403: Reach
- 404: First strike
- 405: Double strike
- 406: Deathtouch
- 407: Trample
- 408: Haste
- 409: Menace
- 410: Indestructible
- 411: Hexproof
- 412: Flash
- 413: Defender
- 414: Prowess
- 415: Scry
- 416: Mill
- 417: Equip
- 418: Fight
- 419: Enchant
- 420: Protection
- 421: Hexproof from
- 422: Battalion
- 423: Treasure

## 2. Phase & Step Validation

The `Engine.get_legal_moves` method is responsible for enforcing MTG timing rules.

### Timing Rules
- **PlayLandAction:** Only legal during the active player's Main Phases (Pre-Combat or Post-Combat) when no other land has been played this turn.
- **CastSpellAction (Non-Instant):** Creatures, Sorceries, Artifacts, etc., are only legal during the active player's Main Phases.
- **CastSpellAction (Instant):** Legal anytime the player has priority (currently anytime in `get_legal_moves`).
- **ActivateManaAbilityAction:** Legal anytime (as long as the source is untapped and not summoning sick if it's a creature, though basic lands are fine).
- **DeclareAttackerAction:** Only legal during the `Declare Attackers Step`.
- **DeclareBlockerAction:** Only legal during the `Declare Blockers Step`.

## 3. Entity Properties

Entities are hydrated from the `cards` table in `mtg_bot.db` and also have dynamic properties:
- `tapped` (bool): Defaults to `False`.
- `damage_taken` (int): Defaults to `0`.
- `is_attacking` (bool): Defaults to `False`.
- `has_summoning_sickness` (bool): Defaults to `True` when entering the battlefield.
- `abilities` (dict): Structure: `{"keywords": [id1, id2], "mana_abilities": [...]}`.
- `effects` (list): Structured effects from `effects_json` in the database, used for targeting and resolution.

## 4. Testing Conventions

- **Card Data:** Card data is loaded from `mtg_bot.db`. This database is the source of truth for card properties and structured effects.
- **Phase Progression:** Tests must explicitly progress the `Engine` to the correct phase before attempting actions (e.g., progress to `Pre-Combat Main Phase` before playing a land).
- **IDs:** Use `id_mapper.get_id_by_name(name, "game_vocabulary")` for vocabulary terms and `card_data_loader.get_card_id_by_name(name)` for cards.
- **Structured Effects:** Prefer testing cards with pre-parsed `effects_json` in the database for generalized logic verification.
