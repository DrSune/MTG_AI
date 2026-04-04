
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

class TestStateConverter(unittest.TestCase):
    def setUp(self):
        # Setup a basic game state
        self.graph = GameGraph().initialize_game([269]*60, [269]*60)
        self.engine = Engine(self.graph)
        self.converter = StateConverter()
        
        self.p1_id = self.graph.players[0]
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
        self.assertIn("features", tokens)
        self.assertIn("zone_ids", tokens)
        
        # Check counts
        num_entities = len(self.graph.entities)
        
        if HAS_TORCH:
            self.assertEqual(tokens["atomic_ids"].shape[1], num_entities + 1)
            # Check creature features
            creature_idx = (tokens["atomic_ids"] == creature.type_id).nonzero(as_tuple=True)[1][0]
            creature_feats = tokens["features"][0, creature_idx]
            stack_idx = num_entities
            self.assertEqual(tokens["zone_ids"][0, stack_idx], 999)
        else:
            self.assertEqual(tokens["atomic_ids"].shape[0], num_entities + 1)
            # Check creature features
            creature_idx = np.where(tokens["atomic_ids"] == creature.type_id)[0][0]
            creature_feats = tokens["features"][creature_idx]
            stack_idx = num_entities
            self.assertEqual(tokens["zone_ids"][stack_idx], 999)
        
        self.assertEqual(creature_feats[3], 1.0, "Creature should be marked as tapped in features.")
        self.assertEqual(creature_feats[5], 1.0, "Creature should be marked as is_creature in features.")
        self.assertGreater(creature_feats[11], 0, "Creature should have flying bit set in keywords.")

    def test_observation_vector(self):
        """Tests the summary observation vector."""
        self.p1.properties['life_total'] = 15
        self.p1.properties['mana_pool'] = {vocab.ID_MANA_RED: 3}
        
        obs = self.converter.convert_graph_to_observation(self.graph)
        
        self.assertEqual(obs.shape[0], 64)
        self.assertEqual(obs[3], 15.0, "Active player life total mismatch.")
        self.assertEqual(obs[4], 3.0, "Active player mana pool sum mismatch.")

if __name__ == "__main__":
    unittest.main()
