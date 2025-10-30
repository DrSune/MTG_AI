import json
import os
import re
import sqlite3
from typing import Dict, Any, List, Optional

from MTG_bot import config
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper

class CardDataLoader:
    """
    Loads and processes card data from MTGJSON.
    """
    def __init__(self, mtgjson_path: str = config.MTGJSON_PATH):
        self.mtgjson_path = mtgjson_path
        self.all_cards_data: Dict[str, Any] = {}
        self.card_name_to_id: Dict[str, int] = {}
        self.card_id_to_data: Dict[int, Dict[str, Any]] = {}
        self.id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)
        self._load_data()

    def _get_id_from_game_vocabulary(self, name: str) -> Optional[int]:
        # This method is used internally by CardDataLoader for vocabulary terms
        conn = sqlite3.connect(self.id_mapper.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM game_vocabulary WHERE name = ?", (name,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

    def _get_max_card_id_from_db(self) -> int:
        conn = sqlite3.connect(config.MTG_BOT_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(card_id) FROM cards")
        max_id = cursor.fetchone()[0]
        conn.close()
        return max_id if max_id else 0

    def _load_data(self):
        print(f"--- CardDataLoader: Loading data from {self.mtgjson_path} ---")
        if not os.path.exists(self.mtgjson_path):
            raise FileNotFoundError(f"MTGJSON file not found at: {self.mtgjson_path}")

        with open(self.mtgjson_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        cards_in_m21 = raw_data.get("data", {}).get("cards", [])
        print(f"Cards in M21.json (first 5): {cards_in_m21[:5]}")

        current_card_id_counter = self._get_max_card_id_from_db() + 1 # Start custom IDs after existing ones

        for card_data in cards_in_m21:
            card_name = card_data.get("name")
            if card_name and card_name not in self.card_name_to_id:
                card_id = current_card_id_counter
                current_card_id_counter += 1
                
                self.card_name_to_id[card_name] = card_id
                self.card_id_to_data[card_id] = self._process_card_data(card_data)
                self.all_cards_data[card_name] = self.card_id_to_data[card_id]

    def _process_card_data(self, raw_card_data: Dict[str, Any]) -> Dict[str, Any]:
        processed_data = {
            "name": raw_card_data.get("name"),
            "mana_cost": self._parse_mana_cost(raw_card_data.get("manaCost", "")),
            "cmc": raw_card_data.get("convertedManaCost", 0),
            "type_line": raw_card_data.get("type"),
            "text": raw_card_data.get("text", ""),
            "power": int(raw_card_data.get("power")) if raw_card_data.get("power") and str(raw_card_data.get("power")).isdigit() else raw_card_data.get("power"),
            "toughness": int(raw_card_data.get("toughness")) if raw_card_data.get("toughness") and str(raw_card_data.get("toughness")).isdigit() else raw_card_data.get("toughness"),
            "loyalty": int(raw_card_data.get("loyalty")) if raw_card_data.get("loyalty") else None,
            "abilities": self._parse_abilities(raw_card_data.get("text", ""), raw_card_data.get("keywords", [])),
            "is_land": "Land" in raw_card_data.get("type", ""),
            "is_creature": "Creature" in raw_card_data.get("type", ""),
            "colors": raw_card_data.get("colors", []),
            "color_identity": raw_card_data.get("colorIdentity", []),
        }
        return processed_data

    def _parse_mana_cost(self, mana_cost_str: str) -> Dict[int, int]:
        cost = {}
        if not mana_cost_str: return cost

        generic_match = re.search(r'\{(\d+)\}', mana_cost_str)
        if generic_match:
            cost[self._get_id_from_game_vocabulary("Generic Mana")] = int(generic_match.group(1))

        for symbol, mana_name in [('W', "White Mana"), ('U', "Blue Mana"), ('B', "Black Mana"), ('R', "Red Mana"), ('G', "Green Mana"), ('C', "Colorless Mana")]:
            count = mana_cost_str.count(f'{{{symbol}}}')
            if count > 0:
                cost[self._get_id_from_game_vocabulary(mana_name)] = count
        return {k: v for k, v in cost.items() if v > 0}

    def _parse_abilities(self, card_text: str, keywords: List[str]) -> Dict[str, Any]:
        abilities = {"keywords": [], "mana_abilities": []}

        # Keyword abilities
        for keyword in keywords:
            keyword_id = self._get_id_from_game_vocabulary(keyword)
            if keyword_id:
                abilities["keywords"].append(keyword_id)

        # Mana abilities from text
        mana_ability_pattern = re.compile(r"\{T\}: Add (.*?).")
        matches = mana_ability_pattern.findall(card_text)
        for match in matches:
            produces = {}
            mana_symbols = re.findall(r'\{([WUBRGC])\}', match)
            for symbol in mana_symbols:
                mana_name = {'W': "White Mana", 'U': "Blue Mana", 'B': "Black Mana", 'R': "Red Mana", 'G': "Green Mana", 'C': "Colorless Mana"}.get(symbol)
                if mana_name:
                    mana_id = self._get_id_from_game_vocabulary(mana_name)
                    if mana_id:
                        produces[mana_id] = produces.get(mana_id, 0) + 1
            
            if produces:
                abilities["mana_abilities"].append({
                    "type": "mana",
                    "cost": {"tap": True},
                    "produces": produces
                })

        return abilities

    def get_card_data_by_id(self, card_id: int) -> Dict[str, Any]:
        return self.card_id_to_data.get(card_id, {})

    def get_card_id_by_name(self, card_name: str) -> int:
        return self.card_name_to_id.get(card_name)

    def get_all_card_ids(self) -> List[int]:
        return list(self.card_id_to_data.keys())
