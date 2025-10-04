"""
Main entry point for the MTG Bot.
This file will contain the main game loop that pits two bot instances against each other
or allows a human to play against the bot.
"""

from .rule_engine.engine import RuleEngine
from .strategic_brain.decision_maker import DecisionMaker
from .rule_engine.game_state import GameState

def main():
    """Initializes and runs the main game loop."""
    print("Initializing MTG Bot...")

    # 1. Initialize the game state with decks for two players
    #    - This will involve loading card data and creating Player objects.
    game = GameState(player1_deck_path="decks/deck1.txt", player2_deck_path="decks/deck2.txt")
    game.initialize_game()

    # 2. Initialize the decision-making agents for each player
    player1_brain = DecisionMaker(player_id=1)
    player2_brain = DecisionMaker(player_id=2)

    print("Starting game loop...")
    while not game.is_over():
        active_player_id = game.get_active_player_id()
        print(f"--- Turn {game.turn_number}, Player {active_player_id} --- ")

        # 3. Get all legal moves from the Rule Engine
        legal_moves = RuleEngine.get_legal_moves(game)

        if not legal_moves:
            print("No legal moves available. Passing priority.")
            game.pass_priority()
            continue

        # 4. The Strategic Brain chooses the best move
        active_brain = player1_brain if active_player_id == 1 else player2_brain
        chosen_move = active_brain.choose_best_move(game, legal_moves)

        # 5. Apply the chosen move to the game state
        game.apply_move(chosen_move)

        print(f"Player {active_player_id} chose move: {chosen_move}")

    print(f"Game over! Winner: {game.get_winner()}")

if __name__ == "__main__":
    # Note: This is a conceptual loop. The actual implementation will be more complex,
    # especially with handling priority and the stack.
    # main()
    print("This is a template. Run specific modules for testing.")
