"""tools/cards/respond.py on a few cards: a removed target or source never crashes the engine."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import respond
from probe import Probe

from MTG_bot.core.executor.games import get_supply


def test_targets_and_sources_removed_in_response() -> None:
    """Brash Taunter's fight with the Taunter gone (it raised until 2026-11-11), a spell whose
    target leaves (Eliminate) and a two-target ability (Garruk, Savage Herald's -2): every case
    resolves cleanly."""
    supply = get_supply("all", "M21")
    by_name = {supply.metas[o].name: o for o in supply.playable_engine_ids}
    for name in ("Brash Taunter", "Eliminate", "Garruk, Savage Herald"):
        runs, found = respond.card_findings(Probe(supply, "M21", by_name[name]))
        assert runs > 0, name
        assert found == [], found
