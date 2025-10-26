import uuid
import random
import sqlite3
from typing import List, Optional, Dict, Any

from MTG_bot.rule_engine.game_graph import GameGraph, Entity
from MTG_bot.rule_engine.card_database import card_data_loader
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot import config
from MTG_bot.utils.logger import setup_logger

logger = setup_logger(__name__)
id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)

def _get_game_settings(game_mode: str) -> Dict[str, Any]:
    """
    Retrieves game settings from the game_vocabulary table in mtg_bot.db.
    Prioritizes mode-specific settings over 'General' settings.
    """
    settings = {}
    conn = sqlite3.connect(config.MTG_BOT_DB_PATH)
    cursor = conn.cursor()

    # Get general settings first
    cursor.execute("SELECT name, value FROM game_vocabulary WHERE type = 'game_setting' AND mode = 'General'")
    for name, value in cursor.fetchall():
        settings[name] = value

    # Override with mode-specific settings
    cursor.execute("SELECT name, value FROM game_vocabulary WHERE type = 'game_setting' AND mode = ?", (game_mode,))
    for name, value in cursor.fetchall():
        settings[name] = value

    conn.close()

    # Convert values to appropriate types
    for key, value in settings.items():
        if value and value.isdigit():
            settings[key] = int(value)

    return settings

def _load_decklist_from_db(deck_id: int) -> List[int]:
    """
    Loads a decklist (list of card IDs) from the mtg_bot.db for a given deck_id.
    """
    decklist = []
    conn = sqlite3.connect(config.MTG_BOT_DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT card_id, quantity FROM deck_cards WHERE deck_id = ?", (deck_id,))
    for card_id, quantity in cursor.fetchall():
        decklist.extend([card_id] * quantity)

    conn.close()
    return decklist

def initialize_game_state(decklist1: List[int], decklist2: List[int], game_mode: str = "Standard", shuffle: bool = True, player1_starting_hand_ids: Optional[List[int]] = None, player2_starting_hand_ids: Optional[List[int]] = None) -> GameGraph:
    """
    Initializes the game state with two players, their decks, and opening hands
    based on the specified game mode.
    """
    logger.info(f"Initializing game state for {game_mode} mode...")
    graph = GameGraph()

    # Get game settings from mtg_bot.db based on game_mode
    game_settings = _get_game_settings(game_mode)
    start_life = game_settings.get("player_start_health", 20)
    hand_size = game_settings.get("player_hand_size", 7)
    deck_size = game_settings.get("deck_size", 60)

    # Validate deck sizes
    if len(decklist1) != deck_size:
        logger.warning(f"Player 1 deck size ({len(decklist1)}) does not match {game_mode} mode requirement ({deck_size}).")
    if len(decklist2) != deck_size:
        logger.warning(f"Player 2 deck size ({len(decklist2)}) does not match {game_mode} mode requirement ({deck_size}).")

    # Create Players
    player1 = graph.add_entity(id_mapper.get_id_by_name("Player", "game_vocabulary"))
    player1.properties['life_total'] = start_life
    player1.properties['mana_pool'] = {m: 0 for m in [
        id_mapper.get_id_by_name("Green Mana", "game_vocabulary"),
        id_mapper.get_id_by_name("Blue Mana", "game_vocabulary"),
        id_mapper.get_id_by_name("Black Mana", "game_vocabulary"),
        id_mapper.get_id_by_name("Red Mana", "game_vocabulary"),
        id_mapper.get_id_by_name("White Mana", "game_vocabulary"),
        id_mapper.get_id_by_name("Colorless Mana", "game_vocabulary"),
        id_mapper.get_id_by_name("Generic Mana", "game_vocabulary"),
    ]}
    player1.properties['name'] = "Player 1"

    player2 = graph.add_entity(id_mapper.get_id_by_name("Player", "game_vocabulary"))
    player2.properties['life_total'] = start_life
    player2.properties['mana_pool'] = {m: 0 for m in [
        id_mapper.get_id_by_name("Green Mana", "game_vocabulary"),
        id_mapper.get_id_by_name("Blue Mana", "game_vocabulary"),
        id_mapper.get_id_by_name("Black Mana", "game_vocabulary"),
        id_mapper.get_id_by_name("Red Mana", "game_vocabulary"),
        id_mapper.get_id_by_name("White Mana", "game_vocabulary"),
        id_mapper.get_id_by_name("Colorless Mana", "game_vocabulary"),
        id_mapper.get_id_by_name("Generic Mana", "game_vocabulary"),
    ]}
    player2.properties['name'] = "Player 2"

    # Set active player
    graph.active_player_id = player1.instance_id
    logger.info(f"Active player set to {player1.properties.get('name')}.")

    # Create and shuffle decks
    deck1_entities = _create_deck_entities(graph, player1, decklist1)
    deck2_entities = _create_deck_entities(graph, player2, decklist2)
    if shuffle:
        random.shuffle(deck1_entities)
        random.shuffle(deck2_entities)
        logger.debug("Decks shuffled.")

    # Draw opening hands
    _draw_opening_hands(graph, player1, deck1_entities, hand_size, player1_starting_hand_ids)
    _draw_opening_hands(graph, player2, deck2_entities, hand_size, player2_starting_hand_ids)

    logger.info("Game initialized successfully.")
    return graph

def _create_deck_entities(graph: GameGraph, player: Entity, decklist: List[int]) -> List[Entity]:
    """
    Creates card entities from a decklist and links them to the player's library.
    Also creates player's zones.
    """
    logger.debug(f"Creating deck entities for player {player.properties.get('name', player.instance_id)[:4]} with {len(decklist)} cards.")
    deck_entities = []
    
    # Create zone entities for the player
    library = graph.add_entity(id_mapper.get_id_by_name("Library", "game_vocabulary"))
    hand = graph.add_entity(id_mapper.get_id_by_name("Hand", "game_vocabulary"))
    graveyard = graph.add_entity(id_mapper.get_id_by_name("Graveyard", "game_vocabulary"))
    battlefield = graph.add_entity(id_mapper.get_id_by_name("Battlefield", "game_vocabulary"))

    graph.add_relationship(player, library, id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
    graph.add_relationship(player, hand, id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
    graph.add_relationship(player, graveyard, id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
    graph.add_relationship(player, battlefield, id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))

    for card_type_id in decklist:
        card = graph.add_entity(card_type_id)
        graph.add_relationship(player, card, id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
        graph.add_relationship(card, library, id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))
        deck_entities.append(card)
    logger.debug(f"Deck entities created for player {player.properties.get('name', player.instance_id)[:4]}.")
    return deck_entities

def _draw_opening_hands(graph: GameGraph, player: Entity, deck: List[Entity], hand_size: int, chosen_cards_ids: Optional[List[int]] = None):
    """
    Draws the opening hand for a player, prioritizing chosen cards.
    """
    logger.debug(f"Drawing opening hand for {player.properties.get('name')} (hand size: {hand_size}).")
    # Find the hand zone for the player
    p_control_rels = graph.get_relationships(source=player, rel_type=id_mapper.get_id_by_name("Controlled By", "game_vocabulary"))
    hand_zone_entity = next((graph.entities[r.target] for r in p_control_rels if graph.entities[r.target].type_id == id_mapper.get_id_by_name("Hand", "game_vocabulary")), None)

    if not hand_zone_entity:
        logger.error(f"Hand zone not found for player {player.properties.get('name')}. Cannot draw opening hand.")
        return

    cards_to_draw_from_deck = []
    if chosen_cards_ids:
        # Prioritize chosen cards
        for chosen_card_id in chosen_cards_ids:
            # Find the entity for the chosen card in the deck
            chosen_card_entity = next((card_entity for card_entity in deck if card_entity.type_id == chosen_card_id), None)
            if chosen_card_entity:
                deck.remove(chosen_card_entity) # Remove from deck
                graph._move_card_to_zone(chosen_card_entity, hand_zone_entity)
                logger.debug(f"{player.properties.get('name')} drew chosen card {chosen_card_entity.properties.get('name', chosen_card_entity.type_id)}.")
            else:
                logger.warning(f"Chosen card ID {chosen_card_id} not found in deck for {player.properties.get('name')}. Drawing random instead.")

    # Draw remaining cards randomly until hand size is met
    while len([r.source for r in graph.get_relationships(target=hand_zone_entity, rel_type=id_mapper.get_id_by_name("Is In Zone", "game_vocabulary"))]) < hand_size:
        if deck:
            card_to_draw = deck.pop(0)
            graph._move_card_to_zone(card_to_draw, hand_zone_entity)
            logger.debug(f"{player.properties.get('name')} drew {card_to_draw.properties.get('name', card_to_draw.type_id)}.")
        else:
            logger.warning(f"Deck empty for {player.properties.get('name')}. Could not draw full opening hand.")
            break
