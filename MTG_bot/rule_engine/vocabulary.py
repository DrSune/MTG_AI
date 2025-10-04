"""
This file establishes the core vocabulary for the MTG rule engine.

It uses unique integer constants to represent every possible concept in the game,
including cards, zones, abilities, and relationships. This provides a highly
efficient and unambiguous language for all other components of the system to use.
"""

# --- Core Game Concepts ---
# These are fundamental identifiers that don't fit into other categories.
ID_PLAYER = 0

# --- Zone Identifiers (100-199) ---
# Zones represent locations where cards can exist.
ID_ZONE_HAND = 100
ID_ZONE_BATTLEFIELD = 101
ID_ZONE_LIBRARY = 102
ID_ZONE_GRAVEYARD = 103
ID_ZONE_STACK = 104
ID_ZONE_EXILE = 105

# --- Relationship Identifiers (200-299) ---
# Relationships define how entities are connected in the game graph.
ID_REL_CONTROLS = 200      # e.g., (Player, Controls, Card)
ID_REL_IS_IN_ZONE = 201    # e.g., (Card, IsInZone, Hand)
ID_REL_HAS_ABILITY = 202   # e.g., (Card, HasAbility, Haste)
ID_REL_TAPPED = 203        # e.g., (Card, Tapped, True) - Could also be a property

# --- Card Identifiers (1000+) ---
# Each unique card in the game gets its own ID.
# Basic Lands
ID_CARD_FOREST = 1000
ID_CARD_ISLAND = 1001
ID_CARD_MOUNTAIN = 1002
ID_CARD_SWAMP = 1003
ID_CARD_PLAINS = 1004

# Creatures
ID_CARD_GRIZZLY_BEARS = 2000

# --- Ability & Keyword Identifiers (5000+) ---
ID_ABILITY_HASTE = 5000
ID_ABILITY_TRAMPLE = 5001
ID_ABILITY_FLYING = 5002
ID_ABILITY_FIRST_STRIKE = 5003
ID_ABILITY_DEATHTOUCH = 5004
ID_ABILITY_LIFELINK = 5005
