print("--- Executing card_database.py ---")
from typing import Dict, Any, List, Optional
from . import vocabulary as vocab
from .card_data_loader import CardDataLoader

# Initialize the CardDataLoader globally
card_data_loader = CardDataLoader()

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
        if vocab.ID_ABILITY_TAP_ADD_GREEN in card_data.get("abilities", []):
            return vocab.ID_MANA_GREEN
        if vocab.ID_ABILITY_TAP_ADD_BLUE in card_data.get("abilities", []):
            return vocab.ID_MANA_BLUE
        if vocab.ID_ABILITY_TAP_ADD_BLACK in card_data.get("abilities", []):
            return vocab.ID_MANA_BLACK
        if vocab.ID_ABILITY_TAP_ADD_RED in card_data.get("abilities", []):
            return vocab.ID_MANA_RED
        if vocab.ID_ABILITY_TAP_ADD_WHITE in card_data.get("abilities", []):
            return vocab.ID_MANA_WHITE
    return None

# This map remains as it's a direct mapping of ability IDs to mana types
MANA_ABILITY_MAP = {
    vocab.ID_ABILITY_TAP_ADD_GREEN: vocab.ID_MANA_GREEN,
    vocab.ID_ABILITY_TAP_ADD_BLUE: vocab.ID_MANA_BLUE,
    vocab.ID_ABILITY_TAP_ADD_BLACK: vocab.ID_MANA_BLACK,
    vocab.ID_ABILITY_TAP_ADD_RED: vocab.ID_MANA_RED,
    vocab.ID_ABILITY_TAP_ADD_WHITE: vocab.ID_MANA_WHITE,
}

# Expose the card data loader for direct access if needed (e.g., for card names)
get_card_name = card_data_loader.get_card_data_by_id
get_card_id_by_name = card_data_loader.get_card_id_by_name
get_all_card_ids = card_data_loader.get_all_card_ids