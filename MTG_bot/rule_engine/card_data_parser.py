import requests
import json
import argparse
import os
import sqlite3
import re
import sys
import random

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
    print(f"Ensuring database tables at {db_path}...")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''DROP TABLE IF EXISTS deck_cards''')
    cursor.execute('''DROP TABLE IF EXISTS cards''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS cards (card_id INTEGER PRIMARY KEY AUTOINCREMENT, set_code TEXT NOT NULL, card_number TEXT NOT NULL, name TEXT, mana_cost TEXT, type TEXT, text TEXT, power TEXT, toughness TEXT, supertypes TEXT, effects_json TEXT, rarity TEXT, UNIQUE (set_code, card_number))''')
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
        
        # Mark as basic land for draft simulator
        is_basic = "Basic" in data.get('supertypes', [])
        
        cursor.execute('''
        INSERT OR REPLACE INTO cards (set_code, card_number, name, mana_cost, type, text, power, toughness, supertypes, effects_json, rarity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            json.dumps(effects),
            data['rarity']
        ))
    conn.commit()
    conn.close()

def parse_mtgjson(mtgjson_data):
    """
    Parses all cards from the MTGJSON data.
    """
    parsed_cards = {}
    all_cards = mtgjson_data.get('data', {}).get('cards', [])
    set_code = mtgjson_data.get('data', {}).get('code')

    for card in all_cards:
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
            'keywords': card.get('keywords', []),
            'rarity': card.get('rarity', 'common')
        }
    return parsed_cards

def parse_effect_structures(card_text: str):
    if not card_text or not card_text.strip(): return [{"ability_type": "vanilla"}]
    if "{T}: Add {" in card_text:
        mana_match = re.search(r"\{T\}: Add \{(.)\}", card_text)
        if mana_match: return [{"ability_type": "activated_ability", "cost": "{T}", "effect": {"ability_type": "add_mana", "mana_type": mana_match.group(1)}}]
    all_effects = []
    if "—" in card_text and ("Choose" in card_text or "choose" in card_text):
        modal_match = re.search(r"(?:Choose|choose) (one|two|three|any number) —\n(.*)", card_text, re.DOTALL | re.IGNORECASE)
        if modal_match:
            mode_lines = re.split(r"\n•\s*", modal_match.group(2))
            modes = [{"mode_text": l.strip(), "effects": parse_paragraph(l.strip())} for l in mode_lines if l.strip()]
            all_effects.append({"ability_type": "modal_ability", "count": modal_match.group(1), "modes": modes})
            return all_effects
    for paragraph in card_text.split("\n"): all_effects.extend(parse_paragraph(paragraph))
    return all_effects

def parse_paragraph(paragraph: str):
    if not paragraph.strip(): return []
    loyalty_match = re.match(r"\[([+−-]\d+)\]: (.*)", paragraph, re.IGNORECASE)
    if loyalty_match: return [{"ability_type": "loyalty_ability", "cost": loyalty_match.group(1).replace("−", "-"), "effects": parse_sentence(loyalty_match.group(2))}]
    activated_match = re.match(r"\{(.*?)\}: (.*)", paragraph, re.IGNORECASE)
    if activated_match: return [{"ability_type": "activated_ability", "cost": activated_match.group(1), "effects": parse_sentence(activated_match.group(2))}]
    effects = []
    for sentence in re.split(r'\.(?=\s|$)', paragraph):
        sentence = sentence.strip()
        if not sentence: continue
        if sentence.lower().startswith("if "):
            cond_match = re.match(r"If (.*?), (.*)", sentence, re.IGNORECASE)
            if cond_match:
                effects.append({"ability_type": "conditional_effect", "condition": cond_match.group(1).strip(), "effects": parse_sentence(cond_match.group(2))})
                continue
        effects.extend(parse_sentence(sentence))
    return effects

def parse_sentence(sentence: str):
    effects = []
    if "as long as" in sentence.lower():
        cond_match = re.search(r"(.*?) as long as (.*)", sentence, re.IGNORECASE)
        if cond_match: return [{"ability_type": "conditional_static_ability", "condition": cond_match.group(2).strip(), "effects": parse_sentence(cond_match.group(1))}]
    trigger_match = re.match(r"(When|At|Whenever) (.*?), (.*)", sentence, re.IGNORECASE)
    if trigger_match: return [{"ability_type": "triggered_ability", "trigger_condition": trigger_match.group(2).strip(), "effects": parse_sentence(trigger_match.group(3))}]
    choose_match = re.search(r"Choose (up to )?(\d+|one|two|three|any number of)", sentence, re.IGNORECASE)
    for pattern, builder in get_atomic_patterns().items():
        for match in re.finditer(pattern, sentence, re.IGNORECASE):
            effect = builder(match)
            if choose_match: effect["choice_meta"] = {"count": choose_match.group(2), "up_to": bool(choose_match.group(1))}
            effects.append(effect)
    cost_match = re.search(r"sacrifice a (creature|permanent|land)", sentence, re.IGNORECASE)
    if cost_match and "additional cost" in sentence: effects.append({"ability_type": "additional_cost", "cost_type": "sacrifice", "target": {"type": cost_match.group(1).lower()}})
    return effects

def text_to_int(text: str):
    mapping = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "a": 1, "an": 1, "up to two": 2, "up to one": 1}
    if text.isdigit(): return int(text)
    return mapping.get(text.lower(), 1)

def get_atomic_patterns():
    num = r"(\d+|one|two|three|four|five|six|seven|eight|nine|ten|a|an|up to two|up to one)"
    return {
        r"target (creature|player|opponent|permanent|spell|land|planeswalker|any target|nonland permanent)": lambda m: {"type": "selector", "count": 1, "filter": {"type": m.group(1).lower() if m.group(1) not in ["any target", "nonland permanent"] else ("any" if m.group(1) == "any target" else "nonland_permanent")}, "mode": "targeted"},
        fr"deals? ({num}|X) damage": lambda m: {"ability_type": "deal_damage", "amount": text_to_int(m.group(1)) if m.group(1).lower() != "x" else "X"},
        fr"draw ({num}|X) cards?": lambda m: {"ability_type": "draw_cards", "amount": text_to_int(m.group(1)) if m.group(1).lower() != "x" else "X"},
        fr"gain ({num}|X) life": lambda m: {"ability_type": "gain_life", "amount": text_to_int(m.group(1)) if m.group(1).lower() != "x" else "X"},
        fr"lose ({num}|X) life": lambda m: {"ability_type": "lose_life", "amount": text_to_int(m.group(1)) if m.group(1).lower() != "x" else "X"},
        r"destroy ([\w\s]+)": lambda m: {"ability_type": "destroy", "target_raw": m.group(1).strip()},
        r"exile ([\w\s]+)": lambda m: {"ability_type": "exile", "target_raw": m.group(1).strip()},
        fr"create {num} (\d+)/(\d+) ([\w\s]+) token": lambda m: {"ability_type": "create_token", "count": text_to_int(m.group(1)), "power": int(m.group(2)), "toughness": int(m.group(3)), "token_type": m.group(4).strip()},
        fr"(?:other )?([\w\s]+) get ([\+-]\d+)/([\+-]\d+)": lambda m: {"ability_type": "continuous_effect", "filter": {"type": m.group(1).strip()}, "effect": {"type": "stat_modifier", "power": int(m.group(2)), "toughness": int(m.group(3))}, "layer": 7},
        r"put a \+1/\+1 counter": lambda m: {"ability_type": "add_counter", "counter_type": "+1/+1"},
        r"return (.*?) from your graveyard to (your hand|the battlefield)": lambda m: {"ability_type": "return_from_graveyard", "target": m.group(1).strip(), "destination": m.group(2).strip()},
        r"search your library for (.*?), (?:reveal (?:it|them|those cards), )?put (.*?), then shuffle": lambda m: {"ability_type": "search_library", "filter": m.group(1).strip(), "destination": m.group(2).strip()},
        r"enters tapped": lambda m: {"ability_type": "static_ability", "effect": "enters_tapped"},
        r"unless its controller pays \{(.*?)\}": lambda m: {"ability_type": "unless_cost", "cost": m.group(1).strip()},
        r"gain (hexproof|indestructible|flying|lifelink|deathtouch|haste)": lambda m: {"ability_type": "gain_keyword", "keyword": m.group(1).lower()},
        r"play (.*?) additional lands?": lambda m: {"ability_type": "rule_change", "rule": "additional_lands", "count": text_to_int(m.group(1))},
        r"can't be blocked": lambda m: {"ability_type": "static_ability", "effect": "unblockable"},
        r"As (?:this|~|this enchantment) enters, (.*)": lambda m: {"ability_type": "enters_choice", "choice_text": m.group(1).strip()},
        r"Play with the top card of your library revealed": lambda m: {"ability_type": "static_rule", "rule": "reveal_top_card"},
        r"You may cast (.*?) spells from the top of your library": lambda m: {"ability_type": "static_rule", "rule": "cast_from_top", "filter": m.group(1).strip()}
    }

if __name__ == "__main__":
    db_path = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')), 'MTG_bot', 'data', 'mtg_bot.db')
    setup_database(db_path)
    json_path = download_set_data("M21")
    if json_path:
        with open(json_path, 'r', encoding='utf-8') as f: mtgjson_data = json.load(f)
        insert_cards_to_db(db_path, parse_mtgjson(mtgjson_data))
