"""
This file defines the Layer System, which is responsible for applying continuous effects
in the correct order according to Magic: The Gathering rules.
"""

from typing import Dict, Any, List
from .game_graph import GameGraph, Entity
from .effect_manager import EffectManager, ContinuousEffect
from .target_filtering import TargetFilter
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config

class LayerSystem:
    """Applies continuous effects in the correct order (layers)."""
    def __init__(self, effect_manager: EffectManager):
        self.effect_manager = effect_manager
        self.id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)

    def apply_all_layers(self, graph: GameGraph):
        """Applies all continuous effects to the game state in layer order."""
        # 0. Hydrate static effects from permanents on battlefield
        self._hydrate_static_effects(graph)

        # Reset stats first
        self._reset_to_base_characteristics(graph)
        
        # Layer 1: Copy effects
        self._apply_layer(graph, 1)
        # Layer 2: Control-changing effects
        self._apply_layer(graph, 2)
        # Layer 3: Text-changing effects
        self._apply_layer(graph, 3)
        # Layer 4: Type-changing effects
        self._apply_layer(graph, 4)
        # Layer 5: Color-changing effects
        self._apply_layer(graph, 5)
        # Layer 6: Ability-granting/removing effects
        self._apply_layer(graph, 6)
        # Layer 7: Power/Toughness changing effects
        self._apply_layer(graph, 7)

    def _hydrate_static_effects(self, graph: GameGraph):
        """
        Scans the battlefield for permanents with static abilities 
        and adds them to the effect manager if they aren't already there.
        For now, we remove all 'as_long_as_on_battlefield' and re-add them.
        """
        self.effect_manager.expire_effects("as_long_as_on_battlefield")
        
        battlefield_zone_id = self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary")
        is_in_zone_rel_id = self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary")
        
        # Find all permanents on battlefield
        for entity in graph.entities.values():
            # Check if entity is in a battlefield zone
            zone_rels = graph.get_relationships(source=entity, rel_type=is_in_zone_rel_id)
            on_battlefield = False
            for r in zone_rels:
                zone = graph.entities.get(r.target)
                if zone and zone.type_id == battlefield_zone_id:
                    on_battlefield = True
                    break
            
            if on_battlefield:
                # Check for static effects in properties
                effects = entity.properties.get("effects", [])
                for eff_data in effects:
                    if eff_data.get("ability_type") == "continuous_effect":
                        new_effect = ContinuousEffect(
                            source_id=entity.instance_id,
                            effect_data=eff_data.get("effect"),
                            duration="as_long_as_on_battlefield",
                            layer=eff_data.get("layer", 7),
                            target_filter=eff_data.get("target_filter") or eff_data.get("filter")
                        )
                        self.effect_manager.add_effect(new_effect)

    def _reset_to_base_characteristics(self, graph: GameGraph):
        """Resets all permanents to their base P/T before layers apply."""
        for entity in graph.entities.values():
            if entity.properties.get('is_on_battlefield'):
                def safe_int(val):
                    if val is None: return 0
                    if isinstance(val, int): return val
                    s = str(val).strip()
                    if not s or s in ["*", "X"]: return 0
                    try:
                        import re
                        m = re.match(r"(\d+)", s)
                        return int(m.group(1)) if m else 0
                    except: return 0

                entity.properties['effective_power'] = safe_int(entity.properties.get('power', 0))
                entity.properties['effective_toughness'] = safe_int(entity.properties.get('toughness', 0))


    def _apply_layer(self, graph: GameGraph, layer: int):
        """Applies effects for a specific layer."""
        effects = self.effect_manager.get_effects_for_layer(layer)
        for eff in effects:
            source_entity = graph.entities.get(eff.source_id)
            if not source_entity: continue
            
            source_player_id = graph.get_controller_id(source_entity)
            source_player = graph.entities.get(source_player_id) if source_player_id else None
            
            # Static effects like Kaervek might not have a source player if not set up correctly in tests,
            # but in a real game they always will.
            # However, for global filters, we MUST have a source player to check 'opponent' etc.
            
            # Determine targets
            targets = []
            if eff.target_id:
                target_entity = graph.entities.get(eff.target_id)
                if target_entity: targets.append(target_entity)
            elif eff.target_filter:
                filter_obj = TargetFilter(eff.target_filter)
                for entity in graph.entities.values():
                    # Only apply to battlefield permanents
                    if self._is_on_battlefield(graph, entity):
                        if filter_obj.matches(graph, source_player, entity):
                            targets.append(entity)
            
            # Apply effect data to targets
            for target in targets:
                self._apply_effect_to_target(eff.effect_data, target, layer)

    def _is_on_battlefield(self, graph: GameGraph, entity: Entity) -> bool:
        battlefield_zone_id = self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary")
        is_in_zone_rel_id = self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary")
        zone_rels = graph.get_relationships(source=entity, rel_type=is_in_zone_rel_id)
        for r in zone_rels:
            zone = graph.entities.get(r.target)
            if zone and zone.type_id == battlefield_zone_id:
                return True
        return False

    def _apply_effect_to_target(self, data: Dict[str, Any], target: Entity, layer: int):
        if layer == 7:
            if data.get('type') == 'stat_modifier':
                target.properties['effective_power'] += data.get('power', 0)
                target.properties['effective_toughness'] += data.get('toughness', 0)
        # Add other layers here as implemented
