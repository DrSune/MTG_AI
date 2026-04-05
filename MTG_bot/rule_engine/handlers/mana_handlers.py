"""This file contains handlers related to mana abilities and the mana pool."""

from typing import List

from ..game_graph import GameGraph, Entity
from ..actions import ActivateManaAbilityAction
from .. import card_database
from MTG_bot.utils.logger import setup_logger
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config

logger = setup_logger(__name__)
id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)

def get_tap_for_mana_moves(graph: GameGraph, player: Entity) -> List[ActivateManaAbilityAction]:
    """Finds all legal 'Tap for Mana' moves for a given player."""
    legal_moves = []
    logger.debug(f"Getting tap for mana moves for Player {player.properties.get('name', player.instance_id)[:4]}.")
    try:
        control_rels = graph.get_relationships(source=player, rel_type=id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
        battlefield_zone = next((graph.entities[r.target] for r in control_rels if graph.entities[r.target].type_id == id_mapper.get_id_by_name("Battlefield", "game_vocabulary")), None)
        
        if not battlefield_zone:
            logger.debug(f"No battlefield zone found for player. Zones: {[graph.entities[r.target].type_id for r in control_rels]}")
            return []

        logger.debug(f"Battlefield Zone Type ID: {battlefield_zone.type_id}")
        target_zone_type_id = id_mapper.get_id_by_name("Is In Zone", "game_vocabulary")
        logger.debug(f"Is In Zone Type ID: {target_zone_type_id}")

        card_on_battlefield_rels = graph.get_relationships(target=battlefield_zone, rel_type=target_zone_type_id)
        cards_on_battlefield = [graph.entities[r.source] for r in card_on_battlefield_rels]
        
        logger.debug(f"Cards on battlefield count: {len(cards_on_battlefield)}")
        logger.debug(f"Cards on battlefield: {[c.properties.get('name') for c in cards_on_battlefield]}")

        for card in cards_on_battlefield:
            if not card.properties.get('tapped'):
                mana_abilities = card.properties.get("abilities", {}).get("mana_abilities", [])
                if not mana_abilities:
                    # FALLBACK: Detect colors from name if abilities are missing
                    name = card.properties.get('name', '')
                    if "Forest" in name:
                        mana_abilities = [{"type": "mana", "cost": {"tap": True}, "produces": {int(id_mapper.get_id_by_name("Green Mana", "game_vocabulary")): 1}}]
                    elif "Island" in name:
                        mana_abilities = [{"type": "mana", "cost": {"tap": True}, "produces": {int(id_mapper.get_id_by_name("Blue Mana", "game_vocabulary")): 1}}]
                    elif "Swamp" in name:
                        mana_abilities = [{"type": "mana", "cost": {"tap": True}, "produces": {int(id_mapper.get_id_by_name("Black Mana", "game_vocabulary")): 1}}]
                    elif "Mountain" in name:
                        mana_abilities = [{"type": "mana", "cost": {"tap": True}, "produces": {int(id_mapper.get_id_by_name("Red Mana", "game_vocabulary")): 1}}]
                    elif "Plains" in name:
                        mana_abilities = [{"type": "mana", "cost": {"tap": True}, "produces": {int(id_mapper.get_id_by_name("White Mana", "game_vocabulary")): 1}}]

                for i, ability in enumerate(mana_abilities):
                    if ability.get("cost", {}).get("tap"):
                        legal_moves.append(ActivateManaAbilityAction(player_id=player.instance_id, card_id=card.instance_id, ability_id=i))
                        logger.debug(f"Found tappable land: {card.properties.get('name', card.type_id)} ({card.type_id})")
        return legal_moves
    except Exception as e:
        logger.error(f"Error getting tap for mana moves for Player {player.properties.get('name', player.instance_id)[:4]}: {e}", exc_info=True)
        raise

def execute_tap_for_mana(graph: GameGraph, player: Entity, card: Entity, ability_id: int):
    """Executes the tap for mana action."""

    logger.info(f"Player {player.properties.get('name')} tapping {card.properties.get('name')}.")
    try:
        card.properties['tapped'] = True

        mana_abilities = card.properties.get("abilities", {}).get("mana_abilities", [])
        if ability_id < len(mana_abilities):
            ability = mana_abilities[ability_id]
            for mana_type, amount in ability.get("produces", {}).items():
                m_type = int(mana_type)
                m_amount = int(amount)
                # Ensure the mana pool is a dictionary
                if 'mana_pool' not in player.properties or not isinstance(player.properties['mana_pool'], dict):
                    player.properties['mana_pool'] = {}
                
                # Increment the mana amount, defaulting to 0 if the type doesn't exist
                player.properties['mana_pool'][m_type] = player.properties['mana_pool'].get(m_type, 0) + m_amount
            logger.info(f"Player {player.properties.get('name')} added {ability.get('produces')} mana. Mana pool: {player.properties['mana_pool']}")

    except Exception as e:
        logger.error(f"Error executing tap for mana for Player {player.properties.get('name', player.instance_id)[:4]}: {e}", exc_info=True)
        raise



