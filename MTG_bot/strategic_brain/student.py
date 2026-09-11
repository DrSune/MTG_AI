try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    HAS_TORCH = True
except ImportError:
    torch = None
    nn = None
    F = None
    HAS_TORCH = False

import random
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from .model import System2Transformer
from MTG_bot.utils.logger import setup_logger
from MTG_bot.utils.rng import stream

class ExperienceBuffer:
    def __init__(self, capacity: int = 1000):
        self.buffer = [] # Now stores full trajectories
        self.capacity = capacity
    def push(self, trajectory: List[Dict[str, Any]]):
        if len(self.buffer) >= self.capacity: self.buffer.pop(0)
        self.buffer.append(trajectory)
    def sample(self, batch_size: int):
        if len(self.buffer) < batch_size: return self.buffer
        return stream("policy").sample(self.buffer, batch_size)

class Student:
    def __init__(self, model_config: Dict[str, Any]):
        self.logger = setup_logger(__name__)
        
        if HAS_TORCH:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = "cpu"
        
        self.model = System2Transformer(
            vocab_size=model_config.get("vocab_size", 50000),
            embedding_dim=model_config.get("embedding_dim", 1024),
            component_dim=model_config.get("component_dim", 32),
            nhead=model_config.get("nhead", 16),
            num_layers=model_config.get("num_layers", 16),
            belief_dim=model_config.get("belief_dim", 512),
            max_actions=model_config.get("max_actions", 100)
        ).to(self.device)
        
        # --- ROBUST WEIGHT LOADING ---
        if HAS_TORCH:
            import os
            # Attempt to load latest checkpoint if it exists
            model_name = f"{model_config.get('set_name', 'M21')}_{model_config.get('format_mode', 'Commander')}_v{model_config.get('version', 3)}.pt"
            checkpoint_path = os.path.join("models", model_name)
            if os.path.exists(checkpoint_path):
                try:
                    state_dict = torch.load(checkpoint_path, map_location=self.device, weights_only=True)
                    # Check for size mismatches
                    own_state = self.model.state_dict()
                    compatible_state = {}
                    
                    for name, param in state_dict.items():
                        if name in own_state:
                            if own_state[name].shape == param.shape:
                                compatible_state[name] = param
                            else:
                                self.logger.warning(f"Shape mismatch for {name}: {own_state[name].shape} vs {param.shape}. Skipping.")
                    
                    self.model.load_state_dict(compatible_state, strict=False)
                    self.logger.info(f"Loaded {len(compatible_state)}/{len(state_dict)} tensors from {checkpoint_path}")
                except Exception as e:
                    self.logger.error(f"Failed to load weights from {checkpoint_path}: {e}. Initializing fresh.")

            self.model = self.model.to(self.device)
            initial_lr = model_config.get("initial_lr") or model_config.get("lr", 1e-4)
            self.optimizer = torch.optim.Adam(self.model.parameters(), lr=initial_lr)
        else:
            self.optimizer = None

        self.max_thoughts = model_config.get("max_thoughts", 8)
        self.thought_threshold = model_config.get("thought_threshold", 0.2)
        self.last_rnn_state = None # Track state during collection

    def set_learning_rate(self, lr: float):
        if HAS_TORCH and self.optimizer:
            for param_group in self.optimizer.param_groups:
                param_group['lr'] = lr

    def reset_rnn_state(self):
        self.last_rnn_state = None

    def select_action(self, obs: Dict[str, Any], deterministic: bool = False, requires_grad: bool = False, 
                      exploration_rate: float = 0.0, proactivity_bias: float = 0.0, 
                      rnn_state: Any = None) -> Tuple[int, float, Any, Any, int, Optional[List[Dict[str, Any]]], Optional[torch.Tensor], Any]:
        """
        Returns (action_idx, value, log_prob, memory, thoughts, plan, plan_queries, next_rnn_state)
        """
        legal_descriptors = obs.get("legal_action_descriptors", [[0]*65])
        
        if not HAS_TORCH:
            return stream("policy").randint(0, len(legal_descriptors)-1), 0.0, 0.0, None, 1, None, None, None

        if requires_grad: self.model.train()
        else: self.model.eval()

        with torch.set_grad_enabled(requires_grad):
            tokens = obs["tokens"]
            atomic_ids = torch.as_tensor(tokens["atomic_ids"], device=self.device).unsqueeze(0)
            features = torch.as_tensor(tokens["component_features"], device=self.device).unsqueeze(0)
            descriptors_np = np.array(legal_descriptors, dtype=np.float32)
            descriptors = torch.as_tensor(descriptors_np, device=self.device).unsqueeze(0)

            # Use provided state or last tracked state
            current_state = rnn_state if rnn_state is not None else self.last_rnn_state

            output = self.model(
                atomic_ids, features, descriptors, 
                rnn_state=current_state,
                num_passes=self.max_thoughts if not deterministic else 1, 
                threshold=self.thought_threshold
            )
            
            logits = output["action_logits"]
            self.last_rnn_state = output["rnn_state"] # Update for next step in episode
            
            # --- PROACTIVITY BIAS ---
            if proactivity_bias > 0 and not deterministic:
                for i, desc in enumerate(legal_descriptors):
                    if desc[0] in [6, 7]: # Pass actions
                        logits[0, i] -= 10.0 * proactivity_bias
            
            probs = torch.softmax(logits, dim=-1)
            if not deterministic and stream("exploration").random() < exploration_rate:
                idx = stream("exploration").randint(0, len(legal_descriptors) - 1)
            else:
                if deterministic: idx = torch.argmax(logits, dim=-1).item()
                else: idx = torch.distributions.Categorical(probs).sample().item()
            
            log_prob = torch.log(probs[0, idx] + 1e-10)
            return int(idx), output["value"].item(), log_prob, output["state_memory"], output["passes_taken"], output.get("plan_sequence"), output.get("plan_step_queries"), output["rnn_state"]

    def train_step(self, trajectory_batch: List[List[Dict[str, Any]]], ppo_epochs: int = 4, clip_param: float = 0.2) -> Dict[str, float]:
        """
        Full BPTT: Backpropagates through entire trajectories.
        Each item in trajectory_batch is an entire episode.
        """
        if not HAS_TORCH or not self.optimizer: return {}
        self.model.train()
        
        total_loss = 0
        batch_size = len(trajectory_batch)
        
        for _ in range(ppo_epochs):
            self.optimizer.zero_grad()
            epoch_loss = 0
            
            for episode in trajectory_batch:
                # Initialize hidden state for the start of the episode
                rnn_state = None 
                episode_loss = 0
                
                # Full BPTT: Run sequentially through the episode to maintain gradient flow
                for t in episode:
                    obs = t["obs"]
                    atomic_ids = torch.as_tensor(obs["tokens"]["atomic_ids"], device=self.device).unsqueeze(0)
                    features = torch.as_tensor(obs["tokens"]["component_features"], device=self.device).unsqueeze(0)
                    descriptors_np = np.array(obs["legal_action_descriptors"], dtype=np.float32)
                    descriptors = torch.as_tensor(descriptors_np, device=self.device).unsqueeze(0)
                    
                    action_idx = t["action"]
                    old_log_prob = t["log_prob"]
                    returns = torch.tensor([t["return"]], device=self.device, dtype=torch.float)
                    advantage = torch.tensor([t["advantage"]], device=self.device, dtype=torch.float)

                    # Forward pass WITH rnn_state continuity
                    output = self.model(atomic_ids, features, descriptors, rnn_state=rnn_state)
                    logits = output["action_logits"]
                    value = output["value"]
                    rnn_state = output["rnn_state"] # Pass to next step in sequence
                    
                    new_probs = torch.softmax(logits, dim=-1)
                    new_log_prob = torch.log(new_probs[0, action_idx] + 1e-10)
                    
                    ratio = torch.exp(new_log_prob - old_log_prob)
                    surr1 = ratio * advantage
                    surr2 = torch.clamp(ratio, 1.0 - clip_param, 1.0 + clip_param) * advantage
                    
                    policy_loss = -torch.min(surr1, surr2)
                    value_loss = F.mse_loss(value.view(-1), returns.view(-1))
                    
                    # Accumulate loss for the step
                    episode_loss += (policy_loss + 0.5 * value_loss)
                
                # Average loss over the episode length
                episode_loss = episode_loss / len(episode)
                # Backward pass through the entire episode trajectory (Full BPTT)
                episode_loss.backward()
                epoch_loss += episode_loss.item()
            
            # Optimizer step after accumulating gradients from all episodes in batch
            self.optimizer.step()
            total_loss += epoch_loss / batch_size
                
        return {"loss": total_loss / ppo_epochs}
