"""This file contains handlers related to mana abilities and the mana pool."""

from typing import List

from ..game_graph import GameGraph, Entity
from ..actions import ActivateManaAbilityAction
from ..card_database import get_land_mana_type, MANA_ABILITY_MAP
from MTG_bot.utils.logger import setup_logger
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config

logger = setup_logger(__name__)
id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)def get_tap_for_mana_moves(graph: GameGraph, player: Entity) -> List[ActivateManaAbilityAction]:
    """Finds all legal 'Tap for Mana' moves for a given player."""
    legal_moves = []
    logger.debug(f"Getting tap for mana moves for Player {player.properties.get('name', player.instance_id)[:4]}.")
    try:
        # Find player's battlefield
        control_rels = graph.get_relationships(source=player, rel_type=id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
        battlefield_zone = next((graph.entities[r.target] for r in control_rels if graph.entities[r.target].type_id == id_mapper.get_id_by_name("Battlefield", "game_vocabulary")), None)
        
        if battlefield_zone:
            card_on_battlefield_rels = graph.get_relationships(target=battlefield_zone, rel_type=id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))
            cards_on_battlefield = [graph.entities[r.source] for r in card_on_battlefield_rels]
            
            tappable_lands = [card for card in cards_on_battlefield if get_land_mana_type(card.type_id) is not None and not card.properties.get('tapped')]

            for land in tappable_lands:
                mana_type = get_land_mana_type(land.type_id)
                # For basic lands, the ability ID can be inferred from the mana type it produces
                if mana_type == id_mapper.get_id_by_name("Green Mana", "game_vocabulary"):
                    ability_id = id_mapper.get_id_by_name("Tap: Add Green Mana", "game_vocabulary")
                elif mana_type == id_mapper.get_id_by_name("Blue Mana", "game_vocabulary"):
                    ability_id = id_mapper.get_id_by_name("Tap: Add Blue Mana", "game_vocabulary")
                elif mana_type == id_mapper.get_id_by_name("Black Mana", "game_vocabulary"):
                    ability_id = id_mapper.get_id_by_name("Tap: Add Black Mana", "game_vocabulary")
                elif mana_type == id_mapper.get_id_by_name("Red Mana", "game_vocabulary"):
                    ability_id = id_mapper.get_id_by_name("Tap: Add Red Mana", "game_vocabulary")
                elif mana_type == id_mapper.get_id_by_name("White Mana", "game_vocabulary"):
                    ability_id = id_mapper.get_id_by_name("Tap: Add White Mana", "game_vocabulary")
                else:
                    ability_id = 0 # Fallback for unknown mana types

                legal_moves.append(ActivateManaAbilityAction(player_id=player.instance_id, card_id=land.instance_id, ability_id=ability_id))
                logger.debug(f"Found tappable land: {land.properties.get('name', land.type_id)} ({land.type_id})")
        logger.debug(f"Found {len(legal_moves)} tap for mana moves.")
        return legal_moves
    except Exception as e:
        logger.error(f"Error getting tap for mana moves for Player {player.properties.get('name', player.instance_id)[:4]}: {e}", exc_info=True)
        raise



def execute_tap_for_mana(graph: GameGraph, player: Entity, land_card: Entity):
    """Executes the tap for mana action."""

    logger.info(f"Player {player.properties.get('name')} tapping {land_card.properties.get('name')}.")
    try:
        # Mark the land as tapped
        land_card.properties['tapped'] = True

        # Add mana to player's mana pool
        mana_type = get_land_mana_type(land_card.type_id)
        player.properties['mana_pool'][mana_type] += 1
        logger.info(f"Player {player.properties.get('name')} added {mana_type} mana. Mana pool: {player.properties['mana_pool']}")

    except Exception as e:
        logger.error(f"Error executing tap for mana for Player {player.properties.get('name', player.instance_id)[:4]} and land {land_card.properties.get('name', land_card.type_id)}: {e}", exc_info=True)
        raise


