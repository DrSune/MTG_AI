from typing import List, Dict
import numpy as np

from ..rule_engine.game_graph import GameGraph, Entity
from ..rule_engine import vocabulary as vocab

class StateConverter:
    """
    Converts the GameGraph into a numerical observation vector for an RL agent.
    """
    def __init__(self):
        # Define the fixed size of the observation vector
        # 2 (player life) + 2 (cards in hand) + 2 (creatures on battlefield) + 2*6 (mana pools) + 5 (phase one-hot)
        self.observation_size = 2 + 2 + 2 + 12 + 5 # Example size, will adjust as we add features

    def convert_graph_to_observation(self, graph: GameGraph) -> np.ndarray:
        """
        Converts the GameGraph into a fixed-size numerical observation vector.
        """
        observation = np.zeros(self.observation_size, dtype=np.float32)
        
        # --- Player Information ---
        player1 = None
        player2 = None
        for entity in graph.entities.values():
            if entity.type_id == vocab.ID_PLAYER:
                if entity.instance_id == graph.active_player_id:
                    player1 = entity # Active player
                else:
                    player2 = entity # Non-active player
        
        if player1 and player2:
            # Helper to get cards in a zone for a player
            def get_cards_in_zone(player_entity, zone_type_id, card_type_filter=None):
                control_rels = graph.get_relationships(source=player_entity, rel_type=vocab.ID_REL_CONTROLS)
                zone_entity = next((graph.entities[r.target] for r in control_rels if graph.entities[r.target].type_id == zone_type_id), None)
                if zone_entity:
                    cards_in_zone_rels = graph.get_relationships(target=zone_entity, rel_type=vocab.ID_REL_IS_IN_ZONE)
                    cards = [graph.entities[r.source] for r in cards_in_zone_rels]
                    if card_type_filter:
                        return [card for card in cards if card.type_id == card_type_filter]
                    return cards
                return []

            # Player 1 (Active Player)
            observation[0] = player1.properties.get('life_total', 0)
            observation[1] = len(get_cards_in_zone(player1, vocab.ID_ZONE_HAND)) # Cards in hand
            observation[2] = len(get_cards_in_zone(player1, vocab.ID_ZONE_BATTLEFIELD, vocab.ID_CREATURE)) # Creatures on battlefield
            # Add mana pool for player 1
            mana_pool_p1 = player1.properties.get('mana_pool', {})
            observation[3] = mana_pool_p1.get(vocab.ID_MANA_GREEN, 0)
            observation[4] = mana_pool_p1.get(vocab.ID_MANA_BLUE, 0)
            observation[5] = mana_pool_p1.get(vocab.ID_MANA_BLACK, 0)
            observation[6] = mana_pool_p1.get(vocab.ID_MANA_RED, 0)
            observation[7] = mana_pool_p1.get(vocab.ID_MANA_WHITE, 0)
            observation[8] = mana_pool_p1.get(vocab.ID_MANA_COLORLESS, 0)

            # Player 2 (Non-Active Player)
            observation[9] = player2.properties.get('life_total', 0)
            observation[10] = len(get_cards_in_zone(player2, vocab.ID_ZONE_HAND)) # Cards in hand
            observation[11] = len(get_cards_in_zone(player2, vocab.ID_ZONE_BATTLEFIELD, vocab.ID_CREATURE)) # Creatures on battlefield
            # Add mana pool for player 2
            mana_pool_p2 = player2.properties.get('mana_pool', {})
            observation[12] = mana_pool_p2.get(vocab.ID_MANA_GREEN, 0)
            observation[13] = mana_pool_p2.get(vocab.ID_MANA_BLUE, 0)
            observation[14] = mana_pool_p2.get(vocab.ID_MANA_BLACK, 0)
            observation[15] = mana_pool_p2.get(vocab.ID_MANA_RED, 0)
            observation[16] = mana_pool_p2.get(vocab.ID_MANA_WHITE, 0)
            observation[17] = mana_pool_p2.get(vocab.ID_MANA_COLORLESS, 0)

        # --- Game State Information ---
        # Current Phase (one-hot encoding for simplicity, assuming 5 phases)
        phase_one_hot = np.zeros(5)
        if graph.phase == vocab.ID_PHASE_BEGINNING: phase_one_hot[0] = 1
        elif graph.phase == vocab.ID_PHASE_MAIN1: phase_one_hot[1] = 1
        elif graph.phase == vocab.ID_PHASE_COMBAT: phase_one_hot[2] = 1
        elif graph.phase == vocab.ID_PHASE_MAIN2: phase_one_hot[3] = 1
        elif graph.phase == vocab.ID_PHASE_ENDING: phase_one_hot[4] = 1
        
        # Concatenate phase one-hot encoding to the observation vector
        observation[18:23] = phase_one_hot
        
        return observation
