
import unittest
import uuid
from MTG_bot.rule_engine.game_graph import GameGraph
from MTG_bot.rule_engine.engine import Engine
from MTG_bot.rule_engine.actions import CastSpellAction, PassPriorityAction, PlayLandAction
from MTG_bot.rule_engine import vocabulary as vocab

class TestInteractions(unittest.TestCase):
    def setUp(self):
        self.graph = GameGraph().initialize_game([269]*60, [269]*60)
        self.engine = Engine(self.graph)
        self.p1_id = self.graph.players[0]
        self.p2_id = self.graph.players[1]
        self.p1 = self.graph.entities[self.p1_id]
        self.p2 = self.graph.entities[self.p2_id]

    def find_id(self, name):
        from MTG_bot.rule_engine import card_database
        return card_database.card_data_loader.card_name_to_id.get(name)

    def test_runed_halo_protection(self):
        """Tests that Runed Halo protection prevents damage."""
        halo_id = self.find_id("Runed Halo")
        shock_id = self.find_id("Shock")
        
        # 1. Setup Halo on battlefield naming "Shock"
        halo = self.graph.add_entity(halo_id)
        halo.properties['name'] = "Runed Halo"
        self.graph.add_relationship(halo, self.p1, vocab.ID_REL_CONTROLLED_BY)
        # Rule: YOU have protection. So set flag on p1.
        self.p1.properties['protection_from_name'] = "Shock"
        halo.properties['is_on_battlefield'] = True
        
        # 2. Player 2 casts Shock targeting Player 1
        shock = self.graph.add_entity(shock_id)
        shock.properties['name'] = "Shock" # Ensure name is set for protection check
        self.p2.properties['life_total'] = 20
        self.p1.properties['life_total'] = 20
        
        # Manually resolve shock from p2 targeting p1
        from MTG_bot.rule_engine.handlers import effect_handlers
        effect_handlers.apply_damage(self.graph, shock, self.p1, 2)
        
        # 3. Verify: Life should still be 20
        self.assertEqual(self.p1.properties['life_total'], 20, "Damage should be prevented by Runed Halo")

    def test_kaervek_sba_death(self):
        """Tests that Kaervek's static effect kills a 1/1 immediately."""
        kaervek_id = self.find_id("Kaervek, the Spiteful")
        cur_id = self.find_id("Igneous Cur")
        
        # 1. Setup Kaervek on battlefield
        kaervek = self.graph.add_entity(kaervek_id)
        kaervek.properties['name'] = "Kaervek, the Spiteful"
        # Move to battlefield so hydration finds it
        bf_zone_p2 = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.p2, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD)
        self.graph._move_card_to_zone(kaervek, bf_zone_p2)
        self.graph.add_relationship(kaervek, self.p2, vocab.ID_REL_CONTROLLED_BY)
        
        # Manually add the effect data since it's normally in DB
        kaervek.properties['effects'] = [{"ability_type": "continuous_effect", "filter": {"type": "creatures"}, "effect": {"type": "stat_modifier", "power": -1, "toughness": -1}, "layer": 7}]
        
        # 2. Player 1 casts a 1/1
        creature = self.graph.add_entity(cur_id)
        creature.properties['power'] = 1
        creature.properties['toughness'] = 1
        creature.properties['name'] = "Small Fry"
        creature.properties['is_creature'] = True
        
        # 3. Move to battlefield
        bf_zone = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.p1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD)
        self.graph._move_card_to_zone(creature, bf_zone)
        
        # 4. Apply Layers
        self.engine.layer_system.apply_all_layers(self.graph)
        
        # Verify: Kaervek should have reduced toughness to 0
        self.assertEqual(creature.properties.get('effective_toughness'), 0, "Creature toughness should be 0 from Kaervek")
        
        # 5. Check SBAs
        self.engine.check_state_based_actions()
        
        # 6. Verify: Creature should be in graveyard
        gy_zone = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.p1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[r.target].type_id == vocab.ID_ZONE_GRAVEYARD)
        self.assertEqual(creature.properties['zone_id'], gy_zone.instance_id, "Creature should have died to Kaervek's static effect")

    def test_azusa_extra_lands(self):
        """Tests that Azusa allows playing 3 lands."""
        azusa_id = self.find_id("Azusa, Lost but Seeking")
        
        # 1. Setup Azusa
        azusa = self.graph.add_entity(azusa_id)
        azusa.properties['is_on_battlefield'] = True
        self.graph.add_relationship(azusa, self.p1, vocab.ID_REL_CONTROLLED_BY)
        
        # 2. Update engine parity for Azusa (manually apply the effect for the test)
        from MTG_bot.rule_engine.handlers import effect_handlers
        effect_handlers.resolve_atomic_effect(self.graph, self.p1, azusa, azusa.properties['effects'][0])
        
        # 3. Check legal moves
        # p1 should be able to play 3 lands total.
        self.p1.properties['lands_played_this_turn'] = 2
        
        # We need a land in hand
        mtn_id = self.find_id("Mountain")
        land = self.graph.add_entity(mtn_id)
        hand_zone = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.p1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[r.target].type_id == vocab.ID_ZONE_HAND)
        self.graph._move_card_to_zone(land, hand_zone)
        
        # Set phase to Main
        self.graph.phase = self.engine.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary")
        
        moves = self.engine.get_legal_moves()
        land_moves = [m for m in moves if isinstance(m, PlayLandAction)]
        
        # Verify: Should have 1 land move (because 2 < 3)
        self.assertEqual(len(land_moves), 1, "Azusa should allow playing a 3rd land")
        
        # Execute and verify limit
        self.engine.execute_move(land_moves[0])
        self.assertEqual(self.p1.properties['lands_played_this_turn'], 3)
        
        moves_after = self.engine.get_legal_moves()
        self.assertEqual(len([m for m in moves_after if isinstance(m, PlayLandAction)]), 0, "Should not be able to play 4th land")
        
if __name__ == "__main__":
    unittest.main()
