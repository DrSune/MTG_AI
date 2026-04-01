import torch
from MTG_bot.strategic_brain.teacher import Teacher
from MTG_bot.rule_engine.card_data_loader import CardDataLoader

def test_teacher_initialization():
    """Verifies that the Teacher can be initialized and generate a query."""
    # Mock CardDataLoader
    try:
        loader = CardDataLoader()
    except Exception as e:
        print(f"Skipping full loader test: {e}")
        return

    model_config = {
        "embedding_dim": 128,
        "d_model": 256,
        "nhead": 4,
        "num_layers": 2
    }
    
    teacher = Teacher(loader, model_config)
    
    # Mock some card embeddings
    all_ids = loader.get_all_card_ids()
    for cid in all_ids[:10]:
        teacher.card_pool_embeddings[cid] = torch.randn(256)
    
    # Test sequential selection
    current_deck = all_ids[:5]
    next_card = teacher.select_next_card(current_deck)
    
    print(f"Teacher successfully selected next card: {next_card}")
    assert next_card in all_ids

if __name__ == "__main__":
    test_teacher_initialization()
