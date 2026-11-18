"""The per-object planner, v1 (docs/DESIGN_PLANNER.md; planner.py): hindsight labels on scripted
games, the read-back, plan-following's inputs, the side losses, and that a network or a run
without it computes what it did."""

from __future__ import annotations

from itertools import pairwise
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from MTG_bot.bench.view import OracleIndex, SeatLens, ViewOptions
from MTG_bot.core.executor.games import TURN_CAP, _play, get_supply
from tools.puzzles import puzzle as P
from tools.selfplay import features as FT
from tools.selfplay import model as M
from tools.selfplay import planner as PL
from tools.selfplay.heuristic import HeuristicAgent
from tools.selfplay.ppo import pack_buffer, planner_terms, ppo_train
from tools.selfplay.rig import SelfplayRouter, play_game
from tools.selfplay.test_selfplay import _LearnerSlot, _small_learner


@pytest.fixture(scope="module")
def table() -> FT.CardTable:
    supply = get_supply("verified", "M21")
    return FT.CardTable.from_records({oid: r.card for oid, r in supply.pool.results.items()})


class _Scripted:
    """A seat answering by a script of option words with pack keys (tools/puzzles/puzzle.py), then
    with each ask's do-nothing option. With a tracker it is a planning seat as actor.NetAgent is
    one: ``begin``; at an ask of several options ``encode`` and ``forecast`` (``forecast(feats)``,
    blank by default); ``end``."""

    def __init__(self, script, handles, table, tracker=None, forecast=None) -> None:
        self.script, self.handles, self.table = list(script), handles, table
        self.tracker, self.forecast = tracker, forecast
        self.samples: list[tuple[dict, int]] = []  # each forecast decision's features and answer

    def decide(self, ask, obs) -> int:
        if self.tracker is not None:
            self.tracker.begin(obs.executor)
        tokens = [o.token for o in ask.options]
        if len(tokens) == 1:
            idx = 0
        elif self.script:
            word = P.resolve(self.script.pop(0), self.handles)
            assert word in tokens, (word, [P.keyed(t, self.handles) for t in tokens])
            idx = tokens.index(word)
        else:
            idx = ask.refuse if ask.refuse is not None else 0
        if self.tracker is None:
            return idx
        if len(tokens) > 1:
            feats = self.tracker.encode(obs.executor, ask, self.table, obs.ctx)
            blank = np.zeros((feats["cards_i"].shape[0], 4), np.int16)
            self.tracker.forecast(self.forecast(feats) if self.forecast else blank)
            self.samples.append((feats, idx))
        self.tracker.end(obs.executor, ask, idx)
        return idx


def _game(table, cards, scripts, life=(20, 20), forecast=None):
    """Seat 0's first main phase of turn 1 with ``cards`` (pack key, card, zone, seat), played to
    the game's end by ``scripts``; seat 0 plans and records. Returns its tracker, its driver and
    the pack keys' handles."""
    pz = {"name": "planner", "set": "M21", "world": {"seed": 7},
          "life": {"0": life[0], "1": life[1]}, "world_prior": [{"p": 1.0, "cards": []}],
          "cards": [{"key": k, "real": r, "zone": z, "controller": s} for k, r, z, s in cards]}
    game, handles = P.build(pz, 0)
    tracker = PL.Tracker(0, keep=True)
    drivers = [_Scripted(scripts[0], handles, table, tracker, forecast),
               _Scripted(scripts[1], handles, table)]
    oracle = OracleIndex.for_sets("M21")
    router = SelfplayRouter(game, drivers, [SeatLens(s, oracle, ViewOptions()) for s in (0, 1)],
                            supply=P.supply_of(pz))
    _play(game, router, list(game.world.player_order), TURN_CAP, resumed=True)
    assert game.over_reason() is not None and not drivers[0].script and not drivers[1].script
    return tracker, drivers[0], handles


def _names(tracker, handles, keys) -> list:
    """The pack key of each object of ``keys`` (p0, p1 the players; None for an unkeyed card)."""
    handle = {i: h for (h, _), i in tracker.ids.items()}
    key = {h: k for k, h in handles.items()}
    return [key.get(handle[int(k)]) for k in keys]


def _samples(tracker) -> list:
    return [d for d in tracker.decisions if d.sample]


def _labels(tracker, handles, sample: int) -> dict:
    """A sample's hindsight labels in words, by pack key: (when, verb, window, target's key)."""
    d, y = _samples(tracker)[sample], PL.hindsight(tracker.decisions)[sample]
    names = _names(tracker, handles, d.keys)
    return {names[2 + r]: (PL.WHEN[y[r, 0]], PL.VERBS[y[r, 1]], PL.WINDOWS[y[r, 2]],
                           names[y[r, 3] - 1] if y[r, 3] else None)
            for r in np.flatnonzero(d.plannable)}


# Seat 0 at turn 1: a land, a Shock at the opponent's creature, a creature cast, an attack for
# lethal (seat 1 at 2 life); an Island it never plays
GAME_A = (("sw1", "Swamp", "battlefield", 0), ("sw2", "Swamp", "battlefield", 0),
          ("mtn", "Mountain", "battlefield", 0), ("dog", "Alpine Watchdog", "battlefield", 0),
          ("sw3", "Swamp", "hand", 0), ("shock", "Shock", "hand", 0),
          ("corpse", "Walking Corpse", "hand", 0), ("isl", "Island", "hand", 0),
          ("their", "Walking Corpse", "battlefield", 1),
          ("lib0", "Island", "library", 0), ("lib1", "Swamp", "library", 1))
SCRIPT_A = (["land:sw3", "cast:shock", "their", "cast:corpse", "ATTACK"], [])
# Seat 0 plays a land and keeps Cancel and its Watchdog home; in its turn seat 1 casts a Walking
# Corpse, which Cancel counters, and attacks with its other one, which the Watchdog blocks
GAME_B = (("i1", "Island", "battlefield", 0), ("i2", "Island", "battlefield", 0),
          ("i3", "Island", "battlefield", 0), ("dog", "Alpine Watchdog", "battlefield", 0),
          ("cancel", "Cancel", "hand", 0), ("i4", "Island", "hand", 0),
          ("s1", "Swamp", "battlefield", 1), ("s2", "Swamp", "battlefield", 1),
          ("their", "Walking Corpse", "battlefield", 1), ("corpse2", "Walking Corpse", "hand", 1),
          ("lib0", "Island", "library", 0), ("lib1", "Swamp", "library", 1))
SCRIPT_B = (["land:i4", "DECLINE", "cast:cancel", "their"], ["cast:corpse2", "PASS", "ATTACK"])
# Village Rites sacrifices the Walking Corpse as its additional cost (CR 601.2h)
GAME_C = (("sw1", "Swamp", "battlefield", 0), ("corpse", "Walking Corpse", "battlefield", 0),
          ("dog", "Alpine Watchdog", "battlefield", 0), ("rites", "Village Rites", "hand", 0),
          ("lib0", "Island", "library", 0), ("lib1", "Swamp", "library", 1))
SCRIPT_C = (["cast:rites", "corpse"], [])
# Kinetic Augur's trigger discards "up to two" cards (its ask offers NONE), then a land is played
GAME_E = (("m1", "Mountain", "battlefield", 0), ("m2", "Mountain", "battlefield", 0),
          ("m3", "Mountain", "battlefield", 0), ("m4", "Mountain", "battlefield", 0),
          ("augur", "Kinetic Augur", "hand", 0), ("m5", "Mountain", "hand", 0),
          ("lib0", "Island", "library", 0), ("lib1", "Swamp", "library", 1))
SCRIPT_E = (["cast:augur", "NONE", "land:m5"], [])
# Seat 0 casts a Walking Corpse, then plays a land; with ``shock``, seat 1 Shocks seat 0 in
# response to the Corpse, between the two
GAME_D = (("sw1", "Swamp", "battlefield", 0), ("sw2", "Swamp", "battlefield", 0),
          ("corpse", "Walking Corpse", "hand", 0), ("sw3", "Swamp", "hand", 0),
          ("mtn", "Mountain", "battlefield", 1), ("shock", "Shock", "hand", 1),
          ("lib0", "Island", "library", 0), ("lib1", "Swamp", "library", 1))


def test_a_main_phase_sequence_is_a1_a2_a3_an_attack_later_and_an_unused_card_never(table) -> None:
    """DESIGN_PLANNER §1 on a scripted turn: from the seat's first decision the land, the Shock
    (its target the creature it was aimed at by the pick after it) and the creature cast are
    this sequence's uses A1, A2, A3 at sorcery speed; the Watchdog attacks later this turn, in my
    combat, at the opponent; the Island in hand and the lands that only paid mana are never used,
    for the game ends first; the opponent's creature is no plannable object. Each later decision
    counts the sequence from itself on."""
    tracker, _, handles = _game(table, GAME_A, SCRIPT_A, life=(20, 2))
    first = _labels(tracker, handles, 0)
    assert first["sw3"] == ("A1", "land", "my main phase", None)
    assert first["shock"] == ("A2", "cast", "my main phase", "their")
    assert first["corpse"] == ("A3", "cast", "my main phase", None)
    assert first["dog"] == ("later this turn", "attack", "my combat", "p1")
    assert first["isl"] == first["mtn"] == first["sw1"] == ("never", "none", "none", None)
    assert "their" not in first
    second = _labels(tracker, handles, 1)  # the Shock cast; the land is a new object now
    assert second["shock"][:2] == ("A1", "cast") and second["corpse"][0] == "A2"
    assert second["sw3"][0] == "never"
    third = _labels(tracker, handles, 2)  # Shock's target pick: its cast was the use before it
    assert third["shock"][0] == "never" and third["corpse"][0] == "A1"
    assert _labels(tracker, handles, 4)["dog"] == ("A1", "attack", "my combat", "p1")


def test_a_held_counter_and_a_blocker_are_planned_into_the_opponents_turn(table) -> None:
    """The owner's case (DESIGN_PLANNER §1): Cancel kept through seat 0's turn and cast in
    response to the opponent's spell reads "their next turn, cast, in response to their spell"
    from the turn before (its target was no entity then: none); the Watchdog kept home blocks in
    their combat, its target the attacker. At the opponent's cast the counter is A1 in its own
    window, in a sequence of its own (the opponent acted)."""
    tracker, _, handles = _game(table, GAME_B, SCRIPT_B)
    first = _labels(tracker, handles, 0)
    assert first["i4"] == ("A1", "land", "my main phase", None)
    assert first["cancel"] == ("their next turn", "cast", "their spell", None)
    assert first["dog"] == ("their next turn", "block", "their combat", "their")
    assert _labels(tracker, handles, 1)["dog"][:2] == ("their next turn", "block")  # the DECLINE
    samples = _samples(tracker)
    cast = next(i for i, d in enumerate(samples) if d.uses and PL.VERBS[d.uses[0][1]] == "cast")
    assert samples[cast].turn == 2 and samples[cast].seq > samples[1].seq
    assert _labels(tracker, handles, cast)["cancel"] == ("A1", "cast", "their spell", None)


def test_an_action_of_the_opponent_ends_the_sequence(table) -> None:
    """A sequence is the seat's run of decisions in one step of one turn with no action of the
    opponent in between: the land played after the Corpse is A2 when the opponent only passed,
    and later this turn when it cast a Shock in response in between."""
    for opponent, land in (([], "A2"), (["cast:shock", "p0"], "later this turn")):
        tracker, _, handles = _game(table, GAME_D, (["cast:corpse", "land:sw3"], opponent))
        first = _labels(tracker, handles, 0)
        assert first["corpse"][0] == "A1" and first["sw3"] == (land, "land", "my main phase", None)


def test_an_up_to_choice_left_empty_is_no_use(table) -> None:
    """Kinetic Augur's trigger discards "up to two" cards and its ask offers NONE. Answered NONE it
    picks no object, so it makes no use and takes no place in the sequence: the land after it is
    A2. (The review of 2026-11-18 found a "cost" use of no object there, which made the land A3.)"""
    tracker, _, handles = _game(table, GAME_E, SCRIPT_E)
    first = _labels(tracker, handles, 0)
    assert first["augur"][:2] == ("A1", "cast")
    assert first["m5"] == ("A2", "land", "my main phase", None)
    assert all(h is not None for h, _ in tracker.ids)


class _MulliganOnce(HeuristicAgent):
    """The heuristic, taking a mulligan at its first mulligan ask, as a recording planning seat
    (blank forecasts); ``hands``: its hand at each mulligan ask, ``samples``: the features of
    each forecast decision."""

    def __init__(self, table) -> None:
        super().__init__()
        self.table, self.tracker = table, PL.Tracker(0, keep=True)
        self.hands: list[list] = []
        self.samples: list[dict] = []

    def decide(self, ask, obs) -> int:
        ex = obs.executor
        self.tracker.begin(ex)
        tokens = [o.token for o in ask.options]
        if ask.kind == "mulligan":
            self.hands.append(list(ex.world.players[ex.world.player_order[0]].zone("hand").entries))
        idx = (tokens.index("mulligan") if ask.kind == "mulligan" and len(self.hands) == 1
               else super().decide(ask, obs))
        if len(tokens) > 1:
            feats = self.tracker.encode(ex, ask, self.table, obs.ctx)
            self.tracker.forecast(np.zeros((feats["cards_i"].shape[0], 4), np.int16))
            self.samples.append(feats)
        self.tracker.end(ex, ask, idx)
        return idx


def test_a_mulligan_makes_every_card_of_the_hand_a_new_object(table) -> None:
    """The London mulligan shuffles the hand into the library (CR 103.5), so each of its cards is
    a new object after it (CR 400.7), drawn again or not. The engine does not journal those moves
    (games.mulligans), so the tracker renews them: at the mulligan every card of the hand is
    "never" used, and the next decision reads no forecast back onto a card drawn again. Seed 8
    draws one again and plays it later (the review of 2026-11-18 found it labelled with that
    use; seed 7 did until gate round W3's re-baked cards left the verified M21 pool and changed
    its deal)."""
    me = _MulliganOnce(table)
    play_game(8, [me, HeuristicAgent()], deck_mode="coherent", pool_mode="verified")
    tracker = me.tracker
    handle = {i: h for (h, _), i in tracker.ids.items()}
    again = set(me.hands[0]) & set(me.hands[1])
    assert again and any(handle[u[0]] in again for d in tracker.decisions for u in d.uses)
    first, second = _samples(tracker)[:2]
    assert set(PL.hindsight(tracker.decisions)[0][first.plannable, 0]) == {PL.NEVER}
    read = me.samples[1]["cards_i"][:, FT.C_PLAN_WHEN:]
    rows = [r for r, k in enumerate(second.keys[2:]) if handle[int(k)] in again]
    assert rows and not read[rows].any()


def test_a_cost_choice_is_a_use_of_the_object_it_picks(table) -> None:
    """Village Rites' sacrifice (CR 601.2h) picks the Walking Corpse: after the cast (A1) the
    Corpse's use is A2, the verb "cost"; the Watchdog, never attacking, is never used."""
    tracker, _, handles = _game(table, GAME_C, SCRIPT_C)
    first = _labels(tracker, handles, 0)
    assert first["rites"] == ("A1", "cast", "my main phase", None)
    assert first["corpse"] == ("A2", "cost", "my main phase", None)
    assert first["dog"] == ("never", "none", "none", None)


def test_the_readback_is_the_last_forecast_until_the_object_moves(table) -> None:
    """Each decision reads back, on each card row, the seat's last forecast for that object:
    when, verb and window as the index + 1, the target as a pointer + 1 to the entity that is
    the target object now. The seat's first decision reads none; a card that changed zones since
    is a new object (CR 400.7) and reads none, as does the opponent's creature (never planned);
    a target that is no entity now points nowhere."""
    def forecast(feats: dict) -> np.ndarray:  # every card: A2, cast, my main phase, the opponent
        return np.tile(np.array([PL.A1 + 1, PL.V_CAST, PL.W_MAIN, 2], np.int16),
                       (feats["cards_i"].shape[0], 1))

    tracker, me, handles = _game(table, GAME_A, SCRIPT_A, life=(20, 2), forecast=forecast)
    cols = slice(FT.C_PLAN_WHEN, FT.C_PLAN_TARGET + 1)
    assert not me.samples[0][0]["cards_i"][:, cols].any()
    second = me.samples[1][0]["cards_i"][:, cols]
    names = _names(tracker, handles, _samples(tracker)[1].keys)[2:]
    for r, name in enumerate(names):
        want = [0, 0, 0, 0] if name in ("sw3", "their") else [2, 2, 2, 2]
        assert second[r].tolist() == want, name
    assert PL.readback(np.array([0, 1, 5, 6]), {5: (0, 1, 1, 9), 7: (2, 2, 2, None)}).tolist() == [
        [1, 2, 2, 0], [0, 0, 0, 0]]


def test_plan_following_reads_the_previous_decisions_hindsight_labels(table) -> None:
    """DESIGN_PLANNER §3.1: plan-following's read-back at a decision is the previous decision's
    realized labels, read back onto it as its forecast was: by object, the target to the entity
    that is that object now. The seat's first decision has none."""
    tracker, _, handles = _game(table, GAME_A, SCRIPT_A, life=(20, 2))
    out, samples = tracker.result(), _samples(tracker)
    assert out[0][1] is None and len(out) == len(samples)
    x = dict(zip(_names(tracker, handles, samples[1].keys)[2:], out[1][1].tolist(), strict=True))
    their = _names(tracker, handles, samples[1].keys).index("their")
    assert x["shock"] == [PL.A1 + 2, PL.V_CAST + 1, PL.W_MAIN + 1, their + 1]  # A2 then
    assert x["dog"] == [PL.LATER_THIS_TURN + 1, PL.V_ATTACK + 1, PL.W_MY_COMBAT + 1, 2]
    assert x["sw3"] == x["their"] == [0, 0, 0, 0]
    for (prev, (y, _)), (cur, (_, x)) in pairwise(zip(samples, out, strict=True)):
        assert np.array_equal(x, PL.readback(cur.keys, PL.plan_of(prev.keys, prev.plannable, y)))


def _batch(table):
    """Games A and B's samples as a training batch with their planner arrays (planner.attach),
    the scripted answers as the actions taken."""
    feats, acts = [], []
    for cards, script, life in ((GAME_A, SCRIPT_A, (20, 2)), (GAME_B, SCRIPT_B, (20, 20))):
        tracker, me, _ = _game(table, cards, script, life)
        for (f, idx), pair in zip(me.samples, tracker.result(), strict=True):
            PL.attach(f, pair)
            feats.append(f)
            acts.append(idx)
    packed = M.pack(feats)
    return M.collate_packed(packed, np.arange(len(feats)), "cpu"), torch.tensor(acts), packed


def test_the_side_losses_fall_on_a_fixed_batch(table) -> None:
    """The hindsight loss of the four heads and the plan-following NLL both fall when trained on
    one fixed batch (the heads and the read-back's layers reach what they predict and read)."""
    torch.manual_seed(0)
    net = M.build(table, d=32, layers=1, heads=4, ff=64, planner=True).eval()  # no name dropout
    b, act, packed = _batch(table)
    rows = packed.plan_m.astype(bool)
    assert rows.sum() == len(act) - 2  # each game's first decision has no previous one
    opt = torch.optim.Adam(net.parameters(), lr=3e-3)
    seen = []
    for _ in range(60):
        _, _, heads = net(b, plan=True)
        hind, nll, counts = planner_terms(net, b, heads, act, rows, False)
        seen.append((float(hind.detach().mean()), float(nll.detach().mean())))
        opt.zero_grad()
        (hind.mean() + nll.mean()).backward()
        opt.step()
    assert counts["labelled"] == int((b["plan_y"][..., 0] >= 0).sum()) > 0
    assert seen[-1][0] < 0.5 * seen[0][0] and seen[-1][1] < 0.5 * seen[0][1]


def test_without_the_planner_nothing_changes(table) -> None:
    """--planner off computes what the code before the planner computed: every encoding's
    read-back columns are 0, and an encoding cut to the old width collates to the same batch
    (``widened``); a network built without it has no planner parameter and saves the config it
    saved; a planner network reads a blank read-back as one without it does (same seed: same
    logits and values); the update with the planner off reads none of a batch's planner arrays
    (the same weights after it as from the batch without them)."""
    feats = []

    class Recording(HeuristicAgent):
        def decide(self, ask, obs):
            if len(ask.options) > 1 and len(feats) < 64:
                feats.append(FT.encode(obs.executor, ask.seat, ask, table, obs.ctx))
            return super().decide(ask, obs)

    play_game(5, [Recording(), Recording()], pool_mode="verified", deck_mode="coherent")
    assert len(feats) == 64 and FT.C_PLAN_WHEN == 9
    assert not any(f["cards_i"][:, FT.C_PLAN_WHEN:].any() for f in feats)
    old = [{**f, "cards_i": f["cards_i"][:, :FT.C_PLAN_WHEN]} for f in feats]
    b = M.collate(feats, "cpu")
    assert all(torch.equal(v, M.collate(old, "cpu")[k]) for k, v in b.items())
    torch.manual_seed(1)
    net = M.build(table, d=32, layers=1, heads=4, ff=64).eval()
    torch.manual_seed(1)
    planner = M.build(table, d=32, layers=1, heads=4, ff=64, planner=True).eval()
    assert "planner" not in net.config and not any(k.startswith("plan_") for k in net.state_dict())
    with torch.no_grad():
        for got, want in zip(planner(b, plan=True)[:2], net(b), strict=True):
            assert torch.equal(got, want)
    a = SimpleNamespace(mb=16, tok_budget=4096, epochs=2, clip=0.2, vclip=0.5, vcoef=0.5,
                        ent=0.01, max_grad=1.0, target_kl=0.0, planner=False)
    n = len(feats)
    rng = np.random.default_rng(0)
    rows = [(f, 0, -0.5, 0.0, float(rng.normal()), float(rng.normal())) for f in feats]
    states = []
    # Bitwise equal weights need one CPU thread: threaded kernels may sum in another order from
    # run to run, so two updates WITHOUT planner arrays already differed by about 1e-8 at 2 and 4
    # threads on some batches (gate round W3's review, MAJOR-1: seed 5's deal moved with the
    # verified pool). One thread keeps the claim exact; reseeding would only move the deal again.
    threads = torch.get_num_threads()
    torch.set_num_threads(1)
    try:
        for with_arrays in (False, True):
            if with_arrays:
                for f in feats:
                    PL.attach(f, None)
            torch.manual_seed(2)
            model = M.build(table, d=32, layers=1, heads=4, ff=64)
            opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
            stats = ppo_train(model, opt, a=a, device=torch.device("cpu"),
                              rng=np.random.default_rng(3), **pack_buffer(rows))
            assert "plan" not in stats and stats["steps"] == n
            states.append(model.state_dict())
    finally:
        torch.set_num_threads(threads)
    assert all(torch.equal(v, states[1][k]) for k, v in states[0].items())


def test_an_older_network_becomes_a_planner_computing_what_it_did(table, tmp_path) -> None:
    """A checkpoint from before the planner loads as it was, and with ``planner`` as a planner
    network whose new layers are zero (model.upgraded): bitwise the same tokens, logits and value
    whatever its read-back holds, and uniform forecasts. A seeded build of a planner network draws
    every older layer's weights as a build without it does (its layers come after _init)."""
    net = M.build(table, d=32, layers=1, heads=4, ff=64).eval()
    with torch.no_grad():
        for p in net.parameters():
            p.normal_(0, 0.1)
    path = tmp_path / "old.pt"
    M.save(str(path), net, table)
    same, _, _ = M.load(str(path))
    grown, _, _ = M.load(str(path), planner=True)
    assert not same.planner and grown.planner
    assert all(not v.any() for k, v in grown.state_dict().items() if k.startswith("plan_"))
    _, me, _ = _game(table, GAME_A, SCRIPT_A, life=(20, 2))
    feats = [f for f, _ in me.samples]
    b = M.collate(feats, "cpu")
    rng = np.random.default_rng(0)
    read = {**b, "cards_i": b["cards_i"].clone()}
    read["cards_i"][..., FT.C_PLAN_WHEN] = torch.from_numpy(rng.integers(0, 11, b["card_mask"].shape))
    read["cards_i"][..., FT.C_PLAN_TARGET] = torch.from_numpy(rng.integers(0, 3, b["card_mask"].shape))
    with torch.no_grad():
        assert torch.equal(same.tokens(b)[0], net.tokens(b)[0])
        assert torch.equal(grown.tokens(read)[0], net.tokens(b)[0])
        logits, value, heads = grown(read, plan=True)
        want = net(b)
    assert torch.equal(logits, want[0]) and torch.equal(value, want[1])
    assert all(not h[b["card_mask"]].any() for h in heads[:3])  # all zero: uniform
    for seed in (0, 7):
        torch.manual_seed(seed)
        base = M.build(table, d=32, layers=2, heads=4, ff=64).state_dict()
        torch.manual_seed(seed)
        plan = M.build(table, d=32, layers=2, heads=4, ff=64, planner=True).state_dict()
        assert all(torch.equal(v, plan[k]) for k, v in base.items())


def test_a_planner_training_game_carries_its_labels_to_the_update(tmp_path, monkeypatch) -> None:
    """--planner end to end in one process: the job asks both seats of a self game to plan; each
    learner decision gets its forecast from the learner's inference and comes back with its
    hindsight labels, one per decision; the update reports the hindsight accuracies and the
    plan-following NLL. A run's network and --planner agree, or it is refused."""
    from tools.selfplay.actor import Worker

    lr = _small_learner(monkeypatch, tmp_path / "run", "--planner", "--p-heuristic", "0",
                        "--p-past", "0", "--p-self", "1", "--follow-share", "0.5")
    lr.stage, lr.versions = "selfplay", ["v0"]
    job = lr.curriculum_job()
    assert lr.model.planner and job["plan"] == [True, True]
    slot = _LearnerSlot(lr)
    res = Worker(0, None, 1, lr.table.to_json()).play(job, slot)
    assert [len(p) for p in res["plans"]] == [slot.asked["learner", s] for s in (0, 1)]
    lr.on_done([res])
    rows = lr.buffer
    assert rows and all(r[0]["plan_y"].shape == (r[0]["cards_i"].shape[0], 4) for r in rows)
    assert sum(int(r[0]["plan_m"][0]) for r in rows) == len(rows) - 2
    a = SimpleNamespace(**{**vars(lr.args), "mb": 64, "tok_budget": 1 << 16, "target_kl": 0.0})
    stats = ppo_train(lr.model, torch.optim.AdamW(lr.model.parameters(), lr=1e-4), a=a,
                      device=torch.device("cpu"), rng=np.random.default_rng(0),
                      **pack_buffer(rows))
    plan = stats["plan"]
    assert plan["labelled"] > 0 and set(plan["acc"]) == set(PL.HEADS)
    assert plan["follow_rows"] > 0 and plan["follow"] > 0
    lr.save("planner.pt")
    with pytest.raises(ValueError, match="planner"):  # a planner network needs --planner
        _small_learner(monkeypatch, tmp_path / "other", "--init", str(lr.run / "planner.pt"))
