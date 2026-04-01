import torch
from MTG_bot.strategic_brain.model import System2Transformer

def test_model_forward():
    print("Testing System2Transformer forward pass...")
    
    # Model parameters
    vocab_size = 1000
    embedding_dim = 128
    component_dim = 10
    nhead = 8
    num_layers = 2
    belief_dim = 64
    max_actions = 10
    
    # Create model
    model = System2Transformer(
        vocab_size, embedding_dim, component_dim, 
        nhead, num_layers, belief_dim, max_actions
    )
    
    # Mock data
    batch_size = 1
    num_entities = 20
    atomic_ids = torch.randint(0, vocab_size, (batch_size, num_entities))
    component_features = torch.randn(batch_size, num_entities, component_dim)
    
    # Forward pass
    output = model(atomic_ids, component_features, num_passes=3)
    
    print("Output shapes:")
    print(f"  Action Logits: {output['action_logits'].shape}") # (B, K, Vocab)
    print(f"  Rethink Prob: {output['rethink_prob'].shape}")   # (B, 1)
    print(f"  Value: {output['value'].shape}")               # (B, 1)
    print(f"  b_t (Belief): {output['b_t'].shape}")           # (B, BeliefDim)
    
    assert output['action_logits'].shape == (batch_size, 10, vocab_size)
    assert output['rethink_prob'].shape == (batch_size, 1)
    assert output['value'].shape == (batch_size, 1)
    
    print("\nForward pass successful!")

if __name__ == "__main__":
    try:
        test_model_forward()
    except Exception as e:
        print(f"Test failed: {e}")
