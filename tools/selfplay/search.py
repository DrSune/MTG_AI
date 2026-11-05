"""Decision-time lookahead: try the candidate moves in copies of the game and keep the best.

At a main-phase decision (play which land, cast what, activate, pass) the searching seat:

1. asks the network for its option probabilities and keeps the top ``k`` options;
2. for each kept option, ``d`` times: forks the game (``tools/search/fork.py``), re-samples
   everything this seat cannot see (see ``determinize``), plays the option, then lets the
   network play BOTH seats greedily through the rest of this turn and the opponent's whole turn,
   and stops at the start of this seat's next turn;
3. scores each simulation by the outcome if the game ended, else by the network's value of the
   real next decision (the act menu at that turn start);
4. plays the option with the best mean score.

Honesty (OWNER_PREFERENCES #1): a fork copies the true hidden zones, so before simulating, the
copy's own library is shuffled (its composition is known to its owner, its order is not) and
every card in the opponent's hand and library is replaced by a card drawn uniformly from the
dealt pool. The prior is the deal itself (decks are uniform samples of the pool), not anything
read from the hidden zones. Each world also gets its own engine seed: with the real game's seed a
simulated coin flip equalled the real one 2,360 times in 2,360, and the search used it with
Tavern Swindler (2026-11-05 audit). Known approximation: coherent two-colour decks are sampled
as five-colour piles.

Searched decisions are the clean points of this rig, where no engine call is in flight: the
router's act loop, and the pre-combat boundary (the end of the act window), where whole attack
plans are compared (``plan_attacks``) and the engine's per-creature attack asks are then answered
from the chosen plan. Blocks (--search-blocks) are planned the same way at the engine's
pre-blocks boundary, where the opponent's attack is declared and no block asked yet.
"""

from __future__ import annotations

import random
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

_IDENT_CACHE: dict[str, Any] = {}


def determinize(game: Any, seat: int, supply: Any, rng: random.Random) -> None:
    world = game.world
    ex = game.executor
    me = world.player_order[seat]
    opp = world.player_order[1 - seat]
    # The engine's randomness is sha256(master_seed:op_seq:tag) (Executor._rng), so a copied seed
    # replays the real game's future coin flips and shuffles: a new one per world.
    world.master_seed = rng.randrange(1 << 62)
    rng.shuffle(world.players[me].zone(ZONE_LIBRARY).entries)
    pool = supply.deckable
    for zone in (ZONE_HAND, ZONE_LIBRARY):
        for h in world.players[opp].zone(zone).entries:
            oid = pool[rng.randrange(len(pool))]
            ident = _IDENT_CACHE.get(oid)
            if ident is None:
                ident = _IDENT_CACHE[oid] = identity_of(ex.binder.records[oid])
            world.cards[h].identity = ident


class SimAgent:
    """A network seat inside a simulation: greedy, never recorded. ``forced`` answers the first
    act ask (the candidate being evaluated)."""

    def __init__(self, slot: Any, gid: int, spec: str, table: FT.CardTable,
                 forced: str | None = None) -> None:
        self.slot = slot
        self.gid = gid
        self.spec = spec
        self.table = table
        self.forced = forced
        self.fallback = HeuristicAgent()
        self.name = f"sim:{spec}"
        self.decisions = 0

    attack_plan: frozenset | None = None
    block_plan: frozenset | None = None

    def decide(self, ask: Any, obs: Any) -> int:
        if self.forced is not None and ask.kind == "act":
            tok, self.forced = self.forced, None
            for i, o in enumerate(ask.options):
                if o.token == tok:
                    return i
        if self.attack_plan is not None and ask.kind == "attack":
            idx = plan_answer(ask, self.attack_plan)
            if idx is not None:
                return idx
        if self.block_plan is not None and ask.kind == "block":
            idx = block_answer(ask, self.block_plan)
            if idx is not None:
                return idx
        n = len(ask.options)
        if n == 1:
            return 0
        if n > FT.MAX_OPTIONS or ask.kind == "name" or self.decisions >= MAX_SIM_DECISIONS:
            return self.fallback.decide(ask, obs)
        self.decisions += 1
        feats = FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx)
        return int(self.slot.infer((self.gid, ask.seat, self.spec, True, False, feats)))


def plan_answer(ask: Any, plan: frozenset) -> int | None:
    """The ATTACK/DECLINE index an attack ask gets under ``plan`` (handles that attack)."""
    h = _handle(":".join(ask.site.split(":")[1:3]))
    tok = "ATTACK" if h in plan else "DECLINE"
    for i, o in enumerate(ask.options):
        if o.token == tok:
            return i
    return None


def mean_scores(raw: dict) -> dict:
    """Each candidate's score over its sampled worlds. A world whose simulation crashed (None)
    scores the mean of every simulation of this search that did not: what the search believes
    of the position, the same for every candidate. Dropped, it scored a candidate only on the
    worlds it survived (a move that crashed its bad worlds looked better, 2026-11-05 red-team);
    scored 0.0, the crashing move won in a bad position. Nothing survived: -1 for all."""
    ok = [v for vals in raw.values() for v in vals if v is not None]
    neutral = sum(ok) / len(ok) if ok else -1.0
    return {c: sum(neutral if v is None else v for v in vals) / len(vals) for c, vals in raw.items()}


def block_answer(ask: Any, plan: frozenset) -> int | None:
    """The index a block ask gets under ``plan`` ((blocker, attacker) pairs; a blocker not in
    it blocks nothing), or None when the engine did not offer that word (it offers only words
    that keep the whole assignment CR-completable: menace pairs, must-be-blocked attackers)."""
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
                 draw_value: float = -1.0, seed: int = 0) -> None:
        self.slot = slot
        self.gid = gid
        # the network that ranks the candidates, plays both seats inside the simulations and
        # scores their leaves with its value head
        self.spec = spec
        self.table = table
        self.k = k
        self.d = d
        self.skip_p = skip_p
        self.draw_value = draw_value
        self.rng = random.Random(seed)
        # the supply the searched game was dealt from: forks share its compiled cards (fork.py)
        # and the opponent's hidden cards are re-drawn from its deckable pool (determinize)
        self.supply = get_supply(pool_mode, set_code)
        self.set_code = set_code
        self.stats = {"searched": 0, "skipped": 0, "sims": 0, "changed": 0, "sim_errors": 0}

    def choose(self, ask: Any, obs: Any, feats: dict) -> int:
        """The searched option index for one act ask (feats: its encoding)."""
        n = len(ask.options)
        a0, _, probs = self.slot.infer((self.gid, ask.seat, self.spec, True, False, feats, 2))
        if max(probs) >= self.skip_p or obs.game is None:
            self.stats["skipped"] += 1
            return int(a0)
        order = sorted(range(n), key=lambda i: -probs[i])[: self.k]
        # Common random numbers: every candidate is played in the SAME d sampled worlds, so a
        # difference in score is the move's, not the luck of the opponent's sampled hand.
        worlds = [self.rng.randrange(1 << 31) for _ in range(self.d)]
        scores = mean_scores({i: [self.simulate(obs.game, ask.seat, ask.options[i].token, world=w)
                                  for w in worlds] for i in order})
        best = max(order, key=lambda i: (scores[i], probs[i]))
        self.stats["searched"] += 1
        self.stats["changed"] += int(best != a0)
        return int(best)

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
            self.stats["plans_skipped"] = self.stats.get("plans_skipped", 0) + 1
            return None
        base = frozenset(declared)
        plans = [base, frozenset(asked), frozenset()]
        for c in sorted(asked, key=lambda c: abs(p_attack[c] - 0.5)):
            plans.append(base ^ {c})
        uniq = []
        for pl in plans:
            if pl not in uniq:
                uniq.append(pl)
        uniq = uniq[:max_plans]
        worlds = [self.rng.randrange(1 << 31) for _ in range(self.d)]
        scores = mean_scores({pl: [self.simulate(game, seat, None, attack_plan=pl, world=w)
                                   for w in worlds] for pl in uniq})
        best = max(uniq, key=lambda pl: (scores[pl], pl == base))
        self.stats["plans"] = self.stats.get("plans", 0) + 1
        self.stats["plans_changed"] = self.stats.get("plans_changed", 0) + int(best != base)
        return best | mandated

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
            self.stats["blocks_skipped"] = self.stats.get("blocks_skipped", 0) + 1
            return None
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
        worlds = [self.rng.randrange(1 << 31) for _ in range(self.d)]
        scores = mean_scores({pl: [self.simulate(game, seat, None, block_plan=pl, world=w)
                                   for w in worlds] for pl in uniq})
        best = max(uniq, key=lambda pl: (scores[pl], pl == base))
        self.stats["blocks"] = self.stats.get("blocks", 0) + 1
        self.stats["blocks_changed"] = self.stats.get("blocks_changed", 0) + int(best != base)
        return best

    def simulate(self, game: Any, seat: int, token: str | None,
                 attack_plan: frozenset | None = None, world: int = 0,
                 block_plan: frozenset | None = None) -> float | None:
        """Score one candidate: ``token`` is a main-phase option to play now (the copy finishes
        this act window), or None with ``attack_plan`` to start at the pre-combat boundary, or
        with ``block_plan`` at the pre-blocks boundary (the opponent's attack declared)."""
        self.stats["sims"] += 1
        # The live provider is the real router's bound method: deepcopy would copy the router,
        # its agents and their worker-thread locks. Detach it for the copy only.
        decisions = game.executor.decisions
        saved, decisions.provider = decisions.provider, None
        try:
            clone = fork(game, self.supply)
        finally:
            decisions.provider = saved
        determinize(clone, seat, self.supply, random.Random(world))
        world = clone.world
        me = world.player_order[seat]
        start = world.turn
        agents = [SimAgent(self.slot, self.gid, self.spec, self.table) for _ in (0, 1)]
        agents[seat].forced = token
        agents[seat].attack_plan = attack_plan
        agents[seat].block_plan = block_plan
        oracle = _ORACLES.get(self.set_code) or OracleIndex.for_sets(self.set_code)
        router = SelfplayRouter(clone, agents, [SeatLens(s, oracle, ViewOptions()) for s in (0, 1)],
                                supply=self.supply)
        clone.executor.decisions.provider = router.answer
        try:
            if token is not None:
                router.take_acts(clone, me)
            clone.skip_next_acts = True
            clone.skip_to_blocks = block_plan is not None

            def stop(g: Any, boundary: str) -> bool:
                return (boundary == "turn_top" and g.world.active_player == me
                        and g.world.turn > start)

            _play(clone, router, list(world.player_order), TURN_CAP, resumed=True,
                  stop_after=stop)
        except GameOver:
            pass  # the candidate itself ended the game (CR 704.3: the loss check ends it there)
        except Exception:  # noqa: BLE001 - a crashed simulation is counted, left out of the mean
            self.stats["sim_errors"] += 1
            return None
        if clone.over_reason() is not None:
            losers = [s for s in world.player_order if clone.is_loser(s)]
            if len(losers) == 1:
                return 1.0 if losers[0] != me else -1.0
            return 0.0
        if (clone.reason or "").startswith(("turn cap", "STALL")):
            return self.draw_value
        return self.leaf_value(router, clone, seat)

    def leaf_value(self, router: SelfplayRouter, clone: Any, seat: int) -> float:
        """The network's value at this seat's next real decision: its turn-start act menu."""
        me = clone.world.player_order[seat]
        menu = router._act_menu(clone, me, seat)
        ask = Ask(seat=seat, kind="act", site=f"act:{me}:{clone.world.turn}", prompt="",
                  options=tuple(o for o, _ in menu), refuse=0)
        feats = FT.encode(clone.executor, seat, ask, self.table, FT.AskContext())
        _, value = self.slot.infer((self.gid, seat, self.spec, True, False, feats, 1))
        return float(value)
