from typing import List, Optional, Union, Dict, Any
import numpy as np
from ..rule_engine.actions import (
    PlayLandAction,
    CastSpellAction,
    ActivateManaAbilityAction,
    DeclareAttackerAction,
    DeclareBlockerAction,
    PassPriorityAction,
    PassTurnAction,
)
from ..rule_engine.game_graph import GameGraph
from ..rule_engine import vocabulary as vocab

# Define constant IDs for action types
ACTION_TYPE_MAP = {
    PlayLandAction: 1,
    CastSpellAction: 2,
    ActivateManaAbilityAction: 3,
    DeclareAttackerAction: 4,
    DeclareBlockerAction: 5,
    PassPriorityAction: 6,
    PassTurnAction: 7,
}
ID_TO_ACTION_TYPE = {v: k for k, v in ACTION_TYPE_MAP.items()}

class ActionSpaceMapper:
    """
    Maps between rule_engine Action objects and semantic descriptors.
    Instead of an index, we provide a vector representing the move's 'Meaning'.
    """
    def __init__(self, vocab_size: int = 10000, component_dim: int = 32):
        self.vocab_size = vocab_size
        self.component_dim = component_dim

    def _safe_float(self, val) -> float:
        if val is None: return 0.0
        try: return float(val)
        except (ValueError, TypeError): return 0.0

    def get_action_descriptor(self, action: any, graph: GameGraph) -> Dict[str, any]:
        """
        Returns a semantic description of the action.
        [ActionType, SourceCardFeatures, TargetCardFeatures]
        """
        action_type = ACTION_TYPE_MAP.get(type(action), 0)
        
        # Source Entity Features
        source_id = getattr(action, "card_id", getattr(action, "blocker_id", None))
        source_features = np.zeros(self.component_dim)
        if source_id:
            entity = graph.entities.get(source_id)
            if entity:
                # Fill features: P, T, CMC, Tapped, Color, Type
                source_features[0] = self._safe_float(entity.properties.get("power", 0))
                source_features[1] = self._safe_float(entity.properties.get("toughness", 0))
                source_features[2] = self._safe_float(entity.properties.get("cmc", 0))
                source_features[3] = 1.0 if entity.properties.get("tapped") else 0.0
                # ... more features ...

        # Target Entity Features
        target_id = getattr(action, "target_id", getattr(action, "attacker_id", None))
        target_features = np.zeros(self.component_dim)
        if target_id:
            entity = graph.entities.get(target_id)
            if entity:
                target_features[0] = self._safe_float(entity.properties.get("power", 0))
                target_features[1] = self._safe_float(entity.properties.get("toughness", 0))

        return {
            "type": action_type,
            "source_features": source_features,
            "target_features": target_features
        }

    def tokens_to_action(self, tokens: List[int], graph: GameGraph) -> Optional[any]:
        """Converts a sequence of integer tokens back into an Action object."""
        if len(tokens) < 3:
            return None
            
        action_type_id = tokens[0]
        action_class = ID_TO_ACTION_TYPE.get(action_type_id)
        if not action_class:
            return None
            
        entities = self._get_sorted_entities(graph)
        active_player_id = graph.active_player_id
        
        def get_uuid(idx):
            if idx == 0 or idx > len(entities):
                return None
            return entities[idx - 1].instance_id
            
        source_uuid = get_uuid(tokens[1])
        target_uuid = get_uuid(tokens[2])
        
        if action_class == PlayLandAction and source_uuid:
            return PlayLandAction(player_id=active_player_id, card_id=source_uuid)
        elif action_class == CastSpellAction and source_uuid:
            return CastSpellAction(player_id=active_player_id, card_id=source_uuid, target_id=target_uuid)
        elif action_class == ActivateManaAbilityAction and source_uuid:
            return ActivateManaAbilityAction(player_id=active_player_id, card_id=source_uuid, ability_id=tokens[2])
        elif action_class == DeclareAttackerAction and source_uuid:
            return DeclareAttackerAction(player_id=active_player_id, card_id=source_uuid)
        elif action_class == DeclareBlockerAction and source_uuid and target_uuid:
            # Find the controller of the blocker
            blocker_entity = graph.entities.get(source_uuid)
            blocker_player_id = active_player_id # Fallback
            if blocker_entity:
                # Find "Controlled By" relationship: Blocker -> Player
                rels = graph.get_relationships(source=blocker_entity, rel_type=vocab.ID_REL_CONTROLLED_BY)
                if rels:
                    blocker_player_id = rels[0].target
            
            return DeclareBlockerAction(player_id=blocker_player_id, blocker_id=source_uuid, attacker_id=target_uuid)
        elif action_class == PassPriorityAction:
            return PassPriorityAction(player_id=active_player_id)
        elif action_class == PassTurnAction:
            return PassTurnAction(player_id=active_player_id)
            
        return None
