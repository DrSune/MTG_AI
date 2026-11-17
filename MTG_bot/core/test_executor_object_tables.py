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

#: The games, by set and seed: a greedy cover of the 39 containers 40 random games per set filled
#: on 2026-11-17, after verification wave 4's stamps (reports/guards_400_7_2026-11-17/seeds.py).
#: Engine changes and verification waves move what a seed's game does; MIN_FILLED says when the
#: cover has worn too thin to trust.
GAMES = {"M21": (9, 2, 16), "M20": (7, 18), "FDN": (22,)}
MIN_FILLED = 34
BEHAVIOURS = ("departure", "lki", "stack", "derived", "kept")
#: Compiled card text: it names no object of a game, so it is not walked.
_IR = ("MTG_bot.core.ability_tree", "MTG_bot.core.compiler")


def _engine_object(value: object) -> bool:
    """An object of the project's own classes, compiled card text and handles aside."""
    module = type(value).__module__
    return (
        module.startswith("MTG_bot.")
        and not module.startswith(_IR)
        and hasattr(value, "__dict__")
        and not isinstance(value, (type, Handle))
    )


def _holds_card(value: object, seen: set[int]) -> bool:
    """Does ``value`` hold a card's handle: itself, or as a key, an element or a record's field,
    however deep? ``seen`` holds the objects not to enter: those already entered, and the helpers,
    which are walked on their own. A player's handle is not an object that changes zones."""
    if isinstance(value, Handle):
        return value.namespace == "card"
    if isinstance(value, (str, bytes, int, float)) or value is None or id(value) in seen:
        return False
    seen.add(id(value))
    if isinstance(value, dict):
        return any(_holds_card(k, seen) or _holds_card(v, seen) for k, v in value.items())
    if isinstance(value, (list, tuple, set, frozenset, deque)):
        return any(_holds_card(v, seen) for v in value)
    if _engine_object(value):
        return any(_holds_card(v, seen) for v in vars(value).values())
    return False


def tables(root: object, found: set[str], names: set[str]) -> None:
    """Walk ``root`` and the helpers it reaches through attributes that hold one of the project's
    objects (the binder, the registries, the journal, the stack, the world): every attribute goes
    into ``names`` as ``Class.attr``, and each one that holds a card's handle into ``found``."""
    helpers: dict[int, object] = {}
    todo = [root]
    while todo:
        obj = todo.pop()
        if id(obj) not in helpers:
            helpers[id(obj)] = obj
            todo.extend(v for v in vars(obj).values() if _engine_object(v))
    for obj in helpers.values():
        for attr, value in vars(obj).items():
            key = f"{type(obj).__name__}.{attr}"
            names.add(key)
            if key in found or _engine_object(value) or callable(value):
                continue
            if _holds_card(value, set(helpers)):
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
            tables(g.executor, found, names)
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
            tables(game.executor, found, names)
    return found, names


def test_every_container_holding_a_card_declares_its_zone_change_behaviour(walked) -> None:
    found, _names = walked
    missing = sorted(found - set(Executor.OBJECT_TABLES))
    assert not missing, (
        f"{missing} hold a card's handle: say in Executor.OBJECT_TABLES what becomes of an entry "
        "when its card changes zones (CR 400.7), and make the departure hook do it"
    )


def test_the_games_still_fill_most_of_the_registry(walked) -> None:
    found, _names = walked
    assert len(found) >= MIN_FILLED, (
        f"the games fill {len(found)} of {len(Executor.OBJECT_TABLES)} registry containers: the "
        "seeds have drifted; pick GAMES again (reports/guards_400_7_2026-11-17/seeds.py)"
    )


def test_every_registry_entry_is_a_container_and_names_its_behaviour(walked) -> None:
    _found, names = walked
    assert sorted(set(Executor.OBJECT_TABLES) - names) == []  # no stale name
    for key, text in Executor.OBJECT_TABLES.items():
        assert text.split(":")[0] in BEHAVIOURS, key


def test_the_walk_finds_a_table_a_helper_gains() -> None:
    """The check can fail: a new table on a helper, a handle deep in a record or a nested
    container, and a scalar handle are found; a table of players' handles is not, nor one that
    only refers to a helper."""
    ex = Executor(GameWorld())
    card = Handle("card", 0)
    player = ex.world.player_order[0]
    ex.binder.probe_table = {card: 1}
    ex.returns.probe_rows = [ex.binder.probe_table]
    ex.layers.probe_last = card
    ex.journal.probe_deep = {player: {"k": [frozenset({(card,)})]}}
    ex.ledger.probe_helper = [ex.binder]
    ex.step_actions[player] = 1
    found: set[str] = set()
    tables(ex, found, set())
    assert {
        "TriggerBinder.probe_table",
        "ReturnRegistry.probe_rows",
        "LayerRegistry.probe_last",
        "EventJournal.probe_deep",
    } <= found
    assert "Executor.step_actions" not in found
    assert "DurationLedger.probe_helper" not in found
