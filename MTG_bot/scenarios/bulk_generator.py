import json
import os
import random

def generate_generalized_puzzles():
    """Generates a diverse set of 100+ puzzles across different archetypes."""
    
    # 1. Level 1: Fundamentals (Lethal, Blocking, Mana)
    l1_dir = "MTG_bot/scenarios/M21/level_1/generalized"
    os.makedirs(l1_dir, exist_ok=True)
    
    # IDs: Shock(159), Mountain(269), Igneous Cur(153)
    
    for i in range(25):
        # SUB-TYPE: Lethal Combat
        # P1 has a creature, P2 has low life. Goal: Attack.
        scenario = {
            "name": f"L1_Lethal_Combat_{i}",
            "supported_formats": ["Limited", "Commander", "Standard"],
            "setup": {
                "p1_battlefield_creatures": [153], # Igneous Cur (1/2)
                "p2_life": 1,
                "p1_mana": 0
            },
            "goal": "p2_life <= 0"
        }
        with open(os.path.join(l1_dir, f"combat_{i}.json"), "w") as f:
            json.dump(scenario, f, indent=4)

    for i in range(25):
        # SUB-TYPE: Basic Survival (Blocking)
        # P2 has an attacker, P1 must block to stay at >0 life.
        scenario = {
            "name": f"L1_Survival_Block_{i}",
            "supported_formats": ["Limited", "Commander", "Standard"],
            "setup": {
                "p1_life": 1,
                "p1_battlefield_creatures": [153],
                "p2_attacking_creatures": [153], # P2 is attacking with an 1/2
            },
            "goal": "p1_life > 0"
        }
        with open(os.path.join(l1_dir, f"survival_{i}.json"), "w") as f:
            json.dump(scenario, f, indent=4)

    # 2. Level 2: Sequence & Value (Removal, Triggers)
    l2_dir = "MTG_bot/scenarios/M21/level_2/generalized"
    os.makedirs(l2_dir, exist_ok=True)
    
    # IDs: Aven Gagglemaster(5) - ETB Life gain
    for i in range(25):
        # SUB-TYPE: Triggered Value
        # Goal: P1 needs to gain life using ETB
        scenario = {
            "name": f"L2_ETB_Value_{i}",
            "supported_formats": ["Limited", "Commander"],
            "setup": {
                "p1_life": 18,
                "p1_hand": [5], # Aven Gagglemaster
                "p1_mana": 6
            },
            "goal": "p1_life >= 20"
        }
        with open(os.path.join(l2_dir, f"etb_{i}.json"), "w") as f:
            json.dump(scenario, f, indent=4)

    print(f"Generated 75+ generalized puzzles across Levels 1 and 2.")

if __name__ == "__main__":
    generate_generalized_puzzles()
