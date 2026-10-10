"""Rollout + single-step ask expansion over the REAL ``games._play`` loop.

KNOWLEDGE/2026-10-10/67. One driver, three roles, all through the SAME
production turn loop (``games._play`` with the additive ``resumed`` /
``stop_after`` hooks) — a forked search never forks the loop:

* ``rollout(position, policies, seed, turn_cap)`` plays the position out with
  a per-seat policy (importable ``RANDOM`` / ``GREEDY_TEACHER`` or any
  ``.decide(AskContext) -> int``), returning win/draw/undecided plus the
  observable life-diff signal at the cap.
* ``expand(position, seat)`` enumerates the seat's NEXT decision exactly: a
  throwaway probe fork discovers the ask (site, full legality-narrowed
  candidate list, global ask index), then one apply-fork per option forces
  that word at that ask and stops at the next CLEAN boundary.
* The clean stop points are the three ``_play`` boundaries (turn_top /
  pre_combat / post_combat) plus one rig-side unwind point: raising
  ``_StepComplete`` from a policy ``decide()`` is safe because every rig ask
  (act menu, target designation) happens OUTSIDE any executor call — the
  position stays consistent mid-act. Asks that fire INSIDE an executor call
  (combat declarations, mid-resolution may/choose) cannot unwind mid-call;
  those branches run the phase out to the next boundary and the target-seat
  asks answered on the way back as recorded ``continuations`` (multi-stage
  information exposed, never silently swallowed — the documented limit of
  clean unwinding, see module tests).

Determinism contract: discovery and every apply run share one driver seed
and the same default decider, the engine's randomness is the pure
``_rng(tag)`` sha256 factory over the forked ``_op_seq``, so all runs replay
an identical ask prefix and the global ask index found by discovery lands on
the same ask in every apply fork.
"""

from __future__ import annotations

import random
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from MTG_bot.core.executor.games import (
    Game,
    Supply,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)
from tools.eval.gameplay_eval_v2 import (
    HeuristicTeacher,
    PolicyActDriver,
    resolve_seat,
    site_kind,
)
from tools.search.fork import fork
from tools.training.ab_duel import snapshot_obs
from tools.training.collector import AskContext

# ------------------------------------------------------------------ policies


class RandomSeat:
    """Importable RANDOM policy: uniform over the legality-narrowed
    candidates the engine hands the ask, on a private stream seeded by
    (seed, seat) so two rollouts of one seed replay identically."""

    def __init__(self, seed: Any) -> None:
        self.rng = random.Random(f"random-seat:{seed}")

    def decide(self, ctx: AskContext) -> int:
        return self.rng.randrange(len(ctx.candidates))


GREEDY_TEACHER = HeuristicTeacher  # the shared deterministic greedy anchor
RANDOM = RandomSeat  # importable search policy marker


def _make_seat(spec: Any, seed: Any) -> Any:
    if spec is RANDOM or spec == "random":
        return RandomSeat(seed)
    if spec is GREEDY_TEACHER or spec == "greedy":
        return HeuristicTeacher()
    if not hasattr(spec, "decide"):
        raise TypeError(f"rollout: policy {spec!r} has no .decide(AskContext)")
    return spec


# ------------------------------------------------------------------ controls


class _StepComplete(BaseException):
    """Clean rig-side unwind: raised from a policy ``decide()`` at the
    target seat's next rig ask after the forced option was played.
    BaseException so no future rig-side ``except Exception`` can eat it."""


class _AskFound(BaseException):
    def __init__(self, rec: AskRec, ctx: AskContext) -> None:
        super().__init__(f"first ask of seat at index {rec.index}: {rec.site}")
        self.rec, self.ctx = rec, ctx


@dataclass(frozen=True)
class AskRec:
    """One ask as seen by the search driver (prefix / continuation ledger)."""

    index: int  # global ask index in this run (ALL seats, ALL lanes)
    site: str  # AskContext.vocab — the engine site name or "act:main"
    kind: str  # site_kind(): attack / block / cw / act / target / ...
    seat: int  # seat that was ASKED (engine attribution)
    lane: str  # "rig" (driver-side) or "engine" (provider stream)
    answer: str  # the word chosen


@dataclass(frozen=True)
class RolloutResult:
    result: str  # "seat0" | "seat1" | "draw" | "undecided" | "crash"
    winner: int | None
    reason: str  # engine stop reason (or crash:<Type>)
    turns: int
    lives: tuple[int, ...]
    life_diff: int  # lives[0] - lives[1]: the observable signal at the cap
    asks: int
    fingerprint: str


@dataclass(frozen=True)
class Expansion:
    option: str
    game: Game  # fork advanced past the option to the next clean boundary
    boundary: str  # where it stopped: mid_act | pre_combat | post_combat
    continuations: tuple[AskRec, ...]  # target-seat asks default-answered after
    prefix: tuple[AskRec, ...]  # asks default-answered before the target ask


@dataclass(frozen=True)
class Expansions:
    site: str
    kind: str
    seat: int
    options: tuple[Expansion, ...]

    @property
    def words(self) -> tuple[str, ...]:
        return tuple(o.option for o in self.options)


@dataclass
class Position:
    """A forkable search node plus the boundary it was taken at (how a
    rollout must resume the loop)."""

    game: Game
    supply: Supply
    boundary: str = "turn_top"  # turn_top | pre_combat | post_combat


# ------------------------------------------------------------------- driver


class SearchDriver(PolicyActDriver):
    """PolicyActDriver with one ask choke point and three modes (see module
    docstring). ``agents`` values are the per-seat :class:`_Routing` proxies;
    every ask of every lane funnels through ``_Routing.decide``."""

    def __init__(
        self,
        seed: int,
        default: Any,
        mode: str,  # rollout | discover | apply
        find_seat: int | None = None,
        target_index: int | None = None,
        option: str | None = None,
    ) -> None:
        super().__init__(seed, {})
        # coerce string specs so _wire's routing proxies always hold a decider
        self.default = _make_seat(default if default is not None else "greedy", seed)
        self.mode = mode
        self.find_seat = find_seat
        self.target_index = target_index
        self.option = option
        # site name of the forced ask — the desync tripwire read by _Routing
        self.log_site: str = ""
        # which clean boundary the apply run stopped at (expand bookkeeping)
        self.stop_boundary: str = ""
        self.ask_count = 0
        self.applied = False
        self.lane = "rig"
        self.log: list[AskRec] = []
        # discover/apply answer EVERY ask through the default decider;
        # rollout() replaces agents with the per-seat policies.
        self.agents: dict[int, Any] = {}


class _Routing:
    """Per-seat proxy — the single place an ask is counted, logged, forced,
    discovered, or answered by the seat's own policy."""

    def __init__(self, driver: SearchDriver, seat: int, policy: Any) -> None:
        self.driver, self.seat, self.policy = driver, seat, policy

    def decide(self, ctx: AskContext) -> int:
        d = self.driver
        g = d.ask_count
        kind = site_kind(ctx.vocab)
        if d.mode == "discover" and self.seat == d.find_seat:
            d.ask_count += 1
            raise _AskFound(AskRec(g, ctx.vocab, kind, self.seat, d.lane, "?"), ctx)
        if d.mode == "apply" and not d.applied and g == d.target_index:
            if ctx.vocab != d.log_site or d.option not in ctx.candidates:
                raise AssertionError(
                    f"search prefix desync at ask {g}: want {d.log_site!r}"
                    f"/{d.option!r}, got {ctx.vocab!r}/{ctx.candidates!r}"
                )
            idx = ctx.candidates.index(d.option)
            d.applied = True
        else:
            if (
                d.mode == "apply"
                and d.applied
                and self.seat == d.find_seat
                and d.lane == "rig"
                and ctx.vocab == "act:main"
            ):
                # The target seat's NEXT act-menu decision: no engine call is
                # in flight (the menu ask sits between acts), so unwinding
                # here leaves a consistent position mid-act-phase. A
                # target:select ask is NOT a stop — designating is part of
                # completing the applied act; it rides the default and is
                # recorded as a continuation.
                raise _StepComplete()
            idx = self.policy.decide(ctx)
        d.ask_count += 1
        d.log.append(AskRec(g, ctx.vocab, kind, self.seat, d.lane, ctx.candidates[idx]))
        return idx


# ------------------------------------------------------------------- running


def _wire(game: Game, driver: SearchDriver) -> None:
    """Provider lane exactly as ``run_v2_game`` wires it: engine asks get
    seat attribution from the site tag, the shared omniscient snapshot plus
    the ``_pt`` table, and go through the seat's routing proxy (lane
    ``engine``). ``driver.answer`` is what ``_play`` registers on the
    executor's DecisionStream."""
    world = game.world
    seats = [str(s) for s in world.player_order]
    # discover/apply seats ride the default decider; rollout seats were
    # registered with their own policies before wiring.
    for seat_idx in range(len(seats)):
        driver.agents.setdefault(seat_idx, _Routing(driver, seat_idx, driver.default))
    handle_words = {str(h) for h in world.cards} | set(seats)
    pt = {
        str(h): [world.cards[h].identity.power, world.cards[h].identity.toughness]
        for h in world.cards
    }

    def provider(vocab: tuple[str, ...], what: str) -> str:
        active = seats.index(str(world.active_player))
        seat = resolve_seat(what, game, seats, active, handle_words)
        obs = snapshot_obs(world, world.active_player)
        obs["_seat"] = seat
        obs["_pt"] = pt
        driver.lane = "engine"
        try:
            idx = driver.agents[seat].decide(
                AskContext(vocab=what, candidates=tuple(vocab), world=obs)
            )
        finally:
            driver.lane = "rig"
        return vocab[idx]

    driver.answer = provider  # type: ignore[method-assign]


def _run(
    game: Game,
    driver: SearchDriver,
    turn_cap: int,
    boundary: str,
    stop_after: Callable[[Game, str], bool] | None = None,
) -> None:
    if not game.executor.turn_open:
        raise ValueError(
            "_run resumes an ALREADY-OPEN turn (forked position); play a "
            "fresh game through _play(resumed=False) or play_position()"
        )
    if boundary == "pre_combat":
        game.skip_next_acts = True  # resume INSIDE an open turn, acts done
    elif boundary == "post_combat":
        game.skip_next_combat = True  # resume INSIDE, combat already resolved
    _play(
        game,
        driver,
        list(game.world.player_order),
        turn_cap,
        resumed=True,
        stop_after=stop_after,
    )


_ROLL_STOP = None  # rollouts run the loop's own terminal conditions


def rollout(
    state: Any,
    policies: Any,
    seed: int,
    turn_cap: int = 60,
) -> RolloutResult:
    """Play ``state`` (a :class:`Position` or a bare forked ``Game`` at a
    turn-top boundary) out by at most ``turn_cap`` turns through ``_play``.

    ``policies``: one spec for both seats or a dict ``{seat: spec}``; specs are
    ``"random"``/``RANDOM``, ``"greedy"``/``GREEDY_TEACHER`` (the shared
    HeuristicTeacher), or any object with ``.decide(AskContext) -> int``.
    Crashes are recorded in ``reason`` as ``crash:<Type>: msg`` — a search
    must never die with its branch.
    """
    game, _supply, boundary = _as_position(state)
    if game.over_reason() is not None:
        return _outcome(game, 0, boundary)
    n = len(game.world.player_order)
    specs = policies if isinstance(policies, dict) else {i: policies for i in range(n)}
    driver = SearchDriver(seed, None, "rollout")
    driver.agents = {
        seat: _Routing(driver, seat, _make_seat(specs[seat], f"{seed}:{seat}"))
        for seat in range(n)
    }
    _wire(game, driver)
    start = game.world.turn
    try:
        _run(game, driver, start + turn_cap, boundary, _ROLL_STOP)
    except BaseException as error:  # noqa: BLE001 - carried, never hidden
        return _outcome(game, driver.ask_count, boundary, error=error)
    return _outcome(game, driver.ask_count, boundary)


def _as_position(state: Any) -> tuple[Game, Supply | None, str]:
    if isinstance(state, Position):
        return state.game, state.supply, state.boundary
    if isinstance(state, Game):
        return state, None, "turn_top"
    raise TypeError(f"rollout: expected Position or Game, got {type(state).__name__}")


def _outcome(
    game: Game, asks: int, boundary: str, error: BaseException | None = None
) -> RolloutResult:
    world = game.world
    try:
        lives = tuple(world.players[s].life for s in world.player_order)
    except Exception:  # noqa: BLE001 - half-crashed worlds may not read
        lives = ()
    diff = (lives[0] - lives[1]) if len(lives) >= 2 else 0
    if error is not None:
        return RolloutResult(
            "crash",
            None,
            f"crash:{type(error).__name__}: {error}",
            game.turns,
            lives,
            diff,
            asks,
            "",
        )
    losers = [
        s
        for s, h in zip(range(len(world.player_order)), world.player_order, strict=True)
        if game.is_loser(h)
    ]
    if len(losers) >= 2:
        result, winner = "draw", None
    elif losers:
        result, winner = f"seat{1 - losers[0]}", 1 - losers[0]
    else:
        result, winner = "undecided", None
    try:
        fp = game.executor.state_fingerprint()
    except Exception:  # noqa: BLE001
        fp = ""
    return RolloutResult(result, winner, game.reason, game.turns, lives, diff, asks, fp)


# ------------------------------------------------------------------ expansion

_EXPLORE_HORIZON = 8  # internal turn budget to reach the seat's next ask


def expand(
    state: Any,
    seat: int,
    default: Any = "greedy",
    horizon: int = _EXPLORE_HORIZON,
) -> Expansions:
    """The seat's next decision, fully enumerated.

    Discovery (throwaway fork, all-default play) finds the FIRST ask
    attributed to ``seat`` and its exact candidate list; each option then
    gets its own fork where that ask — same global index, same site, same
    candidates (deterministic shared prefix) — is answered with the option
    word while every later ask is default-answered until a clean boundary.
    The input state is never touched (it is only ever forked).
    """
    game, supply, boundary = _as_position(state)
    if game.over_reason() is not None:
        return Expansions("", "over", seat, ())
    # ONE driver seed for discovery and every apply fork: the shared default
    # decider plus the pure _rng factory replay an identical ask prefix in
    # every run, so the discovered global ask index lands on the same ask.
    drv_seed = game.seed * 1_000_003 + seat
    decider = _make_seat(default, "default")

    found: _AskFound | None = None
    probe = fork(game, supply)
    find = SearchDriver(drv_seed, decider, "discover", find_seat=seat)
    _wire(probe, find)
    try:
        _run(probe, find, probe.world.turn + horizon, boundary)
    except _AskFound as exc:
        found = exc
    except BaseException:  # noqa: BLE001 - probe is throwaway: no ask to trust
        return Expansions("", "error", seat, ())
    if found is None:  # horizon exhausted / game ended: no seat ask in reach
        return Expansions("", "none", seat, ())
    info, ctx = found.rec, found.ctx

    cap = game.world.turn + horizon
    options: list[Expansion] = []
    for word in ctx.candidates:
        branch = fork(game, supply)
        drv = SearchDriver(
            drv_seed,
            _make_seat(default, "default"),
            "apply",
            find_seat=seat,
            target_index=info.index,
            option=word,
        )
        drv.log_site = info.site  # desync tripwire read by _Routing on force
        _wire(branch, drv)

        def stop(_g: Game, b: str, drv: SearchDriver = drv) -> bool:
            if drv.applied and b in ("pre_combat", "post_combat", "turn_top"):
                drv.stop_boundary = b
                return True
            return False

        try:
            _run(branch, drv, cap, boundary, stop)
        except _StepComplete:
            drv.stop_boundary = "mid_act"  # seat's next menu ask: clean stop
        if not drv.applied:
            raise AssertionError(
                f"expand: forced ask {info.index}@{info.site!r} was never"
                f" reached in the apply fork (option {word!r})"
            )
        continuations = tuple(
            r for r in drv.log if r.seat == seat and r.index > info.index
        )
        prefix = tuple(r for r in drv.log if r.index < info.index)
        options.append(
            Expansion(word, branch, drv.stop_boundary, continuations, prefix)
        )
    return Expansions(info.site, info.kind, seat, tuple(options))


# ----------------------------------------------------------------- positions


def play_position(
    seed: int,
    at_turn: int,
    boundary: str = "turn_top",
    pool_mode: str = "engine",
    deck_pairs_seed: int = 1409,
    policies: Any = "greedy",
) -> Position:
    """Deal a fresh seeded game and drive it with GREEDY teachers until the
    first ``boundary`` of turn ``at_turn`` — the midgame positions the search
    substrate is built and benched on."""
    if boundary not in ("turn_top", "pre_combat", "post_combat"):
        raise ValueError(f"unknown boundary {boundary!r}")
    supply = get_supply(pool_mode)
    decks = deal_decks(seed, deck_pairs_seed, supply)
    game = _setup_game(seed, supply, decks)
    n = len(game.world.player_order)
    specs = policies if isinstance(policies, dict) else {i: policies for i in range(n)}
    driver = SearchDriver(seed, None, "rollout")
    driver.agents = {
        seat: _Routing(driver, seat, _make_seat(specs[seat], f"{seed}:{seat}"))
        for seat in range(n)
    }
    _wire(game, driver)

    def stop(g: Game, b: str) -> bool:
        return b == boundary and g.world.turn >= at_turn

    _play(
        game,
        driver,
        list(game.world.player_order),
        at_turn + 12,
        resumed=False,
        stop_after=stop,
    )
    if game.world.turn < at_turn:
        raise RuntimeError(
            f"seed {seed}: game ended ({game.reason}) before turn {at_turn}"
        )
    return Position(game, supply, boundary)


# ---------------------------------------------------------------------- bench


def _bench() -> None:  # pragma: no cover - measurement entry point
    """Fork / step / rollout timings + the replay-prefix crossover check."""
    seed = 20261010
    pos = play_position(seed, at_turn=12, boundary="turn_top")
    game, supply = pos.game, pos.supply
    n_forks = 20
    t0 = time.perf_counter()
    for _ in range(n_forks):
        fork(game, supply)
    fork_ms = (time.perf_counter() - t0) * 1000 / n_forks

    # replay-prefix rebuild of the same position (the alternative mechanism)
    t0 = time.perf_counter()
    play_position(seed, at_turn=12, boundary="turn_top")
    replay_ms = (time.perf_counter() - t0) * 1000

    xs = expand(Position(game, supply, "turn_top"), seat=game.world.turn % 2)
    t0 = time.perf_counter()
    xs2 = expand(Position(game, supply, "turn_top"), seat=game.world.turn % 2)
    step_ms = (time.perf_counter() - t0) * 1000 / max(1, len(xs2.options))

    n_roll = 20
    last = ""
    t0 = time.perf_counter()
    for i in range(n_roll):
        r = rollout(fork(game, supply), "random", seed * 977 + i, turn_cap=60)
        last = f"{r.result}/{r.reason}"
    rollout_ms = (time.perf_counter() - t0) * 1000 / n_roll
    import os

    print(f"cores={os.cpu_count()}")
    print(f"fork_ms={fork_ms:.2f}")
    print(f"replay_prefix_ms={replay_ms:.1f}  (crossover x{replay_ms / fork_ms:.0f})")
    print(f"expand_option_step_ms={step_ms:.1f}  site={xs.site}/{xs.kind}")
    print(f"rollout_ms(random, cap60)={rollout_ms:.1f}  last={last}")
    print(f"rollouts_per_sec_per_core={1000 / rollout_ms:.2f}")


if __name__ == "__main__":  # pragma: no cover
    _bench()
