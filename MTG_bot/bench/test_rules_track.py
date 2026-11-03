"""Track R: every pack accounted for, readers exact, the §17 pairing holds, masking leaks nothing."""

from __future__ import annotations

import json

import pytest

from MTG_bot.bench import CANARY
from MTG_bot.bench.masking import NameMasker
from MTG_bot.bench.rules_track import (
    PACK_DIR,
    NullAnswerer,
    OracleAnswerer,
    build_items,
    score,
)
from MTG_bot.bench.view import OracleIndex


@pytest.fixture(scope="module")
def real():
    return build_items()


@pytest.fixture(scope="module")
def masked():
    return build_items(masked=True, salt="test")


def test_every_pack_is_an_item_or_a_named_exclusion(real) -> None:
    _, cov = real
    assert cov.items + sum(cov.excluded.values()) + len(cov.reader_mismatch) == cov.packs
    assert cov.items >= 300  # 312 on 2026-10-24; a falling count is lost coverage, not noise


def test_the_state_readers_reproduce_every_gold_value(real) -> None:
    # Replaying each pack and reading the state must give the engine-verified expectations exactly.
    # A mismatch is a reader bug that would corrupt gold, never something to skip quietly.
    assert real[1].reader_mismatch == []


def test_oracle_scores_one_and_the_null_floor_scores_zero_on_changed_keys(real) -> None:
    items, _ = real
    for item in items:
        assert score(item, OracleAnswerer().answer(item))["all_keys"] == 1.0
        null = score(item, NullAnswerer().answer(item))
        assert null["delta"] in (None, 0.0)
    assert sum(score(i, NullAnswerer().answer(i))["all_keys"] for i in items) > 0  # all-keys IS null-favourable


def test_prompts_never_show_pack_notes(real) -> None:
    items, _ = real
    # The probe is the note's first 40-character window that is not verbatim oracle text. An
    # activate step quotes its ability's oracle line on purpose, and a note may open by quoting that
    # same line (leafkin_avenger, renderable since B-49 taught ability_line to skip the cast
    # carrier). Such a match is card text, not a leaked note, so the probe moves to the next window.
    oracle = OracleIndex.for_sets("M21", "ZNR")
    card_text = [oracle.text(oid) for oid in oracle.cards]
    notes = {}
    for path in PACK_DIR.glob("*.json"):
        pack = json.loads(path.read_text())
        text = (pack.get("notes") or "") + (pack.get("note") or "")
        if len(text) > 40:
            windows = (text[i : i + 40] for i in range(0, len(text) - 39, 40))
            probe = next((w for w in windows if not any(w in t for t in card_text)), None)
            if probe is not None:
                notes[path.stem] = probe
    for item in items:
        if item.id in notes:
            assert notes[item.id] not in item.prompt


def test_masked_items_leak_no_card_name_and_carry_the_canary(masked) -> None:
    items, cov = masked
    oracle = OracleIndex.for_sets("M21", "ZNR")
    masker = NameMasker(oracle.names, "test", keep=oracle.token_names)
    assert cov.items > 0
    for item in items:
        assert masker.leaks(item.prompt) == [], item.id
        assert item.to_json()["canary"] == CANARY
