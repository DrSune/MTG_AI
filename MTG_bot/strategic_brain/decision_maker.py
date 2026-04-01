"""
This module contains the final decision-making logic.
It uses the evaluation functions and a search algorithm to select the best move
from the list of legal moves provided by the Rule Engine.
"""

from typing import List
from ..rule_engine.game_graph import GameGraph
from ..rule_engine.game_state import GameState # Keep for now if evaluation still uses it
from .evaluation import MultiHeadedEvaluator
from .opponent_model import OpponentModel
from .state_converter import StateConverter
from .model import System2Transformer
from .action_mapper import ActionSpaceMapper

class DecisionMaker:
    """The 'Player' agent that chooses the best action using System 2 reasoning."""
    def __init__(self, player_id: int):
        self.player_id = player_id
        self.state_converter = StateConverter()
        self.action_mapper = ActionSpaceMapper()
        
        # Initialize the System 2 Model
        # These parameters should ideally come from a config file
        self.model = System2Transformer(
            vocab_size=10000, 
            embedding_dim=128, 
            component_dim=10, 
            nhead=8, 
            num_layers=6, 
            belief_dim=64, 
            max_actions=10
        )

    def choose_best_move(self, game_graph: GameGraph, legal_moves: List) -> any:
        """
        Orchestrates the decision-making process using recursive reasoning.
        """
        if not legal_moves:
            return None

        # 1. Convert GameGraph to tokens for the Transformer
        tokens = self.state_converter.convert_graph_to_tokens(game_graph)
        
        # 2. Recursive Reasoning Loop (Rethink)
        # We start with a base number of passes, but the model can trigger more
        max_rethink_attempts = 3
        current_pass = 0
        
        state_memory = None
        prev_actions = None
        
        while current_pass < max_rethink_attempts:
            # Forward pass through the model
            output = self.model(
                tokens["atomic_ids"], 
                tokens["component_features"],
                num_passes=2, # Each rethink adds 2 reasoning passes
                prev_memory=state_memory,
                prev_actions=prev_actions
            )
            
            rethink_prob = output["rethink_prob"].item()
            state_memory = output["state_memory"]
            prev_actions = output["action_tokens"]
            
            print(f"DecisionMaker: Pass {current_pass}, Rethink Probability: {rethink_prob:.4f}")
            
            # For now, we simulate the rethink decision
            if rethink_prob < 0.5 or current_pass == max_rethink_attempts - 1:
                # Sequence mapped:
                # mapped_action = self.action_mapper.tokens_to_action(prev_actions[0].tolist(), game_graph)
                break
                
            current_pass += 1

        # 3. For the skeleton, we still use the heuristic evaluation to pick from legal_moves
        # until the Action Decoder is fully trained to output valid sequences mapped by ActionSpaceMapper.
        best_move = None
        best_score = -float('inf')
        
        evaluator = MultiHeadedEvaluator(embeddings={})
        for move in legal_moves:
            move_score = evaluator.impact_scorer.score_play(move, game_graph)
            if move_score > best_score:
                best_score = move_score
                best_move = move
        
        if best_move is None:
            best_move = legal_moves[0]

        return best_move

def action_chooser_policy(game_state_encoding, legal_actions):
    # We should consider running this policy network multiple times for different candidates of opponent cards
    # and for different actions that are valued at some minimum long-term expected reward.
    pass

def value_function(game_state_encoding):
    # This function evaluates the current game state and returns a value indicating how well we are doing.
    pass

def mcts_search(game_state, n_simulations):
    # We believe that a larger transformer (that encodes more entities individually) can have a higher ceiling than a small one.
    # A small one benefits from quick learning but risks reaching learning saturation more quickly.
    # It can do deeper searches (higher N for the same time) but with less sophisticated analysis.
    # Very long-term, the increased complexity of a bigger transformer can reach higher levels, and might generalize better,
    # but needs significantly more time to reach this, since exploration will take longer, as N per time will be lower as a result of the quadratic computational cost.
    pass
