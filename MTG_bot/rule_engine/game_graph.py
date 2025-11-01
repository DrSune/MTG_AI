print("--- Executing game_graph.py ---")
"""
This file defines the foundational data structures for the entire rule engine.
The game state is represented as a graph of generic entities and their relationships.
"""

import uuid
import random
from typing import Dict, Any, List, Optional

from . import card_database # Import the entire module to access card_data_loader
from MTG_bot.utils.logger import setup_logger
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config

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
        self.id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)
        mulligan_phase_id = self.id_mapper.get_id_by_name("Mulligan Phase", "game_vocabulary")
        mulligan_step_id = self.id_mapper.get_id_by_name("Mulligan Step", "game_vocabulary")
        self.phase: int = mulligan_phase_id or self.id_mapper.get_id_by_name("Beginning Phase", "game_vocabulary")
        self.step: int = mulligan_step_id or self.id_mapper.get_id_by_name("Untap Step", "game_vocabulary")
        self.players: List[uuid.UUID] = []
        logger.info("GameGraph initialized.")

    def _get_entity_display_name(self, entity: Entity) -> str:
        """Returns a readable name for an entity, preferring card or player names."""
        if not entity:
            return "Unknown"
        name = entity.properties.get('name')
        if name:
            return name
        card_data = card_database.card_data_loader.get_card_data_by_id(entity.type_id)
        card_name = card_data.get('name') if card_data else None
        if card_name:
            return card_name
        vocab_name = self.id_mapper.get_name(entity.type_id, "game_vocabulary")
        if vocab_name:
            return vocab_name
        db_card_name = self.id_mapper.get_name(entity.type_id, "cards")
        if db_card_name:
            return db_card_name
        return str(entity.type_id)

    def _set_zone_order(self, zone_entity: Entity, cards_in_order: List[Entity]):
        """Rebuilds the zone's ordering to match the provided sequence."""
        zone_rel_type = self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary")
        # Remove existing zone membership relationships for this zone
        self.relationships = [
            r for r in self.relationships
            if not (r.target == zone_entity.instance_id and r.type_id == zone_rel_type)
        ]
        # Re-add relationships following the desired order (earlier entries = bottom of library)
        for card_entity in cards_in_order:
            rel = Relationship(card_entity.instance_id, zone_entity.instance_id, zone_rel_type)
            self.relationships.append(rel)

    def add_entity(self, entity_type_id: int) -> Entity:
        try:
            entity = Entity(entity_type_id)
            # If the entity corresponds to a card, hydrate its static data.
            card_data = card_database.card_data_loader.get_card_data_by_id(entity_type_id)
            if card_data:
                entity.properties.update(card_data)
                # Initialize dynamic battlefield state flags for permanents.
                entity.properties.setdefault('tapped', False)
                entity.properties.setdefault('damage_taken', 0)
                entity.properties.setdefault('is_attacking', False)
                entity.properties.setdefault('has_summoning_sickness', True)

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

    def _move_card_to_zone(self, card: Entity, target_zone: Entity, place_on_top: bool = True):
        """Moves a card entity to a new zone by updating its ID_REL_IS_IN_ZONE relationship."""
        logger.debug(f"Moving card {self._get_entity_display_name(card)} to zone {self._get_entity_display_name(target_zone)}.")
        try:
            # Remove existing ID_REL_IS_IN_ZONE relationships for the card
            zone_rel_type = self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary")
            self.relationships = [
                r for r in self.relationships
                if not (r.source == card.instance_id and r.type_id == zone_rel_type)
            ]
            # Add new ID_REL_IS_IN_ZONE relationship in the requested position
            rel = Relationship(card.instance_id, target_zone.instance_id, zone_rel_type)
            if place_on_top:
                self.relationships.append(rel)
            else:
                self.relationships.insert(0, rel)
            card.properties['entered_zone_turn'] = self.turn_number
        except Exception as e:
            logger.error(f"Error moving card {card.instance_id} to zone {target_zone.instance_id}: {e}", exc_info=True)
            raise

    def _create_deck(self, player: Entity, decklist: List[int]) -> List[Entity]:
        """Creates card entities from a decklist and links them to the player."""
        logger.debug(f"Creating deck for player {player.properties.get('name', player.instance_id)[:4]} with {len(decklist)} cards.")
        deck = []
        try:
            # Create zone entities for the player
            library = self.add_entity(self.id_mapper.get_id_by_name("Library", "game_vocabulary"))
            hand = self.add_entity(self.id_mapper.get_id_by_name("Hand", "game_vocabulary"))
            graveyard = self.add_entity(self.id_mapper.get_id_by_name("Graveyard", "game_vocabulary"))
            battlefield = self.add_entity(self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary"))

            self.add_relationship(player, library, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
            self.add_relationship(player, hand, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
            self.add_relationship(player, graveyard, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
            self.add_relationship(player, battlefield, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))

            for card_type_id in decklist:
                card = self.add_entity(card_type_id)
                self.add_relationship(player, card, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
                self.add_relationship(card, library, self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))
                deck.append(card)
            logger.debug(f"Deck created for player {player.properties.get('name', player.instance_id)[:4]}.")
            return deck
        except Exception as e:
            logger.error(f"Error creating deck for player {player.properties.get('name', player.instance_id)[:4]}: {e}", exc_info=True)
            raise

    def draw_hand(self, player_id: uuid.UUID, hand_size: int):
        """Draws a number of cards for a player."""
        player = self.entities[player_id]
        for _ in range(hand_size):
            self.draw_card(player)

    def draw_card(self, player: Entity) -> Optional[Entity]:
        """Moves the top card of a player's library to their hand."""
        player_name = self._get_entity_display_name(player)
        logger.info(f"{player_name} attempts to draw a card.")
        try:
            # Find player's library and hand zones
            control_rels = self.get_relationships(source=player, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
            library_zone = next((self.entities[r.target] for r in control_rels if self.entities[r.target].type_id == self.id_mapper.get_id_by_name("Library", "game_vocabulary")), None)
            hand_zone = next((self.entities[r.target] for r in control_rels if self.entities[r.target].type_id == self.id_mapper.get_id_by_name("Hand", "game_vocabulary")), None)

            if not library_zone or not hand_zone:
                logger.warning(f"{player_name} is missing a library or hand zone. Cannot draw.")
                return None

            # Find cards in library
            cards_in_library_rels = self.get_relationships(target=library_zone, rel_type=self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))
            cards_in_library = [self.entities[r.source] for r in cards_in_library_rels]

            if not cards_in_library:
                logger.info(f"{player_name} has no cards left in library. Cannot draw.")
                # In a real game, this would trigger a loss condition
                return None

            # Take the top card (last in the list if deck was shuffled and popped from end)
            card_to_draw = cards_in_library[-1] # Assuming last card is top of library
            
            # Update its zone relationship using the helper method
            self._move_card_to_zone(card_to_draw, hand_zone)

            card_name = self._get_entity_display_name(card_to_draw)
            logger.info(f"{player_name} drew {card_name}.")
            return card_to_draw
        except Exception as e:
            logger.error(f"Error drawing card for Player {player.properties.get('name', player.instance_id)[:4]}: {e}", exc_info=True)
            return None
