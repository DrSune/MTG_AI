import re
import json
from typing import List, Optional, Dict, Any
from ..game_graph import GameGraph, Entity
from .. import vocabulary as vocab
from . import mana_handlers
from ..target_filtering import get_valid_targets
from MTG_bot.utils.logger import setup_logger

logger = setup_logger(__name__)

def apply_damage(graph: GameGraph, source: Entity, target: Entity, amount: int):
    """Applies damage to a target (Player or Creature)."""
    if target.type_id == vocab.ID_PLAYER:
        target.properties['life_total'] = target.properties.get('life_total', 20) - amount
        logger.info(f"{source.properties.get('name', 'Source')} deals {amount} damage to {target.properties.get('name')}. New life: {target.properties['life_total']}")
    elif target.properties.get("is_creature"):
        target.properties['damage_taken'] = target.properties.get('damage_taken', 0) + amount
        logger.info(f"{source.properties.get('name', 'Source')} deals {amount} damage to creature {target.properties.get('name')}.")

def apply_draw(graph: GameGraph, player: Entity, amount: int):
    """Causes a player to draw cards."""
    logger.info(f"{player.properties.get('name')} draws {amount} card(s).")
    for _ in range(amount):
        graph.draw_card(player)

def apply_gain_life(graph: GameGraph, player: Entity, amount: int):
    """Causes a player to gain life."""
    player.properties['life_total'] = player.properties.get('life_total', 20) + amount
    logger.info(f"{player.properties.get('name')} gains {amount} life. New life: {player.properties['life_total']}")

def apply_destroy(graph: GameGraph, target: Entity):
    """Destroys a target permanent."""
    controller = graph.get_controller(target)
    
    if controller:
        control_rels = graph.get_relationships(source=controller, rel_type=vocab.ID_REL_CONTROLLED_BY)
        graveyard_zone = next((graph.entities[r.target] for r in control_rels if graph.entities[r.target].type_id == vocab.ID_ZONE_GRAVEYARD), None)
        if graveyard_zone:
            graph._move_card_to_zone(target, graveyard_zone)
            logger.info(f"{target.properties.get('name')} was destroyed and moved to graveyard.")
        else:
            logger.warning(f"Could not find graveyard for {controller.properties.get('name')}.")
    else:
        logger.warning(f"Could not find controller for {target.properties.get('name')} to destroy it.")

def get_spell_potential_targets(graph: GameGraph, card: Entity) -> List[Entity]:
    """
    Returns a list of valid targets for a spell based on its structured effects.
    """
    targets = []
    effects = card.properties.get("effects", [])
    source_player = graph.get_controller(card)
    if not source_player:
        return []

    for effect in effects:
        target_criteria = effect.get("target")
        if target_criteria:
            valid_for_this_effect = get_valid_targets(graph, source_player, target_criteria)
            targets.extend(valid_for_this_effect)
    
    unique_targets = {t.instance_id: t for t in targets}
    return list(unique_targets.values())

def resolve_spell_effects(graph: GameGraph, player: Entity, card: Entity, target_id: Optional[str] = None, effect_manager=None):
    """
    Applies a spell's effects using structured data from card.properties['effects'].
    """
    effects = card.properties.get("effects", [])
    target = graph.entities.get(target_id) if target_id else None
    
    if not effects:
        logger.warning(f"No structured effects for {card.properties.get('name')}. Using fallback text parsing.")
        _resolve_spell_effects_fallback(graph, player, card, target)
        return

    from ..effect_manager import ContinuousEffect

    for effect in effects:
        ability_type = effect.get("ability_type")
        
        if ability_type == "deal_damage" and target:
            apply_damage(graph, card, target, effect.get("amount", 0))
            
        elif ability_type == "destroy" and target:
            apply_destroy(graph, target)
            
        elif ability_type == "draw_cards":
            apply_draw(graph, player, effect.get("amount", 1))
            
        elif ability_type == "gain_life":
            apply_gain_life(graph, player, effect.get("amount", 0))
            
        elif ability_type == "add_counter" and target:
            if effect.get("counter_type") == "+1/+1":
                # Permanent counters are tricky, for now we apply to base properties
                target.properties['power'] = int(target.properties.get('power', 0)) + 1
                target.properties['toughness'] = int(target.properties.get('toughness', 0)) + 1
                logger.info(f"Put a +1/+1 counter on {target.properties.get('name')}.")

        elif ability_type == "temporary_stat_modifier" and effect_manager:
            # Handle effects like "+2/+0 until end of turn"
            actual_target = target
            if effect.get("applies_to") == "self":
                actual_target = card
            
            if actual_target:
                new_effect = ContinuousEffect(
                    source_id=card.instance_id,
                    target_id=actual_target.instance_id,
                    effect_data=effect.get("effect"),
                    duration=effect.get("duration", "until_end_of_turn"),
                    layer=7
                )
                effect_manager.add_effect(new_effect)
                logger.info(f"Added temporary effect to {actual_target.properties.get('name')}.")

def _resolve_spell_effects_fallback(graph: GameGraph, player: Entity, card: Entity, target: Optional[Entity]):
    """Original regex-based fallback."""
    card_text = card.properties.get("text", "").lower()
    
    # 1. Damage Effect
    damage_match = re.search(r'deals (\d+) damage', card_text)
    if damage_match and target:
        amount = int(damage_match.group(1))
        apply_damage(graph, card, target, amount)
        
    # 2. Destroy Effect
    if "destroy target" in card_text and target:
        apply_destroy(graph, target)
        
    # 3. Draw Effect
    draw_match = re.search(r'draw (a|one|two|three|four|five|\d+) card', card_text, re.IGNORECASE | re.DOTALL)
    if draw_match:
        val = draw_match.group(1)
        mapping = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5}
        amount = int(val) if val.isdigit() else mapping.get(val, 1)
        apply_draw(graph, player, amount)
