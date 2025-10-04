"""
This file defines the foundational data structures for the entire rule engine.
The game state is represented as a graph of generic entities and their relationships.
"""

import uuid
from typing import Dict, Any, List, Optional

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
