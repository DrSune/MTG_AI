"""
Contains handlers for mechanics that operate from the graveyard.
"""

from ..game_graph import GameGraph
from typing import List

class Move:
    """Placeholder for a move object."""
    pass

def get_flashback_moves(graph: GameGraph) -> List[Move]:
    """
    Checks the active player's graveyard for cards with Flashback and determines
    if they can be cast.
    """
    # 1. Get cards in active player's graveyard.
    # 2. For each card, check if it has the Flashback ability entity attached.
    # 3. If so, check if the player can pay the flashback cost.
    # 4. If they can, create a CastSpellFromGraveyard move object.
    # 5. Return the list of possible flashback moves.
    return []

def get_unearth_moves(graph: GameGraph) -> List[Move]:
    """
    Checks for creatures with Unearth in the graveyard.
    """
    return []
