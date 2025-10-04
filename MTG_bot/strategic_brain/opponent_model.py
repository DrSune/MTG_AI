"""
This module is responsible for modeling the opponent.
It tries to infer hidden information, such as the opponent's deck archetype
and the likely cards in their hand.
"""

from typing import List, Dict
from ..rule_engine.game_state import GameState, Card

class OpponentModel:
    """Models the opponent's strategy and potential plays."""
    def __init__(self):
        # This could load pre-computed data about deck archetypes.
        self.archetype_definitions = {}
        self.detected_archetype = "Unknown"

    def update(self, opponent_move, game_state: GameState):
        """
        Updates the model with the latest action from the opponent.
        This is where archetype detection would happen.
        """
        # Example: if opponent plays Mountain -> Mountain -> Goblin Guide,
        # we can be fairly certain the archetype is "Mono-Red Aggro".
        pass

    def infer_hand_probabilities(self) -> Dict[str, float]:
        """
        Based on the detected archetype, returns a probability distribution
        over cards that are likely in the opponent's hand.

        Returns:
            A dictionary mapping card names to their probability of being in hand.
        """
        if self.detected_archetype == "Mono-Red Aggro":
            return {"Lightning Bolt": 0.75, "Rift Bolt": 0.6, "Goblin Guide": 0.2}
        
        return {}
