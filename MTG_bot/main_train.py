import sys
import os
try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

from MTG_bot.strategic_brain.train import train as run_training_cycle
from MTG_bot.strategic_brain.benchmarker import Benchmarker
from MTG_bot.strategic_brain.environment import MTGEnv
from MTG_bot.strategic_brain.student import Student
from MTG_bot.strategic_brain.teacher import Teacher
from MTG_bot.rule_engine.card_data_loader import CardDataLoader
from MTG_bot.strategic_brain.config_rl import RLConfig
from MTG_bot import config
from MTG_bot.utils.logger import setup_logger

logger = setup_logger("MainTrain")

def main():
    cfg = RLConfig()
    
    print("\n" + "="*60)
    print(f"  MTG AI TRAINING: {cfg.get_model_name()}")
    print("="*60)
    
    # 1. Setup
    print(f"[SYSTEM] Hardware: {'CUDA' if HAS_TORCH and torch.cuda.is_available() else 'CPU'}")
    print(f"[SYSTEM] Mode: {'TORCH' if HAS_TORCH else 'MOCK (No Torch found)'}")
    
    loader = CardDataLoader(config.MTG_BOT_DB_PATH)
    env = MTGEnv(loader)
    student = Student(cfg.to_dict())
    
    # --- RESUME COUNTERS ---
    model_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
    model_path = os.path.join(model_dir, cfg.get_model_name())
    total_games_played = 0
    global_step_counter = 0
    
    if os.path.exists(model_path):
        # Estimate games based on file modification time or a secondary tracker
        # For now, we use a more robust detection: if the model exists, we assume
        # it has completed at least some generations.
        try:
            # We look for the latest backup to get a better game count estimate
            import glob
            backups = glob.glob(os.path.join(model_dir, model_path.replace(".pt", "_G*.pt")))
            if backups:
                latest_backup = max(backups, key=os.path.getctime)
                import re
                match = re.search(r"_G(\d+)\.pt", latest_backup)
                if match:
                    total_games_played = int(match.group(1))
                    global_step_counter = total_games_played * 100 # Rough estimate of 100 steps per game
            else:
                total_games_played = cfg.episodes_per_generation # Minimum one gen resume
        except Exception:
            total_games_played = cfg.episodes_per_generation

        print(f"[SYSTEM] Resume detected: {total_games_played} games already played.")
    else:
        print(f"[SYSTEM] No checkpoint found. Starting fresh.")

    teacher = Teacher(loader, cfg.to_dict())
    benchmarker = Benchmarker(env)
    
    # Optional WandB Init
    if cfg.use_wandb:
        try:
            import wandb
            wandb.init(project=cfg.project_name, config=cfg.to_dict(), name=cfg.get_model_name(), resume="allow")
        except ImportError:
            print("WandB not installed. Continuing with local logging.")

    # State for curriculum
    last_avg_score = 0.0
    last_self_play_winrate = 0.5
    last_avg_steps = 1000.0
    
    # current_matchup will now be Card ID lists
    current_matchup = ([], [])

    # 2. Main Generations
    for gen in range(cfg.num_generations):
        print("\n" + "#"*60)
        print(f"  GENERATION {gen+1}/{cfg.num_generations}")
        print(f"  FORMAT: {cfg.format_mode} | SET: {cfg.set_name}")
        print("#"*60)
        
        # --- TRAINING PHASE ---
        print("\n[PHASE 1: TRAINING]")
        current_matchup = teacher.select_archetypes(last_avg_score, last_self_play_winrate, last_avg_steps, total_games=total_games_played)
        deck_a, deck_b = teacher.generate_matchup(cfg.format_mode, current_matchup, total_games=total_games_played)
        
        print(f"Running {cfg.episodes_per_generation} episodes of self-play...")
        student, last_self_play_winrate, last_avg_steps, total_games_played, global_step_counter = run_training_cycle(
            cfg, student=student, fixed_matchup=(deck_a, deck_b),
            initial_games=total_games_played, initial_steps=global_step_counter
        )
        
        # --- VALIDATION PHASE ---
        print("\n[PHASE 2: VALIDATION]")
        total_score = 0.0
        levels = [1, 2]
        for level in levels:
            eval_results = benchmarker.run_level_evaluation(student, level, cfg.format_mode)
            if "error" not in eval_results:
                total_score += eval_results["score"]
                print(f"  Level {level} Solve Rate: {eval_results['score']*100:.1f}%")
                if cfg.use_wandb:
                    try:
                        import wandb
                        wandb.log({f"gen_metrics/level_{level}_score": eval_results['score']*100}, step=gen)
                    except ImportError: pass
        
        current_avg_score = total_score / len(levels)
        teacher.train_teacher(current_avg_score - last_avg_score)
        last_avg_score = current_avg_score

    print("\n" + "="*60)
    print("  ALL GENERATIONS COMPLETE")
    print("="*60)

if __name__ == "__main__":
    main()
