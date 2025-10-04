"""
This file defines the Rulebook, a central dispatch table that maps
ability IDs from the vocabulary to their corresponding logic functions.
"""

from typing import Dict, Callable, Any, Optional

# We import all the handler modules
from .handlers import (
    keyword_handlers,
    combat_handlers,
    graveyard_handlers,
    mana_handlers,
    continuous_effect_handlers,
    triggered_ability_handlers,
    activated_ability_handlers,
    card_specific_handlers
)

# These vocabulary IDs would be defined in a central, shared file
# so they can be used by the parsers, the engine, and the ML model.
ID_ABILITY_FLYING = 5001
ID_ABILITY_FLASHBACK = 6001
ID_TRIGGER_ETB = 7001 # ETB = Enters The Battlefield
ID_CARD_TARMOGOYF = 1337

class Rulebook:
    """A dispatch table mapping rule IDs to their implementation."""
    def __init__(self):
        # The dispatch table itself. The values are function references.
        self.dispatch_table: Dict[int, Callable] = {}
        self._initialize_rulebook()

    def _initialize_rulebook(self):
        """
        This is where we build the map, creating the link between an ID and its logic.
        This modular structure makes it easy to see where the logic for a rule comes from.
        """
        # Keyword Handlers
        self.dispatch_table[ID_ABILITY_FLYING] = keyword_handlers.can_be_blocked_by

        # Graveyard Handlers
        self.dispatch_table[ID_ABILITY_FLASHBACK] = graveyard_handlers.get_flashback_moves

        # Triggered Ability Handlers
        # Note: The mapping can be more complex. Here, an event type might map to a handler.
        self.dispatch_table[ID_TRIGGER_ETB] = triggered_ability_handlers.check_and_create_triggers

        # Card Specific Handlers
        # Some cards are so unique they get their own entry.
        self.dispatch_table[ID_CARD_TARMOGOYF] = card_specific_handlers.handle_tarmogoyf_update

    def get_handler(self, rule_id: int) -> Optional[Callable]:
        """Retrieves the handler function for a given rule ID."""
        return self.dispatch_table.get(rule_id)