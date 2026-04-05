import os
import torch
from MTG_bot.strategic_brain.train import train
from MTG_bot.strategic_brain.config_rl import RLConfig
from MTG_bot.strategic_brain.student import Student
from MTG_bot.rule_engine.card_data_loader import CardDataLoader
from MTG_bot import config

def smoke_test():
    print("Starting Training Smoke Test...")
    cfg = RLConfig()
    cfg.episodes_per_generation = 1
    cfg.num_generations = 1
    cfg.use_wandb = False # Disable for smoke test
    cfg.save_freq = 100
    cfg.initial_phase_games = 0 # Skip foundation phase logic for test
    
    loader = CardDataLoader(config.MTG_BOT_DB_PATH)
    student = Student(cfg.to_dict())
    
    # We want to test the full loop, so let's just call train
    try:
        train(cfg, student=student)
        print("\nSUCCESS: Training loop executed one episode without crashing.")
    except Exception as e:
        print(f"\nFAILURE: Training loop crashed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    smoke_test()
