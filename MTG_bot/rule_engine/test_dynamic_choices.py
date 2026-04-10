
import unittest
import uuid
from MTG_bot.rule_engine.game_graph import GameGraph
from MTG_bot.rule_engine.engine import Engine
from MTG_bot.rule_engine.actions import CastSpellAction, MakeChoiceAction, PassPriorityAction
from MTG_bot.rule_engine.game_initializer import initialize_game_state
from MTG_bot.rule_engine import vocabulary as vocab

class TestDynamicChoices(unittest.TestCase):
    def setUp(self):
        # M21 basic land (Plains) is 269
        self.graph = initialize_game_state([269]*60, [269]*60)
        self.engine = Engine(self.graph)
        self.p1_id = self.graph.players[0]
        self.graph.active_player_id = self.p1_id
        
    def test_runed_halo_choice_flow(self):
        """Tests that Runed Halo (mocked) triggers a choice and pauses resolution."""
        # 1. Create a mocked Runed Halo in hand
        halo = self.graph.add_entity(1001, {
            "name": "Runed Halo",
            "has_as_enters_choice": True,
            "as_enters_choice_type": "card_name",
            "cmc": 2
        })
        p1 = self.graph.entities[self.p1_id]
        # Add controller relationship
        self.graph.add_relationship(p1, halo, vocab.ID_REL_CONTROLLED_BY)
        
        hand_zone = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=p1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[r.target].type_id == vocab.ID_ZONE_HAND)
        self.graph._move_card_to_zone(halo, hand_zone)
        
        # Give P1 some mana
        p1.properties['mana_pool'] = {vocab.ID_MANA_WHITE: 2}
        
        # 2. Cast Runed Halo
        self.engine.execute_move(CastSpellAction(player_id=self.p1_id, card_id=halo.instance_id))
        self.assertTrue(halo.properties.get('is_on_stack'))
        
        # 3. Pass priority to resolve
        self.engine.execute_move(PassPriorityAction(player_id=self.p1_id))
        
        # 4. Engine should now be waiting for choice
        self.assertEqual(self.engine.waiting_for_choice, halo.instance_id)
        self.assertFalse(halo.properties.get('is_on_battlefield'))
        
        # 5. Check legal moves - should ONLY be MakeChoiceActions
        moves = self.engine.get_legal_moves()
        self.assertTrue(all(isinstance(m, MakeChoiceAction) for m in moves))
        self.assertIn("Shock", [m.choice_value for m in moves])
        
        # 6. Make the choice
        choice = next(m for m in moves if m.choice_value == "Shock")
        self.engine.execute_move(choice)
        
        # 7. Choice should be applied and card should be on battlefield
        self.assertIsNone(self.engine.waiting_for_choice)
        self.assertTrue(halo.properties.get('is_on_battlefield'))
        self.assertEqual(halo.properties.get('named_card'), "Shock")
        
        # Verify Runed Halo specific logic (protection)
        protections = p1.properties.get('protections_from_names', [])
        self.assertIn("Shock", protections)

if __name__ == "__main__":
    unittest.main()
