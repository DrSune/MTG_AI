
import unittest

# Import real game components
from .game_graph import GameGraph, Entity
from . import vocabulary as vocab
from .card_database import CREATURE_STATS

# Import the handlers we want to test
from .handlers import combat_handlers, keyword_handlers

class TestKeywordHandlers(unittest.TestCase):

    def setUp(self):
        """Set up a fresh game state for each test using the real GameGraph."""
        self.graph = GameGraph()
        
        # Create Players
        self.player1 = self.graph.add_entity(vocab.ID_PLAYER)
        self.player1.properties['name'] = "Player 1"
        self.player1.properties['life_total'] = 20

        self.player2 = self.graph.add_entity(vocab.ID_PLAYER)
        self.player2.properties['name'] = "Player 2"
        self.player2.properties['life_total'] = 20

    def test_vigilance(self):
        """Test that a creature with vigilance does not tap when attacking."""
        # Alpine Watchdog has vigilance
        vigilance_creature = self.graph.add_entity(vocab.ID_CARD_ALPINE_WATCHDOG)
        combat_handlers.declare_attacker(self.graph, vigilance_creature)
        self.assertNotIn('tapped', vigilance_creature.properties)

        # A generic creature without vigilance
        non_vigilance_creature = self.graph.add_entity(vocab.ID_CREATURE)
        combat_handlers.declare_attacker(self.graph, non_vigilance_creature)
        self.assertTrue(non_vigilance_creature.properties.get('tapped'))

    def test_lifelink(self):
        """Test that a creature with lifelink causes its controller to gain life."""
        # Anointed Chorister has lifelink
        lifelink_creature = self.graph.add_entity(vocab.ID_CARD_ANOINTED_CHORISTER)
        self.graph.add_relationship(self.player1, lifelink_creature, vocab.ID_REL_CONTROLS)

        # Mock combat setup
        lifelink_creature.properties['is_attacking'] = True
        lifelink_creature.properties['effective_power'] = CREATURE_STATS[vocab.ID_CARD_ANOINTED_CHORISTER]['power']
        self.graph.active_player_id = self.player1.instance_id
        
        # Run the handler
        combat_handlers.assign_combat_damage(self.graph)
        
        # Assertions
        self.assertEqual(self.player1.properties['life_total'], 21) # 20 + 1 damage
        self.assertEqual(self.player2.properties['life_total'], 19) # 20 - 1 damage

    def test_flying(self):
        """Test the blocking rules for flying."""
        # Aven Gagglemaster has flying
        attacker = self.graph.add_entity(vocab.ID_CARD_AVEN_GAGGLEMASTER)

        # Generic creature without flying
        blocker_no_fly = self.graph.add_entity(vocab.ID_CREATURE)

        # Another flying creature
        blocker_with_fly = self.graph.add_entity(vocab.ID_CARD_AVEN_GAGGLEMASTER)

        # A creature with reach (Snarepinner)
        blocker_with_reach = self.graph.add_entity(vocab.ID_CARD_SNARESPINNER)

        # A flying creature CANNOT be blocked by a non-flyer/non-reacher
        self.assertFalse(keyword_handlers.can_be_blocked_by(self.graph, attacker, blocker_no_fly))

        # A flying creature CAN be blocked by another flyer
        self.assertTrue(keyword_handlers.can_be_blocked_by(self.graph, attacker, blocker_with_fly))

        # A flying creature CAN be blocked by a creature with reach
        self.assertTrue(keyword_handlers.can_be_blocked_by(self.graph, attacker, blocker_with_reach))
        
        # A non-flying creature CAN be blocked by a non-flyer
        non_flyer_attacker = self.graph.add_entity(vocab.ID_CREATURE)
        self.assertTrue(keyword_handlers.can_be_blocked_by(self.graph, non_flyer_attacker, blocker_no_fly))


if __name__ == '__main__':
    unittest.main()
