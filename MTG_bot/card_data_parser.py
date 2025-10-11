import sqlite3
import os
import re

# Define paths
DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'mtg_cards.db')
VOCAB_PATH = os.path.join(os.path.dirname(__file__), 'rule_engine', 'vocabulary.py')
CARD_DATABASE_PATH = os.path.join(os.path.dirname(__file__), 'rule_engine', 'card_database.py')

def load_existing_vocabulary():
    """Loads existing vocabulary IDs from vocabulary.py and returns a dict and max ID."""
    vocab_map = {}
    reverse_vocab_map = {}
    max_id = 0
    with open(VOCAB_PATH, 'r') as f:
        for line in f:
            match = re.match(r'(ID_[A-Z_]+)\s*=\s*(\d+)', line)
            if match:
                name, _id = match.groups()
                _id = int(_id)
                vocab_map[name] = _id
                reverse_vocab_map[_id] = name
                if _id > max_id:
                    max_id = _id
    return vocab_map, reverse_vocab_map, max_id

def parse_mana_cost(mana_cost_str, vocab_map):
    """Parses a mana cost string (e.g., '{1}{G}') into a dictionary using vocab IDs."""
    cost = {}
    if not mana_cost_str:
        return cost

    symbols = re.findall(r'\{([0-9WUBRGXCS]+)\}', mana_cost_str)

    for symbol in symbols:
        if symbol.isdigit():
            cost['generic'] = cost.get('generic', 0) + int(symbol)
        elif symbol == 'W': cost[vocab_map['ID_MANA_WHITE']] = cost.get(vocab_map['ID_MANA_WHITE'], 0) + 1
        elif symbol == 'U': cost[vocab_map['ID_MANA_BLUE']] = cost.get(vocab_map['ID_MANA_BLUE'], 0) + 1
        elif symbol == 'B': cost[vocab_map['ID_MANA_BLACK']] = cost.get(vocab_map['ID_MANA_BLACK'], 0) + 1
        elif symbol == 'R': cost[vocab_map['ID_MANA_RED']] = cost.get(vocab_map['ID_MANA_RED'], 0) + 1
        elif symbol == 'G': cost[vocab_map['ID_MANA_GREEN']] = cost.get(vocab_map['ID_MANA_GREEN'], 0) + 1
        elif symbol == 'C': cost[vocab_map['ID_MANA_COLORLESS']] = cost.get(vocab_map['ID_MANA_COLORLESS'], 0) + 1
        # Handle hybrid mana, X, etc. later if needed

    return cost

def generate_files():
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        vocab_map, reverse_vocab_map, current_max_vocab_id = load_existing_vocabulary()
        next_id = current_max_vocab_id + 1

        # --- Step 1: Update Vocabulary with Card Names ---
        cursor.execute("SELECT DISTINCT name FROM cards;")
        card_names_from_db = [row[0] for row in cursor.fetchall()]

        for card_name in card_names_from_db:
            vocab_name = f"ID_CARD_{card_name.replace(' ', '_').replace('-', '_').replace("\\", '').replace("'", '').replace(',', '').upper()}"
            if vocab_name not in vocab_map:
                vocab_map[vocab_name] = next_id
                reverse_vocab_map[next_id] = vocab_name
                next_id += 1
        
        # --- Write updated vocabulary.py ---
        with open(VOCAB_PATH, 'w') as f:
            f.write("""
            
This file establishes the core vocabulary for the MTG rule engine.

It uses unique integer constants to represent every possible concept in the game,
including cards, zones, abilities, and relationships. This provides a highly
efficient and unambiguous language for all other components of the system to use.
"""
)
            # Sort for consistent output
            sorted_vocab = sorted(vocab_map.items(), key=lambda item: item[1])
            for name, _id in sorted_vocab:
                f.write(f"{name} = {_id}\n")
        print(f"Updated {VOCAB_PATH} with {len(card_names_from_db)} card IDs.")

        # Reload vocabulary to ensure new card IDs are available for card_database generation
        vocab_map, reverse_vocab_map, _ = load_existing_vocabulary()

        # --- Step 2: Generate Card Database ---
        card_costs = {}
        creature_stats = {}
        card_abilities = {}

        cursor.execute("SELECT name, mana_cost, type, power, toughness FROM cards;")
        for card_name, mana_cost_str, card_type, power_str, toughness_str in cursor.fetchall():
            card_vocab_id = vocab_map[f"ID_CARD_{card_name.replace(' ', '_').replace('-', '_').replace("\\", '').replace("'", '').replace(',', '').upper()}"]

            # Parse mana cost
            parsed_cost = parse_mana_cost(mana_cost_str, vocab_map)
            if parsed_cost:
                card_costs[card_vocab_id] = parsed_cost

            # Parse creature stats
            if 'Creature' in card_type and power_str and toughness_str:
                try:
                    power = int(power_str)
                    toughness = int(toughness_str)
                    creature_stats[card_vocab_id] = {'power': power, 'toughness': toughness}
                except ValueError:
                    # Handle cases like */* creatures later
                    pass

            # Get abilities from card_components table
            cursor.execute("SELECT component_id FROM card_components WHERE card_name = ?;", (card_name,))
            abilities = [row[0] for row in cursor.fetchall()]
            if abilities:
                card_abilities[card_vocab_id] = abilities

        # --- Write card_database.py ---
        with open(CARD_DATABASE_PATH, 'w') as f:
            f.write('''\
This file contains data definitions for cards, generated by card_data_parser.py.\
''')
            f.write("from . import vocabulary as vocab\n\n")
            f.write(f"CARD_COSTS = {card_costs}\n\n")
            f.write(f"CREATURE_STATS = {creature_stats}\n\n")
            f.write(f"CARD_ABILITIES = {card_abilities}\n\n")
            f.write("MANA_ABILITY_MAP = {{\n")
            # Manually add basic land mana abilities for now, as they are not in card_components
            f.write(f"    vocab.ID_ABILITY_TAP_ADD_GREEN: vocab.ID_MANA_GREEN,\n")
            f.write(f"    vocab.ID_ABILITY_TAP_ADD_BLUE: vocab.ID_MANA_BLUE,\n")
            f.write(f"    vocab.ID_ABILITY_TAP_ADD_BLACK: vocab.ID_MANA_BLACK,\n")
            f.write(f"    vocab.ID_ABILITY_TAP_ADD_RED: vocab.ID_MANA_RED,\n")
            f.write(f"    vocab.ID_ABILITY_TAP_ADD_WHITE: vocab.ID_MANA_WHITE,\n")
            f.write("}}\n")
        print(f"Generated {CARD_DATABASE_PATH} with {len(card_costs)} card entries.")

    except sqlite3.Error as e:
        print(f"SQLite error: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    generate_files()