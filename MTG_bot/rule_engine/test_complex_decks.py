
import unittest
import sys
import os

# Add the project root to sys.path to resolve absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from MTG_bot.rule_engine.game_graph import GameGraph
from MTG_bot.rule_engine.engine import Engine
from MTG_bot.rule_engine.actions import PlayLandAction, ActivateManaAbilityAction, CastSpellAction, PassPriorityAction
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config
from MTG_bot.rule_engine.card_database import card_data_loader
from MTG_bot.rule_engine import vocabulary as vocab

class TestComplexDecks(unittest.TestCase):

    def setUp(self):
        self.graph = GameGraph()
        self.id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)
        # Deck with varied effects
        self.deck1 = [
            card_data_loader.get_card_id_by_name("Mountain"),
            card_data_loader.get_card_id_by_name("Shock"),
            card_data_loader.get_card_id_by_name("Island"),
            card_data_loader.get_card_id_by_name("Opt"),
            card_data_loader.get_card_id_by_name("Swamp"),
            card_data_loader.get_card_id_by_name("Finishing Blow"),
            card_data_loader.get_card_id_by_name("Snarespinner"),
        ] * 10 # 70 cards
        self.graph.initialize_game(
            decklist1=self.deck1, 
            decklist2=[card_data_loader.get_card_id_by_name("Snarespinner")] * 60,
            shuffle=False,
            player1_starting_hand_ids=[
                card_data_loader.get_card_id_by_name("Mountain"),
                card_data_loader.get_card_id_by_name("Shock"),
                card_data_loader.get_card_id_by_name("Island"),
                card_data_loader.get_card_id_by_name("Opt"),
                card_data_loader.get_card_id_by_name("Swamp"),
                card_data_loader.get_card_id_by_name("Finishing Blow"),
                card_data_loader.get_card_id_by_name("Snarespinner"),
            ]
        )
        self.engine = Engine(self.graph)
        self.player1 = self.graph.entities[self.graph.active_player_id]
        self.player2 = next(p for p in self.graph.entities.values() if p.type_id == vocab.ID_PLAYER and p.instance_id != self.player1.instance_id)

    def _progress_to_main(self):
        while self.graph.phase != vocab.ID_PHASE_MAIN1:
            self.engine.progress_phase_and_step()

    def test_shock_player(self):
        """Test Shocking the opponent's face."""
        self._progress_to_main()
        
        # Play Mountain
        mountain = next(c for c in [self.graph.entities[r.source] for r in self.graph.get_relationships(target=next(self.graph.entities[rr.target] for rr in self.graph.get_relationships(source=self.player1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[rr.target].type_id == vocab.ID_ZONE_HAND), rel_type=vocab.ID_REL_IS_IN_ZONE)] if c.properties.get('name') == "Mountain")
        self.engine.execute_move(PlayLandAction(player_id=self.player1.instance_id, card_id=mountain.instance_id))
        
        # Tap for R
        self.engine.execute_move(ActivateManaAbilityAction(player_id=self.player1.instance_id, card_id=mountain.instance_id, ability_id=0))
        
        # Cast Shock targeting player 2
        shock = next(c for c in [self.graph.entities[r.source] for r in self.graph.get_relationships(target=next(self.graph.entities[rr.target] for rr in self.graph.get_relationships(source=self.player1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[rr.target].type_id == vocab.ID_ZONE_HAND), rel_type=vocab.ID_REL_IS_IN_ZONE)] if c.properties.get('name') == "Shock")
        
        legal_moves = self.engine.get_legal_moves()
        shock_move = next((m for m in legal_moves if isinstance(m, CastSpellAction) and m.card_id == shock.instance_id and m.target_id == self.player2.instance_id), None)
        self.assertIsNotNone(shock_move)
        
        initial_life = self.player2.properties['life_total']
        self.engine.execute_move(shock_move)
        
        self.assertEqual(self.player2.properties['life_total'], initial_life - 2)
        # Shock should be in graveyard
        shock_zone = self.graph.entities[self.graph.get_relationships(source=shock, rel_type=vocab.ID_REL_IS_IN_ZONE)[0].target]
        self.assertEqual(shock_zone.type_id, vocab.ID_ZONE_GRAVEYARD)

    def test_opt_draw(self):
        """Test Opt drawing a card (ignoring scry for now as it's not implemented)."""
        self._progress_to_main()
        
        # Play Island
        island = next(c for c in [self.graph.entities[r.source] for r in self.graph.get_relationships(target=next(self.graph.entities[rr.target] for rr in self.graph.get_relationships(source=self.player1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[rr.target].type_id == vocab.ID_ZONE_HAND), rel_type=vocab.ID_REL_IS_IN_ZONE)] if c.properties.get('name') == "Island")
        self.engine.execute_move(PlayLandAction(player_id=self.player1.instance_id, card_id=island.instance_id))
        
        # Tap for U
        self.engine.execute_move(ActivateManaAbilityAction(player_id=self.player1.instance_id, card_id=island.instance_id, ability_id=0))
        
        # Cast Opt
        opt = next(c for c in [self.graph.entities[r.source] for r in self.graph.get_relationships(target=next(self.graph.entities[rr.target] for rr in self.graph.get_relationships(source=self.player1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[rr.target].type_id == vocab.ID_ZONE_HAND), rel_type=vocab.ID_REL_IS_IN_ZONE)] if c.properties.get('name') == "Opt")
        
        hand_zone_p1 = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.player1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[r.target].type_id == vocab.ID_ZONE_HAND)
        initial_hand_size = len(self.graph.get_relationships(target=hand_zone_p1, rel_type=vocab.ID_REL_IS_IN_ZONE))
        
        opt_move = CastSpellAction(player_id=self.player1.instance_id, card_id=opt.instance_id)
        self.engine.execute_move(opt_move)
        
        # Hand size should be initial - 1 (opt) + 1 (draw) = initial
        new_hand_size = len(self.graph.get_relationships(target=hand_zone_p1, rel_type=vocab.ID_REL_IS_IN_ZONE))
        self.assertEqual(new_hand_size, initial_hand_size)
        self.assertEqual(self.graph.entities[self.graph.get_relationships(source=opt, rel_type=vocab.ID_REL_IS_IN_ZONE)[0].target].type_id, vocab.ID_ZONE_GRAVEYARD)

    def test_finishing_blow(self):
        """Test Finishing Blow destroying a creature."""
        self._progress_to_main()
        
        # Give P1 enough mana (5 Swamps)
        for _ in range(5):
            swamp = self.graph.add_entity(card_data_loader.get_card_id_by_name("Swamp"))
            battlefield_p1 = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.player1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD)
            self.graph._move_card_to_zone(swamp, battlefield_p1)
            self.graph.add_relationship(swamp, self.player1, vocab.ID_REL_CONTROLLED_BY)
            self.engine.execute_move(ActivateManaAbilityAction(player_id=self.player1.instance_id, card_id=swamp.instance_id, ability_id=0))
            
        # Put a creature on P2's battlefield
        target_creature = self.graph.add_entity(card_data_loader.get_card_id_by_name("Snarespinner"))
        battlefield_p2 = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.player2, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD)
        self.graph._move_card_to_zone(target_creature, battlefield_p2)
        self.graph.add_relationship(target_creature, self.player2, vocab.ID_REL_CONTROLLED_BY)
        
        # Cast Finishing Blow
        finishing_blow = next(c for c in [self.graph.entities[r.source] for r in self.graph.get_relationships(target=next(self.graph.entities[rr.target] for rr in self.graph.get_relationships(source=self.player1, rel_type=vocab.ID_REL_CONTROLLED_BY) if self.graph.entities[rr.target].type_id == vocab.ID_ZONE_HAND), rel_type=vocab.ID_REL_IS_IN_ZONE)] if c.properties.get('name') == "Finishing Blow")
        
        legal_moves = self.engine.get_legal_moves()
        fb_move = next((m for m in legal_moves if isinstance(m, CastSpellAction) and m.card_id == finishing_blow.instance_id and m.target_id == target_creature.instance_id), None)
        self.assertIsNotNone(fb_move)
        
        self.engine.execute_move(fb_move)
        
        # target_creature should be in P2's graveyard
        target_zone = self.graph.entities[self.graph.get_relationships(source=target_creature, rel_type=vocab.ID_REL_IS_IN_ZONE)[0].target]
        self.assertEqual(target_zone.type_id, vocab.ID_ZONE_GRAVEYARD)
        self.assertEqual(self.graph.entities[self.graph.get_relationships(source=finishing_blow, rel_type=vocab.ID_REL_IS_IN_ZONE)[0].target].type_id, vocab.ID_ZONE_GRAVEYARD)

if __name__ == '__main__':
    unittest.main()
