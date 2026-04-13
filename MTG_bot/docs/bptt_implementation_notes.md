# BPTT and Reward Implementation Notes

## 1. Reward Refinement: "Quick Wins" Focus
The reward logic has been updated to enforce efficiency without penalizing the model for surviving long games that it eventually loses.

### Key Changes:
- **Per-step Penalty Removed**: The `-0.005` penalty previously applied in every call to `MTGEnv.step` has been removed.
- **Conditional Win Penalty**: A length-based penalty is now applied only at the conclusion of an episode if the student is the winner.
- **Formula**: `final_reward = 10.0 - (episode_steps * 0.005)`
- **Rationale**: This ensures the model is incentivized to find the shortest path to victory, but isn't strictly penalized for game length in losing scenarios, which could lead to "premature surrender" behaviors.

## 2. Full BPTT (Backpropagation Through Time)
The model has been upgraded from a stateless transition-based learner to a recurrent temporal learner.

### Architectural Changes:
- **Model Recurrence**: Added an `nn.LSTMCell` to the `System2Transformer`. This cell integrates the mean board state (`z_global`) over time.
- **Temporal Fusion**: The recurrent hidden state is projected and fused back into the board tokens at each step, allowing the reasoning head to contextually "remember" past turns.
- **Hidden State Persistence**: The `rnn_state` is maintained throughout the episode and passed sequentially during training.

### Training Logic:
- **Trajectory-Based Buffer**: The `ExperienceBuffer` now stores full sequence trajectories (episodes) instead of individual steps.
- **Sequential Forward Pass**: During `train_step`, the model processes trajectories sequentially. The `rnn_state` from step $T$ is passed as input to step $T+1$.
- **Full Gradient Flow**: Gradients are accumulated across the entire trajectory before a `backward()` call is made. This allows the model to learn dependencies across long game horizons.

## 3. Performance Considerations
- **Memory Consumption**: Full BPTT through very long games (e.g., 500+ steps) significantly increases memory usage because all intermediate activations for the entire sequence must be stored for the backward pass.
- **Batching**: The `current_batch_size` in `train.py` now refers to the number of full trajectories sampled. This may need to be lowered if GPU "Out of Memory" errors occur.
- **Plan Transitions**: Plans within a turn are currently recorded as individual transitions within the sequence. Future optimizations could group these into "macro-actions".
