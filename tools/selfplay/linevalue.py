"""The value of a line of play: instrument 1 of docs/PLAN_CEILING.md §14.2.

The policy gradient sees only what the policy already tries: for a line it never plays it reads
about 0, whatever the line is worth. This measures the line's value directly, against the policy
as it is, beside how often the policy plays it. A positive value with near-zero use is an
exploration barrier: that is where forcing the line pays (§14.3).

A line (``Line``) is a predicate: at a decision, the options that are its next step, or none.
Two families, with no card names in code:
- ``cast_line(ids)``: cast a card (or play a land) whose oracle id is in ``ids``, whenever it can;
- ``order_line(consumers, producers)``: a consumer before its producers (two sets of oracle ids,
  e.g. a package's payoffs and enablers). While no consumer is on the player's battlefield, cast
  one where a producer could be cast instead: the order is the decision, and the line begins
  there. Once one is there, cast the producers: the line's follow-through.

The procedure (``run``: ``Probe.collect``, then ``Probe.measure``):
1. Games of one checkpoint against itself on coherent decks. At every act or priority decision
   the network makes where a step would begin the line, the policy's probability of the step is
   counted, and a copy of the position is kept: at most ``per_game`` per game, drawn uniformly
   (a reservoir, as the labeller's).
2. At each kept state, ``futures`` futures. In each, three branches from the same copy: B
   ("policy"), the policy chooses; A1 ("first"), the step forced, the policy plays on; A*
   ("through"), the step and every later step of the line forced when legal. The policy plays
   everything else, the opponent included, to the end of the game: the labeller's machinery at
   horizon 0 (``search.play_out``, ``SimAgent``, ``outcome``).
3. Reported (``summarise``): the line's value, A1 - B and A* - B, each a paired mean over a
   state's futures with its standard error over states (a future in which any branch crashed is
   left out for all three, ``search.mean_scores``); the unforced frequency (the policy's
   probability of the step, and how often it is its top choice); the follow-through (in A1, how
   often the policy itself takes the line's later steps, beside B); and the value head's reading
   at the seat's next ``tops`` turn tops, the leaf a horizon-h search reads
   (``Searcher.leaf_value``; the result once the game is over), against the realised result:
   does the critic see the line?

Shared futures. A future is the true hidden cards (a measurement, not a decision: nothing here
plays a move in a real game), both libraries reshuffled (``search.reshuffle_libraries``) and a
new engine seed: the audit's "true" worlds. Every branch of a state meets the same futures. In
sampled play (the default, the training policy) each seat draws its moves from one stream per
future, shared by the branches, and a forced move spends the draw the policy's own move would
have, so the streams stay aligned: a line whose step is whatever the policy picks reads exactly 0.
A step with several options (X, kicker) is forced as the policy's own choice among them.

    .venv/bin/python -m tools.selfplay.linevalue CKPT --cast "Chrome Replicator" --states 30 \
        --futures 3 --out lv.json
    .venv/bin/python -m tools.selfplay.linevalue CKPT --consumer "Vito, Thorn of the Dusk Rose" \
        --producer Revitalize ...
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import torch

from MTG_bot.core.executor.games import get_supply
from MTG_bot.core.state import ZONE_BATTLEFIELD
from MTG_bot.utils.rng import seed_all, substream
from tools.search.fork import fork
from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay import packages as PK
from tools.selfplay import search as S
from tools.selfplay.rig import play_game

#: B, A1, A*: who chooses at the line's steps.
BRANCHES = ("policy", "first", "through")
SPEC = "net"


@dataclass(frozen=True)
class Line:
    """A line of play: ``step(ask, obs)`` gives the indices of ``ask``'s options that are the
    line's next step at that decision ([]: none here). ``begins(ask, obs)``: whether a step there
    begins the line (None: every step does); only those decisions are measured, the later steps
    being its follow-through."""

    name: str
    step: Callable[[Any, Any], list[int]]
    begins: Callable[[Any, Any], bool] | None = None


def plays(ex: Any, options: tuple, ids: frozenset) -> list[int]:
    """The options that cast a card from hand, or play it as a land, whose oracle id is in
    ``ids`` (the router's ``cast:<card>[:k][:x<N>]`` and ``land:<card>`` rows)."""
    out = []
    for i, o in enumerate(options):
        kind, _, rest = o.token.partition(":")
        h = FT._handle(rest) if kind in ("cast", "land") else None
        if h is not None and ex.world.cards[h].identity.oracle_id in ids:
            out.append(i)
    return out


def controls(ex: Any, me: Any, ids: frozenset) -> bool:
    """Whether ``me`` controls a permanent whose oracle id is in ``ids``."""
    world = ex.world
    return any(world.cards[h].identity.oracle_id in ids and ex.controller_of(h) == me
               for p in world.player_order for h in world.players[p].zone(ZONE_BATTLEFIELD).entries)


def cast_line(ids: frozenset, name: str) -> Line:
    return Line(f"cast {name}", lambda ask, obs: plays(obs.executor, ask.options, ids))


def order_line(consumers: frozenset, producers: frozenset, name: str) -> Line:
    def begins(ask: Any, obs: Any) -> bool:
        return not controls(obs.executor, obs.executor.world.player_order[ask.seat], consumers)

    def step(ask: Any, obs: Any) -> list[int]:
        if not begins(ask, obs):
            return plays(obs.executor, ask.options, producers)
        ex = obs.executor
        return plays(ex, ask.options, consumers) if plays(ex, ask.options, producers) else []

    return Line(name, step, begins)


class LineAgent(S.SimAgent):
    """A network seat that plays as ``SimAgent`` and meets the line at its act and priority
    decisions. ``force``: "policy" (the policy chooses), "first" (the root's step forced) or
    "through" (every step forced). ``root``: the kept decision's option tokens, which a copy asks
    first. ``watch(ask, obs, step, top, value, probs, pick)`` sees every decision where a step
    would begin the line."""

    def __init__(self, slot: Any, gid: int, spec: str, table: FT.CardTable, rng: Any,
                 line: Line, force: str = "policy", root: tuple | None = None,
                 watch: Callable | None = None) -> None:
        super().__init__(slot, gid, spec, table, rng)
        self.line, self.force, self.root, self.watch = line, force, root, watch
        self.played: str | None = None  # the root's answer
        self.later: list[tuple[bool, bool, float]] = []  # after the root: (forced, a step, p(step))

    def decide(self, ask: Any, obs: Any) -> int:
        n = len(ask.options)
        if (ask.kind not in S.SEARCH_KINDS or n == 1 or n > FT.MAX_OPTIONS
                or self.decisions >= S.MAX_SIM_DECISIONS):
            return super().decide(ask, obs)
        root = self.root is not None and self.played is None
        step = self.line.step(ask, obs)
        if root and (tuple(o.token for o in ask.options) != self.root or not step):
            raise RuntimeError(f"a copy did not resume at its kept decision ({ask.site})")
        if not step:
            return super().decide(ask, obs)
        self.decisions += 1
        feats = FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx)
        top, value, probs = self.slot.infer((self.gid, ask.seat, self.spec, True, False, feats, 2))
        forced = self.force == "through" or (root and self.force == "first")
        pick = self._pick(int(top), probs, set(step) if forced else None)
        if root:
            self.played = ask.options[pick].token
        else:
            self.later.append((forced, pick in step, sum(probs[i] for i in step)))
        if self.watch is not None and (self.line.begins is None or self.line.begins(ask, obs)):
            self.watch(ask, obs, step, int(top), float(value), probs, pick)
        return pick

    def _pick(self, top: int, probs: list[float], among: set | None) -> int:
        """The policy's move (``among`` None), or its choice among the step's options ``among``.
        Sampled play spends one draw either way, as ``SimAgent`` does, so a forced move leaves
        the stream where the policy's move would have."""
        if self.rng is None:
            return top if among is None or top in among else max(sorted(among), key=probs.__getitem__)
        w = probs if among is None else [p if i in among else 0.0 for i, p in enumerate(probs)]
        if sum(w) <= 0.0:  # the step's probability underflowed: uniform over it
            w = [float(i in among) for i in range(len(probs))]
        return self.rng.choices(range(len(probs)), w)[0]


@dataclass
class State:
    """A kept decision: a copy of the game there (no decision provider), its deal, its rank ``n``
    among the game's decisions where a step would begin the line, and the policy's reading of it."""

    game: Any
    deal: int
    n: int
    seat: int
    turn: int
    tokens: tuple
    step: list[int]
    probs: list[float]
    value: float


class _Reservoir:
    """The watch of a collection game: the policy's use of the step at every decision where a
    step would begin the line, and copies of at most ``size`` of those, drawn uniformly
    (Algorithm R)."""

    def __init__(self, deal: int, size: int, supply: Any) -> None:
        self.deal, self.size, self.supply = deal, size, supply
        self.rng = substream("probe", "linevalue", deal)
        self.kept: list[State] = []
        self.use: Counter = Counter()

    def __call__(self, ask: Any, obs: Any, step: list[int], top: int, value: float,
                 probs: list[float], pick: int) -> None:
        u = self.use
        u["eligible"] += 1
        u["p_step"] += sum(probs[i] for i in step)
        u["top"] += top in step
        u["played"] += pick in step
        n = u["eligible"]
        j = n - 1 if n <= self.size else self.rng.randrange(n)
        if j < self.size:
            st = State(S.fork_live(obs.game, self.supply), self.deal, n, ask.seat,
                       obs.executor.world.turn, tuple(o.token for o in ask.options), list(step),
                       list(probs), value)
            self.kept[j:j + 1] = [st]


class _Timed:
    """A slot that adds up its inference time (the cost report)."""

    def __init__(self, inner: Any) -> None:
        self.inner, self.s, self.calls = inner, 0.0, 0

    def infer(self, req: tuple) -> Any:
        t = time.perf_counter()
        out = self.inner.infer(req)
        self.s += time.perf_counter() - t
        self.calls += 1
        return out


class Probe:
    """One line measured against one network (``slot`` answers for ``SPEC``): ``collect`` the
    states, ``measure`` their branches. Every random draw comes from ``rng.substream``, keyed by
    the deal, the state and the future, so the same master seed gives the same numbers."""

    def __init__(self, slot: Any, table: FT.CardTable, line: Line, *, pool_mode: str = "verified",
                 set_code: str = "M21", greedy: bool = False, tops: int = 3,
                 package: Any = None) -> None:
        self.slot, self.table, self.line = _Timed(slot), table, line
        self.pool_mode, self.set_code, self.greedy, self.tops = pool_mode, set_code, greedy, tops
        self.supply = get_supply(pool_mode, set_code)
        self.package = package  # packages.Package: both decks of every deal built around it
        # its leaf_value is the value a horizon-h search reads at a turn top
        self.leaf = S.Searcher(self.slot, 0, SPEC, table, pool_mode=pool_mode, set_code=set_code)

    def _draws(self, *key: Any) -> Any:
        return None if self.greedy else substream("policy", "linevalue", *key)

    def _decks(self, deal: int) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
        """Both decks built around ``self.package`` from the deal's seed alone (as
        packages.package_decks deals a random package's), or None: coherent decks."""
        if self.package is None:
            return None
        rng = substream("deckbuild", "linevalue", deal)
        first, second = (PK.build(rng.randrange(1 << 40), self.supply, [self.package])[1] for _ in range(2))
        return first, second

    def collect(self, states: int, per_game: int, games: int, deal0: int) -> tuple[list[State], Counter]:
        """Play the network against itself, deal by deal from ``deal0``, until ``states``
        positions where the line has a step are kept, or ``games`` games are played: the kept
        states, and the policy's use of the step at every such decision. A game the engine
        voids counts for nothing."""
        kept: list[State] = []
        use: Counter = Counter()
        for deal in range(deal0, deal0 + games):
            if len(kept) >= states:
                break
            res = _Reservoir(deal, per_game, self.supply)
            agents = [LineAgent(self.slot, 0, SPEC, self.table, self._draws("collect", deal, s),
                                self.line, watch=res) for s in (0, 1)]
            out = play_game(deal, agents, deck_mode="package" if self.package else "coherent",
                            pool_mode=self.pool_mode, set_code=self.set_code, decks=self._decks(deal))
            use["games"] += 1
            use["decisions"] += sum(a.decisions for a in agents)
            use["rails"] += sum(a.decisions >= S.MAX_SIM_DECISIONS for a in agents)
            if out["crash"] is not None:
                use["voided"] += 1
                continue
            use.update(res.use)
            kept += sorted(res.kept, key=lambda st: st.n)
        return kept[:states], use

    def measure(self, states: list[State], futures: int) -> list[dict]:
        """Each state's three branches on ``futures`` shared futures: one row per state."""
        return [state_row(st, {b: [self.branch(st, b, f) for f in range(futures)]
                               for b in BRANCHES}) for st in states]

    def branch(self, st: State, force: str, f: int) -> dict:
        """One branch of ``st`` played to the end in future ``f``: its result, the value head's
        readings at the seat's next turn tops, the root's answer and the line's later steps."""
        key = (st.deal, st.n, f)
        clone = fork(st.game, self.supply)
        clone.world.master_seed = substream("engine", "linevalue", *key).randrange(1 << 62)
        S.reshuffle_libraries(clone, substream("shuffle", "linevalue", *key))
        me = LineAgent(self.slot, 0, SPEC, self.table, self._draws(*key, st.seat), self.line,
                       force, st.tokens)
        agents = [me if s == st.seat else S.SimAgent(self.slot, 0, SPEC, self.table,
                                                     self._draws(*key, s)) for s in (0, 1)]
        seat, reads = clone.world.player_order[st.seat], []

        def read(g: Any, boundary: str) -> bool:  # play_out's stop_after: reads, never stops
            if (boundary == "turn_top" and g.world.active_player == seat and g.world.turn > st.turn
                    and len(reads) < self.tops):
                router = g.executor.decisions.provider.__self__  # play_out's (games._play registers it)
                reads.append(self.leaf.leaf_value(router, S.fork_live(g, self.supply), st.seat))
            return False

        router = S.play_out(clone, agents, self.supply, self.set_code, read)
        z = None if isinstance(router, Exception) else S.outcome(clone, st.seat)
        if z is None:
            return {"crash": type(router).__name__ if isinstance(router, Exception) else "no result"}
        return {"z": z, "reads": reads + [z] * (self.tops - len(reads)), "root": me.played,
                "later": me.later, "decisions": sum(a.decisions for a in agents),
                "rail": any(a.decisions >= S.MAX_SIM_DECISIONS for a in agents)
                or (clone.reason or "").startswith(("turn cap", "STALL"))}


def state_row(st: State, runs: dict[str, list[dict]]) -> dict:
    """One state's numbers: per branch the mean result and readings over the futures every
    branch finished, the root's answers, the line's later steps, and the cost."""
    def means(get: Callable[[dict], float]) -> dict | None:
        return S.mean_scores({b: [get(r) if "z" in r else None for r in runs[b]] for b in BRANCHES})

    done = [r for b in BRANCHES for r in runs[b] if "z" in r]
    z = means(lambda r: r["z"])
    tops = len(done[0]["reads"]) if done else 0
    return {
        "deal": st.deal, "n": st.n, "seat": st.seat, "turn": st.turn, "value": st.value,
        "step": [st.tokens[i] for i in st.step],
        "top": st.tokens[max(range(len(st.probs)), key=st.probs.__getitem__)],
        "p_step": sum(st.probs[i] for i in st.step),
        "futures": sum(all("z" in runs[b][f] for b in BRANCHES) for f in range(len(runs["policy"]))),
        "z": z, "reads": [means(lambda r, h=h: r["reads"][h]) for h in range(tops)] if z else [],
        "root": {b: [r.get("root") for r in runs[b]] for b in BRANCHES},
        "later": {b: [r["later"] for r in runs[b] if "z" in r] for b in BRANCHES},
        "crashes": [r["crash"] for b in BRANCHES for r in runs[b] if "crash" in r],
        "playouts": len(done), "decisions": sum(r["decisions"] for r in done),
        "rails": sum(r["rail"] for r in done),
    }


def _mean_se(xs: list[float]) -> dict:
    n = len(xs)
    m = sum(xs) / n if n else None
    se = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1) / n) if n > 1 else None
    return {"mean": m, "se": se, "n": n}


def summarise(rows: list[dict], use: Counter) -> dict:
    """The report: the line's value, its unforced use, the follow-through and the critic."""
    done = [r for r in rows if r["z"]]
    tops = max((len(r["reads"]) for r in done), default=0)
    critic = [{"turn_top": h + 1,
               **{b: _mean_se([r["reads"][h][b] - r["reads"][h]["policy"] for r in done])
                  for b in BRANCHES[1:]},
               "through_level": _mean_se([r["reads"][h]["through"] for r in done])["mean"]}
              for h in range(tops)]

    def later(b: str) -> dict:
        runs = [run for r in rows for run in r["later"][b]]
        steps = [s for run in runs for s in run]
        n = len(steps)
        return {"playouts": len(runs), "with_a_step": sum(bool(run) for run in runs),
                "steps": n, "forced": sum(s[0] for s in steps),
                "taken": sum(s[1] for s in steps) / n if n else None,
                "p_step": sum(s[2] for s in steps) / n if n else None}

    roots = [(p, a) for r in rows for p, a in zip(r["root"]["policy"], r["root"]["first"])
             if p is not None and a is not None]
    stepped = [p in r["step"] for r in rows for p in r["root"]["policy"] if p is not None]
    e = use["eligible"]
    return {
        "states": len(rows), "measured": len(done),
        "value": {b: _mean_se([r["z"][b] - r["z"]["policy"] for r in done]) for b in BRANCHES[1:]},
        "result": {b: _mean_se([r["z"][b] for r in done])["mean"] for b in BRANCHES},
        "unforced": {
            "games": use["games"], "voided": use["voided"], "eligible": e,
            "p_step": use["p_step"] / e if e else None, "top": use["top"] / e if e else None,
            "played": use["played"] / e if e else None,
            "states_p_step": _mean_se([r["p_step"] for r in rows])["mean"],
            "states_top": _mean_se([float(r["top"] in r["step"]) for r in rows])["mean"],
            "b_root_played": sum(stepped) / len(stepped) if stepped else None},
        "root_changed": sum(p != a for p, a in roots) / len(roots) if roots else None,
        "follow": {b: later(b) for b in BRANCHES},
        "critic": critic,
        "crashes": dict(Counter(c for r in rows for c in r["crashes"])),
        "playouts": sum(r["playouts"] for r in rows), "rails": sum(r["rails"] for r in rows),
        "decisions_per_playout": (sum(r["decisions"] for r in rows)
                                  / max(1, sum(r["playouts"] for r in rows))),
    }


def run(probe: Probe, *, states: int, per_game: int, games: int, deal0: int,
        futures: int) -> dict:
    """Collect, measure and summarise, with the cost of each phase."""
    t0 = time.perf_counter()
    kept, use = probe.collect(states, per_game, games, deal0)
    t1 = time.perf_counter()
    probe.slot.s, probe.slot.calls = 0.0, 0
    rows = probe.measure(kept, futures)
    t2 = time.perf_counter()
    sf = sum(r["futures"] for r in rows)
    return {"line": probe.line.name, "futures": futures, "greedy": probe.greedy,
            **summarise(rows, use),
            "cost": {"collect_s": t1 - t0, "collect_games": use["games"],
                     "collect_decisions": use["decisions"], "collect_rails": use["rails"],
                     "measure_s": t2 - t1,
                     "state_futures": sf, "per_state_future_s": (t2 - t1) / sf if sf else None,
                     "infer_calls": probe.slot.calls,
                     "infer_ms": 1000 * probe.slot.s / probe.slot.calls if probe.slot.calls else None,
                     "infer_share": probe.slot.s / (t2 - t1) if t2 > t1 else None},
            "per_state": rows}


def _f(x: Any, fmt: str = "+.3f") -> str:
    return "-" if x is None else format(x, fmt)


def table(rep: dict) -> str:
    """The report in a few lines."""
    v, u, fo, k = rep["value"], rep["unforced"], rep["follow"], rep["cost"]
    lines = [
        (f"line {rep['line']!r}: {rep['states']} states ({rep['measured']} measured), "
         f"{rep['futures']} futures each, {'greedy' if rep['greedy'] else 'sampled'} play"),
        (f"value     A1 - B {_f(v['first']['mean'])} +- {_f(v['first']['se'], '.3f')}   "
         f"A* - B {_f(v['through']['mean'])} +- {_f(v['through']['se'], '.3f')}   (mean result "
         + ", ".join(f"{b} {_f(rep['result'][b])}" for b in BRANCHES) + ")"),
        (f"unforced  {u['eligible']} decisions with a step in {u['games']} games ({u['voided']} void): "
         f"p(step) {_f(u['p_step'], '.3f')}, the top choice {_f(u['top'], '.3f')}, played "
         f"{_f(u['played'], '.3f')}; at the states p {_f(u['states_p_step'], '.3f')}, B's root "
         f"played it {_f(u['b_root_played'], '.3f')}; A's root differs from B's {_f(rep['root_changed'], '.3f')}"),
        (f"follow    after a forced first step the policy took {_f(fo['first']['taken'], '.3f')} of "
         f"{fo['first']['steps']} later steps (in {fo['first']['with_a_step']} of "
         f"{fo['first']['playouts']} playouts; p {_f(fo['first']['p_step'], '.3f')}); B took "
         f"{_f(fo['policy']['taken'], '.3f')} of {fo['policy']['steps']}; A* forced {fo['through']['forced']}"),
    ]
    for c in rep["critic"]:
        lines.append(f"critic    turn top {c['turn_top']}: A1 - B {_f(c['first']['mean'])} +- "
                     f"{_f(c['first']['se'], '.3f')}   A* - B {_f(c['through']['mean'])} +- "
                     f"{_f(c['through']['se'], '.3f')}   A* {_f(c['through_level'])}")
    lines.append(f"cost      collect {k['collect_s']:.0f} s ({k['collect_games']} games); measure "
                 f"{k['measure_s']:.0f} s, {_f(k['per_state_future_s'], '.1f')} s per state x future "
                 f"({len(BRANCHES)} playouts of {rep['decisions_per_playout']:.0f} network decisions; "
                 f"inference {_f(k['infer_ms'], '.1f')} ms a call, {_f(k['infer_share'], '.2f')} of the "
                 f"time); crashes {rep['crashes']}, rails {rep['rails']}")
    return "\n".join(lines)


def _ids(names: list[str], supply: Any) -> frozenset:
    by_name = {m.name: o for o, m in supply.metas.items()}
    out = set()
    for n in names:
        if n not in supply.metas and n not in by_name:
            raise SystemExit(f"{n!r} is neither an oracle id nor a card name of the dealt pool")
        out.add(n if n in supply.metas else by_name[n])
    return frozenset(out)


def main(argv: list[str] | None = None) -> dict:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("ckpt", help="the policy: plays both seats of every game and playout")
    p.add_argument("--cast", action="append", default=[], help="family (a): a card name or oracle id")
    p.add_argument("--consumer", action="append", default=[], help="family (b): a consumer")
    p.add_argument("--producer", action="append", default=[], help="family (b): a producer")
    p.add_argument("--package", default="", help="deal both decks around the package with this label "
                   "(packages.label, e.g. 'life'); with no --cast/--consumer, its consumers before its producers")
    p.add_argument("--states", type=int, default=30)
    p.add_argument("--per-game", type=int, default=2)
    p.add_argument("--games", type=int, default=1000, help="at most this many collection games")
    p.add_argument("--futures", type=int, default=3)
    p.add_argument("--tops", type=int, default=3, help="turn tops the value head is read at")
    p.add_argument("--greedy", action="store_true", help="argmax play (default: sampled)")
    p.add_argument("--pool", default="verified")
    p.add_argument("--set", default="M21")
    p.add_argument("--deal0", type=int, default=950_000)
    p.add_argument("--seed", type=int, default=0, help="the master seed (rng.seed_all)")
    p.add_argument("--device", default="cpu", help="where the network runs (LocalSlot)")
    p.add_argument("--out", default="")
    a = p.parse_args(argv)
    if bool(a.cast) == bool(a.consumer or a.producer) or bool(a.consumer) != bool(a.producer):
        p.error("give --cast, or --consumer and --producer")
    seed_all(a.seed)
    supply = get_supply(a.pool, a.set)
    pkg = None
    if a.package:
        found = [k for k in PK.packages(supply) if PK.label(k) == a.package]
        if len(found) != 1:
            raise SystemExit(f"--package {a.package!r}: {len(found)} packages carry that label in "
                             f"{a.pool} {a.set}: {sorted(PK.label(k) for k in PK.packages(supply))}")
        pkg = found[0]
    if a.cast:
        line = cast_line(_ids(a.cast, supply), " | ".join(a.cast))
    elif pkg is not None and not a.consumer:
        line = order_line(frozenset(pkg.consumers), frozenset(pkg.producers),
                          f"{a.package}: a consumer before its producers")
    else:
        line = order_line(_ids(a.consumer, supply), _ids(a.producer, supply),
                          f"{' | '.join(a.consumer)} before {' | '.join(a.producer)}")
    net, table_, extra = M.load(a.ckpt, a.device)
    with torch.no_grad():  # a constant at play time: once, not per decision (half a CPU forward)
        emb = net.card_table_emb()
    net.card_table_emb = lambda: emb
    probe = Probe(M.LocalSlot({SPEC: net}), table_, line, pool_mode=a.pool, set_code=a.set,
                  greedy=a.greedy, tops=a.tops, package=pkg)
    rep = {"ckpt": a.ckpt, "ckpt_it": extra.get("it"), "args": vars(a),
           **run(probe, states=a.states, per_game=a.per_game, games=a.games, deal0=a.deal0,
                 futures=a.futures)}
    print(table(rep))
    if a.out:
        with open(a.out, "w") as fh:
            json.dump(rep, fh, indent=1)
    return rep


if __name__ == "__main__":
    main()
