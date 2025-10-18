import json
import os
from typing import Dict, Any, List

from .. import config
from . import vocabulary as vocab

class CardDataLoader:
    """
    Loads and processes card data from MTGJSON.
    """
    def __init__(self, mtgjson_path: str = config.MTGJSON_PATH):
        self.mtgjson_path = mtgjson_path
        self.all_cards_data: Dict[str, Any] = {}
        self.card_name_to_id: Dict[str, int] = {}
        self.card_id_to_data: Dict[int, Dict[str, Any]] = {}
        self._load_data()

    def _load_data(self):
        print(f"--- CardDataLoader: Loading data from {self.mtgjson_path} ---")
        if not os.path.exists(self.mtgjson_path):
            raise FileNotFoundError(f"MTGJSON file not found at: {self.mtgjson_path}")

        with open(self.mtgjson_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        # Directly load cards from the M21.json structure
        cards_in_m21 = raw_data.get("cards", [])

        current_card_id = vocab.ID_CARD_CUSTOM_START # Start custom IDs after predefined ones

        for card_data in cards_in_m21:
            card_name = card_data.get("name")
            if card_name and card_name not in self.card_name_to_id:
                # Assign a new ID if not already in vocabulary
                # Check if the card name exists as a predefined ID in vocab
                # This is a simplified check and might need more robust handling for variations
                vocab_id_name = f"ID_CARD_{card_name.replace(' ', '_').replace('-', '_').replace('\'', '').upper()}"
                if hasattr(vocab, vocab_id_name):
                    card_id = getattr(vocab, vocab_id_name)
                else:
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
            "power": int(raw_card_data.get("power")) if raw_card_data.get("power") else None,
            "toughness": int(raw_card_data.get("toughness")) if raw_card_data.get("toughness") else None,
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
        cost = {vocab.ID_MANA_GENERIC: 0, vocab.ID_MANA_WHITE: 0, vocab.ID_MANA_BLUE: 0, 
                vocab.ID_MANA_BLACK: 0, vocab.ID_MANA_RED: 0, vocab.ID_MANA_GREEN: 0}
        
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
            elif char == 'W': cost[vocab.ID_MANA_WHITE] += 1; i += 1
            elif char == 'U': cost[vocab.ID_MANA_BLUE] += 1; i += 1
            elif char == 'B': cost[vocab.ID_MANA_BLACK] += 1; i += 1
            elif char == 'R': cost[vocab.ID_MANA_RED] += 1; i += 1
            elif char == 'G': cost[vocab.ID_MANA_GREEN] += 1; i += 1
            # Add more complex mana symbols if needed (e.g., hybrid, colorless, X)
            else: i += 1 # Skip unknown characters
        
        return {k: v for k, v in cost.items() if v > 0}

    def _parse_abilities(self, card_text: str, keywords: List[str]) -> List[int]:
        """
        Parses card text and keywords to identify abilities and map them to vocab IDs.
        This is a very basic implementation and will need significant expansion.
        """
        abilities = []
        # Basic keyword mapping
        if "Flying" in keywords: abilities.append(vocab.ID_ABILITY_FLYING)
        if "Haste" in keywords: abilities.append(vocab.ID_ABILITY_HASTE)
        if "Vigilance" in keywords: abilities.append(vocab.ID_ABILITY_VIGILANCE)
        if "Lifelink" in keywords: abilities.append(vocab.ID_ABILITY_LIFELINK)
        if "Trample" in keywords: abilities.append(vocab.ID_ABILITY_TRAMPLE)
        # Add more keyword abilities as needed

        # Basic text-based ability parsing (very rudimentary)
        if "{T}: Add {G}" in card_text: abilities.append(vocab.ID_ABILITY_TAP_ADD_GREEN)
        if "{T}: Add {U}" in card_text: abilities.append(vocab.ID_ABILITY_TAP_ADD_BLUE)
        if "{T}: Add {B}" in card_text: abilities.append(vocab.ID_ABILITY_TAP_ADD_BLACK)
        if "{T}: Add {R}" in card_text: abilities.append(vocab.ID_ABILITY_TAP_ADD_RED)
        if "{T}: Add {W}" in card_text: abilities.append(vocab.ID_ABILITY_TAP_ADD_WHITE)

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
