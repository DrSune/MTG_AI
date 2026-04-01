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
from MTG_bot.rule_engine.actions import CastSpellAction, PassPriorityAction, PassTurnAction, PlayLandAction, ActivateManaAbilityAction
from MTG_bot.scenarios.scenario_runner import Scenario, ScenarioRunner

class StaticPTBuffScenario(Scenario):
    def __init__(self):
        super().__init__("Static P/T Buff", "Verify that a static effect (Glorious Anthem) applies correctly while on battlefield.")

    def setup(self) -> Engine:
        mountain_id = card_data_loader.get_card_id_by_name("Mountain")
        graph = game_initializer.initialize_game_state(
            decklist1=[mountain_id]*60,
            decklist2=[mountain_id]*60,
            game_mode="Standard"
        )
        
        p1 = graph.entities[graph.players[0]]
        battlefield_zone_id = self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary")
        p1_battlefield = next(graph.entities[r.target] for r in graph.get_relationships(source=p1, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if graph.entities[r.target].type_id == battlefield_zone_id)
        
        # P1 Creature
        creature = graph.add_entity(card_data_loader.get_card_id_by_name("Alpine Watchdog"))
        graph.add_relationship(creature, p1, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
        graph._move_card_to_zone(creature, p1_battlefield)
        creature.properties['name'] = "My Dog"
        creature.properties['power'] = 2
        creature.properties['toughness'] = 2
        
        # Anthem (we'll mock it with a basic permanent)
        anthem = graph.add_entity(mountain_id) # Using mountain as base but will change properties
        graph.add_relationship(anthem, p1, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
        graph._move_card_to_zone(anthem, p1_battlefield)
        anthem.properties['name'] = "Glorious Anthem"
        anthem.properties['effects'] = [{
            "ability_type": "continuous_effect",
            "effect": {"type": "stat_modifier", "power": 1, "toughness": 1},
            "layer": 7,
            "target_filter": {"type": "creature", "controller": "self"}
        }]
        
        engine = Engine(graph)
        # Force a layer application
        engine.layer_system.apply_all_layers(graph)
        return engine

    def is_successful(self, engine: Engine) -> bool:
        dog = next((e for e in engine.graph.entities.values() if e.properties.get('name') == "My Dog"), None)
        anthem = next((e for e in engine.graph.entities.values() if e.properties.get('name') == "Glorious Anthem"), None)
        
        if not dog or not anthem: return False

        # Step 1: Dog should be 3/3 due to anthem
        if dog.properties.get('effective_power') != 3:
            print(f"FAILED: Initial power is {dog.properties.get('effective_power')}, expected 3")
            return False
        
        # Step 2: Move anthem to graveyard
        p1 = engine.graph.entities[engine.graph.players[0]]
        graveyard_zone = next(engine.graph.entities[r.target] for r in engine.graph.get_relationships(source=p1, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if engine.graph.entities[r.target].type_id == self.id_mapper.get_id_by_name("Graveyard", "game_vocabulary"))
        engine.graph._move_card_to_zone(anthem, graveyard_zone)
        
        # Step 3: Recalculate layers
        engine.layer_system.apply_all_layers(engine.graph)
        
        # Step 4: Dog should be 2/2 again
        if dog.properties.get('effective_power') != 2:
            print(f"FAILED: After-removal power is {dog.properties.get('effective_power')}, expected 2")
            return False
            
        return True

if __name__ == "__main__":
    runner = ScenarioRunner()
    runner.register(StaticPTBuffScenario())
    runner.run_all(agent_fn=lambda e, m: m[0])
