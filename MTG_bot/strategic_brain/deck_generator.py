import sqlite3
import random
import json
from typing import List, Dict, Any, Optional
from MTG_bot import config

class Archetypes:
    LIFE_GAIN = "life_gain"
    RAMP = "ramp"
    AGGRO = "aggro"
    CONTROL = "control"
    FLYING = "flying"
    BURN = "burn"
    STOMPY = "stompy"

class DeckGenerator:
    """
    Intelligent Deck Generator for the Teacher.
    Builds decks from the entire card pool based on archetypes.
    """
    def __init__(self, db_path: str = config.MTG_BOT_DB_PATH):
        self.db_path = db_path
        self.archetype_seeds = {
            Archetypes.LIFE_GAIN: ["Vito, Thorn of the Dusk Rose", "Revitalize", "Indulging Patrician"],
            Archetypes.RAMP: ["Azusa, Lost but Seeking", "Cultivate", "Llanowar Visionary"],
            Archetypes.AGGRO: ["Subira, Tulzidi Caravanner", "Shock", "Igneous Cur"],
            Archetypes.CONTROL: ["Barrin, Tolarian Archmage", "Cancel", "Opt"],
            Archetypes.FLYING: ["Mangara, the Diplomat", "Aven Gagglemaster", "Gale Swooper"],
            Archetypes.BURN: ["Chandra, Heart of Fire", "Shock", "Bonecrusher Giant"],
            Archetypes.STOMPY: ["Garruk, Unleashed", "Elder Gargaroth", "Colossal Dreadmaw"]
        }

    def generate_constructed_matchup(self, format_name: str = "Standard", archetypes: List[str] = None) -> List[List[int]]:
        """
        Generates two decks for a 1v1 matchup using the full card pool.
        """
        if not archetypes:
            archetypes = random.sample([Archetypes.LIFE_GAIN, Archetypes.RAMP, Archetypes.AGGRO, Archetypes.CONTROL, Archetypes.FLYING], 2)
        
        print(f"  [Teacher] Building Constructed Matchup: {archetypes[0]} vs {archetypes[1]} ({format_name})")
        
        deck_a = self.build_constructed_deck(archetypes[0], format_name)
        deck_b = self.build_constructed_deck(archetypes[1], format_name)
        
        return [deck_a, deck_b]

    def build_constructed_deck(self, archetype_or_colors: str, format_name: str) -> List[int]:
        """
        Builds a deck by selecting synergistic cards from the entire database.
        If archetype_or_colors is a list of characters (e.g. 'WR'), it uses those colors.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 1. Strict Format Enforcement
        if format_name == "Commander":
            deck_size = 100
            max_copies = 1
        elif format_name == "Limited":
            deck_size = 40
            max_copies = 99 # No limit in Limited
        else: # Standard
            deck_size = 60
            max_copies = 4
        
        # 2. Get Color Identity
        colors = set()
        seeds = []
        if archetype_or_colors in self.archetype_seeds:
            seeds = self.archetype_seeds[archetype_or_colors]
            for seed_name in seeds:
                cursor.execute("SELECT mana_cost FROM cards WHERE name = ?", (seed_name,))
                row = cursor.fetchone()
                if row and row[0]:
                    for c in "WUBRG":
                        if c in row[0]: colors.add(c)
        else:
            # Assume it's a color string like 'WRG' or 'random'
            if archetype_or_colors == "random":
                num_colors = random.randint(1, 3)
                colors = set(random.sample("WUBRG", num_colors))
            else:
                for c in archetype_or_colors.upper():
                    if c in "WUBRG": colors.add(c)
        
        if not colors: colors = {"W"} # Default to White
        
        # 3. Pull all playable cards in these colors
        pool = []
        color_query = " OR ".join([f"mana_cost LIKE '%{c}%'" for c in colors])
        # FOUNDATION PHASE: Filter out life-gain
        forbidden = "(text NOT LIKE '%gain life%' AND text NOT LIKE '%life total becomes%' AND text NOT LIKE '%lifelink%')"
        cursor.execute(f"SELECT card_id, name, type FROM cards WHERE (({color_query}) OR mana_cost = '') AND {forbidden}")
        for cid, cname, ctype in cursor.fetchall():
            if "Land" not in ctype:
                pool.append(cid)
        
        if not pool:
            # Fallback to any card if pool is empty
            cursor.execute("SELECT card_id FROM cards WHERE type NOT LIKE '%Land%' LIMIT 100")
            pool = [r[0] for r in cursor.fetchall()]

        # 4. Fill deck with synergistic cards
        deck = []
        # Add primary seed first (this will be our 'Commander' or key card)
        if seeds:
            cursor.execute("SELECT card_id FROM cards WHERE name = ?", (seeds[0],))
            rid = cursor.fetchone()
            if rid: deck.append(rid[0])
            
        # Add cards from pool to reach non-land count
        # Foundation Phase Fix: Strict 40% land / 60% non-land ratio
        non_land_target = int(deck_size * 0.6)
        # Safety for small pools
        actual_non_land_target = min(non_land_target, len(pool) * max_copies)
        
        while len(deck) < actual_non_land_target:
            card = random.choice(pool)
            if deck.count(card) < max_copies:
                deck.append(card)
        
        # 5. Fill with basic lands (FIXED: Exact land count)
        relevant_basics = self._get_basics_for_colors(list(colors))
        while len(deck) < deck_size:
            deck.append(random.choice(relevant_basics))
            
        conn.close()
        return deck

    def build_from_sequence(self, card_ids: List[int], format_name: str, land_ratio: Optional[float] = None) -> List[int]:
        """
        Builds a deck directly from a sequence provided by the Teacher.
        Ensures the deck is valid for the format (size, lands).
        """
        deck = card_ids.copy()
        
        if format_name == "Commander":
            target_size = 100
            default_land_target = 38
        elif format_name == "Limited":
            target_size = 40
            default_land_target = 17
        else:
            target_size = 60
            default_land_target = 24
            
        # Use provided land_ratio or the format default
        if land_ratio is not None:
            land_target = int(target_size * land_ratio)
        else:
            land_target = default_land_target

        # 1. Cap spells to respect land ratio
        spell_limit = target_size - land_target
        if len(deck) > spell_limit:
            deck = deck[:spell_limit]

        # 2. Fill remaining with basic lands
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        colors = set()
        for cid in deck:
            cursor.execute("SELECT mana_cost FROM cards WHERE card_id = ?", (cid,))
            row = cursor.fetchone()
            if row and row[0]:
                for c in "WUBRG":
                    if c in row[0]: colors.add(c)
        
        if not colors: colors = {"W"}
        basics = self._get_basics_for_colors(list(colors))
        
        # Add lands until we reach target size
        while len(deck) < target_size:
            deck.append(random.choice(basics))
            
        conn.close()
        random.shuffle(deck) # Shuffle the final deck
        return deck

    def _get_basics_for_colors(self, identity: List[str]) -> List[int]:
        mapping = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}
        target_names = [mapping[c] for c in identity if c in mapping]
        if not target_names: target_names = ["Plains"]
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        placeholders = ', '.join(['?'] * len(target_names))
        cursor.execute(f"SELECT card_id FROM cards WHERE name IN ({placeholders})", target_names)
        ids = [row[0] for row in cursor.fetchall()]
        conn.close()
        return ids
