"""The London mulligan (CR 103.5) in dealt games: who keeps which opening hand, asked through the
engine's decision stream before the first turn, the library order from the engine's shuffle."""

from __future__ import annotations

from MTG_bot.core.executor import Executor
from MTG_bot.core.executor.games import (
    DECK_SIZE,
    OPENING_HAND,
    Game,
    RandomPolicy,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_HAND, ZONE_LIBRARY, GameWorld


def _card(i: int) -> CardIdentity:
    return CardIdentity(oracle_id=f"00000000-0000-0000-0000-{i:012d}", name=f"Card {i}",
                        type_line="Creature", power="1", toughness="1", cmc=1)


def _dealt(seed: int = 3) -> Game:
    supply = get_supply("castable")
    return _setup_game(seed, supply, deal_decks(seed, 1409, supply))


def _zones(game: Game, seat) -> tuple[list, list]:
    player = game.world.players[seat]
    return list(player.zone(ZONE_HAND).entries), list(player.zone(ZONE_LIBRARY).entries)


def _shuffles(game: Game, seat) -> int:
    """The engine's SHUFFLE events of ``seat``'s library (verbs._v_shuffle)."""
    return sum(1 for event in game.executor.events if event[1:] == ("SHUFFLE", str(seat), ZONE_LIBRARY))


class _Scripted:
    """A ``_play`` policy that never acts. A seat's mulligan declarations are its words in order,
    then "keep"; any other ask takes its highest offered card. ``log`` holds (what, vocab, asking
    seat, answer, the seat's hand size, whether a turn had begun) per ask; ``first_window`` the
    hand and library of each seat at the first act window, before anyone acts."""

    def __init__(self, game: Game, declarations: dict | None = None) -> None:
        self.game = game
        self.words = {seat: list(ws) for seat, ws in (declarations or {}).items()}
        self.log: list[tuple] = []
        self.first_window: dict | None = None

    def answer(self, vocab: tuple[str, ...], what: str) -> str:
        world = self.game.world
        seat = self.game.executor.decisions.asking_seat
        if what.startswith("mulligan:"):
            answer = self.words[seat].pop(0) if self.words.get(seat) else "keep"
        else:
            answer = "DECLINE" if "DECLINE" in vocab else vocab[-1]
        hand = len(world.players[seat].zone(ZONE_HAND).entries)
        self.log.append((what, vocab, seat, answer, hand, world.active_player is not None))
        return answer

    def take_acts(self, game: Game, seat) -> None:
        if self.first_window is None:
            self.first_window = {s: _zones(game, s) for s in game.world.player_order}

    def asked(self, seat, prefix: str = "mulligan") -> list[str]:
        return [row[0] for row in self.log if row[2] == seat and row[0].startswith(prefix)]


def _opening(declarations: dict, seed: int = 3) -> tuple[Game, _Scripted]:
    """Deal ``seed``, play its first turn with the scripted policy; seat 0 plays first and skips
    its draw (CR 103.8a), so the first act window shows the hands the mulligans left."""
    game = _dealt(seed)
    policy = _Scripted(game, {game.world.player_order[i]: ws for i, ws in declarations.items()})
    _play(game, policy, game.world.player_order, turn_cap=1)
    return game, policy


def test_a_mulligan_shuffles_the_hand_into_the_library_and_draws_seven() -> None:
    dealt = _dealt()
    p0, p1 = dealt.world.player_order
    hand0, library0 = _zones(dealt, p0)
    game, policy = _opening({0: ["mulligan"]})
    assert policy.asked(p0) == [f"mulligan:{p0}:0", f"mulligan_bottom:{p0}:1", f"mulligan:{p0}:1"]
    assert policy.asked(p1) == [f"mulligan:{p1}:0"]
    bottom = next(row for row in policy.log if row[0].startswith("mulligan_bottom:"))
    assert bottom[4] == OPENING_HAND and len(bottom[1]) == OPENING_HAND  # a new seven
    assert set(bottom[1]) != {str(h) for h in hand0}  # shuffled in, not put back on top
    assert _shuffles(game, p0) == _shuffles(dealt, p0) + 1
    hand, library = policy.first_window[p0]
    assert sorted(hand + library) == sorted(hand0 + library0)
    assert len(hand) == OPENING_HAND - 1 and len(library) == DECK_SIZE - OPENING_HAND + 1
    assert str(library[0]) == bottom[3]  # the chosen card is the bottom card
    assert policy.first_window[p1] == _zones(dealt, p1)  # a player who keeps keeps the dealt seven


def test_keeping_after_two_mulligans_bottoms_exactly_the_two_cards_chosen() -> None:
    game, policy = _opening({0: ["mulligan", "mulligan"]})
    p0 = game.world.player_order[0]
    assert policy.asked(p0) == [f"mulligan:{p0}:0", f"mulligan_bottom:{p0}:1", f"mulligan:{p0}:1",
                                f"mulligan_bottom:{p0}:2", f"mulligan_bottom:{p0}:1", f"mulligan:{p0}:2"]
    rows = [row for row in policy.log if row[2] == p0]
    first, second = rows[3][3], rows[4][3]
    hand, library = policy.first_window[p0]
    assert len(hand) == OPENING_HAND - 2 and len(library) == DECK_SIZE - OPENING_HAND + 2
    assert [str(h) for h in library[:2]] == [second, first]  # each card goes under the last
    assert not {first, second} & {str(h) for h in hand}
    assert rows[-1][4] == OPENING_HAND - 2  # the declaration that kept saw the kept hand


def test_no_hand_is_kept_below_zero_cards() -> None:
    game, policy = _opening({0: ["mulligan"] * 9})
    p0 = game.world.player_order[0]
    assert policy.asked(p0, "mulligan:") == [f"mulligan:{p0}:{n}" for n in range(OPENING_HAND)]
    hand, library = policy.first_window[p0]
    assert hand == [] and len(library) == DECK_SIZE
    last = [row for row in policy.log if row[0].startswith(f"mulligan_bottom:{p0}:")][1 - OPENING_HAND:]
    assert [row[0].rsplit(":", 1)[1] for row in last] == ["7", "6", "5", "4", "3", "2"]
    # each card goes under the last, and the seventh goes without a choice
    assert [str(h) for h in library[OPENING_HAND - 1:0:-1]] == [row[3] for row in last]


def test_the_starting_player_declares_first_and_the_mulligans_follow_the_declarations() -> None:
    game, policy = _opening({0: ["mulligan"], 1: ["mulligan"]})
    p0, p1 = game.world.player_order
    assert [(row[0], row[2]) for row in policy.log] == [
        (f"mulligan:{p0}:0", p0), (f"mulligan:{p1}:0", p1),
        (f"mulligan_bottom:{p0}:1", p0), (f"mulligan_bottom:{p1}:1", p1),
        (f"mulligan:{p0}:1", p0), (f"mulligan:{p1}:1", p1),
    ]
    assert all(row[1] == ("keep", "mulligan") for row in policy.log if row[0].startswith("mulligan:"))
    assert not any(row[5] for row in policy.log)  # all of it before the first turn begins


def test_only_a_dealt_game_runs_the_mulligans() -> None:
    world = GameWorld(num_players=2, master_seed=1)
    executor = Executor(world)
    for seat in world.player_order:
        for i in range(OPENING_HAND):
            world.add_card(_card(i), seat, ZONE_HAND)
    built = Game(executor=executor, seed=1, pool_mode="castable")
    policy = _Scripted(built)
    _play(built, policy, world.player_order, turn_cap=1)
    assert policy.log == []  # a position built by hand keeps the hands it was given
    assert [len(h) for h, _ in policy.first_window.values()] == [OPENING_HAND, OPENING_HAND]
    game, policy = _opening({})
    assert [row[0] for row in policy.log] == [f"mulligan:{p}:0" for p in game.world.player_order]


def test_a_seed_replays_its_mulligans_identically() -> None:
    def run() -> tuple:
        game = _dealt(6)
        _play(game, RandomPolicy(6), game.world.player_order, turn_cap=8)
        return game.executor.state_fingerprint(), tuple(game.executor.decisions.ask_log)

    first, second = run(), run()
    assert ("mulligan:player:1:0", "mulligan") in first[1]  # this seed's random policy mulligans
    assert first == second


def test_a_multiplayer_game_does_not_count_the_first_mulligan() -> None:
    """CR 103.5c: with more than two players the first mulligan puts no card on the bottom."""
    from MTG_bot.core.executor.games import mulligans

    world = GameWorld(num_players=3, master_seed=5)
    executor = Executor(world)
    for seat in world.player_order:
        for i in range(10):
            world.add_card(_card(i), seat, ZONE_LIBRARY)
        world.draw(seat, OPENING_HAND)
    game = Game(executor=executor, seed=5, pool_mode="castable")
    policy = _Scripted(game, {world.player_order[0]: ["mulligan", "mulligan"]})
    executor.decisions.provider = policy.answer
    p0, p1, p2 = world.player_order
    assert mulligans(executor, world.player_order) == {p0: 2, p1: 0, p2: 0}
    assert policy.asked(p0, "mulligan_bottom") == [f"mulligan_bottom:{p0}:1"]
    assert len(world.players[p0].zone(ZONE_HAND).entries) == OPENING_HAND - 1
