import sys
import os
import uuid
import json
from typing import List

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from MTG_bot.rule_engine.game_graph import GameGraph, Entity
from MTG_bot.rule_engine.engine import Engine
from MTG_bot.rule_engine import game_initializer
from MTG_bot.rule_engine.card_database import card_data_loader
from MTG_bot.rule_engine.actions import CastSpellAction, PassPriorityAction
from MTG_bot.scenarios.scenario_runner import Scenario, ScenarioRunner

class OpponentCreatureOnlyScenario(Scenario):
    def __init__(self):
        super().__init__("Opponent Creature Only", "Testing a custom spell that can only target opponent's creatures.")

    def setup(self) -> Engine:
        # We'll 'mock' a card with a complex target filter
        # Target: {'type': 'creature', 'controller': 'opponent'}
        swift_id = card_data_loader.get_card_id_by_name("Swift Response")
        mountain_id = card_data_loader.get_card_id_by_name("Mountain")
        
        graph = game_initializer.initialize_game_state(
            decklist1=[swift_id] + [mountain_id]*59,
            decklist2=[mountain_id]*60,
            game_mode="Standard",
            player1_starting_hand_ids=[swift_id]
        )
        
        p1 = graph.entities[graph.players[0]]
        p2 = graph.entities[graph.players[1]]
        
        # Give P1 mana
        white_id = self.id_mapper.get_id_by_name("White Mana", "game_vocabulary")
        p1.properties['mana_pool'][white_id] = 2
        
        battlefield_zone_id = self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary")
        
        # P1 Creature
        p1_creature = graph.add_entity(card_data_loader.get_card_id_by_name("Alpine Watchdog"))
        graph.add_relationship(p1_creature, p1, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
        p1_battlefield = next(graph.entities[r.target] for r in graph.get_relationships(source=p1, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if graph.entities[r.target].type_id == battlefield_zone_id)
        graph._move_card_to_zone(p1_creature, p1_battlefield)
        p1_creature.properties['name'] = "My Dog"
        
        # P2 Creature
        p2_creature = graph.add_entity(card_data_loader.get_card_id_by_name("Alpine Watchdog"))
        graph.add_relationship(p2_creature, p2, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
        p2_battlefield = next(graph.entities[r.target] for r in graph.get_relationships(source=p2, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if graph.entities[r.target].type_id == battlefield_zone_id)
        graph._move_card_to_zone(p2_creature, p2_battlefield)
        p2_creature.properties['name'] = "Opponent Dog"
        
        # Modify the spell in hand to have the restrictive filter
        hand_zone = next(graph.entities[r.target] for r in graph.get_relationships(source=p1, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if graph.entities[r.target].type_id == self.id_mapper.get_id_by_name("Hand", "game_vocabulary"))
        spell_in_hand = [graph.entities[r.source] for r in graph.get_relationships(target=hand_zone, rel_type=self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary")) if graph.entities[r.source].type_id == swift_id][0]
        
        spell_in_hand.properties['effects'] = [{
            "ability_type": "destroy",
            "target": {"type": "creature", "controller": "opponent"}
        }]
        
        engine = Engine(graph)
        main_id = self.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary")
        while engine.graph.phase != main_id:
            engine.progress_phase_and_step()
        return engine

    def is_successful(self, engine: Engine) -> bool:
        # Check legal moves
        moves = engine.get_legal_moves()
        cast_moves = [m for m in moves if isinstance(m, CastSpellAction) and hasattr(m, 'target_id')]
        
        # Should only be able to target Opponent Dog
        target_names = []
        for m in cast_moves:
            target = engine.graph.entities[m.target_id]
            target_names.append(target.properties.get('name'))
            
        print(f"DEBUG: Potential targets: {target_names}")
        
        if "Opponent Dog" in target_names and "My Dog" not in target_names:
            return True
        return False

if __name__ == "__main__":
    runner = ScenarioRunner()
    runner.register(OpponentCreatureOnlyScenario())
    runner.run_all(agent_fn=lambda e, m: m[0]) # Agent doesn't matter, we check success in is_successful
