import os
import sys
import json
import random
import uuid
from typing import List, Dict, Any, Optional
import sqlite3

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from MTG_bot import config
from MTG_bot.rule_engine.card_database import card_data_loader
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper

class ProceduralGenerator:
    """
    Generates MTG scenarios procedurally by querying the card database
    and fitting cards into tactical templates.
    """
    def __init__(self, db_path: str = config.MTG_BOT_DB_PATH):
        self.db_path = db_path
        self.id_mapper = IDToNameMapper(db_path)
        self._index_cards()

    def _index_cards(self):
        """Indexes cards by effect and type in a single pass."""
        self.cards_by_effect = {}
        self.cards_by_type = {"Land": [], "Creature": [], "Instant": [], "Sorcery": [], "Planeswalker": []}
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT card_id, type, effects_json FROM cards")
        
        for card_id, type_line, effects_json in cursor.fetchall():
            type_line = type_line or ""
            # Index by type
            for t in self.cards_by_type.keys():
                if t in type_line:
                    self.cards_by_type[t].append(card_id)
            
            # Index by effect
            try:
                effects = json.loads(effects_json or "[]")
                for effect in effects:
                    eff_type = effect.get("ability_type")
                    if eff_type:
                        if eff_type not in self.cards_by_effect:
                            self.cards_by_effect[eff_type] = []
                        self.cards_by_effect[eff_type].append(card_id)
            except:
                continue
        conn.close()

    def generate_lethal_burn_scenario(self) -> Dict[str, Any]:
        """
        Template: Opponent at X life. Player has a burn spell (Instant/Sorcery) that deals X damage.
        """
        burn_cards = self.cards_by_effect.get("deal_damage", [])
        if not burn_cards:
            return None
        
        burn_pool = list(burn_cards)
        random.shuffle(burn_pool)
        
        chosen_card_id = None
        damage = 0
        
        for card_id in burn_pool:
            card_data = card_data_loader.get_card_data_by_id(card_id)
            # ONLY Instants or Sorceries for "Lethal Burn" template
            if not (card_data.get("is_instant") or card_data.get("is_sorcery")):
                continue
            
            # Find the damage amount from structured effects
            for eff in card_data.get("effects", []):
                if eff.get("ability_type") == "deal_damage" and eff.get("target") == "any":
                    damage = max(damage, eff.get("amount", 0))
            
            if damage > 0:
                chosen_card_id = card_id
                break
        
        if not chosen_card_id:
            return None

        card_data = card_data_loader.get_card_data_by_id(chosen_card_id)
        opponent_life = random.randint(1, damage)
        mana_cost = card_data.get("mana_cost", {})
        
        needed_lands = []
        for mana_id, amount in mana_cost.items():
            land_name = self.id_mapper.get_name(mana_id, "game_vocabulary").replace(" Mana", "")
            land_id = card_data_loader.get_card_id_by_name(land_name)
            if land_id:
                needed_lands.extend([land_id] * amount)
        
        return {
            "name": f"Lethal Burn: {card_data['name']}",
            "description": f"Opponent at {opponent_life} life. Cast {card_data['name']} for the win.",
            "setup": {
                "p1_hand": [chosen_card_id],
                "p1_battlefield_lands": needed_lands,
                "p2_life": opponent_life
            },
            "goal": "p2_life <= 0"
        }

    def generate_lethal_combat_scenario(self) -> Dict[str, Any]:
        creatures = self.cards_by_type.get("Creature", [])
        if not creatures:
            return None
        
        creature_pool = list(creatures)
        random.shuffle(creature_pool)
        
        chosen_card_id = None
        power = 0
        
        for card_id in creature_pool:
            card_data = card_data_loader.get_card_data_by_id(card_id)
            p = card_data.get("power", 0)
            if isinstance(p, str) and p.isdigit(): p = int(p)
            if isinstance(p, int) and p > 0:
                # Basic check: is it just a normal creature (not a weird land-creature for now)
                if not card_data.get("is_land"):
                    chosen_card_id = card_id
                    power = p
                    break
        
        if not chosen_card_id:
            return None

        card_data = card_data_loader.get_card_data_by_id(chosen_card_id)
        opponent_life = random.randint(1, power)
        
        return {
            "name": f"Lethal Combat: {card_data['name']}",
            "description": f"Opponent at {opponent_life} life. Attack with {card_data['name']} for the win.",
            "setup": {
                "p1_battlefield_creatures": [chosen_card_id],
                "p2_life": opponent_life
            },
            "goal": "p2_life <= 0"
        }

    def save_scenario(self, scenario: Dict[str, Any], path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(scenario, f, indent=4)

if __name__ == "__main__":
    gen = ProceduralGenerator()
    lethal_dir = os.path.join(os.path.dirname(__file__), "M21", "level_1", "lethal")
    if os.path.exists(lethal_dir):
        for f in os.listdir(lethal_dir):
            if f.endswith(".json"):
                os.remove(os.path.join(lethal_dir, f))

    count = 0
    attempts = 0
    while count < 3 and attempts < 100:
        attempts += 1
        s = gen.generate_lethal_burn_scenario()
        if s:
            gen.save_scenario(s, os.path.join(lethal_dir, f"lethal_burn_{count}.json"))
            print(f"Generated lethal_burn_{count}.json")
            count += 1
            
    count = 0
    attempts = 0
    while count < 3 and attempts < 100:
        attempts += 1
        s = gen.generate_lethal_combat_scenario()
        if s:
            gen.save_scenario(s, os.path.join(lethal_dir, f"lethal_combat_{count}.json"))
            print(f"Generated lethal_combat_{count}.json")
            count += 1
