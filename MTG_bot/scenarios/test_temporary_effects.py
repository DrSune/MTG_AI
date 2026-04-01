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

class TemporaryPTBuffScenario(Scenario):
    def __init__(self):
        super().__init__("Temporary P/T Buff", "Verify that Daybreak Charger's buff (+2/+0) lasts until end of turn and then expires.")
        self.state = "initial" # initial -> buffed -> expired

    def setup(self) -> Engine:
        charger_id = card_data_loader.get_card_id_by_name("Daybreak Charger")
        mountain_id = card_data_loader.get_card_id_by_name("Mountain")
        
        graph = game_initializer.initialize_game_state(
            decklist1=[charger_id] + [mountain_id]*59,
            decklist2=[mountain_id]*60,
            game_mode="Standard",
            player1_starting_hand_ids=[charger_id]
        )
        
        p1 = graph.entities[graph.players[0]]
        white_id = self.id_mapper.get_id_by_name("White Mana", "game_vocabulary")
        p1.properties['mana_pool'][white_id] = 2
        
        creature = graph.add_entity(card_data_loader.get_card_id_by_name("Alpine Watchdog"))
        graph.add_relationship(creature, p1, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
        battlefield_zone_id = self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary")
        p1_battlefield = next(graph.entities[r.target] for r in graph.get_relationships(source=p1, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if graph.entities[r.target].type_id == battlefield_zone_id)
        graph._move_card_to_zone(creature, p1_battlefield)
        creature.properties['name'] = "Target Dog"
        creature.properties['power'] = 2
        creature.properties['effective_power'] = 2
        
        hand_zone = next(graph.entities[r.target] for r in graph.get_relationships(source=p1, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if graph.entities[r.target].type_id == self.id_mapper.get_id_by_name("Hand", "game_vocabulary"))
        card_in_hand = [graph.entities[r.source] for r in graph.get_relationships(target=hand_zone, rel_type=self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary")) if graph.entities[r.source].type_id == charger_id][0]
        
        card_in_hand.properties['effects'] = [{
            "ability_type": "temporary_stat_modifier",
            "effect": {"type": "stat_modifier", "power": 2, "toughness": 0},
            "duration": "until_end_of_turn",
            "target": {"type": "creature"}
        }]
        
        engine = Engine(graph)
        main_id = self.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary")
        while engine.graph.phase != main_id:
            engine.progress_phase_and_step()
        return engine

    def is_successful(self, engine: Engine) -> bool:
        dog = next((e for e in engine.graph.entities.values() if e.properties.get('name') == "Target Dog"), None)
        if not dog: return False

        if self.state == "initial":
            if dog.properties.get('effective_power') == 4:
                print("DEBUG: State changed to BUFFED")
                self.state = "buffed"
        
        elif self.state == "buffed":
            if engine.graph.turn_number > 1:
                if dog.properties.get('effective_power') == 2:
                    print("DEBUG: State changed to EXPIRED")
                    self.state = "expired"
                    return True
        
        return False

def charger_agent(engine, moves):
    # 1. Cast the buff if possible
    for m in moves:
        if isinstance(m, CastSpellAction):
            return m
    
    # 2. Play land/Taps
    for m in moves:
        if isinstance(m, (PlayLandAction, ActivateManaAbilityAction)):
            return m
            
    # 3. Pass everything else
    for m in moves:
        if isinstance(m, (PassPriorityAction, PassTurnAction)):
            return m
    return moves[0]

if __name__ == "__main__":
    runner = ScenarioRunner()
    runner.register(TemporaryPTBuffScenario())
    runner.run_all(agent_fn=charger_agent)
