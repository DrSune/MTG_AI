"""The exact solver of a planning puzzle: the value of each first move, from the rules alone.

A puzzle (``puzzle.py``) is an arranged game at a decision of one seat, the decider, and a prior
over the opponent's hidden cards, ``world_prior``: worlds, each with its probability. The value of
a root option is

    max over the decider's pure strategies that begin with it
        of  sum over worlds w of  p(w) * (the value when, in w, the opponent best-responds)

A pure strategy is one action per decider information set. The decider sees what its seat sees
(the public game and its own cards: ``SeatLens``) and remembers its own decisions, so two
positions with the same observation and the same history of its own choices take the same action
whatever the world: the solver never lets the decider act on a card it cannot see (strategy
fusion). The opponent is given the whole world and the decider's strategy: it plays its best
reply in each world. That is the conservative reading of "the opponent knows its own cards": the
decider commits, the opponent is perfect. Puzzles that need mixing or bluffing are out of scope.

Values are the game's result where it ends inside the horizon (the decider wins: 1, loses or both
lose: 0); a game still running after the puzzle's last turn scores its ``objective``: ``win``
0 (only a win counts), ``survive`` 1 (only a loss counts against), ``result`` 0.5 (undecided, worth
less than a win and more than a loss). Never a network's value.

How (``Solver``). Every option of every decision, both seats, comes from the engine's own asks
(``EngineTree``): a position is a paused copy of the game plus the answers to give after resuming
it; a decision of the game loop's priority point (an ``act`` or ``priority`` ask: no engine call
in flight) is itself a pause point, every other ask (a target, an attacker, a blocker, a mode) is
replayed from the last pause point. The recursion works on groups of positions that the decider
cannot tell apart (one per world and per opponent line leading there): for each option of the
group it follows every opponent line to the decider's next decisions, groups those by
observation, and solves each group; a group's result is the set of Pareto-best value vectors (one
entry per member) its strategies reach. At an opponent's lines a member's value is the minimum
over its lines (the opponent chooses, knowing the world); at a group the decider picks one option
for all members. The root value of an option is the best prior-weighted vector it reaches. With
one world this is plain minimax. Cut-offs that keep it exact: a group stops at an option that
reaches the best value in every member, and a member stops at an opponent line that reaches the
worst value.

``fused`` solves each world on its own (the decider choosing per world): the naive solver, an
upper bound, kept for the tests that show where it is wrong.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from MTG_bot.bench.router import SeatRouter
from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
from MTG_bot.core.executor import GameOver
from MTG_bot.core.executor.games import TURN_CAP, _play
from MTG_bot.core.identity import Handle
from tools.search.fork import fork

#: The asks the game loop makes at a priority point (``SeatRouter.take_priority``): no engine call
#: is in flight, so a copy taken there resumes by asking the same decision again.
CLEAN_KINDS = ("act", "priority")
#: The value of a game still running after the puzzle's last turn, by objective.
OBJECTIVES = {"win": 0.0, "survive": 1.0, "result": 0.5}
LO, HI = 0.0, 1.0
_HANDLE = re.compile(r"\b(card|player|ability|emblem):(\d+)\b")


@dataclass(frozen=True)
class Terminal:
    value: float


@dataclass
class Decision:
    """A decision of ``seat``. ``options`` are its words (the decider's in canonical form, the
    same in every world it cannot tell apart), ``children`` the position after each, ``key`` the
    decider's observation (None for the opponent)."""

    seat: int
    options: tuple[str, ...]
    children: dict[str, Any]
    key: Any = None
    tokens: tuple[str, ...] = ()  # the engine's own words, in the order of ``options``
    kind: str = ""


@dataclass(frozen=True)
class Pos:
    """A paused game ``cp`` (never mutated: every run forks it) and the answers ``script`` to give
    after resuming it; ``hist`` the decider's own decisions so far, in canonical words."""

    cp: Any
    script: tuple[str, ...] = ()
    hist: tuple[str, ...] = ()


class Frontier(Exception):
    """The script is used up at a decision: the position ends there."""

    def __init__(self, ask: Any) -> None:
        super().__init__(ask.site)
        self.ask = ask


class Horizon(Exception):
    """A decision after the puzzle's last turn."""


class ScriptError(RuntimeError):
    """A scripted answer that the ask does not offer."""


class _Driver:
    """Both seats' answers in one script, one word per decision with more than one option (a
    single option is no decision, as for the network: ``actor.NetAgent``)."""

    name = "puzzle-script"

    def __init__(self, script: tuple[str, ...], last_turn: int) -> None:
        self.script = script
        self.i = 0
        self.last_turn = last_turn

    def decide(self, ask: Any, obs: Any) -> int:
        if obs.executor.world.turn > self.last_turn:
            raise Horizon()
        if len(ask.options) == 1:
            return 0
        if self.i < len(self.script):
            word = self.script[self.i]
            self.i += 1
            for j, option in enumerate(ask.options):
                if option.token == word:
                    return j
            raise ScriptError(f"{ask.site}: {word!r} is not offered: {[o.token for o in ask.options]}")
        raise Frontier(ask)


def canonical(text: str, lens: SeatLens, executor: Any) -> str:
    """``text`` (an option token or an ask site) with every handle replaced by what the seat's
    lens calls it: an object by its view id (assigned in the view's own order, so the same visible
    object has the same id in every world), a player by its seat."""
    order = executor.world.player_order

    def sub(m: re.Match) -> str:
        handle = Handle(m.group(1), int(m.group(2)))
        if m.group(1) == "player":
            return f"seat{order.index(handle)}" if handle in order else m.group(0)
        return lens.oid(handle)

    return _HANDLE.sub(sub, text)


class EngineTree:
    """The game tree of an arranged game, read from the engine's own asks (module docstring)."""

    def __init__(self, supply: Any, set_code: str, decider: int, last_turn: int,
                 objective: str) -> None:
        if objective not in OBJECTIVES:
            raise ValueError(f"objective {objective!r}: one of {sorted(OBJECTIVES)}")
        self.supply = supply
        self.oracle = OracleIndex.for_sets(set_code)
        self.decider = decider
        self.last_turn = last_turn
        self.undecided = OBJECTIVES[objective]
        self.runs = 0

    def _stop(self, game: Any, boundary: str) -> bool:
        return game.world.turn > self.last_turn

    def play(self, pos: Pos) -> tuple[Any, Exception | None]:
        """Resume a copy of ``pos.cp`` with its script: the copy, and the exception that stopped
        it (None when the game ended or reached the horizon at a boundary)."""
        self.runs += 1
        game = fork(pos.cp, self.supply)
        driver = _Driver(pos.script, self.last_turn)
        router = SeatRouter(game, [driver, driver],
                            [SeatLens(s, self.oracle, ViewOptions()) for s in (0, 1)],
                            supply=self.supply)
        stop: Exception | None = None
        try:
            _play(game, router, list(game.world.player_order), TURN_CAP, resumed=True,
                  stop_after=self._stop)
        except (Frontier, Horizon) as e:
            stop = e
        except GameOver:  # _play ends a game itself; a loss found outside it ends it the same
            pass
        return game, stop

    def value(self, game: Any) -> float:
        order = game.world.player_order
        losers = [s for s in order if game.is_loser(s)]
        if losers:
            return HI if losers == [order[1 - self.decider]] else LO
        return self.undecided

    def expand(self, pos: Pos) -> Terminal | Decision:
        game, stop = self.play(pos)
        if not isinstance(stop, Frontier):
            return Terminal(self.value(game))
        ask = stop.ask
        tokens = tuple(o.token for o in ask.options)
        if ask.kind in CLEAN_KINDS:  # a pause point: the copy itself, paused at this decision
            game.executor.decisions.provider = None
            base, prefix = game, ()
        else:
            base, prefix = pos.cp, pos.script
        if ask.seat != self.decider:
            return Decision(ask.seat, tokens, {t: Pos(base, prefix + (t,), pos.hist) for t in tokens},
                            tokens=tokens, kind=ask.kind)
        ex = game.executor
        lens = SeatLens(ask.seat, self.oracle, ViewOptions())
        view = lens.view(ex)
        words = tuple(canonical(t, lens, ex) for t in tokens)
        if len(set(words)) != len(words):
            raise ScriptError(f"{ask.site}: two options read the same to the seat: {words}")
        key = (repr(view), ex.passes, ask.kind, canonical(ask.site, lens, ex), words, pos.hist)
        children = {w: Pos(base, prefix + (t,), pos.hist + (w,)) for w, t in zip(words, tokens)}
        return Decision(ask.seat, words, children, key=key, tokens=tokens, kind=ask.kind)


def pareto(vectors: list[tuple[float, ...]]) -> list[tuple[float, ...]]:
    """The vectors no other one weakly dominates (duplicates once)."""
    front: list[tuple[float, ...]] = []
    for v in sorted(set(vectors), reverse=True):  # a dominating vector sorts before what it beats
        if not any(all(a >= b for a, b in zip(f, v)) for f in front):
            front.append(v)
    return front


@dataclass
class Solved:
    values: dict[str, float]  # root option word -> value
    fronts: dict[str, list[tuple[float, ...]]] = field(default_factory=dict)
    runs: int = 0  # engine runs (one fork and replay each)
    decisions: int = 0  # decider groups solved
    seconds: float = 0.0


class Solver:
    """The exact value of every root option (module docstring)."""

    def __init__(self, tree: Any) -> None:
        self.tree = tree
        self.decisions = 0

    def _collect(self, pos: Any) -> list[Terminal | Decision]:
        """Every end of the opponent's lines from ``pos``: results, and the decider's next
        decisions. Only the minimum, when a line reaches it: the opponent takes that line."""
        leaves: list[Terminal | Decision] = []
        stack = [pos]
        while stack:
            node = self.tree.expand(stack.pop())
            if isinstance(node, Terminal):
                if node.value <= LO:
                    return [node]
                leaves.append(node)
            elif node.seat == self.tree.decider:
                leaves.append(node)
            else:
                stack.extend(reversed(list(node.children.values())))
        return leaves

    def _option(self, members: list[Decision], word: str) -> list[tuple[float, ...]]:
        """The Pareto-best vectors (one entry per member) that playing ``word`` in every member
        reaches, the decider then playing on optimally per information set."""
        start = [HI] * len(members)
        groups: dict[Any, list[tuple[int, Decision]]] = {}
        for i, member in enumerate(members):
            for leaf in self._collect(member.children[word]):
                if isinstance(leaf, Terminal):
                    start[i] = min(start[i], leaf.value)
                else:
                    groups.setdefault(leaf.key, []).append((i, leaf))
        partial = [tuple(start)]
        for entries in groups.values():
            live = [(i, leaf) for i, leaf in entries if start[i] > LO]
            if not live:
                continue
            combined = []
            for gv in self._front([leaf for _, leaf in live]):
                for vec in partial:
                    v = list(vec)
                    for (i, _), x in zip(live, gv):
                        v[i] = min(v[i], x)
                    combined.append(tuple(v))
            partial = pareto(combined)
        return partial

    def _front(self, members: list[Decision]) -> list[tuple[float, ...]]:
        """The Pareto-best vectors a group of positions the decider cannot tell apart reaches."""
        self.decisions += 1
        options = members[0].options
        if any(m.options != options for m in members):
            raise ScriptError(f"one information set, different options: {[m.options for m in members]}")
        best = tuple([HI] * len(members))
        front: list[tuple[float, ...]] = []
        for word in options:
            front = pareto(front + self._option(members, word))
            if best in front:
                break
        return front

    def solve(self, roots: list[tuple[float, Any]]) -> Solved:
        """``roots``: (probability, root position) per world."""
        t0 = time.perf_counter()
        runs0 = getattr(self.tree, "runs", 0)
        members = [self.tree.expand(pos) for _, pos in roots]
        if not all(isinstance(m, Decision) and m.seat == self.tree.decider for m in members):
            seen = [m if isinstance(m, Terminal) else (m.seat, m.kind, m.options) for m in members]
            raise ScriptError(f"a root is not a decision of the decider, per world: {seen}")
        if len({m.key for m in members}) != 1:
            raise ScriptError("the worlds' roots look different to the decider: the prior "
                              "contradicts what it sees")
        values, fronts = {}, {}
        for word in members[0].options:
            fronts[word] = self._option(members, word)
            values[word] = max(sum(p * v for (p, _), v in zip(roots, vec)) for vec in fronts[word])
        return Solved(values, fronts, getattr(self.tree, "runs", 0) - runs0, self.decisions,
                      time.perf_counter() - t0)

    # ------------------------------------------------------------------ the naive solver

    def _minimax(self, pos: Any) -> float:
        node = self.tree.expand(pos)
        if isinstance(node, Terminal):
            return node.value
        if node.seat == self.tree.decider:
            best = LO
            for child in node.children.values():
                best = max(best, self._minimax(child))
                if best >= HI:
                    break
            return best
        worst = HI
        for child in node.children.values():
            worst = min(worst, self._minimax(child))
            if worst <= LO:
                break
        return worst

    def fused(self, roots: list[tuple[float, Any]]) -> dict[str, float]:
        """Each world solved alone, the decider choosing per world (strategy fusion): an upper
        bound on every option's value, and wrong where the decider must act without knowing."""
        values: dict[str, float] = {}
        for p, pos in roots:
            node = self.tree.expand(pos)
            for word, child in node.children.items():
                values[word] = values.get(word, 0.0) + p * self._minimax(child)
        return values


def main(argv: list[str] | None = None) -> int:
    from tools.puzzles import puzzle as P

    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--write", action="store_true", help="store the result in the puzzle file")
    args = ap.parse_args(argv)
    for path in args.paths:
        pz = P.load(path)
        res = P.solve(pz)
        print(json.dumps({"puzzle": pz["name"], **P.solver_record(pz, res)}, indent=1))
        if args.write:
            P.write_result(path, pz, res)
    return 0


if __name__ == "__main__":
    sys.exit(main())
