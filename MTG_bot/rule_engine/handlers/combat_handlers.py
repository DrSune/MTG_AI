"""
Contains handlers that orchestrate the phases of combat.
"""

from ..game_graph import GameGraph, Entity
from typing import List

def get_legal_attackers(graph: GameGraph) -> List[Entity]:
    """
    Determines which creatures controlled by the active player can legally attack.
    Checks for summoning sickness (and Haste), tapped status, and effects that
    prevent attacking (e.g., Pacifism).
    """
    # 1. Get active player's creatures from the graph.
    # 2. For each creature, check its properties ('is_tapped').
    # 3. Check for summoning sickness and the Haste ability.
    # 4. Check for relationships to entities that prevent attacking.
    # 5. Return a list of valid attacker entities.
    return []

def get_legal_blockers(graph: GameGraph, attacker: Entity) -> List[Entity]:
    """
    For a given attacker, determines which of the opponent's creatures can legally block.
    """
    # 1. Get defending player's creatures.
    # 2. For each creature, check if it's tapped or has effects preventing blocking.
    # 3. Crucially, calls out to other handlers to check for evasion, e.g.:
    #    can_block = keyword_handlers.can_be_blocked_by(graph, attacker, potential_blocker)
    # 4. Return a list of valid blocker entities.
    return []
