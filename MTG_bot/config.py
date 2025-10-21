import os

# Path to the MTGJSON all-cards database
# Download from https://mtgjson.com/downloads/all-files/
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MTGJSON_PATH = os.path.join(BASE_DIR, "data", "M21.json")

# The subset of cards to be used in the initial versions of the bot
# Example: A small set of vanilla creatures and basic lands from a core set.
CARD_SUBSET_CODES = ["M10"]
