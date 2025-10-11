import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from MTG_bot.rule_engine.game_graph import GameGraph
from MTG_bot.rule_engine.engine import RuleEngine
from MTG_bot.rule_engine import vocabulary as vocab
from MTG_bot.rule_engine.actions import PlayLandAction, ActivateManaAbilityAction, CastSpellAction, DeclareAttackerAction
from MTG_bot.rule_engine.card_database import CREATURE_STATS

def get_action(actions, action_type, card_id=None, target_id=None):
    """Helper to find a specific action type in a list, optionally by card_id and target_id."""
    for a in actions:
        if isinstance(a, action_type):
            if card_id and getattr(a, 'card_id', None) != card_id:
                continue
            if target_id and getattr(a, 'target_id', None) != target_id:
                continue
            return a
    return None

def main():
    """
    Tests the continuous effect of Giant Strength on a creature's power/toughness and combat damage.
    """
    engine = RuleEngine()
    game = GameGraph()

    # Rig the deck for a perfect opening hand: 2 Forests, 1 Grizzly Bears, 1 Giant Strength
    decklist1 = (
        [vocab.ID_CARD_FOREST] * 2 + 
        [vocab.ID_CARD_GRIZZLY_BEARS] + 
        [vocab.ID_CARD_GIANT_STRENGTH] + 
        [vocab.ID_CARD_FOREST] * 26 # Rest of the deck
    )
    decklist2 = [vocab.ID_CARD_MOUNTAIN] * 30
    game.initialize_game(decklist1, decklist2, shuffle=False)

    active_player_id = next(e.instance_id for e in game.entities.values() if e.type_id == vocab.ID_PLAYER)
    player_entity = game.entities[active_player_id]
    opponent_player_id = next(e.instance_id for e in game.entities.values() if e.type_id == vocab.ID_PLAYER and e.instance_id != active_player_id)
    opponent_entity = game.entities[opponent_player_id]

    # --- Turn 1: Play Land 1, Land 2, Cast Grizzly Bears ---
    print("--- Turn 1: Setup ---")
    # Play Land 1
    legal_actions = engine.get_legal_actions(game)
    play_land_1 = get_action(legal_actions, PlayLandAction)
    engine.execute_action(game, play_land_1)
    player_entity.properties['lands_played_this_turn'] = 0 # Reset for next land

    # Play Land 2
    legal_actions = engine.get_legal_actions(game)
    play_land_2 = get_action(legal_actions, PlayLandAction)
    engine.execute_action(game, play_land_2)

    # Tap Lands for Mana
    legal_actions = engine.get_legal_actions(game)
    mana_abilities = [a for a in legal_actions if isinstance(a, ActivateManaAbilityAction)]
    for ability in mana_abilities:
        engine.execute_action(game, ability)
    print(f"Mana pool after tapping: {player_entity.properties['mana_pool']}")

    # Cast Grizzly Bears
    legal_actions = engine.get_legal_actions(game)
    cast_bear_action = get_action(legal_actions, CastSpellAction, card_id=game.entities[vocab.ID_CARD_GRIZZLY_BEARS].instance_id)
    engine.execute_action(game, cast_bear_action)
    print("Grizzly Bears cast.")

    # --- Advance to Turn 2: Cast Giant Strength, Attack ---
    game.turn_number = 2
    player_entity.properties['lands_played_this_turn'] = 0 # Reset for new turn
    # Untap all permanents (simplified)
    for entity in game.entities.values():
        if entity.properties.get('tapped', False):
            entity.properties['tapped'] = False
    # Empty mana pool
    player_entity.properties['mana_pool'] = {m: 0 for m in player_entity.properties['mana_pool']}

    print("\n--- Turn 2: Cast Giant Strength & Attack ---")

    # Cast Giant Strength on Grizzly Bears
    legal_actions = engine.get_legal_actions(game)
    grizzly_bears_on_field = next(c for c in game.entities.values() if c.type_id == vocab.ID_CARD_GRIZZLY_BEARS and c.properties.get('turn_entered') == 1)
    cast_giant_strength_action = get_action(legal_actions, CastSpellAction, card_id=game.entities[vocab.ID_CARD_GIANT_STRENGTH].instance_id, target_id=grizzly_bears_on_field.instance_id)
    assert cast_giant_strength_action is not None, "FAIL: Did not find CastSpellAction for Giant Strength."
    engine.execute_action(game, cast_giant_strength_action)
    print("Giant Strength cast on Grizzly Bears.")

    # Verify effective P/T of Grizzly Bears
    engine.layer_system.apply_all_layers(game) # Ensure layers are applied
    assert grizzly_bears_on_field.properties['effective_power'] == 4, f"FAIL: Expected 4 power, got {grizzly_bears_on_field.properties['effective_power']}"
    assert grizzly_bears_on_field.properties['effective_toughness'] == 4, f"FAIL: Expected 4 toughness, got {grizzly_bears_on_field.properties['effective_toughness']}"
    print(f"Grizzly Bears effective P/T: {grizzly_bears_on_field.properties['effective_power']}/{grizzly_bears_on_field.properties['effective_toughness']}")

    # --- Declare Attacker ---
    game.phase = vocab.ID_PHASE_COMBAT
    game.step = vocab.ID_STEP_DECLARE_ATTACKERS
    legal_actions = engine.get_legal_actions(game)
    declare_attacker_action = get_action(legal_actions, DeclareAttackerAction, card_id=grizzly_bears_on_field.instance_id)
    assert declare_attacker_action is not None, "FAIL: Did not find DeclareAttackerAction for enchanted Grizzly Bears."
    engine.execute_action(game, declare_attacker_action)
    print("Grizzly Bears declared as attacker.")

    # --- Combat Damage (Unblocked Scenario) ---
    game.step = vocab.ID_STEP_COMBAT_DAMAGE
    p2_initial_life = opponent_entity.properties['life_total']
    engine.get_legal_actions(game) # Triggers damage assignment

    expected_life = p2_initial_life - 4 # 2 (base) + 2 (Giant Strength)
    assert opponent_entity.properties['life_total'] == expected_life, f"FAIL: Opponent life is {opponent_entity.properties['life_total']}, expected {expected_life}."
    print(f"Opponent life after unblocked attack: {opponent_entity.properties['life_total']}")

    print("\nContinuous effect and combat damage test successful!")

if __name__ == "__main__":
    main()
