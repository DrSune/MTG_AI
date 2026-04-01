import requests
import json
import argparse
import os
import sqlite3
import re
import sys

# Add the project root to sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

def download_set_data(set_code, output_dir="."):
    """
    Downloads a set's data from MTGJSON.
    """
    url = f"https://mtgjson.com/api/v5/{set_code}.json"
    output_path = os.path.join(os.path.dirname(__file__), '..', 'data')
    file_path = os.path.join(output_path, f"{set_code}.json")

    print(f"Downloading data for set '{set_code}' from {url}...")
    try:
        response = requests.get(url)
        response.raise_for_status()
        os.makedirs(output_path, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(response.json(), f)
        print(f"Successfully downloaded and saved to {file_path}")
        return file_path
    except requests.exceptions.RequestException as e:
        print(f"Error downloading file: {e}")
        return None

def setup_database(db_path):
    """
    Creates the SQLite database and tables if they don't exist.
    DOES NOT drop users/decks/game_vocabulary to preserve manual setup.
    """
    print(f"Ensuring database tables at {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # We only drop and recreate 'cards' and 'deck_cards' for the parser refresh
    cursor.execute('''DROP TABLE IF EXISTS deck_cards''')
    cursor.execute('''DROP TABLE IF EXISTS cards''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        elo INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cards (
        card_id INTEGER PRIMARY KEY AUTOINCREMENT,
        set_code TEXT NOT NULL,
        card_number TEXT NOT NULL,
        name TEXT,
        mana_cost TEXT,
        type TEXT,
        text TEXT,
        power TEXT,
        toughness TEXT,
        supertypes TEXT,
        effects_json TEXT,
        UNIQUE (set_code, card_number)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS decks (
        deck_id INTEGER PRIMARY KEY AUTOINCREMENT,
        deck_name TEXT NOT NULL,
        owner_id INTEGER NOT NULL,
        format TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (owner_id) REFERENCES users(user_id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS deck_cards (
        deck_card_id INTEGER PRIMARY KEY AUTOINCREMENT,
        deck_id INTEGER NOT NULL,
        card_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        FOREIGN KEY (deck_id) REFERENCES decks(deck_id),
        FOREIGN KEY (card_id) REFERENCES cards(card_id),
        UNIQUE (deck_id, card_id)
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS game_vocabulary (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        value TEXT,
        mode TEXT NOT NULL DEFAULT 'General'
    )
    ''')

    conn.commit()
    conn.close()

def insert_cards_to_db(db_path, parsed_cards):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for card_key, data in parsed_cards.items():
        set_code, card_number = card_key
        effects = parse_effect_structures(data['text'])
        for keyword in data.get('keywords', []):
            effects.append({'ability_type': 'keyword', 'keyword': keyword.lower()})

        cursor.execute('''
        INSERT OR REPLACE INTO cards (set_code, card_number, name, mana_cost, type, text, power, toughness, supertypes, effects_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            set_code,
            card_number,
            data['name'],
            data['mana_cost'],
            data['type'],
            data['text'],
            data['power'],
            data['toughness'],
            json.dumps(data['supertypes']),
            json.dumps(effects)
        ))
    conn.commit()
    conn.close()
    print(f"Successfully inserted or replaced {len(parsed_cards)} cards in the database.")

def parse_mtgjson(mtgjson_data):
    """
    Parses all cards from the MTGJSON data.
    """
    parsed_cards = {}
    all_cards = mtgjson_data.get('data', {}).get('cards', [])
    set_code = mtgjson_data.get('data', {}).get('code')

    for card in all_cards:
        # Use (set_code, card_number) as the key for parsed_cards
        card_key = (set_code, card.get('number'))
        card_type = card.get('type', '')
        is_planeswalker = 'Planeswalker' in card_type

        parsed_cards[card_key] = {
            'name': card.get('name'),
            'mana_cost': card.get('manaCost', ''),
            'type': card_type,
            'text': card.get('text', ''),
            'power': '0' if is_planeswalker else card.get('power', None),
            'toughness': card.get('loyalty', None) if is_planeswalker else card.get('toughness', None),
            'supertypes': card.get('supertypes', []),
            'keywords': card.get('keywords', [])
        }
    return parsed_cards

def parse_effect_structures(card_text: str):
    """
    Parses card text for structured effects (target_filter, condition, triggered, activated).
    Returns a list of structured effect dicts.
    """
    effects = []
    if not card_text: return effects
    processed_spans = []

    # Simple patterns with improved regex
    for pattern, effect_builder in get_simple_patterns().items():
        for match in re.finditer(pattern, card_text, re.IGNORECASE):
            is_processed = any(start <= match.start() and end >= match.end() for start, end in processed_spans)
            if not is_processed:
                effects.append(effect_builder(match))
                processed_spans.append(match.span())

    return effects

def get_simple_patterns():
    return {
        r"(?:All|Other) creatures you control get \+(\d+)/\+(\d+)": lambda m: {
            "ability_type": "continuous_effect",
            "effect": {"type": "stat_modifier", "power": int(m.group(1)), "toughness": int(m.group(2))},
            "layer": 7,
            "target_filter": {"type": "creature", "controller": "self"}
        },
        r"Creatures you control get \+(\d+)/\+(\d+)": lambda m: {
            "ability_type": "continuous_effect",
            "effect": {"type": "stat_modifier", "power": int(m.group(1)), "toughness": int(m.group(2))},
            "layer": 7,
            "target_filter": {"type": "creature", "controller": "self"}
        },
        r"Target creature gets \+(\d+)/\+(\d+)": lambda m: {
            "ability_type": "temporary_stat_modifier",
            "effect": {"type": "stat_modifier", "power": int(m.group(1)), "toughness": int(m.group(2))},
            "duration": "until_end_of_turn",
            "target": {"type": "creature"}
        },
        r"Draw (\d+) cards?": lambda m: {
            "ability_type": "draw_cards",
            "amount": int(m.group(1))
        },
        r"(?:(?:~|this card|[\w\s,]+) )?deals? (\d+) damage to any target": lambda m: {
            "ability_type": "deal_damage",
            "amount": int(m.group(1)),
            "target": "any"
        },
        r"You gain (\d+) life": lambda m: {
            "ability_type": "gain_life",
            "amount": int(m.group(1))
        },
        r"Put a \+1/\+1 counter on ([\w\s]+)": lambda m: {
            "ability_type": "add_counter",
            "counter_type": "+1/+1",
            "target": m.group(1).strip()
        },
        r"Destroy target tapped creature": lambda m: {
            "ability_type": "destroy",
            "target": {
                "type": "creature",
                "is_tapped": True
            }
        },
        r"Counter target spell": lambda m: {
            "ability_type": "counter",
            "target": {
                "type": "spell"
            }
        },
        r"\{T\}: Add \{([WUBRGC])\}": lambda m: {
            "ability_type": "activated_ability",
            "cost": "{T}",
            "effect": {
                "ability_type": "add_mana",
                "mana_type": m.group(1)
            }
        }
    }

if __name__ == "__main__":
    # Use the project's standard db path
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    db_path = os.path.join(project_root, 'MTG_bot', 'data', 'mtg_bot.db')
    set_code = "M21"

    # Setup database and tables
    setup_database(db_path)

    # Download and parse card data
    json_path = download_set_data(set_code)
    if json_path:
        with open(json_path, 'r', encoding='utf-8') as f:
            mtgjson_data = json.load(f)
        
        parsed_cards = parse_mtgjson(mtgjson_data)
        insert_cards_to_db(db_path, parsed_cards)
