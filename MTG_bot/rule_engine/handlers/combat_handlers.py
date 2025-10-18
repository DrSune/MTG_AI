"""
This file will contain handlers related to the combat phase.
"""

from ..game_graph import GameGraph
from .. import vocabulary as vocab
from ..card_database import CREATURE_STATS
from MTG_bot.utils.logger import setup_logger

logger = setup_logger(__name__)

def get_legal_attackers(graph: GameGraph, player_id: str) -> list:
    """Determines which creatures a player can legally declare as attackers."""
    player = graph.entities[player_id]
    legal_attackers = []
    logger.debug(f"Getting legal attackers for Player {player.properties.get('name', player.instance_id)[:4]}.")
    try:
        # Find player's creatures on the battlefield
        p_control_rels = graph.get_relationships(source=player, rel_type=vocab.ID_REL_CONTROLS)
        battlefield_zone_entity = next((graph.entities[r.target] for r in p_control_rels if graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD), None)
        if not battlefield_zone_entity:
            logger.debug("No battlefield found for player, no legal attackers.")
            return []

        battlefield_cards = [graph.entities[r.source] for r in graph.get_relationships(target=battlefield_zone_entity, rel_type=vocab.ID_REL_IS_IN_ZONE)]
        
        creatures = [card for card in battlefield_cards if card.type_id in CREATURE_STATS.keys()]

        for creature in creatures:
            # Check for summoning sickness
            turn_entered = creature.properties.get('turn_entered', graph.turn_number)
            is_summoning_sick = turn_entered >= graph.turn_number

            if not creature.properties.get('tapped', False) and not is_summoning_sick:
                legal_attackers.append(creature)
                logger.debug(f"Found legal attacker: {creature.properties.get('name', creature.type_id)} ({creature.type_id})")
            else:
                logger.debug(f"Creature {creature.properties.get('name', creature.type_id)} ({creature.type_id}) cannot attack (tapped: {creature.properties.get('tapped', False)}, summoning sick: {is_summoning_sick}).")
                
        logger.debug(f"Total legal attackers found: {len(legal_attackers)}")
        return legal_attackers
    except Exception as e:
        logger.error(f"Error getting legal attackers for Player {player.properties.get('name', player.instance_id)[:4]}: {e}", exc_info=True)
        raise

def get_legal_blockers(graph: GameGraph, player_id: str) -> list:
    """Determines which creatures a player can legally declare as blockers."""
    player = graph.entities[player_id]
    legal_blockers = []
    logger.debug(f"Getting legal blockers for Player {player.properties.get('name', player.instance_id)[:4]}.")
    try:
        # Find player's creatures on the battlefield
        p_control_rels = graph.get_relationships(source=player, rel_type=vocab.ID_REL_CONTROLS)
        battlefield_zone_entity = next((graph.entities[r.target] for r in p_control_rels if graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD), None)
        if not battlefield_zone_entity:
            logger.debug("No battlefield found for player, no legal blockers.")
            return []

        battlefield_cards = [graph.entities[r.source] for r in graph.get_relationships(target=battlefield_zone_entity, rel_type=vocab.ID_REL_IS_IN_ZONE)]
        creatures = [card for card in battlefield_cards if card.type_id in CREATURE_STATS.keys()]

        for creature in creatures:
            if not creature.properties.get('tapped', False):
                legal_blockers.append(creature)
                logger.debug(f"Found legal blocker: {creature.properties.get('name', creature.type_id)} ({creature.type_id})")
            else:
                logger.debug(f"Creature {creature.properties.get('name', creature.type_id)} ({creature.type_id}) cannot block (tapped: {creature.properties.get('tapped', False)}).")

        logger.debug(f"Total legal blockers found: {len(legal_blockers)}")
        return legal_blockers
    except Exception as e:
        logger.error(f"Error getting legal blockers for Player {player.properties.get('name', player.instance_id)[:4]}: {e}", exc_info=True)
        raise

def declare_attacker(graph: GameGraph, attacker):
    """Declares a creature as an attacker, tapping it if it doesn't have vigilance."""
    logger.info(f"Declaring attacker: {attacker.properties.get('name', attacker.type_id)} ({attacker.type_id})")
    try:
        attacker_abilities = attacker.properties.get('abilities', [])
        if vocab.ID_ABILITY_VIGILANCE not in attacker_abilities:
            attacker.properties['tapped'] = True
            logger.debug(f"{attacker.properties.get('name')} tapped due to attacking (no vigilance).")
        else:
            logger.debug(f"{attacker.properties.get('name')} has vigilance, not tapped.")
    except Exception as e:
        logger.error(f"Error declaring attacker {attacker.properties.get('name', attacker.type_id)}: {e}", exc_info=True)
        raise

def assign_combat_damage(graph: GameGraph):
    """Assigns all combat damage from attackers to blockers and players."""
    logger.info("Assigning combat damage...")
    try:
        all_creatures = [c for c in graph.entities.values() if c.type_id in CREATURE_STATS.keys()]
        attacking_creatures = [c for c in all_creatures if c.properties.get('is_attacking', False)]
        defending_player = next((p for p in graph.entities.values() if p.type_id == vocab.ID_PLAYER and p.instance_id != graph.active_player_id), None)

        for attacker in attacking_creatures:
            blockers = [graph.entities[r.source] for r in graph.get_relationships(target=attacker, rel_type=vocab.ID_REL_IS_BLOCKING)]
            attacker_power = attacker.properties.get('effective_power', CREATURE_STATS[attacker.type_id]['power'])
            attacker_abilities = attacker.properties.get('abilities', [])
            attacker_controller = next((graph.entities[r.source] for r in graph.get_relationships(target=attacker, rel_type=vocab.ID_REL_CONTROLS)), None)

            if not blockers:
                # Unblocked: Deal damage to defending player
                if defending_player:
                    defending_player.properties['life_total'] -= attacker_power
                    logger.info(f"{attacker.properties.get('name', attacker.type_id)} ({attacker.type_id}) deals {attacker_power} damage to {defending_player.properties.get('name', defending_player.type_id)} ({defending_player.type_id}).")
                    if vocab.ID_ABILITY_LIFELINK in attacker_abilities and attacker_controller:
                        attacker_controller.properties['life_total'] += attacker_power
                        logger.info(f"{attacker.properties.get('name')} has Lifelink. {attacker_controller.properties.get('name')} gains {attacker_power} life. New life total: {attacker_controller.properties['life_total']}")
            else:
                # Blocked: Deal damage to blocker(s)
                # (Simplification: assumes one blocker)
                blocker = blockers[0]
                blocker_power = blocker.properties.get('effective_power', CREATURE_STATS[blocker.type_id]['power'])

                # Attacker deals damage to blocker
                blocker.properties['damage_taken'] = blocker.properties.get('damage_taken', 0) + attacker_power
                logger.info(f"{attacker.properties.get('name', attacker.type_id)} ({attacker.type_id}) deals {attacker_power} damage to {blocker.properties.get('name', blocker.type_id)} ({blocker.type_id}).")
                if vocab.ID_ABILITY_LIFELINK in attacker_abilities and attacker_controller:
                    attacker_controller.properties['life_total'] += attacker_power
                    logger.info(f"{attacker.properties.get('name')} has Lifelink. {attacker_controller.properties.get('name')} gains {attacker_power} life. New life total: {attacker_controller.properties['life_total']}")

                # Blocker deals damage to attacker
                attacker.properties['damage_taken'] = attacker.properties.get('damage_taken', 0) + blocker_power
                logger.info(f"{blocker.properties.get('name', blocker.type_id)} ({blocker.type_id}) deals {blocker_power} damage to {attacker.properties.get('name', attacker.type_id)} ({attacker.type_id}).")
    except Exception as e:
        logger.error(f"Error assigning combat damage: {e}", exc_info=True)
        raise