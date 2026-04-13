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
            self.cross_attn = nn.MultiheadAttention(embed_dim=d_model, num_heads=nhead, batch_first=True)
            self.norm1 = nn.LayerNorm(d_model)
            self.norm2 = nn.LayerNorm(d_model)
            self.action_memory_embedder = nn.Embedding(vocab_size, d_model)
            self.action_fusion = nn.Linear(d_model * 2, d_model)
            self.refinement_mlp = nn.Sequential(nn.Linear(d_model + belief_dim, d_model), nn.ReLU(), nn.Linear(d_model, d_model))
    def forward(self, memory_tokens, z_board, b_t, prev_plan_embeddings=None):
        x = memory_tokens
        if prev_plan_embeddings is not None:
            # Plan context: average over plan steps
            plan_context = prev_plan_embeddings.mean(dim=1, keepdim=True).expand(-1, x.size(1), -1)
            x = self.action_fusion(torch.cat([x, plan_context], dim=-1))
            
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

class ActionSequenceDecoder(nn.Module):
    def __init__(self, d_model, nhead, max_seq_len=5):
        super().__init__()
        if HAS_TORCH:
            self.max_seq_len = max_seq_len
            # Tokens: 0:END, 1:PLAY_LAND, 2:CAST, 3:TAP, 4:ATTACK, 5:BLOCK, 6:PASS_PRIO, 7:PASS_TURN, 8:TARGET, 9:RETHINK
            self.action_type_embed = nn.Embedding(10, d_model) 
            self.pos_embed = nn.Parameter(torch.zeros(1, max_seq_len, d_model))
            
            # Autoregressive Transformer Decoder
            decoder_layer = nn.TransformerDecoderLayer(d_model=d_model, nhead=nhead, batch_first=True)
            self.transformer_decoder = nn.TransformerDecoder(decoder_layer, num_layers=4)
            
            # Heads for each part of the action tuple
            self.type_head = nn.Linear(d_model, 10)
            self.source_head = nn.Linear(d_model, d_model)
            self.target_head = nn.Linear(d_model, d_model)

    def forward(self, memory_tokens, board_tokens, action_menu):
        # memory_tokens: (batch, rethink_steps, d_model)
        # board_tokens: (batch, num_entities, d_model)
        # action_menu: (batch, num_legal_actions, d_model)
        batch_size = memory_tokens.size(0)
        
        # Grounding: The planning memory is a combination of Board + Available Actions
        # This ensures the model "sees" its options before planning the sequence.
        planning_memory = torch.cat([board_tokens, action_menu], dim=1)
        
        # Start token: Use global summary of memory
        tgt = memory_tokens.mean(dim=1, keepdim=True)
        
        generated_sequences = []
        plan_embeddings = []
        
        for i in range(self.max_seq_len):
            tgt_with_pos = tgt + self.pos_embed[:, :tgt.size(1), :]
            # Cross-attend over the board AND the actions
            out = self.transformer_decoder(tgt_with_pos, planning_memory)
            last_out = out[:, -1, :]
            plan_embeddings.append(last_out.unsqueeze(1))
            
            type_logits = self.type_head(last_out)
            source_query = self.source_head(last_out)
            target_query = self.target_head(last_out)
            
            # Pointing: source/target can point to entities in planning_memory (Board or Action targets)
            source_logits = torch.bmm(planning_memory, source_query.unsqueeze(2)).squeeze(2)
            target_logits = torch.bmm(planning_memory, target_query.unsqueeze(2)).squeeze(2)
            
            generated_sequences.append({
                "type_logits": type_logits,
                "source_logits": source_logits,
                "target_logits": target_logits
            })
            
            next_type = torch.argmax(type_logits, dim=-1)
            next_embed = self.action_type_embed(next_type).unsqueeze(1)
            tgt = torch.cat([tgt, next_embed], dim=1)
            
            if next_type.item() == 0 or next_type.item() == 7:
                pass
            
        full_plan_embedding = torch.cat(plan_embeddings, dim=1)
        return generated_sequences, full_plan_embedding

class ActionPointerHead(nn.Module):
    def __init__(self, d_model, component_dim, nhead):
        super().__init__()
        if HAS_TORCH:
            self.intent_proj = nn.Linear(d_model, d_model)
            self.action_proj = nn.Linear(component_dim * 2 + 1, d_model)
            self.value_head = nn.Linear(d_model, 1)
            self.sequence_decoder = ActionSequenceDecoder(d_model, nhead)
            self.plan_query_proj = nn.Linear(d_model, d_model)

    def forward(self, memory_tokens, board_tokens, legal_action_descriptors):
        # 1. Global state summary
        z_global = memory_tokens.mean(dim=1)
        
        # 2. Project actions to Intelligence Space FIRST
        projected_actions = self.action_proj(legal_action_descriptors) # (batch, num_legal, d_model)
        
        # 3. Action-Aware Sequence Generation (The Plan)
        # The planner now receives the available actions as part of its "memory"
        plan_sequence, plan_embedding = self.sequence_decoder(memory_tokens, board_tokens, projected_actions)
        
        # 4. Grounded Matching (Gatekeeper)
        plan_step_queries = self.plan_query_proj(plan_embedding)
        first_step_query = plan_step_queries[:, 0, :]
        logits = torch.bmm(projected_actions, first_step_query.unsqueeze(2)).squeeze(2)
        
        # Rethink Signal
        rethink_signal = plan_sequence[0]["type_logits"][:, 9] 
        
        return {
            "logits": logits,
            "rethink_prob": torch.sigmoid(rethink_signal),
            "value": self.value_head(z_global),
            "plan_sequence": plan_sequence,
            "plan_embedding": plan_embedding,
            "plan_step_queries": plan_step_queries
        }

class System2Transformer(nn.Module):
    def __init__(self, vocab_size, embedding_dim, component_dim, nhead, num_layers, belief_dim, max_actions):
        super().__init__()
        self.card_embedder = CardEmbedder(vocab_size, embedding_dim, component_dim)
        self.board_encoder = BoardEncoder(embedding_dim, nhead, num_layers)
        self.opponent_predictor = OpponentPredictor(embedding_dim, belief_dim)
        self.reasoning_head = System2ReasoningHead(embedding_dim, nhead, belief_dim, vocab_size)
        self.decoder = ActionPointerHead(embedding_dim, component_dim, nhead)
        
        # --- RECURRENCE (Full BPTT Support) ---
        if HAS_TORCH:
            self.rnn = nn.LSTMCell(embedding_dim, embedding_dim)
            # Projection to merge RNN state back into board tokens if needed
            self.temporal_fusion = nn.Linear(embedding_dim * 2, embedding_dim)

    def forward(self, atomic_ids, component_features, legal_action_descriptors, rnn_state=None, num_passes=8, threshold=0.5):
        if not HAS_TORCH:
            return {"action_logits": None, "action_idx": 0, "rethink_prob": 0.0, "value": torch.zeros(1), "state_memory": None, "passes_taken": 1, "rnn_state": None}
        
        board_tokens = self.card_embedder(atomic_ids, component_features)
        z_board = self.board_encoder(board_tokens)
        
        # 1. Temporal Aggregation (RNN)
        # We use the mean of board tokens as the "summary" to update our temporal hidden state
        z_global = z_board.mean(dim=1)
        
        if rnn_state is None:
            batch_size = z_global.size(0)
            h = torch.zeros(batch_size, z_global.size(1), device=z_global.device)
            c = torch.zeros(batch_size, z_global.size(1), device=z_global.device)
            rnn_state = (h, c)
            
        h_new, c_new = self.rnn(z_global, rnn_state)
        new_rnn_state = (h_new, c_new)
        
        # 2. Information Fusion: Inject temporal context into all board tokens
        # Allows the reasoning head to know "where we are" in the game's history
        h_expanded = h_new.unsqueeze(1).expand(-1, z_board.size(1), -1)
        z_board_temporal = self.temporal_fusion(torch.cat([z_board, h_expanded], dim=-1))
        
        b_t = self.opponent_predictor(z_board_temporal)
        
        memory_tokens = z_board_temporal
        prev_plan_emb = None
        actual_passes = 0
        
        for p in range(num_passes):
            actual_passes += 1
            # Reasoning pass: sees board, opponent belief, and PREVIOUS plan
            memory_tokens = self.reasoning_head(memory_tokens, z_board_temporal, b_t, prev_plan_embeddings=prev_plan_emb)
            
            res = self.decoder(memory_tokens, z_board_temporal, legal_action_descriptors)
            prev_plan_emb = res["plan_embedding"]
            
            # --- AUTONOMOUS RETHINK TRIGGER ---
            # Model rethinks ONLY if it predicted RETHINK (9) in the plan
            # We check the top prediction of the first step of the plan
            predicted_first_type = torch.argmax(res["plan_sequence"][0]["type_logits"], dim=-1)
            is_rethink_requested = (predicted_first_type == 9).any()
            
            if not is_rethink_requested and p >= 0: # Stop if rethink not requested
                break
        
        logits = res["logits"]
        action_idx = torch.argmax(logits, dim=-1)
        
        return {
            "action_logits": logits, 
            "action_idx": action_idx, 
            "rethink_prob": res["rethink_prob"], 
            "value": res["value"], 
            "plan_sequence": res["plan_sequence"],
            "plan_step_queries": res["plan_step_queries"],
            "state_memory": (z_board_temporal, b_t, memory_tokens),
            "passes_taken": actual_passes,
            "rnn_state": new_rnn_state
        }
