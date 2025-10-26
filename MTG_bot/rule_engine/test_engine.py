
import unittest
import sys
import os

# Add the project root to sys.path to resolve absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from .game_graph import GameGraph
from .engine import Engine
from .actions import PlayLandAction, ActivateManaAbilityAction, CastSpellAction, DeclareAttackerAction, DeclareBlockerAction
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config

class TestEngine(unittest.TestCase):

    def setUp(self):
        """Set up a fresh game state for each test."""
        self.graph = GameGraph()
        self.id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)
        # The GameGraph's initialize_game function is a great way to set up a clean state
        self.graph.initialize_game(
            decklist1=[self.id_mapper.get_id_by_name("Forest", "cards"), self.id_mapper.get_id_by_name("Grizzly Bears", "cards")],
            decklist2=[]
        )
        self.engine = Engine(self.graph)
        self.player1 = self.graph.entities[self.graph.active_player_id]

    def test_play_land(self):
        """Test that a player can play a land from their hand."""
        # Find the Forest in the player's hand
        legal_moves = self.engine.get_legal_moves()
        play_land_move = next((move for move in legal_moves if isinstance(move, PlayLandAction)), None)
        
        self.assertIsNotNone(play_land_move, "Could not find a legal 'Play Land' move.")

        # Execute the move
        self.engine.execute_move(play_land_move)

        battlefield_zone = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.player1, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if self.graph.entities[r.target].type_id == self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary"))
        cards_on_battlefield = [self.graph.entities[r.source] for r in self.graph.get_relationships(target=battlefield_zone, rel_type=self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))]
        land_card = self.graph.entities[play_land_move.card_id]
        self.assertIn(land_card, cards_on_battlefield, "Land was not moved to the battlefield.")

        # Verify the 'one land per turn' rule
        legal_moves_after = self.engine.get_legal_moves()
        play_land_move_after = next((move for move in legal_moves_after if isinstance(move, PlayLandAction)), None)
        self.assertIsNone(play_land_move_after, "Was able to play a second land in one turn.")

    def test_tap_for_mana(self):
        """Test that a land on the battlefield can be tapped for mana."""
        # First, play a land
        play_land_move = next(move for move in self.engine.get_legal_moves() if isinstance(move, PlayLandAction))
        self.engine.execute_move(play_land_move)
        forest_card = self.graph.entities[play_land_move.card_id]

        # Now, find the tap for mana move
        legal_moves = self.engine.get_legal_moves()
        tap_mana_move = next((move for move in legal_moves if isinstance(move, ActivateManaAbilityAction)), None)
        self.assertIsNotNone(tap_mana_move, "Could not find a legal 'Tap for Mana' move.")

        # Execute the move
        self.engine.execute_move(tap_mana_move)

        # Verify the land is tapped
        self.assertTrue(forest_card.properties.get('tapped'), "Land was not tapped.")

        # Verify the player has the mana
        self.assertEqual(self.player1.properties['mana_pool'][self.id_mapper.get_id_by_name("Green Mana", "game_vocabulary")], 1, "Green mana was not added to the pool.")

        # Verify the land cannot be tapped again
        legal_moves_after = self.engine.get_legal_moves()
        tap_mana_move_after = next((move for move in legal_moves_after if isinstance(move, ActivateManaAbilityAction) and move.card_id == forest_card.instance_id), None)
        self.assertIsNone(tap_mana_move_after, "Was able to tap an already tapped land.")

    def test_cast_creature(self):
        """Test that a player can use mana to cast a creature spell."""
        # We need to adjust the decklist for this test
        self.graph.initialize_game(
            decklist1=[self.id_mapper.get_id_by_name("Forest", "cards"), self.id_mapper.get_id_by_name("Forest", "cards"), self.id_mapper.get_id_by_name("Grizzly Bears", "cards")],
            decklist2=[]
        )
        self.player1 = self.graph.entities[self.graph.active_player_id]
        self.engine = Engine(self.graph) # Re-initialize engine with new graph

        # Play two forests over two turns
        play_land_move_1 = next(move for move in self.engine.get_legal_moves() if isinstance(move, PlayLandAction))
        self.engine.execute_move(play_land_move_1)
        self.player1.properties['lands_played_this_turn'] = 0 # Reset for next turn

        play_land_move_2 = next(move for move in self.engine.get_legal_moves() if isinstance(move, PlayLandAction))
        self.engine.execute_move(play_land_move_2)

        # Tap both forests for mana
        tap_mana_moves = [move for move in self.engine.get_legal_moves() if isinstance(move, ActivateManaAbilityAction)]
        self.assertEqual(len(tap_mana_moves), 2, "Should be able to tap two lands.")
        self.engine.execute_move(tap_mana_moves[0])
        self.engine.execute_move(tap_mana_moves[1])

        # Now, check if casting Grizzly Bears is a legal move
        legal_moves = self.engine.get_legal_moves()
        cast_creature_move = next((move for move in legal_moves if isinstance(move, CastSpellAction)), None)
        self.assertIsNotNone(cast_creature_move, "Could not find a legal 'Cast Spell' move.")
        grizzly_bears_card = self.graph.entities[cast_creature_move.card_id]

        # Execute the move
        self.engine.execute_move(cast_creature_move)

        # Verify the creature is on the battlefield
        battlefield_zone = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.player1, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if self.graph.entities[r.target].type_id == self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary"))
        cards_on_battlefield = [self.graph.entities[r.source] for r in self.graph.get_relationships(target=battlefield_zone, rel_type=self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))]
        self.assertIn(grizzly_bears_card, cards_on_battlefield, "Creature was not moved to the battlefield.")

        # Verify mana was spent
        self.assertEqual(self.player1.properties['mana_pool'][self.id_mapper.get_id_by_name("Green Mana", "game_vocabulary")], 0, "Mana was not spent correctly.")

    def test_declare_attacker(self):
        """Test that a creature can be declared as an attacker."""
        # Cast a creature and move it to the battlefield
        self.graph.initialize_game(decklist1=[self.id_mapper.get_id_by_name("Grizzly Bears", "cards")], decklist2=[])
        self.player1 = self.graph.entities[self.graph.active_player_id]
        self.engine = Engine(self.graph)
        creature_card = next(c for c in self.graph.entities.values() if c.type_id == self.id_mapper.get_id_by_name("Grizzly Bears", "cards"))
        
        # Manually move creature to battlefield and set its turn_entered property for the test
        battlefield_zone = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.player1, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if self.graph.entities[r.target].type_id == self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary"))
        card_zone_rel = self.graph.get_relationships(source=creature_card, rel_type=self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))[0]
        card_zone_rel.target = battlefield_zone.instance_id
        creature_card.properties['turn_entered'] = self.graph.turn_number

        # Set the game to the Declare Attackers step
        self.graph.step = self.id_mapper.get_id_by_name("Declare Attackers Step", "game_vocabulary")

        # 1. Verify creature has summoning sickness and cannot attack
        legal_moves = self.engine.get_legal_moves()
        attack_move = next((move for move in legal_moves if isinstance(move, DeclareAttackerAction)), None)
        self.assertIsNone(attack_move, "Creature should have summoning sickness and be unable to attack.")

        # 2. Advance to the next turn
        self.graph.turn_number += 1

        # 3. Verify creature can now attack
        legal_moves = self.engine.get_legal_moves()
        attack_move = next((move for move in legal_moves if isinstance(move, DeclareAttackerAction)), None)
        self.assertIsNotNone(attack_move, "Creature should be able to attack on the next turn.")

        # 4. Execute the attack
        self.engine.execute_move(attack_move)
        self.assertTrue(creature_card.properties.get('is_attacking'), "Creature was not marked as attacking.")
        self.assertTrue(creature_card.properties.get('tapped'), "Creature was not tapped after attacking.")

    def test_full_combat(self):
        """Test a full combat sequence: attack, block, and damage."""
        # Setup: Player 1 has a Grizzly Bears, Player 2 has a Grizzly Bears.
        self.graph.initialize_game(
            decklist1=[self.id_mapper.get_id_by_name("Grizzly Bears", "cards")],
            decklist2=[self.id_mapper.get_id_by_name("Grizzly Bears", "cards")]
        )
        self.player1 = self.graph.entities[self.graph.active_player_id]
        self.player2 = next(p for p in self.graph.entities.values() if p.type_id == self.id_mapper.get_id_by_name("Player", "game_vocabulary") and p.instance_id != self.player1.instance_id)
        self.engine = Engine(self.graph)

        p1_creature = next(c for c in self.graph.entities.values() if c.type_id == self.id_mapper.get_id_by_name("Grizzly Bears", "cards") and self.graph.get_relationships(source=self.player1, target=c, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary")))
        p2_creature = next(c for c in self.graph.entities.values() if c.type_id == self.id_mapper.get_id_by_name("Grizzly Bears", "cards") and self.graph.get_relationships(source=self.player2, target=c, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary")))

        # Manually move creatures to battlefield for the test
        battlefield1 = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.player1, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if self.graph.entities[r.target].type_id == self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary"))
        battlefield2 = next(self.graph.entities[r.target] for r in self.graph.get_relationships(source=self.player2, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if self.graph.entities[r.target].type_id == self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary"))
        self.graph.get_relationships(source=p1_creature, rel_type=self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))[0].target = battlefield1.instance_id
        self.graph.get_relationships(source=p2_creature, rel_type=self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))[0].target = battlefield2.instance_id
        p1_creature.properties['turn_entered'] = 1
        p2_creature.properties['turn_entered'] = 1

        # Declare Attackers Step
        self.graph.turn_number = 2 # To avoid summoning sickness
        self.graph.step = self.id_mapper.get_id_by_name("Declare Attackers Step", "game_vocabulary")
        attack_move = next(move for move in self.engine.get_legal_moves() if isinstance(move, DeclareAttackerAction))
        self.engine.execute_move(attack_move)

        # Declare Blockers Step
        self.graph.step = self.id_mapper.get_id_by_name("Declare Blockers Step", "game_vocabulary")
        block_move = next(move for move in self.engine.get_legal_moves() if isinstance(move, DeclareBlockerAction))
        self.engine.execute_move(block_move)

        # End of Step -> Progress to Damage
        self.engine.progress_step()

        # Assertions
        self.assertEqual(p1_creature.properties.get('damage_taken'), 2)
        self.assertEqual(p2_creature.properties.get('damage_taken'), 2)

    def test_phase_and_step_progression(self):
        """Test that the game correctly progresses through phases and steps."""
        # Initial state
        self.assertEqual(self.graph.phase, self.id_mapper.get_id_by_name("Beginning Phase", "game_vocabulary"))
        self.assertEqual(self.graph.step, self.id_mapper.get_id_by_name("Untap Step", "game_vocabulary"))
        initial_active_player_id = self.graph.active_player_id
        initial_turn_number = self.graph.turn_number

        # Progress through a full turn cycle
        for _ in range(len([self.id_mapper.get_id_by_name("Beginning Phase", "game_vocabulary"), self.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary"), self.id_mapper.get_id_by_name("Combat Phase", "game_vocabulary"), self.id_mapper.get_id_by_name("Post-Combat Main Phase", "game_vocabulary"), self.id_mapper.get_id_by_name("Ending Phase", "game_vocabulary")]) * 3): # Iterate enough times to cover multiple turns
            current_phase = self.graph.phase
            current_step = self.graph.step
            current_phase_steps = {
                self.id_mapper.get_id_by_name("Beginning Phase", "game_vocabulary"): [
                    self.id_mapper.get_id_by_name("Untap Step", "game_vocabulary"),
                    self.id_mapper.get_id_by_name("Upkeep Step", "game_vocabulary"),
                    self.id_mapper.get_id_by_name("Draw Step", "game_vocabulary"),
                ],
                self.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary"): [
                    self.id_mapper.get_id_by_name("Pre-Combat Main Step", "game_vocabulary"),
                ],
                self.id_mapper.get_id_by_name("Combat Phase", "game_vocabulary"): [
                    self.id_mapper.get_id_by_name("Beginning of Combat Step", "game_vocabulary"),
                    self.id_mapper.get_id_by_name("Declare Attackers Step", "game_vocabulary"),
                    self.id_mapper.get_id_by_name("Declare Blockers Step", "game_vocabulary"),
                    self.id_mapper.get_id_by_name("Combat Damage Step", "game_vocabulary"),
                    self.id_mapper.get_id_by_name("End of Combat Step", "game_vocabulary"),
                ],
                self.id_mapper.get_id_by_name("Post-Combat Main Phase", "game_vocabulary"): [
                    self.id_mapper.get_id_by_name("Post-Combat Main Step", "game_vocabulary"),
                ],
                self.id_mapper.get_id_by_name("Ending Phase", "game_vocabulary"): [
                    self.id_mapper.get_id_by_name("End of Turn Step", "game_vocabulary"),
                    self.id_mapper.get_id_by_name("Cleanup Step", "game_vocabulary"),
                ],
            }.get(current_phase, [])
            
            try:
                current_step_index = current_phase_steps.index(current_step)
            except ValueError:
                current_step_index = -1 # Should not happen if initial state is correct

            self.engine.progress_phase_and_step()

            # Assertions for progression
            if current_step_index < len(current_phase_steps) - 1:
                # Should have moved to the next step in the same phase
                self.assertEqual(self.graph.phase, current_phase)
                self.assertEqual(self.graph.step, current_phase_steps[current_step_index + 1])
            else:
                # Should have moved to the next phase (or wrapped around to new turn)
                expected_next_phase_order = [self.id_mapper.get_id_by_name("Beginning Phase", "game_vocabulary"), self.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary"), self.id_mapper.get_id_by_name("Combat Phase", "game_vocabulary"), self.id_mapper.get_id_by_name("Post-Combat Main Phase", "game_vocabulary"), self.id_mapper.get_id_by_name("Ending Phase", "game_vocabulary")]
                expected_next_phase_index = (expected_next_phase_order.index(current_phase) + 1) % len(expected_next_phase_order)
                expected_next_phase = expected_next_phase_order[expected_next_phase_index]
                self.assertEqual(self.graph.phase, expected_next_phase)
                
                expected_next_step = {
                    self.id_mapper.get_id_by_name("Beginning Phase", "game_vocabulary"): [
                        self.id_mapper.get_id_by_name("Untap Step", "game_vocabulary"),
                        self.id_mapper.get_id_by_name("Upkeep Step", "game_vocabulary"),
                        self.id_mapper.get_id_by_name("Draw Step", "game_vocabulary"),
                    ],
                    self.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary"): [
                        self.id_mapper.get_id_by_name("Pre-Combat Main Step", "game_vocabulary"),
                    ],
                    self.id_mapper.get_id_by_name("Combat Phase", "game_vocabulary"): [
                        self.id_mapper.get_id_by_name("Beginning of Combat Step", "game_vocabulary"),
                        self.id_mapper.get_id_by_name("Declare Attackers Step", "game_vocabulary"),
                        self.id_mapper.get_id_by_name("Declare Blockers Step", "game_vocabulary"),
                        self.id_mapper.get_id_by_name("Combat Damage Step", "game_vocabulary"),
                        self.id_mapper.get_id_by_name("End of Combat Step", "game_vocabulary"),
                    ],
                    self.id_mapper.get_id_by_name("Post-Combat Main Phase", "game_vocabulary"): [
                        self.id_mapper.get_id_by_name("Post-Combat Main Step", "game_vocabulary"),
                    ],
                    self.id_mapper.get_id_by_name("Ending Phase", "game_vocabulary"): [
                        self.id_mapper.get_id_by_name("End of Turn Step", "game_vocabulary"),
                        self.id_mapper.get_id_by_name("Cleanup Step", "game_vocabulary"),
                    ],
                }.get(expected_next_phase, [])[0]
                self.assertEqual(self.graph.step, expected_next_step)

            # Check turn number and active player change after a full cycle
            if self.graph.phase == self.id_mapper.get_id_by_name("Beginning Phase", "game_vocabulary") and self.graph.step == self.id_mapper.get_id_by_name("Untap Step", "game_vocabulary") and self.graph.turn_number > initial_turn_number:
                self.assertNotEqual(self.graph.active_player_id, initial_active_player_id)
                self.assertEqual(self.graph.turn_number, initial_turn_number + 1)
                initial_active_player_id = self.graph.active_player_id # Update for next turn check
                initial_turn_number = self.graph.turn_number


if __name__ == '__main__':
    unittest.main()
