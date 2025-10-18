import uuid
from typing import List, Dict, Any

from .rule_engine.engine import Engine
from .rule_engine.game_graph import GameGraph, Entity
from .rule_engine import vocabulary as vocab
from .rule_engine.actions import PlayLandAction, CastSpellAction, ActivateManaAbilityAction, DeclareAttackerAction, DeclareBlockerAction, PassTurnAction
from .rule_engine import card_database
from MTG_bot.utils.logger import setup_logger

# Define a temporary file for output redirection
TEMP_OUTPUT_FILE = "temp_main_output.txt"

logger = setup_logger(__name__)

def display_game_state(graph: GameGraph):
    """Prints the current state of the game in a human-readable format."""
    print("\n" + "="*40)
    print(f"Turn: {graph.turn_number} | Phase: {vocab.ID_TO_NAME.get(graph.phase, graph.phase)} | Step: {vocab.ID_TO_NAME.get(graph.step, graph.step)}")
    print("="*40)

    active_player = graph.entities[graph.active_player_id]
    non_active_player = next(p for p in graph.entities.values() if p.type_id == vocab.ID_PLAYER and p.instance_id != graph.active_player_id)

    # Display Player 1 (Active Player) Info
    print(f"\n--- {active_player.properties.get('name', 'Active Player')} ---")
    print(f"Life: {active_player.properties.get('life_total', 0)}")
    print(f"Mana Pool: {active_player.properties.get('mana_pool', {})}")

    # Hand
    hand_zone = next((graph.entities[r.target] for r in graph.get_relationships(source=active_player, rel_type=vocab.ID_REL_CONTROLS) if graph.entities[r.target].type_id == vocab.ID_ZONE_HAND), None)
    if hand_zone:
        cards_in_hand = [graph.entities[r.source] for r in graph.get_relationships(target=hand_zone, rel_type=vocab.ID_REL_IS_IN_ZONE)]
        print("Hand:")
        if cards_in_hand:
            for i, card in enumerate(cards_in_hand):
                print(f"  {i+1}. {card.properties.get('name', 'Unknown Card')}")
        else:
            print("  (empty)")

    # Battlefield
    battlefield_zone = next((graph.entities[r.target] for r in graph.get_relationships(source=active_player, rel_type=vocab.ID_REL_CONTROLS) if graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD), None)
    if battlefield_zone:
        cards_on_battlefield = [graph.entities[r.source] for r in graph.get_relationships(target=battlefield_zone, rel_type=vocab.ID_REL_IS_IN_ZONE)]
        print("Battlefield:")
        if cards_on_battlefield:
            for card in cards_on_battlefield:
                tapped_status = "(Tapped)" if card.properties.get('tapped', False) else ""
                summoning_sickness = "(Summoning Sickness)" if card.properties.get('has_summoning_sickness', False) else ""
                pt = "" 
                if card.properties.get('is_creature'):
                    pt = f" {card.properties.get('power', '?')}/{card.properties.get('toughness', '?')}"
                print(f"  - {card.properties.get('name', 'Unknown Card')}{pt} {tapped_status} {summoning_sickness}")
        else:
            print("  (empty)")

    # Display Player 2 (Non-Active Player) Info (simplified)
    print(f"\n--- {non_active_player.properties.get('name', 'Non-Active Player')} ---")
    print(f"Life: {non_active_player.properties.get('life_total', 0)}")
    print(f"Cards in Hand: {len(graph.get_relationships(target=next((graph.entities[r.target] for r in graph.get_relationships(source=non_active_player, rel_type=vocab.ID_REL_CONTROLS) if graph.entities[r.target].type_id == vocab.ID_ZONE_HAND), None), rel_type=vocab.ID_REL_IS_IN_ZONE))}")
    # Battlefield (simplified for non-active player)
    non_active_battlefield_zone = next((graph.entities[r.target] for r in graph.get_relationships(source=non_active_player, rel_type=vocab.ID_REL_CONTROLS) if graph.entities[r.target].type_id == vocab.ID_ZONE_BATTLEFIELD), None)
    if non_active_battlefield_zone:
        non_active_cards_on_battlefield = [graph.entities[r.source] for r in graph.get_relationships(target=non_active_battlefield_zone, rel_type=vocab.ID_REL_IS_IN_ZONE)]
        print(f"Cards on Battlefield: {len(non_active_cards_on_battlefield)}")

def get_player_choice(prompt: str, options: List[str]) -> int:
    """Gets a validated integer choice from the player."""
    while True:
        try:
            choice = input(prompt)
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return idx
            else:
                print("Invalid choice. Please enter a number corresponding to an option.")
        except ValueError:
            print("Invalid input. Please enter a number.")

def main():
    # Redirect stdout to a file
    original_stdout = sys.stdout
    with open(TEMP_OUTPUT_FILE, 'w') as f:
        sys.stdout = f
        _run_main_logic()
    sys.stdout = original_stdout # Restore original stdout

def _run_main_logic():
    print("--- main() function started ---")
    logger.info("Initializing MTG Game Engine for Manual Play...")

    # 1. Initialize the game graph and engine
    graph = GameGraph()
    engine = Engine(graph)

    # Sample Decks (using card names for now, will convert to IDs)
    # Ensure these cards exist in M21.json and are parsed by CardDataLoader
    decklist1_names = ["Forest", "Forest", "Grizzly Bears", "Grizzly Bears"]
    decklist2_names = ["Forest", "Forest", "Grizzly Bears", "Grizzly Bears"]

    print("--- Attempting to get card IDs ---")
    decklist1_ids = [card_database.get_card_id_by_name(name) for name in decklist1_names]
    decklist2_ids = [card_database.get_card_id_by_name(name) for name in decklist2_names]

    # Filter out None if some card names are not found
    decklist1_ids = [id for id in decklist1_ids if id is not None]
    decklist2_ids = [id for id in decklist2_ids if id is not None]

    if not decklist1_ids or not decklist2_ids:
        logger.error("One or both sample decks could not be loaded. Check card names in M21.json.")
        print("Error: One or both sample decks could not be loaded. Exiting.")
        return

    print("--- Initializing game with decks ---")
    graph.initialize_game(decklist1=decklist1_ids, decklist2=decklist2_ids)

    logger.info("Starting game loop...")
    game_over = False
    while not game_over:
        display_game_state(graph)

        active_player = graph.entities[graph.active_player_id]
        print(f"It's {active_player.properties.get('name', 'Active Player')}'s turn.")

        legal_moves = engine.get_legal_moves()
        
        if not legal_moves:
            print("No legal moves available. Automatically passing priority/phase.")
            # If no legal moves, automatically pass turn/phase
            engine.progress_phase_and_step(force_next_phase=True)
            continue

        print("\nAvailable Actions:")
        move_options = []
        for i, move in enumerate(legal_moves):
            move_description = str(move) # Default string representation of the action
            if isinstance(move, PlayLandAction):
                card_name = card_database.get_card_name(move.card_id).get('name', 'Unknown Land')
                move_description = f"Play Land: {card_name}"
            elif isinstance(move, CastSpellAction):
                card_name = card_database.get_card_name(move.card_id).get('name', 'Unknown Spell')
                move_description = f"Cast Spell: {card_name}"
            elif isinstance(move, ActivateManaAbilityAction):
                card_name = card_database.get_card_name(move.card_id).get('name', 'Unknown Permanent')
                mana_type = vocab.ID_TO_NAME.get(card_database.MANA_ABILITY_MAP.get(move.ability_id), 'Mana')
                move_description = f"Activate Mana Ability: Tap {card_name} for {mana_type}"
            elif isinstance(move, DeclareAttackerAction):
                card_name = card_database.get_card_name(move.card_id).get('name', 'Unknown Creature')
                move_description = f"Declare Attacker: {card_name}"
            elif isinstance(move, DeclareBlockerAction):
                blocker_name = card_database.get_card_name(move.blocker_id).get('name', 'Unknown Blocker')
                attacker_name = card_database.get_card_name(move.attacker_id).get('name', 'Unknown Attacker')
                move_description = f"Declare Blocker: {blocker_name} blocks {attacker_name}"
            elif isinstance(move, PassTurnAction):
                move_description = "Pass Turn/Phase"
            
            move_options.append(move_description)
            print(f"  {i+1}. {move_description}")
        
        # Add an option to pass priority/phase if not already a legal move
        if not any(isinstance(move, PassTurnAction) for move in legal_moves):
            move_options.append("Pass Priority/Phase")
            print(f"  {len(move_options)}. Pass Priority/Phase")

        choice_idx = get_player_choice("Enter the number of your chosen action: ", move_options)

        chosen_move = None
        if choice_idx < len(legal_moves):
            chosen_move = legal_moves[choice_idx]
        else: # Player chose to pass priority/phase
            chosen_move = PassTurnAction(player_id=active_player.instance_id) # Create a PassTurnAction

        engine.execute_move(chosen_move)

        game_over, winner_id = engine._check_win_loss_conditions()
        if game_over:
            display_game_state(graph)
            winner = graph.entities[winner_id]
            print(f"\nGAME OVER! {winner.properties.get('name', 'Unknown Player')} wins!")
            break

if __name__ == "__main__":
    # Add ID_TO_NAME mapping to vocabulary for better display
    vocab.ID_TO_NAME = {
        vocab.ID_PHASE_BEGINNING: "Beginning Phase",
        vocab.ID_PHASE_MAIN1: "Pre-Combat Main Phase",
        vocab.ID_PHASE_COMBAT: "Combat Phase",
        vocab.ID_PHASE_MAIN2: "Post-Combat Main Phase",
        vocab.ID_PHASE_ENDING: "Ending Phase",
        vocab.ID_STEP_UNTAP: "Untap Step",
        vocab.ID_STEP_UPKEEP: "Upkeep Step",
        vocab.ID_STEP_DRAW: "Draw Step",
        vocab.ID_STEP_PRE_COMBAT_MAIN: "Pre-Combat Main Step",
        vocab.ID_STEP_BEGINNING_OF_COMBAT: "Beginning of Combat Step",
        vocab.ID_STEP_DECLARE_ATTACKERS: "Declare Attackers Step",
        vocab.ID_STEP_DECLARE_BLOCKERS: "Declare Blockers Step",
        vocab.ID_STEP_COMBAT_DAMAGE: "Combat Damage Step",
        vocab.ID_STEP_END_OF_COMBAT: "End of Combat Step",
        vocab.ID_STEP_POST_COMBAT_MAIN: "Post-Combat Main Step",
        vocab.ID_STEP_END: "End Step",
        vocab.ID_STEP_CLEANUP: "Cleanup Step",
        vocab.ID_MANA_GREEN: "Green Mana",
        vocab.ID_MANA_BLUE: "Blue Mana",
        vocab.ID_MANA_BLACK: "Black Mana",
        vocab.ID_MANA_RED: "Red Mana",
        vocab.ID_MANA_WHITE: "White Mana",
        vocab.ID_MANA_COLORLESS: "Colorless Mana",
        vocab.ID_MANA_GENERIC: "Generic Mana",
        # Add more mappings for card types, abilities, etc. as needed
    }
    main()
