
import time
from MTG_bot.rule_engine.game_initializer import initialize_game_state
from MTG_bot.rule_engine.engine import Engine
from MTG_bot.rule_engine.actions import PlayLandAction, CastSpellAction, PassTurnAction, PassPriorityAction, DeclareAttackerAction
from MTG_bot.rule_engine import vocabulary as vocab

def run_test():
    print("Starting Live Visualizer Test...")
    # 1. Initialize Game
    # IDs for M21 cards (Mountain, Igneous Cur)
    deck1 = [269] * 30 + [153] * 30 
    deck2 = deck1.copy()
    
    graph = initialize_game_state(deck1, deck2)
    engine = Engine(graph, manual_mode=False)
    
    # We'll use the IDs for specific M21 cards if available, 
    # but for a demo we'll just manipulate some entities directly.
    player1 = graph.entities[graph.players[0]]
    player2 = graph.entities[graph.players[1]]
    
    player1.properties['name'] = "Player 1"
    player2.properties['name'] = "Opponent"
    
    # Give some life
    player1.properties['life_total'] = 20
    player2.properties['life_total'] = 20
    
    engine.recorder.record(graph, "Start of Test")
    time.sleep(2)

    # --- Step 1: Play a Land ---
    hand_zone = next(graph.entities[r.target] for r in graph.get_relationships(source=player1, rel_type=vocab.ID_REL_CONTROLLED_BY) if graph.entities[r.target].type_id == vocab.ID_ZONE_HAND)
    # Find a land card in hand
    land = None
    for r in graph.get_relationships(target=hand_zone, rel_type=vocab.ID_REL_IS_IN_ZONE):
        candidate = graph.entities[r.source]
        if "Land" in candidate.properties.get("type", "") or candidate.properties.get('is_land'):
            land = candidate
            break
    
    if land:
        engine.execute_move(PlayLandAction(player_id=player1.instance_id, card_id=land.instance_id))
        print(f"Played land: {land.properties.get('name')}")
        time.sleep(2)
    else:
        print("No land found in hand!")

    # --- Step 2: Cast a Creature ---
    creature = None
    for r in graph.get_relationships(target=hand_zone, rel_type=vocab.ID_REL_IS_IN_ZONE):
        candidate = graph.entities[r.source]
        if "Creature" in candidate.properties.get("type", "") or candidate.properties.get('is_creature'):
            creature = candidate
            break
    
    if creature:
        # Force some mana
        player1.properties['mana_pool'] = {vocab.ID_MANA_RED: 5}
        engine.execute_move(CastSpellAction(player_id=player1.instance_id, card_id=creature.instance_id))
        print(f"Casted creature: {creature.properties.get('name')}")
        time.sleep(2)
    else:
        print("No creature found in hand!")

    # --- Step 3: Advance to Combat ---
    while graph.step != vocab.ID_STEP_DECLARE_ATTACKERS:
        engine.progress_phase_and_step()
    print("Entered Combat!")
    time.sleep(2)

    # --- Step 4: Attack! ---
    creature.properties['has_summoning_sickness'] = False # Cheat for the demo
    engine.execute_move(DeclareAttackerAction(player_id=player1.instance_id, card_id=creature.instance_id))
    print(f"{creature.properties.get('name')} is attacking!")
    time.sleep(2)

    # --- Step 5: Deal Damage ---
    while graph.step != vocab.ID_STEP_UNTAP: # Loop until next turn
        engine.progress_phase_and_step()
    
    print(f"Damage dealt! Opponent life: {player2.properties['life_total']}")
    time.sleep(2)
    print("Test Complete. Check the visualizer history to see the sequence!")

if __name__ == "__main__":
    run_test()
