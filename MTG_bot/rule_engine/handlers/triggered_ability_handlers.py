"""
Contains handlers for triggered abilities ("When/Whenever/At").
"""

from ..game_graph import GameGraph

class TriggeredAbility:
    """Placeholder for a triggered ability waiting to go on the stack."""
    pass

def check_and_create_triggers(graph: GameGraph, game_event) -> list[TriggeredAbility]:
    """
    This is a core function of the engine. After any game event (e.g., a creature
    entering the battlefield, a player drawing a card), this function is called.
    It checks the entire graph for any abilities that should have triggered.
    """
    triggered_abilities = []
    # Example: if game_event is 'creature_enters_battlefield':
    # 1. Find all entities with a 'creature_enters_battlefield' trigger condition.
    # 2. For each one, check if the trigger's conditions are met.
    # 3. If so, create a TriggeredAbility object and add it to the list.
    
    return triggered_abilities
