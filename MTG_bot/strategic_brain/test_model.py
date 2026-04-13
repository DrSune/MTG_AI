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
    # Mock legal descriptors: 5 actions, each with (component_dim * 2 + 1) features
    desc_dim = component_dim * 2 + 1
    legal_descriptors = torch.randn(batch_size, 5, desc_dim)
    
    # Forward pass 1 (initial state)
    output1 = model(atomic_ids, component_features, legal_descriptors, num_passes=3)
    
    print("Output shapes:")
    print(f"  Action Logits: {output1['action_logits'].shape}") 
    print(f"  Value: {output1['value'].shape}")              
    print(f"  RNN State (h): {output1['rnn_state'][0].shape}")
    
    assert output1['action_logits'].shape == (batch_size, 5) # 5 legal actions
    assert output1['value'].shape == (batch_size, 1)
    
    # Forward pass 2 (with recurrent state)
    output2 = model(atomic_ids, component_features, legal_descriptors, rnn_state=output1['rnn_state'], num_passes=3)
    
    print("\nRecurrent state handling successful!")
    print("Forward passes successful!")

if __name__ == "__main__":
    try:
        test_model_forward()
    except Exception as e:
        print(f"Test failed: {e}")
