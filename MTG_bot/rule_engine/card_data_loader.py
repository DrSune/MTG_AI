import json
import os
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
        conn = sqlite3.connect(config.MTG_BOT_DB_PATH)
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
        
        # Correctly access cards from the M21.json structure
        cards_in_m21 = raw_data.get("data", {}).get("cards", [])
        print(f"Cards in M21.json (first 5): {cards_in_m21[:5]}")

        current_card_id = self._get_max_card_id_from_db() + 1 # Start custom IDs after existing ones

        for card_data in cards_in_m21:
            card_name = card_data.get("name")
            if card_name and card_name not in self.card_name_to_id:
                # Assign a new ID if not already in vocabulary
                # Check if the card name exists as a predefined ID in vocab
                # This is a simplified check and might need more robust handling for variations
                # vocab_id_name = f"ID_CARD_{card_name.replace(' ', '_').replace('-', '_').replace('\'', '').upper()}"
                # if hasattr(vocab, vocab_id_name):
                #     card_id = getattr(vocab, vocab_id_name)
                # else:
                card_id = current_card_id
                current_card_id += 1
                
                self.card_name_to_id[card_name] = card_id
                self.card_id_to_data[card_id] = self._process_card_data(card_data)
                self.all_cards_data[card_name] = self.card_id_to_data[card_id]

    def _process_card_data(self, raw_card_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extracts and formats relevant data from a raw MTGJSON card entry.
        """
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
        """
        Parses a mana cost string (e.g., "{2}{R}{G}") into a dictionary of vocab IDs.
        """
        MANA_GENERIC = self._get_id_from_game_vocabulary("Generic Mana")
        MANA_WHITE = self._get_id_from_game_vocabulary("White Mana")
        MANA_BLUE = self._get_id_from_game_vocabulary("Blue Mana")
        MANA_BLACK = self._get_id_from_game_vocabulary("Black Mana")
        MANA_RED = self._get_id_from_game_vocabulary("Red Mana")
        MANA_GREEN = self._get_id_from_game_vocabulary("Green Mana")

        cost = {MANA_GENERIC: 0, MANA_WHITE: 0, MANA_BLUE: 0, 
                MANA_BLACK: 0, MANA_RED: 0, MANA_GREEN: 0}
        
        temp_cost_str = mana_cost_str.replace('{', '').replace('}', '')
        
        i = 0
        while i < len(temp_cost_str):
            char = temp_cost_str[i]
            if char.isdigit():
                j = i
                while j < len(temp_cost_str) and temp_cost_str[j].isdigit():
                    j += 1
                cost[vocab.ID_MANA_GENERIC] += int(temp_cost_str[i:j])
                i = j
            elif char == 'W': cost[MANA_WHITE] += 1; i += 1
            elif char == 'U': cost[MANA_BLUE] += 1; i += 1
            elif char == 'B': cost[MANA_BLACK] += 1; i += 1
            elif char == 'R': cost[MANA_RED] += 1; i += 1
            elif char == 'G': cost[MANA_GREEN] += 1; i += 1
            # Add more complex mana symbols if needed (e.g., hybrid, colorless, X)
            else: i += 1 # Skip unknown characters
        
        return {k: v for k, v in cost.items() if v > 0}

    def _parse_abilities(self, card_text: str, keywords: List[str]) -> List[int]:
        """
        Parses card text and keywords to identify abilities and map them to vocab IDs.
        This is a very basic implementation and will need significant expansion.
        """
        ABILITY_FLYING = self._get_id_from_game_vocabulary("Flying")
        ABILITY_HASTE = self._get_id_from_game_vocabulary("Haste")
        ABILITY_VIGILANCE = self._get_id_from_game_vocabulary("Vigilance")
        ABILITY_LIFELINK = self._get_id_from_game_vocabulary("Lifelink")
        ABILITY_TRAMPLE = self._get_id_from_game_vocabulary("Trample")
        ABILITY_TAP_ADD_GREEN = self._get_id_from_game_vocabulary("Tap: Add Green Mana")
        ABILITY_TAP_ADD_BLUE = self._get_id_from_game_vocabulary("Tap: Add Blue Mana")
        ABILITY_TAP_ADD_BLACK = self._get_id_from_game_vocabulary("Tap: Add Black Mana")
        ABILITY_TAP_ADD_RED = self._get_id_from_game_vocabulary("Tap: Add Red Mana")
        ABILITY_TAP_ADD_WHITE = self._get_id_from_game_vocabulary("Tap: Add White Mana")

        # Basic keyword mapping
        if "Flying" in keywords: abilities.append(ABILITY_FLYING)
        if "Haste" in keywords: abilities.append(ABILITY_HASTE)
        if "Vigilance" in keywords: abilities.append(ABILITY_VIGILANCE)
        if "Lifelink" in keywords: abilities.append(ABILITY_LIFELINK)
        if "Trample" in keywords: abilities.append(ABILITY_TRAMPLE)
        # Add more keyword abilities as needed

        # Basic text-based ability parsing (very rudimentary)
        if "{T}: Add {G}" in card_text: abilities.append(ABILITY_TAP_ADD_GREEN)
        if "{T}: Add {U}" in card_text: abilities.append(ABILITY_TAP_ADD_BLUE)
        if "{T}: Add {B}" in card_text: abilities.append(ABILITY_TAP_ADD_BLACK)
        if "{T}: Add {R}" in card_text: abilities.append(ABILITY_TAP_ADD_RED)
        if "{T}: Add {W}" in card_text: abilities.append(ABILITY_TAP_ADD_WHITE)

        return list(set(abilities)) # Return unique abilities

    def get_card_data_by_id(self, card_id: int) -> Dict[str, Any]:
        """
        Returns processed card data for a given card ID.
        """
        return self.card_id_to_data.get(card_id, {})

    def get_card_id_by_name(self, card_name: str) -> int:
        """
        Returns the internal ID for a given card name.
        """
        return self.card_name_to_id.get(card_name)

    def get_all_card_ids(self) -> List[int]:
        """
        Returns a list of all loaded card IDs.
        """
        return list(self.card_id_to_data.keys())
