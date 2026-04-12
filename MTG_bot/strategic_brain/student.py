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

class ExperienceBuffer:
    def __init__(self, capacity: int = 10000):
        self.buffer = []
        self.capacity = capacity
    def push(self, transition):
        if len(self.buffer) >= self.capacity: self.buffer.pop(0)
        self.buffer.append(transition)
    def sample(self, batch_size: int):
        if len(self.buffer) < batch_size: return self.buffer
        return random.sample(self.buffer, batch_size)

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
                    obsolete_keys = ["decoder.rethink_head.weight", "decoder.rethink_head.bias", "decoder.value_head.weight", "decoder.value_head.bias"]
                    
                    for name, param in state_dict.items():
                        if name in own_state:
                            if own_state[name].shape == param.shape:
                                compatible_state[name] = param
                            else:
                                self.logger.warning(f"Shape mismatch for {name}: {own_state[name].shape} vs {param.shape}. Skipping.")
                        elif name not in obsolete_keys:
                            self.logger.warning(f"Key {name} not in model. Skipping.")
                    
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

    def set_learning_rate(self, lr: float):
        if HAS_TORCH and self.optimizer:
            for param_group in self.optimizer.param_groups:
                param_group['lr'] = lr

    def select_action(self, obs: Dict[str, Any], deterministic: bool = False, requires_grad: bool = False, exploration_rate: float = 0.0, proactivity_bias: float = 0.0) -> Tuple[int, float, Any, Any, int, Optional[List[Dict[str, Any]]], Optional[torch.Tensor]]:
        legal_descriptors = obs.get("legal_action_descriptors", [[0]*65])
        
        if not HAS_TORCH:
            return random.randint(0, len(legal_descriptors)-1), 0.0, 0.0, None, 1, None, None

        if requires_grad: self.model.train()
        else: self.model.eval()

        with torch.set_grad_enabled(requires_grad):
            tokens = obs["tokens"]
            # Convert to tensors
            atomic_ids = torch.as_tensor(tokens["atomic_ids"], device=self.device).unsqueeze(0)
            features = torch.as_tensor(tokens["component_features"], device=self.device).unsqueeze(0)

            # OPTIMIZATION: Convert list of arrays to a single numpy array first to avoid slow conversion warning
            descriptors_np = np.array(legal_descriptors, dtype=np.float32)
            descriptors = torch.as_tensor(descriptors_np, device=self.device).unsqueeze(0)

            output = self.model(atomic_ids, features, descriptors, num_passes=self.max_thoughts if not deterministic else 1, threshold=self.thought_threshold)
            logits = output["action_logits"]
            
            # --- PROACTIVITY BIAS (Foundation Phase Hook) ---
            if proactivity_bias > 0 and not deterministic:
                # Identify 'Pass' actions in the legal moves
                # We know the type ID from the first element of descriptors
                # Action types (matching ActionSpaceMapper): 6:PassPriority, 7:PassTurn
                for i, desc in enumerate(legal_descriptors):
                    a_type = desc[0]
                    if a_type in [6, 7]: # Pass actions
                        logits[0, i] -= 10.0 * proactivity_bias # Heavily discourage passing
            
            probs = torch.softmax(logits, dim=-1)
            if not deterministic and random.random() < exploration_rate:
                idx = random.randint(0, len(legal_descriptors) - 1)
            else:
                if deterministic: idx = torch.argmax(logits, dim=-1).item()
                else: idx = torch.distributions.Categorical(probs).sample().item()
            
            log_prob = torch.log(probs[0, idx] + 1e-10)
            return int(idx), output["value"].item(), log_prob, output["state_memory"], output["passes_taken"], output.get("plan_sequence"), output.get("plan_step_queries")

    def train_step(self, batch: List[Dict[str, Any]], ppo_epochs: int = 4, clip_param: float = 0.2) -> Dict[str, float]:
        if not HAS_TORCH or not self.optimizer: return {}
        self.model.train()
        
        total_loss = 0
        for _ in range(ppo_epochs):
            for t in batch:
                obs = t["obs"]
                atomic_ids = torch.as_tensor(obs["tokens"]["atomic_ids"], device=self.device).unsqueeze(0)
                features = torch.as_tensor(obs["tokens"]["component_features"], device=self.device).unsqueeze(0)
                
                descriptors_np = np.array(obs["legal_action_descriptors"], dtype=np.float32)
                descriptors = torch.as_tensor(descriptors_np, device=self.device).unsqueeze(0)
                
                action_idx = t["action"]
                old_log_prob = t["log_prob"]
                returns = torch.tensor([t["return"]], device=self.device, dtype=torch.float)
                advantage = torch.tensor([t["advantage"]], device=self.device, dtype=torch.float)

                output = self.model(atomic_ids, features, descriptors)
                logits = output["action_logits"]
                value = output["value"]
                
                new_probs = torch.softmax(logits, dim=-1)
                new_log_prob = torch.log(new_probs[0, action_idx] + 1e-10)
                
                ratio = torch.exp(new_log_prob - old_log_prob)
                surr1 = ratio * advantage
                surr2 = torch.clamp(ratio, 1.0 - clip_param, 1.0 + clip_param) * advantage
                
                policy_loss = -torch.min(surr1, surr2)
                value_loss = F.mse_loss(value.view(-1), returns.view(-1))
                
                loss = policy_loss + 0.5 * value_loss
                
                self.optimizer.zero_grad()
                loss.backward()
                self.optimizer.step()
                total_loss += loss.item()
                
        return {"loss": total_loss / (len(batch) * ppo_epochs)}
