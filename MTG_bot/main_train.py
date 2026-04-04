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
    loader = CardDataLoader(config.MTG_BOT_DB_PATH)
    env = MTGEnv(loader)
    student = Student(cfg.to_dict())
    
    # --- RESUME LOGIC ---
    model_dir = "models"
    model_path = os.path.join(model_dir, cfg.get_model_name())
    total_games_played = 0
    global_step_counter = 0
    
    if HAS_TORCH and os.path.exists(model_path):
        try:
            student.model.load_state_dict(torch.load(model_path, map_location=student.device, weights_only=True))
            print(f"\n[SYSTEM] Resuming from existing checkpoint: {model_path}")
            # Estimate counters based on existence
            total_games_played = 10 
            global_step_counter = 5000 
        except Exception as e:
            print(f"[SYSTEM] Could not load checkpoint: {e}")
    else:
        print(f"\n[SYSTEM] No checkpoint found. Starting fresh.")

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
        current_matchup = teacher.select_archetypes(last_avg_score, last_self_play_winrate, last_avg_steps)
        deck_a, deck_b = teacher.generate_matchup(cfg.format_mode, current_matchup)
        
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
