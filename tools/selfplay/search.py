"""Decision-time lookahead: try the candidate moves in copies of the game and keep the best.

At a searched decision (the act menu of either main phase; with ``kinds`` also the instant-speed
``priority`` menu) the searching seat:

1. asks the network for its option probabilities;
2. picks candidates and spends simulations on them by its ``root``: ``topk`` plays the top ``k``
   options in the same ``d`` worlds each; ``gumbel`` takes ``m`` candidates by Gumbel-top-k (no
   noise in greedy play) and splits ``n`` simulations over them by sequential halving (Danihelka
   et al., ICLR 2022), every candidate of a round played in the same worlds;
3. each simulation forks the game (``tools/search/fork.py``), re-samples everything this seat
   cannot see (see ``determinize``), plays the candidate, then lets the network play BOTH seats
   (``continuation``: greedily, or sampled with one draw stream per seat and world, shared by
   every candidate) until the start of this seat's ``horizon``-th next turn (0: the game's end);
4. scores each simulation by the outcome if the game ended, else by the network's value of the
   real next decision (the act menu at that turn start);
5. plays the candidate with the best mean score (``topk``), or with the best logit plus
   sigma(mean) (``gumbel``).

Every setting is a learner flag (``--search-*``), and each measured setting's result goes to
KNOWLEDGE/NUMBERS.md (docs/PLAN_CEILING.md §3.2): settings are added beside the old ones.

Honesty (OWNER_PREFERENCES #1): a fork copies the true hidden zones, so before simulating, the
copy's own library is shuffled (its composition is known to its owner, its order is not) and
every card in the opponent's hand and library is replaced by a card drawn uniformly from the
dealt pool. The prior is the deal itself (decks are uniform samples of the pool), not anything
read from the hidden zones. Each world also gets its own engine seed: with the real game's seed
every simulated coin flip would equal the real one, and the search would play on that knowledge.
Known approximation: coherent two-colour decks are sampled as five-colour piles.

Searched decisions are the clean points of this rig, where no engine call is in flight: the
``act`` decisions (a main phase with an empty stack, either main phase), and the pre-attacks
boundary (before the declare-attackers step's declaration), where whole attack plans are compared
(``plan_attacks``) and the engine's per-creature attack asks are then answered from the chosen
plan. Blocks (--search-blocks) are planned the same way at the pre-blocks boundary, where the
opponent's attack is declared and no block asked yet. The game's state, the step and priority
included, lives in the executor, so a copy resumes exactly where it was taken: at a candidate act
the same decision is asked again and answered with the candidate. ``priority`` decisions (instant
speed: outside the main phases or over a non-empty stack) come from the same point of the game
loop (``take_priority``) and are searched when ``kinds`` names them. Target asks are answered by
the network inside each simulation.

A crashed simulation leaves out its world for every candidate, so the candidates stay compared on
the same worlds (``mean_scores``). ``draw_worlds`` is where the worlds come from: uniform re-samples
today, belief futures later (docs/PLAN_LEARNING.md §1.3).

The true-future labeller (``Labeller``, PLAN_LEARNING §1.1-1.2) reuses the same playouts for
training labels: alternatives at a real decision, each played to the end of the game on the
game's true future (no re-sampling; ``reshuffle_libraries`` for the second future), and the
mirror-descent target they define (``mmd_target``).
"""

from __future__ import annotations

import math
import random
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any

from MTG_bot.bench.protocol import Ask, Option
from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
from MTG_bot.core.executor import GameOver
from MTG_bot.core.executor.games import TURN_CAP, _play, get_supply, identity_of
from MTG_bot.core.executor.legality import (
    block_pair_blocked_reason,
    blocker_askable,
    legal_attackers,
    mandated_attackers,
)
from MTG_bot.core.state import ZONE_BATTLEFIELD, ZONE_HAND, ZONE_LIBRARY
from tools.search.fork import fork
from tools.selfplay import features as FT
from tools.selfplay.features import _handle
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import _ORACLES, SelfplayRouter

#: A simulation is cut off (and scored by the value head) after this many network decisions:
#: a rail against runaway loops, not a strategy limit.
MAX_SIM_DECISIONS = 400
#: Labelling scaffolds (BACKLOG): a decision is unsure when its top option has less than
#: UNSURE_P; a CONFIDENT_SHARE of the confident ones is labelled as well; at most
#: LABELS_PER_GAME positions of one game are labelled. LOGODDS_PER_SE sets a label's step: an error
#: of one standard error in its results moves the target's log-odds by at most that much.
UNSURE_P = 0.95
CONFIDENT_SHARE = 0.10
LABELS_PER_GAME = 4
LOGODDS_PER_SE = 0.5

ROOTS = ("topk", "gumbel")
CONTINUATIONS = ("greedy", "sampled")
#: Where a simulation's hidden cards come from: drawn uniformly from the pool, or from the
#: opponent simulator's beliefs (the learner's --search-sim network).
WORLDS = ("uniform", "sim")
#: The candidates an audit scores: the network's top few (``Searcher.audit``).
AUDIT_M = 4
#: The ask kinds a searcher can search at their own decision (combat plans are separate).
SEARCH_KINDS = ("act", "priority")
#: Gumbel MuZero's sigma: a candidate's mean result q in [-1, 1] enters the logits as
#: (C_VISIT + the most simulations any candidate had) * C_SCALE * (q + 1) / 2 (Danihelka et al.
#: 2022, their values).
C_VISIT = 50.0
C_SCALE = 1.0
#: A change of move is a clear correction when the chosen candidate's mean beats the network's
#: own choice by at least this (183 §16; the n-curve counts them, PLAN_CEILING §3.3).
CLEAR_MARGIN = 0.1

_IDENT_CACHE: dict[str, Any] = {}


def determinize(game: Any, seat: int, supply: Any, rng: random.Random,
                assigned: tuple[list[str], list[str]] | None = None) -> None:
    """Re-sample what ``seat`` cannot see in a copy: its own library's order, and the
    opponent's hand and library, drawn uniformly from the pool, or set to ``assigned`` (hand and
    library oracle ids drawn by the simulator; the library in an order drawn here)."""
    world = game.world
    ex = game.executor
    me = world.player_order[seat]
    opp = world.player_order[1 - seat]
    # The engine's randomness is sha256(master_seed:op_seq:tag) (Executor._rng), so a copied seed
    # replays the real game's future coin flips and shuffles: a new one per world.
    world.master_seed = rng.randrange(1 << 62)
    rng.shuffle(world.players[me].zone(ZONE_LIBRARY).entries)
    pool = supply.deckable
    if assigned is not None:
        hand, lib = assigned[0], list(assigned[1])
        rng.shuffle(lib)
    for zone in (ZONE_HAND, ZONE_LIBRARY):
        for i, h in enumerate(world.players[opp].zone(zone).entries):
            if assigned is None:
                oid = pool[rng.randrange(len(pool))]
            else:
                oid = (hand if zone == ZONE_HAND else lib)[i]
            ident = _IDENT_CACHE.get(oid)
            if ident is None:
                ident = _IDENT_CACHE[oid] = identity_of(ex.binder.records[oid])
            world.cards[h].identity = ident
            # A card cast or played stays bound to its record after it leaves the battlefield,
            # so one returned to a hidden zone (a bounce) would refuse its new identity when the
            # copy plays it ("already carries", binding.attach_card): unbound, as a dealt card is.
            ex.binder.handle_record.pop(h, None)


class SimAgent:
    """A network seat inside a simulation, never recorded: greedy, or with ``rng`` sampling from
    the network's probabilities with one draw per decision (a label's sampled playouts: every
    alternative gets the same draws). ``forced`` answers the first act or priority ask: the
    decision the copy was taken at, asked again, with the candidate being evaluated."""

    def __init__(self, slot: Any, gid: int, spec: str, table: FT.CardTable,
                 rng: random.Random | None = None) -> None:
        self.slot = slot
        self.gid = gid
        self.spec = spec
        self.table = table
        self.rng = rng
        self.fallback = HeuristicAgent()
        self.name = f"sim:{spec}"
        self.decisions = 0

    forced: str | None = None
    attack_plan: tuple[int, frozenset] | None = None  # (the turn it was made in, the plan)
    block_plan: tuple[int, frozenset] | None = None

    def decide(self, ask: Any, obs: Any) -> int:
        if self.forced is not None and ask.kind in SEARCH_KINDS:
            tok, self.forced = self.forced, None
            for i, o in enumerate(ask.options):
                if o.token == tok:
                    return i
        idx = planned(ask, obs.executor.world.turn, self.attack_plan, self.block_plan)
        if idx is not None:
            return idx
        n = len(ask.options)
        if n == 1:
            return 0
        if n > FT.MAX_OPTIONS or ask.kind == "name" or self.decisions >= MAX_SIM_DECISIONS:
            return self.fallback.decide(ask, obs)
        self.decisions += 1
        feats = FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx)
        if self.rng is None:
            return int(self.slot.infer((self.gid, ask.seat, self.spec, True, False, feats)))
        _, _, probs = self.slot.infer((self.gid, ask.seat, self.spec, True, False, feats, 2))
        return self.rng.choices(range(len(probs)), probs)[0]


def option_classes(feats: dict) -> list[tuple]:
    """Per option of an encoded ask, a key equal for the options the encoding cannot tell apart:
    the same option type, ability and numbers, pointing at entities whose encoded rows are equal
    (two copies of a card in one zone and one state). To the network they are one move (equal
    tokens give equal logits), and to the rules the same move made with another card object; the
    search's results for them differ only by noise (KNOWLEDGE/2026-11-12/197). Entity refs index
    [me, opponent, cards...] plus one, 0 for none (features.encode)."""
    ci, cf, oi, of = feats["cards_i"], feats["cards_f"], feats["opts_i"], feats["opts_f"]

    def entity(e: int) -> Any:
        return (ci[e - 3].tobytes(), cf[e - 3].tobytes()) if e >= 3 else e

    return [(int(oi[k, 0]), int(oi[k, 3]), of[k].tobytes(), entity(int(oi[k, 1])),
             entity(int(oi[k, 2]))) for k in range(len(oi))]


def distinct(ranked: list[int], feats: dict) -> list[int]:
    """``ranked`` (option indices) with every option after the first of its class
    (``option_classes``) left out."""
    keys, seen, out = option_classes(feats), set(), []
    for i in ranked:
        if keys[i] not in seen:
            seen.add(keys[i])
            out.append(i)
    return out


def planned(ask: Any, turn: int, attack: tuple[int, frozenset] | None,
            block: tuple[int, frozenset] | None) -> int | None:
    """The answer a searched combat plan gives ``ask``, or None. A plan is (the turn it was made
    in, the plan) and answers only that turn's attack (or block) asks: a later combat, in a
    simulation or in the real game, is the network's own decision again. One rule for the real
    seat (actor.NetAgent) and the simulated one (SimAgent)."""
    if ask.kind == "attack" and attack is not None and attack[0] == turn:
        return plan_answer(ask, attack[1])
    if ask.kind == "block" and block is not None and block[0] == turn:
        return block_answer(ask, block[1])
    return None


def plan_answer(ask: Any, plan: frozenset) -> int | None:
    """The ATTACK/DECLINE index an attack ask gets under ``plan`` (handles that attack)."""
    h = _handle(":".join(ask.site.split(":")[1:3]))
    tok = "ATTACK" if h in plan else "DECLINE"
    for i, o in enumerate(ask.options):
        if o.token == tok:
            return i
    return None


def mean_scores(raw: dict, weights: list[float] | None = None) -> dict | None:
    """Each candidate's (weighted) mean result over its worlds. A world in which any candidate's
    simulation crashed (None) is left out for every candidate, so the means stay paired on the
    same worlds (common random numbers) and no move looks better by crashing in its bad worlds
    (PLAN_LEARNING §1.1). None when no world is left."""
    n = len(next(iter(raw.values())))
    weights = weights or [1.0] * n
    keep = [w for w in range(n) if all(vals[w] is not None for vals in raw.values())]
    if not keep:
        return None
    total = sum(weights[w] for w in keep)
    return {c: sum(weights[w] * vals[w] for w in keep) / total for c, vals in raw.items()}


def block_answer(ask: Any, plan: frozenset) -> int | None:
    """The index a block ask gets under ``plan`` ((blocker, attacker) pairs; a blocker not in
    it blocks nothing), or None when the engine did not offer that word (it offers only words
    that keep the whole assignment CR-completable: menace pairs, must-be-blocked attackers, and
    no more blockers than "can't be blocked by more than one creature" allows)."""
    h = _handle(":".join(ask.site.split(":")[1:3]))
    target = next((a for b, a in plan if b == h), None)
    tok = "NONE" if target is None else str(target)
    for i, o in enumerate(ask.options):
        if o.token == tok:
            return i
    return None


class Searcher:
    def __init__(self, slot: Any, gid: int, spec: str, table: FT.CardTable, *, pool_mode: str,
                 set_code: str, k: int = 4, d: int = 2, skip_p: float = 0.97,
                 seed: int = 0, root: str = "topk", n: int = 16, m: int = 16,
                 continuation: str = "greedy", horizon: int = 1,
                 kinds: tuple[str, ...] = ("act",), noise: bool = False,
                 record: bool = False, worlds: str = "uniform", audit: int = 0) -> None:
        if root not in ROOTS or continuation not in CONTINUATIONS or worlds not in WORLDS:
            raise ValueError(f"search root {root!r}, continuation {continuation!r} or worlds "
                             f"{worlds!r} unknown")
        if not set(kinds) <= set(SEARCH_KINDS):
            raise ValueError(f"search kinds {kinds!r}: only {SEARCH_KINDS} are searched")
        self.slot = slot
        self.gid = gid
        # the network that ranks the candidates, plays both seats inside the simulations and
        # scores their leaves with its value head
        self.spec = spec
        self.table = table
        self.k = k
        self.d = d
        self.skip_p = skip_p
        self.root = root
        self.n = n
        self.m = m
        self.continuation = continuation
        self.horizon = horizon
        self.worlds = worlds
        self.root_pos: tuple = ()  # (game, seat, ask, ctx) of the decision being searched
        self.kinds = frozenset(kinds)
        self.noise = noise  # Gumbel noise at the root: on in sampled (training) play only
        # record: keep each searched act or priority decision as a training target (``targets``)
        self.record = record
        self.targets: list[dict] = []
        self.last: dict[int, list[tuple[float, float]]] = {}  # the last comparison's results
        # ... and its first round's alone: under sequential halving the only worlds every
        # compared candidate played (target_record's q1)
        self.first: dict[int, list[tuple[float, float]]] = {}
        self.rng = random.Random(seed)
        # the supply the searched game was dealt from: forks share its compiled cards (fork.py)
        # and the opponent's hidden cards are re-drawn from its deckable pool (determinize)
        self.supply = get_supply(pool_mode, set_code)
        self.set_code = set_code
        self.stats: Counter = Counter({"searched": 0, "skipped": 0, "sims": 0, "changed": 0,
                                       "sim_errors": 0})
        # audit: each searched act decision's top AUDIT_M candidates are also scored in ``audit``
        # worlds of each kind: uniform, the simulator's, and the true hidden cards (192 §7.1's
        # deciding test). The true worlds measure; they never choose a move. The audit's seeds
        # come from its own stream, so its uniform and true worlds leave the search's worlds as
        # they would be without it. Its simulator worlds do not: the learner draws every "sim"
        # request from one torch generator, so with --search-worlds sim an audit changes which
        # worlds the search draws (not how they are distributed).
        self.audit = audit
        self.audits: list[dict] = []
        self.audit_rng = random.Random(f"audit:{seed}")

    def draw_worlds(self, count: int, kind: str | None = None,
                    rng: random.Random | None = None) -> list[tuple[Any, float]]:
        """The worlds the candidates of one comparison are played in, with their weights, 1
        each: an engine seed for a uniform re-sample (``determinize``), or with ``worlds="sim"``
        the seed and the opponent's hidden cards drawn by the simulator from the searching
        seat's own view of the decision (``features.sim_view``; the learner's ``sim``
        requests). The audit alone asks for ``"true"``: the real hidden cards, both libraries
        reshuffled (``simulate``, ``reshuffle_libraries``)."""
        kind, rng = kind or self.worlds, rng or self.rng
        if kind == "uniform":
            return [(rng.randrange(1 << 31), 1.0) for _ in range(count)]
        if kind == "true":
            return [(("true", rng.randrange(1 << 31)), 1.0) for _ in range(count)]
        game, seat, ask, ctx = self.root_pos
        view = FT.sim_view(game.executor, seat, ask, self.table, ctx)
        drawn = self.slot.infer((self.gid, seat, "sim", True, False, view, 3, count, self.set_code))
        return [((rng.randrange(1 << 31), hand, lib), 1.0) for hand, lib in drawn]

    def compare(self, cands: list, logits: list[float], run: Any) -> tuple[int, dict[int, float]]:
        """Choose among ``cands``, whose network log-probabilities are ``logits``: the index of
        the chosen candidate, and each played candidate's mean result by index. ``run(c, world)``
        plays candidate c in a world and gives its result in [-1, 1], or None when the engine
        crashed. Common random numbers: the candidates of one round share its worlds, and a world
        in which any of them crashed is left out for all of them (``mean_scores``)."""
        if self.root == "topk":
            worlds = self.draw_worlds(self.d)
            raw = {i: [run(c, w) for w, _ in worlds] for i, c in enumerate(cands)}
            keep = [j for j in range(len(worlds)) if all(v[j] is not None for v in raw.values())]
            self.last = {i: [(v[j], worlds[j][1]) for j in keep] for i, v in raw.items()}
            self.first = self.last
            q = mean_scores(raw, [x for _, x in worlds])
            if q is None:
                return max(range(len(cands)), key=lambda i: logits[i]), {}
            return max(q, key=lambda i: (q[i], logits[i])), q
        return self._halve(cands, logits, run)

    def _halve(self, cands: list, logits: list[float], run: Any) -> tuple[int, dict[int, float]]:
        """Gumbel sequential halving (Danihelka et al. 2022, Algorithm 2): the top m of logit
        plus Gumbel noise, then ceil(log2 m) rounds that split n simulations evenly, each keeping
        the better half by logit + noise + sigma(mean)."""
        g = [self._gumbel() if self.noise else 0.0 for _ in cands]
        m = max(1, min(self.m, len(cands), self.n))
        alive = sorted(range(len(cands)), key=lambda i: -(g[i] + logits[i]))[:m]
        rounds = max(1, math.ceil(math.log2(m)))
        res: dict[int, list[tuple[float, float]]] = {i: [] for i in alive}

        def key(i: int) -> float:
            if not res[i]:
                return -math.inf
            q = sum(z * w for z, w in res[i]) / sum(w for _, w in res[i])
            most = max(len(v) for v in res.values())
            return g[i] + logits[i] + (C_VISIT + most) * C_SCALE * (q + 1) / 2

        for r in range(rounds):
            worlds = self.draw_worlds(max(1, self.n // (rounds * len(alive))))
            raw = {i: [run(cands[i], w) for w, _ in worlds] for i in alive}
            keep = [j for j in range(len(worlds)) if all(raw[i][j] is not None for i in alive)]
            for i in alive:
                res[i].extend((raw[i][j], worlds[j][1]) for j in keep)
            if r == 0:
                self.first = {i: list(res[i]) for i in alive}
            if len(alive) > 1:
                alive = sorted(alive, key=key, reverse=True)[: math.ceil(len(alive) / 2)]
        self.last = res
        q = {i: sum(z * w for z, w in v) / sum(w for _, w in v) for i, v in res.items() if v}
        if not q:
            return max(range(len(cands)), key=lambda i: logits[i]), {}
        return max(alive, key=key), q

    def _gumbel(self) -> float:
        return -math.log(-math.log(self.rng.random() or 1e-300))

    def _skip(self, kind: str) -> None:
        self.stats["skipped"] += 1
        self.stats[f"skipped:{kind}"] += 1

    def _record(self, kind: str, pick: int, own: int, q: dict[int, float], t0: float) -> None:
        """Statistics of one searched decision of ``kind`` (act, priority, attack or block plan):
        ``pick`` and ``own`` (the network's choice) index the compared candidates; its time in
        buckets of a tenth of a decade (``ms_percentiles``). Totals and per kind."""
        ms = 1000 * (time.perf_counter() - t0)
        st = self.stats
        st["searched"] += 1
        st[f"searched:{kind}"] += 1
        st["changed"] += int(pick != own)
        st[f"changed:{kind}"] += int(pick != own)
        st["clear"] += int(pick != own and own in q and q[pick] - q[own] >= CLEAR_MARGIN)
        st["ms"] += round(ms)
        st[f"ms_db{int(10 * math.log10(max(ms, 1.0)))}"] += 1

    def choose(self, ask: Any, obs: Any, feats: dict) -> int:
        """The searched option index for one act or priority ask (feats: its encoding)."""
        n = len(ask.options)
        a0, v0, probs = self.slot.infer((self.gid, ask.seat, self.spec, True, False, feats, 2))
        if max(probs) >= self.skip_p:
            self._skip(ask.kind)
            return int(a0)
        t0 = time.perf_counter()
        self.root_pos = (obs.game, ask.seat, ask, obs.ctx)
        ranked = sorted(range(n), key=lambda i: -probs[i])
        cands = ranked[: self.k] if self.root == "topk" else ranked
        logits = [math.log(probs[i]) if probs[i] > 0 else -math.inf for i in cands]
        pick, q = self.compare(cands, logits, lambda i, w: self.simulate(
            obs.game, ask.seat, ask.options[i].token, world=w))
        self._record(ask.kind, pick, cands.index(int(a0)) if int(a0) in cands else -1, q, t0)
        if self.record:
            self.targets.append(target_record(feats, probs, v0, cands, self.last,
                                              int(cands[pick]), ask.kind, ask.seat, self.first))
        if self.audit and ask.kind == "act":  # distinct moves: two copies are one candidate
            self._audit(obs.game, ask, distinct(ranked, feats)[:AUDIT_M], probs, int(a0),
                        int(cands[pick]))
        return int(cands[pick])

    def _audit(self, game: Any, ask: Any, top: list[int], probs: list[float], net: int,
               pick: int) -> None:
        """The ``audit`` record of one searched act decision: the network's top candidates'
        mean results in each kind of world, each kind's worlds shared by every candidate (a world
        where any candidate crashed is dropped for all). A second, independent set of true
        worlds (``true2``) measures how far two samples of the truth agree: the most any belief
        can. Its simulations are counted apart, so the search's own statistics stay comparable."""
        sims = self.stats["sims"]
        q = {}
        for key, kind in (("uniform", "uniform"), ("sim", "sim"), ("true", "true"),
                          ("true2", "true")):
            worlds = self.draw_worlds(self.audit, kind, self.audit_rng)
            raw = {i: [self.simulate(game, ask.seat, ask.options[c].token, world=w)
                       for w, _ in worlds] for i, c in enumerate(top)}
            means = mean_scores(raw)
            q[key] = [means[i] for i in range(len(top))] if means else None
        self.stats["audit_sims"] += self.stats["sims"] - sims
        self.stats["sims"] = sims
        self.audits.append({"seat": ask.seat, "turn": game.world.turn, "cands": top,
                            "prior": [probs[c] for c in top], "q": q, "net": net, "pick": pick,
                            "worlds": self.audit})

    def plan_attacks(self, game: Any, seat: int, max_plans: int = 6) -> frozenset | None:
        """At the pre-combat boundary: the attack set to declare this combat, or None to let the
        network answer the asks itself (nothing to decide, or it is confident on every one).

        Candidates: the network's own plan (asked creature by creature in the engine's handle
        order, each ask seeing the attackers declared before it), all-in, none, and the
        network's plan with one creature flipped (least confident first)."""
        ex = game.executor
        world = game.world
        me = world.player_order[seat]
        cands = legal_attackers(ex, me)
        mandated = mandated_attackers(ex, me) & set(cands)
        asked = [c for c in cands if c not in mandated]
        if not asked:
            return None
        declared: set = set()
        p_attack = {}
        for c in asked:
            ask = Ask(seat=seat, kind="attack", site=f"attack:{c}:{world.turn}", prompt="",
                      options=(Option("ATTACK", "ATTACK"), Option("DECLINE", "DECLINE")),
                      refuse=1)
            feats = FT.encode(ex, seat, ask, self.table,
                              FT.AskContext(declared_attackers=frozenset(declared)))
            _, _, probs = self.slot.infer((self.gid, seat, self.spec, True, False, feats, 2))
            p_attack[c] = probs[0]
            if probs[0] >= probs[1]:
                declared.add(c)
        if all(max(p, 1 - p) >= self.skip_p for p in p_attack.values()):
            self._skip("attack")
            return None
        t0 = time.perf_counter()
        self.root_pos = (game, seat, ask, FT.AskContext())  # the last attack ask built above
        base = frozenset(declared)
        plans = [base, frozenset(asked), frozenset()]
        for c in sorted(asked, key=lambda c: abs(p_attack[c] - 0.5)):
            plans.append(base ^ {c})
        uniq = []
        for pl in plans:
            if pl not in uniq:
                uniq.append(pl)
        uniq = uniq[:max_plans]
        # a plan's prior: the network's probability of answering every ask that way
        logits = [sum(math.log(max(p_attack[c] if c in pl else 1 - p_attack[c], 1e-12))
                      for c in asked) for pl in uniq]
        pick, q = self.compare(uniq, logits, lambda pl, w: self.simulate(
            game, seat, None, attack_plan=pl, world=w))
        self._record("attack", pick, 0, q, t0)
        return uniq[pick] | mandated

    def plan_blocks(self, game: Any, seat: int, declared_attackers: frozenset = frozenset(),
                    max_plans: int = 6) -> frozenset | None:
        """At the pre-blocks boundary (the attackers are declared): the block assignment to
        declare, as (blocker, attacker) pairs, or None to let the network answer the asks.

        Candidates: the network's own assignment (asked blocker by blocker in the engine's
        handle order, each ask seeing the blocks declared before it), no blocks, and the
        network's assignment with one blocker moved to its second choice (least confident
        first). The engine's completability filter is not replicated: a planned word it does
        not offer falls back to the network (block_answer)."""
        ex = game.executor
        world = game.world
        me = world.player_order[seat]
        if ex.defending_player != me or world.active_player is None:
            return None
        attackers = ex._live_attackers(world.active_player)
        if not attackers:
            return None
        cands = [c for c in sorted(world.cards)
                 if ex.controller_of(c) == me and world.zone_of(c).kind == ZONE_BATTLEFIELD
                 and blocker_askable(ex, c, attackers)]
        declared: dict = {}
        choices: dict = {}  # blocker -> [(prob, attacker or None)] best first
        for b in cands:
            legal = [a for a in attackers if block_pair_blocked_reason(ex, b, a) is None]
            if not legal:
                continue
            opts = tuple(Option(str(a), str(a)) for a in legal) + (Option("NONE", "NONE"),)
            ask = Ask(seat=seat, kind="block", site=f"block:{b}:{world.turn}", prompt="",
                      options=opts, refuse=len(opts) - 1)
            # the context a real block ask carries (rig._decide): the attackers the router saw
            # declared this combat and the blocks so far
            feats = FT.encode(ex, seat, ask, self.table,
                              FT.AskContext(declared_attackers=declared_attackers,
                                            declared_blocks=dict(declared)))
            _, _, probs = self.slot.infer((self.gid, seat, self.spec, True, False, feats, 2))
            ranked = sorted(zip(probs, [*legal, None]), key=lambda x: -x[0])
            choices[b] = ranked
            if ranked[0][1] is not None:
                declared[b] = ranked[0][1]
        if not choices or all(r[0][0] >= self.skip_p for r in choices.values()):
            self._skip("block")
            return None
        t0 = time.perf_counter()
        self.root_pos = (game, seat, ask, FT.AskContext())  # the last block ask built above
        base = frozenset(declared.items())
        plans = [base, frozenset()]
        for b in sorted(choices, key=lambda b: choices[b][0][0]):
            if len(choices[b]) > 1:
                alt = dict(declared)
                second = choices[b][1][1]
                alt.pop(b, None)
                if second is not None:
                    alt[b] = second
                plans.append(frozenset(alt.items()))
        uniq = []
        for pl in plans:
            if pl not in uniq:
                uniq.append(pl)
        uniq = uniq[:max_plans]
        # a plan's prior: the network's probability of each blocker's assignment in it
        prob = {b: {a: p for p, a in ranked} for b, ranked in choices.items()}
        logits = [sum(math.log(max(prob[b].get(dict(pl).get(b), 0.0), 1e-12)) for b in choices)
                  for pl in uniq]
        pick, q = self.compare(uniq, logits, lambda pl, w: self.simulate(
            game, seat, None, block_plan=pl, world=w))
        self._record("block", pick, 0, q, t0)
        return uniq[pick]

    def simulate(self, game: Any, seat: int, token: str | None,
                 attack_plan: frozenset | None = None, world: Any = 0,
                 block_plan: frozenset | None = None) -> float | None:
        """Score one candidate: ``token`` is an option of the searched act or priority menu to
        play now, or None with ``attack_plan`` at the pre-attacks boundary, or with
        ``block_plan`` at the pre-blocks boundary (the opponent's attack declared). ``world``
        seeds the re-sampled hidden cards and, in sampled continuations, each seat's draws, so
        every candidate played in one world meets the same hands and the same draws."""
        self.stats["sims"] += 1
        clone = fork_live(game, self.supply)
        if isinstance(world, tuple) and world[0] == "true":  # the audit's measure, never a choice
            seed = world[1]
            rng = random.Random(seed)
            clone.world.master_seed = rng.randrange(1 << 62)
            reshuffle_libraries(clone, rng)
        else:
            seed, assigned = (world[0], world[1:]) if isinstance(world, tuple) else (world, None)
            determinize(clone, seat, self.supply, random.Random(seed), assigned)
        sampled = self.continuation == "sampled"
        agents = [SimAgent(self.slot, self.gid, self.spec, self.table,
                           random.Random(f"{seed}:{s}") if sampled else None) for s in (0, 1)]
        agents[seat].forced = token
        turn = clone.world.turn  # the root's combat: the plans answer this turn's asks only
        agents[seat].attack_plan = None if attack_plan is None else (turn, attack_plan)
        agents[seat].block_plan = None if block_plan is None else (turn, block_plan)
        stop = horizon_stop(clone.world.player_order[seat], clone.world.turn, self.horizon)
        router = play_out(clone, agents, self.supply, self.set_code, stop)
        if isinstance(router, Exception):
            self.stats["sim_errors"] += 1
            frame = traceback.extract_tb(router.__traceback__)[-1]
            self.stats[f"sim_error:{type(router).__name__}@{Path(frame.filename).name}"
                       f":{frame.lineno}"] += 1  # what to fix (192 P11), in the eval's summary
            return None
        z = outcome(clone, seat)
        return z if z is not None else self.leaf_value(router, clone, seat)

    def leaf_value(self, router: SelfplayRouter, clone: Any, seat: int) -> float:
        """The network's value at this seat's next real decision: its turn-start act menu."""
        me = clone.world.player_order[seat]
        menu = router._act_menu(clone, me, seat)
        ask = Ask(seat=seat, kind="act", site=f"act:{me}:{clone.world.turn}", prompt="",
                  options=tuple(o for o, _ in menu), refuse=0)
        feats = FT.encode(clone.executor, seat, ask, self.table, FT.AskContext())
        _, value = self.slot.infer((self.gid, seat, self.spec, True, False, feats, 1))
        return float(value)


def target_record(feats: dict, probs: list[float], value: float, cands: list[int],
                  results: dict[int, list[tuple[float, float]]], pick: int, kind: str,
                  seat: int, first: dict[int, list[tuple[float, float]]] | None = None) -> dict:
    """One searched decision as a training target (PLAN_CEILING §6.2): its encoding, the
    network's probabilities and value, and per compared option (an index of the ask's options)
    the weighted mean result, the number of worlds and their variance, so the target's rule (the
    paper's sigma, a step scaled by the standard error; distill.py) is chosen when training.

    ``var`` is the worlds' population variance (divided by their total weight, n with weights
    1): a description of the results, not an estimate. A reader pooling it as an estimate
    divides the sum of n * var by the degrees of freedom, sum(n - 1) (distill.improved).

    ``q1``/``n1`` are the same mean and count over the first round's worlds alone (``first``).
    Under sequential halving only those are shared by every compared option. An option that
    lost the first round has nothing else, and that round was selected low; a survivor adds
    fresh worlds. So ``q`` sets a loser's selected-low mean against a survivor's partly fresh
    one, and ``q1`` is the comparison free of that selection (KNOWLEDGE/2026-11-12/196). With
    no ``first`` (topk: one round) they equal ``q``/``n``. An option with no first-round world
    (every one failed) has ``n1`` 0 and ``q1`` 0: no first-round comparison exists. The
    search's own choice uses every world."""
    def mean(v: list[tuple[float, float]]) -> float:
        return sum(z * w for z, w in v) / sum(w for _, w in v)

    rows = []
    for i, c in enumerate(cands):
        v = results.get(i) or []
        if not v:
            continue
        m = mean(v)
        var = sum(w * (z - m) ** 2 for z, w in v) / sum(w for _, w in v)
        v1 = v if first is None else first.get(i, [])
        rows.append((c, m, len(v), var, mean(v1) if v1 else 0.0, len(v1)))
    return {"feats": feats, "probs": list(probs), "v": float(value), "alts": [r[0] for r in rows],
            "q": [r[1] for r in rows], "n": [r[2] for r in rows], "var": [r[3] for r in rows],
            "q1": [r[4] for r in rows], "n1": [r[5] for r in rows],
            "pick": pick, "kind": kind, "seat": seat}


def horizon_stop(me: Any, start: int, horizon: int) -> Any:
    """The ``stop_after`` of a simulation: True at the top of ``me``'s ``horizon``-th turn after
    turn ``start`` (games._play_turns consults "turn_top" once per turn); None (play to the end
    of the game) when ``horizon`` is 0."""
    if horizon <= 0:
        return None
    tops = 0

    def stop(g: Any, boundary: str) -> bool:
        nonlocal tops
        if boundary == "turn_top" and g.world.active_player == me and g.world.turn > start:
            tops += 1
            return tops >= horizon
        return False

    return stop


def ms_percentiles(stats: dict) -> dict:
    """p50, p90 and p99 of a searched decision's time (ms), read from ``Searcher._record``'s
    buckets (each the upper edge of a tenth of a decade, so within 26%), and the mean."""
    buckets = sorted((int(k[5:]), v) for k, v in stats.items() if k.startswith("ms_db"))
    n = sum(v for _, v in buckets)
    out: dict = {"n": n, "mean": round(stats.get("ms", 0) / n, 1) if n else None}
    for name, frac in (("p50", 0.5), ("p90", 0.9), ("p99", 0.99)):
        seen = 0
        for b, v in buckets:
            seen += v
            if seen >= frac * n:
                out[name] = round(10 ** ((b + 1) / 10), 1)
                break
    return out


def fork_live(game: Any, supply: Any) -> Any:
    """A copy of a game being played. Its decision provider is the real router's bound method,
    which deepcopy would follow into the router, its agents and their worker-thread locks: it is
    detached for the copy only."""
    decisions = game.executor.decisions
    saved, decisions.provider = decisions.provider, None
    try:
        return fork(game, supply)
    finally:
        decisions.provider = saved


def play_out(clone: Any, agents: list, supply: Any, set_code: str,
             stop: Any = None) -> SelfplayRouter | Exception:
    """Play a copy on from where it was taken: the decision being searched is asked again (the
    searching agent's ``forced`` token answers it), or the combat declaration comes (its attack
    or block plan); ``agents`` then play until ``stop`` says so, else to the end of the game.
    The exception when the engine crashed."""
    oracle = _ORACLES.get(set_code) or OracleIndex.for_sets(set_code)
    router = SelfplayRouter(clone, agents, [SeatLens(s, oracle, ViewOptions()) for s in (0, 1)],
                            supply=supply)
    clone.executor.decisions.provider = router.answer
    try:
        _play(clone, router, list(clone.world.player_order), TURN_CAP, resumed=True,
              stop_after=stop)
    except GameOver:
        pass  # the candidate itself ended the game (CR 704.3: the loss check ends it there)
    except Exception as error:  # noqa: BLE001 - a crashed playout is counted by the caller, never scored
        return error
    return router


def outcome(clone: Any, seat: int) -> float | None:
    """The result for ``seat`` once the game is over: +1 win, -1 loss, 0 when both lose at once,
    -1 at the turn cap or the stall rule (the training reward's draw). None while it runs."""
    order = clone.world.player_order
    if clone.over_reason() is not None:
        losers = [s for s in order if clone.is_loser(s)]
        return 0.0 if len(losers) != 1 else (1.0 if losers[0] != order[seat] else -1.0)
    if (clone.reason or "").startswith(("turn cap", "STALL")):
        return -1.0
    return None


def reshuffle_libraries(game: Any, rng: random.Random) -> None:
    """Shuffle every library in a copy of a game: the same deal's cards in an order nobody
    knows, a "true" world (the audit's) or the labeller's second future. Positions some player
    knows (a scry's top, a London mulligan's bottoms) are shuffled too, as a uniform world does
    with the searcher's own library (``determinize``): the engine's journal does not record
    which cards a scry kept or which zone a REVEAL showed (KNOWLEDGE/2026-11-12/197), so
    knowledge rebuilt from it pinned unseen cards, often the next draw."""
    for player in game.world.player_order:
        rng.shuffle(game.world.players[player].zone(ZONE_LIBRARY).entries)


def gumbel_top_k(probs: list[float], k: int, rng: random.Random) -> list[int]:
    """``k`` distinct options drawn without replacement in proportion to ``probs``: the top k of
    log p plus Gumbel noise."""
    keys = [(math.log(p) if p > 0 else -math.inf) - math.log(-math.log(rng.random() or 1e-300))
            for p in probs]
    return sorted(range(len(probs)), key=lambda i: -keys[i])[:k]


def mmd_target(probs: list[float], alts: list[int], q: list[float], se: float,
               alpha: float = 0.0) -> list[float]:
    """A label's target policy (PLAN_LEARNING §1.1): the unrescaled mirror-descent step of Sokota
    et al. (ICLR 2024) on the compared options ``alts``, whose mean results are ``q`` (outcome
    units): pi'(a) = pi(S) u(a) / sum_S u, u(a) = [pi(a) exp(eta q(a)) rho^(eta alpha)]^(1/(1+eta
    alpha)) with rho the uniform magnet (its factor cancels), and eta = LOGODDS_PER_SE / se, so an
    error of one standard error ``se`` in the results moves the log-odds by at most that much.
    Options outside ``alts`` keep their probability."""
    eta = LOGODDS_PER_SE / se
    logu = [((math.log(probs[a]) if probs[a] > 0 else -math.inf) + eta * qa) / (1 + eta * alpha)
            for a, qa in zip(alts, q, strict=True)]
    top = max(logu)
    u = [math.exp(x - top) for x in logu]
    mass = sum(probs[a] for a in alts) / sum(u)
    out = list(probs)
    for a, ua in zip(alts, u, strict=True):
        out[a] = mass * ua
    return out


def placebo(q: list[float], rng: random.Random) -> list[float]:
    """A label's results shuffled across its alternatives (PLAN_LEARNING §1.1): a sound target
    computed from them carries no signal, so the gradient test on them must find none."""
    q = list(q)
    rng.shuffle(q)
    return q


class Labeller:
    """True-future labels for the act decisions of one game, both seats (PLAN_LEARNING §1.1-1.2).

    During the game, ``offer`` sees each act decision a network seat makes and keeps a copy of the
    position when it is unsure (its top option below UNSURE_P), or for a CONFIDENT_SHARE of the
    confident ones: at most LABELS_PER_GAME positions, drawn uniformly from those (a reservoir).
    The real game plays on untouched; its copies are taken without its decision provider.

    After the game, ``labels`` compares k alternatives at each kept position, drawn by
    Gumbel-top-k from the network's probabilities, on d futures: the first is the real one (the
    true hidden cards and library orders), each later one keeps the true cards and reshuffles
    both libraries whole (``reshuffle_libraries``). Each future has
    its own engine seed and, in sampled playouts, its own move draws per seat, shared by every
    alternative. Every alternative is played to the end of the game by the network on both seats,
    each seat encoding only its own view (features.encode), and only its result comes back."""

    def __init__(self, slot: Any, gid: int, spec: str, table: FT.CardTable, *, pool_mode: str,
                 set_code: str, k: int, d: int, greedy: bool, seed: int) -> None:
        self.slot = slot
        self.gid = gid
        self.spec = spec  # the network that plays both seats in the playouts
        self.table = table
        self.k = k
        self.d = d
        self.greedy = greedy
        self.rng = random.Random(seed)
        self.supply = get_supply(pool_mode, set_code)
        self.set_code = set_code
        self.kept: list[tuple] = []
        self.stats = {"eligible": 0, "playouts": 0, "crashes": 0, "rails": 0, "fp": 0}

    def offer(self, game: Any, ask: Any, feats: dict, probs: list[float]) -> None:
        if max(probs) >= UNSURE_P and self.rng.random() >= CONFIDENT_SHARE:
            return
        self.stats["eligible"] += 1
        n = self.stats["eligible"]
        j = n - 1 if n <= LABELS_PER_GAME else self.rng.randrange(n)
        if j < LABELS_PER_GAME:
            pos = (fork_live(game, self.supply), ask.seat, [o.token for o in ask.options],
                   feats, list(probs))
            self.kept[j:j + 1] = [pos]

    def labels(self) -> list[dict]:
        out = []
        for game, seat, tokens, feats, probs in self.kept:
            alts = gumbel_top_k(probs, self.k, self.rng)
            seeds = [self.rng.randrange(1 << 62) for _ in range(self.d)]
            z = [[self.playout(game, seat, tokens[a], s, f > 0) for a in alts]
                 for f, s in enumerate(seeds)]
            q = mean_scores({i: [zf[i] for zf in z] for i in range(len(alts))})
            if q is not None:
                out.append({"feats": feats, "probs": probs, "alts": alts, "z": z,
                            "q": [q[i] for i in range(len(alts))], "seat": seat,
                            "turn": game.world.turn})
        return out

    def playout(self, game: Any, seat: int, token: str, seed: int, reshuffle: bool) -> float | None:
        clone = fork(game, self.supply)
        clone.world.master_seed = seed
        if reshuffle:
            reshuffle_libraries(clone, random.Random(f"{seed}:library"))
        agents = [SimAgent(self.slot, self.gid, self.spec, self.table,
                           None if self.greedy else random.Random(f"{seed}:{s}")) for s in (0, 1)]
        agents[seat].forced = token
        router = play_out(clone, agents, self.supply, self.set_code)
        st = self.stats
        st["playouts"] += 1
        st["fp"] += sum(a.decisions for a in agents)
        st["rails"] += (any(a.decisions >= MAX_SIM_DECISIONS for a in agents)
                        or (clone.reason or "").startswith(("turn cap", "STALL")))
        if isinstance(router, Exception):
            st["crashes"] += 1
            return None
        return outcome(clone, seat)
