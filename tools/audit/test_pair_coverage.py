"""Hermetic pins for B4b pair coverage (§C classes + §F PC-13).

No engine, no replays: co-fire is fed in as synthetic :class:`Game` journals so
the pair arithmetic is pinned independently of what the corpus happens to do.
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE.parents[1], HERE, HERE / "audit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import detectors as D
import pair_coverage as PC
from branch_coverage import Game


def row(i: int, kind: str, subject: str, cause: str, verb: str, data=None) -> D.Row:
    return D.Row(i, i, kind, subject, cause, verb, data)


# ------------------------------------------------------------------ co-fire


def test_pair_key_is_order_independent():
    assert PC.pair_key("A", "B") == PC.pair_key("B", "A")
    assert PC.pair_key("A", "B") not in {"A + A", "B + B"}


def test_fired_names_follows_the_attribution_law():
    g = Game(
        "corpus:1",
        [
            row(0, "DAMAGE", "a", "a", "DEAL_DAMAGE"),  # subject
            row(1, "TAP_STATE", "b", "a", "TAP"),  # cause
            row(2, "ZONE_CHANGE", "x", "y", "MOVE_ZONE", ("c:1",)),  # data handle
            row(3, "DAMAGE", "z", "z", "DEAL_DAMAGE"),  # tag not in map
        ],
        {"a": "Alpha", "b": "Beta", "c:1": "Gamma", "z": "Zed"},
    )
    assert PC.fired_names(g) == {"Alpha", "Beta", "Gamma", "Zed"}


def test_co_fire_counts_shared_games_not_card_totals():
    g1 = Game("corpus:1", [row(0, "D", "a", "a", "V")], {"a": "Alpha", "b": "Beta"})
    g1.rows.append(row(1, "D", "b", "b", "V"))
    g2 = Game("corpus:2", [row(0, "D", "a", "a", "V")], {"a": "Alpha", "b": "Beta"})
    counts = PC.co_fire([g1, g2])
    assert counts[PC.pair_key("Alpha", "Beta")] == 1  # only g1 had both
    assert counts[PC.pair_key("Alpha", "Alpha")] == 0


def test_designed_pairs_reads_real_names_from_pack_files(tmp_path):
    (tmp_path / "p.json").write_text(
        '{"cards": [{"key": "a", "real": "Alpha"}, {"key": "b", "real": "Beta"}]}',
        encoding="utf-8",
    )
    (tmp_path / "q.json").write_text(
        '{"cards": [{"key": "a", "real": "Alpha"}, {"key": "s", "name": "Synth"}]}',
        encoding="utf-8",
    )
    designed = PC.designed_pairs(tmp_path)
    assert designed.get(PC.pair_key("Alpha", "Beta")) == ["p.json"]
    assert PC.pair_key("Alpha", "Synth") not in designed, "synthetic is not a pair"


# ------------------------------------------------------------------- matrix


def _bcs() -> dict:
    return {
        "cards": {
            "Alpha": {
                "bcs": 40,
                "handle": "alpha",
                "collision_flags": [],
                "primitives": {"p7_layers": 1, "p6_replacement": 0},
            },
            "Beta": {
                "bcs": 3,
                "handle": "beta",
                "collision_flags": [],
                "primitives": {"p7_layers": 2, "p6_replacement": 0},
            },
            "Gamma": {
                "bcs": 30,
                "handle": "gamma",
                "collision_flags": [],
                "primitives": {"p7_layers": 1, "p6_replacement": 0},
            },
        }
    }


def test_matrix_gates_on_one_high_end_and_zeroes_heat_when_tested():
    """pt_layers here: all three cards are layer-capable.

    Floor rule (2026-10-04): a pair is in scope when BCS >= T on ONE end, so
    Alpha(40)+Beta(3) qualifies while Beta+Gamma does not need both high.
    """
    key_ab = PC.pair_key("Alpha", "Beta")
    payload = PC.build_payload(
        _bcs(),
        cofire={key_ab: 4},  # Alpha+Beta tested by co-fire
        designed={},
        t=20,
        limit=10,
        games_n=1,
    )
    cls = payload["per_class"]["pt_layers"]
    pairs = {e["pair"] for e in cls["top_untested"]}
    assert cls["candidate_pairs"] == 3  # AB, AG, BG (one end >= 20 each)
    assert cls["tested"] == 1 and cls["untested"] == 2
    assert key_ab not in pairs, "a co-fired pair must not be a hole"
    assert PC.pair_key("Alpha", "Gamma") in pairs


def test_untested_heat_is_bcs_product_and_never_for_tested_pairs():
    payload = PC.build_payload(
        _bcs(),
        cofire={},
        designed={PC.pair_key("Alpha", "Gamma"): ["p.json"]},
        t=20,
        limit=10,
        games_n=0,
    )
    untested = {e["pair"]: e["heat"] for e in payload["untested_pairs"]}
    # pack-designed pair is tested -> heat 0 by §C's 1[untested] factor
    assert PC.pair_key("Alpha", "Gamma") not in untested
    assert untested[PC.pair_key("Alpha", "Beta")] == 40 * 3 * 1.0
    assert payload["totals"]["pairs_designed_in_packs"] == 1


def test_zero_tested_class_is_reported_by_name():
    payload = PC.build_payload(
        _bcs(), cofire={}, designed={}, t=20, limit=10, games_n=0
    )
    # nothing co-fired and no packs: every class is wholly untested
    zero = payload["totals"]["classes_with_zero_tested"]
    assert "pt_layers" in zero
    assert payload["totals"]["tested"] == 0
