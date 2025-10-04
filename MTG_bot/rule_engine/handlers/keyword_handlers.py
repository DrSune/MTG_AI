"""
Contains handlers for simple, atomic keywords (mostly combat-related).
"""

from ..game_graph import GameGraph, Entity

# Vocabulary IDs would be defined centrally
ID_ABILITY_FLYING = 5001
ID_ABILITY_REACH = 5002
ID_ABILITY_FIRST_STRIKE = 5003

def can_be_blocked_by(graph: GameGraph, attacker: Entity, blocker: Entity) -> bool:
    """Determines if a proposed block is legal based on keyword abilities."""
    attacker_abilities = [] # graph.get_abilities_of(attacker)
    blocker_abilities = [] # graph.get_abilities_of(blocker)

    # Flying Rule
    if ID_ABILITY_FLYING in attacker_abilities:
        if ID_ABILITY_FLYING not in blocker_abilities and ID_ABILITY_REACH not in blocker_abilities:
            return False # Flying creature can't be blocked by non-flyer/non-reacher

    # ... other rules for things like Shadow, Landwalk, etc.

    return True

def modifies_damage_step(graph: GameGraph, creature: Entity) -> bool:
    """Checks if a creature deals damage in the first combat damage step."""
    creature_abilities = [] # graph.get_abilities_of(creature)
    if ID_ABILITY_FIRST_STRIKE in creature_abilities:
        return True
    # ... logic for Double Strike
    return False