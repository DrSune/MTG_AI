import logging
import os
from datetime import datetime

LOG_DIR = "logs"
LOG_FILE_NAME = f"game_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
LOG_FILE_PATH = os.path.join(LOG_DIR, LOG_FILE_NAME)

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG) # Log all messages

    # Prevent duplicate handlers if called multiple times
    if not logger.handlers:
        # File handler
        file_handler = logging.FileHandler(LOG_FILE_PATH)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Console handler (optional, for immediate feedback)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.WARNING)  # Suppress info/debug chatter in the terminal
        console_formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    return logger

# Example usage:
# game_logger = setup_logger(__name__)
# game_logger.info("Game started.")
# game_logger.debug("Detailed debug info.")
# try:
#     raise ValueError("Something went wrong!")
# except ValueError as e:
#     game_logger.error("An error occurred: %s", e, exc_info=True)
