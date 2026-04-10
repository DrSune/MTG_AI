
import sys
import os
from MTG_bot.strategic_brain.train import train as run_training_cycle
from MTG_bot.strategic_brain.environment import MTGEnv
from MTG_bot.strategic_brain.student import Student
from MTG_bot.strategic_brain.teacher import Teacher
from MTG_bot.rule_engine.card_data_loader import CardDataLoader
from MTG_bot.strategic_brain.config_rl import RLConfig
from MTG_bot import config

def main():
    cfg = RLConfig()
    # Smoke test settings
    cfg.num_generations = 1
    cfg.episodes_per_generation = 2
    cfg.use_wandb = False
    
    print("Starting Smoke Test Training Run...")
    
    loader = CardDataLoader(config.MTG_BOT_DB_PATH)
    env = MTGEnv(loader)
    student = Student(cfg.to_dict())
    teacher = Teacher(loader, cfg.to_dict())
    
    # Run 1 generation
    print("\n[PHASE 1: SMOKE TEST TRAINING]")
    current_matchup = teacher.select_archetypes(0.0, 0.5, 1000, total_games=0)
    deck_a, deck_b = teacher.generate_matchup(cfg.format_mode, current_matchup, total_games=0)
    
    student, winrate, steps, games, global_steps = run_training_cycle(
        cfg, student=student, fixed_matchup=(deck_a, deck_b),
        initial_games=0, initial_steps=0
    )
    
    print("\nSmoke Test Complete!")
    print(f"Games played: {games}, Winrate: {winrate}")

if __name__ == "__main__":
    main()
