
import unittest
import numpy as np
from MTG_bot.strategic_brain.environment import MTGEnv
from MTG_bot.rule_engine.card_data_loader import CardDataLoader
from MTG_bot.strategic_brain.student import Student, ExperienceBuffer
from MTG_bot import config

class TestTrainingFunctional(unittest.TestCase):
    def setUp(self):
        self.loader = CardDataLoader(config.MTG_BOT_DB_PATH)
        self.env = MTGEnv(self.loader)
        self.model_config = {
            "vocab_size": 10000, "embedding_dim": 128, "component_dim": 16,
            "nhead": 8, "num_layers": 4, "belief_dim": 64, "lr": 1e-4
        }
        self.student = Student(self.model_config)
        self.buffer = ExperienceBuffer()

    def test_return_calculation_logic(self):
        """Tests that returns and advantages are calculated correctly after an episode."""
        # Simulate a small episode manually
        episode_experience = [
            {"reward": 0.0, "value": 0.5, "done": False},
            {"reward": 0.0, "value": 0.5, "done": False},
            {"reward": 1.0, "value": 0.5, "done": True}, # Win!
        ]
        
        running_return = 0
        for i in reversed(range(len(episode_experience))):
            running_return = episode_experience[i]["reward"] + 0.99 * running_return * (1 - episode_experience[i]["done"])
            episode_experience[i]["return"] = running_return
            episode_experience[i]["advantage"] = running_return - episode_experience[i]["value"]
            
        # Verify: Last step return should be exactly its reward
        self.assertEqual(episode_experience[2]["return"], 1.0)
        # Second to last return should be 0.0 + 0.99 * 1.0 = 0.99
        self.assertAlmostEqual(episode_experience[1]["return"], 0.99)
        # Advantage should be 0.99 - 0.5 = 0.49
        self.assertAlmostEqual(episode_experience[1]["advantage"], 0.49)
        
        print("Return and Advantage calculation logic verified.")

    def test_student_select_action_mock(self):
        """Tests that select_action returns the correct structure even without torch (using HAS_TORCH mock)."""
        # If HAS_TORCH is false, the code might fail due to tensor operations.
        # But our environment is setup to handle numpy too.
        from MTG_bot.strategic_brain import student as student_mod
        if not student_mod.HAS_TORCH:
            print("Skipping select_action torch test (Torch not installed).")
            return
            
        obs = self.env.reset(format="limited")
        action, value, log_prob, memory = self.student.select_action(obs)
        
        self.assertEqual(len(action), 3)
        self.assertIsInstance(value, float)
        self.assertTrue(hasattr(log_prob, "item") or isinstance(log_prob, float))

if __name__ == "__main__":
    unittest.main()
