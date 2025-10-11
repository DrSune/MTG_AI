"""
This file defines the foundational data structures for the entire rule engine.
The game state is represented as a graph of generic entities and their relationships.
"""

import uuid
import random
from typing import Dict, Any, List, Optional

from . import vocabulary as vocab

class Entity:
    """A generic container for any object, property, or concept in the game."""
    def __init__(self, entity_type_id: int):
        self.instance_id: uuid.UUID = uuid.uuid4()
        self.type_id: int = entity_type_id
        # Flexible properties for dynamic state values computed by the engine,
        # e.g., current power, toughness, tapped status, etc.
        self.properties: Dict[str, Any] = {}

class Relationship:
    """A directed, typed edge in the game graph, linking two entities."""
    def __init__(self, source_id: uuid.UUID, target_id: uuid.UUID, rel_type_id: int):
        self.source: uuid.UUID = source_id
        self.target: uuid.UUID = target_id
        self.type_id: int = rel_type_id

class GameGraph:
    """The complete, graph-based representation of the game state.
    This object holds the entire "truth" of the game at a single point in time.
    """
    def __init__(self):
        self.entities: Dict[uuid.UUID, Entity] = {}
        self.relationships: List[Relationship] = []
        self.turn_number: int = 1
        self.active_player_id: Optional[uuid.UUID] = None
        self.phase: int = vocab.ID_PHASE_PRE_COMBAT_MAIN # Default to main phase
        self.step: int = 0 # No specific step by default

    def add_entity(self, entity_type_id: int) -> Entity:
        entity = Entity(entity_type_id)
        self.entities[entity.instance_id] = entity
        return entity

    def add_relationship(self, source: Entity, target: Entity, rel_type_id: int):
        rel = Relationship(source.instance_id, target.instance_id, rel_type_id)
        self.relationships.append(rel)

    def get_relationships(self, source: Optional[Entity] = None, target: Optional[Entity] = None, rel_type: Optional[int] = None) -> List[Relationship]:
        """Finds relationships in the graph based on source, target, or type."""
        # This would be a more optimized query in a real implementation
        results = self.relationships
        if source:
            results = [r for r in results if r.source == source.instance_id]
        if target:
            results = [r for r in results if r.target == target.instance_id]
        if rel_type:
            results = [r for r in results if r.type_id == rel_type]
        return results

    def _create_deck(self, player: Entity, decklist: List[int]) -> List[Entity]:
        """Creates card entities from a decklist and links them to the player."""
        deck = []
        # Create zone entities for the player
        library = self.add_entity(vocab.ID_ZONE_LIBRARY)
        hand = self.add_entity(vocab.ID_ZONE_HAND)
        graveyard = self.add_entity(vocab.ID_ZONE_GRAVEYARD)
        battlefield = self.add_entity(vocab.ID_ZONE_BATTLEFIELD)

        self.add_relationship(player, library, vocab.ID_REL_CONTROLS)
        self.add_relationship(player, hand, vocab.ID_REL_CONTROLS)
        self.add_relationship(player, graveyard, vocab.ID_REL_CONTROLS)
        self.add_relationship(player, battlefield, vocab.ID_REL_CONTROLS)

        for card_type_id in decklist:
            card = self.add_entity(card_type_id)
            self.add_relationship(player, card, vocab.ID_REL_CONTROLS)
            self.add_relationship(card, library, vocab.ID_REL_IS_IN_ZONE)
            deck.append(card)
        return deck

    def initialize_game(self, decklist1: List[int], decklist2: List[int], shuffle: bool = True):
        """Sets up the initial game state with two players, their decks, and opening hands."""
        self.turn_number = 1
        # Create Players
        player1 = self.add_entity(vocab.ID_PLAYER)
        player1.properties['life_total'] = 20
        player1.properties['mana_pool'] = {m: 0 for m in [vocab.ID_MANA_GREEN, vocab.ID_MANA_BLUE, vocab.ID_MANA_BLACK, vocab.ID_MANA_RED, vocab.ID_MANA_WHITE, vocab.ID_MANA_COLORLESS]}
        player2 = self.add_entity(vocab.ID_PLAYER)
        player2.properties['life_total'] = 20
        player2.properties['mana_pool'] = {m: 0 for m in [vocab.ID_MANA_GREEN, vocab.ID_MANA_BLUE, vocab.ID_MANA_BLACK, vocab.ID_MANA_RED, vocab.ID_MANA_WHITE, vocab.ID_MANA_COLORLESS]}

        # Set active player
        self.active_player_id = player1.instance_id

        # Create and shuffle decks
        deck1 = self._create_deck(player1, decklist1)
        deck2 = self._create_deck(player2, decklist2)
        if shuffle:
            random.shuffle(deck1)
            random.shuffle(deck2)

        # Draw opening hands
        # Find the hand zone for Player 1
        p1_control_rels = self.get_relationships(source=player1, rel_type=vocab.ID_REL_CONTROLS)
        p1_hand_zone_entity = None
        for rel in p1_control_rels:
            entity = self.entities[rel.target]
            if entity.type_id == vocab.ID_ZONE_HAND:
                p1_hand_zone_entity = entity
                break

        # Find the hand zone for Player 2
        p2_control_rels = self.get_relationships(source=player2, rel_type=vocab.ID_REL_CONTROLS)
        p2_hand_zone_entity = None
        for rel in p2_control_rels:
            entity = self.entities[rel.target]
            if entity.type_id == vocab.ID_ZONE_HAND:
                p2_hand_zone_entity = entity
                break

        for i in range(7):
            # Player 1 draws
            if deck1:
                card_to_draw_p1 = deck1.pop(0)
                rel_to_update_p1 = self.get_relationships(source=card_to_draw_p1, rel_type=vocab.ID_REL_IS_IN_ZONE)[0]
                rel_to_update_p1.target = p1_hand_zone_entity.instance_id

            # Player 2 draws
            if deck2:
                card_to_draw_p2 = deck2.pop(0)
                rel_to_update_p2 = self.get_relationships(source=card_to_draw_p2, rel_type=vocab.ID_REL_IS_IN_ZONE)[0]
                rel_to_update_p2.target = p2_hand_zone_entity.instance_id
