import requests
import json
import argparse
import os
import sqlite3
import re
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from MTG_bot.utils.decorators import with_human_names

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
    """
    print("Setting up database...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''DROP TABLE IF EXISTS deck_cards''')
    cursor.execute('''DROP TABLE IF EXISTS decks''')
    cursor.execute('''DROP TABLE IF EXISTS users''')
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

    cursor.execute('''DROP TABLE IF EXISTS card_components''')
    
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
    print(f"Database setup complete at {db_path}")

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
    processed_spans = []

    # Pattern for triggered ability with a choice
    for match in re.finditer(r"(Whenever .+), (choose one —.+)", card_text, re.IGNORECASE | re.DOTALL):
        trigger = match.group(1).strip()
        choice_text = match.group(2).strip()
        choice_match = re.search(r"Choose (one|two|X) —(.+)", choice_text, re.IGNORECASE | re.DOTALL)
        if choice_match:
            num_choices_str = choice_match.group(1)
            num_choices = 1 if num_choices_str == 'one' else 2 if num_choices_str == 'two' else 'X'
            choices_text = choice_match.group(2)
            choices = [c.strip() for c in choices_text.split('•') if c.strip()]
            effects.append({
                "ability_type": "triggered_ability",
                "trigger": trigger,
                "effect": {
                    "ability_type": "choice",
                    "count": num_choices,
                    "options": choices
                }
            })
            processed_spans.append(match.span())
        continue # Avoid double parsing

    # Pattern for standalone choice
    for match in re.finditer(r"Choose (one|two|X) —(.+)", card_text, re.IGNORECASE | re.DOTALL):
        is_processed = any(start <= match.start() and end >= match.end() for start, end in processed_spans)
        if is_processed:
            continue
        num_choices_str = match.group(1)
        num_choices = 1 if num_choices_str == 'one' else 2 if num_choices_str == 'two' else 'X'
        choices_text = match.group(2)
        choices = [c.strip() for c in choices_text.split('•') if c.strip()]
        effects.append({
            "ability_type": "choice",
            "count": num_choices,
            "options": choices
        })
        processed_spans.append(match.span())

    # Simpler patterns
    for pattern, effect_builder in get_simple_patterns().items():
        for match in re.finditer(pattern, card_text, re.IGNORECASE):
            is_processed = any(start <= match.start() and end >= match.end() for start, end in processed_spans)
            if not is_processed:
                effects.append(effect_builder(match))

    return effects

def get_simple_patterns():
    return {
        r"All (\w+)s? you control get \+(\d+)/\+(\d+)": lambda m: {
            "ability_type": "continuous_effect",
            "effect": {"type": "stat_modifier", "power": int(m.group(2)), "toughness": int(m.group(3))},
            "target_filter": {
                "scope": "battlefield",
                "conditions": [
                    {"property": "type", "value": "creature"},
                    {"property": "subtype", "value": m.group(1)},
                    {"property": "controller", "value": "self"}
                ]
            }
        },
        r"If you control a ([\w\s]+), (?:~|this card|it) gets \+(\d+)/\+(\d+)": lambda m: {
            "ability_type": "continuous_effect",
            "effect": {"type": "stat_modifier", "power": int(m.group(2)), "toughness": int(m.group(3))},
            "condition": {
                "type": "card_presence",
                "card_name": m.group(1).strip(),
                "zone": "battlefield",
                "controller": "self"
            },
            "applies_to": "self"
        },
        r"Whenever ([\w\s,]+), ([\w\s\+\-]+)\.": lambda m: {
            "ability_type": "triggered_ability",
            "trigger": m.group(1).strip(),
            "effect_text": m.group(2).strip()
        },
        r"([\w\s\{\}\d]+): ([\w\s\+\-]+)\.": lambda m: {
            "ability_type": "activated_ability",
            "cost": m.group(1).strip(),
            "effect_text": m.group(2).strip()
        },
        r"(?:~|this card|it|[\w\s]+) gets \+(\d+)/\+(\d+) until end of turn": lambda m: {
            "ability_type": "temporary_stat_modifier",
            "effect": {"type": "stat_modifier", "power": int(m.group(1)), "toughness": int(m.group(2))},
            "duration": "until_end_of_turn",
            "applies_to": "self"
        },
        r"Draw (\d+) cards?": lambda m: {
            "ability_type": "draw_cards",
            "amount": int(m.group(1))
        },
        r"Deal (\d+) damage to any target": lambda m: {
            "ability_type": "deal_damage",
            "amount": int(m.group(1)),
            "target": "any"
        },
        r"You gain (\d+) life": lambda m: {
            "ability_type": "gain_life",
            "amount": int(m.group(1))
        },
        r"Search your library for a ([\w\s]+) card": lambda m: {
            "ability_type": "search_library",
            "card_type": m.group(1).strip()
        },
        r"Put a \+1/\+1 counter on ([\w\s]+)": lambda m: {
            "ability_type": "add_counter",
            "counter_type": "+1/+1",
            "target": m.group(1).strip()
        },
        r"protection from ([\w\s,and]+)": lambda m: {
            "ability_type": "protection",
            "from": [q.strip() for q in re.split(r',|and|from', m.group(1)) if q.strip()]
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
    db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'mtg_cards.db')
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
