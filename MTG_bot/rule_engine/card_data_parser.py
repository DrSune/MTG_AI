import requests
import json
import argparse
import os
import sqlite3

def download_set_data(set_code, output_dir="."):
    """
    Downloads a set's data from MTGJSON.
    """
    url = f"https://mtgjson.com/api/v5/{set_code}.json"
    # Place downloaded JSON inside the data directory
    output_path = os.path.join(os.path.dirname(__file__), '..', 'data')
    file_path = os.path.join(output_path, f"{set_code}.json")

    print(f"Downloading data for set '{set_code}' from {url}...")
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        os.makedirs(output_path, exist_ok=True) # Ensure the data directory exists
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(response.json(), f)
        print(f"Successfully downloaded and saved to {file_path}")
        return file_path
    except requests.exceptions.RequestException as e:
        print(f"Error downloading file: {e}")
        return None

def setup_database(db_path):
    """
    Creates the SQLite database and the cards table if they don't exist.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create table
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
            json.dumps(data['supertypes']) # Store list as a JSON string
        ))
    
    conn.commit()
    conn.close()
    print(f"Successfully inserted or replaced {len(parsed_cards)} cards in the database.")

def parse_mtgjson(mtgjson_data, card_subset=None):
    """
    Parses MTGJSON data to extract information for a specific subset of cards.
    If card_subset is None, it will process all cards.
    """
    parsed_cards = {}
    all_cards = mtgjson_data.get('data', {}).get('cards', [])

    for card in all_cards:
        if card_subset and card['name'] not in card_subset:
            continue

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

    # Define the database path relative to this script
    db_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'mtg_cards.db')

    # 1. Download the data
    json_file_path = download_set_data(args.set_code)

    if json_file_path:
        # 2. Setup the database
        setup_database(db_path)

        # 3. Parse the JSON data
        with open(json_file_path, 'r', encoding='utf-8') as f:
            mtgjson_data = json.load(f)
        
        # For this run, we will parse ALL cards from the set
        parsed_data = parse_mtgjson(mtgjson_data)
        print(f"Parsed {len(parsed_data)} cards from {args.set_code}.json")

        # 4. Insert data into the database
        insert_cards_to_db(db_path, parsed_data)