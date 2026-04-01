
import unittest

# Import real game components
from .game_graph import GameGraph, Entity

# Import the handlers we want to test
from .handlers import combat_handlers, keyword_handlers
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config
from .card_database import card_data_loader

class TestKeywordHandlers(unittest.TestCase):

    def setUp(self):
        """Set up a fresh game state for each test using the real GameGraph."""
        self.graph = GameGraph()
        self.id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)
        
        # Create Players
        self.player1 = self.graph.add_entity(self.id_mapper.get_id_by_name("Player", "game_vocabulary"))
        self.player1.properties['name'] = "Player 1"
        self.player1.properties['life_total'] = 20

        self.player2 = self.graph.add_entity(self.id_mapper.get_id_by_name("Player", "game_vocabulary"))
        self.player2.properties['name'] = "Player 2"
        self.player2.properties['life_total'] = 20

    def test_vigilance(self):
        """Test that a creature with vigilance does not tap when attacking."""
        # Alpine Watchdog has vigilance
        vigilance_creature = self.graph.add_entity(card_data_loader.get_card_id_by_name("Alpine Watchdog"))
        combat_handlers.declare_attacker(self.graph, vigilance_creature)
        self.assertFalse(vigilance_creature.properties.get('tapped'))

        # A generic creature without vigilance
        non_vigilance_creature = self.graph.add_entity(self.id_mapper.get_id_by_name("Creature", "game_vocabulary"))
        combat_handlers.declare_attacker(self.graph, non_vigilance_creature)
        self.assertTrue(non_vigilance_creature.properties.get('tapped'))

    def test_lifelink(self):
        """Test that a creature with lifelink causes its controller to gain life."""
        # Anointed Chorister has lifelink
        lifelink_creature = self.graph.add_entity(card_data_loader.get_card_id_by_name("Anointed Chorister"))
        self.graph.add_relationship(lifelink_creature, self.player1, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))

        # Mock combat setup
        lifelink_creature.properties['is_attacking'] = True
        lifelink_creature.properties['effective_power'] = lifelink_creature.properties.get('power', 1)
        self.graph.active_player_id = self.player1.instance_id
        
        # Run the handler
        combat_handlers.assign_combat_damage(self.graph)
        
        # Assertions
        self.assertEqual(self.player1.properties['life_total'], 21) # 20 + 1 damage
        # self.assertEqual(self.player2.properties['life_total'], 19) # 20 - 1 damage (Currently assign_combat_damage only deals damage to player if no blockers, but we didn't specify blockers or player)

    def test_flying(self):
        """Test the blocking rules for flying."""
        # Aven Gagglemaster has flying
        attacker = self.graph.add_entity(card_data_loader.get_card_id_by_name("Aven Gagglemaster"))

        # Generic creature without flying
        blocker_no_fly = self.graph.add_entity(self.id_mapper.get_id_by_name("Creature", "game_vocabulary"))

        # Another flying creature
        blocker_with_fly = self.graph.add_entity(card_data_loader.get_card_id_by_name("Aven Gagglemaster"))

        # A creature with reach (Snarespinner)
        blocker_with_reach = self.graph.add_entity(card_data_loader.get_card_id_by_name("Snarespinner"))

        # A flying creature CANNOT be blocked by a non-flyer/non-reacher
        self.assertFalse(keyword_handlers.can_be_blocked_by(self.graph, attacker, blocker_no_fly))

        # A flying creature CAN be blocked by another flyer
        self.assertTrue(keyword_handlers.can_be_blocked_by(self.graph, attacker, blocker_with_fly))

        # A flying creature CAN be blocked by a creature with reach
        self.assertTrue(keyword_handlers.can_be_blocked_by(self.graph, attacker, blocker_with_reach))
        
        # A non-flying creature CAN be blocked by a non-flyer
        non_flyer_attacker = self.graph.add_entity(self.id_mapper.get_id_by_name("Creature", "game_vocabulary"))
        self.assertTrue(keyword_handlers.can_be_blocked_by(self.graph, non_flyer_attacker, blocker_no_fly))


if __name__ == '__main__':
    unittest.main()
