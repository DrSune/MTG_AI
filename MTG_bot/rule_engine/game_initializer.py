import uuid
import random
import sqlite3
from typing import List, Optional, Dict, Any

from MTG_bot.rule_engine.game_graph import GameGraph, Entity
from MTG_bot.rule_engine.card_database import card_data_loader
from MTG_bot.utils.id_to_name_mapper import IDToNameMapper
from MTG_bot.utils.logger import setup_logger
from MTG_bot.utils.rng import stream
from MTG_bot import config
from . import vocabulary as vocab

logger = setup_logger(__name__)
id_mapper = IDToNameMapper(config.MTG_BOT_DB_PATH)

def _get_game_settings(game_mode: str) -> Dict[str, Any]:
    """Helper to get game settings from DB or defaults."""
    # Placeholder for DB lookup
    return {}

def initialize_game_state(decklist1: List[int], decklist2: List[int], game_mode: str = "Standard", shuffle: bool = True, player1_starting_hand_ids: Optional[List[int]] = None, player2_starting_hand_ids: Optional[List[int]] = None) -> GameGraph:
    """
    Initializes the game state with players, zones, and decks based on the format.
    """
    logger.info(f"Initializing game state for {game_mode} mode...")
    graph = GameGraph()

    # 1. Format Parameters
    format_deck_sizes = {"Standard": 60, "Limited": 40, "Commander": 100}
    deck_size = format_deck_sizes.get(game_mode, 60)
    start_life = 40 if game_mode == "Commander" else 20
    hand_size = 7

    # 2. Create Players
    player1 = graph.add_entity(vocab.ID_PLAYER)
    player1.properties.update({'life_total': start_life, 'hand_size': hand_size, 'name': "Player 1", 'lands_played_this_turn': 0, 'mana_pool': {m: 0 for m in [vocab.ID_MANA_GREEN, vocab.ID_MANA_BLUE, vocab.ID_MANA_BLACK, vocab.ID_MANA_RED, vocab.ID_MANA_WHITE, vocab.ID_MANA_COLORLESS, vocab.ID_MANA_GENERIC]}})
    graph.players.append(player1.instance_id)

    player2 = graph.add_entity(vocab.ID_PLAYER)
    player2.properties.update({'life_total': start_life, 'hand_size': hand_size, 'name': "Player 2", 'lands_played_this_turn': 0, 'mana_pool': {m: 0 for m in [vocab.ID_MANA_GREEN, vocab.ID_MANA_BLUE, vocab.ID_MANA_BLACK, vocab.ID_MANA_RED, vocab.ID_MANA_WHITE, vocab.ID_MANA_COLORLESS, vocab.ID_MANA_GENERIC]}})
    graph.players.append(player2.instance_id)

    # Randomly select starting player
    graph.active_player_id = stream("shuffle").choice(graph.players)
    
    # Initialize Phase and Step correctly
    graph.phase = id_mapper.get_id_by_name("Beginning Phase", "game_vocabulary")
    graph.step = id_mapper.get_id_by_name("Untap Step", "game_vocabulary")

    # 3. Create Decks and Zones
    from MTG_bot.rule_engine.card_data_loader import CardDataLoader
    loader = CardDataLoader(config.MTG_BOT_DB_PATH)
    
    deck1_entities = _create_deck_entities(graph, player1, decklist1, loader, shuffle=shuffle, game_mode=game_mode)
    deck2_entities = _create_deck_entities(graph, player2, decklist2, loader, shuffle=shuffle, game_mode=game_mode)

    # 4. Draw Hands
    _draw_opening_hands(graph, player1, deck1_entities, hand_size, player1_starting_hand_ids)
    _draw_opening_hands(graph, player2, deck2_entities, hand_size, player2_starting_hand_ids)

    logger.info("Game initialized successfully.")
    return graph

def _create_deck_entities(graph: GameGraph, player: Entity, decklist: List[int], loader: any, shuffle: bool = True, game_mode: str = "Standard") -> List[Entity]:
    """Creates cards and format-aware zones."""
    library = graph.add_entity(vocab.ID_ZONE_LIBRARY)
    hand = graph.add_entity(vocab.ID_ZONE_HAND)
    graveyard = graph.add_entity(vocab.ID_ZONE_GRAVEYARD)
    battlefield = graph.add_entity(vocab.ID_ZONE_BATTLEFIELD)
    exile = graph.add_entity(vocab.ID_ZONE_EXILE)
    command = graph.add_entity(vocab.ID_ZONE_COMMAND)

    for zone in [library, hand, graveyard, battlefield, exile, command]:
        graph.add_relationship(player, zone, vocab.ID_REL_CONTROLLED_BY)

    working_deck = list(decklist)
    
    # Hydrate entities with data
    deck_entities = []
    
    if game_mode == "Commander" and working_deck:
        commander_id = working_deck.pop(0)
        c_data = loader.get_card_data_by_id(commander_id)
        commander_card = graph.add_entity(commander_id, c_data)
        # FIX: Player (Source) -> Card (Target)
        graph.add_relationship(player, commander_card, vocab.ID_REL_CONTROLLED_BY)
        graph._move_card_to_zone(commander_card, command)
        commander_card.properties['is_commander'] = True

    if shuffle: stream("shuffle").shuffle(working_deck)

    for cid in working_deck:
        c_data = loader.get_card_data_by_id(cid)
        card = graph.add_entity(cid, c_data)
        # FIX: Player (Source) -> Card (Target)
        graph.add_relationship(player, card, vocab.ID_REL_CONTROLLED_BY)
        graph._move_card_to_zone(card, library)
        deck_entities.append(card)
    
    return deck_entities

def _draw_opening_hands(graph: GameGraph, player: Entity, deck: List[Entity], hand_size: int, chosen_ids: Optional[List[int]] = None):
    hand_rels = graph.get_relationships(source=player, rel_type=vocab.ID_REL_CONTROLLED_BY)
    hand_zone = next(graph.entities[r.target] for r in hand_rels if graph.entities[r.target].type_id == vocab.ID_ZONE_HAND)

    if chosen_ids:
        for cid in chosen_ids:
            found = next((c for c in deck if c.type_id == cid), None)
            if found:
                deck.remove(found)
                graph._move_card_to_zone(found, hand_zone)

    while len(graph.get_relationships(target=hand_zone, rel_type=vocab.ID_REL_IS_IN_ZONE)) < hand_size and deck:
        card = deck.pop(0)
        graph._move_card_to_zone(card, hand_zone)
