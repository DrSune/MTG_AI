"""
Contains generalized handlers for triggered abilities ("When/Whenever/At").
"""

import uuid
from typing import List, Dict, Any, Optional
from ..game_graph import GameGraph, Entity
from .. import vocabulary as vocab
from . import effect_handlers
from MTG_bot.utils.logger import setup_logger

logger = setup_logger(__name__)

def check_triggers(graph: GameGraph, event_type: str, source_entity: Optional[Entity] = None, zone_id: Optional[int] = None):
    """
    Generalized trigger checker. Handles zone transitions (BF, Grave, Hand, etc.)
    """
    for eid, entity in graph.entities.items():
        if not entity.properties.get('is_on_battlefield'):
            continue
            
        effects = entity.properties.get('effects', [])
        for effect in effects:
            if not isinstance(effect, dict): continue
            if effect.get('ability_type') != "triggered_ability":
                continue
                
            trigger_cond = effect.get('trigger_condition', '').lower()
            
            # --- GENERALIZED ZONE ENTRY ---
            if event_type == "enters_zone" and "enters the" in trigger_cond:
                zone_name = graph.id_mapper.get_name(zone_id, "game_vocabulary").lower() if zone_id else ""
                if zone_name in trigger_cond:
                    if "this" in trigger_cond and source_entity.instance_id != entity.instance_id: continue
                    _queue_trigger(graph, entity, effect)
                    continue

            # Check other conditions (cast, draw, steps)
            if _event_matches_condition(graph, event_type, trigger_cond, entity, source_entity):
                if _check_secondary_conditions(graph, entity, effect):
                    _queue_trigger(graph, entity, effect)

def _event_matches_condition(graph: GameGraph, event_type: str, cond: str, host: Entity, source: Optional[Entity]) -> bool:
    """Matches raw events to MTG text patterns like 'Whenever you cast a spell'."""
    if event_type == "cast_spell" and "cast" in cond:
        if "noncreature" in cond and source and source.properties.get('is_creature'): return False
        if "spell" in cond: return True
        
    if event_type == "enters_battlefield" and "enters the battlefield" in cond:
        if "this" in cond and source and source.instance_id != host.instance_id: return False
        return True
        
    if event_type == "draw_card" and "draw" in cond:
        return True
        
    if event_type == "beginning_of_step":
        # Handle "At the beginning of your upkeep" etc.
        # source would be the step ID here
        step_name = graph.id_mapper.get_name(source, "game_vocabulary").lower() if source else ""
        if step_name in cond:
            # Check 'your' upkeep
            if "your" in cond and graph.get_controller_id(host) != graph.active_player_id: return False
            return True
            
    return False

def _check_secondary_conditions(graph: GameGraph, host: Entity, effect: Dict[str, Any]) -> bool:
    """Checks for counts or state requirements (e.g., 'your second card each turn')."""
    cond = effect.get("secondary_condition")
    if not cond: return True
    
    controller = graph.get_controller(host)
    if not controller: return False
    
    if cond == "second_draw_this_turn":
        return controller.properties.get('cards_drawn_this_turn', 0) == 2
        
    if cond == "7_more_life_than_starting":
        starting = 40 if graph.properties.get('game_mode') == "Commander" else 20
        return controller.properties.get('life_total', 20) >= (starting + 7)
        
    return True

def _queue_trigger(graph: GameGraph, host: Entity, effect: Dict[str, Any]):
    """Actually puts the effect on the engine's stack."""
    from ..engine import StackItem # Local import to avoid circularity
    
    # In a generalized engine, the stack doesn't exist yet, we find it on the graph or pass it.
    # For our project, the Engine manages the stack. We'll return the items to be queued.
    # OR we use a global event bus. For now, we assume engine is accessible or we return list.
    logger.info(f"Trigger Queued: {host.properties.get('name')} -> {effect.get('trigger_condition')}")
    
    # We add to a temporary list on the graph that the engine will sweep
    if not hasattr(graph, 'queued_triggers'): graph.queued_triggers = []
    
    for sub_eff in effect.get('effects', []):
        graph.queued_triggers.append({
            "source_id": host.instance_id,
            "controller_id": graph.get_controller_id(host),
            "effect_data": {"ability_type": "triggered_ability_instance", "effect": sub_eff}
        })
