"""Pins for the honest gate math (KNOWLEDGE 2026-10-07/26 audit).

1. card-level-coin rows: cluster bootstrap SE visibly exceeds iid SE;
2. all-correct rows: p_beats_floor == 1.0 (degenerate SE);
3. gate_stats wires the cluster numbers next to the iid ones;
4. Elo pair admissibility flips on the bootstrap wr CI vs 0.5;
5. recompute_gates rewrites a report gate block, preserving gate_iid.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tools.training.elo import pair_winrate_admissibility
from tools.training.recompute_gates import recompute_report
from tools.training.train_bc import binomial_stats, cluster_bootstrap_stats, gate_stats


def _card_coin(floor: float = 0.5) -> dict[str, list[int]]:
    """20 cards x 5 items; 12 cards ALL correct, 8 ALL wrong (card-level
    coin at p=0.6). Items within a card are perfectly correlated."""
    return {f"c{i:02d}": [1] * 5 if i < 12 else [0] * 5 for i in range(20)}


def test_card_coin_cluster_se_exceeds_iid_se() -> None:
    by = _card_coin()
    boot = cluster_bootstrap_stats(by, 0.5, B=4000, seed=7)
    iid = binomial_stats(60, 100, 0.5)  # same k/n/floor, iid assumption
    assert boot["n_clusters"] == 20
    assert boot["bootstrap_se"] > 1.5 * iid["se"]  # visible factor
    # and the honest margin is visibly SMALLER than the inflated one
    assert boot["margin_bootstrap_se"] < iid["beat_margin_se"]


def test_all_correct_p_beats_floor_is_one() -> None:
    by = {f"c{i}": [1, 1, 1] for i in range(15)}
    boot = cluster_bootstrap_stats(by, 0.5, B=500, seed=3)
    assert boot["p_beats_floor"] == 1.0
    assert boot["bootstrap_se"] == 0.0  # degenerate: every resample acc=1


def test_gate_stats_reports_bootstrap_alongside_iid() -> None:
    rows = [
        {
            "card": f"c{i % 10}",
            "correct": int(i < 7),
            "cert": {"random": 0.5, "null": 0.1, "l1_ready": True},
        }
        for i in range(100)
    ]
    g = gate_stats(rows, boot_seed=5)
    for key in (
        "beat_margin_se",
        "se",
        "margin_bootstrap_se",
        "p_beats_floor",
        "n_clusters",
        "bootstrap_B",
    ):
        assert key in g["vs_random"]
    assert g["vs_random"]["n_clusters"] == 10
    assert g["vs_random"]["bootstrap_B"] == 4000


# ------------------------------------------------------------------ elo pins
def test_elo_admissibility_flips_on_wr_ci_vs_half() -> None:
    pairs = {
        # mirrors elo_s3_sanity: 120 games, wr_a ~0.425 -> CI straddles 0.5
        (0, 1): ["a"] * 50 + ["b"] * 68 + ["d"] * 2,
        # 120 games, wr_a ~0.81 -> CI clears 0.5 comfortably
        (0, 2): ["a"] * 95 + ["b"] * 25,
    }
    adm = pair_winrate_admissibility(pairs, reps=1000)
    lo, hi = adm[(0, 1)]["wr_ci"]
    assert lo <= 0.5 <= hi and adm[(0, 1)]["admissible"] is False
    lo, hi = adm[(0, 2)]["wr_ci"]
    assert lo > 0.5 and adm[(0, 2)]["admissible"] is True


# ----------------------------------------------------------- recompute pins
def _toy_report(tmp_path: Path) -> Path:
    rows = [
        {
            "pack": f"p{i}.json",
            "card": f"card{i % 8}",
            "ordinal": i,
            "gold_idx": 0,
            "pred_idx": 0,
            "correct": bool(i < 60),
            "eval_family": bool(i >= 57),
            "quartile": 0,
        }
        for i in range(100)
    ]
    certified = [
        {**r, "cert": {"random": 0.5, "null": 0.1, "l1_ready": True}} for r in rows
    ]
    report: dict[str, Any] = {
        "gates": {
            "gold_lines_all": gate_stats(certified, boot_seed=1),
            "train_families": gate_stats(
                [r for r in certified if not r["eval_family"]], boot_seed=1
            ),
            "eval_families": gate_stats(
                [r for r in certified if r["eval_family"]], boot_seed=1
            ),
            "l1_certified": gate_stats(certified, boot_seed=1),
        },
        "gate_verdict": {"verdict": "PASS"},
        "eval_rows": rows,
    }
    path = tmp_path / "toy_report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    return path


def test_recompute_gates_rewrites_and_preserves(tmp_path: Path) -> None:
    path = _toy_report(tmp_path)
    before = json.loads(path.read_text())
    rep = recompute_report(path, B=500, seed_fallback=11)
    # old iid block preserved verbatim
    assert rep["gate_iid"] == before["gates"]
    assert rep["gate_verdict_iid"] == {"verdict": "PASS"}
    g = rep["gates"]["eval_families"]["vs_random"]
    # iid numbers still present AND bootstrap added alongside
    assert (
        g["beat_margin_se"]
        == before["gates"]["eval_families"]["vs_random"]["beat_margin_se"]
    )
    assert isinstance(g["margin_bootstrap_se"], (int, float))
    assert rep["gate_verdict"]["bootstrap_seed"] == 11
    assert rep["gate_verdict"]["verdict"] in ("PASS", "NULL")
    assert "not reconstructable" in rep["gates"]["l1_certified"]["cluster_bootstrap"]
    # bootstrap seeds agree with what the verdict records
    assert g["bootstrap_seed"] == 11


def test_recompute_gates_bails_on_slice_mismatch(tmp_path: Path) -> None:
    path = _toy_report(tmp_path)
    rep = json.loads(path.read_text())
    rep["eval_rows"] = rep["eval_rows"][:90]  # corrupt the reconstructable rows
    path.write_text(json.dumps(rep), encoding="utf-8")
    with pytest.raises(SystemExit, match="not reconstructable"):
        recompute_report(path, B=100, seed_fallback=1)
