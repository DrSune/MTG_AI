"""CR 400.7 for per-object state, made checkable (KNOWLEDGE/2026-11-17/212 §3).

A card keeps its handle in every zone, but a card that changes zones is a new object. Four tables
keyed on a handle outlived a zone change before the bug hunt of 2026-11-17 (the loyalty clock,
Malefic Scythe's attachment record, "exiled with", a spell's stack frame), each found by hand. So
every container of the executor and its helpers that holds a card's handle declares its behaviour
in ``Executor.OBJECT_TABLES``, beside the departure hook, and real random games over the three
dealt pools find the containers: one the registry does not name fails here until its author
decides what becomes of it when the card changes zones.
"""

from __future__ import annotations

from collections import deque

import pytest

from MTG_bot.core.executor import Executor, GameOver
from MTG_bot.core.executor.games import (
    TURN_CAP,
    RandomPolicy,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)
from MTG_bot.core.identity import Handle
from MTG_bot.core.state import GameWorld

#: The games, by set and seed: between them they fill every container that 40 random games per
#: set filled on 2026-11-17 (a greedy cover: 38 containers).
GAMES = {"M21": (19, 29, 5, 26), "M20": (8, 1, 34), "FDN": (30,)}
BEHAVIOURS = ("departure", "lki", "stack", "derived", "kept")
_ENGINE = ("MTG_bot.core.executor", "MTG_bot.core.state", "MTG_bot.core.identity")


def _engine_object(value: object) -> bool:
    """An object of the engine's own classes (not a handle): a helper to walk, or a record."""
    return (
        type(value).__module__.startswith(_ENGINE)
        and hasattr(value, "__dict__")
        and not isinstance(value, (type, Handle))
    )


def _holds_card(value: object, depth: int = 3) -> bool:
    """Does ``value`` hold a card's handle: itself, or as a key, an element or a record's field,
    up to ``depth`` levels down? A player's handle is not an object that changes zones."""
    if isinstance(value, Handle):
        return value.namespace == "card"
    if depth == 0:
        return False
    if isinstance(value, dict):
        return any(_holds_card(k, depth - 1) or _holds_card(v, depth - 1) for k, v in value.items())
    if isinstance(value, (list, tuple, set, frozenset, deque)):
        return any(_holds_card(v, depth - 1) for v in value)
    if _engine_object(value):
        return any(_holds_card(v, depth - 1) for v in vars(value).values())
    return False


def tables(obj: object, found: set[str], names: set[str], seen: set[int]) -> None:
    """Walk ``obj`` and the engine objects its attributes hold (the executor's helpers: the
    binder, the registries, the journal, the stack, the world): every attribute goes into
    ``names`` as ``Class.attr``, and each one that holds a card's handle into ``found``."""
    seen.add(id(obj))
    for attr, value in vars(obj).items():
        key = f"{type(obj).__name__}.{attr}"
        names.add(key)
        if _engine_object(value):
            if id(value) not in seen:
                tables(value, found, names, seen)
        elif key not in found and not callable(value) and _holds_card(value):
            found.add(key)


@pytest.fixture(scope="module")
def walked() -> tuple[set[str], set[str]]:
    """The containers holding a card's handle at any point a game loop stops at (every priority
    point, the turn tops, the declarations) where something happened since the last one (the
    journal or the stack changed), or at a game's end, and every attribute name."""
    found: set[str] = set()
    names: set[str] = set()
    last = [(-1, -1)]  # the journal's and the stack's sizes at the last walk

    def walk(g, _boundary: str) -> bool:
        now = (len(g.executor.journal.events), len(g.executor.stack.frames))
        if now != last[0]:
            last[0] = now
            tables(g.executor, found, names, set())
        return False

    for code, seeds in GAMES.items():
        supply = get_supply("verified", code)
        for seed in seeds:
            game = _setup_game(seed, supply, deal_decks(seed, 1409, supply, "stress" if seed % 3 else "coherent"))
            last[0] = (-1, -1)
            try:
                _play(game, RandomPolicy(seed), game.world.player_order, TURN_CAP, stop_after=walk)
            except GameOver:
                pass
            tables(game.executor, found, names, set())
    return found, names


def test_every_container_holding_a_card_declares_its_zone_change_behaviour(walked) -> None:
    found, _names = walked
    missing = sorted(found - set(Executor.OBJECT_TABLES))
    assert not missing, (
        f"{missing} hold a card's handle: say in Executor.OBJECT_TABLES what becomes of an entry "
        "when its card changes zones (CR 400.7), and make the departure hook do it"
    )


def test_every_registry_entry_is_a_container_and_names_its_behaviour(walked) -> None:
    _found, names = walked
    assert sorted(set(Executor.OBJECT_TABLES) - names) == []  # no stale name
    for key, text in Executor.OBJECT_TABLES.items():
        assert text.split(":")[0] in BEHAVIOURS, key


def test_the_walk_finds_a_table_a_helper_gains() -> None:
    """The check can fail: a new table on a helper, a card handle in a record's field, and a
    scalar handle are found; a table of players' handles is not."""
    ex = Executor(GameWorld())
    card = Handle("card", 0)
    ex.binder.probe_table = {card: 1}
    ex.returns.probe_rows = [ex.binder.probe_table]
    ex.layers.probe_last = card
    ex.step_actions[ex.world.player_order[0]] = 1
    found: set[str] = set()
    tables(ex, found, set(), set())
    assert {"TriggerBinder.probe_table", "ReturnRegistry.probe_rows", "LayerRegistry.probe_last"} <= found
    assert "Executor.step_actions" not in found
