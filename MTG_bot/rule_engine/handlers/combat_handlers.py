"""
This file will contain handlers related to the combat phase.
"""

from ..game_graph import GameGraph
from .. import vocabulary as vocab
from ..card_database import CREATURE_STATS

def get_legal_attackers(graph: GameGraph, player_id: str) -> list:
    """Determines which creatures a player can legally declare as attackers."""
    player = graph.entities[player_id]
    legal_attackers = []

    # Find player's creatures on the battlefield
    p_control_rels = graph.get_relationships(source=player, rel_type=vocab.ID_REL_CONTROLS)
    battlefield_zone_entity = next((graph.entities[r.target] for r in p_control_rels if graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD), None)
    if not battlefield_zone_entity:
        return []

    battlefield_cards = [graph.entities[r.source] for r in graph.get_relationships(target=battlefield_zone_entity, rel_type=vocab.ID_REL_IS_IN_ZONE)]
    
    creatures = [card for card in battlefield_cards if card.type_id in CREATURE_STATS.keys()]

    for creature in creatures:
        # Check for summoning sickness
        turn_entered = creature.properties.get('turn_entered', graph.turn_number)
        is_summoning_sick = turn_entered >= graph.turn_number

        if not creature.properties.get('tapped', False) and not is_summoning_sick:
            legal_attackers.append(creature)
            
    return legal_attackers

def get_legal_blockers(graph: GameGraph, player_id: str) -> list:
    """Determines which creatures a player can legally declare as blockers."""
    player = graph.entities[player_id]
    legal_blockers = []

    # Find player's creatures on the battlefield
    p_control_rels = graph.get_relationships(source=player, rel_type=vocab.ID_REL_CONTROLS)
    battlefield_zone_entity = next((graph.entities[r.target] for r in p_control_rels if graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD), None)
    if not battlefield_zone_entity:
        return []

    battlefield_cards = [graph.entities[r.source] for r in graph.get_relationships(target=battlefield_zone_entity, rel_type=vocab.ID_REL_IS_IN_ZONE)]
    creatures = [card for card in battlefield_cards if card.type_id in CREATURE_STATS.keys()]

    for creature in creatures:
        if not creature.properties.get('tapped', False):
            legal_blockers.append(creature)

    return legal_blockers

def assign_combat_damage(graph: GameGraph):
    """Assigns all combat damage from attackers to blockers and players."""
    print("Assigning combat damage...")
    all_creatures = [c for c in graph.entities.values() if c.type_id in CREATURE_STATS.keys()]
    attacking_creatures = [c for c in all_creatures if c.properties.get('is_attacking', False)]
    defending_player = next((p for p in graph.entities.values() if p.type_id == vocab.ID_PLAYER and p.instance_id != graph.active_player_id), None)

    for attacker in attacking_creatures:
        blockers = [graph.entities[r.source] for r in graph.get_relationships(target=attacker, rel_type=vocab.ID_REL_IS_BLOCKING)]
        attacker_power = attacker.properties.get('effective_power', CREATURE_STATS[attacker.type_id]['power'])

        if not blockers:
            # Unblocked: Deal damage to defending player
            if defending_player:
                defending_player.properties['life_total'] -= attacker_power
                print(f"{attacker.type_id} deals {attacker_power} damage to Player {str(defending_player.instance_id)[:4]}.")
        else:
            # Blocked: Deal damage to blocker(s)
            # (Simplification: assumes one blocker)
            blocker = blockers[0]
            blocker_power = blocker.properties.get('effective_power', CREATURE_STATS[blocker.type_id]['power'])

            # Attacker deals damage to blocker
            blocker.properties['damage_taken'] = blocker.properties.get('damage_taken', 0) + attacker_power
            print(f"{attacker.type_id} deals {attacker_power} damage to {blocker.type_id}.")

            # Blocker deals damage to attacker
            attacker.properties['damage_taken'] = attacker.properties.get('damage_taken', 0) + blocker_power
            print(f"{blocker.type_id} deals {blocker_power} damage to {attacker.type_id}.")