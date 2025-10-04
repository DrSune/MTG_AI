"""
Contains handlers for activated abilities (of the form Cost: Effect).
"""

from ..game_graph import GameGraph, Entity
from typing import List

class ActivatedAbilityMove:
    """Placeholder for an activated ability move."""
    pass

def get_legal_activated_abilities(graph: GameGraph, entity: Entity) -> List[ActivatedAbilityMove]:
    """
    Checks a single entity to see if it has any activatable abilities
    that the player can currently afford.
    """
    # 1. Find all activated ability entities attached to the input entity.
    # 2. For each ability, parse its cost.
    # 3. Check if the active player can pay the cost (mana, tapping, sacrificing, etc.).
    # 4. If they can, create an ActivatedAbilityMove object.
    # 5. Return the list of possible ability activations for this entity.
    return []
