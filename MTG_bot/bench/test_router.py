"""SeatRouter: per-seat agents inside the engine's own loop, every ask on the right seat."""

from __future__ import annotations

import pytest

from MTG_bot.bench.agents import PassAgent, UniformRandomAgent
from MTG_bot.bench.protocol import AskRoutingError, UnknownAskSite, resolve_ask_seat
from MTG_bot.bench.router import SeatRouter
from MTG_bot.bench.view import OracleIndex, SeatLens
from MTG_bot.core.executor.games import (
    RandomPolicy,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
    play_game,
)
from MTG_bot.core.identity import Handle
from MTG_bot.utils import rng

ORACLE = OracleIndex.for_sets("M21", "ZNR")
P0, P1 = Handle("player", 0), Handle("player", 1)


def _game(seed: int, set_code: str = "M21"):
    supply = get_supply("castable", set_code)
    return _setup_game(seed, supply, deal_decks(seed, 1409, supply)), supply


def _lenses():
    return [SeatLens(0, ORACLE), SeatLens(1, ORACLE)]


def test_routing_rejects_unknown_kinds_and_disagreeing_tags() -> None:
    assert resolve_ask_seat("attack:card:3:7", P1) == P1
    assert resolve_ask_seat("scry:player:0:1", P0) == P0
    with pytest.raises(AskRoutingError):
        resolve_ask_seat("scry:player:0:1", P1)  # tag and engine disagree
    with pytest.raises(AskRoutingError):
        resolve_ask_seat("may:card:9:abc", None)  # engine named no seat
    with pytest.raises(UnknownAskSite):
        resolve_ask_seat("brand_new_site:card:1", P0)


def test_a_raw_policy_behind_the_router_reproduces_play_game() -> None:
    # The router consumes no randomness and adds no engine calls, so the engine's own random
    # policy routed through it plays the identical game.
    expected = play_game(3, "castable", 1409, turn_cap=10)
    game, supply = _game(3)
    policy = RandomPolicy(3)
    _play(game, SeatRouter(game, [policy, policy], _lenses(), supply=supply), game.world.player_order, 10)
    assert game.digest == expected.digest


@pytest.mark.parametrize("set_code", ["M21", "ZNR"])
def test_uniform_agents_play_whole_games_with_every_ask_routed(set_code: str) -> None:
    rng.seed_all(11, seed_frameworks=False)
    for seed in (1, 2, 3):
        game, supply = _game(seed, set_code)
        agents = [UniformRandomAgent(rng.substream("bench", seed, s)) for s in (0, 1)]
        router = SeatRouter(game, agents, _lenses(), supply=supply, strict=True)
        _play(game, router, game.world.player_order, turn_cap=30)  # strict: a misroute raises
        assert game.reason
        assert all(st["asks"] > 0 for st in router.stats)


def test_pass_agent_never_acts() -> None:
    game, supply = _game(4)
    _play(game, SeatRouter(game, [PassAgent(), PassAgent()], _lenses(), supply=supply), game.world.player_order, 12)
    assert game.acts == 0
    assert game.reason.startswith("turn cap")


def test_tap_effects_are_not_mana_abilities() -> None:
    # Regression (2026-10-24): "Tap target creature" counted as a mana ability, went out with no
    # target behind TAP_ALL_MANA, and crashed the engine. Seed 6 reached that position.
    rng.seed_all(1, seed_frameworks=False)
    game, supply = _game(6)
    agents = [UniformRandomAgent(rng.substream("bench", 6, 0)), PassAgent()]
    _play(game, SeatRouter(game, agents, _lenses(), supply=supply), game.world.player_order, 40)
    assert game.reason
