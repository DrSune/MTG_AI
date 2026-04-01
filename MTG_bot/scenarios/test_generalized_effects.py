import sys
import os
import uuid
from typing import List

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from MTG_bot.rule_engine.game_graph import GameGraph, Entity
from MTG_bot.rule_engine.engine import Engine
from MTG_bot.rule_engine import game_initializer
from MTG_bot.rule_engine.card_database import card_data_loader
from MTG_bot.rule_engine.actions import CastSpellAction, PassPriorityAction
from MTG_bot.scenarios.scenario_runner import Scenario, ScenarioRunner

class SwiftResponseScenario(Scenario):
    def __init__(self):
        super().__init__("Swift Response Scenario", "Destroy a tapped creature using Swift Response.")

    def setup(self) -> Engine:
        swift_response_id = card_data_loader.get_card_id_by_name("Swift Response")
        mountain_id = card_data_loader.get_card_id_by_name("Mountain")
        colossification_id = card_data_loader.get_card_id_by_name("Colossification") # Just a big creature for P2
        
        # Initialize game
        graph = game_initializer.initialize_game_state(
            decklist1=[swift_response_id] + [mountain_id]*59,
            decklist2=[colossification_id]*60,
            game_mode="Standard",
            player1_starting_hand_ids=[swift_response_id]
        )
        
        p1 = graph.entities[graph.players[0]]
        p2 = graph.entities[graph.players[1]]
        
        # Give P1 enough mana
        white_mana_id = self.id_mapper.get_id_by_name("White Mana", "game_vocabulary")
        p1.properties['mana_pool'][white_mana_id] = 2
        
        # Put a creature on P2's battlefield and TAP it
        battlefield_rels = graph.get_relationships(source=p2, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
        battlefield_zone = next(graph.entities[r.target] for r in battlefield_rels if graph.entities[r.target].type_id == self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary"))
        
        creature_id = card_data_loader.get_card_id_by_name("Alpine Watchdog")
        creature = graph.add_entity(creature_id)
        graph.add_relationship(creature, p2, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
        graph._move_card_to_zone(creature, battlefield_zone)
        creature.properties['tapped'] = True # TAP IT
        creature.properties['name'] = "Tapped Dog"
        
        return Engine(graph)

    def is_successful(self, engine: Engine) -> bool:
        # Success if "Tapped Dog" is in graveyard
        for entity in engine.graph.entities.values():
            if entity.properties.get('name') == "Tapped Dog":
                # Check if it's in a graveyard zone
                is_in_zone_rels = engine.graph.get_relationships(source=entity, rel_type=self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))
                for rel in is_in_zone_rels:
                    zone = engine.graph.entities[rel.target]
                    if zone.type_id == self.id_mapper.get_id_by_name("Graveyard", "game_vocabulary"):
                        return True
        return False

if __name__ == "__main__":
    runner = ScenarioRunner()
    runner.register(SwiftResponseScenario())
    
    def swift_response_agent(engine, moves):
        for move in moves:
            if isinstance(move, CastSpellAction):
                return move
        return moves[0]
        
    runner.run_all(agent_fn=swift_response_agent)
