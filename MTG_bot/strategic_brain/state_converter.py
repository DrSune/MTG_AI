from typing import List, Dict, Any, Optional
import numpy as np
import uuid

from ..rule_engine.game_graph import GameGraph, Entity
from ..rule_engine import vocabulary as vocab

try:
    import torch
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

class StateConverter:
    """
    Converts the GameGraph into numerical observations and token sequences.
    Ensures high-priority spatial tokens (Zones) are always included.
    """
    def __init__(self):
        self.observation_size = 64 
        self.feature_dim = 32 
        self.max_tokens = 500 # Increased for Pro-Scale
        
        self.keyword_map = {
            "flying": 0, "haste": 1, "indestructible": 2, "hexproof": 3,
            "lifelink": 4, "deathtouch": 5, "trample": 6, "vigilance": 7,
            "unblockable": 8, "protection_from_name": 9
        }

    def convert_graph_to_tokens(self, graph: GameGraph, engine_stack: List[Any] = None) -> Dict[str, Any]:
        """
        Converts the GameGraph into numeric arrays/tensors.
        Token order: [Zones, Players, Stack, Cards...]
        """
        active_player_id = graph.active_player_id
        
        # 1. Identify Priority Entities (Zones and Players)
        priority_entities = []
        for eid, entity in graph.entities.items():
            if entity.type_id in [vocab.ID_PLAYER, vocab.ID_ZONE_BATTLEFIELD, vocab.ID_ZONE_HAND, vocab.ID_ZONE_GRAVEYARD, vocab.ID_ZONE_LIBRARY]:
                priority_entities.append(entity)
        
        # 2. Identify Cards and other entities
        other_entities = [e for e in graph.entities.values() if e not in priority_entities]
        
        # 3. Stack items
        stack_items = engine_stack if engine_stack else []
        
        # Combine in priority order
        all_tokens_list = priority_entities + stack_items + other_entities
        total_tokens = min(len(all_tokens_list), self.max_tokens)
        
        atomic_ids = np.zeros(total_tokens, dtype=np.int64)
        features = np.zeros((total_tokens, self.feature_dim), dtype=np.float32)
        zone_ids = np.zeros(total_tokens, dtype=np.int64)
        controller_ids = np.zeros(total_tokens, dtype=np.int64)

        for i in range(total_tokens):
            item = all_tokens_list[i]
            
            if isinstance(item, Entity):
                atomic_ids[i] = item.type_id
                c_id = graph.get_controller_id(item)
                if c_id == active_player_id: controller_ids[i] = 1
                elif c_id is not None: controller_ids[i] = 2
                
                zone_ids[i] = self._get_zone_type_id(graph, item)
                features[i] = self._extract_features(item)
            else:
                # Stack Item
                source = graph.entities.get(item.source_id)
                atomic_ids[i] = source.type_id if source else 0
                controller_ids[i] = 1 if item.controller_id == active_player_id else 2
                zone_ids[i] = 999 
                features[i, 15] = 1.0

        res = {"atomic_ids": atomic_ids, "component_features": features, "zone_ids": zone_ids, "controller_ids": controller_ids}
        return res

    def _get_zone_type_id(self, graph: GameGraph, entity: Entity) -> int:
        if entity.properties.get('is_on_battlefield'): return vocab.ID_ZONE_BATTLEFIELD
        if entity.properties.get('is_in_hand'): return vocab.ID_ZONE_HAND
        if entity.properties.get('is_in_graveyard'): return vocab.ID_ZONE_GRAVEYARD
        return 0

    def _extract_features(self, entity: Entity) -> np.ndarray:
        feats = np.zeros(self.feature_dim, dtype=np.float32)
        props = entity.properties
        
        def safe_float(val):
            if val is None: return 0.0
            if isinstance(val, (int, float)): return float(val)
            s = str(val).strip()
            if not s or s in ["*", "X"]: return 0.0
            try:
                import re
                match = re.match(r"(\d+)", s)
                return float(match.group(1)) if match else 0.0
            except: return 0.0

        feats[0] = safe_float(props.get('effective_power') or props.get('power'))
        feats[1] = safe_float(props.get('effective_toughness') or props.get('toughness'))
        feats[2] = safe_float(props.get('cmc'))
        feats[3] = 1.0 if props.get('tapped') else 0.0
        feats[4] = 1.0 if props.get('has_summoning_sickness') else 0.0
        feats[5] = 1.0 if props.get('is_creature') else 0.0
        feats[6] = 1.0 if props.get('is_land') else 0.0
        feats[7] = 1.0 if props.get('is_attacking') else 0.0
        feats[8] = 1.0 if props.get('is_blocking') else 0.0
        
        # New Zone Features (Help model distinguish hand vs battlefield)
        feats[12] = 1.0 if props.get('is_on_battlefield') else 0.0
        feats[13] = 1.0 if props.get('is_in_hand') else 0.0
        feats[14] = 1.0 if props.get('is_in_graveyard') else 0.0
        
        if 'life_total' in props: feats[9] = float(props.get('life_total') or 20) / 20.0
        if 'mana_pool' in props: feats[10] = float(sum((props['mana_pool'] or {}).values()))
        for kw, bit in self.keyword_map.items():
            if props.get(kw): feats[11] += (2 ** bit)
        return feats

    def convert_graph_to_observation(self, graph: GameGraph) -> np.ndarray:
        obs = np.zeros(self.observation_size, dtype=np.float32)
        obs[0] = float(graph.phase); obs[1] = float(graph.step); obs[2] = float(graph.turn_number)
        ap_id = graph.active_player_id
        ap = graph.entities.get(ap_id)
        if ap:
            obs[3] = float(ap.properties.get('life_total', 20)) / 20.0
            mana_pool = ap.properties.get('mana_pool', {})
            obs[4] = float(sum(mana_pool.values())) / 10.0
            
            # --- POTENTIAL MANA (Deep Analysis Fix) ---
            # Calculate how much mana is available if all untapped lands are used
            potential_mana = 0
            # Get all lands controlled by active player on battlefield
            for eid, e in graph.entities.items():
                if e.properties.get('is_land') and e.properties.get('is_on_battlefield') and not e.properties.get('tapped'):
                    # Check controller
                    if graph.get_controller_id(e) == ap_id:
                        potential_mana += 1 # Simplified: assume each land gives 1
            obs[5] = float(potential_mana) / 10.0

        opp_id = next((pid for pid in graph.players if pid != graph.active_player_id), None)
        opp = graph.entities.get(opp_id) if opp_id else None
        if opp: obs[6] = float(opp.properties.get('life_total', 20)) / 20.0
        return obs
