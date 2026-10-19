"""Unit tests for the ZNR smoke tool's pure ledger-grouping logic."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from znr_engine_smoke import (
    crash_signature,
    group_crashes,
    report_prefix,
    repro_command,
)


def _row(seed: int, crash: dict | None, **kw: object) -> dict:
    return {
        "seed": seed,
        "turns": kw.get("turns", 5),
        "acts": kw.get("acts", 12),
        "crash": crash,
        "traceback": kw.get("traceback", ""),
    }


def _crash(exc: str = "ValueError", frame: str = "query.py:41 in pick") -> dict:
    return {
        "exc": exc,
        "message": "boom",
        "frame": frame,
        "turn": 7,
        "attempted": "Lightning Angel",
        "stack": ["some spell"],
        "recent_acts": ["a", "b"],
    }


def test_clean_rows_ignored() -> None:
    assert (
        group_crashes([_row(0, None), _row(1, None)], deck_pairs_seed=99, turn_cap=150)
        == {}
    )


def test_same_signature_collapses() -> None:
    rows = [_row(3, _crash()), _row(1, _crash()), _row(7, _crash(), acts=99)]
    groups = group_crashes(rows, deck_pairs_seed=99, turn_cap=150)
    assert len(groups) == 1
    g = groups["ValueError@query.py:41 in pick"]
    assert g["count"] == 3
    # seeds collected in ascending order, evidence from the FIRST (lowest)
    # seed so the group tells the smallest true story
    assert g["seeds"] == [1, 3, 7]
    assert g["step"] == 12


def test_distinct_frames_are_distinct_signatures() -> None:
    rows = [
        _row(0, _crash()),
        _row(1, _crash(frame="legality.py:88 in check")),
        _row(2, _crash(exc="KeyError")),
    ]
    groups = group_crashes(rows, deck_pairs_seed=99, turn_cap=150)
    assert len(groups) == 3


def test_repro_uses_lowest_seed_and_tool_surface() -> None:
    rows = [_row(9, _crash()), _row(2, _crash()), _row(4, _crash())]
    groups = group_crashes(rows, deck_pairs_seed=777, turn_cap=140)
    g = next(iter(groups.values()))
    assert g["repro"] == repro_command(2, 777, 140)
    assert "--repro 2" in g["repro"]
    assert "deck-pairs-seed 777" in g["repro"]
    assert "turn-cap 140" in g["repro"]
    # ZNR note: the repro must be THIS tool, never games.py --repro (wrong set)
    assert "znr_engine_smoke.py" in g["repro"]


def test_repro_carries_set_flag() -> None:
    assert "--set M21" in repro_command(2, 777, 140, "M21")
    rows = [_row(4, _crash())]
    groups = group_crashes(rows, deck_pairs_seed=777, turn_cap=140, set_code="M21")
    assert "--set M21" in next(iter(groups.values()))["repro"]
    # default remains ZNR (back-compat ledgers)
    groups_znr = group_crashes(rows, deck_pairs_seed=777, turn_cap=140)
    assert "--set ZNR" in next(iter(groups_znr.values()))["repro"]


def test_report_prefix_naming() -> None:
    assert report_prefix("ZNR") == "znr_engine_smoke"
    assert report_prefix("M21") == "m21_engine_smoke"
    assert report_prefix("znr") == "znr_engine_smoke"


def test_traceback_taken_from_first_crashing_row() -> None:
    rows = [
        _row(0, None),
        _row(1, _crash(), traceback="FULL TB"),
        _row(2, _crash(), traceback="other"),
    ]
    groups = group_crashes(rows, deck_pairs_seed=1, turn_cap=1)
    assert groups[crash_signature(_crash())]["traceback"] == "FULL TB"
