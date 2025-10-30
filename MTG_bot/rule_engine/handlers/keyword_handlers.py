"""
Contains handlers for simple, atomic keywords (mostly combat-related).
"""

from typing import List

from ..game_graph import GameGraph, Entity
from MTG_bot.utils.logger import setup_logger
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config

logger = setup_logger(__name__)
id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)

def can_be_blocked_by(graph: GameGraph, attacker: Entity, blocker: Entity) -> bool:
    """Determines if a proposed block is legal based on keyword abilities."""
    logger.debug(f"Checking if {blocker.properties.get('name', blocker.type_id)} ({blocker.type_id}) can block {attacker.properties.get('name', attacker.type_id)} ({attacker.type_id}).")
    try:
        attacker_abilities = attacker.properties.get('abilities', {}).get("keywords", [])
        blocker_abilities = blocker.properties.get('abilities', {}).get("keywords", [])

        # Flying Rule
        if id_mapper.get_id_by_name("Flying", "game_vocabulary") in attacker_abilities:
            if id_mapper.get_id_by_name("Flying", "game_vocabulary") not in blocker_abilities and id_mapper.get_id_by_name("Reach", "game_vocabulary") not in blocker_abilities:
                logger.debug(f"{attacker.properties.get('name')} has Flying, but {blocker.properties.get('name')} has neither Flying nor Reach. Block is illegal.")
                return False # Flying creature can't be blocked by non-flyer/non-reacher
            else:
                logger.debug(f"{attacker.properties.get('name')} has Flying, but {blocker.properties.get('name')} has Flying or Reach. Block is legal.")

        # ... other rules for things like Shadow, Landwalk, etc.

        logger.debug("Block is legal based on keyword abilities.")
        return True
    except Exception as e:
        logger.error(f"Error checking block legality between {attacker.properties.get('name', attacker.type_id)} and {blocker.properties.get('name', blocker.type_id)}: {e}", exc_info=True)
        raise

def modifies_damage_step(graph: GameGraph, creature: Entity) -> bool:
    """Checks if a creature deals damage in the first combat damage step."""
    logger.debug(f"Checking if {creature.properties.get('name', creature.type_id)} ({creature.type_id}) modifies damage step.")
    try:
        creature_abilities = creature.properties.get('abilities', {}).get("keywords", [])
        if id_mapper.get_id_by_name("First Strike", "game_vocabulary") in creature_abilities:
            logger.debug(f"{creature.properties.get('name')} has First Strike.")
            return True
        # ... logic for Double Strike
        return False
    except Exception as e:
        logger.error(f"Error checking damage step modification for {creature.properties.get('name', creature.type_id)}: {e}", exc_info=True)
        raise

def handle_vigilance(graph: GameGraph, creature: Entity):
    """Prevents a creature from tapping when it attacks."""
    # This logic will be handled by the combat handler. 
    # A creature with vigilance simply doesn't get a "tapped" relationship added when it's declared as an attacker.
    logger.debug(f"Handle vigilance called for {creature.properties.get('name', creature.type_id)}.")
    pass

def handle_lifelink(graph: GameGraph, creature: Entity, damage_dealt: int):
    """Causes the creature's controller to gain life equal to damage dealt."""
    # This would be called by the damage-dealing part of the engine.
    logger.debug(f"Handle lifelink called for {creature.properties.get('name', creature.type_id)} dealing {damage_dealt} damage.")
    pass