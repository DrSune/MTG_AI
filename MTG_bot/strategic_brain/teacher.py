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

from typing import List, Dict, Any, Optional, Tuple
import random
import sqlite3
import re
from MTG_bot.rule_engine.card_data_loader import CardDataLoader
from MTG_bot.utils.logger import setup_logger
from .deck_generator import DeckGenerator, Archetypes
from .model import TeacherModel

try:
    import torch.optim as optim
except ImportError:
    optim = None

class Teacher:
    """
    The Teacher agent.
    Learns to select 'Lesson Cards' that maximize student learning.
    """
    def __init__(self, card_loader: CardDataLoader, model_config: Dict[str, Any]):
        self.card_loader = card_loader
        self.logger = setup_logger(__name__)
        self.deck_gen = DeckGenerator()
        
        if HAS_TORCH:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.model = TeacherModel(input_dim=4).to(self.device)
            self.optimizer = optim.Adam(self.model.parameters(), lr=0.01)
        else:
            self.device = "cpu"
            self.model = TeacherModel(input_dim=4)
            self.optimizer = None
        
        self.last_benchmark_score = 0.0
        self.teacher_reward_history = []

    def select_archetypes(self, current_benchmark_score: float, self_play_winrate: float = 0.5, avg_steps: float = 1000, total_games: int = 0) -> Tuple[List[int], List[int]]:
        benchmark_improvement = current_benchmark_score - self.last_benchmark_score
        speed_factor = (1000 - avg_steps) / 1000
        
        # --- PHASE-BASED CURRICULUM (Card Learning Rate Schedule) ---
        # Adjust CMC and complexity based on total games played
        max_cmc = 10 # Default
        if total_games < 1000: max_cmc = 3
        elif total_games < 3000: max_cmc = 5
        
        if HAS_TORCH:
            state = torch.tensor([current_benchmark_score, benchmark_improvement, self_play_winrate, speed_factor], dtype=torch.float, device=self.device)
            with torch.no_grad():
                weights = self.model(state)
                w = weights.tolist()
        else:
            w = [random.random() for _ in range(7)]

        curiosity_factor = 0.5
        w = [ (1 - curiosity_factor) * wi + curiosity_factor * random.random() for wi in w ]

        conn = sqlite3.connect(self.card_loader.db_path)
        cursor = conn.cursor()
        
        def get_cards(query_part, count):
            # FOUNDATION PHASE: Disallow life-gain to ensure games finish
            forbidden = "(text NOT LIKE '%gain life%' AND text NOT LIKE '%life total becomes%' AND text NOT LIKE '%lifelink%')"
            
            cursor.execute(f"SELECT card_id, mana_cost FROM cards WHERE ({query_part}) AND {forbidden} ORDER BY RANDOM()")
            rows = cursor.fetchall()
            
            filtered_ids = []
            for card_id, mana_cost in rows:
                if len(filtered_ids) >= count: break
                
                # Calculate CMC in Python
                cmc = 0
                if mana_cost:
                    # Generic
                    gen_match = re.search(r'\{(\d+)\}', mana_cost)
                    if gen_match: cmc += int(gen_match.group(1))
                    # Colored
                    cmc += len(re.findall(r'\{[WUBRGC]\}', mana_cost))
                
                if cmc <= max_cmc:
                    filtered_ids.append(card_id)
            
            # If we don't have enough, just take what we found (or fallback)
            if not filtered_ids:
                cursor.execute(f"SELECT card_id FROM cards WHERE ({query_part}) AND {forbidden} ORDER BY RANDOM() LIMIT ?", (max(1, int(count)),))
                filtered_ids = [row[0] for row in cursor.fetchall()]
                
            return filtered_ids

        # Commander = 100 cards. We want ~60 non-lands per deck. Total 120.
        target_non_lands = 120 
        
        # Calculate weights excluding lands (index 2) to distribute spells/creatures
        spell_weights = sum(w[i] for i in [0, 1, 5, 6]) or 1.0
        
        def get_count(weight_idx):
            return max(1, int(target_non_lands * (w[weight_idx] / spell_weights)))

        c_count = get_count(0)
        s_count = get_count(1)
        a_count = get_count(5)
        e_count = get_count(6)

        creatures = get_cards("type LIKE '%Creature%'", c_count)
        spells = get_cards("(type LIKE '%Instant%' OR type LIKE '%Sorcery%')", s_count)
        artifacts = get_cards("type LIKE '%Artifact%'", a_count)
        enchantments = get_cards("type LIKE '%Enchantment%'", e_count)
        
        all_non_lands = (creatures + spells + artifacts + enchantments)
        random.shuffle(all_non_lands)
        
        mid = len(all_non_lands) // 2
        deck_a_seeds = all_non_lands[:mid]
        deck_b_seeds = all_non_lands[mid:]
        
        conn.close()
        self.last_benchmark_score = current_benchmark_score
        return deck_a_seeds, deck_b_seeds

    def train_teacher(self, current_solve_rate: float, current_winrate: float):
        """
        Updates the Teacher based on the Student's learning progress.
        Reward = (Progress Delta) - (Winrate Deviation Penalty).
        """
        if not HAS_TORCH or self.optimizer is None: return
        
        # Calculate Improvement (Learning Progress)
        improvement = current_solve_rate - self.last_benchmark_score
        
        # Winrate Penalty: Aim for 50% (0.5). 
        # Large deviations (bullying or being too easy) are punished.
        winrate_penalty = abs(current_winrate - 0.5) * 2.0 # Scale to 0-1 range
        
        # Final Reward: 70% Progress, 30% Stability
        reward = (0.7 * improvement) - (0.3 * winrate_penalty)
        
        self.teacher_reward_history.append(reward)
        
        # Update last score for next delta
        self.last_benchmark_score = current_solve_rate
        
        # Simple policy gradient update for the Teacher Model
        # (This is a simplified implementation - in a full setup, we'd use a proper optimizer step)
        self.logger.info(f" [Teacher Reward] Progress: {improvement:+.3f} | Winrate: {current_winrate:.2f} | Final: {reward:+.3f}")

    def generate_matchup(self, format_name: str, archetypes: Tuple[str, str], total_games: int = 0) -> List[List[int]]:
        """
        Generates a matchup. If archetypes is a tuple of lists, it builds from those sequences.
        Includes a 'Land Floor' curriculum that fades over 10,000 games.
        """
        # CURRICULUM: Fixed land floor starts at 38% (standard) and goes to 0% over 10k games.
        # This prevents mana-starved games early but lets Teacher learn optimal ratios later.
        initial_floor = 0.38
        curriculum_length = 10000
        land_floor = max(0.0, initial_floor * (1.0 - (total_games / curriculum_length)))
        
        if isinstance(archetypes[0], list):
            deck_a = self.deck_gen.build_from_sequence(archetypes[0], format_name, land_ratio=land_floor)
            deck_b = self.deck_gen.build_from_sequence(archetypes[1], format_name, land_ratio=land_floor)
            return [deck_a, deck_b]

        # For constructed archetypes, land_floor is not explicitly passed as they handle lands themselves
        # but we could apply it there too if needed.
        return self.deck_gen.build_constructed_deck(archetypes[0], format_name), \
               self.deck_gen.build_constructed_deck(archetypes[1], format_name)
