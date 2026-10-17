"""AlphaZero-style self-play data generation on the committed search substrate.

KNOWLEDGE/2026-10-10/67 (mandate) + /68 (fork/rollout/expand API). The root
net is ``tools/training/bc10_S4_s2_best.pt``, loaded through the same
machinery the v2 eval rig uses (``gameplay_eval_v2.make_eval_policy`` ->
``BcAsk``; CPU). At every searched ask:

* menu = the engine's full legal candidate list at the discovered ask
  (F1 autopicks are journal-only and never ask);
* expand TOP-k=3 options by root-net ``menu_probs`` (argmax always in, it is
  the max by construction);
* allocate N=6 rollouts TOTAL per ask with plain UCB1 (c = sqrt(2),
  unvisited arms first in index order — deterministic under the seed);
* each rollout plays a forked option-branch out. CHEAP mode (default,
  /69 cost reality): per-seat policies are independently 50/50
  greedy-teacher vs RANDOM — the net NEVER plays a rollout, it is used
  only for ``menu_probs`` pruning at search roots (one forward per real
  ask). NON-cheap mode keeps the /68 contract (fresh root-net stream per
  seat). Either way the draw mix is counted honestly in ``policy_mix``;
* value from the ROOT SEAT's perspective: decided win/loss/draw = 1/0/0.5;
  UNDECIDED at the turn cap = 0.5 + clamp(life_diff, -10, 10) / 40
  (SHAPING — counted honestly in the stats), rollout crashes = 0.5.

Walk architecture (the /68 documented limit, stated up front): a fork taken
INSIDE an in-flight executor call cannot resume that call, so the live game
is a chain of boundary positions. At each position ONE discovery probe finds
the globally first ask (any seat — it is by definition the first ask of its
seat, exactly what the apply mechanism forces); that ask is the search root;
the chosen option's branch game (with its recorded default-answered
continuations) BECOMES the real game. Every real ask is therefore either a
search root or a counted SWALLOWED ask (never silently lost — the stats
break swallowed asks down by kind).

Episode rows are ``bc_data_v2``-compatible with added fields per row:
``pi`` (visit fractions over the FULL menu, unexpanded options 0 — /83 fix:
DIAGNOSTIC only), ``value`` (mean backed value), ``gold_idx``/``label_src``
(the gold rule: backed-value top1 when the decided gates pass, else the
root-net pick — never visit argmax) and episode ``label_class="search"``;
chunking reuses
``dagger_wave.chunk_seat`` so the encode-exactness asserts (n_tokens == the
encoded stream, <= max_len) ride verbatim. Rows go ONLY to
``tools/training/episodes_search.jsonl`` (fresh file, never mixed into the
v2/dagger files).
"""

from __future__ import annotations

import hashlib
import math
import random
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from MTG_bot.core.executor.games import (
    REPEAT_ROUNDS,
    Game,
    Supply,
    _play,
    _setup_game,
    _stall_fingerprint,
    deal_decks,
    get_supply,
)
from tools.eval import dagger_wave as dw
from tools.eval.dagger_wave import chunk_seat
from tools.eval.gameplay_eval_v2 import HeuristicTeacher, site_kind
from tools.search.fork import fork
from tools.search.rollout import (
    AskRec,
    Position,
    RolloutResult,
    SearchDriver,
    _AskFound,
    _run,
    _StepComplete,
    _wire,
    rollout,
)
from tools.training import bc_data_v2
from tools.training.ab_duel import BcAsk, _cards_rows_of
from tools.training.collector import AskContext

NET_SPEC = str(REPO / "tools" / "training" / "bc10_S4_s2_best.pt")
K_DEFAULT = 3
N_ROLLOUTS_DEFAULT = 6
TURN_CAP_DEFAULT = 60  # rollout()'s own default cap
ROLL_CAP_DEFAULT = 25  # /69 cost wave: short AlphaZero-style rollouts
PI_MIX_VISIT_WEIGHT = 0.75  # /72 AZ-v3: pi_mix = w*visits + (1-w)*net probs
ROLLOUT_MIXES = ("greedy", "mixed", "net")  # /72: random drivers contaminated
# values; /74 §5 "net": ON-POLICY rollouts — the root net drives both seats
DECK_PAIRS_SEED = 1409  # the v2 rig pairing
DISCOVER_HORIZON = 8  # turns a probe may run to reach the next ask
WALK_STEP_CAP = 1500  # pathological-loop guard for one self-play game


def stable_int(*parts: Any) -> int:
    """Deterministic cross-process seed derivation (no Python hash salt)."""
    h = hashlib.sha256(":".join(str(p) for p in parts).encode()).digest()
    return int.from_bytes(h[:8], "big")


# ----------------------------------------------------------------- values


def rollout_value(res: RolloutResult, root_seat: int) -> tuple[float, str]:
    """Back a rollout outcome into [0, 1] from the ROOT SEAT's view.

    Returns ``(value, bucket)`` with bucket in {decided, shaping, crash}:
    decided = engine-called win/loss/draw; shaping = undecided at the cap,
    valued by the clamped life-diff nudge; crash = rollout died (0.5, its
    own bucket — neither a decision nor a shaping signal).
    """
    if res.result == "crash":
        return 0.5, "crash"
    if res.result == "draw":
        return 0.5, "decided"
    if res.result in ("seat0", "seat1"):
        return (1.0 if res.result == f"seat{root_seat}" else 0.0), "decided"
    # undecided at cap: observable life-diff signal, root-seat sign
    sign = 1 if root_seat == 0 else -1
    nudged = max(-10.0, min(10.0, sign * float(res.life_diff)))
    return 0.5 + nudged / 40.0, "shaping"


# -------------------------------------------------------------------- UCB1


class Ucb1:
    """Plain UCB1 over a fixed arm set: unvisited arms first (index order —
    the ``_net_pulls`` batched prefix depends on that order being the ledger
    alone), then argmax(Q_i + sqrt(2 ln t / n_i)). /83 SUPERSEDED fix: with
    a seeded ``rng`` an EXACT UCB tie (or an exact visits tie in :meth:`best`)
    draws uniformly among the tied arms instead of falling to the lowest
    index — the old ``>`` tie-break gave every tie to arm 0 (73% index-0
    gold concentration). Without ``rng``: the legacy deterministic contract,
    ties to the lowest index."""

    def __init__(self, arms: list[int], rng: random.Random | None = None) -> None:
        if not arms:
            raise ValueError("Ucb1: no arms")
        self.arms = list(arms)
        self.n = {a: 0 for a in self.arms}
        self.q = {a: 0.0 for a in self.arms}
        self.t = 0
        self.rng = rng

    def _tie(self, ties: list[int]) -> int:
        return ties[0] if self.rng is None or len(ties) == 1 else self.rng.choice(ties)

    def pick(self) -> int:
        for a in self.arms:  # unvisited first, deterministic index order
            if self.n[a] == 0:
                return a
        vals = {
            a: self.q[a] / self.n[a] + math.sqrt(2.0 * math.log(self.t) / self.n[a])
            for a in self.arms
        }
        best_v = max(vals.values())
        return self._tie([a for a in self.arms if vals[a] == best_v])

    def best(self) -> int:
        """Most-visited arm; an exact visits tie draws from ``rng`` (the
        played-arm pick must not inherit index-0 gravity either)."""
        mx = max(self.n.values())
        return self._tie([a for a in self.arms if self.n[a] == mx])

    def push(self, arm: int, value: float) -> None:
        self.n[arm] += 1
        self.q[arm] += value
        self.t += 1

    def visit_fracs(self, menu_len: int) -> list[float]:
        """Visit fractions over the FULL menu; unexpanded options 0."""
        tot = sum(self.n.values())
        pi = [0.0] * menu_len
        if tot:
            for a, c in self.n.items():
                pi[a] = c / tot
        return pi


def pi_mix_of(
    visits: list[float], probs: list[float], w: float = PI_MIX_VISIT_WEIGHT
) -> list[float]:
    """/72 AZ-v3 distill target: ``w*visit_fracs + (1-w)*net_menu_probs`` over
    the FULL menu. Unexpanded options keep ``(1-w)*p_net`` instead of a hard
    zero — the hard-zero brittleness hardened visit noise into the /72 pi
    targets. Renormalised exactly so the sum==1 verify law holds."""
    if not visits or len(visits) != len(probs):
        raise ValueError("pi_mix_of: menu-length mismatch")
    mix = [w * v + (1.0 - w) * p for v, p in zip(visits, probs)]
    tot = sum(mix)
    return [x / tot for x in mix] if tot > 0 else [1.0 / len(mix)] * len(mix)


def adv_mix_of(means: dict[int, float], chosen: int, net_idx: int) -> float:
    """IMPROVEMENT label (/74 §5, on-policy values; /83 fix: ``chosen`` is
    now the VALUE-top1 arm, not the visit-top1 arm): ``value(value-top1
    option) - value(champion-pick option)`` — the root net's own argmax pick
    is the champion — from the ROOT SEAT's view, over arm mean backed
    values. In [-1, 1] by construction. 0.0 when the champion pick is the
    value top1 itself or was never evaluated (its apply fork crashed)."""
    if chosen == net_idx or chosen not in means or net_idx not in means:
        return 0.0
    return max(-1.0, min(1.0, means[chosen] - means[net_idx]))


# ---------------------------------------------------------------- gold labelling
# /83 SUPERSEDED fix: episode gold derives from BACKED VALUES, never from raw
# UCB visit fractions (the old visit-argmax gold concentrated 73% on menu
# index 0: the ``>`` UCB tie-break plus index-order prefix pulls leave the
# lowest evaluated index permanently a pull ahead). An ask is labelled
# ``"value"`` (gold = value-top1 arm) only when ALL THREE gates hold, else
# ``"net"`` (gold = root-net argmax, the honest expert pick):
#   * margin  — mean(value-top1) - mean(value-top2) > 0.05. That is half the
#     shaping nudge quantum (a +-2 life diff moves a cap-out value by 0.05):
#     anything smaller is inside the resolution of short-horizon rollouts.
#   * support — the value-top1 arm has >= 2 pulls; one rollout is a single
#     0/0.5/1 sample and cannot back a mean.
#   * coverage — N total pulls >= 2 * menu size. Under unvisited-first
#     allocation that means EVERY legal option was rolled out at least twice,
#     so value-top1 never outranks an arm that was never evaluated.
# Visit counts survive only as diagnostics (pi / top1_visit_share).
GOLD_VALUE_MARGIN = 0.05
GOLD_ARM_MIN_VISITS = 2
GOLD_MIN_N_PER_ARM = 2


def gold_from_values(
    means: dict[int, float],
    visits: dict[int, int],
    n_total: int,
    menu_len: int,
    net_idx: int,
    rng: random.Random | None = None,
) -> tuple[int, str, int]:
    """(/83 fix) ``(gold_idx, label_src, value_top1)`` with ``label_src`` in
    ``{'value', 'net'}``. Only EVALUATED arms (a mean backed value exists)
    are ranked; ``rng`` breaks value ties so no arm gets index-0 gravity.
    ``value_top1`` is the ranked winner regardless of the gates (the adv_mix
    diagnostic consumes it)."""
    if not means:
        return net_idx, "net", net_idx
    arms = sorted(means)
    top_v = max(means.values())
    tie = [a for a in arms if means[a] == top_v]
    top = tie[0] if rng is None or len(tie) == 1 else rng.choice(tie)
    rest = [means[a] for a in arms if a != top]
    decided = (
        (not rest or means[top] - max(rest) > GOLD_VALUE_MARGIN)
        and visits.get(top, 0) >= GOLD_ARM_MIN_VISITS
        and n_total >= GOLD_MIN_N_PER_ARM * menu_len
    )
    return (top, "value", top) if decided else (net_idx, "net", top)


# ------------------------------------------------- discovery / apply forks


class SearchError(RuntimeError):
    """The walk cannot continue at this position (no valid branch)."""


class _AnyFirstSeat:
    """Probe-lane proxy: raises on the FIRST ask of ANY seat (the engine or
    the rig lane both route through the per-seat agents, so one raise point
    covers both)."""

    def __init__(self, driver: SearchDriver, seat: int) -> None:
        self.driver, self.seat = driver, seat

    def decide(self, ctx: AskContext) -> int:
        d = self.driver
        raise _AskFound(
            AskRec(
                d.ask_count, ctx.vocab, site_kind(ctx.vocab), self.seat, d.lane, "?"
            ),
            ctx,
        )


@dataclass
class Branch:
    option: str
    idx: int
    game: Game
    boundary: str  # turn_top | pre_combat | post_combat | mid_act
    swallowed: tuple[AskRec, ...]  # asks default-answered inside the branch
    prefix_skipped: tuple[AskRec, ...] = ()  # always empty: root is the FIRST ask
    # mid_act stops carry the ask the branch is suspended AT (provably the
    # globally first future ask): the walk adopts it without a re-probe.
    next_ask: tuple[AskRec, AskContext] | None = None


@dataclass
class Probe:
    """One default-play probe of a position. ``ask`` = the globally first
    ask (raise at the first ask of any seat); ``stalled`` carries a STALL
    end declared INSIDE the probe (CR 104.4b sets only ``reason``, never a
    world loser, so over_reason() cannot see it — see WalkCap incident,
    seed 9001 turn 17). A horizon ``turn cap`` reason is NOT an outcome and
    is cleared before adoption."""

    game: Game
    ask: tuple[AskRec, AskContext] | None
    stalled: str = ""


def _probe(pos: Position) -> Probe:
    if pos.game.over_reason() is not None:
        return Probe(pos.game, None, "")
    probe = fork(pos.game, pos.supply)
    drv = SearchDriver(probe.seed * 1_000_003 + 7, HeuristicTeacher(), "rollout")
    n = len(probe.world.player_order)
    drv.agents = {s: _AnyFirstSeat(drv, s) for s in range(n)}
    _wire(probe, drv)
    try:
        _run(probe, drv, probe.world.turn + DISCOVER_HORIZON, pos.boundary)
    except _AskFound as exc:
        return Probe(probe, (exc.rec, exc.ctx))
    except BaseException as error:
        raise SearchError(
            f"discover crashed: {type(error).__name__}: {error}"
        ) from error
    if (probe.reason or "").startswith("STALL"):
        return Probe(probe, None, probe.reason)
    if (probe.reason or "").startswith("turn cap"):
        probe.reason = ""  # a horizon hit is bookkeeping, not an outcome
    return Probe(probe, None, "")


def discover(pos: Position) -> tuple[AskRec, AskContext] | None:
    """The globally first ask of the position, or None (no ask in reach /
    game ended). Thin wrapper over :func:`_probe` for tests/callers."""
    return _probe(pos).ask


def _resume_stalls(game: Game) -> bool:
    """Would :func:`_play`'s stall rule (CR 104.4b) fire on the FIRST loop
    iteration of a resume of this game? A mid_act resume re-enters the active
    seat's turn top (no skip flags), so the stall check runs BEFORE the acts
    are re-asked — the probe-cache handover must honour it or the apply
    forks stall out and every arm dies (seed 9100 turn 8 incident)."""
    seat = game.world.active_player
    if seat is None:
        return False
    fp = _stall_fingerprint(game.executor)
    previous, streak = game.stall_seen.get(seat, (None, 0))
    return fp == previous and streak + 1 >= REPEAT_ROUNDS


def quiescent(pos: Position) -> Position:
    """Advance the position by default play through the discovery horizon;
    the probe's game becomes the position."""
    return Position(_probe(pos).game, pos.supply, "turn_top")


def _apply_word(pos: Position, info: AskRec, word: str, idx: int, seat: int) -> Branch:
    """Force ``word`` at the discovered ask and advance to a clean boundary,
    mirroring ``rollout.expand``'s apply mechanism exactly: same driver-seed
    formula, same desync tripwire, same mid_act unwind at the seat's next
    act menu. Rollouts always fork the branch game, never consume it."""
    branch = fork(pos.game, pos.supply)
    drv = SearchDriver(
        pos.game.seed * 1_000_003 + seat,
        HeuristicTeacher(),
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

    cap = pos.game.world.turn + DISCOVER_HORIZON
    boundary = ""
    next_ask = None
    try:
        _run(branch, drv, cap, pos.boundary, stop)
    except _StepComplete as exc:
        boundary = "mid_act"  # seat's next menu ask: clean stop
        rec, actx = exc.rec, exc.ctx
        if rec is not None and actx is not None:
            # Re-index to 0: from the suspended branch a fresh discovery
            # probe raises on THIS ask first, so the walk/probe view of the
            # position always sees it at ask index 0.
            next_ask = (AskRec(0, rec.site, rec.kind, rec.seat, rec.lane, "?"), actx)
    if not drv.applied:
        raise SearchError(
            f"apply: forced ask {info.index}@{info.site!r}/{word!r} never reached"
        )
    swallowed = tuple(r for r in drv.log if r.index > info.index)
    return Branch(
        word,
        idx,
        branch,
        boundary or drv.stop_boundary or "turn_top",
        swallowed,
        next_ask=next_ask,
    )


# -------------------------------------------------------------- root search


def _net_pulls(
    branches: dict[int, Branch],
    supply: Supply,
    net_spec: str,
    device: str,
    game_seed: int,
    seat: int,
    ask_ordinal: int,
    n_rollouts: int,
    turn_cap: int,
    ucb: Ucb1,
    buckets: Counter,
    mix: Counter,
) -> None:
    """Allocate + play the ``rollout_mix="net"`` pulls (/79 cost gate).

    UCB allocation stays EXACTLY sequential: the first ``min(n, arms)``
    pulls are the unvisited-index picks Ucb1 makes with an empty ledger —
    values cannot influence them — so they play CONCURRENTLY on forked
    branches and every parked net decision across the group is scored in ONE
    batched forward per rollout step (one model instance per process,
    ``tools/search/batch_net``). Pull k+1 needs values 1..k backed, so the
    tail stays serial by necessity; its single-seat forwards are dim-1
    batches on the same weights. Values are pushed in pull order either way.
    Same seed derivation, same fresh-per-pull-seat streams as the legacy loop."""
    from tools.search import batch_net

    arms = sorted(branches)
    prefix = min(n_rollouts, len(arms))
    BcAsk.fresh(net_spec, device)  # warm on THIS thread: no lazy CUDA load in workers
    bn = batch_net.NetBatcher()

    def rseed_of(t: int, arm: int) -> int:
        return stable_int("roll", game_seed, seat, ask_ordinal, arm, t)

    states = [fork(branches[arms[t]].game, supply) for t in range(prefix)]
    specs = [{s: BcAsk.fresh(net_spec, device) for s in (0, 1)} for _ in range(prefix)]
    seeds = [rseed_of(t, arms[t]) for t in range(prefix)]

    def record(arm: int, res: RolloutResult) -> None:
        v, bucket = rollout_value(res, seat)
        buckets[bucket] += 1
        mix["net"] += 2
        ucb.push(arm, v)

    for t, res in enumerate(batch_net.rollout_many(states, specs, seeds, turn_cap, bn)):
        record(arms[t], res)  # prefix values backed BEFORE any tail pick
    for t in range(prefix, n_rollouts):  # tail: exact UCB needs all prior values
        arm = ucb.pick()  # ledger here == exactly the sequential loop's state
        pols = {s: BcAsk.fresh(net_spec, device) for s in (0, 1)}
        record(
            arm,
            rollout(fork(branches[arm].game, supply), pols, rseed_of(t, arm), turn_cap),
        )


@dataclass
class SearchOutcome:
    pi: list[float]  # visit fractions over the FULL menu (diagnostic only)
    value: float  # mean backed value over all N pulls
    chosen: int  # argmax visits, ties -> seeded rng (the PLAYED arm)
    gold_idx: int  # episode label (/83 fix, gold_from_values)
    label_src: str  # 'value' | 'net' (which rule produced gold_idx)
    net_idx: int  # root-net argmax (top-1 of menu_probs)
    heur_idx: int  # greedy teacher pick at the same ask
    visits: dict[int, int]
    buckets: Counter  # decided / shaping / crash pull counts
    rollouts: int
    arm_crash: int  # apply forks that died (arm dropped)
    policy_mix: Counter = field(default_factory=Counter)  # seat-policy draws
    probe_cache: bool = False  # chosen branch exposed its own next ask
    apply_ms: float = 0.0
    rollout_ms: float = 0.0
    net_fwd: int = 1  # menu_probs is the root's only net forward
    net_fwd_ms: float = 0.0
    pi_mix: list[float] = field(default_factory=list)  # /72 AZ-v3 blend target
    adv_mix: float = 0.0  # /74 §5 IMPROVEMENT label (see adv_mix_of)
    branches: dict[int, Branch] = field(default_factory=dict, repr=False)


def root_search(
    pos: Position,
    info: AskRec,
    ctx: AskContext,
    seat: int,
    net: BcAsk,
    game_seed: int,
    ask_ordinal: int,
    k: int = K_DEFAULT,
    n_rollouts: int = N_ROLLOUTS_DEFAULT,
    turn_cap: int = TURN_CAP_DEFAULT,
    net_spec: str = NET_SPEC,
    policy_rng: random.Random | None = None,
    cheap_rollout: bool = True,
    rollout_mix: str = "mixed",
    rollout_device: str = "cpu",
) -> SearchOutcome:
    """One searched ask: root probs -> top-k arms -> UCB1 allocation of N
    rollouts -> soft pi + backed value. ``net`` (the seat's root instance)
    sees this ask exactly once in its causal stream (menu_probs appends the
    same block ``decide`` would). With ``cheap_rollout`` (default) the net
    never plays a rollout: seats draw greedy vs RANDOM 50/50.
    ``rollout_mix="greedy"`` (/72 AZ-v3) drives BOTH rollout seats with the
    greedy teacher — random drivers contaminated the backed values.
    ``rollout_mix="net"`` (/74 §5 IMPROVEMENT) drives BOTH seats with a
    FRESH instance of the root net on ``rollout_device`` (weights shared
    per-process via BcAsk's model cache) — on-policy values;
    ``cheap_rollout`` is then irrelevant."""
    rng = policy_rng or random.Random(stable_int("ucb", game_seed, seat, ask_ordinal))
    t_fwd = time.perf_counter()
    probs = net.menu_probs(ctx)
    fwd_ms = (time.perf_counter() - t_fwd) * 1000
    menu = list(ctx.candidates)
    net_idx = max(range(len(probs)), key=lambda i: (probs[i], -i))
    order = sorted(range(len(probs)), key=lambda i: (-probs[i], i))
    want = order[: max(1, min(k, len(order)))]
    if net_idx not in want:  # lock: argmax ALWAYS included
        want[0] = net_idx

    branches: dict[int, Branch] = {}
    arm_crash = 0
    t_apply = time.perf_counter()
    for i in want:
        try:
            branches[i] = _apply_word(pos, info, menu[i], i, seat)
        except BaseException:  # noqa: BLE001 - an arm that dies is dropped
            arm_crash += 1
    apply_ms = (time.perf_counter() - t_apply) * 1000
    if not branches:
        raise SearchError(f"all {len(want)} apply forks crashed at {info.site!r}")

    ucb = Ucb1(sorted(branches), rng=rng)
    buckets: Counter = Counter()
    mix: Counter = Counter()
    t_roll = time.perf_counter()
    if rollout_mix == "net":
        # /79 cost gate: BATCHED on-policy rollouts — one model instance per
        # process, all parked seats scored in one forward per rollout step
        # (tools/search/batch_net). UCB allocation stays exact-sequential.
        _net_pulls(
            branches,
            pos.supply,
            net_spec,
            rollout_device,
            game_seed,
            seat,
            ask_ordinal,
            n_rollouts,
            turn_cap,
            ucb,
            buckets,
            mix,
        )
    else:
        for t in range(n_rollouts):
            arm = ucb.pick()
            pols = {}
            for s in range(2):
                if rollout_mix == "greedy" or rng.random() < 0.5:
                    pols[s] = "greedy"
                    mix["greedy"] += 1
                elif cheap_rollout:
                    pols[s] = "random"
                    mix["random"] += 1
                else:
                    pols[s] = BcAsk.fresh(net_spec, rollout_device)
                    mix["net"] += 1
            rseed = stable_int("roll", game_seed, seat, ask_ordinal, arm, t)
            res = rollout(fork(branches[arm].game, pos.supply), pols, rseed, turn_cap)
            v, bucket = rollout_value(res, seat)
            buckets[bucket] += 1
            ucb.push(arm, v)
    rollout_ms = (time.perf_counter() - t_roll) * 1000

    pi = ucb.visit_fracs(len(menu))
    pi_mix = pi_mix_of(pi, list(probs))
    value = sum(ucb.q.values()) / max(1, sum(ucb.n.values()))
    chosen = ucb.best()  # PLAYED arm: visit-argmax, ties via the seeded rng
    means = {a: ucb.q[a] / ucb.n[a] for a in ucb.n if ucb.n[a]}
    # /83 fix: the episode GOLD comes from backed values, not visit fractions
    gold_idx, label_src, value_top1 = gold_from_values(
        means, dict(ucb.n), sum(ucb.n.values()), len(menu), net_idx, rng
    )
    adv_mix = adv_mix_of(means, value_top1, net_idx)
    chosen_cache = branches[chosen].next_ask is not None
    heur = HeuristicTeacher()
    heur_idx = heur.decide(ctx)
    if not 0 <= heur_idx < len(menu):
        heur_idx = 0  # probe contract guard (dagger_wave precedent)
    return SearchOutcome(
        pi=pi,
        value=value,
        chosen=chosen,
        gold_idx=gold_idx,
        label_src=label_src,
        net_idx=net_idx,
        heur_idx=heur_idx,
        visits={a: c for a, c in ucb.n.items() if c},
        buckets=buckets,
        rollouts=n_rollouts,
        arm_crash=arm_crash,
        policy_mix=mix,
        probe_cache=chosen_cache,
        apply_ms=apply_ms,
        rollout_ms=rollout_ms,
        net_fwd_ms=fwd_ms,
        pi_mix=pi_mix,
        adv_mix=adv_mix,
        branches=branches,
    )


# ------------------------------------------------------------- game walker


@dataclass
class GameStats:
    asks_searched: int = 0
    rollouts: int = 0
    buckets: Counter = field(default_factory=Counter)  # decided / shaping / crash
    arm_crash: int = 0
    swallowed: int = 0
    top1_visit_sum: float = 0.0
    abs_value_dev_sum: float = 0.0
    net_disagree: int = 0
    adv_mix_sum: float = 0.0  # /74 §5 IMPROVEMENT-label aggregates
    abs_adv_mix_sum: float = 0.0
    adv_gt01: int = 0  # asks where value-top1 beat the champion pick by >0.1
    adv_on_disagree_sum: float = 0.0  # cold-feet map: adv on net-disagree asks
    # /83 fix monitors: gold must not concentrate on menu index 0 (target:
    # ~1/mean menu size, was 0.73 via visit-argmax) and the value-rule must
    # report its own coverage; adv per-ask list feeds a bootstrap SE.
    gold_idx0_asks: int = 0
    gold_value_asks: int = 0  # asks whose label_src == 'value' (decided)
    adv_values: list[float] = field(default_factory=list)
    by_kind: dict[str, Counter] = field(default_factory=dict)
    setup_asks: int = 0
    # cost instrumentation (/69): where the CPU-minutes actually go
    probes: int = 0  # throwaway discovery probes RUN
    probe_cache_hits: int = 0  # probes SKIPPED via branch next_ask
    probe_ms: float = 0.0
    apply_ms: float = 0.0
    rollout_ms: float = 0.0
    net_fwd: int = 0  # net forwards (menu_probs at roots; 1 per searched ask)
    net_fwd_ms: float = 0.0
    policy_mix: Counter = field(default_factory=Counter)
    kind_top1: dict[str, float] = field(default_factory=dict)  # per ask-kind
    kind_dev: dict[str, float] = field(default_factory=dict)


def _row_of(
    what: str, obs: dict, cands: list[str], out: SearchOutcome
) -> dict[str, Any]:
    """bc_data_v2-compatible ask row + the search fields (pi, value)."""
    row = {
        "ordinal": 0,
        "what": what,
        "candidates": list(cands),
        "kind": site_kind(what),
        "obs": {k: v for k, v in obs.items() if not k.startswith("_")},
        "ground": [
            list(g)
            for g in bc_data_v2.ground_with(_cards_rows_of(obs), what, list(cands))
        ],
        "gold": True,
        "gold_idx": out.gold_idx,  # /83 fix: value/net rule, not visit argmax
        "label_src": out.label_src,  # 'value' | 'net' — which rule labelled it
        "pi": list(out.pi),  # NOT rounded: sum==1 +-1e-6 must hold exactly
        "pi_mix": list(out.pi_mix),  # /72 AZ-v3 blend target (same law)
        "value": round(out.value, 6),
        "adv_mix": round(out.adv_mix, 6),  # /74 §5 IMPROVEMENT label
        "net_idx": out.net_idx,
        "heur_idx": out.heur_idx,
    }
    return row


def verify_episode(ep: dict[str, Any]) -> None:
    """Encode-exactness law on one emitted episode (dagger_wave discipline):
    n_tokens == the encode_episode_v2 stream length, <= 1024, every row
    menu-aligned with a valid pi/value, gold rows grounded."""
    from tools.training import bc_data_v2 as v2

    enc = v2.encode_episode_v2(ep, v2.build_vocab_v2([ep]))
    assert len(enc["seq"]) == ep["n_tokens"], (ep["pack"], len(enc["seq"]))
    assert len(enc["seq"]) <= 1024, (ep["pack"], len(enc["seq"]))
    assert len(enc["gold"]) == sum(1 for r in ep["asks"] if r["gold"])
    for src in ep["asks"]:
        assert not any(k.startswith("_") for k in src["obs"])
        assert len(src["ground"]) == len(src["candidates"])
        assert len(src["pi"]) == len(src["candidates"])
        assert abs(sum(src["pi"]) - 1.0) < 1e-6, (ep["pack"], src["what"])
        if "pi_mix" in src:  # /72 AZ-v3 rows: blend target menu-aligned
            assert len(src["pi_mix"]) == len(src["candidates"])
            assert abs(sum(src["pi_mix"]) - 1.0) < 1e-6, (ep["pack"], src["what"])
            assert all(p >= 0.0 for p in src["pi_mix"])
        assert 0.0 <= src["value"] <= 1.0
        if "adv_mix" in src:  # /74 §5 rows: improvement label in [-1, 1]
            assert -1.0 <= src["adv_mix"] <= 1.0, (ep["pack"], src["what"])
        assert 0 <= src["gold_idx"] < len(src["candidates"])
        if "label_src" in src:  # /83 fix rows: the gold rule is recorded
            assert src["label_src"] in ("value", "net"), (ep["pack"], src["what"])
    for m in ep["gold_meta"]:  # meta must agree with the row it points at
        assert m["gold_idx"] == ep["asks"][m["pos"]]["gold_idx"], ep["pack"]
        if "label_src" in m:
            assert m["label_src"] == ep["asks"][m["pos"]]["label_src"], ep["pack"]


def gen_game(
    seed: int,
    deck_pairs_seed: int = DECK_PAIRS_SEED,
    k: int = K_DEFAULT,
    n_rollouts: int = N_ROLLOUTS_DEFAULT,
    turn_cap: int = ROLL_CAP_DEFAULT,
    net_spec: str = NET_SPEC,
    device: str = "cpu",
    cheap_rollout: bool = True,
    rollout_mix: str = "mixed",
    rollout_device: str = "cpu",
) -> dict[str, Any]:
    """One AlphaZero-style self-play game: both seats root-search with the
    same net (independent UCB streams by seed derivation). Returns episodes
    (verified) + per-game stats. Raises nothing: a crash ends the game and
    lands in the stats with the rows searched so far.

    Cost levers (/69): ``cheap_rollout`` keeps the net out of every rollout
    (greedy/random seats only; net = root menu_probs only) and an adopted
    branch that stopped mid_act hands the walk its next search root for
    free (probe cache — no throwaway re-walk)."""
    bc_data_v2.install_choose_stash()
    supply = get_supply("engine")
    decks = deal_decks(seed, deck_pairs_seed, supply)
    game = _setup_game(seed, supply, decks)
    stats = GameStats()
    nets = {s: BcAsk.fresh(net_spec, device) for s in (0, 1)}
    max_len = getattr(nets[0], "max_len", 1024)

    history: dict[int, list[dict]] = {0: [], 1: []}
    golds: dict[int, list[dict]] = {0: [], 1: []}

    crash = ""
    reason = ""
    pos: Position | None = None
    ask_ordinal = {0: 0, 1: 0}
    try:
        # --- open the game to the first turn_top (setup asks default-answered)
        drv = SearchDriver(seed, HeuristicTeacher(), "rollout")
        _wire(game, drv)
        _play(
            game,
            drv,
            list(game.world.player_order),
            1,
            resumed=False,
            stop_after=lambda g, b: b == "turn_top" and g.world.turn >= 1,
        )
        stats.setup_asks = len(drv.log)
        pos = Position(game, supply, "turn_top")
        stagnant = 0  # consecutive no-progress quiescent adopts
        pending: tuple[AskRec, AskContext] | None = None  # branch next_ask
        for _step in range(WALK_STEP_CAP):
            if pos.game.over_reason() is not None or pos.game.reason:
                break
            if pending is not None:
                if _resume_stalls(pos.game):
                    # the engine's own CR 104.4b rule fires on resume before
                    # the carried ask is ever re-asked: honest draw outcome
                    pos.game.reason = (
                        f"STALL (CR 104.4b repeated-loop draw: world fingerprint "
                        f"unchanged for {REPEAT_ROUNDS} consecutive rounds)"
                    )
                    break
                info, ctx = pending  # probe cache: branch exposed its own ask
                pending = None
                stats.probe_cache_hits += 1
            else:
                t_p = time.perf_counter()
                pr = _probe(pos)
                stats.probe_ms += (time.perf_counter() - t_p) * 1000
                stats.probes += 1
                if pr.stalled:
                    pos = Position(pr.game, supply, "turn_top")  # STALL draw
                    break
                if pr.ask is None:
                    if pr.game.world.turn == pos.game.world.turn:
                        stagnant += 1  # probe neither asked, stalled, advanced
                        if stagnant > 8:
                            raise SearchError("quiescent probe made no progress")
                    else:
                        stagnant = 0
                    pos = Position(pr.game, supply, "turn_top")  # quiescent
                    continue
                info, ctx = pr.ask
            seat = info.seat
            out = root_search(
                pos,
                info,
                ctx,
                seat,
                nets[seat],
                seed,
                ask_ordinal[seat],
                k=k,
                n_rollouts=n_rollouts,
                turn_cap=turn_cap,
                net_spec=net_spec,
                cheap_rollout=cheap_rollout,
                rollout_mix=rollout_mix,
                rollout_device=rollout_device,
            )
            ask_ordinal[seat] += 1
            stats.asks_searched += 1
            stats.rollouts += out.rollouts
            stats.buckets.update(out.buckets)
            stats.arm_crash += out.arm_crash
            stats.top1_visit_sum += max(out.pi) if out.pi else 0.0
            stats.abs_value_dev_sum += abs(out.value - 0.5)
            stats.net_disagree += int(out.chosen != out.net_idx)
            stats.adv_mix_sum += out.adv_mix
            stats.abs_adv_mix_sum += abs(out.adv_mix)
            stats.adv_gt01 += int(out.adv_mix > 0.1)
            stats.gold_idx0_asks += int(out.gold_idx == 0)
            stats.gold_value_asks += int(out.label_src == "value")
            stats.adv_values.append(out.adv_mix)
            if out.chosen != out.net_idx:
                stats.adv_on_disagree_sum += out.adv_mix
            stats.apply_ms += out.apply_ms
            stats.rollout_ms += out.rollout_ms
            stats.net_fwd += out.net_fwd
            stats.net_fwd_ms += out.net_fwd_ms
            stats.policy_mix.update(out.policy_mix)
            kd = stats.by_kind.setdefault(info.kind, Counter())
            kd["asks"] += 1
            kd["rollouts"] += out.rollouts
            kd["decided"] += out.buckets["decided"]
            kd["shaping"] += out.buckets["shaping"]
            kd["crash"] += out.buckets["crash"]
            kd["net_disagree"] += int(out.chosen != out.net_idx)
            kd["gold_idx0"] += int(out.gold_idx == 0)
            kd["gold_value"] += int(out.label_src == "value")
            stats.kind_top1[info.kind] = stats.kind_top1.get(info.kind, 0.0) + (
                max(out.pi) if out.pi else 0.0
            )
            stats.kind_dev[info.kind] = stats.kind_dev.get(info.kind, 0.0) + abs(
                out.value - 0.5
            )
            row = _row_of(info.site, ctx.world, list(ctx.candidates), out)
            n_gold = len(golds[seat])
            history[seat].append({"row": row})
            golds[seat].append(
                {
                    "row": n_gold,
                    "kind": info.kind,
                    "gold_idx": out.gold_idx,  # /83 fix: value/net gold rule
                    "label_src": out.label_src,
                    "heur_idx": out.heur_idx,
                    "policy_idx": out.net_idx,
                    "backings": [],
                    "value": out.value,
                }
            )
            # the chosen arm's branch game BECOMES the real game line
            branch = out.branches[out.chosen]
            pos = Position(branch.game, supply, branch.boundary)
            stats.swallowed += len(branch.swallowed)
            pending = branch.next_ask  # probe cache when boundary is mid_act
        else:
            crash = "WalkCap"
            reason = "walk step cap reached"
    except BaseException as error:  # noqa: BLE001 - recorded, never hidden
        crash = type(error).__name__
        reason = f"crash:{type(error).__name__}: {error}"

    # --- outcome of the walked game
    walked = pos.game if pos is not None else game
    world = walked.world
    losers = [s for s, h in enumerate(world.player_order) if walked.is_loser(h)]
    if not crash:
        if walked.reason.startswith("STALL"):
            result = "draw"  # CR 104.4b repeated-loop draw (no world loser)
        elif len(losers) >= 2:
            result = "draw"
        elif losers:
            result = f"seat{1 - losers[0]}"
        else:
            result = "undecided"
        reason = walked.reason or reason
        turns = walked.turns
    else:
        result, turns = "crash", walked.turns

    episodes: dict[int, list[dict]] = {}
    trunc = {"gold_row_overflow": 0}
    for seat in (0, 1):
        eps = chunk_seat(
            history[seat], golds[seat], max_len, seed, seat, "search", trunc
        )
        dw._renumber(eps)
        for ep in eps:
            ep["pack"] = ep["pack"].replace("daggerwave", "search")
            ep["card"] = ep["pack"]
            verify_episode(ep)
        episodes[seat] = eps
    return {
        "seed": seed,
        "result": result,
        "reason": reason,
        "crash": crash or None,
        "turns": turns,
        "stats": stats,
        "trunc": trunc,
        "episodes": episodes,
    }
