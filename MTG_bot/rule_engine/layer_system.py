"""
This file defines the Layer System, which is responsible for applying continuous effects
in the correct order according to Magic: The Gathering rules.
"""

from typing import Dict, Any
from .game_graph import GameGraph
from .rulebook import Rulebook
from .card_database import CREATURE_STATS, CARD_ABILITIES, ABILITY_EFFECT_PARAMS
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config

class LayerSystem:
    """Applies continuous effects in the correct order (layers)."""
    def __init__(self, rulebook: Rulebook):
        self.rulebook = rulebook
        self.id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)

    def apply_all_layers(self, graph: GameGraph):
        """Applies all continuous effects to the game state in layer order."""
        # For now, we only implement Layer 7 (Power/Toughness changing effects)
        self._apply_layer_7(graph)

    def _apply_layer_7(self, graph: GameGraph):
        """Applies power/toughness changing effects (Layer 7)."""
        # print("Applying layer system...")
        all_creatures = [c for c in graph.entities.values() if c.type_id in CREATURE_STATS.keys()]

        for creature in all_creatures:
            # Reset effective P/T to base stats
            base_stats = CREATURE_STATS.get(creature.type_id, {'power': 0, 'toughness': 0})
            creature.properties['effective_power'] = base_stats['power']
            creature.properties['effective_toughness'] = base_stats['toughness']
            creature.properties['damage_taken'] = 0 # Reset damage for new P/T calculation

            # Find Auras enchanting this creature
            enchanting_auras = [graph.entities[r.source] for r in graph.get_relationships(target=creature, rel_type=self.id_mapper.get_id_by_name("Enchanted By", "game_vocabulary"))]

            for aura in enchanting_auras:
                # Check if the aura grants P/T bonuses
                aura_abilities = CARD_ABILITIES.get(aura.type_id, [])
                if self.id_mapper.get_id_by_name("Grant P T", "game_vocabulary") in aura_abilities:
                    effect_params = ABILITY_EFFECT_PARAMS.get(self.id_mapper.get_id_by_name("Grant P T", "game_vocabulary"), {})
                    power_bonus = effect_params.get('power_bonus', 0)
                    toughness_bonus = effect_params.get('toughness_bonus', 0)

                    creature.properties['effective_power'] += power_bonus
                    creature.properties['effective_toughness'] += toughness_bonus

        # print("Layer system applied.")

    def _apply_layer(self, graph: GameGraph, layer: int):
        """A generic function to apply effects for a given layer."""
        # In a real implementation, you would find all entities that generate
        # continuous effects for this layer and ask the rulebook to execute them.
        pass

    def _apply_power_toughness_layer(self, graph: GameGraph):
        """Layer 7 is special as it has its own sub-layers."""
        # 7a: P/T setting from characteristic-defining abilities
        # 7b: P/T setting effects
        # 7c: Effects that modify P/T (e.g., +1/+1 counters)
        # 7d: P/T switching effects
        pass
