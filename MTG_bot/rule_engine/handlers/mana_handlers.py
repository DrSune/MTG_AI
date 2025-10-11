"""
This file will contain handlers related to mana abilities and mana costs.
"""

from ..game_graph import GameGraph
from .. import vocabulary as vocab

def can_pay_cost(graph: GameGraph, player_id: str, cost: dict) -> bool:
    """Checks if a player can pay a given mana cost."""
    player = graph.entities[player_id]
    pool = player.properties.get('mana_pool', {}).copy()

    # Pay colored costs first
    for mana_type, required in cost.items():
        if mana_type == 'generic':
            continue
        if pool.get(mana_type, 0) < required:
            return False
        pool[mana_type] -= required

    # Check if remaining pool can cover generic costs
    generic_cost = cost.get('generic', 0)
    if sum(pool.values()) < generic_cost:
        return False

    return True

def pay_cost(graph: GameGraph, player_id: str, cost: dict):
    """Deducts a mana cost from a player's available mana."""
    player = graph.entities[player_id]
    mana_pool = player.properties['mana_pool']
    
    print(f"Player {str(player_id)[:4]} attempting to pay cost {cost} with pool {mana_pool}")

    # Pay colored costs first
    for mana_type, required in cost.items():
        if mana_type != 'generic':
            mana_pool[mana_type] -= required

    # Pay generic costs with remaining mana
    generic_cost = cost.get('generic', 0)
    if generic_cost > 0:
        # Iterate through all mana types to spend them
        for mana_type in [vocab.ID_MANA_GREEN, vocab.ID_MANA_BLUE, vocab.ID_MANA_BLACK, vocab.ID_MANA_RED, vocab.ID_MANA_WHITE, vocab.ID_MANA_COLORLESS]:
            if generic_cost == 0:
                break
            
            available = mana_pool.get(mana_type, 0)
            payable = min(generic_cost, available)
            mana_pool[mana_type] -= payable
            generic_cost -= payable

    print(f"Player {str(player_id)[:4]} new mana pool: {mana_pool}")