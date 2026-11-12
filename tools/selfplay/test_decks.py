"""The drafter v0's pieces (tools/selfplay/decks.py, docs/PLAN_DRAFTER.md)."""

import json
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
    x, y, seeds, vocab, feat, n_pil = D.design([(decks, games)], cards=True)
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
