import sys
import os
import uuid
import json
from typing import List, Dict, Any, Callable, Optional

# Add the project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from MTG_bot.rule_engine.game_graph import GameGraph, Entity
from MTG_bot.rule_engine.engine import Engine
from MTG_bot.rule_engine import game_initializer
from MTG_bot.rule_engine.card_database import card_data_loader
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot.rule_engine.actions import CastSpellAction, PassPriorityAction, PlayLandAction, ActivateManaAbilityAction, PassTurnAction, DeclareAttackerAction
from MTG_bot import config

# Force reload card_data_loader to ensure basic land abilities are parsed
from MTG_bot.rule_engine import card_database
card_database.card_data_loader = card_database.CardDataLoader()

class Scenario:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)

    def setup(self) -> Engine:
        """Initializes the game state for the scenario."""
        raise NotImplementedError

    def is_successful(self, engine: Engine) -> bool:
        """Checks if the scenario's goal was achieved."""
        raise NotImplementedError

class JSONScenario(Scenario):
    """Loads a scenario from a JSON definition."""
    def __init__(self, json_path: str):
        with open(json_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        super().__init__(self.data['name'], self.data['description'])

    def setup(self) -> Engine:
        setup_data = self.data['setup']
        p1_hand = setup_data.get('p1_hand', [])
        p1_battlefield_lands = setup_data.get('p1_battlefield_lands', [])
        p1_battlefield_creatures = setup_data.get('p1_battlefield_creatures', [])
        p2_life = setup_data.get('p2_life', 20)
        
        # Use Mountains as filler
        mountain_id = card_data_loader.get_card_id_by_name("Mountain")
        
        graph = game_initializer.initialize_game_state(
            decklist1=p1_hand + [mountain_id]*(60-len(p1_hand)),
            decklist2=[mountain_id]*60,
            game_mode="Standard",
            player1_starting_hand_ids=p1_hand
        )
        
        p1 = graph.entities[graph.players[0]]
        p2 = graph.entities[graph.players[1]]
        p2.properties['life_total'] = p2_life
        
        # Add lands to P1 battlefield
        battlefield_rels = graph.get_relationships(source=p1, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
        battlefield_zone = next(graph.entities[r.target] for r in battlefield_rels if graph.entities[r.target].type_id == self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary"))
        
        for land_id in p1_battlefield_lands:
            land = graph.add_entity(land_id)
            graph.add_relationship(land, p1, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
            graph._move_card_to_zone(land, battlefield_zone)
            
        # Add creatures to P1 battlefield
        for creature_id in p1_battlefield_creatures:
            creature = graph.add_entity(creature_id)
            graph.add_relationship(creature, p1, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
            graph._move_card_to_zone(creature, battlefield_zone)
            # Ensure it's not summoning sick
            creature.properties['turn_entered'] = graph.turn_number - 1
            creature.properties['has_summoning_sickness'] = False
        
        engine = Engine(graph)
        # PROGRESS TO MAIN PHASE
        main_phase_id = self.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary")
        while engine.graph.phase != main_phase_id:
            engine.progress_phase_and_step()
            
        return engine

    def is_successful(self, engine: Engine) -> bool:
        goal_expr = self.data.get('goal')
        if goal_expr == "p2_life <= 0":
            p2 = engine.graph.entities[engine.graph.players[1]]
            return p2.properties['life_total'] <= 0
        return False

class ScenarioRunner:
    def __init__(self):
        self.scenarios: List[Scenario] = []

    def register(self, scenario: Scenario):
        self.scenarios.append(scenario)

    def run_all(self, agent_fn: Optional[Callable] = None):
        results = []
        for scenario in self.scenarios:
            success = self.run_scenario(scenario, agent_fn)
            results.append((scenario.name, success))
        
        print("\n" + "="*30)
        print("SCENARIO RESULTS")
        print("="*30)
        passed = 0
        for name, success in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{name}: {status}")
            if success:
                passed += 1
        print(f"\nTotal: {passed}/{len(self.scenarios)} passed.")

    def run_scenario(self, scenario: Scenario, agent_fn: Optional[Callable] = None, max_steps: int = 25) -> bool:
        print(f"\nRunning Scenario: {scenario.name}")
        print(f"Description: {scenario.description}")
        
        engine = scenario.setup()
        
        # If no agent provided, use a simple heuristic
        if agent_fn is None:
            def simple_agent(engine, moves):
                p2_id = engine.graph.players[1]
                
                # 1. Attack if possible
                for move in moves:
                    if isinstance(move, DeclareAttackerAction):
                        return move

                # 2. Play Land if possible
                for move in moves:
                    if isinstance(move, PlayLandAction):
                        return move
                
                # 3. Cast the spell if possible
                for move in moves:
                    if isinstance(move, CastSpellAction):
                        # Prioritize targeting opponent
                        if hasattr(move, 'target_id') and move.target_id == p2_id:
                            return move
                
                for move in moves:
                    if isinstance(move, CastSpellAction):
                        return move
                
                # 4. Activate mana abilities if available
                for move in moves:
                    if isinstance(move, ActivateManaAbilityAction):
                        return move

                # 5. Default to PassPriorityAction
                for move in moves:
                    if isinstance(move, PassPriorityAction):
                        return move
                return moves[0]
            agent_fn = simple_agent

        for step in range(max_steps):
            legal_moves = engine.get_legal_moves()
            if not legal_moves:
                print(f"No legal moves available at step {step}.")
                break
                
            chosen_move = agent_fn(engine, legal_moves)
            print(f"Step {step+1}: Agent chose {chosen_move}")
            
            engine.execute_move(chosen_move)
            
            # Check success after each move
            if scenario.is_successful(engine):
                print(f"Scenario SUCCESS at step {step+1}!")
                return True
            
        return False

# --- Specific Scenarios ---

class LethalWithShock(Scenario):
    def __init__(self):
        super().__init__("Lethal with Shock", "Opponent at 2 life. Player has Shock in hand and mana available.")

    def setup(self) -> Engine:
        shock_id = card_data_loader.get_card_id_by_name("Shock")
        mountain_id = card_data_loader.get_card_id_by_name("Mountain")
        
        graph = game_initializer.initialize_game_state(
            decklist1=[shock_id] + [mountain_id]*59, 
            decklist2=[mountain_id]*60,
            game_mode="Standard",
            player1_starting_hand_ids=[shock_id]
        )
        
        p1 = graph.entities[graph.players[0]]
        p2 = graph.entities[graph.players[1]]
        p2.properties['life_total'] = 2
        
        red_mana_id = self.id_mapper.get_id_by_name("Red Mana", "game_vocabulary")
        p1.properties['mana_pool'][red_mana_id] = 1
        
        engine = Engine(graph)
        main_phase_id = self.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary")
        while engine.graph.phase != main_phase_id:
            engine.progress_phase_and_step()
            
        return engine

    def is_successful(self, engine: Engine) -> bool:
        p2_id = engine.graph.players[1]
        p2 = engine.graph.entities[p2_id]
        return p2.properties['life_total'] <= 0

class PlayLandAndCast(Scenario):
    def __init__(self):
        super().__init__("Play Land and Cast", "Player has 4 Forests in play, 1 Forest in hand, and a Garruk's Gorehorn (4G) in hand. Must play land, tap all 5, and cast.")

    def setup(self) -> Engine:
        forest_id = card_data_loader.get_card_id_by_name("Forest")
        gorehorn_id = card_data_loader.get_card_id_by_name("Garruk's Gorehorn")
        
        graph = game_initializer.initialize_game_state(
            decklist1=[forest_id]*30 + [gorehorn_id]*30,
            decklist2=[forest_id]*60,
            game_mode="Standard",
            player1_starting_hand_ids=[forest_id, gorehorn_id]
        )
        
        p1 = graph.entities[graph.players[0]]
        battlefield_rels = graph.get_relationships(source=p1, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
        battlefield_zone = next(graph.entities[r.target] for r in battlefield_rels if graph.entities[r.target].type_id == self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary"))
        
        for _ in range(4):
            existing_forest = graph.add_entity(forest_id)
            graph.add_relationship(existing_forest, p1, self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
            graph._move_card_to_zone(existing_forest, battlefield_zone)
        
        engine = Engine(graph)
        main_phase_id = self.id_mapper.get_id_by_name("Pre-Combat Main Phase", "game_vocabulary")
        while engine.graph.phase != main_phase_id:
            engine.progress_phase_and_step()
            
        return engine

    def is_successful(self, engine: Engine) -> bool:
        p1 = engine.graph.entities[engine.graph.players[0]]
        battlefield_rels = engine.graph.get_relationships(source=p1, rel_type=self.id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
        battlefield_zone = next(engine.graph.entities[r.target] for r in battlefield_rels if engine.graph.entities[r.target].type_id == self.id_mapper.get_id_by_name("Battlefield", "game_vocabulary"))
        cards_on_battlefield = [engine.graph.entities[r.source] for r in engine.graph.get_relationships(target=battlefield_zone, rel_type=self.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))]
        gorehorn_id = card_data_loader.get_card_id_by_name("Garruk's Gorehorn")
        return any(c.type_id == gorehorn_id for c in cards_on_battlefield)

if __name__ == "__main__":
    runner = ScenarioRunner()
    runner.register(LethalWithShock())
    runner.register(PlayLandAndCast())
    lethal_dir = os.path.join(os.path.dirname(__file__), "M21", "level_1", "lethal")
    if os.path.exists(lethal_dir):
        for filename in os.listdir(lethal_dir):
            if filename.endswith(".json"):
                runner.register(JSONScenario(os.path.join(lethal_dir, filename)))
    runner.run_all()
