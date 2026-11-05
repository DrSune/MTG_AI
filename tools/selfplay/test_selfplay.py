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


def test_scry_context_never_reads_under_the_viewed_window() -> None:
    """Every scry ask's 'revealed' card is one of the top n cards of that scry (two scries of the
    same size in one act window used to point the second one under the window: a hidden card)."""
    from MTG_bot.bench.protocol import ask_kind
    from tools.selfplay.rig import SelfplayRouter

    checked, wrong = 0, []
    orig = SelfplayRouter._context

    def ctx(self, what, seat, i):
        nonlocal checked
        out = orig(self, what, seat, i)
        if ask_kind(what) == "scry":
            n = int(what.rsplit(":", 1)[-1])
            top = self.game.world.players[seat].zone("library").entries[-n:]
            if self._revealed not in top:  # recorded, not asserted: play_game voids raises
                wrong.append((self.game.world.turn, what, self._revealed))
            checked += 1
        return out

    SelfplayRouter._context = ctx
    try:
        # the three seeds of 3000-3599 where one window held two scries of the same size
        for seed in (3261, 3369, 3485):
            agents = [HeuristicAgent(), HeuristicAgent()]
            res = play_game(seed, agents, deck_mode="coherent" if seed % 3 else "stress")
            assert res["crash"] is None, res["crash"]
    finally:
        SelfplayRouter._context = orig
    assert checked >= 3 and not wrong, wrong


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


# ------------------------------------------- the teacher on the 2026-11-05 menu (no TAP_ALL_MANA)


def _teach(hand0=(), field0=(), field1=(), **kw):
    """Seat 0's turn on an arranged board (MTG_bot/bench/test_router.py), the heuristic acting."""
    from MTG_bot.bench.test_router import P0, _arranged, _router

    game, supply = _arranged(hand0=hand0, field0=field0, field1=field1, **kw)
    router = _router(game, supply, HeuristicAgent())
    return game, router, P0


def _named(game, name):
    return next(h for h, c in game.world.cards.items() if c.identity.name == name)


def test_heuristic_taps_a_mana_creature_only_for_a_spell_it_casts() -> None:
    game, router, me = _teach(hand0=("Fierce Empath",), field0=("Forest", "Forest", "Forest", "Llanowar Visionary"))
    router.take_acts(game, me)
    assert game.world.zone_of(_named(game, "Fierce Empath")).kind == "battlefield"
    assert not game.world.cards[_named(game, "Llanowar Visionary")].tapped  # the lands paid
    game, router, me = _teach(hand0=("Fierce Empath",), field0=("Forest", "Forest", "Llanowar Visionary"))
    router.take_acts(game, me)
    assert game.world.zone_of(_named(game, "Fierce Empath")).kind == "battlefield"
    assert game.world.cards[_named(game, "Llanowar Visionary")].tapped  # its {G} was the third mana


def test_heuristic_never_trades_two_mana_for_one() -> None:
    # Prismite's "{2}: Add one mana of any color" was activated 752 times in 300 games.
    game, router, me = _teach(hand0=("Pursued Whale",), field0=("Island", "Island", "Prismite"))
    router.take_acts(game, me)
    assert not any(a.card == "Prismite" for a in router.acts)


def test_heuristic_casts_an_x_spell_at_its_largest_x() -> None:
    game, router, me = _teach(hand0=("Volcanic Geyser",), field0=("Mountain", "Mountain", "Island", "Island", "Island"),
                              field1=("Walking Corpse",))
    router.take_acts(game, me)
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
    router.take_acts(game, me)
    assert not any(a.card == "Wildwood Scourge" for a in router.acts)


def test_heuristic_names_the_colour_its_treasure_is_for() -> None:
    # Review 2026-11-05: the mana ask took the colour from identity.mana_cost, which no dealt card
    # carries, so a Treasure sacrificed for Walking Corpse ({1}{B}) next to a Plains made {W}.
    game, router, me = _teach(hand0=("Walking Corpse",), field0=("Plains",), tokens0=("Treasure",))
    router.take_acts(game, me)
    assert game.world.zone_of(_named(game, "Walking Corpse")).kind == "battlefield"


def test_heuristic_never_taps_mana_for_a_play_it_will_not_make() -> None:
    # Wildwood Scourge with one {G} source is castable only at X = 0, which the teacher never casts.
    game, router, me = _teach(hand0=("Wildwood Scourge",), field0=("Llanowar Visionary",))
    router.take_acts(game, me)
    assert not game.world.cards[_named(game, "Llanowar Visionary")].tapped and router.acts == []


def test_heuristic_aims_minus_n_at_the_opponent() -> None:
    # "Target creature gets -4/-4" compiles to PtDelta(DECREASE, 4); the harm test read only
    # negative numbers, so Grasp of Darkness was aimed at the teacher's own creature.
    game, router, me = _teach(hand0=("Grasp of Darkness",), field0=("Swamp", "Swamp", "Walking Corpse"),
                              field1=("Onakke Ogre",))
    router.take_acts(game, me)
    assert game.world.zone_of(_named(game, "Onakke Ogre")).kind == "graveyard"
    assert game.world.zone_of(_named(game, "Walking Corpse")).kind == "battlefield"
