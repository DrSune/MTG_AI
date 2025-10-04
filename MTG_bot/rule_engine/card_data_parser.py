import requests
import json
import argparse
import os
import sqlite3
import vocabulary

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
        supertypes TEXT
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
    """
    Inserts a dictionary of parsed card data into the SQLite database.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for name, data in parsed_cards.items():
        cursor.execute('''
        INSERT OR REPLACE INTO cards (name, mana_cost, type, text, power, toughness, supertypes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            name,
            data['mana_cost'],
            data['type'],
            data['text'],
            data['power'],
            data['toughness'],
            json.dumps(data['supertypes'])
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
        "haste": vocabulary.ID_ABILITY_HASTE
    }

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Clear old components for this set of cards before re-inserting
    card_names = list(parsed_cards.keys())
    cursor.execute(f'DELETE FROM card_components WHERE card_name IN ({("?,"*len(card_names))[:-1]})', card_names)

    component_mappings = []
    for name, data in parsed_cards.items():
        text = data.get('text', '').lower()
        for keyword, component_id in keyword_map.items():
            if keyword in text.split(): # Check if keyword is a whole word
                component_mappings.append((name, component_id))

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
        }
    return parsed_cards

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download MTGJSON set data and store it in an SQLite database.")
    parser.add_argument("set_code", help="The MTGJSON set code (e.g., M21).")
    args = parser.parse_args()

    db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'mtg_cards.db')

    json_file_path = download_set_data(args.set_code)

    if json_file_path:
        setup_database(db_path)

        with open(json_file_path, 'r', encoding='utf-8') as f:
            mtgjson_data = json.load(f)
        
        parsed_data = parse_mtgjson(mtgjson_data)
        print(f"Parsed {len(parsed_data)} cards from {args.set_code}.json")

        insert_cards_to_db(db_path, parsed_data)
        map_and_insert_components(db_path, parsed_data)
