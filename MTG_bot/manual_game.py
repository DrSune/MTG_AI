import uuid
from typing import List, Dict, Any

from rule_engine.game_graph import GameGraph, Entity
from rule_engine.engine import Engine, PlayLandAction, PassTurnAction
from rule_engine import vocabulary as vocab
from rule_engine import card_database

def display_game_state(graph: GameGraph):
    print("\n--- Current Game State ---")
    active_player = graph.entities[graph.active_player_id]
    inactive_player = next(p for p in graph.entities.values() if p.type_id == vocab.ID_PLAYER and p.instance_id != graph.active_player_id)

    print(f"Turn: {graph.turn_number}")
    print(f"Phase: {vocab.ID_TO_NAME.get(graph.phase, 'Unknown Phase')}")
    print(f"Step: {vocab.ID_TO_NAME.get(graph.step, 'Unknown Step')}")

    # Display Active Player Info
    print(f"\n--- {active_player.properties['name']} (Active Player) ---")
    print(f"Life: {active_player.properties['life_total']}")
    print(f"Mana Pool: {active_player.properties['mana_pool']}")

    # Hand
    active_player_hand_zone = next(graph.entities[r.target] for r in graph.get_relationships(source=active_player, rel_type=vocab.ID_REL_CONTROLS) if graph.entities[r.target].type_id == vocab.ID_ZONE_HAND)
    cards_in_hand_rels = graph.get_relationships(target=active_player_hand_zone, rel_type=vocab.ID_REL_IS_IN_ZONE)
    cards_in_hand = [graph.entities[r.source] for r in cards_in_hand_rels]
    print("Hand:")
    if cards_in_hand:
        for i, card in enumerate(cards_in_hand):
            print(f"  {i+1}. {card.properties.get('name', vocab.ID_TO_NAME.get(card.type_id, 'Unknown Card'))}")
    else:
        print("  (empty)")

    # Battlefield
    active_player_battlefield_zone = next(graph.entities[r.target] for r in graph.get_relationships(source=active_player, rel_type=vocab.ID_REL_CONTROLS) if graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD)
    cards_on_battlefield_rels = graph.get_relationships(target=active_player_battlefield_zone, rel_type=vocab.ID_REL_IS_IN_ZONE)
    cards_on_battlefield = [graph.entities[r.source] for r in cards_on_battlefield_rels]
    print("Battlefield:")
    if cards_on_battlefield:
        for card in cards_on_battlefield:
            tapped_status = "(Tapped)" if card.properties.get('tapped') else ""
            print(f"  - {card.properties.get('name', vocab.ID_TO_NAME.get(card.type_id, 'Unknown Card'))} {tapped_status}")
    else:
        print("  (empty)")

    # Display Inactive Player Info
    print(f"\n--- {inactive_player.properties['name']} (Inactive Player) ---")
    print(f"Life: {inactive_player.properties['life_total']}")
    print(f"Mana Pool: {inactive_player.properties['mana_pool']}")

    # Battlefield (for inactive player)
    inactive_player_battlefield_zone = next(graph.entities[r.target] for r in graph.get_relationships(source=inactive_player, rel_type=vocab.ID_REL_CONTROLS) if graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD)
    cards_on_inactive_battlefield_rels = graph.get_relationships(target=inactive_player_battlefield_zone, rel_type=vocab.ID_REL_IS_IN_ZONE)
    cards_on_inactive_battlefield = [graph.entities[r.source] for r in cards_on_inactive_battlefield_rels]
    print("Battlefield:")
    if cards_on_inactive_battlefield:
        for card in cards_on_inactive_battlefield:
            tapped_status = "(Tapped)" if card.properties.get('tapped') else ""
            print(f"  - {card.properties.get('name', vocab.ID_TO_NAME.get(card.type_id, 'Unknown Card'))} {tapped_status}")
    else:
        print("  (empty)")
    print("--------------------------")

def get_player_input(legal_moves: List[Any]) -> Any:
    print("\n--- Legal Moves ---")
    if not legal_moves:
        print("No legal moves available. Passing turn...")
        return PassTurnAction(player_id=uuid.UUID('00000000-0000-0000-0000-000000000000')) # Placeholder for passing turn

    for i, move in enumerate(legal_moves):
        if isinstance(move, PlayLandAction):
            card_name = vocab.ID_TO_NAME.get(move.card_id, str(move.card_id))
            print(f"  {i+1}. Play Land: {card_name}")
        # Add other action types here as they are implemented
        else:
            print(f"  {i+1}. {move.__class__.__name__}")

    while True:
        try:
            choice = input("Enter the number of your chosen move: ")
            choice_index = int(choice) - 1
            if 0 <= choice_index < len(legal_moves):
                return legal_moves[choice_index]
            else:
                print("Invalid choice. Please enter a number corresponding to a legal move.")
        except ValueError:
            print("Invalid input. Please enter a number.")

def main():
    # For MVP, use simple decks with basic lands
    decklist1 = [vocab.ID_CARD_FOREST] * 20 + [vocab.ID_CARD_ISLAND] * 20
    decklist2 = [vocab.ID_CARD_MOUNTAIN] * 20 + [vocab.ID_CARD_SWAMP] * 20

    game_graph = GameGraph()
    game_graph.initialize_game(decklist1, decklist2)
    engine = Engine(game_graph)

    while True:
        display_game_state(game_graph)
        legal_moves = engine.get_legal_moves()
        chosen_move = get_player_input(legal_moves)

        if chosen_move:
            engine.execute_move(chosen_move)
        else:
            # If no moves and no chosen_move (e.g., PassTurnAction placeholder)
            engine.progress_phase_and_step(force_next_phase=True)

        # Check for win/loss conditions after each move
        is_game_over, winner_id = engine._check_win_loss_conditions()
        if is_game_over:
            winner_name = game_graph.entities[winner_id].properties['name'] if winner_id else 'No one'
            print(f"\nGAME OVER! {winner_name} wins!")
            break

if __name__ == "__main__":
    # Ensure card_database is initialized if it needs to load data
    # For now, assuming basic lands don't need complex loading beyond their ID
    # If card_database.card_data_loader needs explicit init, do it here
    # card_database.initialize_card_data()
    main()
