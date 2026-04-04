import json
import os
import re
import sqlite3
from typing import Dict, Any, List, Optional

from MTG_bot import config
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot.utils.logger import setup_logger

class CardDataLoader:
    """
    Loads and processes card data from the SQLite database.
    """
    def __init__(self, db_path: str = config.MTG_BOT_DB_PATH):
        self.db_path = db_path
        self.all_cards_data: Dict[str, Any] = {}
        self.card_name_to_id: Dict[str, int] = {}
        self.card_id_to_data: Dict[int, Dict[str, Any]] = {}
        self.id_mapper = IDToNameMapper(db_path)
        self.logger = setup_logger(__name__)
        self._load_data_from_db()

    def _get_id_from_game_vocabulary(self, name: str) -> Optional[int]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM game_vocabulary WHERE name = ?", (name,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

    def _load_data_from_db(self):
        self.logger.info(f"Loading card data from database: {self.db_path}")
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database file not found at: {self.db_path}")

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM cards")
        rows = cursor.fetchall()
        
        for row in rows:
            card_id = row['card_id']
            card_name = row['name']
            
            processed_data = self._process_db_row(row)
            
            self.card_name_to_id[card_name] = card_id
            self.card_id_to_data[card_id] = processed_data
            self.all_cards_data[card_name] = processed_data

        conn.close()
        self.logger.debug(f"Loaded {len(self.card_id_to_data)} cards from database.")

    def _process_db_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        mana_cost_str = row['mana_cost'] or ""
        type_line = row['type'] or ""
        text = row['text'] or ""
        name = row['name']
        
        # Parse effects_json
        try:
            effects = json.loads(row['effects_json'] or "[]")
        except json.JSONDecodeError:
            effects = []

        processed_data = {
            "name": name,
            "mana_cost": self._parse_mana_cost(mana_cost_str),
            "type_line": type_line,
            "text": text,
            "power": int(row['power']) if row['power'] and str(row['power']).isdigit() else 0,
            "toughness": int(row['toughness']) if row['toughness'] and str(row['toughness']).isdigit() else 0,
            "effects": effects,
            "is_land": "Land" in type_line,
            "is_creature": "Creature" in type_line,
            "is_instant": "Instant" in type_line,
            "is_sorcery": "Sorcery" in type_line,
            "supertypes": json.loads(row['supertypes'] or "[]"),
        }

        # --- AUTOMATIC TRIGGER MAPPING (Generalization) ---
        text_lower = text.lower()
        if "when skyscanner enters the battlefield, draw a card" in text_lower or ("enters the battlefield" in text_lower and "draw a card" in text_lower):
            # Generalized ETB Draw check
            if not any(e.get('trigger_condition') == "enters the battlefield" for e in processed_data["effects"]):
                processed_data["effects"].append({
                    "ability_type": "triggered_ability",
                    "trigger_condition": "When this enters the battlefield",
                    "effects": [{"ability_type": "draw_cards", "amount": 1}]
                })

        # --- VIRTUAL HYDRATION ---
        if name == "Nine Lives":
            processed_data["replacement_effect"] = {"event": "damage", "target_type": "controller", "action": "prevent_and_counter"}
        
        elif name == "Runed Halo":
            processed_data["has_as_enters_choice"] = True
            processed_data["as_enters_choice_type"] = "card_name"
            
        elif name == "Riddleform":
            processed_data["effects"].append({
                "ability_type": "triggered_ability",
                "trigger_condition": "Whenever you cast a noncreature spell",
                "effects": [{"ability_type": "animate_permanent", "power": 3, "toughness": 3, "keywords": ["Flying"]}]
            })
            
        elif name == "Teferi's Ageless Insight":
            processed_data["replacement_effect"] = {"event": "draw", "action": "draw_twice"}
            
        elif name == "Jolrael, Mwonvuli Recluse":
            processed_data["effects"].append({
                "ability_type": "triggered_ability",
                "trigger_condition": "Whenever you draw a card",
                "secondary_condition": "second_draw_this_turn",
                "effects": [{"ability_type": "create_token", "name": "Cat", "power": 2, "toughness": 2}]
            })

        processed_data["abilities"] = self._extract_abilities_from_effects(processed_data["effects"], text)
        return processed_data

    def _extract_abilities_from_effects(self, effects: List[Dict[str, Any]], text: str) -> Dict[str, Any]:
        abilities = {"keywords": [], "mana_abilities": []}
        
        for effect in effects:
            if effect.get("ability_type") == "keyword":
                keyword_name = effect.get("keyword", "").capitalize()
                keyword_id = self._get_id_from_game_vocabulary(keyword_name)
                if keyword_id:
                    abilities["keywords"].append(keyword_id)
            
            elif effect.get("ability_type") == "activated_ability":
                # Check if it's a mana ability
                # Simplified: if it adds mana
                eff = effect.get("effect", {})
                if eff.get("ability_type") == "add_mana":
                    mana_type = eff.get("mana_type")
                    mana_name = {'W': "White Mana", 'U': "Blue Mana", 'B': "Black Mana", 'R': "Red Mana", 'G': "Green Mana", 'C': "Colorless Mana"}.get(mana_type)
                    if mana_name:
                        mana_id = self._get_id_from_game_vocabulary(mana_name)
                        if mana_id:
                            abilities["mana_abilities"].append({
                                "type": "mana",
                                "cost": {"tap": "{T}" in effect.get("cost", "")},
                                "produces": {int(mana_id): 1}
                            })

        return abilities

    def _parse_mana_cost(self, mana_cost_str: str) -> Dict[int, int]:
        cost = {}
        if not mana_cost_str: return cost

        generic_match = re.search(r'\{(\d+)\}', mana_cost_str)
        if generic_match:
            generic_id = self._get_id_from_game_vocabulary("Generic Mana")
            if generic_id:
                cost[int(generic_id)] = int(generic_match.group(1))

        for symbol, mana_name in [('W', "White Mana"), ('U', "Blue Mana"), ('B', "Black Mana"), ('R', "Red Mana"), ('G', "Green Mana"), ('C', "Colorless Mana")]:
            count = mana_cost_str.count(f'{{{symbol}}}')
            if count > 0:
                mana_id = self._get_id_from_game_vocabulary(mana_name)
                if mana_id:
                    cost[int(mana_id)] = count
        return {k: v for k, v in cost.items() if v > 0}

    def get_card_data_by_id(self, card_id: int) -> Dict[str, Any]:
        return self.card_id_to_data.get(card_id, {})

    def get_card_id_by_name(self, card_name: str) -> int:
        return self.card_name_to_id.get(card_name)

    def get_all_card_ids(self) -> List[int]:
        return list(self.card_id_to_data.keys())
