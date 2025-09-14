from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Dict, Optional, Any
import json

class Color(Enum):
    WHITE = "W"
    BLUE = "U"
    BLACK = "B"
    RED = "R"
    GREEN = "G"
    COLORLESS = ""

class Phase(Enum):
    BEGINNING = "beginning"
    MAIN1 = "main1"
    COMBAT_BEGIN = "combat_begin"
    COMBAT_DECLARE_ATTACKERS = "declare_attackers"
    COMBAT_DECLARE_BLOCKERS = "declare_blockers"
    COMBAT_DAMAGE = "combat_damage"
    COMBAT_END = "combat_end"
    MAIN2 = "main2"
    END = "end"
    CLEANUP = "cleanup"

class Zone(Enum):
    HAND = "hand"
    BATTLEFIELD = "battlefield"
    GRAVEYARD = "graveyard"
    LIBRARY = "library"
    EXILE = "exile"
    STACK = "stack"

class ManaCost:
    def __init__(self, cost_string=""):
        """Parse mana cost like '2RG' or '1UU'"""
        self.generic = 0
        self.colored = {color: 0 for color in Color}
        self.total_cmc = 0
        self._parse_cost(cost_string)

    def _parse_cost(self, cost_string):
        i = 0
        while i < len(cost_string):
            char = cost_string[i]
            if char.isdigit():
                # Handle multi-digit generic costs
                num_str = ""
                while i < len(cost_string) and cost_string[i].isdigit():
                    num_str += cost_string[i]
                    i += 1
                self.generic += int(num_str)
                self.total_cmc += int(num_str)
                continue
            elif char in "WUBRG":
                color_map = {"W": Color.WHITE, "U": Color.BLUE, "B": Color.BLACK, 
                           "R": Color.RED, "G": Color.GREEN}
                self.colored[color_map[char]] += 1
                self.total_cmc += 1
            i += 1

class Ability(ABC):
    """Base class for all abilities"""
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description

    @abstractmethod
    def can_activate(self, game_state, source) -> bool:
        pass

    @abstractmethod
    def resolve(self, game_state, source, targets=None):
        pass

class KeywordAbility(Ability):
    """Simple keyword abilities like Flying, Trample, etc."""
    def __init__(self, keyword: str):
        super().__init__(keyword, f"This creature has {keyword.lower()}")
        self.keyword = keyword

    def can_activate(self, game_state, source) -> bool:
        return False  # Most keywords are static, not activated

    def resolve(self, game_state, source, targets=None):
        pass  # Static abilities don't resolve

class Card:
    def __init__(self, name: str, card_type: str, mana_cost: str = "", 
                 abilities: List[Ability] = None, **kwargs):
        self.name = name
        self.card_type = card_type
        self.mana_cost = ManaCost(mana_cost)
        self.abilities = abilities or []
        self.owner = None
        self.controller = None
        self.zone = Zone.LIBRARY
        self.tapped = False
        self.summoning_sick = True
        self.damage = 0
        self.counters = {}

        # Store additional attributes for extensibility
        self.attributes = kwargs

    def has_ability(self, ability_name: str) -> bool:
        return any(ability.name == ability_name for ability in self.abilities)

    def add_ability(self, ability: Ability):
        self.abilities.append(ability)

    def remove_ability(self, ability_name: str):
        self.abilities = [a for a in self.abilities if a.name != ability_name]

class Creature(Card):
    def __init__(self, name: str, power: int, toughness: int, mana_cost: str = "",
                 abilities: List[Ability] = None, **kwargs):
        super().__init__(name, "Creature", mana_cost, abilities, **kwargs)
        self.base_power = power
        self.base_toughness = toughness
        self.power_modifiers = []
        self.toughness_modifiers = []

    @property
    def power(self) -> int:
        return max(0, self.base_power + sum(self.power_modifiers))

    @property
    def toughness(self) -> int:
        return max(1, self.base_toughness + sum(self.toughness_modifiers))

    def is_dead(self) -> bool:
        return self.damage >= self.toughness or self.toughness <= 0

class Land(Card):
    def __init__(self, name: str, produces: List[Color] = None, **kwargs):
        super().__init__(name, "Land", "", [], **kwargs)
        self.produces = produces or []

class Instant(Card):
    def __init__(self, name: str, mana_cost: str = "", abilities: List[Ability] = None, **kwargs):
        super().__init__(name, "Instant", mana_cost, abilities, **kwargs)

class Sorcery(Card):
    def __init__(self, name: str, mana_cost: str = "", abilities: List[Ability] = None, **kwargs):
        super().__init__(name, "Sorcery", mana_cost, abilities, **kwargs)

class Player:
    def __init__(self, name: str):
        self.name = name
        self.life = 20
        self.hand = []
        self.battlefield = []
        self.graveyard = []
        self.library = []
        self.exile = []
        self.mana_pool = {color: 0 for color in Color}
        self.lands_played_this_turn = 0
        self.max_hand_size = 7

    def draw_card(self, count: int = 1):
        for _ in range(count):
            if self.library:
                card = self.library.pop(0)
                card.zone = Zone.HAND
                self.hand.append(card)

    def play_land(self, card: Land):
        if self.lands_played_this_turn >= 1:
            raise ValueError("Already played a land this turn")
        if not isinstance(card, Land):
            raise ValueError("Not a land card")

        self.hand.remove(card)
        self.battlefield.append(card)
        card.zone = Zone.BATTLEFIELD
        card.controller = self
        self.lands_played_this_turn += 1

    def add_mana(self, color: Color, amount: int = 1):
        self.mana_pool[color] += amount

    def can_pay_cost(self, mana_cost: ManaCost) -> bool:
        # Simple mana payment check (doesn't handle complex costs)
        total_available = sum(self.mana_pool.values())
        if total_available < mana_cost.total_cmc:
            return False

        # Check colored requirements
        for color, required in mana_cost.colored.items():
            if self.mana_pool[color] < required:
                return False

        return True

class Game:
    def __init__(self, players: List[Player]):
        self.players = players
        self.active_player_index = 0
        self.turn_number = 1
        self.phase = Phase.BEGINNING
        self.stack = []
        self.priority_player_index = 0

    @property
    def active_player(self) -> Player:
        return self.players[self.active_player_index]

    @property
    def priority_player(self) -> Player:
        return self.players[self.priority_player_index]

    def next_phase(self):
        phases = list(Phase)
        current_index = phases.index(self.phase)

        if current_index == len(phases) - 1:  # End of turn
            self.next_turn()
        else:
            self.phase = phases[current_index + 1]

    def next_turn(self):
        # Reset turn-based values
        self.active_player.lands_played_this_turn = 0

        # Untap all permanents
        for card in self.active_player.battlefield:
            card.tapped = False
            if isinstance(card, Creature):
                card.summoning_sick = False

        # Next player
        self.active_player_index = (self.active_player_index + 1) % len(self.players)
        self.priority_player_index = self.active_player_index
        self.turn_number += 1
        self.phase = Phase.BEGINNING

        # Draw card
        self.active_player.draw_card()

# Rule checking functions
def can_attack(creature: Creature, game: Game) -> bool:
    """Check if a creature can attack"""
    if creature.tapped:
        return False
    if creature.summoning_sick and not creature.has_ability("Haste"):
        return False
    if creature.has_ability("Defender"):
        return False
    return True

def can_block(blocker: Creature, attacker: Creature) -> bool:
    """Check if a creature can block another"""
    if blocker.tapped:
        return False
    if attacker.has_ability("Flying") and not (blocker.has_ability("Flying") or blocker.has_ability("Reach")):
        return False
    return True

# Card factory for easy card creation
class CardFactory:
    @staticmethod
    def create_basic_land(land_type: str) -> Land:
        color_map = {
            "Plains": [Color.WHITE],
            "Island": [Color.BLUE],
            "Swamp": [Color.BLACK],
            "Mountain": [Color.RED],
            "Forest": [Color.GREEN]
        }
        return Land(land_type, produces=color_map.get(land_type, []))

    @staticmethod
    def create_grizzly_bears() -> Creature:
        return Creature("Grizzly Bears", power=2, toughness=2, mana_cost="1G")

    @staticmethod
    def create_lightning_bolt() -> Instant:
        class LightningBoltAbility(Ability):
            def __init__(self):
                super().__init__("Lightning Bolt Effect", "Deal 3 damage to any target")

            def can_activate(self, game_state, source) -> bool:
                return True

            def resolve(self, game_state, source, targets=None):
                if targets and len(targets) > 0:
                    target = targets[0]
                    if isinstance(target, Player):
                        target.life -= 3
                    elif isinstance(target, Creature):
                        target.damage += 3

        return Instant("Lightning Bolt", mana_cost="R", abilities=[LightningBoltAbility()])

    @staticmethod
    def create_serra_angel() -> Creature:
        flying = KeywordAbility("Flying")
        vigilance = KeywordAbility("Vigilance")
        return Creature("Serra Angel", power=4, toughness=4, mana_cost="3WW", 
                       abilities=[flying, vigilance])

# Example usage and testing
if __name__ == "__main__":
    # Create players
    player1 = Player("Alice")
    player2 = Player("Bob")

    # Create some cards
    forest = CardFactory.create_basic_land("Forest")
    bears = CardFactory.create_grizzly_bears()
    bolt = CardFactory.create_lightning_bolt()

    # Add cards to player's hand
    player1.hand.extend([forest, bears, bolt])

    # Create game
    game = Game([player1, player2])

    # Example: Play a land
    try:
        player1.play_land(forest)
        print(f"Played {forest.name}")
    except ValueError as e:
        print(f"Cannot play land: {e}")

    print(f"Game phase: {game.phase}")
    print(f"Active player: {game.active_player.name}")
    print(f"Player 1 battlefield: {[card.name for card in player1.battlefield]}")
