"""
This file defines the data structures for the game state.
It represents the "board" and all its components at any given point in time.
It is the single source of truth that the Rule Engine acts upon.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional

@dataclass
class Card:
    """A machine-readable representation of a single Magic card."""
    name: str
    mana_cost: str
    type_line: str
    text: str
    power: Optional[int] = None
    toughness: Optional[int] = None
    # Add other relevant attributes like loyalty, colors, etc.

@dataclass
class Player:
    """Represents a player and all their associated zones."""
    player_id: int
    life: int = 20
    hand: List[Card] = field(default_factory=list)
    library: List[Card] = field(default_factory=list)
    graveyard: List[Card] = field(default_factory=list)
    battlefield: List[Card] = field(default_factory=list)
    exile: List[Card] = field(default_factory=list)
    mana_pool: Dict[str, int] = field(default_factory=dict)

@dataclass
class GameState:
    """The complete state of the game at one point in time."""
    players: List[Player] = field(default_factory=list)
    turn_number: int = 1
    active_player_id: int = 1
    current_phase: str = "main1"
    stack: List = field(default_factory=list) # Represents the stack

    # ... methods to manipulate the game state will go here
    # e.g., draw_card, play_land, cast_spell, resolve_stack, etc.
    def initialize_game(self, player1_deck_path, player2_deck_path):
        print(f"Initializing game with decks: {player1_deck_path} and {player2_deck_path}")
        # Placeholder for deck loading and initial draw
        pass

    def is_over(self) -> bool:
        # Placeholder for game over conditions
        return self.turn_number > 10 # Simple stop condition for now

    def get_active_player_id(self) -> int:
        return self.active_player_id

    def apply_move(self, move):
        # Placeholder for applying a move and changing the state
        pass

    def pass_priority(self):
        # Placeholder for passing priority or advancing phases
        pass

    def get_winner(self) -> Optional[int]:
        # Placeholder
        return None
