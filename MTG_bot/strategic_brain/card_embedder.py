"""
This module is responsible for converting card data into numerical vectors (embeddings).
These embeddings are the foundation of the Strategic Brain, allowing it to understand
card similarity and synergy.
"""

import json
from typing import Dict
from .. import config

# It's recommended to use a pre-trained transformer model for this task.
# from sentence_transformers import SentenceTransformer

def load_card_database() -> Dict:
    """Loads the MTGJSON database file."""
    with open(config.MTGJSON_PATH, 'r', encoding='utf-8') as f:
        all_printings = json.load(f)
    # It's often better to work with a simplified, card-centric database.
    # This is a placeholder for that processing step.
    print("MTGJSON database loaded conceptually.")
    return all_printings

def create_card_embeddings(cards: Dict) -> Dict[str, list]:
    """
    Generates semantic vector embeddings for each card.

    The embedding should capture the card's function, type, and abilities.
    A good input for the model would be a string like:
    "[TYPE] Creature - Goblin Warrior. [MANA] 1R. [TEXT] Haste. Whenever this attacks..."

    Args:
        cards: A dictionary of card data from the database.

    Returns:
        A dictionary mapping card names to their vector embeddings.
    """
    print("Generating card embeddings...")
    # model = SentenceTransformer('all-MiniLM-L6-v2')
    embeddings = {}
    # for card_name, card_data in cards.items():
    #     text_to_embed = f"[TYPE] {card_data['type_line']}. [MANA] {card_data['mana_cost']}. [TEXT] {card_data['text']}"
    #     embedding = model.encode(text_to_embed)
    #     embeddings[card_name] = embedding
    print("Card embeddings generated conceptually.")
    return embeddings
