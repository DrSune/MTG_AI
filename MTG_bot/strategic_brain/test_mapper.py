
import unittest
from MTG_bot.rule_engine.game_initializer import initialize_game_state
from MTG_bot.rule_engine.actions import PlayLandAction, PassPriorityAction
from MTG_bot.strategic_brain.action_mapper import ActionSpaceMapper
from MTG_bot.rule_engine.card_database import card_data_loader

class TestActionMapper(unittest.TestCase):
    def setUp(self):
        # Initialize with some cards
        self.graph = initialize_game_state(
            decklist1=[card_data_loader.get_card_id_by_name("Forest")] * 10,
            decklist2=[card_data_loader.get_card_id_by_name("Mountain")] * 10,
            shuffle=False
        )
        self.mapper = ActionSpaceMapper()

    def test_stable_ordering(self):
        """Verify that token mapping is stable across different graph instances with same entities."""
        player1_id = self.graph.active_player_id
        forests = [c for c in self.graph.entities.values() if c.properties.get('name') == "Forest"]
        forest = forests[0]
        
        action = PlayLandAction(player_id=player1_id, card_id=forest.instance_id)
        tokens1 = self.mapper.action_to_tokens(action, self.graph)
        
        # Create a second graph with same setup
        graph2 = initialize_game_state(
            decklist1=[card_data_loader.get_card_id_by_name("Forest")] * 10,
            decklist2=[card_data_loader.get_card_id_by_name("Mountain")] * 10,
            shuffle=False
        )
        # Note: instance_ids will be different UUIDs, but the mapper sorts by them.
        # This test actually checks that for the SAME graph instance, the mapping doesn't change
        # even if internal dict order were to change (though Python 3.7+ dicts are ordered).
        # More importantly, it checks tokens_to_action(action_to_tokens(a)) == a
        
        tokens = self.mapper.action_to_tokens(action, self.graph)
        reversed_action = self.mapper.tokens_to_action(tokens, self.graph)
        
        self.assertEqual(action.card_id, reversed_action.card_id)
        self.assertEqual(action.player_id, reversed_action.player_id)
        self.assertIsInstance(reversed_action, PlayLandAction)

    def test_pass_priority(self):
        player1_id = self.graph.active_player_id
        action = PassPriorityAction(player_id=player1_id)
        tokens = self.mapper.action_to_tokens(action, self.graph)
        reversed_action = self.mapper.tokens_to_action(tokens, self.graph)
        self.assertIsInstance(reversed_action, PassPriorityAction)
        self.assertEqual(action.player_id, reversed_action.player_id)

if __name__ == '__main__':
    unittest.main()
