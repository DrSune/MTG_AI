"""
This file defines the data structures for representing game actions (moves).
"""

from dataclasses import dataclass
import uuid
from typing import Optional

@dataclass
class PlayLandAction:
    """Represents the action of playing a land card from hand."""
    player_id: uuid.UUID
    card_id: uuid.UUID

    def __repr__(self) -> str:
        return f"PlayLand(Player: {str(self.player_id)[:4]}, Card: {str(self.card_id)[:4]})"

@dataclass
class CastSpellAction:
    """Represents the action of casting a spell from hand."""
    player_id: uuid.UUID
    card_id: uuid.UUID
    target_id: Optional[uuid.UUID] = None # Added for spells that target, like Auras

    def __repr__(self) -> str:
        target_str = f", Target: {str(self.target_id)[:4]}" if self.target_id else ""
        return f"CastSpell(Player: {str(self.player_id)[:4]}, Card: {str(self.card_id)[:4]}{target_str})"

@dataclass
class ActivateManaAbilityAction:
    """Represents the action of activating a mana ability."""
    player_id: uuid.UUID
    card_id: uuid.UUID
    ability_id: int

    def __repr__(self) -> str:
        return f"ActivateManaAbility(Player: {str(self.player_id)[:4]}, Card: {str(self.card_id)[:4]}, Ability: {self.ability_id})"

@dataclass
class DeclareAttackerAction:
    """Represents declaring a single creature as an attacker."""
    player_id: uuid.UUID
    card_id: uuid.UUID

    def __repr__(self) -> str:
        return f"DeclareAttacker(Player: {str(self.player_id)[:4]}, Card: {str(self.card_id)[:4]})"

@dataclass
class DeclareBlockerAction:
    """Represents one creature blocking one attacking creature."""
    player_id: uuid.UUID      # The player declaring the blocker
    blocker_id: uuid.UUID     # The creature that is blocking
    attacker_id: uuid.UUID    # The creature being blocked

    def __repr__(self) -> str:
        return f"DeclareBlocker(Player: {str(self.player_id)[:4]}, Blocker: {str(self.blocker_id)[:4]}, Attacker: {str(self.attacker_id)[:4]})"
