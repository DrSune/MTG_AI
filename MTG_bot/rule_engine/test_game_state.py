import unittest
import uuid
from typing import List

from .game_graph import GameGraph, Entity, Relationship
from .engine import Engine, PlayLandAction, PassTurnAction
from .card_database import card_data_loader
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config

class TestGameState(unittest.TestCase):

    def setUp(self):
        self.game_graph = GameGraph()
        self.engine = Engine(self.game_graph)
        self.id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)

        # Define simple decks for testing
        self.decklist1 = [
            self.id_mapper.get_id_by_name("Forest", "cards"), self.id_mapper.get_id_by_name("Forest", "cards"), self.id_mapper.get_id_by_name("Forest", "cards"), self.id_mapper.get_id_by_name("Forest", "cards"),
            self.id_mapper.get_id_by_name("Island", "cards"), self.id_mapper.get_id_by_name("Island", "cards"), self.id_mapper.get_id_by_name("Island", "cards"), self.id_mapper.get_id_by_name("Island", "cards"),
            self.id_mapper.get_id_by_name("Grizzly Bears", "cards"), self.id_mapper.get_id_by_name("Grizzly Bears", "cards")
        ] * 2 # 40 cards total
        self.decklist2 = [
            self.id_mapper.get_id_by_name("Mountain", "cards"), self.id_mapper.get_id_by_name("Mountain", "cards"), self.id_mapper.get_id_by_name("Mountain", "cards"), self.id_mapper.get_id_by_name("Mountain", "cards"),
            self.id_mapper.get_id_by_name("Swamp", "cards"), self.id_mapper.get_id_by_name("Swamp", "cards"), self.id_mapper.get_id_by_name("Swamp", "cards"), self.id_mapper.get_id_by_name("Swamp", "cards"),
            self.id_mapper.get_id_by_name("Walking Corpse", "cards"), self.id_mapper.get_id_by_name("Walking Corpse", "cards")
        ] * 2 # 40 cards total

        self.game_graph.initialize_game(self.decklist1, self.decklist2, shuffle=False) # Don't shuffle for predictable tests

        self.player1 = next(p for p in self.game_graph.entities.values() if p.type_id == self.id_mapper.get_id_by_name("Player", "game_vocabulary") and p.properties['name'] == "Player 1")
        self.player2 = next(p for p in self.game_graph.entities.values() if p.type_id == self.id_mapper.get_id_by_name("Player", "game_vocabulary") and p.properties['name'] == "Player 2")

    def _get_cards_in_zone(self, player: Entity, zone_id: int) -> List[Entity]:
        zone_entity = next(self.game_graph.entities[r.target] for r in self.game_graph.get_relationships(source=player, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if self.game_graph.entities[r.target].type_id == zone_id)
        card_rels = self.game_graph.get_relationships(target=zone_entity, rel_type=self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))
        return [self.game_graph.entities[r.source] for r in card_rels]

    def test_game_initialization(self):
        self.assertIsNotNone(self.player1)
        self.assertIsNotNone(self.player2)
        self.assertEqual(self.player1.properties['life_total'], 20)
        self.assertEqual(self.player2.properties['life_total'], 20)
        self.assertEqual(self.game_graph.turn_number, 1)
        self.assertEqual(self.game_graph.active_player_id, self.player1.instance_id)

        # Check initial hands (7 cards each)
        player1_hand = self._get_cards_in_zone(self.player1, self.id_mapper.get_id_by_name("Hand", "game_vocabulary"))
        player2_hand = self._get_cards_in_zone(self.player2, self.id_mapper.get_id_by_name("Hand", "game_vocabulary"))
        self.assertEqual(len(player1_hand), 7)
        self.assertEqual(len(player2_hand), 7)

        # Check libraries (remaining cards)
        player1_library = self._get_cards_in_zone(self.player1, self.id_mapper.get_id_by_name("Library", "game_vocabulary"))
        player2_library = self._get_cards_in_zone(self.player2, self.id_mapper.get_id_by_name("Library", "game_vocabulary"))
        self.assertEqual(len(player1_library), len(self.decklist1) - 7)
        self.assertEqual(len(player2_library), len(self.decklist2) - 7)

    def test_play_land_action(self):
        # Ensure it's Main Phase 1 for playing lands
        self.game_graph.phase = self.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary")
        self.game_graph.step = self.id_mapper.get_id_by_name("Pre-Combat Main Step", "game_vocabulary")

        player1_hand = self._get_cards_in_zone(self.player1, self.id_mapper.get_id_by_name("Hand", "game_vocabulary"))
        # Find a land card in hand
        land_in_hand = next((card for card in player1_hand if card.properties.get('is_land')), None)
        self.assertIsNotNone(land_in_hand, "Player 1 should have a land in hand to play.")

        # Get legal moves and find the PlayLandAction
        legal_moves = self.engine.get_legal_moves()
        play_land_move = next((move for move in legal_moves if isinstance(move, PlayLandAction) and move.card_id == land_in_hand.instance_id), None)
        self.assertIsNotNone(play_land_move, "PlayLandAction for the land should be a legal move.")

        # Execute the move
        self.engine.execute_move(play_land_move)

        # Verify land moved to battlefield
        player1_hand_after = self._get_cards_in_zone(self.player1, self.id_mapper.get_id_by_name("Hand", "game_vocabulary"))
        player1_battlefield_after = self._get_cards_in_zone(self.player1, self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary"))
        self.assertNotIn(land_in_hand, player1_hand_after)
        self.assertIn(land_in_hand, player1_battlefield_after)
        self.assertEqual(self.player1.properties['lands_played_this_turn'], 1)

        # Verify entered_zone_turn property
        self.assertEqual(land_in_hand.properties['entered_zone_turn'], self.game_graph.turn_number)

        # Try to play another land (should not be allowed)
        legal_moves_after_land = self.engine.get_legal_moves()
        play_another_land_move = next((move for move in legal_moves_after_land if isinstance(move, PlayLandAction) and move.card_id != land_in_hand.instance_id and self.game_graph.entities[move.card_id].properties.get('is_land')), None)
        self.assertIsNone(play_another_land_move, "Should not be able to play a second land this turn.")

    def test_turn_progression(self):
        # Initial state: Player 1, Turn 1, Beginning Phase, Untap Step
        self.assertEqual(self.game_graph.active_player_id, self.player1.instance_id)
        self.assertEqual(self.game_graph.turn_number, 1)
        self.assertEqual(self.game_graph.phase, self.id_mapper.get_id_by_name("Beginning Phase", "game_vocabulary"))
        self.assertEqual(self.game_graph.step, self.id_mapper.get_id_by_name("Untap Step", "game_vocabulary"))

        # Progress through steps and phases
        # Untap -> Upkeep -> Draw
        self.engine.progress_phase_and_step() # Untap -> Upkeep
        self.assertEqual(self.game_graph.step, self.id_mapper.get_id_by_name("Upkeep Step", "game_vocabulary"))
        self.engine.progress_phase_and_step() # Upkeep -> Draw
        self.assertEqual(self.game_graph.step, self.id_mapper.get_id_by_name("Draw Step", "game_vocabulary"))

        # Draw step should draw a card
        player1_hand_before_draw = self._get_cards_in_zone(self.player1, self.id_mapper.get_id_by_name("Hand", "game_vocabulary"))
        self.engine.progress_phase_and_step() # Draw -> Pre-Combat Main (and draws a card)
        player1_hand_after_draw = self._get_cards_in_zone(self.player1, self.id_mapper.get_id_by_name("Hand", "game_vocabulary"))
        self.assertEqual(len(player1_hand_after_draw), len(player1_hand_before_draw) + 1)
        self.assertEqual(self.game_graph.phase, self.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary"))
        self.assertEqual(self.game_graph.step, self.id_mapper.get_id_by_name("Pre-Combat Main Step", "game_vocabulary"))

        # Pass turn to Player 2
        self.engine.execute_move(PassTurnAction(player_id=self.player1.instance_id))
        self.assertEqual(self.game_graph.active_player_id, self.player2.instance_id)
        self.assertEqual(self.game_graph.turn_number, 2)
        self.assertEqual(self.game_graph.phase, self.id_mapper.get_id_by_name("Beginning Phase", "game_vocabulary"))
        self.assertEqual(self.game_graph.step, self.id_mapper.get_id_by_name("Untap Step", "game_vocabulary"))

        # Verify lands_played_this_turn reset for Player 1
        self.assertEqual(self.player1.properties['lands_played_this_turn'], 0)

if __name__ == '__main__':
    unittest.main()
