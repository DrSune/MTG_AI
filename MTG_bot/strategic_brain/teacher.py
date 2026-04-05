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

    def select_archetypes(self, current_benchmark_score: float, self_play_winrate: float = 0.5, avg_steps: float = 1000) -> Tuple[List[int], List[int]]:
        benchmark_improvement = current_benchmark_score - self.last_benchmark_score
        speed_factor = (1000 - avg_steps) / 1000
        
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
            cursor.execute(f"SELECT card_id FROM cards WHERE ({query_part}) AND {forbidden} ORDER BY RANDOM() LIMIT ?", (max(1, int(count)),))
            return [row[0] for row in cursor.fetchall()]

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

    def train_teacher(self, student_improvement: float):
        if not HAS_TORCH or self.optimizer is None: return
        self.teacher_reward_history.append(student_improvement)

    def generate_matchup(self, format_name: str, archetypes: Tuple[str, str]) -> List[List[int]]:
        if isinstance(archetypes[0], list):
            deck_a = self.deck_gen.build_from_sequence(archetypes[0], format_name)
            deck_b = self.deck_gen.build_from_sequence(archetypes[1], format_name)
            return [deck_a, deck_b]

        return self.deck_gen.build_constructed_deck(archetypes[0], format_name), \
               self.deck_gen.build_constructed_deck(archetypes[1], format_name)
