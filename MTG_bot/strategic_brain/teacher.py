import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Dict, Any, Optional
from MTG_bot.rule_engine.card_data_loader import CardDataLoader
from MTG_bot.utils.logger import setup_logger

class DeckMatchupAnalyzer(nn.Module):
    """
    A Transformer-based model that evaluates the synergy of a deck and its 
    performance against an opponent's deck.
    
    It serves as the 'Brain' for the Teacher, allowing it to evaluate 
    card combinations holistically rather than just as a sequence.
    """
    def __init__(self, embedding_dim, nhead, num_layers, d_model):
        super().__init__()
        self.d_model = d_model
        # Processes the 'Current Deck A' tokens
        encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, batch_first=True)
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # Outputs a 'Query Vector' for the next card selection
        self.query_head = nn.Linear(d_model, embedding_dim)
        
        # Evaluation head to predict matchup outcome (Win Rate / Learning Gain)
        self.eval_head = nn.Sequential(
            nn.Linear(d_model, d_model),
            nn.ReLU(),
            nn.Linear(d_model, 1)
        )

    def forward(self, deck_embeddings, opponent_deck_embeddings=None, student_weakness_context=None):
        """
        Args:
            deck_embeddings: (batch, num_cards, d_model)
            opponent_deck_embeddings: (batch, num_opponent_cards, d_model)
            student_weakness_context: (batch, context_dim)
        """
        # 1. Self-Attention over the current deck to understand synergy
        combined_context = deck_embeddings
        if opponent_deck_embeddings is not None:
            # In a full implementation, we would use cross-attention or concat 
            # to see how Deck A interacts with Deck B
            combined_context = torch.cat([deck_embeddings, opponent_deck_embeddings], dim=1)
            
        z = self.transformer_encoder(combined_context)
        
        # 2. Pool the state to get a global 'Matchup Representation'
        z_pooled = z.mean(dim=1)
        
        # 3. Generate a Query Vector for the next card search
        query_vector = self.query_head(z_pooled)
        
        # 4. Predict the 'Matchup Quality'
        quality_score = torch.sigmoid(self.eval_head(z_pooled))
        
        return query_vector, quality_score

class Teacher:
    """
    The Teacher RL agent. Dual-purpose:
    1. Curriculum Designer: Challenges the Student AI.
    2. Deck Optimizer: Assists human players in finding synergistic cards.
    """
    def __init__(self, card_loader: CardDataLoader, model_config: Dict[str, Any]):
        self.card_loader = card_loader
        self.logger = setup_logger(__name__)
        
        self.embedding_dim = model_config.get("embedding_dim", 128)
        self.d_model = model_config.get("d_model", 256)
        
        self.analyzer = DeckMatchupAnalyzer(
            embedding_dim=self.embedding_dim,
            nhead=model_config.get("nhead", 8),
            num_layers=model_config.get("num_layers", 4),
            d_model=self.d_model
        )
        
        # Placeholder for the global card embedding pool (TurboQuant target)
        # In production, this would be a FAISS index or similar vector DB
        self.card_pool_embeddings: Dict[int, torch.Tensor] = {} 
        
        self.student_weakness_profile = {} # Detailed tracking of Student misplays
        self.min_deck_size = 40

    def select_next_card(self, current_deck: List[int], opponent_deck: Optional[List[int]] = None) -> int:
        """
        Sequentially selects the best card to add to the deck.
        Uses the Transformer to generate a 'Query' and searches the card pool.
        """
        if not current_deck:
            # Start with a random 'Seed' card or an archetype staple
            return random.choice(self.card_loader.get_all_card_ids())

        # 1. Convert current IDs to embeddings
        deck_vecs = torch.stack([self.card_pool_embeddings.get(cid, torch.zeros(self.d_model)) for cid in current_deck])
        deck_vecs = deck_vecs.unsqueeze(0) # Add batch dim

        # 2. Get the Query Vector from the Transformer
        query_vector, _ = self.analyzer(deck_vecs)

        # 3. Perform Vector Search (Cosine Similarity)
        # This is the 'Search' part: find the card in the pool most similar to the query
        best_card_id = self._vector_search(query_vector)
        
        return best_card_id

    def _vector_search(self, query_vector: torch.Tensor) -> int:
        """
        Searches the card embedding database for the best match.
        For now, this is a conceptual placeholder.
        """
        # Concept:
        # scores = {}
        # for card_id, emb in self.card_pool_embeddings.items():
        #     scores[card_id] = F.cosine_similarity(query_vector, emb)
        # return max(scores, key=scores.get)
        return random.choice(self.card_loader.get_all_card_ids())

    def generate_optimized_deck(self, archetype_staples: List[int], opponent_deck: Optional[List[int]] = None) -> List[int]:
        """
        Builds a full deck sequentially. 
        Can be used to challenge a Student or optimize a Human Player's deck.
        """
        deck = list(archetype_staples)
        while len(deck) < self.min_deck_size:
            next_card = self.select_next_card(deck, opponent_deck)
            deck.append(next_card)
        return deck

    def evaluate_matchup(self, deck_a: List[int], deck_b: List[int]) -> float:
        """
        Uses full information to predict the 'Fairness' and 'Learning Potential'
        of a matchup before starting the simulation.
        """
        # Convert to embeddings and run through the analyzer's eval_head
        # Returns a score between 0 and 1
        return 0.5
