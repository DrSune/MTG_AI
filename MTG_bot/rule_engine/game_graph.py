print("--- Executing game_graph.py ---")
"""
This file defines the foundational data structures for the entire rule engine.
The game state is represented as a graph of generic entities and their relationships.
"""

import uuid
import random
from typing import List, Dict, Any, Optional
from MTG_bot.utils.logger import setup_logger
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config

logger = setup_logger(__name__)

class Relationship:
    def __init__(self, source: uuid.UUID, target: uuid.UUID, type_id: int):
        self.source = source
        self.target = target
        self.type_id = type_id

    def __repr__(self):
        return f"Relationship({self.source} --[{self.type_id}]--> {self.target})"

class Entity:
    def __init__(self, instance_id: uuid.UUID, type_id: int):
        self.instance_id = instance_id
        self.type_id = type_id
        self.properties: Dict[str, Any] = {}
        self.timestamp: int = 0

    def __repr__(self):
        name = self.properties.get('name', str(self.instance_id)[:4])
        return f"Entity({name}, type={self.type_id}, t={self.timestamp})"

class GameGraph:
    def __init__(self):
        self.entities: Dict[uuid.UUID, Entity] = {}
        self.relationships: List[Relationship] = []
        self.id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)
        self.players: List[uuid.UUID] = []
        self.active_player_id: Optional[uuid.UUID] = None
        self.turn_number: int = 1
        self.step: int = 0
        self.phase: int = 0
        self.global_clock: int = 0
        self.properties: Dict[str, Any] = {}

    def add_entity(self, type_id: int, properties: Optional[Dict[str, Any]] = None) -> Entity:
        instance_id = uuid.uuid4()
        entity = Entity(instance_id, type_id)
        if properties:
            entity.properties.update(properties)
        
        self.global_clock += 1
        entity.timestamp = self.global_clock
        
        self.entities[instance_id] = entity
        return entity

    def add_relationship(self, source: Entity, target: Entity, type_id: int):
        self.relationships.append(Relationship(source.instance_id, target.instance_id, type_id))

    def get_relationships(self, source: Optional[Entity] = None, target: Optional[Entity] = None, rel_type: Optional[int] = None) -> List[Relationship]:
        results = self.relationships
        if source:
            results = [r for r in results if r.source == source.instance_id]
        if target:
            results = [r for r in results if r.target == target.instance_id]
        if rel_type:
            results = [r for r in results if r.type_id == rel_type]
        return results

    def _get_entity_display_name(self, entity: Entity) -> str:
        return entity.properties.get('name', str(entity.instance_id)[:4])

    def create_player(self, name: str, life_total: int = 20) -> Entity:
        player_type_id = self.id_mapper.get_id_by_name("Player", "game_vocabulary")
        player = self.add_entity(player_type_id, {
            "name": name,
            "life_total": life_total,
            "mana_pool": {},
            "lands_played_this_turn": 0,
            "additional_lands": 0,
            "cards_drawn_this_turn": 0
        })
        self.players.append(player.instance_id)
        
        # Create standard zones for player
        zone_type_names = ["Library", "Hand", "Battlefield", "Graveyard", "Exile"]
        for zone_name in zone_type_names:
            zone_type_id = self.id_mapper.get_id_by_name(zone_name, "game_vocabulary")
            zone = self.add_entity(zone_type_id, {"name": f"{name}'s {zone_name}"})
            self.add_relationship(player, zone, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
            
        return player

    def initialize_deck(self, player_id: uuid.UUID, card_ids: List[int]):
        """Creates entities for cards and places them in the player's library."""
        player = self.entities.get(player_id)
        if not player: return
        
        try:
            control_rels = self.get_relationships(source=player, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
            library_zone = next((self.entities[r.target] for r in control_rels if self.entities[r.target].type_id == self.id_mapper.get_id_by_name("Library", "game_vocabulary")), None)
            
            if not library_zone:
                logger.error(f"Player {player.properties.get('name', str(player_id)[:4])} is missing a library zone.")
                return

            from MTG_bot.rule_engine.card_data_loader import CardDataLoader
            loader = CardDataLoader(config.MTG_BOT_DB_PATH)

            for card_id in card_ids:
                card_data = loader.get_card_data_by_id(card_id)
                card_entity = self.add_entity(card_id, card_data)
                
                # Add relationship to library
                self.add_relationship(card_entity, library_zone, self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))
                # Add relationship to controller
                self.add_relationship(player, card_entity, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
                
        except Exception as e:
            logger.error(f"Error creating deck for player {player.properties.get('name', player.instance_id)[:4]}: {e}", exc_info=True)
            raise

    def draw_hand(self, player_id: uuid.UUID, hand_size: int):
        """Draws a number of cards for a player."""
        player = self.entities[player_id]
        for _ in range(hand_size):
            self.draw_card(player)

    def draw_card(self, player: Entity) -> Optional[Entity]:
        """Moves the top card of a player's library to their hand. Returns None if library is empty."""
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
                logger.info(f"{player_name} has no cards left in library. DRAW LOSS TRIGGERED.")
                player.properties['lost_by_deckout'] = True
                return None

            # Take the top card (last in the list if deck was shuffled and popped from end)
            card_to_draw = cards_in_library[-1] 
            
            # Update its zone relationship using the helper method
            self._move_card_to_zone(card_to_draw, hand_zone)

            card_name = self._get_entity_display_name(card_to_draw)
            logger.info(f"{player_name} drew {card_name}.")
            
            # Update properties
            card_to_draw.properties['is_in_hand'] = True
            card_to_draw.properties['is_on_battlefield'] = False
            
            return card_to_draw
        except Exception as e:
            logger.error(f"Error drawing card for {player_name}: {e}", exc_info=True)
            return None

    def _move_card_to_zone(self, card: Entity, target_zone: Entity):
        """Helper to move an entity to a specific zone by updating its 'Is In Zone' relationship."""
        # Update timestamp and global clock
        self.global_clock += 1
        card.timestamp = self.global_clock
        
        # 1. Remove old zone relationships
        rel_type_id = self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary")
        old_rels = [r for r in self.relationships if r.source == card.instance_id and r.type_id == rel_type_id]
        for r in old_rels:
            self.relationships.remove(r)
            
        # 2. Add new zone relationship
        self.add_relationship(card, target_zone, rel_type_id)
        
        # 3. Update basic properties for convenience
        card.properties['is_on_battlefield'] = (target_zone.type_id == self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary"))
        card.properties['is_in_hand'] = (target_zone.type_id == self.id_mapper.get_id_by_name("Hand", "game_vocabulary"))
        card.properties['is_in_graveyard'] = (target_zone.type_id == self.id_mapper.get_id_by_name("Graveyard", "game_vocabulary"))

    def get_entities_in_zone(self, player_id: uuid.UUID, zone_type_id: int) -> List[Entity]:
        """Returns all entities in a specific zone for a specific player."""
        player = self.entities.get(player_id)
        if not player: return []
        
        control_rels = self.get_relationships(source=player, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
        zone = next((self.entities[r.target] for r in control_rels if self.entities[r.target].type_id == zone_type_id), None)
        
        if not zone: return []
        
        rel_type_id = self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary")
        card_rels = self.get_relationships(target=zone, rel_type=rel_type_id)
        return [self.entities[r.source] for r in card_rels]

    def get_controller_id(self, entity: Entity) -> Optional[uuid.UUID]:
        """Returns the player ID who controls the given entity."""
        rel_type_id = self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary")
        rels = [r for r in self.relationships if r.target == entity.instance_id and r.type_id == rel_type_id]
        if rels: return rels[0].source
        return None

    def get_controller(self, entity: Entity) -> Optional[Entity]:
        """Returns the player entity who controls the given entity."""
        controller_id = self.get_controller_id(entity)
        return self.entities.get(controller_id) if controller_id else None

    def get_zone(self, player_id: uuid.UUID, zone_type_id: int) -> Optional[Entity]:
        """Helper to find a specific zone entity for a player."""
        player = self.entities.get(player_id)
        if not player: return None
        control_rels = self.get_relationships(source=player, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
        for r in control_rels:
            target = self.entities.get(r.target)
            if target and target.type_id == zone_type_id:
                return target
        return None
