"""Gates for the A/B duel + anchored ELO batch.

Covers the pre-registered gates: ELO anchor pin (random == 0.0 exactly by
construction), bootstrap CI sanity on synthetic data, D9 seed-bank
disjointness (+ reuse refusal), seat balance, duel determinism on rerun,
the elo.json schema, Wilson edges, outcome classification, and the BcAsk
closed-loop plumbing on a toy model (no real checkpoint, no torch games).
"""

from __future__ import annotations

import json
import random as pyrandom
from pathlib import Path

import pytest

from tools.training.ab_duel import (
    AskContext,
    allocate_seeds,
    classify_outcome,
    load_bank,
    normalize_spec,
    pair_key,
    run_duel,
    seat_swaps,
    summarize,
    wilson,
)
from tools.training.elo import bootstrap_ci, fit_elo


# ------------------------------------------------------------------ unit
def test_wilson_edges() -> None:
    lo, hi = wilson(0, 100)
    assert lo == 0.0 and 0.0 < hi < 0.05
    lo, hi = wilson(100, 100)
    assert hi == pytest.approx(1.0) and 0.95 < lo < 1.0
    lo, hi = wilson(50, 400)
    assert lo < 0.125 < hi and (hi - lo) < 0.08
    assert wilson(3, 0) == (0.0, 1.0)


def test_classify_outcome_lanes() -> None:
    seats = ["p0", "p1"]
    assert classify_outcome("game over: p1(life<=0)", "p0", seats, 0) == "a"
    assert classify_outcome("game over: p0(life<=0)", "p1", seats, 0) == "b"
    assert classify_outcome("STALL (CR 104.4b ...)", None, seats, 0) == "draw-stall"
    assert (
        classify_outcome("turn cap 60 reached (no loser)", None, seats, 0) == "draw-cap"
    )
    assert classify_outcome("draw: p0, p1", None, seats, 0) == "draw-other"
    assert classify_outcome("crash:KeyError: x", None, seats, 0) == "crash"


def test_spec_normalization_and_pair_symmetry() -> None:
    assert normalize_spec("scripted") == "pass-floor"
    assert pair_key("random", "scripted") == pair_key("pass-floor", "random")


# ------------------------------------------------------------- seed bank
def test_seed_bank_disjoint_and_reuse_refused(tmp_path: Path) -> None:
    bank: dict = {"pairs": {}}
    key = pair_key("random", "first")
    s1 = allocate_seeds(bank, key, 5)
    s2 = allocate_seeds(bank, key, 5)
    assert set(s1).isdisjoint(s2)
    with pytest.raises(ValueError, match="D9"):
        allocate_seeds(bank, key, 3, explicit=s1[:3])
    # other pairs keep their own bank
    other = allocate_seeds(bank, pair_key("random", "pass-floor"), 5)
    assert set(other) == set(s1)


def test_seat_balance() -> None:
    assert sum(seat_swaps(10)) == 5
    assert abs(sum(seat_swaps(9)) - 4) <= 1
    assert len(seat_swaps(7)) == 7


# ---------------------------------------------------------------- elo fit
def _synthetic_pairs(
    n: int, true_elo: list[float], anchor: int, rng: pyrandom.Random
) -> dict[tuple[int, int], list[str]]:
    """Round-robin outcomes sampled from latent strengths (pair i<j)."""
    out: dict[tuple[int, int], list[str]] = {}
    for i in range(len(true_elo)):
        for j in range(i + 1, len(true_elo)):
            p = 1.0 / (1.0 + 10.0 ** ((true_elo[j] - true_elo[i]) / 400.0))
            out[(i, j)] = ["a" if rng.random() < p else "b" for _ in range(n)]
    return out


def test_elo_anchor_pin_exact_zero() -> None:
    rng = pyrandom.Random(7)
    pairs = _synthetic_pairs(400, [0.0, 150.0, 400.0], 0, rng)
    elo = fit_elo(
        {k: (v.count("a"), v.count("b"), 0) for k, v in pairs.items()}, 3, anchor=0
    )
    assert elo[0] == 0.0  # pinned BY CONSTRUCTION, not approximately
    assert elo[1] > 40 and elo[2] > elo[1] + 100  # order + rough magnitude


def test_elo_order_recovers_true_strength() -> None:
    rng = pyrandom.Random(11)
    truth = [0.0, 60.0, 220.0, 500.0]
    pairs = _synthetic_pairs(600, truth, 0, rng)
    elo = fit_elo(
        {k: (v.count("a"), v.count("b"), 0) for k, v in pairs.items()}, 4, anchor=0
    )
    assert elo == sorted(elo)  # index order IS strength order


def test_bootstrap_ci_sane_on_synthetic() -> None:
    rng = pyrandom.Random(13)
    pairs_small = _synthetic_pairs(100, [0.0, 250.0], 0, rng)
    pairs_big = _synthetic_pairs(1600, [0.0, 250.0], 0, rng)
    ci_s = bootstrap_ci(pairs_small, 2, 0, reps=200)
    ci_b = bootstrap_ci(pairs_big, 2, 0, reps=200)
    elo_s = fit_elo(
        {k: (v.count("a"), v.count("b"), 0) for k, v in pairs_small.items()}, 2, 0
    )
    # anchor CI is degenerate by construction; the field CI is honest
    assert ci_s[0][0] == pytest.approx(0.0) and ci_s[0][1] == pytest.approx(0.0)
    lo, hi = ci_s[1]
    assert hi > lo > -100 and hi - lo > 10 and lo <= elo_s[1] <= hi
    assert (ci_b[1][1] - ci_b[1][0]) < (ci_s[1][1] - ci_s[1][0])  # more games, tighter


# ------------------------------------------------------------ duel batch
def _duel_kwargs(tmp_path: Path) -> dict:
    return {
        "workers": 1,
        "pool_mode": "all",
        "device": "cpu",
        "bank_path": tmp_path / "seeds.json",
    }


def _solo(tmp_path: Path, bank_name: str) -> dict:
    """One duel batch on its own EMPTY bank file (fresh banks both start
    the D9 allocation at seed 1) -> same pair, same seeds, comparable."""
    kw = _duel_kwargs(tmp_path)
    kw["bank_path"] = tmp_path / bank_name
    res = run_duel(
        "random", "scripted", 4, bank={"pairs": {}}, persist_bank=False, **kw
    )
    return res


def test_duel_determinism_on_rerun(tmp_path: Path) -> None:
    r1, r2 = _solo(tmp_path, "seeds_a.json"), _solo(tmp_path, "seeds_b.json")
    s1 = {k: v for k, v in r1["summary"].items() if k != "games_per_sec"}
    s2 = {k: v for k, v in r2["summary"].items() if k != "games_per_sec"}
    assert s1 == s2
    assert s1["seat_balance_ok"] and s1["games"] == 4
    assert r1["records"] == r2["records"]  # per-game outcome + reason too


def test_seed_bank_persists_and_blocks_reuse(tmp_path: Path) -> None:
    kw = _duel_kwargs(tmp_path)
    run_duel("random", "first", 3, **kw)  # persists the bank
    bank = load_bank(kw["bank_path"])
    assert len(bank["pairs"][pair_key("random", "first")]["used"]) == 3
    with pytest.raises(ValueError, match="D9"):
        run_duel("random", "first", 3, seeds=[1, 2, 3], **kw)  # explicit reuse


def test_summarize_honest_draw_split() -> None:
    records = [
        {
            "seed": 1,
            "swap": False,
            "outcome": "a",
            "reason": "",
            "turns": 9,
            "crash": None,
            "trunc": {},
        },
        {
            "seed": 2,
            "swap": True,
            "outcome": "draw-stall",
            "reason": "",
            "turns": 5,
            "crash": None,
            "trunc": {},
        },
        {
            "seed": 3,
            "swap": False,
            "outcome": "draw-cap",
            "reason": "",
            "turns": 60,
            "crash": None,
            "trunc": {},
        },
    ]
    s = summarize(records, "random", "pass-floor")
    assert s["draws"] == {"stall": 1, "cap": 1, "other": 0}
    assert s["a"]["wins"] == 1 and s["b"]["wins"] == 0
    assert s["a"]["winrate"] == pytest.approx(1 / 3, abs=1e-4)
    assert s["a"]["score"] == pytest.approx(2 / 3, abs=1e-4)  # (1+0.5*2)/3
    assert s["a"]["ci"][0] < 1 / 3 < s["a"]["ci"][1]


def test_elo_json_schema(tmp_path: Path) -> None:
    from tools.training.elo import run_ladder

    bank_path = tmp_path / "elo_seeds.json"
    doc = run_ladder(
        ["random", "scripted", "first"],
        4,
        workers=1,
        device="cpu",
        reps=60,
        bank_path=bank_path,
    )
    assert set(doc) >= {"updated", "anchor", "games_per_pair", "ratings", "games_total"}
    assert doc["anchor"] == "random=0"
    assert doc["games_per_pair"] == 4 and doc["games_total"] == 12
    by_name = {r["policy"]: r for r in doc["ratings"]}
    assert by_name["random"]["elo"] == 0.0  # pinned, exact, in the JSON
    for r in doc["ratings"]:
        assert set(r) == {"policy", "elo", "ci_lo", "ci_hi", "vs_field_wr"}
        assert r["ci_lo"] <= r["elo"] <= r["ci_hi"]
        assert 0.0 <= r["vs_field_wr"] <= 1.0
    json.dumps(doc)  # board-safe


# ----------------------------------------------------------- BcAsk plumbing
def test_bcask_plumbing_toy_model() -> None:
    """Closed-loop adapter on a toy PointerBC (no real checkpoint, no
    engine games): valid in-vocabulary argmax each ask, stream grows under
    the max_len law, truncation counter fires when the budget bites."""
    torch = pytest.importorskip("torch")
    from tools.training import bc_data
    from tools.training.ab_duel import BcAsk
    from tools.training.bc_model import PointerBC

    vocab = {t: i for i, t in enumerate(bc_data.SPECIALS)}
    for w in ("card", "pass", "1", "2", "t", "act", "seat", "life", "p"):
        vocab.setdefault(w, len(vocab))
    torch.manual_seed(0)
    model = PointerBC(
        len(vocab),
        d=64,
        layers=1,
        heads=4,
        ff=64,
        max_len=32,
        grad_checkpoint=False,
    ).eval()
    ask = BcAsk(model, vocab, model.max_len)
    world = {"turn": 3, "active": 0, "seat": 0, "lives": [20, 19]}
    for cands in (
        ("card:1", "card:2"),
        ("PASS", "card:1"),
        ("card:2",),
        ("PASS", "card:2"),
    ):
        idx = ask.decide(AskContext(vocab="choose:x:1", candidates=cands, world=world))
        assert 0 <= idx < len(cands)
    assert ask.truncations > 0  # the 32-token toy budget must have bitten
    assert len(ask.seq) <= model.max_len
