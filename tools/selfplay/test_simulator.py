"""Tests for the opponent simulator (simulator.py) and its data (actor.Capture): capture changes
no game, the truth stays apart, no input reads a hidden card, and both decoders and the
yardstick are proper distributions over multisets."""

from __future__ import annotations

import itertools
import math
import random

import numpy as np
import pytest
import torch

from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
from MTG_bot.core.executor.games import _play, _setup_game, deal_decks, get_supply, identity_of
from MTG_bot.core.state import ZONE_HAND, ZONE_LIBRARY
from tools.selfplay import features as FT
from tools.selfplay import simulator as S
from tools.selfplay.actor import Capture
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import SelfplayRouter


@pytest.fixture(scope="module")
def table() -> FT.CardTable:
    supply = get_supply("castable")
    return FT.CardTable.from_records({oid: r.card for oid, r in supply.pool.results.items()})


def _game(seed: int, agents: list, turn_cap: int = 60):
    """rig.play_game on a coherent deal, keeping the game (its state digest)."""
    supply = get_supply("verified")
    game = _setup_game(seed, supply, deal_decks(seed, 1409, supply, "coherent"))
    oracle = OracleIndex.for_sets("M21")
    router = SelfplayRouter(game, agents, [SeatLens(s, oracle, ViewOptions()) for s in (0, 1)],
                            supply=supply)
    _play(game, router, game.world.player_order, turn_cap)
    return game


def test_capture_changes_no_game_and_keeps_the_truth_apart(table) -> None:
    plain = _game(21, [HeuristicAgent(), HeuristicAgent()])
    seats = [Capture(HeuristicAgent(), s, table, 1.0, 21) for s in (0, 1)]
    captured = _game(21, seats)
    assert captured.executor.state_fingerprint() == plain.executor.state_fingerprint()
    for seat in seats:
        assert len(seat.views) == len(seat.truth) > 20
        for view, (hand, library) in zip(seat.views, seat.truth, strict=True):
            assert not {"hand", "library"} & set(view)
            assert (len(hand), len(library)) == (view["h"], view["l"])
            # every card of the opponent's coherent 60 is public, in its hand or in its library
            assert len(view["public"]) + view["h"] + view["l"] == 60


class _Leak(HeuristicAgent):
    """At its first decision from turn 6 on, rewrites everything this seat cannot see (the
    opponent's hand and library cards, which of them entered when, both libraries' order) and
    checks that the simulator's input and output stay byte-identical."""

    def __init__(self, table, net) -> None:
        self.table, self.net, self.checked, self.window = table, net, 0, None

    def decide(self, ask, obs) -> int:
        ex = obs.executor
        world = ex.world
        if len(ask.options) > 1 and world.turn >= 6 and not self.checked:
            before = FT.sim_view(ex, ask.seat, ask, self.table, obs.ctx)
            out = self._run(before)
            opp = world.player_order[1 - ask.seat]
            zones = [world.players[opp].zone(ZONE_HAND), world.players[opp].zone(ZONE_LIBRARY),
                     world.players[world.player_order[ask.seat]].zone(ZONE_LIBRARY)]
            saved = [(z, list(z.entries)) for z in zones]
            idents = {h: world.cards[h].identity for z in zones[:2] for h in z.entries}
            rng = random.Random(5)
            pool = sorted(ex.binder.records)
            for h in idents:
                world.cards[h].identity = identity_of(ex.binder.records[rng.choice(pool)])
            for z in zones:
                rng.shuffle(z.entries)
            after = FT.sim_view(ex, ask.seat, ask, self.table, obs.ctx)
            for z, entries in saved:
                z.entries[:] = entries
            for h, ident in idents.items():
                world.cards[h].identity = ident
            assert before.keys() == after.keys()
            for key in before:
                assert np.array_equal(np.asarray(before[key]), np.asarray(after[key])), key
            for x, y in zip(out, self._run(after), strict=True):
                assert torch.equal(x, y)
            self.window = before["ev_i"]
            self.checked = 1
        return super().decide(ask, obs)

    def _run(self, view: dict) -> tuple:
        basic = int(np.flatnonzero(S.pool_rows(self.table, "M21")[1])[0])
        truth = [([basic] * view["h"], [basic] * view["l"])]
        b = S.Data.from_records([view], truth, ["M21"], self.table).batch(np.arange(1), "cpu")
        with torch.no_grad():
            return self.net(b)


def test_the_simulator_never_reads_hidden_cards(table) -> None:
    torch.manual_seed(0)
    net = S.Simulator(table, d=32, layers=1, heads=4, ff=64, window=True).eval()
    probe = _Leak(table, net)
    _game(23, [probe, HeuristicAgent()])
    assert probe.checked
    named = probe.window[:, 1] > FT.UNK
    assert (probe.window[:, 0] > 0).sum() >= 20 and named.sum() >= 5  # the window is not empty


def _multisets(rows: list[int], cap: dict[int, int], n: int) -> list[list[int]]:
    out = []
    for combo in itertools.combinations_with_replacement(sorted(rows), n):
        if all(combo.count(r) <= cap[r] for r in set(combo)):
            out.append(list(combo))
    return out


def test_hand_and_library_decoders_are_distributions_over_multisets(table) -> None:
    """Over a small candidate set (one basic, three capped cards) the hand probabilities of every
    hand that keeps the copy limit sum to one, and so do the library's given a hand."""
    torch.manual_seed(1)
    net = S.Simulator(table, d=32, layers=2, heads=4, ff=64, window=True).eval()
    seat = Capture(HeuristicAgent(), 0, table, 0.2, 31)
    _game(31, [seat, HeuristicAgent()], turn_cap=6)
    view = {**seat.views[-1], "h": 3, "l": 4}
    basic = int(np.flatnonzero(S.pool_rows(table, "M21")[1])[0])
    others = [r for r in range(2, len(table.oracle_ids)) if r != basic][:3]
    cap = {basic: S.BASIC_CAP, others[0]: 2, others[1]: 4, others[2]: 1}
    caps = np.zeros(len(table.oracle_ids), np.int64)
    caps[list(cap)] = list(cap.values())

    def logp(hands: list, libraries: list, which: int) -> float:
        data = S.Data.from_records([view] * len(hands), list(zip(hands, libraries, strict=True)),
                                   ["M21"] * len(hands), table)
        b = data.batch(np.arange(len(hands)), "cpu")
        b["cap"] = torch.as_tensor(caps).expand(len(hands), -1).clone()  # the toy candidates
        with torch.no_grad():
            return torch.logsumexp(net(b)[which].double(), 0).item()

    hands = _multisets(list(cap), cap, 3)
    assert math.isclose(logp(hands, [[basic] * 4] * len(hands), 0), 0.0, abs_tol=1e-4)
    hand = hands[len(hands) // 2]
    left = {r: c - hand.count(r) for r, c in cap.items()}
    libraries = _multisets(list(cap), left, 4)
    assert math.isclose(logp([hand] * len(libraries), libraries, 1), 0.0, abs_tol=1e-4)


def test_the_yardstick_is_a_distribution_over_hands_and_libraries() -> None:
    """A toy pool: five basics and two-colour spells. Given the public cards, the yardstick's
    hand probabilities sum to one over every possible hand, and its library probabilities sum
    to one over every library that completes the deck."""
    colours = "WUBRG"
    basics = {c: f"basic-{c}" for c in colours}
    spells = {"w1": "W", "w2": "W", "u1": "U", "wu": "WU", "g1": "G", "ub": "UB", "c0": ""}
    yard = S.Yardstick(basics, {k: set(v) for k, v in spells.items()}, lands=4, size=10)
    public = ["basic-W", "w1"]  # the pairs W/x stay possible, each as likely as it makes w1
    rows = sorted(set(basics.values()) | set(spells))
    total = 0.0
    for hand in itertools.combinations_with_replacement(rows, 2):
        total += math.exp(yard.logp(public, list(hand), None)[0])
    assert math.isclose(total, 1.0, rel_tol=1e-9)
    hand = ["basic-W", "u1"]
    unknown = 10 - len(public) - len(hand)
    total = 0.0
    for library in itertools.combinations_with_replacement(rows, unknown):
        total += math.exp(yard.logp(public, hand, list(library))[1])
    assert math.isclose(total, 1.0, rel_tol=1e-9)
    marginal = yard.logp(public, hand, None)[2]
    assert marginal["ub"] == 0.0  # every pair the public cards allow holds white
    assert 0.0 < marginal["wu"] < marginal["g1"] < marginal["basic-W"] < 1.0


def test_one_training_step_moves_every_trained_parameter(table) -> None:
    torch.manual_seed(2)
    net = S.Simulator(table, d=32, layers=1, heads=4, ff=64, window=True)
    seat = Capture(HeuristicAgent(), 1, table, 0.3, 41)
    _game(41, [HeuristicAgent(), seat], turn_cap=8)
    data = S.Data.from_records(seat.views, seat.truth, ["M21"] * len(seat.views), table)
    loss = S.loss(net, data.batch(np.arange(len(data)), "cpu"))
    loss.backward()
    dead = [n for n, p in net.named_parameters() if p.requires_grad and p.grad is None
            and not n.startswith(S.UNUSED)]
    assert not dead
    assert torch.isfinite(loss)
