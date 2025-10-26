from typing import Dict, Any, List, Optional
from MTG_bot import config
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from .card_data_loader import CardDataLoader

# Initialize the CardDataLoader globally
card_data_loader = CardDataLoader()
id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)

def get_card_cost(card_id: int) -> Dict[int, int]:
    """Returns the mana cost for a given card ID."""
    card_data = card_data_loader.get_card_data_by_id(card_id)
    return card_data.get("mana_cost", {})

def get_creature_stats(card_id: int) -> Dict[str, int]:
    """Returns the power and toughness for a given creature card ID."""
    card_data = card_data_loader.get_card_data_by_id(card_id)
    power = card_data.get("power")
    toughness = card_data.get("toughness")
    if power is not None and toughness is not None:
        return {"power": power, "toughness": toughness}
    return {}

def get_card_abilities(card_id: int) -> List[int]:
    """Returns a list of ability IDs for a given card ID."""
    card_data = card_data_loader.get_card_data_by_id(card_id)
    return card_data.get("abilities", [])

def get_land_mana_type(card_id: int) -> Optional[int]:
    """Returns the mana type a land produces, if any."""
    card_data = card_data_loader.get_card_data_by_id(card_id)
    # This is a simplified mapping. A real implementation would check for specific mana abilities.
    if card_data.get("is_land"):
        if id_mapper.get_id_by_name("Tap: Add Green Mana", "game_vocabulary") in card_data.get("abilities", []):
            return id_mapper.get_id_by_name("Green Mana", "game_vocabulary")
        if id_mapper.get_id_by_name("Tap: Add Blue Mana", "game_vocabulary") in card_data.get("abilities", []):
            return id_mapper.get_id_by_name("Blue Mana", "game_vocabulary")
        if id_mapper.get_id_by_name("Tap: Add Black Mana", "game_vocabulary") in card_data.get("abilities", []):
            return id_mapper.get_id_by_name("Black Mana", "game_vocabulary")
        if id_mapper.get_id_by_name("Tap: Add Red Mana", "game_vocabulary") in card_data.get("abilities", []):
            return id_mapper.get_id_by_name("Red Mana", "game_vocabulary")
        if id_mapper.get_id_by_name("Tap: Add White Mana", "game_vocabulary") in card_data.get("abilities", []):
            return id_mapper.get_id_by_name("White Mana", "game_vocabulary")
    return None

# This map remains as it's a direct mapping of ability IDs to mana types
MANA_ABILITY_MAP = {
    id_mapper.get_id_by_name("Tap: Add Green Mana", "game_vocabulary"): id_mapper.get_id_by_name("Green Mana", "game_vocabulary"),
    id_mapper.get_id_by_name("Tap: Add Blue Mana", "game_vocabulary"): id_mapper.get_id_by_name("Blue Mana", "game_vocabulary"),
    id_mapper.get_id_by_name("Tap: Add Black Mana", "game_vocabulary"): id_mapper.get_id_by_name("Black Mana", "game_vocabulary"),
    id_mapper.get_id_by_name("Tap: Add Red Mana", "game_vocabulary"): id_mapper.get_id_by_name("Red Mana", "game_vocabulary"),
    id_mapper.get_id_by_name("Tap: Add White Mana", "game_vocabulary"): id_mapper.get_id_by_name("White Mana", "game_vocabulary"),
}