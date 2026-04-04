
import unittest
import uuid
from MTG_bot.rule_engine.game_graph import GameGraph
from MTG_bot.rule_engine.engine import Engine
from MTG_bot.rule_engine.actions import CastSpellAction, PassPriorityAction
from MTG_bot.rule_engine import vocabulary as vocab

class TestFunctionalParity(unittest.TestCase):
    def setUp(self):
        # Card IDs from previous DB check: 
        # Village Rites (some ID), Aven Gagglemaster (some ID), Mountain (269), Igneous Cur (153)
        # I'll use IDs that I know exist in the DB
        self.village_rites_id = 311 # Dummy, need to confirm
        self.aven_id = 5 # Dummy, need to confirm
        
        # We'll use names to find them for the test to be robust
        self.graph = GameGraph().initialize_game([269]*60, [269]*60)
        self.engine = Engine(self.graph)
        self.player1_id = self.graph.players[0]
        self.player2_id = self.graph.players[1]
        self.player1 = self.graph.entities[self.player1_id]

    def find_card_by_name(self, name):
        from MTG_bot.rule_engine import card_database
        return card_database.card_data_loader.card_name_to_id.get(name)

    def test_village_rites_sacrifice_and_draw(self):
        """Tests that Village Rites requires a sacrifice and draws 2 cards."""
        vr_id = self.find_card_by_name("Village Rites")
        cur_id = self.find_card_by_name("Igneous Cur")
        
        # Setup: Creature on battlefield, Village Rites in hand
        creature = self.graph.add_entity(cur_id)
        player1_entity = self.graph.entities[self.player1_id]
        self.graph.add_relationship(creature, player1_entity, vocab.ID_REL_CONTROLLED_BY)
        bf_zone = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.player1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD)
        self.graph._move_card_to_zone(creature, bf_zone)
        
        spell = self.graph.add_entity(vr_id)
        hand_zone = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.player1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[r.target].type_id == vocab.ID_ZONE_HAND)
        self.graph._move_card_to_zone(spell, hand_zone)
        
        # Force mana
        self.player1.properties['mana_pool'] = {vocab.ID_MANA_BLACK: 1}
        
        # Get legal moves - should find CastSpell with cost_target_id=creature
        moves = self.engine.get_legal_moves()
        vr_moves = [m for m in moves if isinstance(m, CastSpellAction) and m.card_id == spell.instance_id]
        
        self.assertTrue(len(vr_moves) > 0, "Should have legal moves for Village Rites")
        self.assertIsNotNone(vr_moves[0].cost_target_id, "Village Rites must have a sacrifice target")
        
        # Execute
        initial_hand_size = len(self.graph.get_relationships(target=hand_zone, rel_type=vocab.ID_REL_IS_IN_ZONE))
        self.engine.execute_move(vr_moves[0])
        
        # Verify: Creature is in graveyard, Hand size +2 (minus 1 for the spell itself)
        gy_zone = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.player1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[r.target].type_id == vocab.ID_ZONE_GRAVEYARD)
        self.assertEqual(creature.properties['zone_id'], gy_zone.instance_id, "Creature should be in graveyard")
        
        final_hand_size = len(self.graph.get_relationships(target=hand_zone, rel_type=vocab.ID_REL_IS_IN_ZONE))
        self.assertEqual(final_hand_size, initial_hand_size + 2 - 1, "Should have drawn 2 cards")

    def test_aven_gagglemaster_etb_trigger(self):
        """Tests that Aven Gagglemaster triggers life gain on ETB."""
        aven_id = self.find_card_by_name("Aven Gagglemaster")
        
        spell = self.graph.add_entity(aven_id)
        hand_zone = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.player1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[r.target].type_id == vocab.ID_ZONE_HAND)
        self.graph._move_card_to_zone(spell, hand_zone)
        
        # Force mana
        self.player1.properties['mana_pool'] = {vocab.ID_MANA_WHITE: 6}
        self.player1.properties['life_total'] = 20
        
        # Cast
        move = CastSpellAction(player_id=self.player1_id, card_id=spell.instance_id)
        self.engine.execute_move(move)
        
        # Verify: Life should be 22
        self.assertEqual(self.player1.properties['life_total'], 22, "Should have gained 2 life from ETB")

if __name__ == "__main__":
    unittest.main()
