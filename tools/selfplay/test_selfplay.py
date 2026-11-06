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
    for feats, idx in samples:
        e = feats["cards_i"].shape[0]
        k = feats["opts_i"].shape[0]
        assert 2 <= k <= FT.MAX_OPTIONS and 0 <= idx < k
        assert feats["cards_f"].shape == (e, FT.CF)
        refs = feats["opts_i"][:, 1:3]
        assert refs.min() >= 0 and refs.max() <= e + 2  # [none, me, opp, cards...]
        assert feats["cards_i"][:, 4].max(initial=0) <= e + 2


def test_heuristic_beats_uniform_random() -> None:
    """The teacher works. It wins ~0.89 against uniform random, so 14 of 20 fails a working
    teacher with p = 0.005 and passes a coin-flip one with p = 0.06."""
    wins = 0
    for seed in range(1, 21):
        seat = seed % 2
        agents = [None, None]
        agents[seat] = HeuristicAgent()
        agents[1 - seat] = UniformRandomAgent(random.Random(seed))
        res = play_game(seed, agents, deck_mode="stress" if seed % 3 else "coherent")
        wins += res["outcome"] == "win" and res["winner"] == seat
    assert wins >= 14, wins


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


def test_pre_blocks_boundary_is_opt_in() -> None:
    """Only a policy with a before_blocks hook sees the pre_blocks boundary; every other
    caller's stop_after sees turn_top, pre_combat and post_combat, never pre_blocks."""
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
    # Prismite's "{2}: Add one mana of any color" is a mana-cost filter: it never adds mana.
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
    # The colour comes from the spell the mana is for: a Treasure sacrificed for Walking Corpse
    # ({1}{B}) next to a Plains makes {B}, so the Corpse is cast.
    game, router, me = _teach(hand0=("Walking Corpse",), field0=("Plains",), tokens0=("Treasure",))
    router.take_acts(game, me)
    assert game.world.zone_of(_named(game, "Walking Corpse")).kind == "battlefield"


def test_heuristic_never_taps_mana_for_a_play_it_will_not_make() -> None:
    # Wildwood Scourge with one {G} source is castable only at X = 0, which the teacher never casts.
    game, router, me = _teach(hand0=("Wildwood Scourge",), field0=("Llanowar Visionary",))
    router.take_acts(game, me)
    assert not game.world.cards[_named(game, "Llanowar Visionary")].tapped and router.acts == []


def test_heuristic_aims_minus_n_at_the_opponent() -> None:
    # "Target creature gets -4/-4" compiles to PtDelta(DECREASE, 4), which is harmful: Grasp of
    # Darkness is aimed at the opponent's creature, not the teacher's own.
    game, router, me = _teach(hand0=("Grasp of Darkness",), field0=("Swamp", "Swamp", "Walking Corpse"),
                              field1=("Onakke Ogre",))
    router.take_acts(game, me)
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
    that wins inside the search's own take_acts scores as a win, not as a crashed simulation."""
    from MTG_bot.core.executor.games import get_supply
    from tools.selfplay import rig
    from tools.selfplay.search import Searcher

    supply = get_supply("castable")
    game = rig._setup_game(7, supply, rig.deal_decks(7, 1409, supply, "coherent"))
    torch.manual_seed(0)
    net = M.build(table, d=32, layers=1, heads=4, ff=64).eval()
    searcher = Searcher(M.LocalSlot({"learner": net}), 0, "learner", table, pool_mode="castable",
                        set_code="M21", k=2, d=1, seed=0)

    def winning_act(self, g, seat) -> None:  # the act drains the opponent to 0: the check ends it
        opp = next(p for p in g.world.player_order if p != seat)
        g.world.players[opp].life = 0
        g.executor._player_losses()

    orig = rig.SelfplayRouter.take_acts
    rig.SelfplayRouter.take_acts = winning_act
    try:
        score = searcher.simulate(game, 0, "PASS")
    finally:
        rig.SelfplayRouter.take_acts = orig
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


def test_a_crashed_world_is_neutral_between_candidates() -> None:
    """A crashed simulation scores the search's mean belief, the same for every candidate:
    dropping it would score a move only on the worlds it survived."""
    from tools.selfplay.search import mean_scores
    got = mean_scores({"a": [1.0, None], "b": [0.0, 0.0]})
    assert abs(got["a"] - (1.0 + 1 / 3) / 2) < 1e-9 and got["b"] == 0.0
    assert mean_scores({"a": [None], "b": [None]}) == {"a": -1.0, "b": -1.0}


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


def test_heuristic_casts_a_raid_creature_after_it_attacks() -> None:
    """A spell that reads whether its controller attacked this turn (raid) waits for the second
    main phase while the teacher has a creature that can attack. Goblin Boarders ("enters with a
    +1/+1 counter on it if you attacked this turn") then enters with the counter; with no attacker
    it is cast in the first main phase."""
    for field, held in ((("Mountain",) * 3 + ("Bear Cub",), True), (("Mountain",) * 3, False)):
        game, router, me = _teach(hand0=("Goblin Boarders",), field0=field, set_code="FDN")
        boarders = _named(game, "Goblin Boarders")
        router.take_acts(game, me)
        assert game.world.zone_of(boarders).kind == ("hand" if held else "battlefield")
        game.executor.combat_step(me)
        router.take_acts(game, me)
        assert game.world.zone_of(boarders).kind == "battlefield"
        assert game.world.cards[boarders].counters.get("PLUS_1_PLUS_1", 0) == int(held)


class _CombatPlanLog(HeuristicAgent):
    """The heuristic, logging where the rig asks it to plan combat (search.py's hook)."""

    def __init__(self) -> None:
        self.plans: list[tuple[int, str | None]] = []

    def plan_combat(self, game, seat: int) -> None:
        self.plans.append((game.world.turn, game.executor.phase))


def test_combat_is_planned_once_per_turn_before_combat() -> None:
    """The search plans its attack at the pre-combat boundary, not at the end of an act window:
    the second main phase's comes after combat, and planning there would search an attack that
    cannot happen."""
    agent = _CombatPlanLog()
    res = play_game(41, [agent, HeuristicAgent()], deck_mode="coherent")
    assert res["crash"] is None and agent.plans
    assert {phase for _, phase in agent.plans} == {"FIRST_MAIN"}
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
    grow from "other", what they were encoded as before. Played greedily it keeps: its keep and
    mulligan rows start equal, and the tie goes to the first option."""
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
    for key, names, index in (("ask_emb.weight", FT.ASK_KINDS, FT.ASK_INDEX),
                              ("opt_type.weight", FT.OPTION_TYPES, FT.OPT_INDEX)):
        w, n_old = old.state_dict()[key], cut[key]
        assert w.shape[0] == len(names) and torch.equal(w[:n_old], net.state_dict()[key][:n_old])
        assert all(torch.equal(w[index[k]], w[index["other"]]) for k in names[n_old:])
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
    router.take_acts(game, me)
    assert [a.detail for a in router.acts if a.card == "Rabid Bite"] == ["2t"]
    assert game.world.zone_of(_named(game, "Barony Vampire")).kind == "graveyard"  # 3 from the Courser
    assert game.world.zone_of(_named(game, "Goblin Assailant")).kind == "battlefield"
    game, router, me = _teach(hand0=("Primal Might",),
                              field0=("Forest",) * 4 + ("Walking Corpse", "Staunch Shieldmate"),
                              field1=("Onakke Ogre", "Staunch Shieldmate"))
    router.take_acts(game, me)
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
    and Staunch Shieldmate; seat 1 Onakke Ogre and Wishcoin Crab. One act window."""
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
    router.take_acts(game, P0)
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
