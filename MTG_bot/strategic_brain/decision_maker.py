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

class DecisionMaker:
    """The "Player" agent that chooses the best action."""
    def __init__(self, player_id: int):
        self.player_id = player_id
        self.evaluator = MultiHeadedEvaluator(embeddings={}) # Load embeddings here
        self.opponent_model = OpponentModel()
        self.state_converter = StateConverter()

    def choose_best_move(self, game_graph: GameGraph, legal_moves: List) -> any:
        """
        Orchestrates the decision-making process.

        1. Converts the current GameGraph into an observation.
        2. Evaluates the current state.
        3. Prunes the list of legal moves based on heuristics.
        4. Runs a search algorithm (like MCTS) on the pruned list.
        5. Returns the best move found by the search.
        """
        if not legal_moves:
            return None

        # 1. Convert GameGraph to observation
        observation = self.state_converter.convert_graph_to_observation(game_graph)
        # logger.debug(f"Current observation: {observation}") # Uncomment for debugging

        # 2. Assess the current situation (evaluator needs to be updated to use GameGraph)
        assessment = self.evaluator.assess_game_potential(game_graph) # Pass GameGraph

        # 3. Check for special strategic conditions
        if assessment["hail_mary_needed"] == 1.0:
            # In a desperate state, change the goal:
            # Find the move that maximizes the chance of drawing a specific out.
            print("DecisionMaker: Hail Mary mode activated!")
            # This would involve a different kind of search.
            pass

        # 4. Prune moves and run search (e.g., MCTS)
        # For now, we'll just use a simple evaluation of each move.
        best_move = None
        best_score = -float('inf')

        for move in legal_moves:
            # For each move, we would conceptually:
            # a. Create a hypothetical future_state by applying the move.
            # b. Score that future_state using the evaluator.
            # c. The score would be a combination of synergy, impact, etc.
            move_score = self.evaluator.impact_scorer.score_play(move, game_graph) # Pass GameGraph

            if move_score > best_score:
                best_score = move_score
                best_move = move
        
        # A real implementation would use a much more robust search algorithm here.
        # If no move seems good, it might default to the first legal move.
        if best_move is None:
            best_move = legal_moves[0]

        return best_move
