"""The scripted scenario packs as pytest cases.

The packs under ``tools/scenarios/`` are the executable rules-conformance suite: a small world,
one or two scripted engine actions, and the expected post-state. One test per pack makes a broken
pack a named red test in the default ``pytest MTG_bot`` run, so HEAD cannot break them unnoticed.

Each pack's set code comes from its own top-level ``"set"`` key, as ``run_scenarios.main`` reads
it; a pack without one runs on the M21 supply.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import pytest

from MTG_bot.core.executor.games import Supply, compile_supply, get_supply
from tools.run_scenarios import run_pack

PACK_DIR = Path(__file__).resolve().parents[2] / "tools" / "scenarios"
PACKS = sorted(PACK_DIR.glob("*.json"))
# Spec packs of verified cards (docs/PLAN_CARD_ONBOARDING.md gate G4), copied in by
# `tools/cards/cardtool.py verify`: tools/scenarios/cards/<SET>/<card>_<n>.json. They pin the
# printed behaviour of every verified card, so an engine change that breaks one fails here.
CARD_PACKS = sorted(PACK_DIR.glob("cards/*/*.json"))
# Packs of mapped cards not verified yet, played on their records as `cardtool runpack` plays
# them (unverified records applied): an engine fix's packs for the cards it fixes, kept here
# while the cards wait on blind re-verification (tools/scenarios/mapped/<SET>/). Once a card is
# verified, its packs move to cards/<SET>/.
MAPPED_PACKS = sorted(PACK_DIR.glob("mapped/*/*.json"))


def _set_code(path: Path) -> str:
    try:
        return str(json.loads(path.read_text()).get("set", "M21"))
    except (OSError, ValueError):
        return "M21"  # run_pack reports the malformed pack itself


def test_pack_directory_is_complete() -> None:
    # A shrinking pack directory is a silent coverage loss; 428 is a floor, not the count.
    assert len(PACKS) >= 428, f"only {len(PACKS)} packs in {PACK_DIR}"


@pytest.mark.parametrize("path", PACKS, ids=[p.stem for p in PACKS])
def test_pack(path: Path) -> None:
    failures = run_pack(path, get_supply("all", _set_code(path)))
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("path", CARD_PACKS, ids=[f"{p.parent.name}/{p.stem}" for p in CARD_PACKS])
def test_card_pack(path: Path) -> None:
    failures = run_pack(path, get_supply("all", _set_code(path)))
    assert not failures, "\n".join(failures)


@cache
def _mapped_supply(code: str) -> Supply:
    return compile_supply("all", code, require_verified=False)


@pytest.mark.parametrize("path", MAPPED_PACKS, ids=[f"mapped/{p.parent.name}/{p.stem}" for p in MAPPED_PACKS])
def test_mapped_pack(path: Path) -> None:
    failures = run_pack(path, _mapped_supply(_set_code(path)))
    assert not failures, "\n".join(failures)
