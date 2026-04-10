
import unittest
import numpy as np
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from MTG_bot.rule_engine.game_graph import GameGraph
from MTG_bot.rule_engine.engine import Engine, StackItem
from MTG_bot.strategic_brain.state_converter import StateConverter
from MTG_bot.rule_engine import vocabulary as vocab

from MTG_bot.rule_engine.game_initializer import initialize_game_state

class TestStateConverter(unittest.TestCase):
    def setUp(self):
        # Setup a basic game state
        self.graph = initialize_game_state([269]*60, [269]*60)
        # Ensure active player is p1 for consistent testing
        self.p1_id = self.graph.players[0]
        self.graph.active_player_id = self.p1_id
        
        self.engine = Engine(self.graph)
        self.converter = StateConverter()
        
        self.p1 = self.graph.entities[self.p1_id]

    def test_token_conversion_with_stack(self):
        """Tests that tokens correctly include entities and stack items."""
        # 1. Add a creature to the battlefield
        creature = self.graph.add_entity(153) # Igneous Cur
        bf_zone = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.p1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD)
        self.graph._move_card_to_zone(creature, bf_zone)
        creature.properties['tapped'] = True
        creature.properties['is_creature'] = True
        creature.properties['flying'] = True
        
        # 2. Add an item to the stack
        self.engine.stack.append(StackItem(
            source_id=creature.instance_id,
            controller_id=self.p1_id,
            effect_data={"ability_type": "activated_ability"}
        ))
        
        # 3. Convert
        tokens = self.converter.convert_graph_to_tokens(self.graph, self.engine.stack)
        
        # 4. Verify Tensors/Arrays
        self.assertIn("atomic_ids", tokens)
        self.assertIn("component_features", tokens)
        self.assertIn("zone_ids", tokens)
        
        # Check counts
        num_entities = len(self.graph.entities)
        
        # converter.convert_graph_to_tokens returns 1D numpy arrays
        self.assertEqual(tokens["atomic_ids"].shape[0], num_entities + 1)
        
        # Check creature features
        all_indices = np.where(tokens["atomic_ids"] == creature.type_id)[0]
        # The entity should have its zone_id correctly set (not 999 which is for Stack)
        creature_idx = next(idx for idx in all_indices if tokens["zone_ids"][idx] != 999)
        creature_feats = tokens["component_features"][creature_idx]
        
        self.assertEqual(creature_feats[3], 1.0, "Creature should be marked as tapped in features.")
        self.assertEqual(creature_feats[5], 1.0, "Creature should be marked as is_creature in features.")
        self.assertGreater(creature_feats[11], 0, "Creature should have flying bit set in keywords.")
        
        # 5. Verify Temporal State Encoding (New Task)
        self.assertGreater(creature_feats[16], 0, "Creature should have a non-zero timestamp feature.")

    def test_observation_vector(self):
        """Tests the summary observation vector."""
        self.p1.properties['life_total'] = 15
        self.p1.properties['mana_pool'] = {vocab.ID_MANA_RED: 3}
        
        obs = self.converter.convert_graph_to_observation(self.graph)
        
        self.assertEqual(obs.shape[0], 64)
        self.assertAlmostEqual(obs[3], 15.0 / 20.0, places=5, msg="Active player life total mismatch.")
        self.assertAlmostEqual(obs[4], 3.0 / 10.0, places=5, msg="Active player mana pool sum mismatch.")

if __name__ == "__main__":
    unittest.main()
