"""The game rig: the bench's ``SeatRouter`` plus the per-decision context agents need.

``SelfplayRouter`` adds an ``AskContext`` (features.py) to every observation: the card being
scried (the router already computes it for its prompt), the attackers declared so far in this
combat and the blocks declared so far. The engine applies a whole declaration only after its
last ask, so without this an agent would declare each attacker blind to the others.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Any

from MTG_bot.bench.agents import AgentError, Observation
from MTG_bot.bench.protocol import ask_kind
from MTG_bot.bench.router import SeatRouter
from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
from MTG_bot.core.executor.games import (
    TURN_CAP,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)
from MTG_bot.core.identity import Handle
from tools.selfplay.features import AskContext, _handle


@dataclass
class SPObservation(Observation):
    ctx: AskContext = field(default_factory=AskContext)
    game: Any = None  # the live Game: decision-time search forks it (search.py)


class SelfplayRouter(SeatRouter):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._turn = -1
        self._attackers: set = set()
        self._blocks: dict = {}
        self._revealed: Handle | None = None

    def _sync_turn(self) -> None:
        turn = self.game.world.turn
        if turn != self._turn:
            self._turn = turn
            self._attackers = set()
            self._blocks = {}

    def _declared_attackers(self) -> frozenset:
        """This turn's attackers: the answers so far while attacks are being declared, plus the
        engine's record once the declaration is complete, which also holds the attackers the
        engine picks itself (a creature that must attack is never asked)."""
        return frozenset(self._attackers).union(self.game.executor.attackers)

    def _context(self, what: str, seat: Handle, i: int) -> str:
        self._revealed = None
        if ask_kind(what) == "scry":
            k = self.scry_position(what)
            library = self.game.world.players[seat].zone("library").entries
            if k < len(library):
                self._revealed = library[-1 - k]
        return super()._context(what, seat, i)

    def answer(self, vocab: tuple[str, ...], what: str) -> str:
        self._sync_turn()
        token = super().answer(vocab, what)
        kind = ask_kind(what)
        if kind == "attack" and token != "DECLINE":  # ATTACK (the player) or a planeswalker
            h = _handle(":".join(what.split(":")[1:3]))
            if h is not None:
                self._attackers.add(h)
        elif kind == "block" and token != "NONE":
            blocker = _handle(":".join(what.split(":")[1:3]))
            attacker = _handle(token)
            if blocker is not None and attacker is not None:
                self._blocks[blocker] = attacker
        return token

    def take_acts(self, game: Any, seat: Handle) -> None:
        super().take_acts(game, seat)
        # The pre-combat boundary: a driver that plans its combat (search.py) does it here,
        # with no engine call in flight.
        driver = self.drivers[self._index(seat)]
        plan = getattr(driver, "plan_combat", None)
        if plan is not None and game.over_reason() is None and game.executor.turn_open:
            plan(game, self._index(seat))

    def before_blocks(self, game: Any, seat: Handle) -> None:
        """The pre-blocks boundary (games._play, after ``seat``'s attack is declared): a
        defending driver that plans its blocks (search.py) does it here, no engine call in
        flight."""
        defender = 1 - self._index(seat)
        plan = getattr(self.drivers[defender], "plan_blocks", None)
        if plan is not None and game.over_reason() is None:
            self._sync_turn()
            plan(game, defender, self._declared_attackers())

    def _decide(self, driver: Any, ask: Any) -> int:
        self._sync_turn()
        st = self.stats[ask.seat]
        st["asks"] += 1
        st[f"ask:{ask.kind}"] += 1
        if ask.leaky:
            st["leaky_asks"] += 1
        picked = 0
        if ask.site.startswith("pick:"):
            tail = ask.site.rsplit(":", 1)[-1]
            picked = int(tail) if tail.isdigit() else 0
        ctx = AskContext(
            revealed=self._revealed if ask.kind == "scry" else None,
            declared_attackers=self._declared_attackers(),
            declared_blocks=dict(self._blocks),
            picked=picked,
        )
        obs = SPObservation(self.lenses[ask.seat], self.game.executor, ctx=ctx, game=self.game)
        idx = driver.decide(ask, obs)
        if not isinstance(idx, int) or not 0 <= idx < len(ask.options):
            raise AgentError(f"agent {getattr(driver, 'name', driver)!r} returned {idx!r} for {ask.site}")
        return idx


_ORACLES: dict[str, OracleIndex] = {}


def outcome_of(game: Any) -> tuple[str, int | None]:
    """('win', seat) | ('draw-cap'|'draw-stall'|'draw-mutual'|'draw-other', None)."""
    reason = game.reason or ""
    if reason.startswith("STALL"):
        return "draw-stall", None
    if reason.startswith("turn cap"):
        return "draw-cap", None
    order = game.world.player_order
    losers = [i for i, seat in enumerate(order) if game.is_loser(seat)]
    if len(losers) == 2:
        return "draw-mutual", None
    if len(losers) == 1:
        return "win", 1 - losers[0]
    return "draw-other", None


_ALLOWED: dict[tuple, Any] = {}


def allowed_supply(pool_mode: str, set_code: str, allow: frozenset | None) -> Any:
    """The set's supply, its non-land deck cards cut to ``allow`` (a curated list of oracle
    ids: e.g. new cards labelled faithful and simple). Lands are kept so deck recipes still find
    their basics. Cached per (mode, set, list)."""
    supply = get_supply(pool_mode, set_code)
    if not allow:
        return supply
    key = (pool_mode, set_code, hash(allow))
    if key not in _ALLOWED:
        deck = tuple(o for o in supply.deckable if supply.metas[o].is_land or o in allow)
        _ALLOWED[key] = replace(supply, deckable=deck)
    return _ALLOWED[key]


def play_game(seed: int, agents: list[Any], *, deck_mode: str = "stress",
              pool_mode: str = "castable", set_code: str = "M21", deck_pairs_seed: int = 1409,
              turn_cap: int = TURN_CAP, deck_allow: frozenset | None = None) -> dict[str, Any]:
    """Play one game between ``agents[0]`` (seat 0) and ``agents[1]`` (seat 1)."""
    supply = allowed_supply(pool_mode, set_code, deck_allow)
    oracle = _ORACLES.get(set_code)
    if oracle is None:
        oracle = _ORACLES[set_code] = OracleIndex.for_sets(set_code)
    game = _setup_game(seed, supply, deal_decks(seed, deck_pairs_seed, supply, deck_mode))
    router = SelfplayRouter(game, agents, [SeatLens(s, oracle, ViewOptions()) for s in (0, 1)],
                            supply=supply)
    started = time.monotonic()
    crash = None
    try:
        _play(game, router, game.world.player_order, turn_cap)
        outcome, winner = outcome_of(game)
    except AgentError as error:
        outcome, winner, crash = "void-agent", None, f"{type(error).__name__}: {error}"
    except Exception as error:  # noqa: BLE001 - an engine crash voids the game, never scores it
        outcome, winner, crash = "void-crash", None, f"{type(error).__name__}: {error}"
    leaky = sum(st.get("leaky_asks", 0) for st in router.stats)
    return {
        "seed": seed,
        "deck_mode": deck_mode,
        "outcome": outcome,
        "winner": winner,
        "reason": game.reason,
        "turns": game.turns,
        "crash": crash,
        "leaky": leaky,
        "asks": [st["asks"] for st in router.stats],
        "lives": [game.world.players[s].life for s in game.world.player_order],
        "wall_s": round(time.monotonic() - started, 3),
    }
