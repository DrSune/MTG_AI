import re
import json
import random
from typing import List, Optional, Dict, Any
from ..game_graph import GameGraph, Entity
from .. import vocabulary as vocab
from . import mana_handlers
from ..target_filtering import get_valid_targets
from MTG_bot.utils.logger import setup_logger

logger = setup_logger(__name__)

def apply_damage(graph: GameGraph, source: Entity, target: Entity, amount: int):
    """Applies damage to a target (Player or Creature)."""
    # 1. Check for Replacement Effects (Generalized)
    for eid, entity in list(graph.entities.items()):
        if not entity.properties.get('is_on_battlefield'): continue
        repl = entity.properties.get('replacement_effect')
        if repl and repl.get('event') == "damage" and repl.get('target_type') == "controller":
            if graph.get_controller_id(entity) == target.instance_id:
                if _handle_replacement(graph, entity, repl, "damage", source, target, amount):
                    return

    # 2. Protection Enforcement
    protections = target.properties.get("protections_from_names", [])
    if "protection_from_name" in target.properties:
        protections.append(target.properties["protection_from_name"])
    
    source_name = source.properties.get("name")
    if not source_name:
        from .. import card_database
        card_data = card_database.card_data_loader.get_card_data_by_id(source.type_id)
        if card_data: source_name = card_data.get("name")

    if protections and source_name in protections:
        logger.info(f"Damage from {source_name} to {target.properties.get('name')} prevented by protection.")
        return

    # 3. Apply Damage
    if target.type_id == vocab.ID_PLAYER:
        target.properties['life_total'] = target.properties.get('life_total', 20) - amount
        logger.info(f"{source.properties.get('name', 'Source')} deals {amount} damage to {target.properties.get('name')}.")
    elif target.properties.get("is_creature"):
        target.properties['damage_taken'] = target.properties.get('damage_taken', 0) + amount
        logger.info(f"{source.properties.get('name', 'Source')} deals {amount} damage to {target.properties.get('name')}.")

def _handle_replacement(graph: GameGraph, host: Entity, effect: Dict[str, Any], event_type: str, source: Entity, target: Entity, value: Any) -> bool:
    """Processes a replacement effect. Returns True if the original event was consumed."""
    action = effect.get('action')
    
    if action == "prevent_and_counter":
        # Nine Lives pattern
        counters = host.properties.get('reincarnation_counters', 0)
        host.properties['reincarnation_counters'] = counters + 1
        logger.info(f"{host.properties.get('name')} replaced {event_type}. Added counter ({counters + 1}).")
        return True
        
    if action == "draw_twice" and event_type == "draw":
        # Teferi's Ageless Insight pattern
        # We need a recursion guard to prevent infinite loops if we just call apply_draw again
        if not hasattr(graph, '_in_replacement'): graph._in_replacement = False
        if graph._in_replacement: return False
        
        graph._in_replacement = True
        apply_draw(graph, target, 2)
        graph._in_replacement = False
        return True
        
    return False

def apply_draw(graph: GameGraph, player: Entity, amount: Any):
    # Check for Draw replacements
    for eid, entity in list(graph.entities.items()):
        if not entity.properties.get('is_on_battlefield'): continue
        repl = entity.properties.get('replacement_effect')
        if repl and repl.get('event') == "draw":
            if graph.get_controller_id(entity) == player.instance_id:
                if _handle_replacement(graph, entity, repl, "draw", entity, player, amount):
                    return

    try: amount = int(amount)
    except: amount = 1
    
    for _ in range(amount):
        graph.draw_card(player)
        # Update turn draw count
        player.properties['cards_drawn_this_turn'] = player.properties.get('cards_drawn_this_turn', 0) + 1
        # Check triggers
        from . import triggered_ability_handlers
        triggered_ability_handlers.check_triggers(graph, "draw_card", player)

def apply_gain_life(graph: GameGraph, player: Entity, amount: int):
    player.properties['life_total'] = player.properties.get('life_total', 20) + amount
    logger.info(f"{player.properties.get('name')} gains {amount} life.")
    from . import triggered_ability_handlers
    triggered_ability_handlers.check_triggers(graph, "gain_life", player)

def apply_destroy(graph: GameGraph, target: Entity):
    if target.properties.get("indestructible"): return
    controller = graph.get_controller(target)
    if controller:
        gy = graph.get_zone(controller.instance_id, vocab.ID_ZONE_GRAVEYARD)
        if gy: graph._move_card_to_zone(target, gy)

def get_spell_potential_targets(graph: GameGraph, card: Entity) -> List[Entity]:
    targets = []
    effects = card.properties.get("effects", [])
    source_player = graph.get_controller(card)
    if not source_player: return []
    for effect in effects:
        criteria = effect.get("target")
        if criteria: targets.extend(get_valid_targets(graph, source_player, criteria, source_card=card))
    return list({t.instance_id: t for t in targets}.values())

def resolve_atomic_effect(graph: GameGraph, player: Entity, source: Entity, effect: Dict[str, Any], target: Optional[Entity] = None):
    ability_type = effect.get("ability_type")
    if ability_type == "modal_ability":
        modes = effect.get("modes", [])
        if modes:
            for sub in modes[0].get("effects", []): resolve_atomic_effect(graph, player, source, sub, target)
        return
    if ability_type == "conditional_effect":
        if evaluate_condition(graph, player, effect.get("condition")):
            for sub in effect.get("effects", []): resolve_atomic_effect(graph, player, source, sub, target)
        return
    if not target and effect.get("target"):
        valid = get_valid_targets(graph, player, effect.get("target"), source_card=source)
        if valid: target = valid[0]
        
    if ability_type == "deal_damage" and target: apply_damage(graph, source, target, effect.get("amount", 0))
    elif ability_type == "destroy" and target: apply_destroy(graph, target)
    elif ability_type == "draw_cards": apply_draw(graph, player, effect.get("amount", 1))
    elif ability_type == "gain_life": apply_gain_life(graph, player, effect.get("amount", 0))
    elif ability_type == "add_counter" and target:
        if effect.get("counter_type") == "+1/+1":
            target.properties['power'] = int(target.properties.get('power', 0)) + 1
            target.properties['toughness'] = int(target.properties.get('toughness', 0)) + 1
    elif ability_type == "animate_permanent" and source:
        source.properties['is_creature'] = True
        source.properties['power'] = effect.get("power", 3)
        source.properties['toughness'] = effect.get("toughness", 3)
        source.properties.setdefault('abilities', {}).setdefault('keywords', []).append("Flying")
    elif ability_type == "create_token":
        # Jolrael pattern
        from .. import game_initializer
        token = graph.add_entity(vocab.ID_ENTITY_CREATURE_TOKEN if hasattr(vocab, "ID_ENTITY_CREATURE_TOKEN") else 999)
        token.properties.update({
            "name": effect.get("name", "Token"),
            "power": effect.get("power", 1),
            "toughness": effect.get("toughness", 1),
            "is_creature": True,
            "is_on_battlefield": True
        })
        graph.add_relationship(player, token, vocab.ID_REL_CONTROLLED_BY)
        graph._move_card_to_zone(token, graph.get_zone(player.instance_id, vocab.ID_ZONE_BATTLEFIELD))

def evaluate_condition(graph: GameGraph, player: Entity, condition_text: str) -> bool:
    condition_text = condition_text.lower()
    if "you control a creature" in condition_text:
        return any(e.properties.get("is_creature") and e.properties.get("is_on_battlefield") for e in graph.entities.values() if graph.get_controller_id(e) == player.instance_id)
    return True

def resolve_spell_effects(graph: GameGraph, player: Entity, card: Entity, target_id: Optional[str] = None, effect_manager=None):
    effects = card.properties.get("effects", [])
    target = graph.entities.get(target_id) if target_id else None
    for effect in effects:
        resolve_atomic_effect(graph, player, card, effect, target)
