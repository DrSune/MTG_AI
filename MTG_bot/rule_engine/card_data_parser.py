import requests
import json
import argparse
import os
import sqlite3
import vocabulary
import re

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
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS cards (
        name TEXT PRIMARY KEY,
        mana_cost TEXT,
        type TEXT,
        text TEXT,
        power TEXT,
        toughness TEXT,
        supertypes TEXT,
        effects_json TEXT
    )
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS card_components (
        card_name TEXT,
        component_id INTEGER,
        FOREIGN KEY (card_name) REFERENCES cards(name),
        PRIMARY KEY (card_name, component_id)
    )
    ''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_card_name ON card_components (card_name)''')
    
    conn.commit()
    conn.close()
    print(f"Database setup complete at {db_path}")

def insert_cards_to_db(db_path, parsed_cards):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for name, data in parsed_cards.items():
        effects = parse_effect_structures(data['text'])
        for keyword in data.get('keywords', []):
            effects.append({'ability_type': 'keyword', 'keyword': keyword.lower()})

        cursor.execute('''
        INSERT OR REPLACE INTO cards (name, mana_cost, type, text, power, toughness, supertypes, effects_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            name,
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

def map_and_insert_components(db_path, parsed_cards):
    """
    Maps card text to component IDs and inserts them into the database.
    """
    keyword_map = {
        "trample": vocabulary.ID_ABILITY_TRAMPLE,
        "flying": vocabulary.ID_ABILITY_FLYING,
        "first strike": vocabulary.ID_ABILITY_FIRST_STRIKE,
        "deathtouch": vocabulary.ID_ABILITY_DEATHTOUCH,
        "lifelink": vocabulary.ID_ABILITY_LIFELINK,
        "haste": vocabulary.ID_ABILITY_HASTE,
        "protection": vocabulary.ID_ABILITY_PROTECTION,
        "double strike": vocabulary.ID_ABILITY_DOUBLE_STRIKE,
        "vigilance": vocabulary.ID_ABILITY_VIGILANCE,
        "indestructible": vocabulary.ID_ABILITY_INDESTRUCTIBLE,
        "flash": vocabulary.ID_ABILITY_FLASH,
        "hexproof": vocabulary.ID_ABILITY_HEXPROOF,
        "prowess": vocabulary.ID_ABILITY_PROWESS,
        "menace": vocabulary.ID_ABILITY_MENACE,
        "defender": vocabulary.ID_ABILITY_DEFENDER,
        "reach": vocabulary.ID_ABILITY_REACH
    }

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Clear old components for this set of cards before re-inserting
    card_names = list(parsed_cards.keys())
    if card_names:
        cursor.execute(f'DELETE FROM card_components WHERE card_name IN ({("?,"*len(card_names))[:-1]})', card_names)

    component_mappings = []
    for name, data in parsed_cards.items():
        card_keywords = data.get('keywords', [])
        if card_keywords:
            for keyword in card_keywords:
                if keyword.lower() in keyword_map:
                    component_mappings.append((name, keyword_map[keyword.lower()]))
        else:
            text = data.get('text', '').lower()
            for keyword, component_id in keyword_map.items():
                if re.search(r'\b' + keyword + r'\b', text):
                    component_mappings.append((name, component_id))

    if component_mappings:
        cursor.executemany('INSERT INTO card_components (card_name, component_id) VALUES (?, ?)', component_mappings)
    
    conn.commit()
    conn.close()
    print(f"Successfully inserted {len(component_mappings)} component mappings into the database.")

def parse_mtgjson(mtgjson_data):
    """
    Parses all cards from the MTGJSON data.
    """
    parsed_cards = {}
    all_cards = mtgjson_data.get('data', {}).get('cards', [])

    for card in all_cards:
        parsed_cards[card['name']] = {
            'mana_cost': card.get('manaCost', ''),
            'type': card.get('type', ''),
            'text': card.get('text', ''),
            'power': card.get('power', None),
            'toughness': card.get('toughness', None),
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
    parser = argparse.ArgumentParser(description="Download MTGJSON set data and store it in an SQLite database.")
    parser.add_argument("set_code", help="The MTGJSON set code (e.g., M21).")
    args = parser.parse_args()

    db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'mtg_cards.db')

    json_file_path = download_set_data(args.set_code)

    if json_file_path:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            mtgjson_data = json.load(f)
        setup_database(db_path)
        parsed_cards = parse_mtgjson(mtgjson_data)
        insert_cards_to_db(db_path, parsed_cards)
        map_and_insert_components(db_path, parsed_cards)

        # Verification
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        test_cards = ["Pestilent Haze", "Destructive Tampering", "Elder Gargaroth", "Heartfire Immolator", "Swift Response", "Cancel", "Radiant Fountain"]
        for card_name in test_cards:
            print(f"\n--- Verifying {card_name} ---")
            cursor.execute("SELECT effects_json FROM cards WHERE name = ?", (card_name,))
            row = cursor.fetchone()
            if row:
                effects = json.loads(row[0])
                print(f"Found effects for {card_name}: {effects}")
            else:
                print(f"Did not find {card_name}.")

        conn.close()
