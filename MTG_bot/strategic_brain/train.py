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
from MTG_bot.rule_engine.actions import PassPriorityAction, PassTurnAction, ActivateManaAbilityAction, \
    CastSpellAction, DeclareAttackerAction, DeclareBlockerAction, MakeChoiceAction, PlayLandAction
from MTG_bot.rule_engine.card_data_loader import CardDataLoader
from MTG_bot.utils.training_logger import TrainingLogger
from MTG_bot.strategic_brain.config_rl import RLConfig
from MTG_bot import config
from MTG_bot.utils.logger import setup_logger
from MTG_bot.utils.rng import stream

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
    frozen_model = copy.deepcopy(student.model).to(student.device)
    frozen_model.eval()
    
    teacher = Teacher(loader, cfg.to_dict())
    buffer = ExperienceBuffer()
    
    # Track win history for smoothed metrics
    win_history = [] # Stores 1 for win, 0.5 for draw/timeout, 0 for loss
    
    student_wins = 0
    total_games_in_gen = 0
    
    # Track the current decks for stability
    if fixed_matchup:
        deck_a, deck_b = fixed_matchup
    else:
        deck_a, deck_b = [], []
        
    format_name = cfg.format_mode
    
    # 2. Benchmark Curriculum State
    consecutive_mastery_counts = {}

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
        
        # Calculate 'Forced Activity' probability (1.0 -> 0.0 over 10k games)
        forced_play_prob = max(0.0, 1.0 - (total_games_played_overall / 10000))
        
        # Calculate Proactivity Bias (1.0 -> 0.0 over 10k games)
        proactivity_bias = max(0.0, 1.0 - (total_games_played_overall / 10000))
        
        # 1. Matchup Stability: Update decks only every N games
        if not fixed_matchup and episode % cfg.deck_refresh_freq == 0:
            current_format = cfg.format_mode
            print(f"\n" + "="*60)
            print(f" [Teacher] >>> DESIGNING AUTONOMOUS MATCHUP <<<")
            seeds_a, seeds_b = teacher.select_archetypes(0.0, student_wins/(total_games_in_gen or 1), 500)
            decks = teacher.generate_matchup(current_format, (seeds_a, seeds_b), total_games_played_overall)
            deck_a, deck_b = decks[0], decks[1]
            format_name = current_format
            print("="*60)
        elif fixed_matchup:
            format_name = cfg.format_mode
        
        # 2. Reset Environment
        obs, _, _ = env.reset_with_decks(deck_a, deck_b, mode=format_name)
        student.reset_rnn_state() # Clear RNN memory for new game
        p1_id = env.graph.players[0]
        p2_id = next(pid for pid in env.graph.players if pid != p1_id)
        
        p1_hand_size = len(env.graph.get_entities_in_zone(p1_id, vocab.ID_ZONE_HAND))
        p2_hand_size = len(env.graph.get_entities_in_zone(p2_id, vocab.ID_ZONE_HAND))
        print(f"\n[Game {total_games_played_overall}] {format_name} | Student (P1): {p1_hand_size} cards | Frozen (P2): {p2_hand_size} cards")
        
        done = False
        steps = 0
        episode_experience = []
        episode_reward = 0
        
        # Track action history per step to prevent infinite loops
        step_action_history = {}
        last_step_count = -1
        
        # Track "Meaningful Action" to detect stalls
        last_meaningful_step = 0
        last_p1_life, last_p2_life = 40, 40
        last_board_count = 0
        
        while not done and steps < cfg.steps_per_episode:
            active_id = obs["active_player"]
            is_student = (active_id == p1_id)
            
            # Reset action history if steps advanced
            if steps != last_step_count:
                step_action_history = {}
                last_step_count = steps

            # Select Action / Plan
            all_legal = env.engine.get_legal_moves()
            
            # Detect Stall
            current_board = len(env.graph.entities)
            current_p1_life = env.graph.entities[p1_id].properties.get('life_total', 40)
            current_p2_life = env.graph.entities[p2_id].properties.get('life_total', 40)
            
            is_stall = (steps - last_meaningful_step > 100)
            if current_p1_life != last_p1_life or current_p2_life != last_p2_life or current_board != last_board_count:
                last_meaningful_step = steps
                last_p1_life, last_p2_life = current_p1_life, current_p2_life
                last_board_count = current_board
            
            non_repetitive_legal = []
            for m in all_legal:
                m_str = str(m)
                if step_action_history.get(m_str, 0) < 5:
                    non_repetitive_legal.append(m)
            
            if not non_repetitive_legal:
                non_repetitive_legal = [m for m in all_legal if isinstance(m, (PassPriorityAction, PassTurnAction))]
                if not non_repetitive_legal: non_repetitive_legal = [all_legal[0]]

            intentional_moves = [m for m in non_repetitive_legal if isinstance(m, (CastSpellAction, DeclareAttackerAction, DeclareBlockerAction, MakeChoiceAction, PlayLandAction))]
            mana_moves = [m for m in non_repetitive_legal if isinstance(m, ActivateManaAbilityAction)]
            pass_moves = [m for m in non_repetitive_legal if isinstance(m, (PassPriorityAction, PassTurnAction))]
            
            if is_stall:
                candidate_moves = intentional_moves + pass_moves
                if not candidate_moves: candidate_moves = [all_legal[0]]
                if steps % 50 == 0: print(f"  [STALL WARNING] Step {steps}: Forcing game progression...")
            elif intentional_moves:
                sampled_mana = stream("exploration").sample(mana_moves, min(len(mana_moves), 1))
                candidate_moves = intentional_moves + sampled_mana
                if stream("exploration").random() > forced_play_prob:
                    candidate_moves += pass_moves
            else:
                if mana_moves and stream("exploration").random() < forced_play_prob:
                    candidate_moves = mana_moves
                else:
                    candidate_moves = non_repetitive_legal
            
            if not candidate_moves:
                candidate_moves = pass_moves if pass_moves else [non_repetitive_legal[0]]

            legal_moves = candidate_moves
                
            filtered_to_original = []
            for m in legal_moves:
                for idx, orig_m in enumerate(all_legal):
                    if m == orig_m:
                        filtered_to_original.append(idx)
                        break

            descriptors = []
            for m in legal_moves:
                d = env.mapper.get_action_descriptor(m, env.graph)
                flat_d = np.concatenate([[d["type"]], d["source_features"], d["target_features"]])
                descriptors.append(flat_d)
            
            obs["legal_action_descriptors"] = descriptors
            obs["legal_actions_count"] = len(legal_moves)

            if is_student:
                # 1. Generate Grounded Plan (with RNN state)
                res = student.select_action(
                    obs, requires_grad=HAS_TORCH, exploration_rate=exploration_rate, proactivity_bias=proactivity_bias
                )
                action_idx, value, log_prob, memory, thoughts, plan_sequence, plan_queries, _ = res

                # 2. Plan Execution Loop
                plan_steps_taken = 0
                max_plan_follow = 5
                current_plan_obs = obs
                
                for step_idx in range(min(len(plan_sequence or []), max_plan_follow)):
                    if step_idx == 0:
                        best_move_idx = action_idx
                        actual_move = legal_moves[best_move_idx]
                    else:
                        current_legal_all = env.engine.get_legal_moves()
                        curr_non_pass = [m for m in current_legal_all if not isinstance(m, (PassPriorityAction, PassTurnAction))]
                        if curr_non_pass and stream("exploration").random() < forced_play_prob:
                            current_legal = curr_non_pass
                        else:
                            current_legal = current_legal_all

                        if not current_legal: break
                        query = plan_queries[0, step_idx, :]

                        descriptors = []
                        for m in current_legal:
                            d = env.mapper.get_action_descriptor(m, env.graph)
                            flat_d = np.concatenate([[d["type"]], d["source_features"], d["target_features"]])
                            descriptors.append(flat_d)

                        with torch.no_grad():
                            proj_legal = student.model.decoder.action_proj(torch.tensor(np.array(descriptors), dtype=torch.float, device=student.device))
                            scores = torch.mv(proj_legal, query)

                            if exploration_rate > 0 and stream("exploration").random() < exploration_rate:
                                categories = {}
                                for idx, move in enumerate(current_legal):
                                    m_type = type(move)
                                    if m_type not in categories: categories[m_type] = []
                                    categories[m_type].append(idx)
                                if categories:
                                    chosen_cat = stream("exploration").choice(list(categories.keys()))
                                    best_move_idx = stream("exploration").choice(categories[chosen_cat])
                                else:
                                    best_move_idx = 0
                            else:
                                probs = torch.softmax(scores, dim=-1)
                                best_move_idx = torch.distributions.Categorical(probs).sample().item()
                        
                        actual_move = current_legal[best_move_idx]

                    original_legal = env.engine.get_legal_moves()
                    original_idx = -1
                    for i, m in enumerate(original_legal):
                        if m == actual_move:
                            original_idx = i; break
                    
                    if original_idx == -1: break

                    m_str = str(actual_move)
                    step_action_history[m_str] = step_action_history.get(m_str, 0) + 1
                    
                    next_obs, reward, done, info = env.step(original_idx)
                    action_str = info.get("action_taken", "Unknown")
                    
                    if "CastSpell" in action_str and ("Creature" in action_str or "Artifact" in action_str):
                        print(f"  *** [S] DEPLOYED PERMANENT: {action_str}")
                    elif "DeclareAttacker" in action_str:
                        print(f"  >>> [S] ATTACK: {action_str}")
                    elif "DeclareBlocker" in action_str:
                        print(f"  <<< [S] BLOCK: {action_str}")

                    p1_tele = f"S:{info.get('p1_life'):>2}hp {info.get('p1_hand'):>1}h"
                    p2_tele = f"F:{info.get('p2_life'):>2}hp {info.get('p2_hand'):>1}h"
                    print(f"  (Plan {step_idx}) Step {steps:4d}: [S] {action_str:<45} | {p1_tele} | {p2_tele}")

                    episode_experience.append({
                        "obs": current_plan_obs, "action": best_move_idx, "reward": reward, "value": value, 
                        "log_prob": log_prob.item() if hasattr(log_prob, "item") else log_prob, "done": done
                    })

                    current_plan_obs = next_obs
                    obs = next_obs
                    episode_reward += reward
                    steps += 1
                    global_step_counter += 1
                    plan_steps_taken += 1
                    if done: break
                
                if plan_steps_taken == 0 and not done:
                    original_idx = filtered_to_original[action_idx]
                    m_str = str(all_legal[original_idx])
                    step_action_history[m_str] = step_action_history.get(m_str, 0) + 1
                    next_obs, reward, done, info = env.step(original_idx)
                    episode_experience.append({
                        "obs": obs, "action": action_idx, "reward": reward, "value": value, 
                        "log_prob": log_prob.item() if hasattr(log_prob, "item") else log_prob, "done": done
                    })
                    obs = next_obs; episode_reward += reward; steps += 1; global_step_counter += 1
            else:
                # Frozen/Opponent Move
                if HAS_TORCH:
                    with torch.no_grad():
                        orig_model = student.model
                        student.model = frozen_model
                        res = student.select_action(
                            obs, requires_grad=False, exploration_rate=0.05, deterministic=False, proactivity_bias=proactivity_bias
                        )
                        action_idx = res[0]
                        student.model = orig_model
                else:
                    action_idx = student.select_action(obs, deterministic=False)[0]
                
                original_idx = filtered_to_original[action_idx]
                m_str = str(all_legal[original_idx])
                step_action_history[m_str] = step_action_history.get(m_str, 0) + 1
                next_obs, reward, done, info = env.step(original_idx)
                
                action_str = info.get("action_taken", "Unknown")
                p1_tele = f"S:{info.get('p1_life'):>2}hp {info.get('p1_hand'):>1}h"
                p2_tele = f"F:{info.get('p2_life'):>2}hp {info.get('p2_hand'):>1}h"
                print(f"  Step {steps:4d}: [F] {action_str:<45} | {p1_tele} | {p2_tele}")

                obs = next_obs; steps += 1; global_step_counter += 1
            
            if steps % 20 == 0:
                t_logger.log_metrics({
                    "step/p1_life": info.get("p1_life"),
                    "step/p2_life": info.get("p2_life"),
                    "step/p1_hand": info.get("p1_hand"),
                    "step/p2_hand": info.get("p2_hand"),
                }, global_step=global_step_counter)

            if is_student:
                t_logger.log_thinking(thoughts)
        
        # 3. Post-Episode Statistics
        p1_life, p2_life = info.get("p1_life", 40), info.get("p2_life", 40)
        is_timeout = (not done and steps >= cfg.steps_per_episode)
        
        game_result = 0.5
        length_penalty = steps * 0.005
        
        if env.engine.game_over and env.engine.winner_id is not None:
            if env.engine.winner_id == p1_id:
                student_wins += 1; winner_str = "STUDENT (P1)"; game_result = 1.0
                if episode_experience: episode_experience[-1]["reward"] -= length_penalty
            else:
                winner_str = "FROZEN (P2)"; game_result = 0.0
        elif is_timeout:
            if p1_life > p2_life:
                student_wins += 1; winner_str = "STUDENT (P1) [Timeout]"; game_result = 1.0
                if episode_experience: episode_experience[-1]["reward"] -= length_penalty
            elif p2_life > p1_life:
                winner_str = "FROZEN (P2) [Timeout]"; game_result = 0.0
            else:
                winner_str = "DRAW (Stall)"; game_result = 0.5
        else:
            winner_str = "UNKNOWN"; game_result = 0.5
            
        win_history.append(game_result)
        if len(win_history) > 100: win_history.pop(0)
        smoothed_win_rate = np.mean(win_history) * 100
        win_rate = (student_wins / total_games_in_gen) * 100
        print(f" >>> Episode End! Winner: {winner_str} | Steps: {steps} | S:{p1_life}hp F:{p2_life}hp | Student Win Rate (Gen): {win_rate:.1f}%")

        # 4. Process Returns and Advantages for PPO
        running_return = 0
        for i in reversed(range(len(episode_experience))):
            running_return = episode_experience[i]["reward"] + cfg.gamma * running_return * (1 - episode_experience[i]["done"])
            episode_experience[i]["return"] = running_return
            episode_experience[i]["advantage"] = running_return - episode_experience[i]["value"]
            
        if episode_experience:
            buffer.push(episode_experience)

        # 5. Global Metrics
        t_logger.log_metrics({
            "episode/student_win_rate_gen": win_rate,
            "episode/student_win_rate_smooth": smoothed_win_rate,
            "episode/reward": episode_reward,
            "episode/game_length": steps,
        }, global_game=total_games_played_overall)

        if total_games_played_overall % cfg.deck_refresh_freq == 0:
            from .benchmarker import Benchmarker
            benchmarker = Benchmarker(env)
            results = benchmarker.run_level_evaluation(student, level=1, current_format=cfg.format_mode)
            overall_solve_rate = results.get("score", 0.0) if "error" not in results else 0.0
            teacher.train_teacher(overall_solve_rate, student_wins / (total_games_in_gen or 1))

        # 6. Periodic Model Update
        if len(buffer.buffer) >= current_batch_size:
            loss_metrics = student.train_step(buffer.sample(current_batch_size), ppo_epochs=cfg.ppo_epochs, clip_param=cfg.clip_param)
            t_logger.log_metrics(loss_metrics, global_game=total_games_played_overall)

        if total_games_played_overall % cfg.save_freq == 0 or is_foundation_phase:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            model_dir = os.path.join(base_dir, "models")
            os.makedirs(model_dir, exist_ok=True)
            model_path = os.path.join(model_dir, cfg.get_model_name())
            if HAS_TORCH:
                try:
                    torch.save(student.model.state_dict(), model_path)
                    print(f"\n[SYSTEM] Checkpoint saved: {model_path}")
                except Exception as e:
                    print(f"[SYSTEM] Error saving checkpoint: {e}")

    t_logger.save_report()
    return student, win_rate / 100, 500, total_games_played_overall, global_step_counter
