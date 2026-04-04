from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class RLConfig:
    # --- Training Loop ---
    num_generations: int = 1000 # Extended for deep learning
    episodes_per_generation: int = 50 
    steps_per_episode: int = 10000 # Increased from 2000 to remove bottleneck
    deck_refresh_freq: int = 1 
    save_freq: int = 10
    
    # --- Formats ---
    format_mode: str = "Commander" 
    set_name: str = "M21"
    version: int = 3 # Pro-Scale Foundation
    
    # --- Dynamic Phase Control ---
    initial_phase_games: int = 1000
    initial_lr: float = 1e-3 
    initial_batch_size: int = 1 
    
    # --- PPO Hyperparameters ---
    lr: float = 2e-4 # Slightly lower for larger model stability
    batch_size: int = 32
    gamma: float = 0.99
    ppo_epochs: int = 4
    clip_param: float = 0.2
    
    # --- PRO-SCALE ARCHITECTURE ---
    embedding_dim: int = 1024 # Massive relational capacity
    nhead: int = 16 # 1024 / 64
    num_layers: int = 16 # Deep transformer depth
    belief_dim: int = 512 # Extensive opponent modeling
    max_actions: int = 100 # Effectively unlimited with dynamic decoder
    vocab_size: int = 50000 # Ready for all of MTG history
    component_dim: int = 32 # Detailed entity features
    
    # --- Reasoning ---
    max_thoughts: int = 8 # Deep iterative thinking
    thought_threshold: float = 0.2 # Force more reasoning passes

    # --- Hardware & Optimization ---
    use_cuda: bool = True 
    
    # --- Logging ---
    use_wandb: bool = True
    project_name: str = "MTG-AI-Pro-Foundation"
    
    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}

    def get_model_name(self) -> str:
        return f"{self.set_name}_{self.format_mode}_v{self.version}.pt"
