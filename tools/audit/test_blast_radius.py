"""blast_radius.py's reading of two sides' replays (KNOWLEDGE/2026-11-18/215 §8 d, f): the games
that differ are listed (by digest, journal or event log), games per CPU-second compared, and each
differing game's first differing journal row shown with card names. Hermetic: synthetic replay
files, no game is played (the protocol's smoke run is reports/engine_wave_w0_2026-11-18)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import blast_radius as br


def _game(i: int, journal: str, cpu: float = 0.5) -> dict:
    return {"game": i, "digest": "d", "journal": journal, "events": "e", "outcome": "win", "turns": 9,
            "crash": None, "cpu": cpu}


def _side(tmp: Path, name: str, games: list[dict]) -> str:
    path = tmp / f"{name}.json"
    path.write_text(json.dumps({"M21": {"deckable": 280, "taken_out": [], "games": games}}))
    return str(path)


def test_compare_lists_the_games_that_differ_and_the_speed(tmp_path: Path) -> None:
    base = _side(tmp_path, "base", [_game(0, "j0"), _game(1, "j1")])
    branch = _side(tmp_path, "branch", [_game(0, "j0", cpu=0.6), _game(1, "jX", cpu=0.6)])
    listing = tmp_path / "differing.txt"
    out = br.compare(base, branch, str(listing))
    assert "identical digests 2, journals 1, event logs 2" in out
    assert "games that differ: 1 of 2" in out
    assert "base 2.00, branch 1.67 (-16.7%" in out
    assert listing.read_text() == "M21:1\n"


def test_first_rows_shows_the_first_differing_journal_row(tmp_path: Path) -> None:
    rows = ["(1, 'CAST', card:3)", "(2, 'DAMAGE', card:7, 3)", "(3, 'ZONE_CHANGE', card:7)"]
    names = {"card:3": "Shock", "card:7": "Bear"}
    base = {**_game(4, "j"), "rows": rows, "names": names}
    branch = {**_game(4, "k"), "rows": [*rows[:1], "(2, 'DAMAGE', card:7, 2)"], "names": names}
    out = br.first_rows(_side(tmp_path, "b", [base]), _side(tmp_path, "n", [branch]))
    assert out.splitlines()[0].startswith("M21:4: first differing row 1 of 3 (base) / 2 (branch)")
    assert "   same:   (1, 'CAST', card:3[Shock])" in out
    assert "   base:   (2, 'DAMAGE', card:7[Bear], 3)" in out and "   branch: (2, 'DAMAGE', card:7[Bear], 2)" in out
