from typing import List, Optional, Union
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
    Maps between rule_engine Action objects and discrete tokens for the neural network.
    Since entities have dynamic UUIDs, we map them to their positional index in the 
    GameGraph's entity list during a specific turn.
    
    A token sequence for an action is generally:
    [ACTION_TYPE_ID, SOURCE_ENTITY_INDEX, TARGET_ENTITY_INDEX]
    """
    
    def __init__(self, vocab_size: int = 10000):
        self.vocab_size = vocab_size

    def _get_sorted_entities(self, graph: GameGraph):
        """Returns a list of entities sorted by instance_id for stable indexing."""
        return sorted(graph.entities.values(), key=lambda e: str(e.instance_id))

    def action_to_tokens(self, action: any, graph: GameGraph) -> List[int]:
        """Converts an Action object to a list of integer tokens."""
        entities = self._get_sorted_entities(graph)
        
        # Helper to get index
        def get_idx(uuid_str):
            if not uuid_str:
                return 0
            for i, e in enumerate(entities):
                if e.instance_id == uuid_str:
                    return i + 1 # offset by 1, 0 is null/none
            return 0
            
        action_type_id = ACTION_TYPE_MAP.get(type(action), 0)
        tokens = [action_type_id, 0, 0]
        
        if isinstance(action, PlayLandAction):
            tokens[1] = get_idx(action.card_id)
        elif isinstance(action, CastSpellAction):
            tokens[1] = get_idx(action.card_id)
            tokens[2] = get_idx(action.target_id)
        elif isinstance(action, ActivateManaAbilityAction):
            tokens[1] = get_idx(action.card_id)
            tokens[2] = action.ability_id # raw integer, assume fits in vocab
        elif isinstance(action, DeclareAttackerAction):
            tokens[1] = get_idx(action.card_id)
        elif isinstance(action, DeclareBlockerAction):
            tokens[1] = get_idx(action.blocker_id)
            tokens[2] = get_idx(action.attacker_id)
            
        return tokens

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
