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
    class MockModule:
        def __init__(self, *args, **kwargs): pass
        def to(self, device): return self
        def eval(self): pass
        def train(self): pass
        def parameters(self): return []
    class MockNN:
        Module = MockModule
    nn = MockNN()

class CardEmbedder(nn.Module):
    def __init__(self, vocab_size, embedding_dim, component_dim):
        super().__init__()
        if HAS_TORCH:
            self.atomic_embedding = nn.Embedding(vocab_size, embedding_dim)
            self.component_mlp = nn.Sequential(nn.Linear(component_dim, embedding_dim), nn.ReLU(), nn.Linear(embedding_dim, embedding_dim))
            self.fusion = nn.Linear(embedding_dim * 2, embedding_dim)
    def forward(self, atomic_ids, component_features):
        atomic_vecs = self.atomic_embedding(atomic_ids)
        component_vecs = self.component_mlp(component_features)
        combined = torch.cat([atomic_vecs, component_vecs], dim=-1)
        return self.fusion(combined)

class BoardEncoder(nn.Module):
    def __init__(self, d_model, nhead, num_layers):
        super().__init__()
        if HAS_TORCH:
            encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, batch_first=True)
            self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
    def forward(self, x, mask=None): return self.transformer_encoder(x, src_key_padding_mask=mask)

class OpponentPredictor(nn.Module):
    def __init__(self, d_model, belief_dim):
        super().__init__()
        if HAS_TORCH:
            self.mlp = nn.Sequential(nn.Linear(d_model, d_model), nn.ReLU(), nn.Linear(d_model, belief_dim))
    def forward(self, z_board): return self.mlp(z_board.mean(dim=1))

class System2ReasoningHead(nn.Module):
    def __init__(self, d_model, nhead, belief_dim, vocab_size):
        super().__init__()
        if HAS_TORCH:
            self.cross_attn = nn.MultiheadAttention(embed_dim=d_model, nhead=nhead, batch_first=True)
            self.norm1 = nn.LayerNorm(d_model)
            self.norm2 = nn.LayerNorm(d_model)
            self.action_memory_embedder = nn.Embedding(vocab_size, d_model)
            self.action_fusion = nn.Linear(d_model * 2, d_model)
            self.refinement_mlp = nn.Sequential(nn.Linear(d_model + belief_dim, d_model), nn.ReLU(), nn.Linear(d_model, d_model))
    def forward(self, memory_tokens, z_board, b_t, prev_action_tokens=None):
        x = memory_tokens
        if prev_action_tokens is not None:
            action_vecs = self.action_memory_embedder(prev_action_tokens)
            action_context = action_vecs.mean(dim=1, keepdim=True).expand(-1, x.size(1), -1)
            x = self.action_fusion(torch.cat([x, action_context], dim=-1))
        attn_output, _ = self.cross_attn(x, z_board, z_board)
        x = self.norm1(x + attn_output)
        b_t_expanded = b_t.unsqueeze(1).expand(-1, x.size(1), -1)
        return self.norm2(x + self.refinement_mlp(torch.cat([x, b_t_expanded], dim=-1)))

class TeacherModel(nn.Module):
    def __init__(self, input_dim=10, hidden_dim=64):
        super().__init__()
        if HAS_TORCH:
            self.network = nn.Sequential(
                nn.Linear(input_dim, hidden_dim),
                nn.ReLU(),
                nn.Linear(hidden_dim, 7)
            )
    def forward(self, state):
        return torch.softmax(self.network(state), dim=-1)

class ActionPointerHead(nn.Module):
    def __init__(self, d_model, component_dim):
        super().__init__()
        if HAS_TORCH:
            self.intent_proj = nn.Linear(d_model, d_model)
            self.action_proj = nn.Linear(component_dim * 2 + 1, d_model)
            self.rethink_head = nn.Linear(d_model, 1)
            self.value_head = nn.Linear(d_model, 1)
    def forward(self, memory_tokens, legal_action_descriptors):
        intent = self.intent_proj(memory_tokens.mean(dim=1))
        projected_actions = self.action_proj(legal_action_descriptors)
        logits = torch.bmm(projected_actions, intent.unsqueeze(2)).squeeze(2)
        return logits, torch.sigmoid(self.rethink_head(intent)), self.value_head(intent)

class System2Transformer(nn.Module):
    def __init__(self, vocab_size, embedding_dim, component_dim, nhead, num_layers, belief_dim, max_actions):
        super().__init__()
        self.card_embedder = CardEmbedder(vocab_size, embedding_dim, component_dim)
        self.board_encoder = BoardEncoder(embedding_dim, nhead, num_layers)
        self.opponent_predictor = OpponentPredictor(embedding_dim, belief_dim)
        self.reasoning_head = System2ReasoningHead(embedding_dim, nhead, belief_dim, vocab_size)
        self.decoder = ActionPointerHead(embedding_dim, component_dim)
        
    def forward(self, atomic_ids, component_features, legal_action_descriptors, num_passes=1, threshold=0.5):
        if not HAS_TORCH:
            return {"action_logits": None, "action_idx": 0, "rethink_prob": 0.0, "value": torch.zeros(1), "state_memory": None, "passes_taken": 1}
        
        z_board = self.board_encoder(self.card_embedder(atomic_ids, component_features))
        b_t = self.opponent_predictor(z_board)
        memory_tokens = z_board
        
        actual_passes = 0
        for p in range(num_passes):
            actual_passes += 1
            memory_tokens = self.reasoning_head(memory_tokens, z_board, b_t)
            _, rethink_prob, _ = self.decoder(memory_tokens, legal_action_descriptors)
            if p > 0 and rethink_prob.item() < threshold:
                break
            
        logits, rethink_prob, value = self.decoder(memory_tokens, legal_action_descriptors)
        action_idx = torch.argmax(logits, dim=-1)
        
        return {
            "action_logits": logits, 
            "action_idx": action_idx, 
            "rethink_prob": rethink_prob, 
            "value": value, 
            "state_memory": (z_board, b_t, memory_tokens),
            "passes_taken": actual_passes
        }
