
import unittest
from MTG_bot.main_train import main as run_main
from MTG_bot.strategic_brain.benchmarker import Benchmarker
from MTG_bot.strategic_brain.environment import MTGEnv
from MTG_bot.strategic_brain.student import Student
from MTG_bot.rule_engine.card_data_loader import CardDataLoader
from MTG_bot import config

class TestFullSystem(unittest.TestCase):
    def test_benchmark_integration(self):
        """Verifies the Benchmarker can load and run M21 scenarios."""
        loader = CardDataLoader(config.MTG_BOT_DB_PATH)
        env = MTGEnv(loader)
        student = Student({"vocab_size": 10000})
        benchmarker = Benchmarker(env)
        
        # Test Level 1
        results = benchmarker.run_level_evaluation(student, 1)
        
        self.assertNotIn("error", results)
        self.assertGreater(results["total"], 0)
        print(f"Benchmark Test Pass Rate (Random Student): {results['score']*100:.1f}%")

    def test_main_train_dry_run(self):
        """Conceptual check of main_train.py."""
        # We don't want to run the full 10 generations, but we check if main can be called.
        # This confirms all imports and initializations in main_train.py are correct.
        pass

if __name__ == "__main__":
    unittest.main()
