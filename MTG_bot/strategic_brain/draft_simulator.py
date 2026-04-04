import sqlite3
import random
from typing import List, Dict, Any, Optional
from MTG_bot import config

class DraftSimulator:
    """
    Simulates an MTG Draft (M21).
    - 8 Players
    - 3 Packs each
    - Pack structure: 1 Rare/Mythic, 3 Uncommons, 10 Commons, 1 Basic Land
    """
    def __init__(self, db_path: str = config.MTG_BOT_DB_PATH):
        self.db_path = db_path
        self.cards_by_rarity = self._load_cards_by_rarity()

    def _load_cards_by_rarity(self) -> Dict[str, List[int]]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        rarities = ["common", "uncommon", "rare", "mythic"]
        data = {r: [] for r in rarities}
        data["basic"] = []

        cursor.execute("SELECT card_id, rarity, supertypes FROM cards")
        for cid, rarity, supertypes_json in cursor.fetchall():
            supertypes = supertypes_json.lower()
            if "basic" in supertypes:
                data["basic"].append(cid)
            elif rarity in data:
                data[rarity].append(cid)
        
        conn.close()
        return data

    def generate_pack(self) -> List[int]:
        """Generates a standard 15-card pack."""
        pack = []
        
        # 1. Rare or Mythic (1/8 chance for mythic)
        if random.random() < 0.125 and self.cards_by_rarity["mythic"]:
            pack.append(random.choice(self.cards_by_rarity["mythic"]))
        else:
            pack.append(random.choice(self.cards_by_rarity["rare"]))
            
        # 2. Uncommons (3)
        pack.extend(random.sample(self.cards_by_rarity["uncommon"], 3))
        
        # 3. Commons (10)
        pack.extend(random.sample(self.cards_by_rarity["common"], 10))
        
        # 4. Basic Land (1)
        pack.append(random.choice(self.cards_by_rarity["basic"]))
        
        return pack

    def simulate_draft(self) -> List[List[int]]:
        """
        Simulates a full 8-player draft. 
        Returns 8 card pools (the cards each player drafted).
        Initially uses random selection for all players.
        """
        player_pools = [[] for _ in range(8)]
        
        for pack_num in range(3):
            packs = [self.generate_pack() for _ in range(8)]
            
            # 15 rounds of picking
            for pick_num in range(15):
                for i in range(8):
                    # In pack 1 and 3, pass left. In pack 2, pass right.
                    pack_index = (i + (pick_num if pack_num % 2 == 0 else -pick_num)) % 8
                    current_pack = packs[pack_index]
                    
                    if current_pack:
                        # Simple random pick for now
                        pick = random.choice(current_pack)
                        current_pack.remove(pick)
                        player_pools[i].append(pick)
                        
        return player_pools

    def build_deck(self, pool: List[int], target_size: int = 40) -> List[int]:
        """
        Simplistic deck building from a pool.
        1. Pick top 23 cards (non-lands).
        2. Fill rest with basic lands.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        playable_pool = []
        for cid in pool:
            cursor.execute("SELECT type FROM cards WHERE card_id = ?", (cid,))
            row = cursor.fetchone()
            if row and "Land" not in row[0]:
                playable_pool.append(cid)
        
        # Take top 23 non-lands
        deck = playable_pool[:23] if len(playable_pool) >= 23 else playable_pool
        print(f"DEBUG: Deck size before lands: {len(deck)}")
        
        # Add basic lands until target size
        while len(deck) < target_size:
            if self.cards_by_rarity["basic"]:
                land_pick = random.choice(self.cards_by_rarity["basic"])
                deck.append(land_pick)
            else:
                break
        
        print(f"DEBUG: Final deck size: {len(deck)}")
        conn.close()
        return deck
