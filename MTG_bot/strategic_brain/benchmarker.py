import os
import json
from typing import List, Dict, Any
from .environment import MTGEnv
from .student import Student
from MTG_bot.rule_engine import vocabulary as vocab

class Benchmarker:
    """
    Evaluates Student performance across standardized scenario levels.
    Supports Fractional Scoring (Reward Function Delta) and Concept Tagging.
    """
    def __init__(self, env: MTGEnv):
        self.env = env
        self.scenario_root = "MTG_bot/scenarios/M21"

    def run_level_evaluation(self, student: Student, level: int, current_format: str) -> Dict[str, Any]:
        level_dir = os.path.join(self.scenario_root, f"level_{level}")
        if not os.path.exists(level_dir):
            return {"error": f"Level {level} directory not found."}

        results = {"total_puzzles": 0, "total_score": 0.0, "scenarios": []}
        
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

                    # Fractional score (0.0 to 1.0)
                    score = self._evaluate_scenario(student, scenario)
                    results["total_puzzles"] += 1
                    results["total_score"] += score
                    results["scenarios"].append({
                        "name": scenario["name"], 
                        "score": score,
                        "concept": scenario.get("concept", "Generic")
                    })

        results["score"] = results["total_score"] / results["total_puzzles"] if results["total_puzzles"] > 0 else 0
        
        # Log specifically to WandB if available
        try:
            import wandb
            if wandb.run:
                wandb.log({f"puzzles/level_{level}_solve_rate": results["score"] * 100})
        except ImportError: pass

        return results

    def _evaluate_scenario(self, student: Student, scenario: Dict[str, Any]) -> float:
        """
        Runs a single scenario and returns a score (0.0 to 1.0) 
        reflecting proximity to the goal.
        """
        # 1. Setup
        self.env.reset(format="limited") 
        graph = self.env.graph
        p1_id = graph.players[0]
        p2_id = graph.players[1]
        p1 = graph.entities[p1_id]
        p2 = graph.entities[p2_id]
        
        setup = scenario["setup"]
        self._clear_all_zones(graph)
        
        # Set Life
        initial_p1_life = setup.get("p1_life", 20)
        initial_p2_life = setup.get("p2_life", 20)
        p1.properties['life_total'] = initial_p1_life
        p2.properties['life_total'] = initial_p2_life
        
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
            
        # Standard mana pool if not specific
        if "p1_mana" not in setup:
            p1.properties['mana_pool'] = {vocab.ID_MANA_RED: 10, vocab.ID_MANA_WHITE: 10, vocab.ID_MANA_BLUE: 10, vocab.ID_MANA_BLACK: 10, vocab.ID_MANA_GREEN: 10}
        
        # 2. Run
        done = False
        steps = 0
        best_score = 0.0
        obs = self.env._get_obs()
        
        while not done and steps < 5:
            # select_action returns (tokens, value, log_prob, memory, thoughts)
            action, _, _, _, _ = student.select_action(obs, deterministic=True)
            obs, _, done, _ = self.env.step(action)
            
            # Calculate current proximity to goal
            current_score = self._calculate_proximity(graph, scenario["goal"], initial_p1_life, initial_p2_life)
            best_score = max(best_score, current_score)
            
            if best_score >= 1.0: 
                return 1.0
            steps += 1
            
        return best_score

    def _clear_all_zones(self, graph):
        """Removes all card-zone relationships."""
        zone_rel = graph.id_mapper.get_id_by_name("Is In Zone", "game_vocabulary")
        graph.relationships = [r for r in graph.relationships if r.type_id != zone_rel]

    def _get_zone(self, graph, player, zone_type):
        return next(graph.entities[r.target] for r in graph.get_relationships(source=player, rel_type=vocab.ID_REL_CONTROLLED_BY) if graph.entities[r.target].type_id == zone_type)

    def _calculate_proximity(self, graph, goal_str: str, init_p1: int, init_p2: int) -> float:
        """Calculates 0.0 to 1.0 proximity to a goal string."""
        p1_id = graph.players[0]
        p2_id = graph.players[1]
        p1_life = graph.entities[p1_id].properties.get('life_total', 20)
        p2_life = graph.entities[p2_id].properties.get('life_total', 20)
        
        if "p2_life <= 0" in goal_str:
            if p2_life <= 0: return 1.0
            # Linear proximity based on damage dealt
            damage_dealt = max(0, init_p2 - p2_life)
            return min(0.95, damage_dealt / init_p2) if init_p2 > 0 else 0.0
            
        if "p1_life > 0" in goal_str:
            # Survival logic
            if p1_life <= 0: return 0.0
            return min(1.0, p1_life / init_p1) if init_p1 > 0 else 1.0
            
        if "p1_life >= 20" in goal_str:
            return min(1.0, p1_life / 20.0)
            
        return 0.0
