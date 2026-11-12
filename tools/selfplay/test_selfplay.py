"""Tests for the self-play package: honest features, a working heuristic, a sound network."""

from __future__ import annotations

import pickle
import random
from collections import Counter

import numpy as np
import pytest
import torch

from MTG_bot.bench.agents import UniformRandomAgent
from MTG_bot.core.executor.games import get_supply
from MTG_bot.core.identity import CardIdentity, Handle
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
    """Heuristic seat that checks the hidden-info invariant at every one of its decisions:
    rewriting the opponent's hand and both libraries (all but the cards the ask itself offers or
    shows, a search or a scry) must not change this seat's encoding."""

    name = "probe"

    def __init__(self, table: FT.CardTable) -> None:
        self.inner = HeuristicAgent()
        self.table = table
        self.kinds: Counter = Counter()

    def decide(self, ask, obs) -> int:
        ex = obs.executor
        world = ex.world
        before = FT.encode(ex, ask.seat, ask, self.table, obs.ctx)
        opp = world.player_order[1 - ask.seat]
        hidden = list(world.players[opp].zone(ZONE_HAND).entries)
        for p in world.player_order:
            hidden += list(world.players[p].zone(ZONE_LIBRARY).entries)
        shown = {o.token for o in ask.options} | {str(obs.ctx.revealed)}
        saved = {}
        for h in hidden:
            if str(h) in shown:
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
            assert np.array_equal(before[key], after[key]), (ask.kind, key)
        self.kinds[ask.kind] += 1
        return self.inner.decide(ask, obs)


def test_encoding_never_reads_hidden_cards(table) -> None:
    kinds: Counter = Counter()
    for seed, mode in ((11, "coherent"), (12, "coherent"), (13, "stress"), (14, "stress")):
        probe = _Probe(table)
        play_game(seed, [probe, HeuristicAgent()], deck_mode=mode)
        kinds += probe.kinds
    assert sum(kinds.values()) >= 100 and {"act", "attack", "block"} <= set(kinds), kinds


class _Observer:
    """The heuristic, logging every ask it answers with the encoding its seat sees."""

    name = "observer"

    def __init__(self, table: FT.CardTable) -> None:
        self.inner = HeuristicAgent()
        self.table = table
        self.seen: list[tuple] = []

    def decide(self, ask, obs) -> int:
        feats = FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx)
        self.seen.append((ask.kind, ask.site, tuple(o.token for o in ask.options), feats))
        return self.inner.decide(ask, obs)


def test_a_pass_looks_the_same_whatever_the_passer_holds(table) -> None:
    """DESIGN_PRIORITY §2.1.4, §4.4: two games differing only by the opponent's hand card, a Shock
    it could cast at every priority point (it is asked, and passes) or an Onakke Ogre it never can
    with one Mountain (it is not asked): the observer's asks, its encodings and the journal are the
    same, so whether the opponent was asked reveals nothing of its hand."""
    from MTG_bot.bench.agents import PassAgent
    from MTG_bot.bench.test_router import _arranged, _lenses
    from MTG_bot.core.executor.games import TURN_CAP, _play
    from tools.selfplay.rig import SelfplayRouter

    runs = []
    for held in ("Shock", "Onakke Ogre"):
        game, supply = _arranged(hand0=("Fierce Empath",), field0=("Forest",) * 3 + ("Staunch Shieldmate",),
                                 field1=("Mountain",), hand1=(held,))
        observer, opponent = _Observer(table), PassAgent()
        router = SelfplayRouter(game, [observer, opponent], _lenses(), supply=supply)
        _play(game, router, game.world.player_order, min(TURN_CAP, 4), resumed=True)
        runs.append((observer.seen, game.executor.journal.dump(), router.stats[1]["ask:priority"]))
    (seen_a, journal_a, asked_a), (seen_b, journal_b, asked_b) = runs
    # at instant speed the Shock's holder was asked (and passed), the Ogre's never
    assert asked_a > 0 and asked_b == 0
    assert journal_a == journal_b
    assert [s[:3] for s in seen_a] == [s[:3] for s in seen_b] and len(seen_a) >= 5
    for (kind, site, _, fa), (_, _, _, fb) in zip(seen_a, seen_b, strict=True):
        for key in fa:
            assert np.array_equal(fa[key], fb[key]), (kind, site, key)


def test_the_stack_its_order_targets_and_abilities_reach_the_encoding(table) -> None:
    """DESIGN_PRIORITY §3.2: with Bone Pit Brute's trigger (aimed at the Ox) and a Shock (aimed
    at seat 1) waiting on the stack, seat 1's encoding gives each object its depth (the Shock on
    top), the trigger its kind, its ability index and a pointer to the Brute, each object a
    pointer to its first target, the targets a mark, and the step and the pass."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from run_scenarios import ScenarioRunner

    from MTG_bot.bench.protocol import Ask, Option

    pack = {"set": "M21", "world": {"life": 20, "seed": 7}, "mana": {"0": {"R": 1}}, "steps": [],
            "cards": [{"key": "brute", "real": "Bone Pit Brute", "zone": "hand", "controller": 0},
                      {"key": "shock", "real": "Shock", "zone": "hand", "controller": 0},
                      {"key": "ox", "name": "Ox", "type": "Creature", "power": "2",
                       "toughness": "2", "zone": "battlefield", "controller": 0}]}
    r = ScenarioRunner(pack, get_supply("all", "M21"))
    r.run_step({"op": "enter", "key": "brute", "hold": True, "decisions": ["ox"]})
    r.run_step({"op": "cast", "key": "shock", "real": "Shock", "targets": ["p1"], "hold": True})
    ex = r.ex
    ex.pass_priority()  # seat 0 passes: seat 1 holds priority
    ask = Ask(seat=1, kind="priority", site=f"priority:{r.seats[1]}", prompt="",
              options=(Option("PASS", "pass"),), refuse=0)
    f = FT.encode(ex, 1, ask, table)
    trig, spell = (frame.handle for frame in ex.stack.frames)
    p0, p1 = r.seats
    # the encoder's entity order: the stack top first, the decider's hand and battlefield, the
    # opponent's battlefield (nothing else is in a public zone here)
    zones = ex.world.players
    ents = [fr.handle for fr in reversed(ex.stack.frames)]
    ents += zones[p1].zone("hand").entries + zones[p1].zone("battlefield").entries
    ents += zones[p0].zone("battlefield").entries
    assert len(ents) == f["cards_i"].shape[0]
    ci, cf = f["cards_i"], f["cards_f"].astype(np.float32)
    s, t, ox, brute = (ents.index(h) for h in (spell, trig, r.handles["ox"], r.handles["brute"]))
    assert 0 < cf[s, FT.F_STACK_DEPTH] < cf[t, FT.F_STACK_DEPTH]  # the Shock resolves first
    assert cf[t, FT.F_TRIGGERED] == 1 and cf[t, FT.F_ACTIVATED] == 0 and cf[s, FT.F_TRIGGERED] == 0
    assert ci[t, FT.C_SOURCE] == brute + 3  # entities: the two players, then the cards; +1
    assert ci[t, FT.C_TARGET] == ox + 3
    assert ci[s, FT.C_TARGET] == 1  # the Shock's target is seat 1, the decider: entity 0, +1
    assert cf[ox, FT.F_STACK_TARGETED] > 0 and cf[brute, FT.F_STACK_TARGETED] == 0
    players = f["players_f"].astype(np.float32)
    assert players[0, FT.P_STACK_TARGETED] > 0 and players[1, FT.P_STACK_TARGETED] == 0
    glob = f["glob_f"].astype(np.float32)
    assert glob[FT.G_STEP0 + FT.STEPS.index("FIRST_MAIN")] == 1 and glob[FT.G_PASSED] == 1


def test_unbounded_numbers_stay_finite_and_ordered() -> None:
    x = np.array([0.0, 3.0, -20.0, 21.0, 59136.0, 1e30, -1e30], dtype=np.float32)
    y = FT._squash(x)
    assert np.isfinite(y.astype(np.float16)).all()
    assert np.array_equal(y[:3], x[:3])
    assert y[3] < y[4] < y[5] and y[6] == -y[5]


def test_encodings_are_consistent_over_whole_games(table) -> None:
    recs = [RecordingHeuristic(0, table), RecordingHeuristic(1, table)]
    res = play_game(5, recs, deck_mode="stress")
    assert res["crash"] is None
    samples = recs[0].samples + recs[1].samples
    assert len(samples) > 20
    for feats, idx in samples:
        e = feats["cards_i"].shape[0]
        k = feats["opts_i"].shape[0]
        assert 2 <= k <= FT.MAX_OPTIONS and 0 <= idx < k
        assert feats["cards_f"].shape == (e, FT.CF)
        refs = feats["opts_i"][:, 1:3]
        assert refs.min() >= 0 and refs.max() <= e + 2  # [none, me, opp, cards...]
        assert feats["cards_i"][:, 4].max(initial=0) <= e + 2


def test_heuristic_beats_uniform_random() -> None:
    """The teacher works. It wins ~0.9 against uniform random (0.92 on 200 coherent games,
    2026-11-11), so 14 of 20 fails a working teacher with p = 0.005 and passes a coin-flip one with
    p = 0.06."""
    wins = 0
    for seed in range(1, 21):
        seat = seed % 2
        agents = [None, None]
        agents[seat] = HeuristicAgent()
        agents[1 - seat] = UniformRandomAgent(random.Random(seed))
        res = play_game(seed, agents, deck_mode="stress" if seed % 3 else "coherent")
        wins += res["outcome"] == "win" and res["winner"] == seat
    assert wins >= 14, wins


def test_grow_keeps_the_function(table, tmp_path) -> None:
    """A grown network computes what it was grown from (PLAN_CEILING §4.1): deeper (identity
    layers) exactly, wider (feed-forward units with zero outgoing weights) to rounding, and so
    after save and load; the new layers are not clones of one another."""
    recs = [RecordingHeuristic(0, table), RecordingHeuristic(1, table)]
    play_game(7, recs, deck_mode="coherent")
    batch = M.collate([s[0] for s in recs[0].samples[:16]], "cpu")
    torch.manual_seed(0)
    net = M.build(table, d=32, layers=2, heads=4, ff=64).eval()
    for p in net.parameters():
        p.data.normal_(0, 0.1)
    deep = M.grow(net, table, layers=4).eval()
    big = M.grow(net, table, layers=4, ff=128).eval()
    M.save(str(tmp_path / "big.pt"), big, table)
    loaded = M.load(str(tmp_path / "big.pt"))[0].eval()
    assert (big.config["layers"], big.config["ff"]) == (4, 128) == (
        loaded.config["layers"], loaded.config["ff"])
    with torch.no_grad():
        a, va = net(batch)
        ok = torch.isfinite(a)
        d, vd = deep(batch)
        assert torch.equal(a, d) and torch.equal(va, vd)
        for b, vb in (big(batch), loaded(batch)):
            assert torch.equal(ok, torch.isfinite(b))
            assert torch.allclose(a[ok], b[ok], atol=1e-5) and torch.allclose(va, vb, atol=1e-5)
    layers = deep.encoder.layers
    assert not torch.equal(layers[1].self_attn.in_proj_weight, layers[3].self_attn.in_proj_weight)
    assert not layers[1].linear2.weight.any() and not layers[1].self_attn.out_proj.bias.any()
    with pytest.raises(ValueError, match="grow"):
        M.grow(net, table, layers=3)


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


class _BlockPlanner:
    """The heuristic, except that it plans its blocks with the searcher (rig.before_blocks)."""

    name = "block-planner"

    def __init__(self, searcher) -> None:
        self.inner = HeuristicAgent()
        self.searcher = searcher
        self.plan, self.turn = None, -1
        self.planned = self.answered = 0

    def plan_blocks(self, game, seat: int, declared_attackers=frozenset()) -> None:
        self.plan = self.searcher.plan_blocks(game, seat, declared_attackers)
        self.turn = game.world.turn
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
        searcher = Searcher(M.LocalSlot({"learner": net}), 0, "learner", table, pool_mode="castable",
                            set_code="M21", k=2, d=1, skip_p=1.01, seed=seed)
        planner = _BlockPlanner(searcher)
        res = play_game(seed, [planner, HeuristicAgent()], deck_mode="coherent")
        assert res["crash"] is None
        assert searcher.stats["sim_errors"] == 0
        planned += planner.planned
        answered += planner.answered
    assert planned >= 1 and answered >= 1


def test_every_router_sees_every_boundary() -> None:
    """stop_after is consulted at the turn top, before the declarations of attackers and of
    blockers, and at every priority point, whichever router plays."""
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
    for name in ("SeatRouter", "SelfplayRouter"):
        assert seen[name] == {"turn_top", "pre_attacks", "pre_blocks", "priority"}, name


def test_feature_caches_are_bounded() -> None:
    """features._static keeps each identity it has seen alive, so the cache must stay under its
    bound however many distinct identity objects pass through."""
    from MTG_bot.core.identity import CardIdentity

    FT._STATIC_CACHE.clear()
    for i in range(FT._CACHE_MAX + 500):
        ident = CardIdentity(oracle_id="00000000-0000-0000-0000-000000000000", name=f"c{i}",
                             type_line="Creature", power="1", toughness="1", cmc=1)
        FT._static(ident)
        assert len(FT._STATIC_CACHE) <= FT._CACHE_MAX
    assert FT._static(ident) is FT._static(ident)  # still a cache


def test_scry_context_reveals_only_the_viewed_window() -> None:
    """Every scry ask reveals one of the top n cards of that scry. The engine asks once per card
    under one key per (player, n), and the counter resets only when an act window opens, so a
    second scry of the same size in one window must start at the top again, not point under the
    window at a card its owner has not seen. Driven directly, so it does not depend on a deal
    containing that window."""
    from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
    from tools.selfplay import rig
    supply = get_supply("castable")
    game = rig._setup_game(7, supply, rig.deal_decks(7, 1409, supply, "coherent"))
    lenses = [SeatLens(s, OracleIndex.for_sets("M21"), ViewOptions()) for s in (0, 1)]
    router = rig.SelfplayRouter(game, [HeuristicAgent(), HeuristicAgent()], lenses, supply=supply)
    seat = game.world.player_order[0]
    library = game.world.players[seat].zone(ZONE_LIBRARY).entries
    seen = []
    for _ in range(4):  # two scries of two cards in one act window
        router._context(f"scry:{seat}:2", seat, 0)
        seen.append(router._revealed)
    assert seen == [library[-1], library[-2], library[-1], library[-2]]


def test_table_extension_reads_new_cards_through_known_components(table) -> None:
    """New cards get rows in the SAME component vocabulary and the unknown-card name; a grown
    network still answers the old cards exactly as before."""
    from MTG_bot.core.executor.games import get_supply as supply_of

    torch.manual_seed(0)
    net = M.build(table, d=32, layers=2, heads=4, ff=64).eval()
    recs = {oid: r.card for oid, r in supply_of("castable", "M20").pool.results.items()}
    t2, stats = table.extend(recs)
    assert stats["added"] > 100 and stats["known_share"] > 0.95
    assert t2.ir_vocab == table.ir_vocab and t2.oracle_ids[: len(table.oracle_ids)] == table.oracle_ids
    recs_play = [RecordingHeuristic(0, table), RecordingHeuristic(1, table)]
    play_game(7, recs_play, deck_mode="coherent")
    feats = recs_play[0].samples[5][0]
    with torch.no_grad():
        before, _ = net(M.collate([feats], "cpu"))
        M.extend_cards(net, t2)
        after, _ = net(M.collate([feats], "cpu"))
    assert torch.allclose(before, after, atol=1e-5)
    assert torch.equal(net.name_emb.weight[-1], net.name_emb.weight[FT.UNK])
    assert net.ir_table.shape[0] == len(t2.oracle_ids)


def test_table_refresh_is_idempotent_and_grows_the_network(table) -> None:
    """Refreshing from the compile that built the table changes nothing; a refreshed table with
    new component types grows the network's component embedding with zero rows."""
    from MTG_bot.core.executor.games import get_supply as supply_of

    recs = {oid: r.card for oid, r in supply_of("castable", "M21").pool.results.items()}
    same, st = table.refresh(recs)
    assert st == {"rows_changed": 0, "tokens_added": 0, "new_tokens": []}
    assert same.ir == table.ir and same.ir_vocab == table.ir_vocab
    grown = FT.CardTable(table.oracle_ids, table.names, table.ir_vocab + ["New.Component"],
                         [row + [len(table.ir_vocab)] if i == 2 else row
                          for i, row in enumerate(table.ir)], table.max_ir)
    net = M.build(table, d=32, layers=2, heads=4, ff=64)
    M.extend_cards(net, grown)
    assert net.ir_emb.weight.shape[0] == len(table.ir_vocab) + 1
    assert torch.equal(net.ir_emb.weight[-1], torch.zeros(32))
    assert net.ir_table.shape[0] == len(table.oracle_ids) and net.config["n_ir"] == len(grown.ir_vocab)


class _CounterProbe:
    """Heuristic seat that, at its first act ask with a creature of its own on the battlefield,
    puts the engine's own counter kinds on its creatures and records the encoding."""

    name = "counter-probe"

    def __init__(self, table: FT.CardTable) -> None:
        self.inner = HeuristicAgent()
        self.table = table
        self.cards_f = None

    def decide(self, ask, obs) -> int:
        ex = obs.executor
        if ask.kind == "act" and self.cards_f is None:
            me = ex.world.player_order[ask.seat]
            mine = [h for h in ex.world.players[me].zone("battlefield").entries
                    if "Creature" in ex.world.cards[h].identity.type_line]
            if mine:
                for h in mine:
                    ex.world.cards[h].counters.update({"PLUS_1_PLUS_1": 2, "MINUS_1_MINUS_1": 1})
                self.cards_f = FT.encode(ex, ask.seat, ask, self.table, obs.ctx)["cards_f"]
                for h in mine:
                    ex.world.cards[h].counters.clear()
        return self.inner.decide(ask, obs)


def test_counters_reach_the_encoding(table) -> None:
    """The engine keys counters by CounterKind value (PLUS_1_PLUS_1), and the encoder's counter
    features read them by that key."""
    probe = _CounterProbe(table)
    play_game(7, [probe, HeuristicAgent()], deck_mode="coherent")
    assert probe.cards_f is not None
    f = probe.cards_f.astype(np.float32)
    assert np.isclose(f[:, FT.F_P1].max(), 2 / 3, atol=1e-3)
    assert np.isclose(f[:, FT.F_M1].max(), 1 / 3, atol=1e-3)


def test_every_engine_ask_kind_has_its_own_embedding_row() -> None:
    """Every engine ask kind has its own row: a kind missing from FT.ASK_KINDS reads as "other"."""
    from MTG_bot.bench.protocol import SITE_KINDS
    assert {k for k in SITE_KINDS if k not in FT.ASK_INDEX} == set()


def test_load_grows_ask_kinds_added_after_a_checkpoint(table, tmp_path) -> None:
    """A kind appended after a checkpoint starts as the kind it was encoded as before it existed:
    "other", or "act" for the second main phase's act menu, so an old network plays that menu as
    it plays the first main phase's."""
    net = M.build(table, d=32, layers=1, heads=4, ff=64)
    path = tmp_path / "old.pt"
    M.save(str(path), net, table)
    ck = torch.load(path, weights_only=False)
    n_old = FT.ASK_INDEX["other"] + 1
    ck["state"]["ask_emb.weight"] = ck["state"]["ask_emb.weight"][:n_old].clone()
    torch.save(ck, path)
    grown, _, _ = M.load(str(path))
    w = grown.ask_emb.weight.data
    assert w.shape[0] == len(FT.ASK_KINDS)
    assert torch.equal(w[:n_old], net.ask_emb.weight.data[:n_old])
    for k in FT.ASK_KINDS[n_old:]:
        assert torch.equal(w[FT.ASK_INDEX[k]], w[FT.ASK_INDEX[FT.ASK_GROWN_FROM.get(k, "other")]])
    assert torch.equal(w[FT.ASK_INDEX["act_second_main"]], w[FT.ASK_INDEX["act"]])


def test_the_encoding_tells_the_two_main_phases_apart(table) -> None:
    """The act menu of the second main phase, after combat (CR 505.1), is its own ask kind: the
    same board and menu encode differently in the two main phases."""
    from MTG_bot.bench.protocol import Ask

    game, router, me = _teach(hand0=("Forest",))

    def act_kind() -> int:
        options = tuple(option for option, _ in router._act_menu(game, me, 0))
        ask = Ask(seat=0, kind="act", site=f"act:{me}:{game.world.turn}", prompt="", options=options,
                  refuse=0)
        return int(FT.encode(game.executor, 0, ask, table)["ask_i"][0])

    assert act_kind() == FT.ASK_INDEX["act"]
    game.executor.combat_step(me)
    assert act_kind() == FT.ASK_INDEX["act_second_main"]


def test_manifest_appends_one_entry_per_start(tmp_path) -> None:
    """A resume adds a manifest entry; it never overwrites the first start's."""
    import json

    from tools.selfplay.learner import parse, write_manifest

    write_manifest(tmp_path, parse(["--run", str(tmp_path), "--seed", "5"]))
    write_manifest(tmp_path, parse(["--run", str(tmp_path), "--resume", str(tmp_path)]))
    entries = json.loads((tmp_path / "manifest.json").read_text())
    assert len(entries) == 2
    assert entries[0]["args"]["seed"] == 5 and entries[0]["args"]["resume"] == ""
    assert entries[1]["args"]["resume"] == str(tmp_path) and entries[1]["args"]["pool"] == "verified"
    for e in entries:
        assert len(e["git_commit"]) == 40 and isinstance(e["git_dirty"], bool)
        assert e["torch"] == torch.__version__ and e["host"] and e["started"]


def test_resume_refuses_another_pool(table, tmp_path, monkeypatch) -> None:
    """A run deals from one pool; a state file from before --pool existed was dealt castable."""
    from tools.selfplay import learner as L

    monkeypatch.setattr(L.Learner, "_start_workers", lambda self: None)
    src = tmp_path / "src"
    src.mkdir()
    M.save(str(src / "last.pt"), M.build(table, d=32, layers=1, heads=4, ff=64), table)
    (src / "state.pkl").write_bytes(pickle.dumps(
        {"it": 3, "stage": "teacher", "versions": [], "elo_games": []}))

    def learner(pool: str) -> L.Learner:
        return L.Learner(L.parse(["--run", str(tmp_path / pool), "--device", "cpu", "--d", "32",
                                  "--layers", "1", "--heads", "4", "--ff", "64", "--pool", pool]))

    with pytest.raises(ValueError, match="'castable' pool"):
        learner("verified").load_state(str(src))
    assert learner("castable").load_state(str(src))["it"] == 3


def test_the_run_seed_moves_the_training_deals(table, tmp_path, monkeypatch) -> None:
    """Runs of one lineage (each --init from the last) must not train again on the decks and
    shuffles an ancestor trained on: --seed moves the block of deals a run trains on."""
    from tools.selfplay import learner as L

    monkeypatch.setattr(L.Learner, "_start_workers", lambda self: None)

    def deals(run_seed: int) -> set[int]:
        lr = L.Learner(L.parse(["--run", str(tmp_path / str(run_seed)), "--device", "cpu",
                                "--d", "32", "--layers", "1", "--heads", "4", "--ff", "64",
                                "--seed", str(run_seed)]))
        lr.stage = "teacher"
        return {lr.curriculum_job()["seed"] for _ in range(50)}

    assert not deals(1) & deals(2)


def test_every_training_game_is_logged_with_its_deal(table, tmp_path, monkeypatch) -> None:
    """train_rows.jsonl gets one row per finished training game, a void one included: the deal
    (seed, deck mode, set), who played and the result, from which the deck critic rebuilds both
    decks (docs/PLAN_DRAFTER.md §3)."""
    import json

    from tools.selfplay import learner as L

    monkeypatch.setattr(L.Learner, "_start_workers", lambda self: None)
    lr = L.Learner(L.parse(["--run", str(tmp_path / "run"), "--device", "cpu", "--d", "32",
                            "--layers", "1", "--heads", "4", "--ff", "64"]))
    lr.it = 7
    deal = {"kind": "train", "seed": 11, "deck_mode": "coherent", "set_code": "M20",
            "seats": ["learner", "v1"], "turns": 9}
    lr.on_done([{**deal, "gid": 1, "outcome": "win", "winner": 0},
                {**deal, "gid": 2, "outcome": "void-crash", "winner": None}])
    rows = [json.loads(x) for x in (tmp_path / "run" / "train_rows.jsonl").read_text().splitlines()]
    assert [(r["gid"], r["it"], r["seed"], r["deck_mode"], r["set_code"], r["seats"],
             r["outcome"], r["winner"]) for r in rows] == [
        (1, 7, 11, "coherent", "M20", ["learner", "v1"], "win", 0),
        (2, 7, 11, "coherent", "M20", ["learner", "v1"], "void-crash", None)]


def test_training_rows_carry_their_game_and_step(table, tmp_path, monkeypatch) -> None:
    """A finished game's recorded decisions enter the buffer with the game id, the step and the
    game's step count, which --collect keeps for held-out games and game phases."""
    from tools.selfplay import learner as L

    monkeypatch.setattr(L.Learner, "_start_workers", lambda self: None)
    lr = L.Learner(L.parse(["--run", str(tmp_path / "run"), "--device", "cpu", "--d", "32",
                            "--layers", "1", "--heads", "4", "--ff", "64", "--gamma", "1",
                            "--lam", "1"]))
    lr.traj[(9, 0)] = [("f0", 0, -0.5, 0.1), ("f1", 1, -0.7, 0.3), ("f2", 0, -0.1, 0.6)]
    lr.on_done([{"kind": "train", "gid": 9, "seed": 3, "deck_mode": "coherent",
                 "set_code": "M21", "seats": ["learner", "v0"], "outcome": "win", "winner": 0,
                 "turns": 12}])
    assert [(b[0], b[6], b[7], b[8]) for b in lr.buffer] == [
        ("f0", 9, 0, 3), ("f1", 9, 1, 3), ("f2", 9, 2, 3)]
    assert [b[5] for b in lr.buffer] == pytest.approx([1.0] * 3)  # gamma = lambda = 1: z


def test_paired_reads_rows_with_and_without_set_and_pool(tmp_path, capsys) -> None:
    """One file can hold rows without set and pool beside rows with them."""
    import json

    from tools.selfplay import paired

    rows = []
    for seed in (1, 2):
        for a_seat in (0, 1):
            old = {"opp": "heuristic", "seed": seed, "deck_mode": "stress", "a_seat": a_seat,
                   "outcome": "win", "winner": a_seat}
            rows += [old, {**old, "seed": seed + 10, "set_code": "M21", "pool": "verified"}]
    path = tmp_path / "eval_rows.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    assert paired.main([str(path), str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["deals"] == 4


def test_gae_bootstraps_a_truncated_game() -> None:
    from tools.selfplay.learner import gae
    vals = [0.2, -0.4, -0.8]
    end = gae(vals, -1.0, 1.0, 0.95)
    cut = gae(vals, vals[-1], 1.0, 0.95)
    assert np.isclose(end[-1], -0.2) and cut[-1] == 0.0
    # a cut-off game is never worth more than playing the position out would be expected to be
    assert np.allclose(cut, [(-0.6) + 0.95 * (-0.4), -0.4, 0.0])


def test_learner_refuses_init_flags_without_init() -> None:
    """--refresh-table, --extend-sets and --mask-names act on the --init checkpoint, so without
    --init they are an error, never ignored."""
    from tools.selfplay.learner import parse
    with pytest.raises(SystemExit):
        parse(["--run", "/tmp/x", "--refresh-table"])
    assert parse(["--run", "/tmp/x", "--init", "a.pt", "--refresh-table"]).refresh_table


# ----------------------------------------------------------------- the teacher on the act menu


def _teach(hand0=(), field0=(), field1=(), **kw):
    """Seat 0's turn on an arranged board (MTG_bot/bench/test_router.py), the heuristic acting."""
    from MTG_bot.bench.test_router import P0, _arranged, _router

    game, supply = _arranged(hand0=hand0, field0=field0, field1=field1, **kw)
    router = _router(game, supply, HeuristicAgent())
    return game, router, P0


def _named(game, name):
    return next(h for h, c in game.world.cards.items() if c.identity.name == name)


def _main_phase(router, game, seat, limit=10) -> None:
    """``seat``'s decisions where it holds priority, until it passes (an undriven world: each
    action resolves before the next decision)."""
    for _ in range(limit):
        if not router.take_priority(game, seat):
            return


def test_heuristic_taps_a_mana_creature_only_for_a_spell_it_casts() -> None:
    game, router, me = _teach(hand0=("Fierce Empath",), field0=("Forest", "Forest", "Forest", "Llanowar Visionary"))
    _main_phase(router, game, me)
    assert game.world.zone_of(_named(game, "Fierce Empath")).kind == "battlefield"
    assert not game.world.cards[_named(game, "Llanowar Visionary")].tapped  # the lands paid
    game, router, me = _teach(hand0=("Fierce Empath",), field0=("Forest", "Forest", "Llanowar Visionary"))
    _main_phase(router, game, me)
    assert game.world.zone_of(_named(game, "Fierce Empath")).kind == "battlefield"
    assert game.world.cards[_named(game, "Llanowar Visionary")].tapped  # its {G} was the third mana


def test_heuristic_never_trades_two_mana_for_one() -> None:
    # Prismite's "{2}: Add one mana of any color" is a mana-cost filter: it never adds mana.
    game, router, me = _teach(hand0=("Pursued Whale",), field0=("Island", "Island", "Prismite"))
    _main_phase(router, game, me)
    assert not any(a.card == "Prismite" for a in router.acts)


def _at_their_end_step(hand1=(), field1=(), field0=()):
    """The heuristic is seat 1, holding priority in seat 0's end step (an arranged board)."""
    from MTG_bot.bench.agents import PassAgent
    from MTG_bot.bench.router import SeatRouter
    from MTG_bot.bench.test_router import P1, _arranged, _lenses
    from MTG_bot.core.executor.legality import END_STEP

    game, supply = _arranged(hand1=hand1, field1=field1, field0=field0)
    router = SeatRouter(game, [PassAgent(), HeuristicAgent()], _lenses(), supply=supply)
    game.executor.decisions.provider = router.answer
    game.executor.pass_until(END_STEP)
    return game, router, P1


def test_heuristic_casts_an_x_spell_at_its_largest_x() -> None:
    # An instant waits for the opponent's turn (DESIGN_PRIORITY §3.3): cast in its end step.
    game, router, me = _at_their_end_step(
        hand1=("Volcanic Geyser",), field1=("Mountain", "Mountain", "Island", "Island", "Island"),
        field0=("Walking Corpse",))
    _main_phase(router, game, me)
    assert [a.detail for a in router.acts if a.card == "Volcanic Geyser"] == ["1t:x3"]


def test_heuristic_names_the_opponents_most_expensive_public_card() -> None:
    from MTG_bot.core.ability_tree import Atom, AtomArgs, Verb

    game, _router, me = _teach(field0=("Plains",), field1=("Walking Corpse", "Pursued Whale"))
    source = _named(game, "Plains")
    game.executor.apply_effect(Atom(verb=Verb.CHOOSE_NAME, args=AtomArgs(pairs=())), source=source, controller=me)
    assert game.executor.name_choices[source] == "Pursued Whale"


def test_heuristic_never_casts_an_x_spell_for_x_zero() -> None:
    # Only X = 0 is payable ({G} for Wildwood Scourge): a 0/0 that dies at once is not a play.
    game, router, me = _teach(hand0=("Wildwood Scourge",), field0=("Forest",))
    _main_phase(router, game, me)
    assert not any(a.card == "Wildwood Scourge" for a in router.acts)


def test_heuristic_names_the_colour_its_treasure_is_for() -> None:
    # The colour comes from the spell the mana is for: a Treasure sacrificed for Walking Corpse
    # ({1}{B}) next to a Plains makes {B}, so the Corpse is cast.
    game, router, me = _teach(hand0=("Walking Corpse",), field0=("Plains",), tokens0=("Treasure",))
    _main_phase(router, game, me)
    assert game.world.zone_of(_named(game, "Walking Corpse")).kind == "battlefield"


def test_heuristic_never_taps_mana_for_a_play_it_will_not_make() -> None:
    # Wildwood Scourge with one {G} source is castable only at X = 0, which the teacher never casts.
    game, router, me = _teach(hand0=("Wildwood Scourge",), field0=("Llanowar Visionary",))
    _main_phase(router, game, me)
    assert not game.world.cards[_named(game, "Llanowar Visionary")].tapped and router.acts == []


class _AttacksWith:
    """Seat 0's driver: attacks with the creatures named, passes everything else."""

    name = "attacks"

    def __init__(self, *names: str) -> None:
        self.names = names

    def decide(self, ask, obs) -> int:
        tokens = [o.token for o in ask.options]
        if ask.kind == "attack" and "ATTACK" in tokens:
            card = obs.executor.world.cards[Handle("card", int(ask.site.split(":")[2]))]
            if card.identity.name in self.names:
                return tokens.index("ATTACK")
        return ask.refuse if ask.refuse is not None else 0


def test_heuristic_answers_at_instant_speed() -> None:
    """DESIGN_PRIORITY §3.3. Seat 1's heuristic counters seat 0's three-mana creature spell while it
    waits on the stack, and after seat 0 declares its attacker it aims Eliminate at the attacker,
    not at the bigger creature that stayed home."""
    from MTG_bot.bench.router import SeatRouter
    from MTG_bot.bench.test_router import P0, P1, _arranged, _lenses
    from MTG_bot.core.executor.legality import DECLARE_ATTACKERS
    from MTG_bot.core.executor.stack import cast

    game, supply = _arranged(hand0=("Onakke Ogre",), hand1=("Cancel",), field1=("Island",) * 3,
                             pool0={"R": 3})
    router = SeatRouter(game, [_AttacksWith(), HeuristicAgent()], _lenses(), supply=supply)
    ex = game.executor
    ex.decisions.provider = router.answer
    with ex.holding_priority():
        cast(ex, P0, _named(game, "Onakke Ogre"))
        ex.pass_priority()
    router.take_priority(game, P1)
    assert game.world.zone_of(_named(game, "Onakke Ogre")).kind == "graveyard"
    assert game.world.zone_of(_named(game, "Cancel")).kind == "graveyard"

    game, supply = _arranged(field0=("Walking Corpse", "Onakke Ogre"), hand1=("Eliminate",),
                             field1=("Swamp", "Swamp"))
    router = SeatRouter(game, [_AttacksWith("Walking Corpse"), HeuristicAgent()], _lenses(),
                        supply=supply)
    ex = game.executor
    ex.decisions.provider = router.answer
    ex.pass_until(DECLARE_ATTACKERS)
    assert ex.attackers == [_named(game, "Walking Corpse")]
    ex.pass_priority()
    router.take_priority(game, P1)
    assert game.world.zone_of(_named(game, "Walking Corpse")).kind == "graveyard"
    assert game.world.zone_of(_named(game, "Onakke Ogre")).kind == "battlefield"


def test_heuristic_aims_minus_n_at_the_opponent() -> None:
    # "Target creature gets -4/-4" compiles to PtDelta(DECREASE, 4), which is harmful: Grasp of
    # Darkness is aimed at the opponent's creature, not the teacher's own. An instant: held in its
    # own main phase, cast in the opponent's end step.
    game, router, me = _teach(hand0=("Grasp of Darkness",), field0=("Swamp", "Swamp", "Walking Corpse"),
                              field1=("Onakke Ogre",))
    _main_phase(router, game, me)
    assert game.world.zone_of(_named(game, "Grasp of Darkness")).kind == "hand"
    game, router, me = _at_their_end_step(
        hand1=("Grasp of Darkness",), field1=("Swamp", "Swamp", "Walking Corpse"), field0=("Onakke Ogre",))
    _main_phase(router, game, me)
    assert game.world.zone_of(_named(game, "Onakke Ogre")).kind == "graveyard"
    assert game.world.zone_of(_named(game, "Walking Corpse")).kind == "battlefield"


def test_x_rows_reach_the_encoding_with_their_card_and_x() -> None:
    """The router writes cast:<card>[:k][:x<N>]; the parser reads the card and X of every form."""
    from MTG_bot.core.identity import Handle
    c = Handle("card", 12)
    assert FT._parse_option("cast:card:12:x3") == (FT.OPT_INDEX["cast"], c, None, 0, 3.0, 0.0)
    assert FT._parse_option("cast:card:12:k:x2") == (FT.OPT_INDEX["cast_kicked"], c, None, 0, 2.0, 1.0)
    assert FT._parse_option("cast:card:12") == (FT.OPT_INDEX["cast"], c, None, 0, 0.0, 0.0)
    p1 = Handle("player", 1)  # a combat-window cast at a target, with X (stack.py)
    assert FT._parse_option("card:12@player:1:x4") == (FT.OPT_INDEX["cast_at"], c, p1, 0, 4.0, 0.0)
    assert FT._parse_option("card:12@player:1") == (FT.OPT_INDEX["cast_at"], c, p1, 0, 0.0, 0.0)


def test_a_candidate_that_wins_at_once_scores_a_win(table) -> None:
    """The engine ends a game with GameOver at the loss check (CR 704.3, 704.5a): a candidate act
    that wins inside the simulation scores as a win, not as a crashed simulation."""
    from MTG_bot.core.executor.games import TURN_CAP, RandomPolicy, _play, get_supply
    from tools.selfplay import rig
    from tools.selfplay.search import Searcher

    supply = get_supply("castable")
    game = rig._setup_game(7, supply, rig.deal_decks(7, 1409, supply, "coherent"))
    # the game's first priority point (turn 1's upkeep), where the simulation resumes
    _play(game, RandomPolicy(0), game.world.player_order, TURN_CAP,
          stop_after=lambda _g, boundary: boundary == "priority")
    torch.manual_seed(0)
    net = M.build(table, d=32, layers=1, heads=4, ff=64).eval()
    searcher = Searcher(M.LocalSlot({"learner": net}), 0, "learner", table, pool_mode="castable",
                        set_code="M21", k=2, d=1, seed=0)

    def winning_act(self, g, seat) -> bool:  # the act drains the opponent to 0: the check ends it
        opp = next(p for p in g.world.player_order if p != seat)
        g.world.players[opp].life = 0
        g.executor._player_losses()
        return True

    orig = rig.SelfplayRouter.take_priority
    rig.SelfplayRouter.take_priority = winning_act
    try:
        score = searcher.simulate(game, 0, "PASS")
    finally:
        rig.SelfplayRouter.take_priority = orig
    assert score == 1.0 and searcher.stats["sim_errors"] == 0


def test_a_determinized_world_cannot_foresee_the_real_games_randomness() -> None:
    """The engine draws randomness from sha256(master_seed:op_seq:tag), so each sampled world gets
    its own seed: with the real one the search would know every future coin flip."""
    import random as _random

    from MTG_bot.core.executor.games import get_supply
    from tools.selfplay import rig
    from tools.selfplay.search import determinize, fork

    supply = get_supply("castable")
    game = rig._setup_game(7, supply, rig.deal_decks(7, 1409, supply, "coherent"))
    flips = []
    for world in range(32):
        clone = fork(game, supply)
        determinize(clone, 0, supply, _random.Random(world))
        flips.append(clone.executor._rng("coin").random() < 0.5)
    real = game.executor._rng("coin").random() < 0.5
    assert 4 < sum(f == real for f in flips) < 28  # about half agree, not all of them


def test_a_redrawn_card_that_was_played_before_binds_its_new_identity() -> None:
    """A card played stays bound to its compiled record after it leaves the battlefield. When a
    bounce returns it to its owner's hand, a world re-draws it like any hidden card, and the copy
    must bind the new identity when it plays it: window 1's pilot lost 0.1-0.3% of its
    simulations to "attach_card: ... already carries ..." (KNOWLEDGE/2026-11-11/192)."""
    import random as _random

    from MTG_bot.core.state import ZONE_BATTLEFIELD
    from tools.selfplay import rig
    from tools.selfplay.search import determinize, fork

    supply = get_supply("castable")
    game = rig._setup_game(7, supply, rig.deal_decks(7, 1409, supply, "coherent"))
    world, ex = game.world, game.executor
    opp = world.player_order[1]
    land = next(h for h in world.players[opp].zone(ZONE_LIBRARY).entries
                if world.cards[h].identity.name in ("Plains", "Island", "Swamp", "Mountain", "Forest"))
    old = world.cards[land].identity.oracle_id
    world.move_to_zone(land, opp, ZONE_BATTLEFIELD)
    ex.binder.attach_card(land, ex.binder.records[old])  # played: bound, as stack.play_land binds
    world.move_to_zone(land, opp, ZONE_HAND)  # bounced
    hand = [world.cards[h].identity.oracle_id for h in world.players[opp].zone(ZONE_HAND).entries]
    lib = [world.cards[h].identity.oracle_id for h in world.players[opp].zone(ZONE_LIBRARY).entries]
    new = next(o for o in supply.deckable if o != old)
    hand[world.players[opp].zone(ZONE_HAND).entries.index(land)] = new
    clone = fork(game, supply)
    determinize(clone, 0, supply, _random.Random(0), (hand, lib))
    assert clone.world.cards[land].identity.oracle_id == new
    clone.executor.binder.attach_card(land, clone.executor.binder.records[new])  # raised before
    assert clone.executor.binder.handle_record[land].oracle_id == new
    assert ex.binder.handle_record[land].oracle_id == old  # the real game keeps its own binding


def test_gates_use_a_deal_level_interval_on_fresh_deals() -> None:
    """A deal's two seat-swapped games are anti-correlated, so the deal is the independent unit;
    and the teacher gate, like the self-play gate, never decides a freeze on the ladder's fixed
    deals."""
    from types import SimpleNamespace

    from tools.selfplay import learner as L
    assert L.deal_interval([0.5] * 200) == (0.5, 0.5)  # every deal split 1-0: no doubt at all
    lo, hi = L.deal_interval([1.0, 0.5, 0.5, 0.0] * 50)  # hand: sd sqrt(25/199) = 0.3544, h 0.0491
    assert (lo, hi) == (0.4509, 0.5491)
    fake = SimpleNamespace(n_gates=0, eval_queue=[])
    for kind in ("teacher", "gate", "ladder"):
        L.Learner.queue_eval(fake, kind, kind, "eval", ["heuristic"], 10)
    assert [q[5] for q in fake.eval_queue] == [L.GATE_SEED0, L.GATE_SEED0 + 1000, L.EVAL_SEED0]


def _ppo_case(table):
    recs = [RecordingHeuristic(0, table), RecordingHeuristic(1, table)]
    play_game(7, recs, deck_mode="coherent")
    samples = recs[0].samples + recs[1].samples
    n = len(samples)
    packed = M.pack([s[0] for s in samples])
    acts = np.array([s[1] for s in samples])
    torch.manual_seed(0)
    net = M.build(table, d=32, layers=1, heads=4, ff=64)
    torch.nn.init.normal_(net.policy_head[-1].weight, std=0.5)
    net.eval()
    with torch.no_grad():
        logits, _ = net(M.collate_packed(packed, np.arange(n), "cpu"))
        lp = torch.log_softmax(logits, -1).gather(1, torch.from_numpy(acts)[:, None]).squeeze(1)
    return net, packed, acts, lp.numpy().astype(np.float32), n


def test_ppo_stops_inside_the_epoch_once_the_update_has_moved(table) -> None:
    """--target-kl acts within an epoch, so also at --epochs 1. It bounds the update's own
    movement (KL from the policy at the start of the update): a large first step stops the epoch
    before the remaining minibatches."""
    from types import SimpleNamespace

    from tools.selfplay.ppo import ppo_train
    net, packed, acts, lp, n = _ppo_case(table)
    opt = torch.optim.AdamW(net.parameters(), lr=0.05)
    steps = []
    step = opt.step
    opt.step = lambda *a, **k: (steps.append(1), step(*a, **k))[1]
    a = SimpleNamespace(epochs=1, mb=16, tok_budget=10**9, clip=0.2, vclip=0.2, vcoef=0.5,
                        ent=0.0, max_grad=1.0, target_kl=0.03)
    adv = np.random.default_rng(0).standard_normal(n).astype(np.float32)
    zeros = np.zeros(n, dtype=np.float32)
    out = ppo_train(net, opt, packed, acts, lp, zeros, adv, adv, a, torch.device("cpu"))
    assert out["kl_stop"] and 1 <= len(steps) < out["minibatches"]


def test_rows_from_the_previous_weights_do_not_stop_an_update_that_has_not_moved(table) -> None:
    """Rows played while the previous update ran (~40% of a batch) carry its movement, so the KL
    stop is measured from the policy at the start of this update: data one update away (k3 KL
    ~0.05) must not stop an update before its first step. The clipped ratio still uses the
    behaviour log-probs."""
    from types import SimpleNamespace

    from tools.selfplay.ppo import ppo_train
    net, packed, acts, lp, n = _ppo_case(table)
    shift = np.where(np.arange(n) % 2 == 0, 0.33, -0.33).astype(np.float32)
    assert ((np.exp(shift) - 1) - shift).mean() > 1.5 * 0.03
    before = [p.detach().clone() for p in net.parameters()]
    opt = torch.optim.AdamW(net.parameters(), lr=1e-4)
    a = SimpleNamespace(epochs=1, mb=10**6, tok_budget=10**9, clip=0.2, vclip=0.5, vcoef=0.5,
                        ent=0.002, max_grad=1.0, target_kl=0.03)
    adv = np.random.default_rng(0).standard_normal(n).astype(np.float32)
    zeros = np.zeros(n, dtype=np.float32)
    out = ppo_train(net, opt, packed, acts, lp - shift, zeros, adv, adv, a, torch.device("cpu"))
    assert not out["kl_stop"]
    assert any(not torch.equal(b, p) for b, p in zip(before, net.parameters(), strict=True))


def test_ppo_without_a_kl_stop_reads_each_minibatch_once(table) -> None:
    """--target-kl 0 turns the stop off, so the update skips the no-grad pass only the stop reads
    (a quarter of an update's time): one forward pass per minibatch, and every step is taken."""
    from types import SimpleNamespace

    from tools.selfplay.ppo import ppo_train
    net, packed, acts, lp, n = _ppo_case(table)
    opt = torch.optim.AdamW(net.parameters(), lr=0.05)
    passes = []
    net.register_forward_hook(lambda *_: passes.append(1))
    a = SimpleNamespace(epochs=1, mb=16, tok_budget=10**9, clip=0.2, vclip=0.2, vcoef=0.5,
                        ent=0.0, max_grad=1.0, target_kl=0.0)
    adv = np.random.default_rng(0).standard_normal(n).astype(np.float32)
    zeros = np.zeros(n, dtype=np.float32)
    out = ppo_train(net, opt, packed, acts, lp, zeros, adv, adv, a, torch.device("cpu"))
    assert not out["kl_stop"] and "kl_update" not in out
    assert len(passes) == out["minibatches"] > 1
    # DESIGN_PRIORITY §3.5: every ask kind of the batch reported on its own
    kinds = out["kinds"]
    assert sum(k["n"] for k in kinds.values()) == n
    prio = packed.ask_i[:, 0] == FT.ASK_INDEX["priority"]
    chosen = packed.opts_i[packed.o_off[:-1] + acts, 0]
    passed = (chosen[prio] == FT.OPT_INDEX["PASS"]).mean()
    assert {"act", "priority"} <= set(kinds) and kinds["priority"]["pass"] == round(float(passed), 4)
    assert all(k["ent"] is None or 0.0 <= k["ent"] <= 1.0 + 1e-3 for k in kinds.values())


def test_heuristic_casts_a_raid_creature_after_it_attacks() -> None:
    """A spell that reads whether its controller attacked this turn (raid) waits for the second
    main phase while the teacher has a creature that can attack. Goblin Boarders ("enters with a
    +1/+1 counter on it if you attacked this turn") then enters with the counter; with no attacker
    it is cast in the first main phase."""
    for field, held in ((("Mountain",) * 3 + ("Bear Cub",), True), (("Mountain",) * 3, False)):
        game, router, me = _teach(hand0=("Goblin Boarders",), field0=field, set_code="FDN")
        boarders = _named(game, "Goblin Boarders")
        _main_phase(router, game, me)
        assert game.world.zone_of(boarders).kind == ("hand" if held else "battlefield")
        game.executor.combat_step(me)
        _main_phase(router, game, me)
        assert game.world.zone_of(boarders).kind == "battlefield"
        assert game.world.cards[boarders].counters.get("PLUS_1_PLUS_1", 0) == int(held)


class _CombatPlanLog(HeuristicAgent):
    """The heuristic, logging where the rig asks it to plan combat (search.py's hook)."""

    def __init__(self) -> None:
        self.plans: list[tuple[int, str | None]] = []

    def plan_combat(self, game, seat: int) -> None:
        self.plans.append((game.world.turn, game.executor.phase))


def test_combat_is_planned_once_per_turn_before_combat() -> None:
    """The search plans its attack at the pre-attacks boundary, before the declare-attackers
    step's declaration, once per turn."""
    agent = _CombatPlanLog()
    res = play_game(41, [agent, HeuristicAgent()], deck_mode="coherent")
    assert res["crash"] is None and agent.plans
    assert {phase for _, phase in agent.plans} == {"DECLARE_ATTACKERS"}
    turns = [turn for turn, _ in agent.plans]
    assert len(turns) == len(set(turns))



# ------------------------------------------------------------------- the mulligan (CR 103.5)


class _ProbeSlot:
    """The actor's slot over a LocalSlot: keeps every request's encoding, and answers the first
    mulligan declaration with "mulligan" when ``force`` (so a bottom ask follows)."""

    def __init__(self, net, force: bool = True) -> None:
        self.inner = M.LocalSlot({"net": net.eval()})
        self.feats: list[dict] = []
        self.force = force

    def infer(self, req):
        feats = req[5]
        self.feats.append(feats)
        answer = self.inner.infer(req)
        if self.force and int(feats["ask_i"][0]) == FT.ASK_INDEX["mulligan"]:
            self.force = False
            return int(np.flatnonzero(feats["opts_i"][:, 0] == FT.OPT_INDEX["mulligan"])[0])
        return answer

    def of(self, kind: str) -> list[dict]:
        return [f for f in self.feats if int(f["ask_i"][0]) == FT.ASK_INDEX[kind]]


class _HeuristicLog(HeuristicAgent):
    def __init__(self, table) -> None:
        self.table = table
        self.kinds: list[str] = []
        self.plays_first: list[float] = []

    def decide(self, ask, obs) -> int:
        self.kinds.append(ask.kind)
        if ask.kind == "mulligan":
            feats = FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx)
            self.plays_first.append(float(feats["glob_f"][1]))
        return super().decide(ask, obs)


def _net_vs_heuristic(net, table, slot_force: bool = True):
    """Seat 0 a network (NetAgent through a probe slot), seat 1 the heuristic with a deck of no
    lands, one turn: the heuristic mulligans its seven and its six and keeps five."""
    from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
    from MTG_bot.core.executor.games import _play, _setup_game, deal_decks
    from tools.selfplay.actor import NetAgent
    from tools.selfplay.rig import SelfplayRouter

    supply = get_supply("castable")
    corpse = next(o for o, m in supply.metas.items() if m.name == "Walking Corpse")
    game = _setup_game(9, supply, (deal_decks(9, 1409, supply)[0], (corpse,) * 60))
    slot = _ProbeSlot(net, slot_force)
    job = {"gid": 0, "seats": ["net", "heuristic"], "greedy": [True, True], "record": [False, False]}
    heuristic = _HeuristicLog(table)
    oracle = OracleIndex.for_sets("M21")
    router = SelfplayRouter(game, [NetAgent(slot, job, 0, table), heuristic],
                            [SeatLens(s, oracle, ViewOptions()) for s in (0, 1)], supply=supply)
    _play(game, router, game.world.player_order, turn_cap=1)
    return game, slot, heuristic


def test_the_network_and_the_heuristic_both_answer_the_mulligan(table) -> None:
    torch.manual_seed(0)
    game, slot, heuristic = _net_vs_heuristic(M.build(table, d=32, layers=1, heads=4, ff=64), table)
    declaration = slot.of("mulligan")[0]
    assert list(declaration["opts_i"][:, 0]) == [FT.OPT_INDEX["keep"], FT.OPT_INDEX["mulligan"]]
    assert float(declaration["glob_f"][1]) == 1.0  # it plays first: no turn has begun yet
    bottom = slot.of("mulligan_bottom")[0]
    assert len(bottom["opts_i"]) == 7 and set(bottom["opts_i"][:, 0]) == {FT.OPT_INDEX["card"]}
    pointed = bottom["opts_i"][:, 1].astype(int) - 3  # refs: 0 none, 1 me, 2 opponent, 3+ cards
    assert set(bottom["cards_i"][pointed, 1]) == {FT.ZONE_INDEX[ZONE_HAND]}
    assert np.isclose(float(bottom["glob_f"][4]), 1 / 3, atol=1e-3)  # one card to put there
    assert [k for k in heuristic.kinds if k.startswith("mulligan")] == [
        "mulligan", "mulligan_bottom", "mulligan", "mulligan_bottom", "mulligan_bottom", "mulligan"]
    assert heuristic.plays_first == [0.0, 0.0, 0.0]
    hands = [len(game.world.players[p].zone(ZONE_HAND).entries) for p in game.world.player_order]
    assert hands[1] == 5


def test_an_old_checkpoint_loads_and_plays_the_mulligan(table, tmp_path) -> None:
    """A checkpoint from before the mulligan has neither its ask kinds nor its option types; they
    grow from "other", what they were encoded as before (the priority kind, newer still, from
    "cw": features.ASK_GROWN_FROM). Played greedily it keeps: its keep and mulligan rows start
    equal, and the tie goes to the first option."""
    net = M.build(table, d=32, layers=1, heads=4, ff=64)
    for p in net.parameters():
        p.data.normal_(0, 0.1)
    path = tmp_path / "old.pt"
    M.save(str(path), net, table)
    ck = torch.load(path, weights_only=False)
    cut = {"ask_emb.weight": FT.ASK_INDEX["mulligan"], "opt_type.weight": FT.OPT_INDEX["keep"]}
    for key, n_old in cut.items():
        ck["state"][key] = ck["state"][key][:n_old].clone()
    torch.save(ck, path)
    old, _, _ = M.load(str(path))
    for key, names, index, grown_from in (("ask_emb.weight", FT.ASK_KINDS, FT.ASK_INDEX, FT.ASK_GROWN_FROM),
                                          ("opt_type.weight", FT.OPTION_TYPES, FT.OPT_INDEX, {})):
        w, n_old = old.state_dict()[key], cut[key]
        assert w.shape[0] == len(names) and torch.equal(w[:n_old], net.state_dict()[key][:n_old])
        assert all(torch.equal(w[index[k]], w[index[grown_from.get(k, "other")]]) for k in names[n_old:])
    game, slot, _ = _net_vs_heuristic(old, table, slot_force=False)
    assert game.world.turn == 1 and game.turns == 1
    declarations = slot.of("mulligan")
    assert len(declarations) == 1  # kept its seven
    _, _, probs = slot.inner.infer((0, 0, "net", True, False, declarations[0], 2))
    assert abs(probs[0] - probs[1]) < 1e-5


def test_heuristic_mulligan_rule() -> None:
    """Keep five cards or fewer, or a bigger hand with two lands and two other cards; bottom a land
    while lands outnumber the rest (a copy of the land it holds most of), else the priciest card."""
    from MTG_bot.bench.agents import Observation
    from MTG_bot.bench.protocol import Ask, Option
    from MTG_bot.bench.test_router import P0, _arranged, _lenses

    def decide(hand: tuple[str, ...], kind: str) -> str:
        game, _ = _arranged(hand0=hand)
        cards = sorted(game.world.players[P0].zone(ZONE_HAND).entries)
        words = ("keep", "mulligan") if kind == "mulligan" else tuple(str(c) for c in cards)
        ask = Ask(seat=0, kind=kind, site=f"{kind}:{P0}:1", prompt="",
                  options=tuple(Option(w, w) for w in words), refuse=0 if kind == "mulligan" else None)
        token = words[HeuristicAgent().decide(ask, Observation(_lenses()[0], game.executor))]
        return token if kind == "mulligan" else _name_of(game, token)

    others = ("Walking Corpse", "Pursued Whale", "Fierce Empath", "Onakke Ogre", "Grasp of Darkness")
    assert decide(("Swamp", "Island", *others), "mulligan") == "keep"
    assert decide(("Swamp", "Walking Corpse", *others), "mulligan") == "mulligan"  # one land
    assert decide(("Swamp",) * 5 + ("Island", "Walking Corpse"), "mulligan") == "mulligan"  # one spell
    assert decide(("Swamp", *others[:4]), "mulligan") == "keep"  # five cards
    assert decide(("Swamp", "Swamp", "Swamp", "Island", "Island", *others[:2]), "mulligan_bottom") == "Swamp"
    assert decide(("Swamp", "Island", *others), "mulligan_bottom") == "Pursued Whale"


def _name_of(game, token: str) -> str:
    return next(c.identity.name for h, c in game.world.cards.items() if str(h) == token)


# ------------------------------------------------------- several target slots (CR 601.2c)


def test_heuristic_judges_each_target_slot_by_its_own_effect() -> None:
    """Rabid Bite ("Target creature you control deals damage equal to its power to target creature
    you don't control") harms only its second target, so the teacher's best creature deals the
    damage to the opponent's best; read as a whole harmful card, its own worst creature would
    deal it. Primal Might pumps the first target and fights the second."""
    game, router, me = _teach(hand0=("Rabid Bite",), field0=("Forest", "Forest", "Centaur Courser", "Coral Merfolk"),
                              field1=("Barony Vampire", "Goblin Assailant"), set_code="M20")
    _main_phase(router, game, me)
    assert [a.detail for a in router.acts if a.card == "Rabid Bite"] == ["2t"]
    assert game.world.zone_of(_named(game, "Barony Vampire")).kind == "graveyard"  # 3 from the Courser
    assert game.world.zone_of(_named(game, "Goblin Assailant")).kind == "battlefield"
    game, router, me = _teach(hand0=("Primal Might",),
                              field0=("Forest",) * 4 + ("Walking Corpse", "Staunch Shieldmate"),
                              field1=("Onakke Ogre", "Staunch Shieldmate"))
    _main_phase(router, game, me)
    corpse = _named(game, "Walking Corpse")
    assert [a.detail for a in router.acts if a.card == "Primal Might"] == ["2t:x3"]
    assert game.world.zone_of(_named(game, "Onakke Ogre")).kind == "graveyard"
    assert game.executor.damage == {corpse: 4}


class _CastSlot:
    """The actor's slot over a LocalSlot: answers each act ask with its last cast row (the largest
    X) and keeps every request's encoding and answer."""

    def __init__(self, net) -> None:
        self.inner = M.LocalSlot({"net": net.eval()})
        self.feats: list[dict] = []
        self.answers: list[int] = []

    def infer(self, req):
        feats = req[5]
        casts = np.flatnonzero(feats["opts_i"][:, 0] == FT.OPT_INDEX["cast"])
        if int(feats["ask_i"][0]) == FT.ASK_INDEX["act"] and len(casts):
            answer = int(casts[-1])
        else:
            answer = self.inner.infer(req)
        self.feats.append(feats)
        self.answers.append(answer)
        return answer

    def targets(self) -> list[tuple[dict, int]]:
        return [(f, a) for f, a in zip(self.feats, self.answers, strict=True)
                if int(f["ask_i"][0]) == FT.ASK_INDEX["target"]]


def _net_casts_primal_might(net, table):
    """Seat 0 a network (NetAgent through _CastSlot) with Primal Might, four Forests, Walking Corpse
    and Staunch Shieldmate; seat 1 Onakke Ogre and Wishcoin Crab. Its main phase."""
    from MTG_bot.bench.test_router import P0, _arranged
    from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
    from tools.selfplay.actor import NetAgent
    from tools.selfplay.rig import SelfplayRouter

    game, supply = _arranged(hand0=("Primal Might",), field0=("Forest",) * 4 + ("Walking Corpse", "Staunch Shieldmate"),
                             field1=("Onakke Ogre", "Wishcoin Crab"))
    slot = _CastSlot(net)
    job = {"gid": 0, "seats": ["net", "heuristic"], "greedy": [True, True], "record": [False, False]}
    oracle = OracleIndex.for_sets("M21")
    router = SelfplayRouter(game, [NetAgent(slot, job, 0, table), HeuristicAgent()],
                            [SeatLens(s, oracle, ViewOptions()) for s in (0, 1)], supply=supply)
    game.executor.decisions.provider = router.answer
    _main_phase(router, game, P0)
    return game, slot


def test_the_network_answers_one_target_ask_per_slot_and_sees_which(table) -> None:
    """The second target ask says it is the second slot (glob_f[G_SLOT]) and marks the creature the
    first one chose (F_TARGETED), as attacks mark the attackers declared so far."""
    torch.manual_seed(0)
    game, slot = _net_casts_primal_might(M.build(table, d=32, layers=1, heads=4, ff=64), table)
    (first, picked), (second, _) = slot.targets()
    assert float(first["glob_f"][FT.G_SLOT]) == 0.0 and not first["cards_f"][:, FT.F_TARGETED].any()
    assert np.isclose(float(second["glob_f"][FT.G_SLOT]), 1 / 3, atol=1e-3)
    flagged = np.flatnonzero(second["cards_f"][:, FT.F_TARGETED])
    pointed = int(first["opts_i"][picked, 1]) - 3  # refs: 0 none, 1 me, 2 opponent, 3+ cards
    assert list(flagged) == [pointed] and int(second["cards_i"][pointed, 2]) == 1  # mine
    assert set(second["opts_i"][:, 0]) == {FT.OPT_INDEX["card"], FT.OPT_INDEX["DONE"]}  # "up to one"
    assert game.world.zone_of(_named(game, "Primal Might")).kind == "graveyard"


def test_an_old_checkpoint_loads_and_plays_two_target_spells(table, tmp_path) -> None:
    """A checkpoint from before the slot features has narrower card, player and global inputs. The
    new columns load with zero weights, so it computes what it computed before, and it plays the
    second target ask."""
    net = M.build(table, d=32, layers=1, heads=4, ff=64)
    for p in net.parameters():
        p.data.normal_(0, 0.1)
    path = tmp_path / "old.pt"
    M.save(str(path), net, table)
    ck = torch.load(path, weights_only=False)
    cut = {"card_f.weight": FT.F_TARGETED, "player_f.weight": FT.P_TARGETED, "glob_f.weight": FT.G_SLOT}
    for key, width in cut.items():
        ck["state"][key] = ck["state"][key][:, :width].clone()
    torch.save(ck, path)
    old, _, _ = M.load(str(path))
    for key, width in cut.items():
        w = old.state_dict()[key]
        assert torch.equal(w[:, :width], net.state_dict()[key][:, :width]) and not w[:, width:].any()
    game, slot = _net_casts_primal_might(old, table)
    assert len(slot.targets()) == 2 and game.world.zone_of(_named(game, "Primal Might")).kind == "graveyard"
    second = slot.targets()[1][0]
    blank = {k: v.copy() for k, v in second.items()}
    blank["cards_f"][:, FT.F_TARGETED] = 0
    blank["players_f"][:, FT.P_TARGETED] = 0
    blank["glob_f"][FT.G_SLOT] = 0
    probs = [slot.inner.infer((0, 0, "net", True, False, f, 2))[2] for f in (second, blank)]
    assert probs[0] == probs[1]


def test_the_search_plays_a_two_target_candidate(table, monkeypatch) -> None:
    """Decision-time search forks the game and plays a two-target cast in the copy: the network
    answers both target asks there, and the simulation does not crash."""
    from MTG_bot.bench.test_router import _arranged
    from tools.selfplay import rig
    from tools.selfplay.search import Searcher

    game, _supply = _arranged(hand0=("Primal Might",), field0=("Forest",) * 4 + ("Walking Corpse",),
                              field1=("Onakke Ogre",))
    pm = _named(game, "Primal Might")
    played: list[str] = []
    execute = rig.SelfplayRouter._execute

    def record(self, g, seat, i, option, payload):
        played.append(option.token)
        return execute(self, g, seat, i, option, payload)

    monkeypatch.setattr(rig.SelfplayRouter, "_execute", record)
    torch.manual_seed(0)
    net = M.build(table, d=32, layers=1, heads=4, ff=64).eval()
    searcher = Searcher(M.LocalSlot({"learner": net}), 0, "learner", table, pool_mode="castable",
                        set_code="M21", k=2, d=1, seed=0)
    score = searcher.simulate(game, 0, f"cast:{pm}:x3")
    assert played[0] == f"cast:{pm}:x3" and searcher.stats["sim_errors"] == 0
    assert score is not None and -1.0 <= score <= 1.0
    assert game.world.zone_of(pm).kind == "hand"  # the real game is untouched


def test_gumbel_halving_spends_its_budget_on_shared_worlds(table) -> None:
    """root="gumbel" (PLAN_CEILING §3.2): at most n simulations; every candidate of a round is
    played in the same worlds; the better half survives each round; and a clearly better mean
    beats a prior that prefers another candidate."""
    from tools.selfplay.search import Searcher

    s = Searcher(None, 0, "learner", table, pool_mode="castable", set_code="M21",
                 root="gumbel", n=32, m=8, seed=0)
    seen: dict[int, list] = {}

    def run(c, world):
        seen.setdefault(c, []).append(world)
        return c / 10  # candidate 7 is best

    logits = [2.0] + [0.0] * 7  # the network prefers candidate 0
    pick, q = s.compare(list(range(8)), logits, run)
    assert pick == 7 and q[7] == pytest.approx(0.7)
    assert sum(len(w) for w in seen.values()) <= 32
    assert seen[6] == seen[7]  # the last two met every world together
    assert set(seen[0]) < set(seen[7])  # an early loser met only the first round's worlds


def test_a_world_where_one_candidate_crashed_counts_for_none(table) -> None:
    """Common random numbers under sequential halving: a world in which any candidate's
    simulation crashed is left out for every candidate of that round."""
    from tools.selfplay.search import Searcher

    s = Searcher(None, 0, "learner", table, pool_mode="castable", set_code="M21",
                 root="gumbel", n=24, m=2, seed=0)
    first: list = []

    def run(c, world):
        first.append(world) if not first else None
        if world == first[0]:  # candidate 0 wins big in the world where candidate 1 crashes
            return 1.0 if c == 0 else None
        return 0.0 if c == 0 else 0.05

    pick, q = s.compare([0, 1], [0.0, 0.0], run)
    assert q == {0: 0.0, 1: pytest.approx(0.05)} and pick == 1


def test_the_horizon_stops_at_the_searchers_nth_next_turn() -> None:
    from types import SimpleNamespace as NS

    from tools.selfplay.search import horizon_stop

    def at(active, turn):
        return NS(world=NS(active_player=active, turn=turn))

    assert horizon_stop("p0", 5, 0) is None  # to the end of the game
    stop = horizon_stop("p0", 5, 2)
    assert not stop(at("p1", 6), "turn_top")  # the opponent's turn
    assert not stop(at("p0", 7), "priority")  # not a turn top
    assert not stop(at("p0", 7), "turn_top")  # the searcher's first next turn
    assert not stop(at("p1", 8), "turn_top")
    assert stop(at("p0", 9), "turn_top")  # its second


class _PrioritySearcher:
    """The searching seat of a game: its first ``limit`` decisions of a searched kind go to the
    Searcher, everything else to the heuristic (a short test)."""

    def __init__(self, searcher, table, limit: int = 3) -> None:
        self.searcher = searcher
        self.table = table
        self.limit = limit
        self.inner = HeuristicAgent()
        self.name = "priority-searcher"

    def decide(self, ask, obs) -> int:
        if (len(ask.options) > 1 and ask.kind in self.searcher.kinds
                and self.searcher.stats["searched"] < self.limit):
            feats = FT.encode(obs.executor, ask.seat, ask, self.table, obs.ctx)
            return self.searcher.choose(ask, obs, feats)
        return self.inner.decide(ask, obs)


def test_the_search_answers_instant_speed_decisions(table) -> None:
    """kinds=("priority",): at the searcher's instant-speed decisions each copy resumes at the same
    priority point and plays the candidate there (SimAgent.forced answers the priority ask); no
    simulation crashes, and the game ends normally."""
    from tools.selfplay.search import Searcher, ms_percentiles

    torch.manual_seed(0)
    net = M.build(table, d=32, layers=1, heads=4, ff=64).eval()
    searcher = Searcher(M.LocalSlot({"learner": net}), 0, "learner", table, pool_mode="castable",
                        set_code="M21", root="gumbel", n=2, m=2, skip_p=1.01,
                        kinds=("priority",), seed=41, record=True)
    res = play_game(41, [_PrioritySearcher(searcher, table, limit=2), HeuristicAgent()],
                    deck_mode="coherent")
    assert res["crash"] is None and searcher.stats["sim_errors"] == 0
    assert searcher.stats["searched:priority"] == 2
    assert ms_percentiles(searcher.stats)["n"] == 2
    # record=True keeps each searched decision as a training target: its encoding, the
    # network's probabilities, and per compared option its mean, worlds and variance
    assert len(searcher.targets) == 2
    for t in searcher.targets:
        assert t["kind"] == "priority" and set(t["feats"]) >= {"cards_i", "cards_f"}
        assert sum(t["n"]) <= 2 and all(-1.0 <= q <= 1.0 for q in t["q"])
        assert len(t["probs"]) > max(t["alts"]) and t["pick"] in range(len(t["probs"]))


def test_a_sampled_continuation_shares_its_draws_within_a_world(table) -> None:
    """continuation="sampled": the world seeds the hidden cards and each seat's draws, so a
    candidate played twice in one world scores the same, as every candidate of a world does."""
    from MTG_bot.core.executor.games import TURN_CAP, RandomPolicy, _play, get_supply
    from tools.selfplay import rig
    from tools.selfplay.search import Searcher

    supply = get_supply("castable")
    game = rig._setup_game(7, supply, rig.deal_decks(7, 1409, supply, "coherent"))
    _play(game, RandomPolicy(0), game.world.player_order, TURN_CAP,
          stop_after=lambda _g, boundary: boundary == "priority")
    torch.manual_seed(0)
    net = M.build(table, d=32, layers=1, heads=4, ff=64).eval()
    searcher = Searcher(M.LocalSlot({"learner": net}), 0, "learner", table, pool_mode="castable",
                        set_code="M21", continuation="sampled", seed=0)
    scores = [searcher.simulate(game, 0, "PASS", world=w) for w in (5, 5, 6)]
    assert scores[0] == scores[1] is not None and searcher.stats["sim_errors"] == 0


def test_the_n_curve_reads_paired_points_and_fits_log_n(tmp_path) -> None:
    """tools/selfplay/ncurve.py: each run is one point (a deal is the mean of its two
    seat-swapped games); the points differing only in n are fitted against log2 n."""
    import json
    from pathlib import Path

    from tools.selfplay import ncurve

    def run(name: str, n: int, wins: list[int]) -> Path:
        d = tmp_path / name
        d.mkdir()
        args = {"search_n": n, "search_root": "gumbel", "init": "c.pt"}
        (d / "manifest.json").write_text(json.dumps([{"args": args}]))
        (d / "metrics.jsonl").write_text(json.dumps({"event": "eval", "search": {
            "searched": 40, "changed": 10, "clear": 4}, "search_ms": {"p50": 12.6}}) + "\n")
        rows = [{"seed": i // 2, "deck_mode": "coherent", "a_seat": i % 2, "outcome": "win",
                 "winner": i % 2 if w else 1 - i % 2} for i, w in enumerate(wins)]
        (d / "eval_rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        return d

    a = ncurve.point(run("a", 4, [1, 0, 1, 1, 0, 0, 1, 0]))
    b = ncurve.point(run("b", 16, [1, 1, 1, 1, 0, 1, 1, 0]))
    assert (a["score"], b["score"]) == (0.5, 0.75) and a["deals"] == 4
    assert a["searched_per_game"] == 5.0 and a["changed"] == 0.25 and a["clear_per_game"] == 0.5
    slope, se, _ = ncurve.fit([a, b])
    assert slope == pytest.approx(0.125) and se > 0  # +0.25 over two doublings


def test_simulator_worlds_keep_the_rules_and_the_sizes(table) -> None:
    """worlds="sim" (PLAN_CEILING §3.2): the simulator draws the opponent's hand and library from
    the searching seat's own view; every draw has the view's sizes, only cards of the dealt pool,
    and no more copies of a card than the rules allow next to its public copies; a search plays
    in those worlds without a simulation error."""
    from MTG_bot.bench.protocol import Ask, Option
    from MTG_bot.core.executor.games import (
        MAX_COPIES,
        TURN_CAP,
        RandomPolicy,
        _play,
        get_supply,
    )
    from tools.selfplay import rig
    from tools.selfplay import simulator as S
    from tools.selfplay.search import Searcher

    supply = get_supply("castable")
    game = rig._setup_game(7, supply, rig.deal_decks(7, 1409, supply, "coherent"))
    _play(game, RandomPolicy(0), game.world.player_order, TURN_CAP,
          stop_after=lambda g, boundary: boundary == "turn_top" and g.world.turn >= 5)
    torch.manual_seed(0)
    sim = S.Simulator(table, d=32, layers=1, heads=4, ff=64).eval()
    me = game.world.player_order[0]
    ask = Ask(seat=0, kind="act", site=f"act:{me}:{game.world.turn}", prompt="",
              options=(Option("PASS", "PASS"),), refuse=0)
    view = FT.sim_view(game.executor, 0, ask, table, FT.AskContext())
    worlds = S.sample_for_views(sim, table, [view], ["M21"], [16], "cpu")[0]
    pool = set(supply.deckable)
    public = Counter(table.oracle_ids[r] for r in view["public"])
    assert len(worlds) == 16
    for hand, lib in worlds:
        assert (len(hand), len(lib)) == (view["h"], view["l"]) and set(hand + lib) <= pool
        for oid, n in Counter(hand + lib).items():
            if not supply.metas[oid].is_basic:
                assert n + public[oid] <= MAX_COPIES
    net = M.build(table, d=32, layers=1, heads=4, ff=64).eval()
    searcher = Searcher(M.LocalSlot({"learner": net}, sim=(sim, table)), 0, "learner", table,
                        pool_mode="castable", set_code="M21", worlds="sim", seed=0)
    searcher.root_pos = (game, 0, ask, FT.AskContext())
    (world, weight), = searcher.draw_worlds(1)
    assert weight == 1.0 and len(world[1]) == view["h"]
    assert searcher.simulate(game, 0, "PASS", world=world) is not None
    assert searcher.stats["sim_errors"] == 0


def test_the_audit_measures_true_worlds_beside_the_search(table, monkeypatch) -> None:
    """--search-audit (192 §7.1): a true world plays the opponent's real hidden cards (a uniform
    one re-draws them); the audit records each kind's means, counts its simulations apart, and
    leaves the search's own random stream untouched."""
    from MTG_bot.bench.protocol import Ask, Option
    from MTG_bot.core.executor.games import TURN_CAP, RandomPolicy, _play, get_supply
    from MTG_bot.core.state import ZONE_HAND
    from tools.selfplay import rig, search
    from tools.selfplay import simulator as S

    supply = get_supply("castable")
    game = rig._setup_game(7, supply, rig.deal_decks(7, 1409, supply, "coherent"))
    _play(game, RandomPolicy(0), game.world.player_order, TURN_CAP,
          stop_after=lambda g, boundary: boundary == "turn_top" and g.world.turn >= 5)
    opp = game.world.player_order[1]

    def hand(g):
        return sorted(g.world.cards[h].identity.oracle_id
                      for h in g.world.players[opp].zone(ZONE_HAND).entries)

    real, seen = hand(game), []
    play_out = search.play_out
    monkeypatch.setattr(search, "play_out", lambda clone, *a: seen.append(hand(clone))
                        or play_out(clone, *a))
    torch.manual_seed(0)
    sim = S.Simulator(table, d=32, layers=1, heads=4, ff=64).eval()
    net = M.build(table, d=32, layers=1, heads=4, ff=64).eval()
    s = search.Searcher(M.LocalSlot({"learner": net}, sim=(sim, table)), 0, "learner", table,
                        pool_mode="castable", set_code="M21", seed=0, audit=2)
    me = game.world.player_order[0]
    ask = Ask(seat=0, kind="act", site=f"act:{me}:{game.world.turn}", prompt="",
              options=(Option("PASS", "PASS"),), refuse=0)
    s.root_pos = (game, 0, ask, FT.AskContext())
    state = s.rng.getstate()
    s._audit(game, ask, [0], [1.0], 0, 0)
    assert s.rng.getstate() == state and s.stats["sims"] == 0 and s.stats["audit_sims"] == 8
    (rec,) = s.audits
    assert set(rec["q"]) == {"uniform", "sim", "true", "true2"}
    assert all(len(v) == 1 for v in rec["q"].values())
    assert len(real) > 0 and seen[4:] == [real] * 4  # both sets of true worlds, played last
    assert seen[0] != real and s.stats["sim_errors"] == 0


def test_distilling_search_targets_moves_the_network_toward_the_better_move(table) -> None:
    """tools/selfplay/distill.py (PLAN_CEILING §6.2): the "se" rule leaves the policy unchanged
    when every compared option had the same result and moves it toward the better one otherwise;
    "sigma" is a distribution favouring the better one; training on such records raises the
    better option's probability."""
    from MTG_bot.bench.protocol import Ask, Option
    from MTG_bot.core.executor.games import TURN_CAP, RandomPolicy, _play, get_supply
    from tools.selfplay import distill as D
    from tools.selfplay import rig

    pi = np.array([0.6, 0.3, 0.1])
    tie = {"alts": [0, 1], "q": [1.0, 1.0], "n": [4, 4], "var": [0.0, 0.0], "v": 0.0}
    clear = {**tie, "q": [-1.0, 1.0]}
    assert np.allclose(D.improved(tie, pi, "se"), pi)
    se = D.improved(clear, pi, "se")
    assert se[1] > pi[1] and se[0] < pi[0] and se[2] == pytest.approx(pi[2])
    sg = D.improved(clear, pi, "sigma")
    assert sg.sum() == pytest.approx(1.0) and sg.argmax() == 1

    supply = get_supply("castable")
    game = rig._setup_game(7, supply, rig.deal_decks(7, 1409, supply, "coherent"))
    _play(game, RandomPolicy(0), game.world.player_order, TURN_CAP,
          stop_after=lambda g, boundary: boundary == "turn_top" and g.world.turn >= 3)
    me = game.world.player_order[0]
    ask = Ask(seat=0, kind="act", site=f"act:{me}:3", prompt="",
              options=(Option("PASS", "PASS"), Option("x", "x")), refuse=0)
    feats = FT.encode(game.executor, 0, ask, table, FT.AskContext())
    recs = [{"feats": feats, **clear, "pick": 1, "seed": g} for g in range(40)]
    torch.manual_seed(0)
    net = M.build(table, d=32, layers=1, heads=4, ff=64)
    before = D.policy(net.eval(), [feats], torch.device("cpu"))[0][1]
    seen: list[tuple[int, int, float]] = []
    (trained, rep), = D.distil(net, recs, "se", [40], torch.device("cpu"), lr=1e-3, epochs=3,
                               on_epoch=lambda n, e, m: seen.append(
                                   (n, e, D.policy(m, [feats], torch.device("cpu"))[0][1]))
                               ).values()
    after = D.policy(trained, [feats], torch.device("cpu"))[0][1]
    assert after > before and rep["val"] == 2 and rep["held_out_agreement"] == 1.0
    # every trained epoch is shown, as it was then (E3 kept epoch 0 and hid them, 186 §5)
    assert [(n, e) for n, e, _ in seen] == [(40, 1), (40, 2), (40, 3)]
    assert after in [p for _, _, p in seen] and seen[0][2] > before


def test_a_player_is_rated_against_frozen_pool_ratings(tmp_path) -> None:
    """tools/selfplay/rate.py (PLAN_CEILING §7.2): the pool's ratings are fitted once from games
    among its members; a player is then rated against them held fixed. An even score against a
    member at 0 and one at 400 puts the player at 200."""
    import json
    from pathlib import Path

    from tools.selfplay import rate as R

    def run(name: str, init: str, opp: str, wins: list[float]) -> Path:
        d = tmp_path / name
        d.mkdir()
        args = {"init": init, "eval_opponents": "snap:opp", "opp_ckpt": opp}
        (d / "manifest.json").write_text(json.dumps([{"args": args}]))
        rows = [{"seed": i // 2, "a_seat": i % 2, "outcome": "win",
                 "winner": i % 2 if w else 1 - i % 2} for i, w in enumerate(wins)]
        (d / "eval_rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        return d

    ratings = R.fit([run("ab", "a.pt", "b.pt", [1, 1, 1, 0] * 25)])  # a scores 0.75 against b
    assert ratings["a.pt"] == 0.0 and -200 < ratings["b.pt"] < -180
    pool = {"a.pt": 0.0, "b.pt": 400.0}
    out = R.rate(pool, [run("pa", "p.pt", "a.pt", [1, 0] * 50),
                        run("pb", "p.pt", "b.pt", [1, 0] * 50)])
    assert out["player"] == "p.pt" and out["elo"] == pytest.approx(200, abs=0.5)
    assert out["ci95"][0] <= 200 <= out["ci95"][1] and out["deals"] == 100
