"""
This module provides access to core game constants and IDs.
It dynamically fetches IDs from the database to ensure consistency.
"""
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config

_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)

def get_id(name: str) -> int:
    return _mapper.get_id_by_name(name, "game_vocabulary")

# --- Common Entity Types ---
ID_PLAYER = get_id("Player")
ID_CREATURE = get_id("Creature")
ID_LAND = get_id("Land")
ID_INSTANT = get_id("Instant")
ID_SORCERY = get_id("Sorcery")

# --- Common Zones ---
ID_ZONE_HAND = get_id("Hand")
ID_ZONE_BATTLEFIELD = get_id("Battlefield")
ID_ZONE_LIBRARY = get_id("Library")
ID_ZONE_GRAVEYARD = get_id("Graveyard")
ID_ZONE_EXILE = get_id("Exile")
ID_ZONE_COMMAND = get_id("Command Zone")
ID_ZONE_STACK = get_id("Stack")

# --- Common Relationships ---
ID_REL_CONTROLLED_BY = get_id("Controlled By")
ID_REL_IS_IN_ZONE = get_id("Is In Zone")

# --- Mana Types ---
ID_MANA_GREEN = get_id("Green Mana")
ID_MANA_BLUE = get_id("Blue Mana")
ID_MANA_BLACK = get_id("Black Mana")
ID_MANA_RED = get_id("Red Mana")
ID_MANA_WHITE = get_id("White Mana")
ID_MANA_COLORLESS = get_id("Colorless Mana")
ID_MANA_GENERIC = get_id("Generic Mana")

# --- Phases ---
ID_PHASE_BEGINNING = get_id("Beginning Phase")
ID_PHASE_MAIN1 = get_id("Pre-Combat Main Phase")
ID_PHASE_COMBAT = get_id("Combat Phase")
ID_PHASE_MAIN2 = get_id("Post-Combat Main Phase")
ID_PHASE_ENDING = get_id("Ending Phase")

# --- Steps ---
ID_STEP_UNTAP = get_id("Untap Step")
ID_STEP_UPKEEP = get_id("Upkeep Step")
ID_STEP_DRAW = get_id("Draw Step")
ID_STEP_DECLARE_ATTACKERS = get_id("Declare Attackers Step")
ID_STEP_DECLARE_BLOCKERS = get_id("Declare Blockers Step")
