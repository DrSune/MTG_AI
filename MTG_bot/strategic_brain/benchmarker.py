import os
import json
from typing import List, Dict, Any
from .environment import MTGEnv
from .student import Student
from MTG_bot.rule_engine import vocabulary as vocab

class Benchmarker:
    """
    Evaluates Student performance across standardized scenario levels.
    """
    def __init__(self, env: MTGEnv):
        self.env = env
        self.scenario_root = "MTG_bot/scenarios/M21"

    def run_level_evaluation(self, student: Student, level: int, current_format: str) -> Dict[str, Any]:
        level_dir = os.path.join(self.scenario_root, f"level_{level}")
        if not os.path.exists(level_dir):
            return {"error": f"Level {level} directory not found."}

        results = {"total": 0, "passed": 0, "scenarios": []}
        
        for root, _, files in os.walk(level_dir):
            for file in files:
                if file.endswith(".json"):
                    scenario_path = os.path.join(root, file)
                    with open(scenario_path, "r") as f:
                        scenario = json.load(f)
                    
                    # --- FORMAT FILTERING ---
                    supported = scenario.get("supported_formats", ["Limited", "Commander", "Standard"])
                    if current_format not in supported:
                        continue

                    passed = self._evaluate_scenario(student, scenario)
                    results["total"] += 1
                    if passed: results["passed"] += 1
                    results["scenarios"].append({"name": scenario["name"], "passed": passed})

        results["score"] = results["passed"] / results["total"] if results["total"] > 0 else 0
        
        # Log specifically to WandB if available
        try:
            import wandb
            if wandb.run:
                wandb.log({f"puzzles/level_{level}_solve_rate": results["score"] * 100})
        except ImportError: pass

        return results

    def _evaluate_scenario(self, student: Student, scenario: Dict[str, Any]) -> bool:
        """Runs a single scenario and checks if the goal was reached."""
        # 1. Setup
        # We pass empty archetypes but standard reset logic expects deck generation.
        # However, Benchmarker overrides everything anyway.
        self.env.reset(format="limited") 
        graph = self.env.graph
        p1_id = graph.players[0]
        p2_id = graph.players[1]
        p1 = graph.entities[p1_id]
        p2 = graph.entities[p2_id]
        
        setup = scenario["setup"]
        
        # Clear existing zones for clean test
        self._clear_all_zones(graph)
        
        # Set Life
        p1.properties['life_total'] = setup.get("p1_life", 20)
        p2.properties['life_total'] = setup.get("p2_life", 20)
        
        # Setup P1 Hand
        hand_zone_p1 = self._get_zone(graph, p1, vocab.ID_ZONE_HAND)
        for card_id in setup.get("p1_hand", []):
            card = graph.add_entity(card_id)
            graph.add_relationship(card, p1, vocab.ID_REL_CONTROLLED_BY)
            graph._move_card_to_zone(card, hand_zone_p1)
            
        # Setup P1 Battlefield
        bf_zone_p1 = self._get_zone(graph, p1, vocab.ID_ZONE_BATTLEFIELD)
        for card_id in setup.get("p1_battlefield_creatures", []):
            card = graph.add_entity(card_id)
            card.properties['is_creature'] = True
            graph.add_relationship(card, p1, vocab.ID_REL_CONTROLLED_BY)
            graph._move_card_to_zone(card, bf_zone_p1)
            
        # Give P1 infinite mana if not specified (to test ability/spell logic)
        if "p1_mana" not in setup:
            p1.properties['mana_pool'] = {vocab.ID_MANA_RED: 10, vocab.ID_MANA_WHITE: 10, vocab.ID_MANA_BLUE: 10, vocab.ID_MANA_BLACK: 10, vocab.ID_MANA_GREEN: 10}
        
        # 2. Run
        done = False
        steps = 0
        obs = self.env._get_obs()
        while not done and steps < 5:
            # select_action returns (tokens, value, log_prob, memory, thoughts)
            action, _, _, _, _ = student.select_action(obs, deterministic=True)
            obs, _, done, _ = self.env.step(action)
            if self._check_goal(graph, scenario["goal"]): return True
            steps += 1
        return False

    def _clear_all_zones(self, graph):
        """Removes all card-zone relationships."""
        zone_rel = graph.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary")
        graph.relationships = [r for r in graph.relationships if r.type_id != zone_rel]

    def _get_zone(self, graph, player, zone_type):
        return next(graph.entities[r.target] for r in graph.get_relationships(source=player, rel_type=vocab.ID_REL_CONTROLLED_BY) if graph.entities[r.target].type_id == zone_type)

    def _check_goal(self, graph, goal_str: str) -> bool:
        """Robust goal checker for generalized puzzles."""
        p1_id = graph.players[0]
        p2_id = graph.players[1]
        p1_life = graph.entities[p1_id].properties.get('life_total', 20)
        p2_life = graph.entities[p2_id].properties.get('life_total', 20)
        
        if "p2_life <= 0" in goal_str:
            return p2_life <= 0
        if "p1_life > 0" in goal_str:
            # This is usually for survival tests after combat resolves
            return p1_life > 0
        if "p1_life >= 20" in goal_str:
            return p1_life >= 20
            
        return False
