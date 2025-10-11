"""
The main public-facing class for the Rule Engine.
It orchestrates all the other components (Graph, Layers, Rulebook)
to produce a list of legal actions.
"""

from .game_graph import GameGraph
from .layer_system import LayerSystem
from .rulebook import Rulebook
from . import vocabulary as vocab
from .actions import PlayLandAction, CastSpellAction, ActivateManaAbilityAction, DeclareAttackerAction, DeclareBlockerAction
from .handlers import mana_handlers, combat_handlers
from .card_database import CARD_COSTS, CREATURE_STATS, CARD_ABILITIES, MANA_ABILITY_MAP

class RuleEngine:
    """The main orchestrator for rule enforcement."""
    def __init__(self):
        self.rulebook = Rulebook()
        self.layer_system = LayerSystem(self.rulebook)

    def get_legal_actions(self, graph: GameGraph) -> list:
        """_summary_

        Args:
            graph (GameGraph): _description_

        Returns:
            list: _description_
        """
        print("RuleEngine: Determining legal actions...")

        self.layer_system.apply_all_layers(graph)

        # --- Handle Turn-Based Actions ---
        # If we are in the combat damage step, assign damage and end action processing for this state.
        if graph.step == vocab.ID_STEP_COMBAT_DAMAGE:
            combat_handlers.assign_combat_damage(graph)
            # After damage is assigned, typically state-based actions are checked (e.g., creature death).
            # For now, we'll just end the action sequence here.
            return []

        active_player = graph.entities.get(graph.active_player_id)
        if not active_player:
            return []

        legal_actions = []

        # --- Find cards in various zones ---
        p_control_rels = graph.get_relationships(source=active_player, rel_type=vocab.ID_REL_CONTROLS)
        hand_zone_entity = next((graph.entities[r.target] for r in p_control_rels if graph.entities[r.target].type_id == vocab.ID_ZONE_HAND), None)
        battlefield_zone_entity = next((graph.entities[r.target] for r in p_control_rels if graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD), None)

        hand_cards = []
        if hand_zone_entity:
            hand_cards = [graph.entities[r.source] for r in graph.get_relationships(target=hand_zone_entity, rel_type=vocab.ID_REL_IS_IN_ZONE)]

        battlefield_cards = []
        if battlefield_zone_entity:
            battlefield_cards = [graph.entities[r.source] for r in graph.get_relationships(target=battlefield_zone_entity, rel_type=vocab.ID_REL_IS_IN_ZONE)]

        # --- Main Phase Actions ---
        if graph.phase in [vocab.ID_PHASE_PRE_COMBAT_MAIN, vocab.ID_PHASE_POST_COMBAT_MAIN]:
            # --- Check for "Play Land" action ---
            if active_player.properties.get('lands_played_this_turn', 0) < 1:
                land_cards_in_hand = [card for card in hand_cards if card.type_id in CARD_ABILITIES]
                for land_card in land_cards_in_hand:
                    action = PlayLandAction(player_id=active_player.instance_id, card_id=land_card.instance_id)
                    legal_actions.append(action)

                    # --- Check for "Cast Spell" action ---
                    spell_cards_in_hand = [card for card in hand_cards if card.type_id in CARD_COSTS]
                    for spell_card in spell_cards_in_hand:
                        cost = CARD_COSTS[spell_card.type_id]
                        if mana_handlers.can_pay_cost(graph, active_player.instance_id, cost):
                            if spell_card.type_id == vocab.ID_CARD_GIANT_STRENGTH: # Auras target creatures
                                # Find all creatures on the battlefield (simplified for now)
                                all_creatures = [c for c in graph.entities.values() if c.type_id in CREATURE_STATS.keys()]
                                for creature in all_creatures:
                                    # For now, any creature is a legal target
                                    action = CastSpellAction(player_id=active_player.instance_id, card_id=spell_card.instance_id, target_id=creature.instance_id)
                                    legal_actions.append(action)
                            else:
                                action = CastSpellAction(player_id=active_player.instance_id, card_id=spell_card.instance_id)
                                legal_actions.append(action)
                    
                    # --- Mana Abilities (can be activated anytime) ---
                    for card in battlefield_cards:
                        if not card.properties.get('tapped', False):
                            if card.type_id in CARD_ABILITIES:
                                for ability_id in CARD_ABILITIES[card.type_id]:
                                    action = ActivateManaAbilityAction(player_id=active_player.instance_id, card_id=card.instance_id, ability_id=ability_id)
                                    legal_actions.append(action)
                    
                    # --- Combat Actions ---
                    if graph.phase == vocab.ID_PHASE_COMBAT:
                        if graph.step == vocab.ID_STEP_DECLARE_ATTACKERS:
                            legal_attackers = combat_handlers.get_legal_attackers(graph, active_player.instance_id)
                            for attacker in legal_attackers:
                                action = DeclareAttackerAction(player_id=active_player.instance_id, card_id=attacker.instance_id)
                                legal_actions.append(action)
                        
                        elif graph.step == vocab.ID_STEP_DECLARE_BLOCKERS:
                            # Find the defending player (not the active player)
                            defending_player = next((p for p in graph.entities.values() if p.type_id == vocab.ID_PLAYER and p.instance_id != graph.active_player_id), None)
                            if defending_player:
                                legal_blockers = combat_handlers.get_legal_blockers(graph, defending_player.instance_id)
                                # Find all attacking creatures
                                all_creatures = [c for c in graph.entities.values() if c.type_id in CARD_COSTS] # Simplified
                                attacking_creatures = [c for c in all_creatures if c.properties.get('is_attacking', False)]
            
                                for blocker in legal_blockers:
                                    for attacker in attacking_creatures:
                                        # In a real game, you can't block your own creatures, etc.
                                        # This is a simplified version.
                                        action = DeclareBlockerAction(player_id=defending_player.instance_id, blocker_id=blocker.instance_id, attacker_id=attacker.instance_id)
                                        legal_actions.append(action)
            
                    print(f"RuleEngine: Found {len(legal_actions)} legal actions.")
                    return legal_actions
            
                def execute_action(self, graph: GameGraph, action):
                    """Applies the effects of a single action to the game state."""
                    print(f"RuleEngine: Executing action: {action}")
                    player = graph.entities[action.player_id]
                    # In most cases, the action is performed with a card.
                    card = graph.entities.get(getattr(action, 'card_id', None) or getattr(action, 'blocker_id', None))
            
                    battlefield_zone_entity = next((graph.entities[r.target] for r in graph.get_relationships(source=player, rel_type=vocab.ID_REL_CONTROLS) if graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD), None)
            
                    if isinstance(action, PlayLandAction):
                        if battlefield_zone_entity:
                            rel_to_update = graph.get_relationships(source=card, rel_type=vocab.ID_REL_IS_IN_ZONE)[0]
                            rel_to_update.target = battlefield_zone_entity.instance_id
                            player.properties['lands_played_this_turn'] = player.properties.get('lands_played_this_turn', 0) + 1
                            card.properties['turn_entered'] = graph.turn_number
                            print(f"RuleEngine: Moved {card.type_id} to battlefield on turn {graph.turn_number}.")
                        else:
                            print("RuleEngine: Error - Could not find battlefield for player.")
            
                    elif isinstance(action, CastSpellAction):
                        cost = CARD_COSTS[card.type_id]
                        mana_handlers.pay_cost(graph, player.instance_id, cost)
                        if battlefield_zone_entity:
                            rel_to_update = graph.get_relationships(source=card, rel_type=vocab.ID_REL_IS_IN_ZONE)[0]
                            rel_to_update.target = battlefield_zone_entity.instance_id
                            card.properties['turn_entered'] = graph.turn_number
                            print(f"RuleEngine: Moved {card.type_id} to battlefield on turn {graph.turn_number}.")
            
                            if action.target_id: # If it's an Aura with a target
                                target_creature = graph.entities[action.target_id]
                                graph.add_relationship(card, target_creature, vocab.ID_REL_ENCHANTED_BY)
                                print(f"RuleEngine: {card.type_id} enchants {target_creature.type_id}.")
            
                        else:
                            print("RuleEngine: Error - Could not find battlefield for player.")
            
                    elif isinstance(action, ActivateManaAbilityAction):
                        card.properties['tapped'] = True
                        mana_type = MANA_ABILITY_MAP[action.ability_id]
                        player.properties['mana_pool'][mana_type] += 1
                        print(f"RuleEngine: Tapped {card.type_id} to add {mana_type}.")
            
                    elif isinstance(action, DeclareAttackerAction):
                        card.properties['tapped'] = True
                        card.properties['is_attacking'] = True
                        print(f"RuleEngine: {card.type_id} is now attacking.")
            
                    elif isinstance(action, DeclareBlockerAction):
                        blocker = graph.entities[action.blocker_id]
                        attacker = graph.entities[action.attacker_id]
                        graph.add_relationship(blocker, attacker, vocab.ID_REL_IS_BLOCKING)
                        print(f"RuleEngine: {blocker.type_id} is now blocking {attacker.type_id}.")
            
                    else:
                        print(f"RuleEngine: Error - Unknown action type: {type(action)}")