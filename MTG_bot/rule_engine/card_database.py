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

def get_card_abilities(card_id: int) -> Dict[str, Any]:
    """Returns a dictionary of abilities (keywords and mana abilities) for a given card ID."""
    card_data = card_data_loader.get_card_data_by_id(card_id)
    return card_data.get("abilities", {"keywords": [], "mana_abilities": []})