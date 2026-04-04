
import unittest
from MTG_bot.strategic_brain.teacher import Teacher
from MTG_bot.rule_engine.card_data_loader import CardDataLoader
from MTG_bot import config

class TestDrafting(unittest.TestCase):
    def setUp(self):
        self.loader = CardDataLoader(config.MTG_BOT_DB_PATH)
        model_config = {
            "embedding_dim": 128,
            "d_model": 256,
            "nhead": 8,
            "num_layers": 4
        }
        self.teacher = Teacher(self.loader, model_config)

    def test_full_draft_and_matchup(self):
        """Tests that the Teacher can generate two valid 40-card Limited decks."""
        # Debug: Check if basic lands are loaded
        print(f"Basics in simulator: {len(self.teacher.deck_gen.cards_by_rarity['basic'])}")
        
        deck_a, deck_b = self.teacher.generate_limited_matchup()
        
        # Verify Deck A
        self.assertEqual(len(deck_a), 40, "Deck A should have exactly 40 cards.")
        
        def count_lands(deck):
            land_count = 0
            import sqlite3
            conn = sqlite3.connect(config.MTG_BOT_DB_PATH)
            cursor = conn.cursor()
            for cid in deck:
                cursor.execute("SELECT type FROM cards WHERE card_id = ?", (cid,))
                row = cursor.fetchone()
                if row and "Land" in row[0]:
                    land_count += 1
            conn.close()
            return land_count

        lands_a = count_lands(deck_a)
        print(f"Limited Deck A Lands: {lands_a}")
        self.assertGreater(lands_a, 0, "Limited Deck A should contain lands.")

    def test_commander_matchup(self):
        """Tests that the Teacher can generate two valid 100-card Commander decks."""
        from MTG_bot.strategic_brain.deck_generator import Archetypes
        deck_a, deck_b = self.teacher.generate_commander_matchup(Archetypes.LIFE_GAIN, Archetypes.RAMP)
        
        self.assertEqual(len(deck_a), 100, "Commander Deck A should have exactly 100 cards.")
        self.assertEqual(len(deck_b), 100, "Commander Deck B should have exactly 100 cards.")
        
        # Verify Singleton (excluding basic lands)
        def check_singleton(deck):
            non_basics = []
            import sqlite3
            conn = sqlite3.connect(config.MTG_BOT_DB_PATH)
            cursor = conn.cursor()
            for cid in deck:
                cursor.execute("SELECT supertypes FROM cards WHERE card_id = ?", (cid,))
                row = cursor.fetchone()
                if row and "Basic" not in row[0]:
                    non_basics.append(cid)
            conn.close()
            return len(non_basics) == len(set(non_basics))

        self.assertTrue(check_singleton(deck_a), "Commander Deck A must be singleton for non-basics.")
        self.assertTrue(check_singleton(deck_b), "Commander Deck B must be singleton for non-basics.")
        
        print("Commander Matchup Test Passed.")

if __name__ == "__main__":
    unittest.main()
