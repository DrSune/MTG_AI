"""Tests for the self-play package: honest features, a working heuristic, a sound network."""

from __future__ import annotations

import pickle
import random

import numpy as np
import pytest
import torch

from MTG_bot.bench.agents import UniformRandomAgent
from MTG_bot.core.executor.games import get_supply
from MTG_bot.core.identity import CardIdentity
from MTG_bot.core.state import ZONE_HAND, ZONE_LIBRARY
from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay.actor import RecordingHeuristic
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.rig import play_game


@pytest.fixture(scope="module")
def table() -> FT.CardTable:
    supply = get_supply("castable")
    return FT.CardTable.from_records({oid: r.card for oid, r in supply.pool.results.items()})


class _Probe:
    """Heuristic seat that, at its first act ask after turn 3, checks the hidden-info invariant:
    rewriting the opponent's hand and both libraries must not change this seat's encoding."""

    name = "probe"

    def __init__(self, table: FT.CardTable) -> None:
        self.inner = HeuristicAgent()
        self.table = table
        self.checked = 0

    def decide(self, ask, obs) -> int:
        ex = obs.executor
        if ask.kind == "act" and ex.world.turn >= 3 and not self.checked:
            before = FT.encode(ex, ask.seat, ask, self.table, obs.ctx)
            world = ex.world
            opp = world.player_order[1 - ask.seat]
            saved = {}
            hidden = list(world.players[opp].zone(ZONE_HAND).entries)
            for p in world.player_order:
                hidden += list(world.players[p].zone(ZONE_LIBRARY).entries)
            offered = {o.token for o in ask.options}
            for h in hidden:
                if str(h) in offered:
                    continue
                card = world.cards[h]
                saved[h] = card.identity
                card.identity = CardIdentity(oracle_id="00000000-0000-0000-0000-000000000000",
                                             name="Swapped", type_line="Creature", power="9",
                                             toughness="9", cmc=9)
            after = FT.encode(ex, ask.seat, ask, self.table, obs.ctx)
            for h, ident in saved.items():
                world.cards[h].identity = ident
            for key in before:
                assert np.array_equal(before[key], after[key]), key
            self.checked = 1
        return self.inner.decide(ask, obs)


def test_encoding_never_reads_hidden_cards(table) -> None:
    checked = 0
    for seed in (11, 12, 13):
        probe = _Probe(table)
        play_game(seed, [probe, HeuristicAgent()], deck_mode="coherent")
        checked += probe.checked
    assert checked >= 2


def test_encodings_are_consistent_over_whole_games(table) -> None:
    recs = [RecordingHeuristic(0, table), RecordingHeuristic(1, table)]
    res = play_game(5, recs, deck_mode="stress")
    assert res["crash"] is None
    samples = recs[0].samples + recs[1].samples
    assert len(samples) > 20
    for feats, idx, _wp in samples:
        e = feats["cards_i"].shape[0]
        k = feats["opts_i"].shape[0]
        assert 2 <= k <= FT.MAX_OPTIONS and 0 <= idx < k
        assert feats["cards_f"].shape == (e, FT.CF)
        refs = feats["opts_i"][:, 1:3]
        assert refs.min() >= 0 and refs.max() <= e + 2  # [none, me, opp, cards...]
        assert feats["cards_i"][:, 4].max(initial=0) <= e + 2


def test_heuristic_beats_uniform_random() -> None:
    wins = 0
    for seed in range(1, 11):
        seat = seed % 2
        agents = [None, None]
        agents[seat] = HeuristicAgent()
        agents[1 - seat] = UniformRandomAgent(random.Random(seed))
        res = play_game(seed, agents, deck_mode="stress" if seed % 3 else "coherent")
        wins += res["outcome"] == "win" and res["winner"] == seat
    assert wins >= 8


def test_network_is_equivariant_over_options_and_roundtrips(table, tmp_path) -> None:
    recs = [RecordingHeuristic(0, table), RecordingHeuristic(1, table)]
    play_game(7, recs, deck_mode="coherent")
    samples = recs[0].samples
    torch.manual_seed(0)
    net = M.build(table, d=32, layers=2, heads=4, ff=64).eval()
    for p in net.parameters():
        p.data.normal_(0, 0.1)
    feats = next(s[0] for s in samples if s[0]["opts_i"].shape[0] >= 3)
    rev = dict(feats)
    rev["opts_i"] = feats["opts_i"][::-1].copy()
    rev["opts_f"] = feats["opts_f"][::-1].copy()
    with torch.no_grad():
        a, va = net(M.collate([feats], "cpu"))
        b, vb = net(M.collate([rev], "cpu"))
    assert torch.allclose(a[0], b[0].flip(0), atol=1e-4)
    assert torch.allclose(va, vb, atol=1e-5)
    # padding other rows into a batch must not change a row's outputs
    with torch.no_grad():
        c, vc = net(M.collate([feats] + [s[0] for s in samples[:7]], "cpu"))
    k = feats["opts_i"].shape[0]
    assert torch.allclose(a[0, :k], c[0, :k], atol=1e-4) and torch.allclose(va[0], vc[0], atol=1e-5)
    path = tmp_path / "net.pt"
    M.save(str(path), net, table, {"note": "test"})
    net2, table2, extra = M.load(str(path))
    net2.eval()
    with torch.no_grad():
        a2, _ = net2(M.collate([feats], "cpu"))
    assert torch.allclose(a, a2) and extra["note"] == "test" and table2.oracle_ids == table.oracle_ids


def test_packed_collation_equals_collate(table) -> None:
    recs = [RecordingHeuristic(0, table), RecordingHeuristic(1, table)]
    play_game(9, recs, deck_mode="stress")
    feats = [s[0] for s in recs[0].samples + recs[1].samples]
    packed = M.pack(feats)
    assert len(packed) == len(feats)
    idx = np.array([5, 0, 17, 3, len(feats) - 1])
    a = M.collate([feats[i] for i in idx], "cpu")
    b = M.collate_packed(packed, idx, "cpu")
    for key in a:
        assert a[key].shape == b[key].shape, key
        assert torch.equal(a[key].float(), b[key].float()), key
    clone = pickle.loads(pickle.dumps(packed))
    assert np.array_equal(clone.cards_f, packed.cards_f) and len(clone) == len(packed)


class _CpuSlot:
    """Synchronous inference for tests: the worker slot's request protocol on a CPU net."""

    def __init__(self, net: torch.nn.Module) -> None:
        self.net = net

    @torch.no_grad()
    def infer(self, req: tuple):
        feats, want = req[5], (req[6] if len(req) > 6 else 0)
        logits, value = self.net(M.collate([feats], "cpu"))
        probs = torch.softmax(logits[0, : feats["opts_i"].shape[0]], -1)
        a = int(probs.argmax())
        if want == 0:
            return a
        if want == 1:
            return a, float(value[0])
        return a, float(value[0]), probs.tolist()


class _BlockPlanner:
    """The heuristic, except that it plans its blocks with the searcher (rig.before_blocks)."""

    name = "block-planner"

    def __init__(self, searcher) -> None:
        self.inner = HeuristicAgent()
        self.searcher = searcher
        self.plan, self.turn = None, -1
        self.planned = self.answered = 0

    def plan_blocks(self, game, seat: int) -> None:
        self.plan, self.turn = self.searcher.plan_blocks(game, seat), game.world.turn
        self.planned += self.plan is not None

    def decide(self, ask, obs) -> int:
        from tools.selfplay.search import block_answer

        if ask.kind == "block" and self.plan is not None and self.turn == obs.executor.world.turn:
            idx = block_answer(ask, self.plan)
            if idx is not None:
                self.answered += 1
                return idx
        return self.inner.decide(ask, obs)


def test_block_search_plans_at_the_pre_blocks_boundary(table) -> None:
    from tools.selfplay.search import Searcher

    torch.manual_seed(0)
    net = M.build(table, d=32, layers=2, heads=4, ff=64).eval()
    planned = answered = 0
    for seed in (21, 22, 23, 24):
        searcher = Searcher(_CpuSlot(net), 0, "learner", table, k=2, d=1, skip_p=1.01, seed=seed)
        planner = _BlockPlanner(searcher)
        res = play_game(seed, [planner, HeuristicAgent()], deck_mode="coherent")
        assert res["crash"] is None
        assert searcher.stats["sim_errors"] == 0
        planned += planner.planned
        answered += planner.answered
    assert planned >= 1 and answered >= 1


def test_pre_blocks_boundary_is_opt_in() -> None:
    """Only a policy with a before_blocks hook sees the pre_blocks boundary; every other
    caller's stop_after gets exactly the historical three."""
    from MTG_bot.bench.router import SeatRouter
    from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
    from MTG_bot.core.executor.games import TURN_CAP, _play, _setup_game, deal_decks
    from tools.selfplay.rig import SelfplayRouter

    supply = get_supply("castable", "M21")
    oracle = OracleIndex.for_sets("M21")
    seen: dict[str, set] = {}
    for cls in (SeatRouter, SelfplayRouter):
        game = _setup_game(31, supply, deal_decks(31, 1409, supply, "coherent"))
        agents = [UniformRandomAgent(random.Random(3)), UniformRandomAgent(random.Random(4))]
        router = cls(game, agents, [SeatLens(s, oracle, ViewOptions()) for s in (0, 1)],
                     supply=supply)
        boundaries: set = set()

        def stop(_g, b, out=boundaries) -> bool:
            out.add(b)
            return False

        _play(game, router, game.world.player_order, TURN_CAP, stop_after=stop)
        seen[cls.__name__] = boundaries
    assert {"turn_top", "pre_combat", "post_combat"} <= seen["SeatRouter"]
    assert "pre_blocks" not in seen["SeatRouter"] and "pre_blocks" in seen["SelfplayRouter"]


def test_feature_caches_are_bounded() -> None:
    """features._static keeps each identity it has seen alive; unbounded it leaked ~31 per game
    (a 22-hour run hit its memory floor). The cache must stay under its bound however many
    distinct identity objects pass through."""
    from MTG_bot.core.identity import CardIdentity

    FT._STATIC_CACHE.clear()
    for i in range(FT._CACHE_MAX + 500):
        ident = CardIdentity(oracle_id="00000000-0000-0000-0000-000000000000", name=f"c{i}",
                             type_line="Creature", power="1", toughness="1", cmc=1)
        FT._static(ident)
        assert len(FT._STATIC_CACHE) <= FT._CACHE_MAX
    assert FT._static(ident) is FT._static(ident)  # still a cache
