print("--- Executing game_graph.py ---")
"""
This file defines the foundational data structures for the entire rule engine.
The game state is represented as a graph of generic entities and their relationships.
"""

import uuid
import random
from typing import Dict, Any, List, Optional

from . import vocabulary as vocab
from . import card_database # Import the entire module to access card_data_loader
from MTG_bot.utils.logger import setup_logger

logger = setup_logger(__name__)

class Entity:
    """A generic container for any object, property, or concept in the game."""
    def __init__(self, entity_type_id: int):
        self.instance_id: uuid.UUID = uuid.uuid4()
        self.type_id: int = entity_type_id
        # Flexible properties for dynamic state values computed by the engine,
        # e.g., current power, toughness, tapped status, etc.
        self.properties: Dict[str, Any] = {}
        logger.debug(f"Created Entity: {self.instance_id} (Type: {self.type_id})")

class Relationship:
    """A directed, typed edge in the game graph, linking two entities."""
    def __init__(self, source_id: uuid.UUID, target_id: uuid.UUID, rel_type_id: int):
        self.source: uuid.UUID = source_id
        self.target: uuid.UUID = target_id
        self.type_id: int = rel_type_id
        logger.debug(f"Created Relationship: {self.source} -> {self.target} (Type: {self.type_id})")

class GameGraph:
    """The complete, graph-based representation of the game state.
    This object holds the entire "truth" of the game at a single point in time.
    """
    def __init__(self):
        self.entities: Dict[uuid.UUID, Entity] = {}
        self.relationships: List[Relationship] = []
        self.turn_number: int = 1
        self.active_player_id: Optional[uuid.UUID] = None
        self.phase: int = vocab.ID_PHASE_BEGINNING # Start of the game
        self.step: int = vocab.ID_STEP_UNTAP # Start of the game
        logger.info("GameGraph initialized.")

    def add_entity(self, entity_type_id: int) -> Entity:
        try:
            entity = Entity(entity_type_id)
            # If the entity is a card, load its properties from the CardDataLoader
            if entity_type_id >= vocab.ID_CARD_FOREST: # Assuming all card IDs are >= ID_CARD_FOREST
                card_data = card_database.card_data_loader.get_card_data_by_id(entity_type_id)
                if card_data:
                    entity.properties.update(card_data)
                    # Initialize dynamic properties for cards on battlefield
                    entity.properties['tapped'] = False
                    entity.properties['damage_taken'] = 0
                    entity.properties['is_attacking'] = False
                    entity.properties['has_summoning_sickness'] = True # Set to True initially

            self.entities[entity.instance_id] = entity
            logger.debug(f"Added entity {entity.instance_id} (Type: {entity_type_id}) to graph.")
            return entity
        except Exception as e:
            logger.error(f"Error adding entity {entity_type_id}: {e}", exc_info=True)
            raise

    def add_relationship(self, source: Entity, target: Entity, rel_type_id: int):
        try:
            rel = Relationship(source.instance_id, target.instance_id, rel_type_id)
            self.relationships.append(rel)
            logger.debug(f"Added relationship {source.instance_id} -> {target.instance_id} (Type: {rel_type_id}) to graph.")
        except Exception as e:
            logger.error(f"Error adding relationship {source.instance_id} -> {target.instance_id} (Type: {rel_type_id}): {e}", exc_info=True)
            raise

    def get_relationships(self, source: Optional[Entity] = None, target: Optional[Entity] = None, rel_type: Optional[int] = None) -> List[Relationship]:
        """Finds relationships in the graph based on source, target, or type."""
        logger.debug(f"Querying relationships: source={source.instance_id if source else 'None'}, target={target.instance_id if target else 'None'}, rel_type={rel_type}")
        try:
            results = self.relationships
            if source:
                results = [r for r in results if r.source == source.instance_id]
            if target:
                results = [r for r in results if r.target == target.instance_id]
            if rel_type:
                results = [r for r in results if r.type_id == rel_type]
            logger.debug(f"Found {len(results)} relationships.")
            return results
        except Exception as e:
            logger.error(f"Error getting relationships: {e}", exc_info=True)
            raise

    def _create_deck(self, player: Entity, decklist: List[int]) -> List[Entity]:
        """Creates card entities from a decklist and links them to the player."""
        logger.debug(f"Creating deck for player {player.properties.get('name', player.instance_id)[:4]} with {len(decklist)} cards.")
        deck = []
        try:
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
            logger.debug(f"Deck created for player {player.properties.get('name', player.instance_id)[:4]}.")
            return deck
        except Exception as e:
            logger.error(f"Error creating deck for player {player.properties.get('name', player.instance_id)[:4]}: {e}", exc_info=True)
            raise

    def initialize_game(self, decklist1: List[int], decklist2: List[int], shuffle: bool = True):
        """Sets up the initial game state with two players, their decks, and opening hands."""
        logger.info("Initializing game...")
        try:
            self.turn_number = 1
            # Create Players
            player1 = self.add_entity(vocab.ID_PLAYER)
            player1.properties['life_total'] = 20
            player1.properties['mana_pool'] = {m: 0 for m in [vocab.ID_MANA_GREEN, vocab.ID_MANA_BLUE, vocab.ID_MANA_BLACK, vocab.ID_MANA_RED, vocab.ID_MANA_WHITE, vocab.ID_MANA_COLORLESS]}
            player1.properties['name'] = "Player 1"
            player2 = self.add_entity(vocab.ID_PLAYER)
            player2.properties['life_total'] = 20
            player2.properties['mana_pool'] = {m: 0 for m in [vocab.ID_MANA_GREEN, vocab.ID_MANA_BLUE, vocab.ID_MANA_BLACK, vocab.ID_MANA_RED, vocab.ID_MANA_WHITE, vocab.ID_MANA_COLORLESS]}
            player2.properties['name'] = "Player 2"

            # Set active player
            self.active_player_id = player1.instance_id
            logger.info(f"Active player set to {player1.properties.get('name')}.")

            # Create and shuffle decks
            deck1 = self._create_deck(player1, decklist1)
            deck2 = self._create_deck(player2, decklist2)
            if shuffle:
                random.shuffle(deck1)
                random.shuffle(deck2)
                logger.debug("Decks shuffled.")

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
                    logger.debug(f"{player1.properties.get('name')} drew {card_to_draw_p1.properties.get('name', card_to_draw_p1.type_id)}.")

                # Player 2 draws
                if deck2:
                    card_to_draw_p2 = deck2.pop(0)
                    rel_to_update_p2 = self.get_relationships(source=card_to_draw_p2, rel_type=vocab.ID_REL_IS_IN_ZONE)[0]
                    rel_to_update_p2.target = p2_hand_zone_entity.instance_id
                    logger.debug(f"{player2.properties.get('name')} drew {card_to_draw_p2.properties.get('name', card_to_draw_p2.type_id)}.")
            logger.info("Game initialized successfully.")
        except Exception as e:
            logger.error(f"Error initializing game: {e}", exc_info=True)

    def draw_card(self, player: Entity) -> Optional[Entity]:
        """Moves the top card of a player's library to their hand."""
        logger.info(f"Player {player.properties.get('name')} attempts to draw a card.")
        try:
            # Find player's library and hand zones
            control_rels = self.get_relationships(source=player, rel_type=vocab.ID_REL_CONTROLS)
            library_zone = next((self.entities[r.target] for r in control_rels if self.entities[r.target].type_id == vocab.ID_ZONE_LIBRARY), None)
            hand_zone = next((self.entities[r.target] for r in control_rels if self.entities[r.target].type_id == vocab.ID_ZONE_HAND), None)

            if not library_zone or not hand_zone:
                logger.warning(f"Player {player.properties.get('name')} is missing a library or hand zone. Cannot draw.")
                return None

            # Find cards in library
            cards_in_library_rels = self.get_relationships(target=library_zone, rel_type=vocab.ID_REL_IS_IN_ZONE)
            cards_in_library = [self.entities[r.source] for r in cards_in_library_rels]

            if not cards_in_library:
                logger.info(f"Player {player.properties.get('name')} has no cards left in library. Cannot draw.")
                # In a real game, this would trigger a loss condition
                return None

            # Take the top card (last in the list if deck was shuffled and popped from end)
            card_to_draw = cards_in_library[-1] # Assuming last card is top of library
            
            # Update its zone relationship
            card_zone_rel = next(r for r in cards_in_library_rels if r.source == card_to_draw.instance_id)
            card_zone_rel.target = hand_zone.instance_id

            logger.info(f"Player {player.properties.get('name')} drew {card_to_draw.properties.get('name', card_to_draw.type_id)}.")
            return card_to_draw
        except Exception as e:
            logger.error(f"Error drawing card for Player {player.properties.get('name', player.instance_id)[:4]}: {e}", exc_info=True)
            return None
