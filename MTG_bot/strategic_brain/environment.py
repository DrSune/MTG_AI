import uuid
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from ..rule_engine.game_graph import GameGraph
from ..rule_engine.engine import Engine
from ..rule_engine import vocabulary as vocab
from ..rule_engine.game_initializer import initialize_game_state
from .state_converter import StateConverter
from .action_mapper import ActionSpaceMapper
from .deck_generator import DeckGenerator, Archetypes
from ..rule_engine.actions import PassPriorityAction, CastSpellAction, PlayLandAction
from MTG_bot.rule_engine.card_data_loader import CardDataLoader
from MTG_bot.utils.logger import setup_logger
from MTG_bot import config

logger = setup_logger(__name__)

class MTGEnv:
    """
    A Gym-like environment for the MTG AI.
    Wraps the Rule Engine, State Converter, and Action Mapper.
    """
    def __init__(self, card_loader: CardDataLoader):
        self.card_loader = card_loader
        self.deck_gen = DeckGenerator()
        self.converter = StateConverter()
        self.mapper = ActionSpaceMapper()
        
        self.engine: Optional[Engine] = None
        self.graph: Optional[GameGraph] = None
        self.game_over = False

    def reset(self, format: str = "limited", archetypes: Tuple[str, str] = ("random", "random")) -> Tuple[Dict[str, Any], List[int], List[int]]:
        """Resets the environment with a new game and matchup."""
        if format == "limited":
            decks = self.deck_gen.generate_constructed_matchup(format_name="Limited", archetypes=list(archetypes))
            mode_name = "Limited"
        else:
            decks = self.deck_gen.generate_constructed_matchup(format_name="Commander", archetypes=list(archetypes))
            mode_name = "Commander"
            
        self.graph = initialize_game_state(decks[0], decks[1], game_mode=mode_name)
        self.engine = Engine(self.graph)
        self.game_over = False
        
        return self._get_obs(), decks[0], decks[1]

    def reset_with_decks(self, deck_a: List[int], deck_b: List[int], mode: str = "Standard") -> Tuple[Dict[str, Any], List[int], List[int]]:
        """Resets the environment using provided decklists."""
        self.graph = initialize_game_state(deck_a, deck_b, game_mode=mode)
        self.engine = Engine(self.graph)
        self.game_over = False
        return self._get_obs(), deck_a, deck_b

    def _resolve_name(self, instance_id: uuid.UUID) -> str:
        if not instance_id: return "None"
        entity = self.graph.entities.get(instance_id)
        if not entity: return "Unknown"
        return entity.properties.get('name', str(instance_id)[:4])

    def _format_plan(self, plan_sequence: List[Dict[str, Any]]) -> str:
        """Converts a sequence of action logits into a readable plan string."""
        if not plan_sequence: return "None"
        
        # Get sorted entities for indexing (matches ActionSpaceMapper logic)
        priority_entities = []
        for eid, entity in self.graph.entities.items():
            if entity.type_id in [vocab.ID_PLAYER, vocab.ID_ZONE_BATTLEFIELD, vocab.ID_ZONE_HAND, vocab.ID_ZONE_GRAVEYARD, vocab.ID_ZONE_LIBRARY]:
                priority_entities.append(entity)
        other_entities = [e for e in self.graph.entities.values() if e not in priority_entities]
        all_entities = priority_entities + other_entities

        plan_steps = []
        from .action_mapper import ID_TO_ACTION_TYPE
        
        for step in plan_sequence:
            # step: {"type_logits": (1, 10), "source_logits": (1, 500), "target_logits": (1, 500)}
            type_id = torch.argmax(step["type_logits"], dim=-1).item()
            action_class = ID_TO_ACTION_TYPE.get(type_id)
            if not action_class or type_id == 0: continue # Skip null/unknown actions
            
            action_name = action_class.__name__.replace("Action", "")
            
            # Pointing: Get most probable source and target indices
            source_idx = torch.argmax(step["source_logits"], dim=-1).item()
            target_idx = torch.argmax(step["target_logits"], dim=-1).item()
            
            source_name = "None"
            if source_idx < len(all_entities):
                source_name = self._resolve_name(all_entities[source_idx].instance_id)
                
            target_name = "None"
            if target_idx < len(all_entities):
                target_name = self._resolve_name(all_entities[target_idx].instance_id)
                
            if target_name != "None" and action_name in ["CastSpell", "DeclareBlocker"]:
                plan_steps.append(f"{action_name}({source_name} -> {target_name})")
            else:
                plan_steps.append(f"{action_name}({source_name})")
                
        return " -> ".join(plan_steps[:3]) # Show first 3 steps of plan

    def step(self, action_idx: int) -> Tuple[Dict[str, Any], float, bool, Dict[str, Any]]:
        """
        Executes an action from the model using its index in the legal moves list.
        Returns (obs, reward, done, info)
        """
        if self.game_over:
            return self._get_obs(), 0.0, True, {}

        penalty = 0.0
        # Track state before action for impact calculation
        p1_id = self.graph.players[0]
        p2_id = self.graph.players[1]
        
        pre_p1_life = self.graph.entities[p1_id].properties.get('life_total', 20)
        pre_p2_life = self.graph.entities[p2_id].properties.get('life_total', 20)
        
        pre_p1_perm = len(self.graph.get_entities_in_zone(p1_id, vocab.ID_ZONE_BATTLEFIELD)) if hasattr(vocab, "ID_ZONE_BATTLEFIELD") else 0
        pre_p1_hand = len(self.graph.get_entities_in_zone(p1_id, vocab.ID_ZONE_HAND)) if hasattr(vocab, "ID_ZONE_HAND") else 0

        # 1. Select Action by Index (Pointer Logic)
        legal_moves = self.engine.get_legal_moves()
        
        if action_idx < len(legal_moves):
            actual_action = legal_moves[action_idx]
        else:
            # Fallback to Pass if index is out of bounds (should not happen with masking)
            penalty = -0.1
            actual_action = next((m for m in legal_moves if isinstance(m, PassPriorityAction)), legal_moves[0])

        # 2. Execute & Resolve Name for Logging
        action_name = type(actual_action).__name__.replace("Action", "")
        player_name = self._resolve_name(actual_action.player_id)
        
        action_detail = ""
        if hasattr(actual_action, "card_id"):
            action_detail = f"({self._resolve_name(actual_action.card_id)})"
        elif hasattr(actual_action, "blocker_id"):
            action_detail = f"({self._resolve_name(actual_action.blocker_id)} -> {self._resolve_name(actual_action.attacker_id)})"
            
        target_detail = ""
        if hasattr(actual_action, "target_id") and actual_action.target_id:
            target_detail = f" target {self._resolve_name(actual_action.target_id)}"

        readable_action = f"{action_name}{action_detail}{target_detail}"
            
        self.engine.execute_move(actual_action)
        
        # 4. Calculate Impact & Dense Reward
        # Turn/Efficiency Penalty: -0.005 per step (approx 1 damage per 10 steps)
        # This encourages winning fast and discourages stalling.
        step_penalty = -0.005 

        post_p1_life = self.graph.entities[p1_id].properties.get('life_total', 20)
        post_p2_life = self.graph.entities[p2_id].properties.get('life_total', 20)
        
        post_p1_perm = len(self.graph.get_entities_in_zone(p1_id, vocab.ID_ZONE_BATTLEFIELD)) if hasattr(vocab, "ID_ZONE_BATTLEFIELD") else 0
        post_p1_hand = len(self.graph.get_entities_in_zone(p1_id, vocab.ID_ZONE_HAND)) if hasattr(vocab, "ID_ZONE_HAND") else 0

        damage_dealt = max(0, pre_p2_life - post_p2_life)
        damage_reward = damage_dealt * 0.1 # Increased from 0.05
        
        life_reward = ((pre_p2_life - post_p2_life) - (pre_p1_life - post_p1_life)) * 0.02 # Increased from 0.01
        board_reward = (post_p1_perm - pre_p1_perm) * 0.05
        card_reward = (post_p1_hand - pre_p1_hand) * 0.02

        self.game_over = self.engine.game_over
        win_loss_reward = self.engine.get_reward(p1_id)
        
        # Total Reward: win + damage + life + board + cards + illegal penalty + efficiency penalty
        total_reward = win_loss_reward + damage_reward + life_reward + board_reward + card_reward + penalty + step_penalty
        
        p1_mana_pool = self.graph.entities[p1_id].properties.get('mana_pool', {})
        p2_mana_pool = self.graph.entities[p2_id].properties.get('mana_pool', {})
        p1_mana_total = sum(p1_mana_pool.values()) if isinstance(p1_mana_pool, dict) else 0
        p2_mana_total = sum(p2_mana_pool.values()) if isinstance(p2_mana_pool, dict) else 0

        info = {
            "action_taken": readable_action,
            "player_name": player_name,
            "p1_life": post_p1_life,
            "p2_life": post_p2_life,
            "p1_perm": post_p1_perm,
            "p1_hand": post_p1_hand,
            "p2_hand": len(self.graph.get_entities_in_zone(p2_id, vocab.ID_ZONE_HAND)) if hasattr(vocab, "ID_ZONE_HAND") else 0,
            "p1_mana": p1_mana_total,
            "p2_mana": p2_mana_total
        }
        
        return self._get_obs(), total_reward, self.game_over, info

    def get_legal_actions_as_tokens(self) -> List[List[int]]:
        """Returns all legal moves converted to tokens for the model."""
        legal_moves = self.engine.get_legal_moves()
        return [self.mapper.action_to_tokens(m, self.graph) for m in legal_moves]

    def _get_obs(self) -> Dict[str, Any]:
        """Returns the current state as observation tensors, including legal moves."""
        tokens = self.converter.convert_graph_to_tokens(self.graph, self.engine.stack)
        obs_vec = self.converter.convert_graph_to_observation(self.graph)
        
        # Get legal moves and their semantic descriptors
        legal_moves = self.engine.get_legal_moves()
        descriptors = []
        for m in legal_moves:
            d = self.mapper.get_action_descriptor(m, self.graph)
            # Flatten descriptor: [type, src_feats(32), tgt_feats(32)] = 65 dim
            flat_d = np.concatenate([[d["type"]], d["source_features"], d["target_features"]])
            descriptors.append(flat_d)
            
        if not descriptors:
            descriptors = [np.zeros(65)]
        
        return {
            "tokens": tokens,
            "observation": obs_vec,
            "active_player": self.graph.active_player_id,
            "legal_action_descriptors": descriptors,
            "legal_actions_count": len(legal_moves)
        }

from ..rule_engine.actions import PassPriorityAction # Import for fallback
