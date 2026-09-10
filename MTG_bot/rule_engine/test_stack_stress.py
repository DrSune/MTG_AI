
import unittest
import uuid
import time
from MTG_bot.rule_engine.game_initializer import initialize_game_state
from MTG_bot.rule_engine.engine import Engine
from MTG_bot.rule_engine.actions import CastSpellAction, PassPriorityAction
from MTG_bot.rule_engine import vocabulary as vocab

class TestStackStress(unittest.TestCase):
    def setUp(self):
        # Card IDs confirmed: Aven (5), Shock (159), Mountain (269)
        self.aven_id = 5
        self.shock_id = 159
        self.mountain_id = 269
        
        # Initialize Game: 60 Mountains each
        self.graph = initialize_game_state([269]*60, [269]*60)
        self.engine = Engine(self.graph)
        self.player1_id = self.graph.players[0]
        self.player2_id = self.graph.players[1]
        self.player1 = self.graph.entities[self.player1_id]
        self.player2 = self.graph.entities[self.player2_id]

    def test_lifo_resolution(self):
        """Tests that a spell resolves before an ETB trigger it responds to."""
        # 1. Setup: Aven Gagglemaster (ETB Trigger) and Shock (Instant) in hand
        aven = self.graph.add_entity(self.aven_id)
        shock = self.graph.add_entity(self.shock_id)
        
        hand_zone = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.player1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[r.target].type_id == vocab.ID_ZONE_HAND)
        self.graph._move_card_to_zone(aven, hand_zone)
        self.graph._move_card_to_zone(shock, hand_zone)
        
        # Force mana and initial life
        self.player1.properties['mana_pool'] = {vocab.ID_MANA_RED: 5, vocab.ID_MANA_WHITE: 5}
        self.player1.properties['life_total'] = 20
        self.player2.properties['life_total'] = 20
        
        # 2. Step 1: Cast Aven Gagglemaster (Added to Stack)
        self.engine.execute_move(CastSpellAction(player_id=self.player1_id, card_id=aven.instance_id))
        self.assertEqual(len(self.engine.stack), 1, "Aven should be on the stack.")
        
        # 3. Step 2: Pass priority to resolve Aven
        self.engine.execute_move(PassPriorityAction(player_id=self.player1_id))
        self.assertEqual(len(self.engine.stack), 1, "Aven ETB Trigger should be on the stack after Aven resolves.")
        self.assertEqual(self.player1.properties['life_total'], 20, "Should NOT have gained life yet (trigger still on stack).")
        
        # 4. Step 3: Cast Shock in response to ETB trigger (targeting Opponent)
        self.engine.execute_move(CastSpellAction(player_id=self.player1_id, card_id=shock.instance_id, target_id=self.player2_id))
        self.assertEqual(len(self.engine.stack), 2, "Stack should contain ETB trigger and Shock.")
        
        # 5. Step 4: Pass priority to resolve Shock
        self.engine.execute_move(PassPriorityAction(player_id=self.player1_id))
        self.assertEqual(len(self.engine.stack), 1, "Only ETB trigger should remain on the stack.")
        self.assertEqual(self.player2.properties['life_total'], 18, "Opponent should have taken 2 damage from Shock.")
        self.assertEqual(self.player1.properties['life_total'], 20, "Still no life gain.")

        # 6. Step 5: Pass priority to resolve ETB Trigger
        self.engine.execute_move(PassPriorityAction(player_id=self.player1_id))
        self.assertEqual(len(self.engine.stack), 0, "Stack should be empty.")
        self.assertEqual(self.player1.properties['life_total'], 22, "Life gain trigger should have resolved finally.")

if __name__ == "__main__":
    unittest.main()
