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

    def matches(self, graph: GameGraph, source_player: Entity, target: Entity) -> bool:
        if self.criteria == "any":
            return target.type_id == vocab.ID_PLAYER or target.properties.get("is_creature", False)
        
        if self.criteria == "player":
            return target.type_id == vocab.ID_PLAYER
            
        if self.criteria == "creature":
            return target.properties.get("is_creature", False)

        if isinstance(self.criteria, dict):
            # Type matching
            req_type = self.criteria.get("type")
            if req_type == "creature" and not target.properties.get("is_creature", False):
                return False
            if req_type == "player" and target.type_id != vocab.ID_PLAYER:
                return False
            if req_type == "permanent":
                # Simplification: Lands and Creatures are permanents
                is_perm = target.properties.get("is_creature") or target.properties.get("is_land")
                if not is_perm: return False
                
            # Status matching
            if self.criteria.get("is_tapped") is True and not target.properties.get("tapped", False):
                return False
            if self.criteria.get("is_tapped") is False and target.properties.get("tapped", False):
                return False
                
            # Controller matching
            req_controller = self.criteria.get("controller")
            if req_controller:
                target_controller_id = graph.get_controller_id(target)
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

def get_valid_targets(graph: GameGraph, source_player: Entity, criteria: Any) -> List[Entity]:
    """
    Returns all entities in the graph that match the given criteria.
    """
    filter_obj = TargetFilter(criteria)
    valid_targets = []
    
    # Check all entities
    for entity in graph.entities.values():
        # Only check things that CAN be targets (Players and Battlefield permanents for now)
        is_player = entity.type_id == vocab.ID_PLAYER
        
        is_on_battlefield = False
        if not is_player:
            # Check if it's in a battlefield zone
            zone_rels = graph.get_relationships(source=entity, rel_type=vocab.ID_REL_IS_IN_ZONE)
            for rel in zone_rels:
                zone = graph.entities.get(rel.target)
                if zone and zone.type_id == vocab.ID_ZONE_BATTLEFIELD:
                    is_on_battlefield = True
                    break
        
        if is_player or is_on_battlefield:
            if filter_obj.matches(graph, source_player, entity):
                valid_targets.append(entity)
                
    return valid_targets
