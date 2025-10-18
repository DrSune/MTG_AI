print("--- Executing engine.py ---")
import uuid
from typing import List, Union, Optional

from .game_graph import GameGraph, Entity
from . import vocabulary as vocab
from . import card_database
from .handlers import mana_handlers, combat_handlers, keyword_handlers
from .actions import PlayLandAction, CastSpellAction, ActivateManaAbilityAction, DeclareAttackerAction, DeclareBlockerAction, PassTurnAction
from MTG_bot.utils.logger import setup_logger

# A type alias for any possible game action
AnyAction = Union[PlayLandAction, CastSpellAction, ActivateManaAbilityAction, DeclareAttackerAction, DeclareBlockerAction, PassTurnAction]

logger = setup_logger(__name__)

class Engine:
    """The main game engine.

    Responsibilities:
    - Determining all legal moves for the current player.
    - Executing a chosen move and updating the game state.
    """
    def __init__(self, graph: GameGraph):
        self.graph = graph
        logger.info("Engine initialized.")

    def _can_pay_cost(self, mana_pool: dict, cost: dict) -> bool:
        """Checks if a player's mana pool can pay a given cost."""
        temp_pool = mana_pool.copy()
        
        for mana_type, amount in cost.items():
            if mana_type == vocab.ID_MANA_GENERIC:
                continue
            if temp_pool.get(mana_type, 0) < amount:
                return False
            temp_pool[mana_type] -= amount

        generic_cost = cost.get(vocab.ID_MANA_GENERIC, 0)
        total_remaining_mana = sum(temp_pool.values())
        return total_remaining_mana >= generic_cost

    def get_legal_moves(self) -> List[AnyAction]:
        """Calculates and returns a list of all possible legal moves for the active player."""
        legal_moves: List[AnyAction] = []
        active_player = self.graph.entities[self.graph.active_player_id]
        mana_pool = active_player.properties.get('mana_pool', {})
        logger.debug(f"Calculating legal moves for Player {active_player.properties.get('name', active_player.instance_id)[:4]} (Turn {self.graph.turn_number}, Phase {self.graph.phase}, Step {self.graph.step})")

        try:
            # Find player's hand
            control_rels = self.graph.get_relationships(source=active_player, rel_type=vocab.ID_REL_CONTROLS)
            hand_zone = next((self.graph.entities[r.target] for r in control_rels if self.graph.entities[r.target].type_id == vocab.ID_ZONE_HAND), None)

            # 1. Check for playing a land
            if active_player.properties.get('lands_played_this_turn', 0) < 1 and hand_zone:
                card_in_hand_rels = self.graph.get_relationships(target=hand_zone, rel_type=vocab.ID_REL_IS_IN_ZONE)
                cards_in_hand = [self.graph.entities[r.source] for r in card_in_hand_rels]
                land_cards = [card for card in cards_in_hand if card.properties.get('is_land')]
                for land in land_cards:
                    legal_moves.append(PlayLandAction(player_id=active_player.instance_id, card_id=land.instance_id))
                    logger.debug(f"Found PlayLandAction for {land.properties.get('name', land.type_id)} ({land.type_id})")

            # 2. Check for tapping lands for mana
            mana_moves = mana_handlers.get_tap_for_mana_moves(self.graph, active_player)
            legal_moves.extend(mana_moves)
            for move in mana_moves:
                logger.debug(f"Found ActivateManaAbilityAction for {self.graph.entities[move.card_id].properties.get('name', self.graph.entities[move.card_id].type_id)} ({move.card_id}) ")

            # 3. Check for casting spells
            if hand_zone:
                card_in_hand_rels = self.graph.get_relationships(target=hand_zone, rel_type=vocab.ID_REL_IS_IN_ZONE)
                cards_in_hand = [self.graph.entities[r.source] for r in card_in_hand_rels]
                for card in cards_in_hand:
                    cost = card_database.get_card_cost(card.type_id)
                    if cost and self._can_pay_cost(mana_pool, cost):
                        legal_moves.append(CastSpellAction(player_id=active_player.instance_id, card_id=card.instance_id))
                        logger.debug(f"Found CastSpellAction for {card.properties.get('name', card.type_id)} ({card.type_id}) with cost {cost}")

            # 4. Check for declaring attackers
            if self.graph.step == vocab.ID_STEP_DECLARE_ATTACKERS:
                attackers = combat_handlers.get_legal_attackers(self.graph, active_player.instance_id)
                for attacker in attackers:
                    # Only creatures without summoning sickness can attack
                    if not attacker.properties.get('has_summoning_sickness', True):
                        legal_moves.append(DeclareAttackerAction(player_id=active_player.instance_id, card_id=attacker.instance_id))
                        logger.debug(f"Found DeclareAttackerAction for {attacker.properties.get('name', attacker.type_id)} ({attacker.type_id})")

            # 5. Check for declaring blockers
            if self.graph.step == vocab.ID_STEP_DECLARE_BLOCKERS:
                # The non-active player is the one declaring blockers
                non_active_player = next(p for p in self.graph.entities.values() if p.type_id == vocab.ID_PLAYER and p.instance_id != self.graph.active_player_id)
                if non_active_player:
                    potential_blockers = combat_handlers.get_legal_blockers(self.graph, non_active_player.instance_id)
                    attacking_creatures = [c for c in self.graph.entities.values() if c.properties.get('is_attacking')]
                    for blocker in potential_blockers:
                        for attacker in attacking_creatures:
                            if keyword_handlers.can_be_blocked_by(self.graph, attacker, blocker):
                                legal_moves.append(DeclareBlockerAction(player_id=non_active_player.instance_id, blocker_id=blocker.instance_id, attacker_id=attacker.instance_id))
                                logger.debug(f"Found DeclareBlockerAction: {blocker.properties.get('name', blocker.type_id)} ({blocker.type_id}) blocking {attacker.properties.get('name', attacker.type_id)} ({attacker.type_id})")

        except Exception as e:
            logger.error(f"Error calculating legal moves: {e}", exc_info=True)

        logger.debug(f"Total legal moves found: {len(legal_moves)}")
        return legal_moves

    def execute_move(self, move: AnyAction):
        """Executes a game action and updates the graph."""
        logger.info(f"Executing move: {move}")
        try:
            if isinstance(move, (PlayLandAction, CastSpellAction, ActivateManaAbilityAction, DeclareAttackerAction)):
                player = self.graph.entities[move.player_id]
                card = self.graph.entities[move.card_id]

                if isinstance(move, PlayLandAction):
                    # Find the battlefield zone and move the card
                    control_rels = self.graph.get_relationships(source=player, rel_type=vocab.ID_REL_CONTROLS)
                    battlefield_zone = next((self.graph.entities[r.target] for r in control_rels if self.graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD), None)
                    card_zone_rel = self.graph.get_relationships(source=card, rel_type=vocab.ID_REL_IS_IN_ZONE)[0]
                    card_zone_rel.target = battlefield_zone.instance_id
                    player.properties['lands_played_this_turn'] = player.properties.get('lands_played_this_turn', 0) + 1
                    logger.info(f"{player.properties.get('name')} played {card.properties.get('name')} to battlefield.")
                
                elif isinstance(move, ActivateManaAbilityAction):
                    mana_handlers.execute_tap_for_mana(self.graph, player, card)
                    logger.info(f"{player.properties.get('name')} tapped {card.properties.get('name')} for mana. Mana pool: {player.properties['mana_pool']}")

                elif isinstance(move, CastSpellAction):
                    cost = card_database.get_card_cost(card.type_id)
                    mana_pool = player.properties['mana_pool']

                    # Deduct colored mana first
                    for mana_type, amount in cost.items():
                        if mana_type != vocab.ID_MANA_GENERIC:
                            mana_pool[mana_type] -= amount
                    
                    # Deduct generic mana from remaining pool
                    generic_cost = cost.get(vocab.ID_MANA_GENERIC, 0)
                    for mana_type in mana_pool:
                        spend = min(generic_cost, mana_pool[mana_type])
                        mana_pool[mana_type] -= spend
                        generic_cost -= spend
                        if generic_cost == 0:
                            break
                    logger.info(f"{player.properties.get('name')} cast {card.properties.get('name')} for {cost}. Remaining mana: {mana_pool}")

                    # Move card to battlefield
                    control_rels = self.graph.get_relationships(source=player, rel_type=vocab.ID_REL_CONTROLS)
                    battlefield_zone = next((self.graph.entities[r.target] for r in control_rels if self.graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD), None)
                    card_zone_rel = self.graph.get_relationships(source=card, rel_type=vocab.ID_REL_IS_IN_ZONE)[0]
                    card_zone_rel.target = battlefield_zone.instance_id
                    card.properties['turn_entered'] = self.graph.turn_number
                    # Creatures entering the battlefield have summoning sickness
                    if card.properties.get('is_creature'):
                        card.properties['has_summoning_sickness'] = True
                    logger.info(f"{card.properties.get('name')} moved to battlefield.")

            combat_handlers.declare_attacker(self.graph, card)

            elif isinstance(move, DeclareBlockerAction):
                blocker = self.graph.entities[move.blocker_id]
                attacker = self.graph.entities[move.attacker_id]
                self.graph.add_relationship(blocker, attacker, vocab.ID_REL_IS_BLOCKING)
                logger.info(f"{self.graph.entities[move.player_id].properties.get('name')} declared {blocker.properties.get('name')} blocking {attacker.properties.get('name')}.")

            elif isinstance(move, PassTurnAction):
                self.progress_phase_and_step(force_next_phase=True) # Force progression to next phase/turn

        except Exception as e:
            logger.error(f"Error executing move {move}: {e}", exc_info=True)
        
        # After any move, attempt to progress the game state (e.g., pass priority, advance step)
        self.progress_phase_and_step()

    def _handle_step_effects(self):
        """Processes automatic state changes at the end of a step."""
        logger.info(f"Handling effects for step {self.graph.step}")
        try:
            active_player = self.graph.entities[self.graph.active_player_id]
            
            if self.graph.step == vocab.ID_STEP_UNTAP:
                # Untap permanents and remove summoning sickness
                control_rels = self.graph.get_relationships(source=active_player, rel_type=vocab.ID_REL_CONTROLS)
                battlefield_zone = next((self.graph.entities[r.target] for r in control_rels if self.graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD), None)
                if battlefield_zone:
                    cards_on_battlefield = [self.graph.entities[r.source] for r in self.graph.get_relationships(target=battlefield_zone, rel_type=vocab.ID_REL_IS_IN_ZONE)]
                    for card in cards_on_battlefield:
                        if card.properties.get('tapped', False):
                            card.properties['tapped'] = False
                            logger.debug(f"Untapped {card.properties.get('name', card.type_id)}.")
                        # Remove summoning sickness for creatures that have been on the battlefield for a full turn
                        if card.properties.get('is_creature') and card.properties.get('has_summoning_sickness', False):
                            card.properties['has_summoning_sickness'] = False
                            logger.debug(f"Removed summoning sickness from {card.properties.get('name', card.type_id)}.")
                logger.info(f"Untap Step: Permanents untapped and summoning sickness removed for {active_player.properties.get('name')}.")

            elif self.graph.step == vocab.ID_STEP_DRAW:
                # Active player draws a card
                self.graph.draw_card(active_player)
                logger.info(f"Draw Step: {active_player.properties.get('name')} drew a card.")

            elif self.graph.step == vocab.ID_STEP_DECLARE_BLOCKERS:
                combat_handlers.assign_combat_damage(self.graph)
                logger.info(f"Combat Damage Step: Combat damage assigned.")
            
            elif self.graph.step == vocab.ID_STEP_CLEANUP:
                # Discard down to hand size, remove damage, end "until end of turn" effects
                # For MVP, just clear mana pool and reset lands played
                active_player.properties['lands_played_this_turn'] = 0
                active_player.properties['mana_pool'] = {m: 0 for m in [vocab.ID_MANA_GREEN, vocab.ID_MANA_BLUE, vocab.ID_MANA_BLACK, vocab.ID_MANA_RED, vocab.ID_MANA_WHITE, vocab.ID_MANA_COLORLESS, vocab.ID_MANA_GENERIC]}
                logger.info(f"Cleanup Step: {active_player.properties.get('name')}'s mana pool cleared and lands played reset.")

        except Exception as e:
            logger.error(f"Error handling step effects for {self.graph.step}: {e}", exc_info=True)
            raise

    def progress_phase_and_step(self, force_next_phase: bool = False):
        """
        Advances the game state through phases and steps.
        If force_next_phase is True, it skips remaining steps in the current phase.
        """
        logger.info(f"Attempting to progress phase/step. Current: Phase {self.graph.phase}, Step {self.graph.step}")
        
        current_phase_index = vocab.PHASE_ORDER.index(self.graph.phase)
        current_step_list = vocab.PHASE_STEPS.get(self.graph.phase, [])
        
        # Find current step index
        try:
            current_step_index = current_step_list.index(self.graph.step)
        except ValueError:
            # If current step is not in the list for the current phase, start from beginning
            current_step_index = -1 

        self._handle_step_effects() # Handle effects for the step just completed

        is_game_over, _ = self._check_win_loss_conditions() # Check conditions after every state change
        if is_game_over:
            logger.info("Game is over. Stopping phase/step progression.")
            return # Stop progression if game is over

        if not force_next_phase and current_step_index < len(current_step_list) - 1:
            # Move to the next step in the current phase
            self.graph.step = current_step_list[current_step_index + 1]
            logger.info(f"Advanced to next step: {self.graph.step}")
        else:
            # Move to the next phase
            next_phase_index = (current_phase_index + 1) % len(vocab.PHASE_ORDER)
            self.graph.phase = vocab.PHASE_ORDER[next_phase_index]
            logger.info(f"Advanced to next phase: {self.graph.phase}")

            # If we wrapped around to the beginning phase, it's a new turn
            if self.graph.phase == vocab.ID_PHASE_BEGINNING:
                self.graph.turn_number += 1
                logger.info(f"New turn started. Turn number: {self.graph.turn_number}")
                
                # Switch active player
                all_players = [p for p in self.graph.entities.values() if p.type_id == vocab.ID_PLAYER]
                current_active_player = self.graph.entities[self.graph.active_player_id]
                next_player = next(p for p in all_players if p.instance_id != current_active_player.instance_id)
                self.graph.active_player_id = next_player.instance_id
                logger.info(f"Active player switched to {next_player.properties.get('name')}.")

            # Set the step to the first step of the new phase
            new_phase_steps = vocab.PHASE_STEPS.get(self.graph.phase, [])
            if new_phase_steps:
                self.graph.step = new_phase_steps[0]
                logger.info(f"Set step to first step of new phase: {self.graph.step}")
            else:
                logger.warning(f"Phase {self.graph.phase} has no defined steps.")
        

    def end_turn(self, player_id: uuid.UUID):
        """Ends the current player's turn and prepares for the next."""
        logger.info(f"Player {self.graph.entities[player_id].properties.get('name')} ending turn {self.graph.turn_number}.")
        # Force progression to the next phase, which will eventually lead to the next player's turn
        self.progress_phase_and_step(force_next_phase=True)
        logger.info(f"Turn ended. Game state progressed to next turn's beginning phase.")

    def _check_win_loss_conditions(self) -> (bool, Optional[uuid.UUID]):
        """Checks if any player has won or lost the game."""
        for player_id, player_entity in self.graph.entities.items():
            if player_entity.type_id == vocab.ID_PLAYER:
                if player_entity.properties['life_total'] <= 0:
                    logger.info(f"GAME OVER! Player {player_entity.properties.get('name')} has lost.")
                    # The other player wins
                    winner_id = next(p for p in self.graph.entities.values() if p.type_id == vocab.ID_PLAYER and p.instance_id != player_id).instance_id
                    return True, winner_id
        return False, None

    def get_reward(self, player_id: uuid.UUID) -> float:
        """Returns the reward for a given player based on the game outcome."""
        is_game_over, winner_id = self._check_win_loss_conditions()
        if is_game_over:
            if player_id == winner_id:
                return 1.0 # Win
            else:
                return -1.0 # Loss
        return 0.0 # Game not over

