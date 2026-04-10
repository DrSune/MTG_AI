import torch
import torch.nn as nn
import torch.nn.functional as F
HAS_TORCH = True

import time
import os
import random
import numpy as np
from typing import List, Dict, Any, Optional, Tuple

from .environment import MTGEnv
from .student import Student, ExperienceBuffer
from .teacher import Teacher
from MTG_bot.rule_engine import vocabulary as vocab
from MTG_bot.rule_engine.actions import PassPriorityAction, PassTurnAction, ActivateManaAbilityAction
from MTG_bot.rule_engine.card_data_loader import CardDataLoader
from MTG_bot.utils.training_logger import TrainingLogger
from MTG_bot.strategic_brain.config_rl import RLConfig
from MTG_bot import config
from MTG_bot.utils.logger import setup_logger

logger = setup_logger("Training")

def train(cfg: RLConfig, student: Student = None, fixed_matchup: Optional[Tuple[List[int], List[int]]] = None, 
          initial_games: int = 0, initial_steps: int = 0):
    """
    Main training loop. 
    Runs self-play episodes, collects experience, and updates the student.
    """
    logger.info(f"Initializing Training Loop: {cfg.format_mode}")
    
    loader = CardDataLoader(config.MTG_BOT_DB_PATH)
    env = MTGEnv(loader)
    
    # Initialize logger with WandB if configured
    t_logger = TrainingLogger(use_wandb=cfg.use_wandb, config=cfg.to_dict())
    
    # 1. Initialize Student and Frozen version
    if student is None:
        student = Student(cfg.to_dict())
    
    # Persistent metrics across generations
    total_games_played_overall = initial_games
    global_step_counter = initial_steps
    
    # Create a frozen copy of the student for self-play evaluation
    import copy
    frozen_model = copy.deepcopy(student.model)
    frozen_model.eval()
    
    teacher = Teacher(loader, cfg.to_dict())
    buffer = ExperienceBuffer()
    
    student_wins = 0
    total_games_in_gen = 0
    
    # Track the current decks for stability
    if fixed_matchup:
        deck_a, deck_b = fixed_matchup
    else:
        deck_a, deck_b = [], []
        
    format_name = cfg.format_mode

    for episode in range(cfg.episodes_per_generation):
        total_games_played_overall += 1
        total_games_in_gen += 1
        is_foundation_phase = total_games_played_overall <= cfg.initial_phase_games
        
        # Adjust Hyperparameters dynamically
        if is_foundation_phase:
            current_lr = cfg.initial_lr
            current_batch_size = cfg.initial_batch_size
        else:
            current_lr = cfg.lr
            current_batch_size = cfg.batch_size
            
        student.set_learning_rate(current_lr)

        # Update frozen model periodically (e.g., every 20 episodes)
        if HAS_TORCH and total_games_played_overall > 0 and total_games_played_overall % 20 == 0:
            frozen_model.load_state_dict(student.model.state_dict())
            print(f"\n[SYSTEM] Frozen Student weights updated to match current Student.")

        # Calculate exploration rate: Start higher and decay slower
        exploration_rate = max(0.15, 0.7 * (1 - total_games_played_overall / 10000))
        
        # Calculate curriculum discovery factor (1.0 -> 0.0 over 10k games)
        discovery_factor = max(0.0, 1.0 - (total_games_played_overall / 10000))
        env.discovery_factor = discovery_factor
        
        # Calculate 'Forced Activity' probability (1.0 -> 0.0 over 5k games)
        # This forces the model to choose non-pass actions if they are legal.
        forced_play_prob = max(0.0, 1.0 - (total_games_played_overall / 5000))
        
        # 1. Matchup Stability: Update decks only every N games
        if not fixed_matchup and episode % cfg.deck_refresh_freq == 0:
            current_format = cfg.format_mode
            print(f"\n" + "="*60)
            print(f" [Teacher] >>> DESIGNING AUTONOMOUS MATCHUP <<<")
            seeds_a, seeds_b = teacher.select_archetypes(0.0, student_wins/(total_games_in_gen or 1), 500)
            # Use Teacher.generate_matchup to apply land curriculum
            decks = teacher.generate_matchup(current_format, (seeds_a, seeds_b), total_games_played_overall)
            deck_a, deck_b = decks[0], decks[1]
            format_name = current_format
            print("="*60)
        elif fixed_matchup:
            format_name = cfg.format_mode
        
        # 2. Reset Environment
        obs, _, _ = env.reset_with_decks(deck_a, deck_b, mode=format_name)
        p1_id = env.graph.players[0]
        p2_id = next(pid for pid in env.graph.players if pid != p1_id)
        
        p1_hand_size = len(env.graph.get_entities_in_zone(p1_id, vocab.ID_ZONE_HAND))
        p2_hand_size = len(env.graph.get_entities_in_zone(p2_id, vocab.ID_ZONE_HAND))
        print(f"\n[Game {total_games_played_overall}] {format_name} | Student (P1): {p1_hand_size} cards | Frozen (P2): {p2_hand_size} cards")
        
        done = False
        steps = 0
        episode_experience = []
        episode_reward = 0
        last_menu_str = ""
        
        while not done and steps < cfg.steps_per_episode:
            active_id = obs["active_player"]
            is_student = (active_id == p1_id)
            current_turn = env.graph.turn_number
            
            # Select Action / Plan
            all_legal = env.engine.get_legal_moves()
            
            # INTENTIONAL ACTION FILTERING: 
            # If we have spells to cast or combat moves, limit the number of mana tapping options
            # to prevent the model from getting lost in 'Safe' but 'Useless' loops.
            intentional_moves = [m for m in all_legal if isinstance(m, (CastSpellAction, DeclareAttackerAction, DeclareBlockerAction, MakeChoiceAction, PlayLandAction))]
            mana_moves = [m for m in all_legal if isinstance(m, ActivateManaAbilityAction)]
            pass_moves = [m for m in all_legal if isinstance(m, (PassPriorityAction, PassTurnAction))]
            
            if intentional_moves:
                # If we have something 'Real' to do, only show a few mana options (or none if prob hits)
                sampled_mana = random.sample(mana_moves, min(len(mana_moves), 2))
                candidate_moves = intentional_moves + sampled_mana
                if random.random() > forced_play_prob:
                    candidate_moves += pass_moves
            else:
                candidate_moves = all_legal

            # FORCED ACTIVITY MASKING: Temporarily hide Pass actions if alternatives exist
            non_pass_moves = [m for m in candidate_moves if not isinstance(m, (PassPriorityAction, PassTurnAction))]
            if non_pass_moves and random.random() < forced_play_prob:
                legal_moves = non_pass_moves
            else:
                legal_moves = candidate_moves
                
            legal_move_names = [type(m).__name__.replace("Action", "") for m in legal_moves]
            
            # Create a mapping from filtered indices back to original engine indices
            filtered_to_original = []
            for m in legal_moves:
                for idx, orig_m in enumerate(all_legal):
                    if m == orig_m:
                        filtered_to_original.append(idx)
                        break

            if is_student:
                # Update observation with FILTERED descriptors
                descriptors = []
                for m in legal_moves:
                    d = env.mapper.get_action_descriptor(m, env.graph)
                    flat_d = np.concatenate([[d["type"]], d["source_features"], d["target_features"]])
                    descriptors.append(flat_d)
                
                # Update current obs for the model
                obs["legal_action_descriptors"] = descriptors
                obs["legal_actions_count"] = len(legal_moves)

                # 1. Generate Grounded Plan
                action_idx, value, log_prob, memory, thoughts, plan_sequence, plan_queries = student.select_action(
                    obs, requires_grad=HAS_TORCH, exploration_rate=exploration_rate
                )

                # 2. Plan Execution Loop (Grounded Sequential Thinking)
                # We attempt to follow the plan as long as steps are legal and no rethink/end is hit.
                plan_steps_taken = 0
                max_plan_follow = 5 # Don't follow too far without seeing fresh board
                
                current_plan_obs = obs
                
                for step_idx in range(min(len(plan_sequence), max_plan_follow)):
                    # Get legal moves for CURRENT sub-state (re-apply masking if needed)
                    current_legal_all = env.engine.get_legal_moves()
                    curr_non_pass = [m for m in current_legal_all if not isinstance(m, (PassPriorityAction, PassTurnAction))]
                    if curr_non_pass and random.random() < forced_play_prob:
                        current_legal = curr_non_pass
                    else:
                        current_legal = current_legal_all

                    if not current_legal: break

                    if step_idx == 0:
                        # For the first step, use the action_idx already selected
                        # This action_idx is ALREADY an index into the FILTERED current_legal
                        best_move_idx = action_idx
                    else:
                        # Match current legal moves against the query for this plan step
                        query = plan_queries[0, step_idx, :]

                        # Get descriptors for current FILTERED legal moves
                        descriptors = []
                        for m in current_legal:
                            d = env.mapper.get_action_descriptor(m, env.graph)
                            flat_d = np.concatenate([[d["type"]], d["source_features"], d["target_features"]])
                            descriptors.append(flat_d)

                        # Calculate similarity (dot product)
                        with torch.no_grad():
                            proj_legal = student.model.decoder.action_proj(torch.tensor(np.array(descriptors), dtype=torch.float, device=student.device))
                            scores = torch.mv(proj_legal, query)

                            if exploration_rate > 0 and random.random() < exploration_rate:
                                categories = {}
                                for idx, move in enumerate(current_legal):
                                    m_type = type(move)
                                    if m_type not in categories: categories[m_type] = []
                                    categories[m_type].append(idx)
                                chosen_cat = random.choice(list(categories.keys()))
                                best_move_idx = random.choice(categories[chosen_cat])
                            else:
                                probs = torch.softmax(scores, dim=-1)
                                best_move_idx = torch.distributions.Categorical(probs).sample().item()

                    # Execute the move (must use ORIGINAL engine index if needed, 
                    # but here env.step handles it via index in its OWN current engine.get_legal_moves call)
                    # Wait, env.step(idx) uses engine.get_legal_moves()[idx]. 
                    # If we filtered, we must map back to the original index.
                    
                    actual_move = current_legal[best_move_idx]
                    # Find original index for env.step
                    original_legal = env.engine.get_legal_moves()
                    original_idx = -1
                    for i, m in enumerate(original_legal):
                        if m == actual_move:
                            original_idx = i; break
                    
                    if original_idx == -1: break # Should not happen

                    next_obs, reward, done, info = env.step(original_idx)
                    
                    # Log the grounded action
                    action_str = info.get("action_taken", "Unknown")
                    role = "[S]"
                    
                    # ENHANCED LOGGING: Alert when active play happens
                    if "CastSpell" in action_str and ("Creature" in action_str or "Artifact" in action_str):
                        print(f"  *** [S] DEPLOYED PERMANENT: {action_str}")
                    elif "DeclareAttacker" in action_str:
                        print(f"  >>> [S] ATTACK: {action_str}")
                    elif "DeclareBlocker" in action_str:
                        print(f"  <<< [S] BLOCK: {action_str}")

                    p1_deck = len(env.graph.get_entities_in_zone(p1_id, vocab.ID_ZONE_LIBRARY))
                    p2_deck = len(env.graph.get_entities_in_zone(p2_id, vocab.ID_ZONE_LIBRARY))
                    
                    p1_tele = f"S:{info.get('p1_life'):>2}hp {info.get('p1_hand'):>1}h {p1_deck:>2}d"
                    p2_tele = f"F:{info.get('p2_life'):>2}hp {info.get('p2_hand'):>1}h {p2_deck:>2}d"
                    print(f"  (Plan {step_idx}) Step {steps:4d}: {role} {action_str:<45} | {p1_tele} | {p2_tele}")

                    # Store transition
                    if is_student:
                        episode_experience.append({
                            "obs": current_plan_obs, "action": best_move_idx, "reward": reward, "value": value, 
                            "log_prob": log_prob.item() if hasattr(log_prob, "item") else log_prob, "done": done
                        })

                    # Update state
                    current_plan_obs = next_obs
                    obs = next_obs
                    episode_reward += reward
                    steps += 1
                    global_step_counter += 1
                    plan_steps_taken += 1
                    
                    if done: break
                
                # If plan was followed, 'obs' is now the state AFTER the last plan step.
                # We should NOT append the original action_idx again.
                if plan_steps_taken == 0 and not done:
                    # Fallback if plan loop didn't execute (e.g. immediate END_PLAN)
                    # We must take at least one real action (usually Pass)
                    next_obs, reward, done, info = env.step(action_idx)
                    
                    # Store fallback transition
                    episode_experience.append({
                        "obs": obs, "action": action_idx, "reward": reward, "value": value, 
                        "log_prob": log_prob.item() if hasattr(log_prob, "item") else log_prob, "done": done
                    })
                    
                    obs = next_obs; episode_reward += reward; steps += 1; global_step_counter += 1
            else:
                # Frozen/Opponent Move (Non-planning for simplicity)
                if HAS_TORCH:
                    with torch.no_grad():
                        orig_model = student.model
                        student.model = frozen_model
                        # Use small exploration for Frozen to keep it "active"
                        action_idx, _, _, _, _, _, _ = student.select_action(
                            obs, requires_grad=False, exploration_rate=0.05, deterministic=False
                        )
                        student.model = orig_model
                else:
                    action_idx, _, _, _, _, _, _ = student.select_action(obs, deterministic=False)
                
                next_obs, reward, done, info = env.step(action_idx)
                
                # Log the frozen model's action
                action_str = info.get("action_taken", "Unknown")
                role = "[F]"
                
                # ENHANCED LOGGING for Frozen too
                if "CastSpell" in action_str and ("Creature" in action_str or "Artifact" in action_str):
                    print(f"  *** [F] DEPLOYED PERMANENT: {action_str}")
                elif "DeclareAttacker" in action_str:
                    print(f"  >>> [F] ATTACK: {action_str}")
                elif "DeclareBlocker" in action_str:
                    print(f"  <<< [F] BLOCK: {action_str}")

                p1_deck = len(env.graph.get_entities_in_zone(p1_id, vocab.ID_ZONE_LIBRARY))
                p2_deck = len(env.graph.get_entities_in_zone(p2_id, vocab.ID_ZONE_LIBRARY))
                
                p1_tele = f"S:{info.get('p1_life'):>2}hp {info.get('p1_hand'):>1}h {p1_deck:>2}d"
                p2_tele = f"F:{info.get('p2_life'):>2}hp {info.get('p2_hand'):>1}h {p2_deck:>2}d"
                print(f"  Step {steps:4d}: {role} {action_str:<45} | {p1_tele} | {p2_tele}")

                obs = next_obs; steps += 1; global_step_counter += 1
            
            if steps % 20 == 0:
                p1_deck = len(env.graph.get_entities_in_zone(p1_id, vocab.ID_ZONE_LIBRARY))
                p2_deck = len(env.graph.get_entities_in_zone(p2_id, vocab.ID_ZONE_LIBRARY))
                
                t_logger.log_metrics({
                    "step/p1_life": info.get("p1_life"),
                    "step/p2_life": info.get("p2_life"),
                    "step/p1_hand": info.get("p1_hand"),
                    "step/p2_hand": info.get("p2_hand"),
                    "step/p1_deck": p1_deck,
                    "step/p2_deck": p2_deck,
                    "step/p1_mana": info.get("p1_mana"),
                    "step/p2_mana": info.get("p2_mana")
                }, global_step=global_step_counter)

            if is_student:
                t_logger.log_thinking(thoughts)

            # Note: Transition recording is now handled INSIDE the plan/fallback loop above.
            # We must NOT append again here.
            
            episode_reward += reward if is_student else 0
        
        # 3. Post-Episode Statistics
        p1_id = env.graph.players[0]
        p1_life, p2_life = info.get("p1_life", 40), info.get("p2_life", 40)
        is_timeout = (not done and steps >= cfg.steps_per_episode)
        
        # Check Engine's Winner First (Handles Deckout, State-Based Actions)
        if env.engine.game_over and env.engine.winner_id is not None:
            if env.engine.winner_id == p1_id:
                student_wins += 1; winner_str = "STUDENT (P1)"
            else:
                winner_str = "FROZEN (P2)"
        elif is_timeout:
            # Fallback for Timeout/Draw
            if p1_life > p2_life:
                student_wins += 1; winner_str = "STUDENT (P1) [Timeout]"
            elif p2_life > p1_life:
                winner_str = "FROZEN (P2) [Timeout]"
            else:
                winner_str = "DRAW (Stall)"
        else:
            # Fallback for other completions (e.g. done but winner_id not set, shouldn't happen)
            if p1_life > p2_life:
                student_wins += 1; winner_str = "STUDENT (P1)"
            else:
                winner_str = "FROZEN (P2)"
            
        win_rate = (student_wins / total_games_in_gen) * 100
        print(f" >>> Episode End! Winner: {winner_str} | Steps: {steps} | S:{p1_life}hp F:{p2_life}hp | Student Win Rate: {win_rate:.1f}%")

        # 4. Process Returns and Advantages for PPO
        running_return = 0
        for i in reversed(range(len(episode_experience))):
            running_return = episode_experience[i]["reward"] + cfg.gamma * running_return * (1 - episode_experience[i]["done"])
            episode_experience[i]["return"] = running_return
            episode_experience[i]["advantage"] = running_return - episode_experience[i]["value"]
            buffer.push(episode_experience[i])

        # 5. Global Metrics
        t_logger.log_metrics({
            "episode/student_win_rate": win_rate,
            "episode/reward": episode_reward,
            "episode/game_length": steps
        }, global_game=total_games_played_overall)

        # 6. Periodic Model Update & Checkpoint
        if len(buffer.buffer) >= current_batch_size:
            loss_metrics = student.train_step(buffer.sample(current_batch_size), ppo_epochs=cfg.ppo_epochs, clip_param=cfg.clip_param)
            t_logger.log_metrics(loss_metrics, global_game=total_games_played_overall)

        # SAVE LOGIC: Save every 10 games, or EVERY game during foundation phase
        if total_games_played_overall % cfg.save_freq == 0 or is_foundation_phase:
            # Use absolute path to avoid ambiguity
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            model_dir = os.path.join(base_dir, "models")
            os.makedirs(model_dir, exist_ok=True)
            model_path = os.path.join(model_dir, cfg.get_model_name())
            
            if HAS_TORCH:
                try:
                    torch.save(student.model.state_dict(), model_path)
                    print(f"\n[SYSTEM] Checkpoint saved: {model_path} (Game {total_games_played_overall})")
                    
                    if total_games_played_overall % 50 == 0:
                        backup_path = model_path.replace(".pt", f"_G{total_games_played_overall}.pt")
                        torch.save(student.model.state_dict(), backup_path)
                        print(f"[SYSTEM] Permanent backup created: {backup_path}")
                except Exception as e:
                    print(f"[SYSTEM] Error saving checkpoint: {e}")

    t_logger.save_report()
    return student, win_rate / 100, 500, total_games_played_overall, global_step_counter
