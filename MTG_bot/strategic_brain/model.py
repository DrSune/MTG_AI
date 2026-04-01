import torch
import torch.nn as nn
import torch.nn.functional as F

class CardEmbedder(nn.Module):
    """
    Encodes cards into dense vectors using atomic IDs and component features.
    """
    def __init__(self, vocab_size, embedding_dim, component_dim):
        super().__init__()
        self.atomic_embedding = nn.Embedding(vocab_size, embedding_dim)
        # Component features: power, toughness, mana cost, keywords, etc.
        self.component_mlp = nn.Sequential(
            nn.Linear(component_dim, embedding_dim),
            nn.ReLU(),
            nn.Linear(embedding_dim, embedding_dim)
        )
        self.fusion = nn.Linear(embedding_dim * 2, embedding_dim)

    def forward(self, atomic_ids, component_features):
        atomic_vecs = self.atomic_embedding(atomic_ids)
        component_vecs = self.component_mlp(component_features)
        combined = torch.cat([atomic_vecs, component_vecs], dim=-1)
        return self.fusion(combined)

class BoardEncoder(nn.Module):
    """
    Transformer-based encoder for the visible board state.
    Produces the 'Frozen Board' representation (Z_board).
    """
    def __init__(self, d_model, nhead, num_layers):
        super().__init__()
        encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, batch_first=True)
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)

    def forward(self, x, mask=None):
        return self.transformer_encoder(x, src_key_padding_mask=mask)

class OpponentPredictor(nn.Module):
    """
    Predicts the 'Belief Vector' (b_t) representing hidden opponent state.
    """
    def __init__(self, d_model, belief_dim):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(d_model, d_model),
            nn.ReLU(),
            nn.Linear(d_model, belief_dim)
        )

    def forward(self, z_board):
        # Pool the board representation (e.g., mean pooling over entity tokens)
        z_pooled = z_board.mean(dim=1)
        return self.mlp(z_pooled)

class System2ReasoningHead(nn.Module):
    """
    Iterative reasoning head that uses cross-attention over the frozen board
    and analyzes its own previous action proposals.
    """
    def __init__(self, d_model, nhead, belief_dim, vocab_size):
        super().__init__()
        self.cross_attn = nn.MultiheadAttention(embed_dim=d_model, nhead=nhead, batch_first=True)
        self.norm1 = nn.LayerNorm(d_model)
        self.norm2 = nn.LayerNorm(d_model)
        
        # New: Embeddings for previous actions so the model can critique them
        self.action_memory_embedder = nn.Embedding(vocab_size, d_model)
        self.action_fusion = nn.Linear(d_model * 2, d_model)

        self.refinement_mlp = nn.Sequential(
            nn.Linear(d_model + belief_dim, d_model),
            nn.ReLU(),
            nn.Linear(d_model, d_model)
        )

    def forward(self, memory_tokens, z_board, b_t, prev_action_tokens=None):
        # 1. Action Critique: Incorporate previous thoughts if they exist
        x = memory_tokens
        if prev_action_tokens is not None:
            # Embed the actions the model just thought of
            action_vecs = self.action_memory_embedder(prev_action_tokens)
            # Pool actions to match memory_tokens sequence length or use attention
            # For simplicity, we fusion the mean action-vector into each memory token
            action_context = action_vecs.mean(dim=1, keepdim=True).expand(-1, x.size(1), -1)
            x = self.action_fusion(torch.cat([x, action_context], dim=-1))

        # 2. Cross-attention: Memory tokens 'look back' at the frozen board
        attn_output, _ = self.cross_attn(x, z_board, z_board)
        x = self.norm1(x + attn_output)
        
        # 3. Condition on the belief vector (b_t)
        b_t_expanded = b_t.unsqueeze(1).expand(-1, x.size(1), -1)
        combined = torch.cat([x, b_t_expanded], dim=-1)
        
        refined = self.refinement_mlp(combined)
        return self.norm2(x + refined)

class ActionSequenceDecoder(nn.Module):
    """
    Generates a sequence of K action tokens and metadata autoregressively.
    """
    def __init__(self, d_model, vocab_size, max_seq_len):
        super().__init__()
        self.max_seq_len = max_seq_len
        self.vocab_size = vocab_size
        self.action_embedding = nn.Embedding(vocab_size, d_model)
        self.decoder_rnn = nn.GRUCell(d_model, d_model)
        self.output_head = nn.Linear(d_model, vocab_size)
        self.rethink_head = nn.Linear(d_model, 1)
        self.value_head = nn.Linear(d_model, 1)

    def forward(self, z_refined):
        batch_size = z_refined.size(0)
        # Pool the refined state to get an initial hidden state for the RNN
        # Z_refined is (batch, num_entities, d_model)
        h_t = z_refined.mean(dim=1) 
        
        # Start token (assuming token 0 is <SOS>)
        current_token = torch.zeros(batch_size, dtype=torch.long, device=z_refined.device)
        
        all_logits = []
        all_tokens = []
        
        for _ in range(self.max_seq_len):
            x_t = self.action_embedding(current_token)
            h_t = self.decoder_rnn(x_t, h_t)
            
            logits = self.output_head(h_t)
            token = torch.argmax(logits, dim=-1)
            
            all_logits.append(logits.unsqueeze(1))
            all_tokens.append(token.unsqueeze(1))
            
            current_token = token
            # In a real training scenario, we would use teacher forcing here.
            
        logits_seq = torch.cat(all_logits, dim=1)
        token_seq = torch.cat(all_tokens, dim=1)
        
        # Use the final hidden state to predict rethink probability and state value
        rethink_prob = torch.sigmoid(self.rethink_head(h_t))
        value = self.value_head(h_t)
        
        return logits_seq, token_seq, rethink_prob, value

class System2Transformer(nn.Module):
    """
    The full System 2 Recursive Transformer Model.
    """
    def __init__(self, vocab_size, embedding_dim, component_dim, nhead, num_layers, belief_dim, max_actions):
        super().__init__()
        self.card_embedder = CardEmbedder(vocab_size, embedding_dim, component_dim)
        self.board_encoder = BoardEncoder(embedding_dim, nhead, num_layers)
        self.opponent_predictor = OpponentPredictor(embedding_dim, belief_dim)
        self.reasoning_head = System2ReasoningHead(embedding_dim, nhead, belief_dim, vocab_size)
        self.decoder = ActionSequenceDecoder(embedding_dim, vocab_size, max_actions)

    def forward(self, atomic_ids, component_features, num_passes=1, prev_memory=None, prev_actions=None):
        # 1. Facts: Frozen Board Encoding (Only runs if no previous memory)
        if prev_memory is None:
            card_embeddings = self.card_embedder(atomic_ids, component_features)
            z_board = self.board_encoder(card_embeddings)
            b_t = self.opponent_predictor(z_board)
            memory_tokens = z_board 
        else:
            # We reuse the facts from the previous pass
            z_board, b_t, memory_tokens = prev_memory

        # 2. Reasoning: The iterative "Thought" pass
        for _ in range(num_passes):
            memory_tokens = self.reasoning_head(memory_tokens, z_board, b_t, prev_actions)
        
        # 3. Prediction: Propose a sequence and check if we should rethink
        logits, action_tokens, rethink_prob, value = self.decoder(memory_tokens)
        
        return {
            "action_logits": logits,
            "action_tokens": action_tokens, # These can be fed back into the next forward call
            "rethink_prob": rethink_prob,
            "value": value,
            "state_memory": (z_board, b_t, memory_tokens) # The "Latent Memory"
        }
