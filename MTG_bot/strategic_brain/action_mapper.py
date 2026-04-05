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
                # Use common feature extraction logic
                from .state_converter import StateConverter
                sc = StateConverter()
                source_features = sc._extract_features(entity)
                
                # Special handling for ActivateManaAbilityAction: encode produced mana
                if isinstance(action, ActivateManaAbilityAction):
                    # We have 32 dims. Let's use dims 20-26 for WUBRGC + Generic
                    abilities = entity.properties.get("abilities", {}).get("mana_abilities", [])
                    if action.ability_id < len(abilities):
                        produces = abilities[action.ability_id].get("produces", {})
                        # Mapping from vocab ID to index
                        mana_map = {
                            vocab.ID_MANA_WHITE: 20, vocab.ID_MANA_BLUE: 21,
                            vocab.ID_MANA_BLACK: 22, vocab.ID_MANA_RED: 23,
                            vocab.ID_MANA_GREEN: 24, vocab.ID_MANA_COLORLESS: 25,
                            vocab.ID_MANA_GENERIC: 26
                        }
                        for m_id, amt in produces.items():
                            idx = mana_map.get(m_id)
                            if idx: source_features[idx] = float(amt)

        # Target Entity Features
        target_id = getattr(action, "target_id", getattr(action, "attacker_id", None))
        target_features = np.zeros(self.component_dim)
        if target_id:
            entity = graph.entities.get(target_id)
            if entity:
                from .state_converter import StateConverter
                sc = StateConverter()
                target_features = sc._extract_features(entity)

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

    def action_to_tokens(self, action: any, graph: GameGraph) -> List[int]:
        """Converts an Action object into a sequence of integer tokens."""
        action_type_id = ACTION_TYPE_MAP.get(type(action), 0)
        entities = self._get_sorted_entities(graph)
        
        def get_index(uuid_val):
            if uuid_val is None:
                return 0
            for i, entity in enumerate(entities):
                if entity.instance_id == uuid_val:
                    return i + 1
            return 0
            
        source_id = getattr(action, "card_id", getattr(action, "blocker_id", None))
        target_id = getattr(action, "target_id", getattr(action, "attacker_id", None))
        
        source_idx = get_index(source_id)
        
        # Special case for mana abilities: target_idx is the ability_id
        if isinstance(action, ActivateManaAbilityAction):
            target_idx = action.ability_id
        else:
            target_idx = get_index(target_id)
            
        return [action_type_id, source_idx, target_idx]

    def _get_sorted_entities(self, graph: GameGraph) -> List[Entity]:
        """Returns a stable, sorted list of all entities in the graph."""
        # This MUST match the sorting logic in StateConverter.convert_graph_to_tokens
        priority_entities = []
        for eid, entity in graph.entities.items():
            if entity.type_id in [vocab.ID_PLAYER, vocab.ID_ZONE_BATTLEFIELD, vocab.ID_ZONE_HAND, vocab.ID_ZONE_GRAVEYARD, vocab.ID_ZONE_LIBRARY]:
                priority_entities.append(entity)
        
        other_entities = [e for e in graph.entities.values() if e not in priority_entities]
        return priority_entities + other_entities
