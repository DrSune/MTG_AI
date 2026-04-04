"""
A catch-all file for handlers of truly unique and complex card effects
that do not fit into a generalizable pattern.
"""

from ..game_graph import GameGraph, Entity
from .. import vocabulary as vocab
from MTG_bot.utils.logger import setup_logger

logger = setup_logger(__name__)

def handle_runed_halo_choice(graph: GameGraph, halo_entity: Entity):
    """
    Handles the 'As Runed Halo enters the battlefield, choose a card name' choice.
    For simplicity in foundation training, we pick a relevant threat if possible,
    or a default if not.
    """
    # In a real scenario, this would be an AI decision. 
    # For now, we look at the opponent's graveyard or just name a common threat.
    chosen_name = "Shock" # Default for M21 foundation
    
    # Set the property on the halo itself
    halo_entity.properties['named_card'] = chosen_name
    
    # Also set protection on the controller
    controller = graph.get_controller(halo_entity)
    if controller:
        # We use a list to support multiple Runed Halos
        protections = controller.properties.get('protections_from_names', [])
        if chosen_name not in protections:
            protections.append(chosen_name)
        controller.properties['protections_from_names'] = protections
        logger.info(f"Runed Halo naming {chosen_name}. {controller.properties.get('name')} now has protection.")

def handle_nine_lives_prevention(graph: GameGraph, player: Entity, amount: int) -> bool:
    """
    Handles Nine Lives replacement effect:
    'If damage would be dealt to you, prevent that damage and put a reincarnation counter on Nine Lives.'
    Returns True if damage was prevented.
    """
    # Find Nine Lives controlled by this player on the battlefield
    nine_lives_id = 0 # We need to find the ID or use name
    
    for eid, e in graph.entities.items():
        if e.properties.get('name') == "Nine Lives" and e.properties.get('is_on_battlefield'):
            if graph.get_controller_id(e) == player.instance_id:
                # Prevent damage
                # Add counter
                counters = e.properties.get('reincarnation_counters', 0)
                e.properties['reincarnation_counters'] = counters + 1
                logger.info(f"Nine Lives prevented {amount} damage. Now has {counters + 1} counters.")
                return True
    return False

def handle_generalized_enters_choice(graph: GameGraph, source: Entity):
    """
    Generalized hook for 'As [this] enters the battlefield, choose...'
    Cards specify their choice type in properties (e.g., 'choose_card_name', 'choose_color').
    """
    choice_type = source.properties.get('as_enters_choice_type')
    
    if choice_type == "card_name":
        # Reuse Runed Halo logic but make it card-agnostic
        handle_runed_halo_choice(graph, source)
    elif choice_type == "color":
        source.properties['chosen_color'] = "White" # Default for now
        logger.info(f"{source.properties.get('name')} chose White.")

def handle_nine_lives_loss(graph: GameGraph, nine_lives_entity: Entity):
    """
    Handles Nine Lives leaves-battlefield trigger:
    'When Nine Lives leaves the battlefield, you lose the game.'
    """
    controller = graph.get_controller(nine_lives_entity)
    if controller:
        logger.info(f"Nine Lives left the battlefield! {controller.properties.get('name')} loses the game.")
        # Trigger SBA loss
        controller.properties['life_total'] = 0
