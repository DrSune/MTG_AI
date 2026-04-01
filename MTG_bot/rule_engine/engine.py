print("--- Executing engine.py ---")
import uuid
import random
from typing import List, Union, Optional

from .game_graph import GameGraph, Entity
from . import card_database, vocabulary as vocab
from .handlers import mana_handlers, combat_handlers, keyword_handlers, effect_handlers
from .effect_manager import EffectManager
from .layer_system import LayerSystem
from .actions import (
    PlayLandAction,
    CastSpellAction,
    ActivateManaAbilityAction,
    DeclareAttackerAction,
    DeclareBlockerAction,
    PassPriorityAction,
    PassTurnAction,
)
from MTG_bot.utils.logger import setup_logger
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config

# A type alias for any possible game action
AnyAction = Union[
    PlayLandAction,
    CastSpellAction,
    ActivateManaAbilityAction,
    DeclareAttackerAction,
    DeclareBlockerAction,
    PassPriorityAction,
    PassTurnAction,
]

logger = setup_logger(__name__)

class Engine:
    """The main game engine.

    Responsibilities:
    - Determining all legal moves for the current player.
    - Executing a chosen move and updating the game state.
    """
    def __init__(self, graph: GameGraph, manual_mode: bool = False):
        self.graph = graph
        self.id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)
        self.manual_mode = manual_mode
        self.effect_manager = EffectManager()
        self.layer_system = LayerSystem(self.effect_manager)
        logger.info("Engine initialized.")

    def _get_card_display_name(self, card: Entity) -> str:
        """Returns a readable name for a card entity."""
        if not card:
            return "Unknown Card"
        name = card.properties.get("name")
        if name:
            return name
        card_data = card_database.card_data_loader.get_card_data_by_id(card.type_id)
        if card_data and card_data.get("name"):
            return card_data["name"]
        mapped_name = self.id_mapper.get_name(card.type_id, "cards")
        if mapped_name:
            return mapped_name
        return str(card.type_id)

    def _prompt_cards_to_bottom(self, cards: List[Entity], count: int) -> List[Entity]:
        """Interactive selection for manual mode mulligans."""
        while True:
            print(f"\nChoose {count} card{'s' if count != 1 else ''} to place on the bottom of your library:")
            for idx, card in enumerate(cards, start=1):
                print(f"  {idx}. {self._get_card_display_name(card)}")
            prompt = f"Enter {count} card number{'s' if count != 1 else ''} to bottom (space-separated): "
            choice = input(prompt).strip()
            try:
                indices = sorted({int(token) for token in choice.split()})
            except ValueError:
                print("Invalid input. Please enter numeric choices.")
                continue
            if len(indices) != count:
                print(f"Please select exactly {count} unique card{'s' if count != 1 else ''}.")
                continue
            if any(idx < 1 or idx > len(cards) for idx in indices):
                print("Selection out of range. Try again.")
                continue
            return [cards[idx - 1] for idx in indices]

    def _can_pay_cost(self, mana_pool: dict, cost: dict) -> bool:
        """Checks if a player's mana pool can pay a given cost."""
        temp_pool = mana_pool.copy()
        for mana_type, amount in cost.items():
            if mana_type == self.id_mapper.get_id_by_name("Generic Mana", "game_vocabulary"):
                continue
            if temp_pool.get(mana_type, 0) < amount:
                return False
            temp_pool[mana_type] -= amount

        generic_mana_id = self.id_mapper.get_id_by_name("Generic Mana", "game_vocabulary")
        generic_cost = cost.get(generic_mana_id, 0)
        total_remaining_mana = sum(temp_pool.values())
        return total_remaining_mana >= generic_cost

    def get_legal_moves(self) -> List[AnyAction]:
        """Calculates and returns a list of all possible legal moves for the active player."""
        legal_moves: List[AnyAction] = []
        active_player = self.graph.entities[self.graph.active_player_id]
        mana_pool = active_player.properties.get('mana_pool', {})
        
        pre_main_id = self.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary")
        post_main_id = self.id_mapper.get_id_by_name("Post-Combat Main Phase", "game_vocabulary")
        is_main_phase = self.graph.phase in [pre_main_id, post_main_id]
        
        logger.debug(f"Calculating legal moves for Player {active_player.properties.get('name', active_player.instance_id)[:4]} (Turn {self.graph.turn_number}, Phase {self.graph.phase}, Step {self.graph.step})")

        try:
            # Find player's hand
            control_rels = self.graph.get_relationships(source=active_player, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
            hand_zone = next((self.graph.entities[r.target] for r in control_rels if self.graph.entities[r.target].type_id == self.id_mapper.get_id_by_name("Hand", "game_vocabulary")), None)

            # 1. Check for playing a land (Active player, Main Phase only)
            if is_main_phase and active_player.properties.get('lands_played_this_turn', 0) < 1 and hand_zone:
                card_in_hand_rels = self.graph.get_relationships(target=hand_zone, rel_type=self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))
                cards_in_hand = [self.graph.entities[r.source] for r in card_in_hand_rels]
                land_cards = [card for card in cards_in_hand if card.properties.get('is_land')]
                for land in land_cards:
                    legal_moves.append(PlayLandAction(player_id=active_player.instance_id, card_id=land.instance_id))
                    logger.debug(f"Found PlayLandAction for {land.properties.get('name', land.type_id)} ({land.type_id})")
                    break

            # 2. Check for tapping lands for mana (Anytime)
            mana_moves = mana_handlers.get_tap_for_mana_moves(self.graph, active_player)
            legal_moves.extend(mana_moves)

            # 3. Check for casting spells
            if hand_zone:
                card_in_hand_rels = self.graph.get_relationships(target=hand_zone, rel_type=vocab.ID_REL_IS_IN_ZONE)
                cards_in_hand = [self.graph.entities[r.source] for r in card_in_hand_rels]
                for card in cards_in_hand:
                    is_instant = card.properties.get("is_instant", False)
                    if not is_instant and not is_main_phase:
                        continue

                    cost = card_database.get_card_cost(card.type_id)
                    if cost and self._can_pay_cost(mana_pool, cost):
                        potential_targets = effect_handlers.get_spell_potential_targets(self.graph, card)
                        if potential_targets:
                            for target in potential_targets:
                                legal_moves.append(CastSpellAction(player_id=active_player.instance_id, card_id=card.instance_id, target_id=target.instance_id))
                        else:
                            legal_moves.append(CastSpellAction(player_id=active_player.instance_id, card_id=card.instance_id))
                        
                        logger.debug(f"Found CastSpellAction for {card.properties.get('name', card.type_id)} ({card.type_id}) with cost {cost}")

            # 4. Check for declaring attackers
            if self.graph.step == self.id_mapper.get_id_by_name("Declare Attackers Step", "game_vocabulary"):
                attackers = combat_handlers.get_legal_attackers(self.graph, active_player.instance_id)
                for attacker in attackers:
                    legal_moves.append(DeclareAttackerAction(player_id=active_player.instance_id, card_id=attacker.instance_id))
                    logger.debug(f"Found DeclareAttackerAction for {attacker.properties.get('name', attacker.type_id)} ({attacker.type_id})")

            # 5. Check for declaring blockers
            if self.graph.step == self.id_mapper.get_id_by_name("Declare Blockers Step", "game_vocabulary"):
                non_active_player = next(p for p in self.graph.entities.values() if p.type_id == self.id_mapper.get_id_by_name("Player", "game_vocabulary") and p.instance_id != self.graph.active_player_id)
                if non_active_player:
                    blockers = combat_handlers.get_legal_blockers(self.graph, non_active_player.instance_id)
                    for blocker in blockers:
                        attacking_creatures = [c for c in self.graph.entities.values() if c.properties.get('is_attacking')]
                        for attacker in attacking_creatures:
                            legal_moves.append(DeclareBlockerAction(player_id=non_active_player.instance_id, blocker_id=blocker.instance_id, attacker_id=attacker.instance_id))

            # 6. Pass priority/Turn
            legal_moves.append(PassPriorityAction(player_id=active_player.instance_id))
            if is_main_phase:
                legal_moves.append(PassTurnAction(player_id=active_player.instance_id))

        except Exception as e:
            logger.error(f"Error calculating legal moves: {e}", exc_info=True)

        return legal_moves

    def execute_move(self, move: AnyAction):
        """Updates the game state by executing the given action."""
        try:
            if hasattr(move, 'player_id'):
                player = self.graph.entities[move.player_id]
            
            if hasattr(move, 'card_id'):
                card = self.graph.entities[move.card_id]

            if isinstance(move, PlayLandAction):
                control_rels = self.graph.get_relationships(source=player, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
                battlefield_zone = next((self.graph.entities[r.target] for r in control_rels if self.graph.entities[r.target].type_id == self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary")), None)
                if battlefield_zone:
                    self.graph._move_card_to_zone(card, battlefield_zone)
                    player.properties['lands_played_this_turn'] = player.properties.get('lands_played_this_turn', 0) + 1
                    logger.info(f"{player.properties.get('name')} played {card.properties.get('name')} to battlefield.")
            
            elif isinstance(move, ActivateManaAbilityAction):
                mana_handlers.execute_tap_for_mana(self.graph, player, card, move.ability_id)
                logger.info(f"{player.properties.get('name')} tapped {card.properties.get('name')} for mana.")

            elif isinstance(move, CastSpellAction):
                cost = card_database.get_card_cost(card.type_id)
                mana_pool = player.properties['mana_pool']
                for mana_type, amount in cost.items():
                    if mana_type != self.id_mapper.get_id_by_name("Generic Mana", "game_vocabulary"):
                        mana_pool[mana_type] -= amount
                generic_cost = cost.get(self.id_mapper.get_id_by_name("Generic Mana", "game_vocabulary"), 0)
                for mana_type in mana_pool:
                    spend = min(generic_cost, mana_pool[mana_type])
                    mana_pool[mana_type] -= spend
                    generic_cost -= spend
                    if generic_cost == 0: break
                
                # Resolve effects (Instants/Sorceries OR ETBs for permanents)
                effect_handlers.resolve_spell_effects(self.graph, player, card, move.target_id, effect_manager=self.effect_manager)

                if card.properties.get("is_instant") or card.properties.get("is_sorcery"):
                    control_rels = self.graph.get_relationships(source=player, rel_type=vocab.ID_REL_CONTROLLED_BY)
                    graveyard_zone = next((self.graph.entities[r.target] for r in control_rels if self.graph.entities[r.target].type_id == vocab.ID_ZONE_GRAVEYARD), None)
                    self.graph._move_card_to_zone(card, graveyard_zone)
                else:
                    control_rels = self.graph.get_relationships(source=player, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
                    battlefield_zone = next((self.graph.entities[r.target] for r in control_rels if self.graph.entities[r.target].type_id == self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary")), None)
                    self.graph._move_card_to_zone(card, battlefield_zone)
                    card.properties['turn_entered'] = self.graph.turn_number
                    if card.properties.get('is_creature'):
                        card.properties['has_summoning_sickness'] = True

            elif isinstance(move, DeclareAttackerAction):
                combat_handlers.declare_attacker(self.graph, card)

            elif isinstance(move, DeclareBlockerAction):
                blocker = self.graph.entities[move.blocker_id]
                attacker = self.graph.entities[move.attacker_id]
                self.graph.add_relationship(blocker, attacker, self.id_mapper.get_id_by_name("Blocking", "game_vocabulary"))

            elif isinstance(move, PassPriorityAction):
                self.progress_phase_and_step()

            elif isinstance(move, PassTurnAction):
                self.end_turn(move.player_id)

            # Apply layer system after any state change
            self.layer_system.apply_all_layers(self.graph)

        except Exception as e:
            logger.error(f"Error executing move {move}: {e}", exc_info=True)

    def progress_phase_and_step(self, force_next_phase: bool = False):
        beginning_phase_id = self.id_mapper.get_id_by_name("Beginning Phase", "game_vocabulary")
        mulligan_phase_id = self.id_mapper.get_id_by_name("Mulligan Phase", "game_vocabulary")
        
        turn_phases = [
            beginning_phase_id,
            self.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary"),
            self.id_mapper.get_id_by_name("Combat Phase", "game_vocabulary"),
            self.id_mapper.get_id_by_name("Post-Combat Main Phase", "game_vocabulary"),
            self.id_mapper.get_id_by_name("Ending Phase", "game_vocabulary"),
        ]

        phase_steps = {
            beginning_phase_id: [
                self.id_mapper.get_id_by_name("Untap Step", "game_vocabulary"),
                self.id_mapper.get_id_by_name("Upkeep Step", "game_vocabulary"),
                self.id_mapper.get_id_by_name("Draw Step", "game_vocabulary"),
            ],
            self.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary"): [
                self.id_mapper.get_id_by_name("Pre-Combat Main Step", "game_vocabulary"),
            ],
            self.id_mapper.get_id_by_name("Combat Phase", "game_vocabulary"): [
                self.id_mapper.get_id_by_name("Beginning of Combat Step", "game_vocabulary"),
                self.id_mapper.get_id_by_name("Declare Attackers Step", "game_vocabulary"),
                self.id_mapper.get_id_by_name("Declare Blockers Step", "game_vocabulary"),
                self.id_mapper.get_id_by_name("Combat Damage Step", "game_vocabulary"),
                self.id_mapper.get_id_by_name("End of Combat Step", "game_vocabulary"),
            ],
            self.id_mapper.get_id_by_name("Post-Combat Main Phase", "game_vocabulary"): [
                self.id_mapper.get_id_by_name("Post-Combat Main Step", "game_vocabulary"),
            ],
            self.id_mapper.get_id_by_name("Ending Phase", "game_vocabulary"): [
                self.id_mapper.get_id_by_name("End of Turn Step", "game_vocabulary"),
                self.id_mapper.get_id_by_name("Cleanup Step", "game_vocabulary"),
            ],
        }

        current_step_list = phase_steps.get(self.graph.phase, [])
        try:
            current_step_index = current_step_list.index(self.graph.step)
        except ValueError:
            current_step_index = -1 

        if not force_next_phase and current_step_index < len(current_step_list) - 1:
            self.graph.step = current_step_list[current_step_index + 1]
        else:
            if self.graph.phase == mulligan_phase_id:
                self.graph.phase = beginning_phase_id
            elif self.graph.phase in turn_phases:
                idx = turn_phases.index(self.graph.phase)
                self.graph.phase = turn_phases[(idx + 1) % len(turn_phases)]
            else:
                self.graph.phase = beginning_phase_id
            
            if self.graph.phase == beginning_phase_id:
                self.graph.turn_number += 1
                all_players = [p for p in self.graph.entities.values() if p.type_id == vocab.ID_PLAYER]
                next_player = next(p for p in all_players if p.instance_id != self.graph.active_player_id)
                self.graph.active_player_id = next_player.instance_id
                
                # Reset turn-based properties
                next_player.properties['lands_played_this_turn'] = 0
                for c in self.graph.entities.values():
                    if c.properties.get('is_creature'):
                        # Simplification: Untap all creatures controlled by active player
                        if self.graph.get_controller_id(c) == next_player.instance_id:
                            c.properties['tapped'] = False
                            c.properties['has_summoning_sickness'] = False

            new_steps = phase_steps.get(self.graph.phase, [])
            if new_steps: self.graph.step = new_steps[0]

        # Cleanup Step: Expire effects
        if self.graph.step == self.id_mapper.get_id_by_name("Cleanup Step", "game_vocabulary"):
            self.effect_manager.expire_effects("until_end_of_turn")
            self.layer_system.apply_all_layers(self.graph)

    def end_turn(self, player_id: uuid.UUID):
        starting_player = self.graph.active_player_id
        safety = 0
        while self.graph.active_player_id == starting_player and safety < 20:
            self.progress_phase_and_step(force_next_phase=True)
            safety += 1

    def get_reward(self, player_id: uuid.UUID) -> float:
        is_game_over, winner_id = self._check_win_loss_conditions()
        if is_game_over:
            return 1.0 if player_id == winner_id else -1.0
        return 0.0

    def _check_win_loss_conditions(self):
        for pid, p in self.graph.entities.items():
            if p.type_id == vocab.ID_PLAYER and p.properties.get('life_total', 20) <= 0:
                winner = next(op for opid, op in self.graph.entities.items() if op.type_id == vocab.ID_PLAYER and opid != pid)
                return True, winner.instance_id
        return False, None
