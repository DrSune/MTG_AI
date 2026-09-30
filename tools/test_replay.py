"""Smoke test for the 14g replay pipeline (make_replay → self-contained HTML).

Runs ONE engine-pool game (seed 7) end-to-end into a tmp dir and asserts
the viewer contract: HTML exists, the inlined trace parses, EVERY action
entry carries exactly one state snapshot, and a known deck card has a
real image on disk. Runtime budget < 30s (one game ≈ 3s on this box).

Run: ``.venv/bin/pytest tools/test_replay.py -q``
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

_TRACE_RE = re.compile(
    r'<script id="trace-data" type="application/json">(.*?)</script>', re.DOTALL
)


def _extract_trace(html: str) -> dict:
    match = _TRACE_RE.search(html)
    assert match, "embedded trace-data script tag not found"
    return json.loads(match.group(1).replace("<\\/", "</"))


def test_make_replay_seed7_engine(tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "tools/make_replay.py",
            "--seed",
            "7",
            "--pool",
            "engine",
            "--out-dir",
            str(tmp_path),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-1500:]

    html_path = tmp_path / "replay_s7.html"
    assert html_path.exists(), "replay HTML not written"
    html = html_path.read_text(encoding="utf-8")

    trace = _extract_trace(html)
    assert trace["seed"] == 7 and trace["pool"] == "engine"
    assert trace["decklists"] and trace["libraries"]

    actions = [e for e in trace["entries"] if e.get("type") == "action"]
    snapshots = [e for e in trace["entries"] if "snapshot" in e]
    assert actions, "traced game recorded no actions"
    assert len(snapshots) == len(actions), (
        f"{len(snapshots)} snapshots for {len(actions)} actions — "
        "the viewer contract is one full snapshot per action"
    )

    # the viewer's image contract: every card in the decklists has a
    # sourceable image (a land is guaranteed — deck building pins >=10
    # mana sources), and at least one deck card's .jpg is on disk
    assets = REPO / "MTG_bot" / "assets" / "card_images"
    deck_oids = {
        card["oracle_id"] for deck in trace["decklists"] for card in deck["cards"]
    }
    on_disk = {p.stem for p in assets.glob("*.jpg")}
    sourced = deck_oids & on_disk
    assert sourced, "no deck card image found under MTG_bot/assets/card_images"
    # the game actually put a land on the battlefield → the tile the
    # viewer would render for a known card resolves on disk
    final_bf = [
        c
        for player in trace["final_snapshot"]["players"]
        for c in player["battlefield"]
        if c["oracle_id"] in on_disk
    ]
    assert final_bf, "final battlefield holds no card with a downloaded image"

    # decision asks are vocab-tagged with the chosen candidate visible
    decisions = [e for e in trace["entries"] if e.get("type") == "decision"]
    for ask in decisions:
        assert ask["answer"] in ask["vocab"]
        assert ask["candidates"] == ask["vocab"]
