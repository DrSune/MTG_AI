
import unittest
import numpy as np
from MTG_bot.strategic_brain.environment import MTGEnv
from MTG_bot.strategic_brain.teacher import Teacher
from MTG_bot.rule_engine.card_data_loader import CardDataLoader
from MTG_bot import config

class TestTrainingFlow(unittest.TestCase):
    def setUp(self):
        self.loader = CardDataLoader(config.MTG_BOT_DB_PATH)
        self.env = MTGEnv(self.loader)
        model_config = {"embedding_dim": 128, "d_model": 256}
        self.teacher = Teacher(self.loader, model_config)

    def test_single_episode_flow(self):
        """Verifies that an episode can run from start to finish with random actions."""
        # 1. Reset
        obs = self.env.reset(format="limited")
        self.assertIn("tokens", obs)
        self.assertIn("observation", obs)
        
        # 2. Run a few steps
        for i in range(5):
            # Get legal actions from env
            legal_actions = self.env.get_legal_actions_as_tokens()
            self.assertGreater(len(legal_actions), 0)
            
            # Pick a random valid action
            action = legal_actions[0]
            
            # Step
            next_obs, reward, done, info = self.env.step(action)
            
            self.assertIn("tokens", next_obs)
            self.assertIsInstance(reward, float)
            
            if done: break
            obs = next_obs
            
        print(f"Verified training flow for {i+1} steps.")

if __name__ == "__main__":
    unittest.main()
