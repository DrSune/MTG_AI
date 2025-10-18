import os

# Path to the MTGJSON all-cards database
# Download from https://mtgjson.com/downloads/all-files/
MTGJSON_PATH = os.path.join("data", "M21.json")

# The subset of cards to be used in the initial versions of the bot
# Example: A small set of vanilla creatures and basic lands from a core set.
CARD_SUBSET_CODES = ["M10"]
