"""The engine primer: generated from the compiled pools and gated on the owner's 99% target."""

from __future__ import annotations

import pytest

from MTG_bot.bench.masking import NameMasker
from MTG_bot.bench.primer import (
    attach_pack_evidence,
    census,
    component_of,
    coverage,
    render_primer,
)
from MTG_bot.bench.view import OracleIndex
from MTG_bot.core.ability_tree import FAnd, QConst


@pytest.fixture(scope="module")
def entries():
    found = census()
    attach_pack_evidence(found)
    return found


def test_structural_nodes_are_not_components() -> None:
    assert component_of(FAnd(())) is None
    assert component_of(QConst(1)) is None


def test_exercised_share_meets_the_owner_target(entries) -> None:
    # Owner, 2026-10-24: models should understand >= 99% of atomic-subcomponent scenarios. This is
    # a stated target for the instrument, not a strategy heuristic. A new card whose components
    # no passing pack exercises lowers the share; when it drops below the target, write the packs
    # coverage()['uncovered'] names.
    cov = coverage(entries)
    assert cov["exercised_occurrence_share"] >= 0.99, cov["uncovered"][:10]


def test_verified_is_never_inferred_from_exercise(entries) -> None:
    assert coverage(entries)["verified_occurrence_share"] is None


def test_the_primer_states_the_engine_simplifications(entries) -> None:
    text = render_primer(entries)
    assert "Mana pools do not empty" in text
    assert "verified" not in text.lower().replace("not exercised", "")


def test_the_masked_primer_leaks_no_card_name(entries) -> None:
    oracle = OracleIndex.for_sets("M21", "ZNR")
    masker = NameMasker(oracle.names, "test", keep=oracle.token_names)
    text = render_primer(entries, masker)
    assert masker.leaks(text) == []
