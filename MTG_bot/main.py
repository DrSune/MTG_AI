import uuid
import sys
from typing import List, Dict, Any, Optional, Tuple

from .rule_engine.engine import Engine
from .rule_engine.game_graph import GameGraph, Entity
from .rule_engine.actions import (
    PlayLandAction,
    CastSpellAction,
    ActivateManaAbilityAction,
    DeclareAttackerAction,
    DeclareBlockerAction,
    PassPriorityAction,
    PassTurnAction,
)
from .rule_engine import card_database, game_initializer
from MTG_bot.utils.logger import setup_logger
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config

# Define a temporary file for output redirection
TEMP_OUTPUT_FILE = "temp_main_output.txt"

logger = setup_logger(__name__)
id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)

def get_card_entity_and_data(graph: GameGraph, instance_id) -> Tuple[Optional[Entity], Optional[Dict[str, Any]]]:
    """Helper to fetch an entity and its static card data."""
    entity = graph.entities.get(instance_id)
    if not entity:
        return None, None
    card_data = card_database.card_data_loader.get_card_data_by_id(entity.type_id)
    return entity, card_data

def get_card_display_name(graph: GameGraph, instance_id) -> str:
    """Returns a human-readable card name for the provided entity instance."""
    entity, card_data = get_card_entity_and_data(graph, instance_id)
    if card_data and card_data.get("name"):
        return card_data["name"]
    if entity:
        name = entity.properties.get("name")
        if name:
            return name
        card_name = id_mapper.get_name(entity.type_id, "cards")
        if card_name:
            return card_name
    return "Unknown Card"

def get_zone_cards(graph: GameGraph, zone_entity: Entity) -> List[Entity]:
    """Returns the list of true card entities that currently occupy the zone."""
    card_entities: List[Entity] = []
    if not zone_entity:
        return card_entities
    is_in_zone_id = id_mapper.get_id_by_name("Is In Zone", "game_vocabulary")
    zone_rels = graph.get_relationships(target=zone_entity, rel_type=is_in_zone_id) if is_in_zone_id else graph.get_relationships(target=zone_entity)
    for rel in zone_rels:
        entity = graph.entities.get(rel.source)
        if not entity:
            continue
        # Only include entities that correspond to real cards in the database.
        has_card_reference = bool(id_mapper.get_name(entity.type_id, "cards")) or bool(card_database.card_data_loader.get_card_data_by_id(entity.type_id))
        if has_card_reference:
            card_entities.append(entity)
    return card_entities

def format_mana_pool(mana_pool: Dict[int, int]) -> str:
    """Formats a mana pool dict using vocabulary names for display."""
    if not mana_pool:
        return "{}"
    entries = []
    for mana_id, amount in mana_pool.items():
        mana_name = id_mapper.get_name(mana_id, "game_vocabulary") or str(mana_id)
        entries.append(f"{mana_name}: {amount}")
    return "{ " + ", ".join(entries) + " }"

def display_game_state(graph: GameGraph, header: Optional[str] = None, show_non_active_hand: bool = True):
    """Prints the current state of the game in a human-readable format."""
    print("\n" + "=" * 40)
    if header:
        print(header)
    else:
        print(f"Turn: {graph.turn_number} | Phase: {id_mapper.get_name(graph.phase, 'game_vocabulary')} | Step: {id_mapper.get_name(graph.step, 'game_vocabulary')}")
    print("=" * 40)

    active_player = graph.entities[graph.active_player_id]
    non_active_player = next(p for p in graph.entities.values() if p.type_id == id_mapper.get_id_by_name("Player", "game_vocabulary") and p.instance_id != graph.active_player_id)

    # Display Player 1 (Active Player) Info
    print(f"\n--- {active_player.properties.get('name', 'Active Player')} ---")
    print(f"Life: {active_player.properties.get('life_total', 0)}")
    print(f"Mana Pool: {format_mana_pool(active_player.properties.get('mana_pool', {}))}")

    # Hand
    hand_zone = next((graph.entities[r.target] for r in graph.get_relationships(source=active_player, rel_type=id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if graph.entities[r.target].type_id == id_mapper.get_id_by_name("Hand", "game_vocabulary")), None)
    if hand_zone:
        cards_in_hand = get_zone_cards(graph, hand_zone)
        print("Hand:")
        if cards_in_hand:
            for i, card in enumerate(cards_in_hand):
                print(f"  {i+1}. {get_card_display_name(graph, card.instance_id)}")
        else:
            print("  (none)")

    # Battlefield
    battlefield_zone = next((graph.entities[r.target] for r in graph.get_relationships(source=active_player, rel_type=id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if graph.entities[r.target].type_id == id_mapper.get_id_by_name("Battlefield", "game_vocabulary")), None)
    cards_on_battlefield = get_zone_cards(graph, battlefield_zone) if battlefield_zone else []
    print("Battlefield:")
    if cards_on_battlefield:
        for card in cards_on_battlefield:
            detailed_card_data = card_database.card_data_loader.get_card_data_by_id(card.type_id) or {}
            card_name = detailed_card_data.get("name", get_card_display_name(graph, card.instance_id))
            mana_cost = detailed_card_data.get("mana_cost", "N/A")
            
            # Display abilities using the new structured format
            abilities_display_list = []
            abilities_data = detailed_card_data.get("abilities", {"keywords": [], "mana_abilities": []})
            
            for keyword_id in abilities_data.get("keywords", []):
                abilities_display_list.append(id_mapper.get_name(keyword_id, "game_vocabulary"))
            
            for mana_ability in abilities_data.get("mana_abilities", []):
                produces_str = ", ".join([f"{id_mapper.get_name(m_id, 'game_vocabulary')}: {amount}" for m_id, amount in mana_ability["produces"].items()])
                abilities_display_list.append(f"Tap for {produces_str}")

            original_power = detailed_card_data.get("power", "?")
            original_toughness = detailed_card_data.get("toughness", "?")

            tapped_status = "(Tapped)" if card.properties.get('tapped', False) else ""
            summoning_sickness = "(Summoning Sickness)" if card.properties.get('has_summoning_sickness', False) else ""
            
            pt_display = "" 
            if card.properties.get('is_creature'):
                current_power = card.properties.get('effective_power', original_power)
                current_toughness = card.properties.get('effective_toughness', original_toughness)
                pt_display = f" ({current_power}/{current_toughness} - Original: {original_power}/{original_toughness})"
            
            abilities_display = f" Abilities: {', '.join(abilities_display_list)}" if abilities_display_list else ""

            print(f"  - {card_name}{pt_display} Mana: {mana_cost}{abilities_display} {tapped_status} {summoning_sickness}")
    else:
        print("  (none)")

    # Display Player 2 (Non-Active Player) Info (simplified)
    print(f"\n--- {non_active_player.properties.get('name', 'Non-Active Player')} ---")
    print(f"Life: {non_active_player.properties.get('life_total', 0)}")
    print(f"Mana Pool: {format_mana_pool(non_active_player.properties.get('mana_pool', {}))}")
    non_active_hand_zone = next((graph.entities[r.target] for r in graph.get_relationships(source=non_active_player, rel_type=id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if graph.entities[r.target].type_id == id_mapper.get_id_by_name("Hand", "game_vocabulary")), None)
    non_active_hand_cards = get_zone_cards(graph, non_active_hand_zone)
    print("Hand:")
    if show_non_active_hand and non_active_hand_cards:
        for idx, card in enumerate(non_active_hand_cards, start=1):
            print(f"  {idx}. {get_card_display_name(graph, card.instance_id)}")
    else:
        print("  (none)")
    # Battlefield (simplified for non-active player)
    non_active_battlefield_zone = next((graph.entities[r.target] for r in graph.get_relationships(source=non_active_player, rel_type=id_mapper.get_id_by_name("Controlled By", "game_vocabulary")) if graph.entities[r.target].type_id == id_mapper.get_id_by_name("Battlefield", "game_vocabulary")), None)
    non_active_cards_on_battlefield = get_zone_cards(graph, non_active_battlefield_zone) if non_active_battlefield_zone else []
    print("Battlefield:")
    if non_active_cards_on_battlefield:
        for card in non_active_cards_on_battlefield:
            detailed_card_data = card_database.card_data_loader.get_card_data_by_id(card.type_id) or {}
            card_name = detailed_card_data.get("name", get_card_display_name(graph, card.instance_id))
            mana_cost = detailed_card_data.get("mana_cost", "N/A")

            abilities_display_list = []
            abilities_data = detailed_card_data.get("abilities", {"keywords": [], "mana_abilities": []})
            for keyword_id in abilities_data.get("keywords", []):
                abilities_display_list.append(id_mapper.get_name(keyword_id, "game_vocabulary"))
            for mana_ability in abilities_data.get("mana_abilities", []):
                produces_str = ", ".join([f"{id_mapper.get_name(m_id, 'game_vocabulary')}: {amount}" for m_id, amount in mana_ability["produces"].items()])
                abilities_display_list.append(f"Tap for {produces_str}")

            original_power = detailed_card_data.get("power", "?")
            original_toughness = detailed_card_data.get("toughness", "?")
            tapped_status = "(Tapped)" if card.properties.get('tapped', False) else ""
            summoning_sickness = "(Summoning Sickness)" if card.properties.get('has_summoning_sickness', False) else ""

            pt_display = "" 
            if card.properties.get('is_creature'):
                current_power = card.properties.get('effective_power', original_power)
                current_toughness = card.properties.get('effective_toughness', original_toughness)
                pt_display = f" ({current_power}/{current_toughness} - Original: {original_power}/{original_toughness})"

            abilities_display = f" Abilities: {', '.join(abilities_display_list)}" if abilities_display_list else ""

            print(f"  - {card_name}{pt_display} Mana: {mana_cost}{abilities_display} {tapped_status} {summoning_sickness}")
    else:
        print("  (none)")
    print()

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

    # 1. Choose gameplay format and initialize the game graph/engine
    PLAY_MODE = "Manual" # Can be "Manual", "Training", "Inference"

    available_modes = game_initializer.get_available_game_modes()
    if not available_modes:
        logger.error("No gameplay modes configured in the database.")
        return

    print("Available Game Modes:")
    mode_options = [mode for mode in available_modes]
    for index, mode in enumerate(mode_options, start=1):
        print(f"  {index}. {mode}")
    mode_choice_idx = get_player_choice("Select a game mode: ", mode_options)
    selected_game_mode = mode_options[mode_choice_idx]

    # Deck Selection
    available_decks = game_initializer.get_available_decks(selected_game_mode)
    if not available_decks:
        logger.error(f"No decks found for game mode '{selected_game_mode}'. Exiting.")
        return

    deck_items = sorted(available_decks.items(), key=lambda item: item[1])
    deck_option_labels = [f"{name} (Deck #{deck_id})" for deck_id, name in deck_items]

    print(f"Available Decks for {selected_game_mode}:")
    for idx, label in enumerate(deck_option_labels, start=1):
        print(f"  {idx}. {label}")

    deck1_idx = get_player_choice("Choose a deck for Player 1: ", deck_option_labels)
    deck2_idx = get_player_choice("Choose a deck for Player 2: ", deck_option_labels)

    deck1_id = deck_items[deck1_idx][0]
    deck2_id = deck_items[deck2_idx][0]

    decklist1_ids = game_initializer._load_decklist_from_db(deck1_id)
    decklist2_ids = game_initializer._load_decklist_from_db(deck2_id)

    graph = game_initializer.initialize_game_state(decklist1=decklist1_ids, decklist2=decklist2_ids, game_mode=selected_game_mode)
    engine = Engine(graph, manual_mode=(PLAY_MODE == "Manual"))

    # Mulligan Phase
    for player_id in [engine.graph.players[0], engine.graph.players[1]]:
        player = engine.graph.entities[player_id]
        while True:
            display_game_state(graph, header="Mulligan Phase", show_non_active_hand=True)
            mull_count = player.properties.get('mulligans_taken', 0)
            print(f"[{player.properties.get('name')} | Mulligans taken: {mull_count}]")
            print(f"{player.properties.get('name')}, would you like to mulligan? (y/n)")
            choice = input().lower()
            if choice == 'y':
                print(f"--> {player.properties.get('name')} is taking mulligan #{mull_count + 1} (London mulligan).")
                engine.mulligan(player_id)
            else:
                break
    print("\n=== Mulligans Complete ===\n")

    graph.phase = id_mapper.get_id_by_name("Beginning Phase", "game_vocabulary") or graph.phase
    graph.step = id_mapper.get_id_by_name("Untap Step", "game_vocabulary") or graph.step

    logger.info("Starting game loop...")
    game_over = False
    while not game_over:
        display_game_state(graph, show_non_active_hand=True)

        active_player = graph.entities[graph.active_player_id]
        print(f"It's {active_player.properties.get('name', 'Active Player')}'s turn.")

        legal_moves = engine.get_legal_moves()

        if not legal_moves:
            if engine.manual_mode:
                legal_moves = [
                    PassPriorityAction(player_id=active_player.instance_id),
                    PassTurnAction(player_id=active_player.instance_id),
                ]
            else:
                print("No legal moves available. Automatically passing priority/phase.")
                engine.progress_phase_and_step(force_next_phase=True)
                continue

        print("\nAvailable Actions:")
        move_options = []
        for i, move in enumerate(legal_moves):
            move_description = str(move) # Default string representation of the action
            if isinstance(move, PlayLandAction):
                card_name = get_card_display_name(graph, move.card_id)
                move_description = f"Play Land: {card_name}"
            elif isinstance(move, CastSpellAction):
                card_name = get_card_display_name(graph, move.card_id)
                move_description = f"Cast Spell: {card_name}"
            elif isinstance(move, ActivateManaAbilityAction):
                card_name = get_card_display_name(graph, move.card_id)
                # Get the mana ability details from the card's properties
                _, card_data = get_card_entity_and_data(graph, move.card_id)
                mana_abilities = card_data.get("abilities", {}).get("mana_abilities", []) if card_data else []
                if move.ability_id < len(mana_abilities):
                    mana_ability = mana_abilities[move.ability_id]
                    produces_str = ", ".join([f"{id_mapper.get_name(m_id, 'game_vocabulary')}: {amount}" for m_id, amount in mana_ability["produces"].items()])
                    move_description = f"Activate Mana Ability: Tap {card_name} for {produces_str}"
                else:
                    move_description = f"Activate Mana Ability: Tap {card_name} (Unknown Ability)"
            elif isinstance(move, DeclareAttackerAction):
                card_name = get_card_display_name(graph, move.card_id)
                move_description = f"Declare Attacker: {card_name}"
            elif isinstance(move, DeclareBlockerAction):
                blocker_name = get_card_display_name(graph, move.blocker_id)
                attacker_name = get_card_display_name(graph, move.attacker_id)
                move_description = f"Declare Blocker: {blocker_name} blocks {attacker_name}"
            elif isinstance(move, PassPriorityAction):
                move_description = "Advance Step / Pass Priority"
            elif isinstance(move, PassTurnAction):
                move_description = "End Turn"
            
            move_options.append(move_description)
            print(f"  {i+1}. {move_description}")

        choice_idx = get_player_choice("Enter the number of your chosen action: ", move_options)

        chosen_move = legal_moves[choice_idx]

        if engine.manual_mode:
            confirmation = input(f"Execute '{move_options[choice_idx]}'? (Y/n): ").strip().lower()
            if confirmation not in ("", "y", "yes"):
                print("Action cancelled. Re-select an option.")
                continue

        engine.execute_move(chosen_move)

        game_over, winner_id = engine._check_win_loss_conditions()
        if game_over:
            display_game_state(graph, show_non_active_hand=True)
            winner = graph.entities[winner_id]
            print(f"\nGAME OVER! {winner.properties.get('name', 'Unknown Player')} wins!")
            break

if __name__ == "__main__":
    main()
