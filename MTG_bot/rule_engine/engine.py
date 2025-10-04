"""
The main public-facing class for the Rule Engine.
It orchestrates all the other components (Graph, Layers, Rulebook)
to produce a list of legal moves.
"""

from .game_graph import GameGraph
from .layer_system import LayerSystem
from .rulebook import Rulebook

class RuleEngine:
    """The main orchestrator for rule enforcement."""
    def __init__(self):
        self.rulebook = Rulebook()
        self.layer_system = LayerSystem(self.rulebook)

    def get_legal_moves(self, graph: GameGraph) -> list:
        """
        The primary public method. Determines all legal moves for the active player.

        Returns:
            A list of move objects, e.g., [PlayLand(card), CastSpell(card), ...]
        """
        print("RuleEngine: Determining legal moves...")

        # 1. First, apply all continuous effects to get a definitive board state.
        #    This resolves all layers to determine final P/T, abilities, etc.
        self.layer_system.apply_all_layers(graph)

        # 2. Determine the active player and current phase from the graph.
        # active_player = graph.get_active_player()
        # current_phase = graph.get_current_phase()

        legal_moves = []

        # 3. Check for all possible actions based on the current state.
        #    This is where the engine uses the rulebook to validate actions.
        #    For example, to check if a creature can attack:
        #    - Is it the combat phase?
        #    - Is the creature affected by summoning sickness? (Check for Haste ability)
        #    - Are there any effects that prevent it from attacking?
        #      (e.g., call rulebook handler for ID_EFFECT_CANT_ATTACK)

        # This process is repeated for casting spells, activating abilities, etc.

        print(f"RuleEngine: Found {len(legal_moves)} legal moves.")
        return legal_moves