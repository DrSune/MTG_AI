"""True-future labels (docs/PLAN_LEARNING.md §1.1-1.4, §3): the policy cannot read what it must not,
labelling leaves the real game alone, the second future reshuffles both libraries whole, a
crashed future leaves the comparison paired, and the owner's 45/30/25 example in search and in
distillation."""

from __future__ import annotations

import random
from types import SimpleNamespace

import pytest
import torch

from MTG_bot.bench.protocol import Ask, Option
from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
from MTG_bot.core.executor.games import (
    TURN_CAP,
    _play,
    _setup_game,
    deal_decks,
    get_supply,
)
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_HAND, ZONE_LIBRARY
from tools.search.fork import fork
from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay import search as S
from tools.selfplay.actor import NetAgent
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import SelfplayRouter, play_game


@pytest.fixture(scope="module")
def table() -> FT.CardTable:
    supply = get_supply("castable")
    return FT.CardTable.from_records({oid: r.card for oid, r in supply.pool.results.items()})


@pytest.fixture(scope="module")
def net(table):
    torch.manual_seed(0)
    net = M.build(table, d=32, layers=1, heads=4, ff=64)
    for p in net.parameters():  # a fresh network's policy head is zero: every option would tie
        p.data.normal_(0, 0.1)
    return net.eval()


def _router(game, agents, supply):
    oracle = OracleIndex.for_sets("M21")
    return SelfplayRouter(game, agents, [SeatLens(s, oracle, ViewOptions()) for s in (0, 1)],
                          supply=supply)


def _private_rewrites(ex, seat):
    """What the deciding seat must not see, each as a rewrite of the live game (the opponent's
    hidden cards, which of its hand cards entered when, its private knowledge: its own answers to
    its mulligan and scry asks and its library's order; our own library's order), and the undo."""
    world = ex.world
    me, opp = world.player_order[seat], world.player_order[1 - seat]
    hand = world.players[opp].zone(ZONE_HAND).entries
    olib = world.players[opp].zone(ZONE_LIBRARY).entries
    mylib = world.players[me].zone(ZONE_LIBRARY).entries
    log = ex.decisions.ask_log
    saved = ({h: world.cards[h].identity for h in hand + olib}, list(hand), list(olib),
             list(mylib), list(log))
    swapped = CardIdentity(oracle_id="00000000-0000-0000-0000-000000000000", name="Swapped",
                           type_line="Creature", power="9", toughness="9", cmc=9)

    def hidden_cards():
        for h in hand + olib:
            world.cards[h].identity = swapped

    def hand_ages():
        idents = [world.cards[h].identity for h in hand]
        for h, ident in zip(hand, idents[1:] + idents[:1]):
            world.cards[h].identity = ident
        hand.reverse()

    def private_knowledge():
        log[:] = [(w, "rewritten" if str(opp) in w else a) for w, a in log]
        olib.reverse()

    def undo():
        idents, hand[:], olib[:], mylib[:], log[:] = saved
        for h, ident in idents.items():
            world.cards[h].identity = ident

    return [hidden_cards, hand_ages, private_knowledge, mylib.reverse], undo


def test_policy_outputs_never_read_the_opponents_private_state(table, net) -> None:
    """Guard (e), PLAN §1.2 and §3: at a real decision the network's encoding and outputs are
    byte-identical after each rewrite of what this seat cannot know."""
    slot = M.LocalSlot({"net": net})
    checked = []

    class Probe(HeuristicAgent):
        def decide(self, ask, obs):
            ex = obs.executor
            if ask.kind == "act" and ex.world.turn >= 4 and not checked:
                def outputs():
                    f = FT.encode(ex, ask.seat, ask, table, obs.ctx)
                    return [v.tobytes() for v in f.values()], slot.infer((0, 0, "net", True, False, f, 2))

                before = outputs()
                rewrites, undo = _private_rewrites(ex, ask.seat)
                for rewrite in rewrites:
                    rewrite()
                    assert outputs() == before, rewrite.__name__
                    undo()
                checked.append(1)
            return super().decide(ask, obs)

    for seed in (11, 12, 13):
        checked.clear()
        play_game(seed, [Probe(), HeuristicAgent()], deck_mode="coherent")
        if checked:
            return
    pytest.fail("no game reached an act decision on turn 4")


class _LogSlot:
    """A LocalSlot that keeps each request's encoding and the action it answered."""

    def __init__(self, net) -> None:
        self.inner = M.LocalSlot({"learner": net})
        self.rows: list = []

    def infer(self, req):
        answer = self.inner.infer(req)
        self.rows.append(([v.tobytes() for v in req[5].values()],
                          answer if isinstance(answer, int) else answer[0]))
        return answer


def test_labelling_leaves_the_real_game_and_its_decisions_alone(table, net, monkeypatch) -> None:
    """Guards (c) and (e): a game whose unsure decisions are forked for labels makes byte-identical
    decisions and ends in the same state as the same game unlabelled; the labels, computed after
    it from the forks, leave that state alone. Each label compares two Gumbel-drawn alternatives
    over two futures, scored from the labelled seat's side."""
    monkeypatch.setattr(S, "MAX_SIM_DECISIONS", 8)  # the playouts then run on the fallback: fast
    monkeypatch.setattr(S, "LABELS_PER_GAME", 2)
    monkeypatch.setattr(S, "CONFIDENT_SHARE", 1.0)  # every act decision is a candidate
    supply = get_supply("castable")
    job = {"gid": 0, "seats": ["learner", "heuristic"], "greedy": [True, True],
           "record": [False, False]}

    def run(label: bool, deal: int):
        slot = _LogSlot(net)
        lab = S.Labeller(slot, 0, "learner", table, pool_mode="castable", set_code="M21", k=2,
                         d=2, greedy=True, seed=5) if label else None
        game = _setup_game(deal, supply, deal_decks(deal, 1409, supply, "coherent"))
        router = _router(game, [NetAgent(slot, job, 0, table, lab), HeuristicAgent()], supply)
        _play(game, router, game.world.player_order, TURN_CAP)
        state, decisions = game.executor.state_fingerprint(), list(slot.rows)
        return state, decisions, (lab.labels() if lab else None), game

    # The untrained network may mulligan its hand away; take a deal where it makes two act
    # decisions or more.
    for deal in range(3, 9):
        state1, decisions1, labels, game = run(True, deal)
        if len(labels) == 2:
            break
    else:
        pytest.fail("no deal gave the network seat two act decisions")
    state0, decisions0, _, _ = run(False, deal)
    assert decisions1 == decisions0 and state1 == state0
    assert game.executor.state_fingerprint() == state1
    assert len(labels) == 2
    for lab in labels:
        assert len(lab["alts"]) == 2 and len(set(lab["alts"])) == 2 and len(lab["z"]) == 2
        assert all(z in (-1.0, 0.0, 1.0, None) for zf in lab["z"] for z in zf)


def test_a_true_world_reshuffles_both_libraries_whole() -> None:
    """A true world (the audit's) and the labeller's second future keep the deal's cards and
    shuffle both libraries whole, the same way for one seed. The journal pins nothing: it does
    not say which cards a scry kept or which zone a reveal showed, and reading it as if it did
    kept unseen cards in place, often the next draw (KNOWLEDGE/2026-11-12/197)."""
    supply = get_supply("castable")
    game = _setup_game(9, supply, deal_decks(9, 1409, supply))
    router = _router(game, [HeuristicAgent(), HeuristicAgent()], supply)
    _play(game, router, game.world.player_order, 1, stop_after=lambda g, b: b == "turn_top")
    players = game.world.player_order
    ex = game.executor
    # the journal rows that pinned cards: a scry's size, and Duress's hand reveal journalled as
    # the target's whole library
    ex.events.append((len(ex.events), "SCRY", str(players[0]), 2))
    lib1 = game.world.players[players[1]].zone(ZONE_LIBRARY).entries
    ex.events.append((len(ex.events), "REVEAL", str(players[1]),
                      tuple(str(h) for h in reversed(lib1))))
    zones = (ZONE_LIBRARY, ZONE_HAND)
    before = {(p, z): list(game.world.players[p].zone(z).entries) for p in players for z in zones}
    futures = []
    for _ in range(2):
        copy = fork(game, supply)
        S.reshuffle_libraries(copy, random.Random(7))
        futures.append({(p, z): list(copy.world.players[p].zone(z).entries)
                        for p in players for z in zones})
    assert futures[0] == futures[1]
    for p in players:
        assert futures[0][(p, ZONE_HAND)] == before[(p, ZONE_HAND)]
        a, b = futures[0][(p, ZONE_LIBRARY)], before[(p, ZONE_LIBRARY)]
        assert sorted(a) == sorted(b) and a[-2:] != b[-2:]  # the top moves like any card


def test_a_crashed_future_is_dropped_for_every_alternative() -> None:
    """PLAN §1.1 (m2): a future in which any alternative's playout crashed is left out for all of
    them, so every mean compares the alternatives on the same futures; futures may be weighted."""
    assert S.mean_scores({"a": [1.0, None, -1.0], "b": [0.0, 1.0, 1.0]}) == {"a": 0.0, "b": 0.5}
    assert S.mean_scores({"a": [None], "b": [1.0]}) is None
    assert S.mean_scores({"a": [1.0, -1.0], "b": [-1.0, 1.0]}, [3.0, 1.0]) == {"a": 0.5, "b": -0.5}


_PAYOFF = {"R1": {"A": 1.0, "B": -1.0, "C": -1.0}, "R2": {"A": -1.0, "B": 1.0, "C": 1.0}}
_BELIEF = {"A": 0.45, "B": 0.30, "C": 0.25}


def test_the_search_plays_the_answer_the_threats_share(table) -> None:
    """The owner's example (PLAN §1.4): the opponent holds threat A (45%), B (30%) or C (25%); R1
    answers A, R2 answers B and C. With that belief injected, the search averages each move over
    every sampled world and plays R2, though the network prefers R1; it still plays R2 when
    importance sampling draws A four times as often as B or C and weights each world back."""

    class Slot:
        def infer(self, req):
            return 0, 0.0, [0.7, 0.3]

    searcher = S.Searcher(Slot(), 0, "learner", table, pool_mode="castable", set_code="M21",
                          k=2, d=400, seed=0)
    searcher.simulate = lambda game, seat, token, world=None, **_: _PAYOFF[token][world]
    ask = Ask(seat=0, kind="act", site="act:player:0:5", prompt="",
              options=(Option("R1", "R1"), Option("R2", "R2")), refuse=0)
    for proposal in (_BELIEF, {"A": 0.8, "B": 0.1, "C": 0.1}):
        draws = random.Random(1).choices(list(proposal), list(proposal.values()), k=searcher.d)
        searcher.draw_worlds = lambda count, draws=draws, q=proposal: [(w, _BELIEF[w] / q[w]) for w in draws]
        assert searcher.choose(ask, SimpleNamespace(game=None, ctx=None), None) == 1


def test_distilling_per_world_labels_learns_the_shared_answer() -> None:
    """The owner's example as labels (PLAN §1.4): in positions the policy cannot tell apart, each
    true-future label credits the move that worked in its world. Distilling them, round after
    round, converges on R2 with the target in its linear regime, and stays at the 45/55 mixture
    with hard labels (argmax per label). A third option, outside the compared pair, keeps its
    probability."""
    worlds = [(0.45, (1.0, -1.0)), (0.30, (-1.0, 1.0)), (0.25, (-1.0, 1.0))]

    def distil(target):
        p = [0.4, 0.4, 0.2]
        for _ in range(1000):
            p = [sum(w * t for w, t in zip((w for w, _ in worlds), col))
                 for col in zip(*(target(p, q) for _, q in worlds))]
        return p

    linear = distil(lambda p, q: S.mmd_target(p, [0, 1], q, se=10.0))
    hard = distil(lambda p, q: [p[0] + p[1], 0.0, p[2]] if q[0] > q[1] else [0.0, p[0] + p[1], p[2]])
    assert linear[1] / (linear[0] + linear[1]) > 0.99 and linear[2] == pytest.approx(0.2)
    assert hard[1] / (hard[0] + hard[1]) == pytest.approx(0.55) and hard[2] == pytest.approx(0.2)
