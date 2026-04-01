import uuid
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, field
from .game_graph import GameGraph, Entity

@dataclass
class ContinuousEffect:
    source_id: uuid.UUID
    effect_data: Dict[str, Any]
    duration: str # 'until_end_of_turn', 'indefinite', 'as_long_as_on_battlefield'
    layer: int # 1-7
    target_id: Optional[uuid.UUID] = None # For specific targets (like buff spells)
    target_filter: Optional[Any] = None # For static abilities (like "creatures you control")
    id: uuid.UUID = field(default_factory=uuid.uuid4)

class EffectManager:
    """
    Manages active continuous effects and their life cycles.
    """
    def __init__(self):
        self.active_effects: List[ContinuousEffect] = []

    def add_effect(self, effect: ContinuousEffect):
        self.active_effects.append(effect)

    def expire_effects(self, duration_type: str):
        """Removes effects that have reached their expiration condition."""
        self.active_effects = [e for e in self.active_effects if e.duration != duration_type]

    def get_effects_for_layer(self, layer: int) -> List[ContinuousEffect]:
        return [e for e in self.active_effects if e.layer == layer]

    def remove_effects_from_source(self, source_id: uuid.UUID):
        self.active_effects = [e for e in self.active_effects if e.source_id != source_id]
