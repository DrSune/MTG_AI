"""The drafter v0's pieces (tools/selfplay/decks.py, docs/PLAN_DRAFTER.md)."""

import json
import os
from collections import Counter

import numpy as np
import pytest

from tools.selfplay import decks as D


def _rows(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return str(path)


def test_rebuild_gives_the_decks_the_seed_dealt(tmp_path) -> None:
    """The rebuilt decks are deal_decks' decks for the row's seed, mode and set, seat 0 first."""
    from MTG_bot.core.executor.games import deal_decks, get_supply

    rows = _rows(tmp_path / "rows.jsonl", [
        {"seed": 5, "deck_mode": "coherent", "set_code": "M21"},
        {"seed": 5, "deck_mode": "coherent", "set_code": "M21"},  # a deal's second game
        {"seed": 6, "deck_mode": "stress", "set_code": "M21"},
        {"seed": 7, "deck_mode": "coherent", "set_code": "M20"},
        {"seed": 8, "deck_mode": None}])
    out = str(tmp_path / "decks.npz")
    D._rebuild_here(out, "verified", "test", [rows])
    z = np.load(out)
    assert [(int(s), str(m), str(t)) for s, m, t in zip(z["seed"], z["mode"], z["set"],
                                                         strict=True)] == [
        (5, "coherent", "M21"), (6, "stress", "M21"), (7, "coherent", "M20")]
    for k in range(3):
        sup = get_supply("verified", str(z["set"][k]))
        want = deal_decks(int(z["seed"][k]), D.DEAL_SEED, sup, str(z["mode"][k]))
        for seat in (0, 1):
            a, b = z["off"][2 * k + seat], z["off"][2 * k + seat + 1]
            got = Counter({str(z["card"][i]): int(n) for i, n in zip(z["idx"][a:b], z["cnt"][a:b],
                                                                     strict=True)})
            assert got == Counter(want[seat])
    assert set(z["rarity"]) <= {"common", "uncommon", "rare", "mythic"}


def _toy(n_games: int, true: np.ndarray, rng: np.random.Generator) -> tuple[dict, list]:
    """Decks of 10 copies over 6 cards, and games won by the higher true value (logistic)."""
    seeds, off, idx, cnt, games = [], [0], [], [], []
    for g in range(n_games):
        for _ in (0, 1):
            deck = Counter(rng.integers(0, 6, 10).tolist())
            for c, n in sorted(deck.items()):
                idx.append(c)
                cnt.append(n)
            off.append(len(idx))
        seeds.append(g)
        v = [sum(true[idx[i]] * cnt[i] for i in range(off[2 * g + s], off[2 * g + s + 1]))
             for s in (0, 1)]
        won = int(rng.random() < 1 / (1 + np.exp(-(v[0] - v[1]))))
        games.append((g, won, "x:a", "x:b", g))
    decks = {"seed": np.array(seeds), "mode": np.array(["coherent"] * n_games),
             "set": np.array(["M21"] * n_games), "off": np.array(off), "idx": np.array(idx),
             "cnt": np.array(cnt), "card": np.array([f"c{i}" for i in range(6)]),
             "basic": np.zeros(6, bool), "land": np.zeros(6, bool), "mv": np.full(6, 2),
             "creature": np.ones(6, bool), "rarity": np.array(["common"] * 6)}
    return decks, games


def test_the_critic_recovers_card_values_and_beats_a_blind_baseline() -> None:
    rng = np.random.default_rng(0)
    true = np.array([0.0, 0.1, 0.2, -0.2, 0.4, -0.3])
    decks, games = _toy(4000, true, rng)
    x, y, seeds, vocab, _feat, n_pil = D.design([(decks, games)], cards=True)
    assert x.shape == (4000, 6 + 2) and n_pil == 2 and vocab == [f"c{i}" for i in range(6)]
    w, _ = D.fit(x, y, 1e-4)
    assert np.corrcoef(w[:6], true)[0, 1] > 0.9  # the values, up to a constant per deck size
    cards = D.cross_validate(x, y, seeds, (1e-4,))
    xb, *_ = D.design([(decks, games)], cards=False)  # every deck's summaries are equal here
    base = D.cross_validate(xb, y, seeds, (1e-4,))
    assert cards["loss"].mean() < base["loss"].mean()


def test_games_keep_decided_network_games_and_refuse_unknown_deals(tmp_path) -> None:
    decks = {"seed": np.array([1]), "mode": np.array(["coherent"]), "set": np.array(["M21"])}
    base = {"seed": 1, "deck_mode": "coherent", "set_code": "M21", "outcome": "win",
            "winner": 1, "seats": ["eval", "v0"], "tag": "gate:it25"}
    rows = _rows(tmp_path / "rows.jsonl", [
        base,
        {**base, "seats": ["heuristic", "v0"]},  # not two networks
        {**base, "outcome": "void-crash", "winner": None},
        {**base, "deck_mode": "stress"}])
    assert D.games(rows, decks, "r") == [(0, 0, "r:eval@gate:it25", "r:v0", 1)]
    bad = _rows(tmp_path / "bad.jsonl", [{**base, "seed": 2}])
    with pytest.raises(ValueError, match="not among the rebuilt decks"):
        D.games(bad, decks, "r")


def test_swap_spends_k_swaps_on_the_best_gain_within_the_guard() -> None:
    value = {"a": -0.2, "b": 0.0, "c": 0.1, "d": 0.3, "e": 0.5}
    spells = sorted(value)
    deck = Counter({"a": 4, "b": 4, "Plains": 12})
    assert D.swap(deck, value, spells, 0) == deck
    one = D.swap(deck, value, spells, 1)
    assert one == Counter({"a": 3, "b": 4, "e": 1, "Plains": 12})  # worst out, best in
    five = D.swap(deck, value, spells, 5)
    assert five == Counter({"b": 3, "d": 1, "e": 4, "Plains": 12})  # e capped at 4, then b->d
    assert D.swap(deck, value, spells, 5) == five  # deterministic
    guarded = D.swap(deck, value, spells, 5, ok=lambda d: d["e"] <= 1)
    assert guarded["e"] == 1 and guarded["d"] == 4  # the guard turns it to the next best card
    best = Counter({"e": 4, "d": 4})
    assert D.swap(best, value, spells, 3) == best  # nothing gains: it stops


def _critic(supply, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    value = {c: float(rng.normal(0, 0.1)) for c in supply.deckable}
    wide = {"mv": [0.0, 99.0], "creatures": [0.0, 99.0], "copies": 4.0, "decks": 0}
    return {"value": value, "band": {"M21": wide}, "sha256": "ab" * 32}


def test_drafted_decks_swap_the_right_seats_and_stay_legal() -> None:
    from MTG_bot.core.executor.games import _BASIC_COLOR, deal_decks, get_supply

    sup = get_supply("verified", "M21")
    critic = _critic(sup)
    dealt = deal_decks(31, D.DEAL_SEED, sup, "coherent")
    same = D.drafted_decks(31, "versus:0:abababab", 0, sup, critic, "M21")
    assert [Counter(d) for d in same] == [Counter(d) for d in dealt]  # k = 0 is the deal
    v1 = D.drafted_decks(31, "versus:6:abababab", 1, sup, critic, "M21")
    assert Counter(v1[0]) == Counter(dealt[1])  # the evaluated seat 1 holds seat 0's deck, drafted
    mine = Counter(v1[1])
    assert mine != Counter(dealt[0]) and sum(mine.values()) == 60
    pair = {_BASIC_COLOR[sup.metas[c].name] for c in dealt[0] if sup.metas[c].is_basic}
    for c, n in mine.items():
        m = sup.metas[c]
        assert m.is_basic or (n <= 4 and set(sup.pool.results[c].card.color_identity) <= pair)
    assert sum(critic["value"][c] * n for c, n in mine.items()) > sum(
        critic["value"][c] for c in dealt[0])
    both = D.drafted_decks(31, "drafted:6:abababab", None, sup, critic, "M21")
    assert Counter(both[0]) == mine and Counter(both[1]) != Counter(dealt[1])
    with pytest.raises(ValueError, match="does not match critic"):
        D.drafted_decks(31, "versus:6:cdcdcdcd", 0, sup, critic, "M21")


def test_play_game_deals_the_decks_it_is_given(monkeypatch) -> None:
    from tools.selfplay import rig

    seen = []

    def stop(seed, supply, decks, **kw):
        seen.append(decks)
        raise RuntimeError("stop")

    monkeypatch.setattr(rig, "_setup_game", stop)
    decks = (("a",) * 60, ("b",) * 60)
    with pytest.raises(RuntimeError, match="stop"):
        rig.play_game(1, [None, None], deck_mode="versus:4:abababab", decks=decks)
    assert seen == [decks]


def test_the_learner_wants_a_critic_for_a_drafted_deck_mode() -> None:
    from tools.selfplay import learner as L

    assert L.parse(["--run", "x", "--eval-decks", "versus:8", "--draft-critic", "c.json"])
    for bad in (["--eval-decks", "versus:8"], ["--eval-decks", "best", "--draft-critic", "c"]):
        with pytest.raises(SystemExit):
            L.parse(["--run", "x", *bad])


# ------------------------------------------------- package mode (tools/selfplay/packages.py)

def _m21():
    from MTG_bot.core.executor.games import get_supply

    sup = get_supply("verified", "M21")
    return sup, {sup.metas[c].name: c for c in sup.deckable}


def test_package_decks_depend_on_the_deal_seed_alone() -> None:
    """The same deal gives the same decks whatever the global RNG and the process's string hash
    seed (each learner worker derives the packages itself); other deals give other decks."""
    import random
    import subprocess
    import sys

    from tools.selfplay import packages as PK

    sup, _ = _m21()
    random.seed(1)
    here = [PK.package_decks(s, sup) for s in range(1, 9)]
    random.seed(2)
    assert [PK.package_decks(s, sup) for s in range(1, 9)] == here
    assert len(set(here)) == 8
    code = ("from MTG_bot.core.executor.games import get_supply\n"
            "from tools.selfplay import packages as PK\n"
            "sup = get_supply('verified', 'M21')\n"
            "print(repr([PK.package_decks(s, sup) for s in range(1, 9)]))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                         cwd=D.REPO, env={**os.environ, "PYTHONHASHSEED": "7"}).stdout
    assert out.strip() == repr(here)


def test_package_decks_are_legal_and_carry_their_package() -> None:
    from MTG_bot.core.executor.games import COHERENT_LANDS, DECK_SIZE, MAX_COPIES
    from tools.selfplay import packages as PK

    sup, _ = _m21()
    kept = PK.packages(sup)
    seen = set()
    for seed in range(60):
        pkg, deck = PK.build(seed, sup, kept)
        seen.add(pkg)
        n = Counter(deck)
        basics = [c for c in n if sup.metas[c].is_basic]
        pair = set().union(*(sup.pool.results[c].card.color_identity for c in basics))
        assert len(deck) == DECK_SIZE and len(pair) == 2
        assert sorted(n[c] for c in basics) == [COHERENT_LANDS // 2] * 2
        for c, k in n.items():
            if not sup.metas[c].is_basic:
                assert k <= MAX_COPIES and not sup.metas[c].is_land
                assert sup.pool.results[c].card.color_identity <= pair
        held = [c for c in pkg.consumers if sup.pool.results[c].card.color_identity <= pair]
        assert sum(n[c] for c in pkg.consumers) >= min(PK.CONSUMER_COPIES, MAX_COPIES * len(held))
        assert sum(n[c] for c in pkg.producers) >= PK.PRODUCER_COPIES  # basics included
    assert len(seen) > len(kept) // 2  # the deal draws packages, not always the same one


def test_a_derived_package_holds_its_consumers_and_producers() -> None:
    """M21's lifegain package, read off the trees: "whenever you gain life" (Vito) and a granted
    one (Light of Promise) are consumers; GAIN_LIFE (Revitalize) and lifelink (Baneslayer Angel)
    produce, a burn spell does not. The flyers package takes a token maker (Falconer Adept's
    Birds) but not a flyer made for the opponent (Angelic Ascension's Angel)."""
    from tools.selfplay import packages as PK

    sup, oid = _m21()
    kept = PK.packages(sup)
    life = next(p for p in kept if oid["Vito, Thorn of the Dusk Rose"] in p.consumers)
    assert PK.label(life) == "life" and life.pairs == ("BW",)
    assert oid["Light of Promise"] in life.consumers
    assert {oid["Revitalize"], oid["Baneslayer Angel"]} <= set(life.producers)
    assert oid["Shock"] not in life.producers
    fly = next(p for p in kept if oid["Watcher of the Spheres"] in p.consumers)
    assert oid["Falconer Adept"] in fly.producers
    assert oid["Angelic Ascension"] not in fly.producers


def test_an_event_or_predicate_the_table_does_not_read_is_skipped() -> None:
    from MTG_bot.core.ability_tree import (
        Atom,
        AtomArgs,
        ControllerRef,
        FAtom,
        FAtomPred,
        FNot,
        LifeGainedEvent,
        PhasingEvent,
        QConst,
        StaticAbility,
        TriggeredAbility,
        Verb,
    )
    from tools.selfplay import packages as PK

    draw = Atom(Verb.DRAW, AtomArgs((("amount", QConst(1)), ("controller", ControllerRef.YOU))))
    creature = FAtom(FAtomPred.TYPE_EQ, string_value="Creature")
    you = FAtom(FAtomPred.CONTROLLER_IS, who=ControllerRef.YOU)
    assert PK.shapes(TriggeredAbility(PhasingEvent(True, creature), None, draw)) == set()
    assert PK.shapes(TriggeredAbility(LifeGainedEvent(you), None, draw)) == {("life", None)}
    gained = FAtom(FAtomPred.LIFE_GAINED_THIS_TURN_GE, count=QConst(3), who=ControllerRef.YOU)
    assert PK.shapes(StaticAbility(draw, gained)) == {("life", None)}
    assert PK.shapes(StaticAbility(draw, FNot(gained))) == set()  # wants no life gained


def test_the_learner_deals_a_share_of_coherent_deals_as_package_decks(monkeypatch) -> None:
    """--package-share: chosen from the deal's seed, so a training deal and an evaluation deal
    of one seed agree; only coherent training and evaluation deals; and the worker deals them."""
    from types import SimpleNamespace

    from MTG_bot.core.executor.games import get_supply
    from tools.selfplay import actor as A
    from tools.selfplay import features as FT
    from tools.selfplay import learner as L
    from tools.selfplay import packages as PK

    me = SimpleNamespace(gid=0, args=SimpleNamespace(package_share=0.5, pool="verified"))

    def mode(kind: str, seed: int, deck_mode: str = "coherent") -> str:
        return L.Learner._job(me, kind, seed, ["heuristic"] * 2, [True] * 2, [False] * 2,
                              deck_mode)["deck_mode"]

    train = [mode("train", s) for s in range(400)]
    assert 150 < train.count("package") < 250
    assert [mode("eval", s) for s in range(400)] == train
    assert {mode(k, s) for k in ("bc", "capture") for s in range(50)} == {"coherent"}
    assert {mode("train", s, "stress") for s in range(50)} == {"stress"}
    with pytest.raises(SystemExit):
        L.parse(["--run", "x", "--package-share", "1.5"])
    seen = []
    monkeypatch.setattr(A, "play_game", lambda seed, agents, **kw: seen.append(kw["decks"]) or {})
    job = {"gid": 1, "kind": "eval", "seed": 5, "deck_mode": "package", "set_code": "M21",
           "pool_mode": "verified", "seats": ["heuristic"] * 2, "greedy": [True] * 2,
           "record": [False] * 2}
    A.Worker(0, None, 1, FT.CardTable.from_records({}).to_json()).play(job, None)
    assert seen == [PK.package_decks(5, get_supply("verified", "M21"))]
