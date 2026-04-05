import uuid
from typing import List, Dict, Any, Optional
from .game_graph import GameGraph, Entity
from . import vocabulary as vocab
from MTG_bot.utils.logger import setup_logger

logger = setup_logger(__name__)

class TargetFilter:
    """
    Evaluates if a given entity matches a set of criteria.
    Criteria can be a simple string (e.g., "any", "player", "creature")
    or a complex dictionary.
    """
    def __init__(self, criteria: Any):
        self.criteria = criteria

    def matches(self, graph: GameGraph, source_player: Entity, target: Entity, source_card: Optional[Entity] = None) -> bool:
        if self.criteria == "any":
            return target.type_id == vocab.ID_PLAYER or target.properties.get("is_creature", False)
        
        if self.criteria == "player":
            return target.type_id == vocab.ID_PLAYER
            
        if self.criteria == "creature":
            return target.properties.get("is_creature", False)

        if isinstance(self.criteria, dict):
            # ...
            # Controller matching
            req_controller = self.criteria.get("controller")
            target_controller_id = graph.get_controller_id(target)
            
            # --- HEXPROOF ENFORCEMENT ---
            if target.properties.get("hexproof") and target_controller_id != source_player.instance_id:
                return False

            # --- PROTECTION ENFORCEMENT ---
            protections = target.properties.get("protections_from_names", [])
            if "protection_from_name" in target.properties:
                protections.append(target.properties["protection_from_name"])
            
            if protections and source_card:
                source_name = source_card.properties.get("name")
                if source_name in protections:
                    return False

            if req_controller:
                if req_controller == "opponent":
                    if target_controller_id == source_player.instance_id:
                        return False
                    if target.type_id == vocab.ID_PLAYER and target.instance_id == source_player.instance_id:
                        return False
                elif req_controller == "self":
                    if target_controller_id != source_player.instance_id:
                        return False
                    if target.type_id == vocab.ID_PLAYER and target.instance_id != source_player.instance_id:
                        return False

            # Color matching (placeholder)
            # req_color = self.criteria.get("color")
            
            return True

        return False

def get_valid_targets(graph: GameGraph, source_player: Entity, criteria: Any, source_card: Optional[Entity] = None) -> List[Entity]:
    """
    Returns all entities in the graph that match the given criteria.
    """
    filter_obj = TargetFilter(criteria)
    valid_targets = []
    
    # Check all entities
    for entity in graph.entities.values():
        is_player = entity.type_id == vocab.ID_PLAYER
        is_on_battlefield = entity.properties.get("is_on_battlefield", False)
        
        if is_player or is_on_battlefield:
            if filter_obj.matches(graph, source_player, entity, source_card):
                valid_targets.append(entity)
                
    return valid_targets
