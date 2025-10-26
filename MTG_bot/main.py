import uuid
import sys
from typing import List, Dict, Any

from .rule_engine.engine import Engine
from .rule_engine.game_graph import GameGraph, Entity
from .rule_engine.actions import PlayLandAction, CastSpellAction, ActivateManaAbilityAction, DeclareAttackerAction, DeclareBlockerAction, PassTurnAction
from .rule_engine import card_database
from .rule_engine.game_initializer import initialize_game_state
from MTG_bot.utils.logger import setup_logger
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config

# Define a temporary file for output redirection
TEMP_OUTPUT_FILE = "temp_main_output.txt"

logger = setup_logger(__name__)
id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)
def display_game_state(graph: GameGraph):
    """Prints the current state of the game in a human-readable format."""
    print("\n" + "="*40)
    print(f"Turn: {graph.turn_number} | Phase: {id_mapper.get_name(graph.phase, "game_vocabulary")} | Step: {id_mapper.get_name(graph.step, "game_vocabulary")}")
    print("="*40)

    active_player = graph.entities[graph.active_player_id]
    non_active_player = next(p for p in graph.entities.values() if p.type_id == id_mapper.get_id_by_name("Player", "game_vocabulary") and p.instance_id != graph.active_player_id)

    # Display Player 1 (Active Player) Info
    print(f"\n--- {active_player.properties.get('name', 'Active Player')} ---")
    print(f"Life: {active_player.properties.get('life_total', 0)}")
    print(f"Mana Pool: {active_player.properties.get('mana_pool', {})}")

    # Hand
    hand_zone = next((graph.entities[r.target] for r in graph.get_relationships(source=active_player, rel_type=id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if graph.entities[r.target].type_id == id_mapper.get_id_by_name("Hand", "game_vocabulary")), None)
    if hand_zone:
        cards_in_hand = [graph.entities[r.source] for r in graph.get_relationships(target=hand_zone, rel_type=id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))]
        print("Hand:")
        if cards_in_hand:
            for i, card in enumerate(cards_in_hand):
                print(f"  {i+1}. {card.properties.get('name', 'Unknown Card')}")
        else:
            print("  (empty)")

    # Battlefield
    battlefield_zone = next((graph.entities[r.target] for r in graph.get_relationships(source=active_player, rel_type=id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if graph.entities[r.target].type_id == id_mapper.get_id_by_name("Battlefield", "game_vocabulary")), None)
    if battlefield_zone:
        cards_on_battlefield = [graph.entities[r.source] for r in graph.get_relationships(target=battlefield_zone, rel_type=id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))]
        print("Battlefield:")
        if cards_on_battlefield:
            for card in cards_on_battlefield:
                detailed_card_data = card_database.card_data_loader.get_card_data_by_id(card.type_id)
                card_name = detailed_card_data.get("name", "Unknown Card")
                mana_cost = detailed_card_data.get("mana_cost", "N/A")
                abilities = [id_mapper.get_name(ability_id, "game_vocabulary") for ability_id in detailed_card_data.get("abilities", []) if id_mapper.get_name(ability_id, "game_vocabulary")]
                original_power = detailed_card_data.get("power", "?")
                original_toughness = detailed_card_data.get("toughness", "?")

                tapped_status = "(Tapped)" if card.properties.get('tapped', False) else ""
                summoning_sickness = "(Summoning Sickness)" if card.properties.get('has_summoning_sickness', False) else ""
                
                owner_rel = next((r for r in graph.get_relationships(target=card, rel_type=id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))), None)
                owner_name = graph.entities[owner_rel.source].properties.get('name', 'Unknown') if owner_rel else 'Unknown'

                pt_display = "" 
                if card.properties.get('is_creature'):
                    current_power = card.properties.get('effective_power', original_power)
                    current_toughness = card.properties.get('effective_toughness', original_toughness)
                    pt_display = f" ({current_power}/{current_toughness} - Original: {original_power}/{original_toughness})"
                
                abilities_display = f" Abilities: {', '.join(abilities)}" if abilities else ""

                print(f"  - {card_name}{pt_display} Mana: {mana_cost}{abilities_display} Owner: {owner_name} {tapped_status} {summoning_sickness}")
        else:
            print("  (empty)")

    # Display Player 2 (Non-Active Player) Info (simplified)
    print(f"\n--- {non_active_player.properties.get('name', 'Non-Active Player')} ---")
    print(f"Life: {non_active_player.properties.get('life_total', 0)}")
    print(f"Cards in Hand: {len(graph.get_relationships(target=next((graph.entities[r.target] for r in graph.get_relationships(source=non_active_player, rel_type=id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if graph.entities[r.target].type_id == id_mapper.get_id_by_name("Hand", "game_vocabulary")), None), rel_type=id_mapper.get_id_by_name("Is In Zone", "game_vocabulary")))}")
    # Battlefield (simplified for non-active player)
    non_active_battlefield_zone = next((graph.entities[r.target] for r in graph.get_relationships(source=non_active_player, rel_type=id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if graph.entities[r.target].type_id == id_mapper.get_id_by_name("Battlefield", "game_vocabulary")), None)
    if non_active_battlefield_zone:
        non_active_cards_on_battlefield = [graph.entities[r.source] for r in graph.get_relationships(target=non_active_battlefield_zone, rel_type=id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))]
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
    _run_main_logic()

def _run_main_logic():
    print("--- main() function started ---")
    logger.info("Initializing MTG Game Engine for Manual Play...")

    # 1. Initialize the game graph and engine
    GAME_MODE = "Standard" # Can be "Manual", "Training", "Inference"

    # Load default decks from mtg_bot.db
    # Assuming deck_id 1 and 2 exist for demonstration
    deck1_id = 1
    deck2_id = 2
    decklist1_ids = game_initializer._load_decklist_from_db(deck1_id)
    decklist2_ids = game_initializer._load_decklist_from_db(deck2_id)

    # Sample chosen starting hands (for demonstration)
    player1_chosen_hand = [
        id_mapper.get_id_by_name("Forest", "cards"),
        id_mapper.get_id_by_name("Island", "cards"),
        id_mapper.get_id_by_name("Grizzly Bears", "cards"),
    ]
    player2_chosen_hand = [
        id_mapper.get_id_by_name("Forest", "cards"),
        id_mapper.get_id_by_name("Island", "cards"),
        id_mapper.get_id_by_name("Cancel", "cards"),
    ]

    graph = initialize_game_state(decklist1=decklist1_ids, decklist2=decklist2_ids, game_mode=GAME_MODE, player1_starting_hand_ids=player1_chosen_hand, player2_starting_hand_ids=player2_chosen_hand)
    engine = Engine(graph)

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
                card_name = id_mapper.get_name(move.card_id, "cards")
                move_description = f"Play Land: {card_name}"
            elif isinstance(move, CastSpellAction):
                card_name = id_mapper.get_name(move.card_id, "cards")
                move_description = f"Cast Spell: {card_name}"
            elif isinstance(move, ActivateManaAbilityAction):
                card_name = id_mapper.get_name(move.card_id, "cards")
                mana_type = id_mapper.get_name(card_database.MANA_ABILITY_MAP.get(move.ability_id), "game_vocabulary")
                move_description = f"Activate Mana Ability: Tap {card_name} for {mana_type}"
            elif isinstance(move, DeclareAttackerAction):
                card_name = id_mapper.get_name(move.card_id, "cards")
                move_description = f"Declare Attacker: {card_name}"
            elif isinstance(move, DeclareBlockerAction):
                blocker_name = id_mapper.get_name(move.blocker_id, "cards")
                attacker_name = id_mapper.get_name(move.attacker_id, "cards")
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
    main()
