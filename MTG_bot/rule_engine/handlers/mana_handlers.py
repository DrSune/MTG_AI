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
        
        if battlefield_zone:
            card_on_battlefield_rels = graph.get_relationships(target=battlefield_zone, rel_type=id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))
            cards_on_battlefield = [graph.entities[r.source] for r in card_on_battlefield_rels]
            
            for card in cards_on_battlefield:
                if not card.properties.get('tapped'):
                    mana_abilities = card.properties.get("abilities", {}).get("mana_abilities", [])
                    for i, ability in enumerate(mana_abilities):
                        if ability.get("cost", {}).get("tap"):
                            legal_moves.append(ActivateManaAbilityAction(player_id=player.instance_id, card_id=card.instance_id, ability_id=i))
                            logger.debug(f"Found tappable land: {card.properties.get('name', card.type_id)} ({card.type_id})")
        logger.debug(f"Found {len(legal_moves)} tap for mana moves.")
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
                player.properties['mana_pool'][mana_type] += amount
            logger.info(f"Player {player.properties.get('name')} added {ability.get('produces')} mana. Mana pool: {player.properties['mana_pool']}")

    except Exception as e:
        logger.error(f"Error executing tap for mana for Player {player.properties.get('name', player.instance_id)[:4]}: {e}", exc_info=True)
        raise



