"""The scripted scenario packs as pytest cases (added 2026-10-24).

The 428 packs under ``tools/scenarios/`` are the executable rules-conformance suite: a small
world, one or two scripted engine actions, and the expected post-state. Until now they ran only
through ``tools/run_scenarios.py``, outside the documented ``pytest MTG_bot`` contract, so HEAD
could break them unnoticed. It did: the R0 Selector change left the runner calling the old API,
and only 265/428 passed until the fix was committed. One test per pack makes a broken pack a
named red test in the default run. The whole set costs about 1.3 s.

Each pack's set code comes from its own top-level ``"set"`` key, as ``run_scenarios.main``
reads it; packs without one ran on the M21 supply historically and still do.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from MTG_bot.core.executor.games import get_supply
from tools.run_scenarios import run_pack

PACK_DIR = Path(__file__).resolve().parents[2] / "tools" / "scenarios"
PACKS = sorted(PACK_DIR.glob("*.json"))
# Spec packs of verified cards (docs/PLAN_CARD_ONBOARDING.md gate G4), copied in by
# `tools/cards/cardtool.py verify`: tools/scenarios/cards/<SET>/<card>_<n>.json. They pin the
# printed behaviour of every verified card, so an engine change that breaks one fails here.
CARD_PACKS = sorted(PACK_DIR.glob("cards/*/*.json"))


def _set_code(path: Path) -> str:
    try:
        return str(json.loads(path.read_text()).get("set", "M21"))
    except (OSError, ValueError):
        return "M21"  # run_pack reports the malformed pack itself


def test_pack_directory_is_complete() -> None:
    # A shrinking pack directory is a silent coverage loss; 428 is the 2026-10-24 count.
    assert len(PACKS) >= 428, f"only {len(PACKS)} packs in {PACK_DIR}"


@pytest.mark.parametrize("path", PACKS, ids=[p.stem for p in PACKS])
def test_pack(path: Path) -> None:
    failures = run_pack(path, get_supply("all", _set_code(path)))
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("path", CARD_PACKS, ids=[f"{p.parent.name}/{p.stem}" for p in CARD_PACKS])
def test_card_pack(path: Path) -> None:
    failures = run_pack(path, get_supply("all", _set_code(path)))
    assert not failures, "\n".join(failures)
