import json
import os
import numpy as np
from datetime import datetime
from collections import defaultdict

class TrainingLogger:
    """
    Advanced logging for MTG AI training.
    Supports dual-track WandB metrics (Step-level vs Game-level).
    """
    def __init__(self, log_dir="logs/training_stats", use_wandb=False, config=None):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.use_wandb = use_wandb
        
        if self.use_wandb:
            try:
                import wandb
                wandb.init(project="MTG-AI-Pro-Foundation", config=config, name=self.session_id)
                # DUAL-TRACK DEFINITION
                # episode/* metrics use global_game as x-axis
                # step/* metrics use global_step as x-axis
                wandb.define_metric("step/*", step_metric="global_step")
                wandb.define_metric("episode/*", step_metric="global_game")
                wandb.define_metric("thinking/*", step_metric="global_step")
            except ImportError:
                print("WandB not installed. Falling back to local logging.")
                self.use_wandb = False

        self.card_stats = defaultdict(lambda: {"played": 0, "wins": 0, "impact_sum": 0.0})
        self.episode_history = []
        self.thinking_stats = []

    def log_metrics(self, metrics: dict, global_step: int = None, global_game: int = None):
        """Logs scalar metrics to WandB with dual-axis support."""
        if not self.use_wandb: return
        import wandb
        
        log_data = metrics.copy()
        if global_step is not None:
            log_data["global_step"] = global_step
        if global_game is not None:
            log_data["global_game"] = global_game
            
        # Add thinking stats
        if self.thinking_stats:
            if global_step is not None:
                log_data["thinking/step_avg_passes"] = np.mean(self.thinking_stats)
                self.thinking_stats = [] # Clear for next step sample
            elif global_game is not None:
                log_data["thinking/game_avg_passes"] = np.mean(self.thinking_stats)
                self.thinking_stats = [] # Clear for next game
            
        wandb.log(log_data)

    def log_thinking(self, thoughts: int):
        self.thinking_stats.append(thoughts)

    def save_report(self):
        # JSON local report logic
        pass
