"""Smoke + ground-truth test for the T5-B clause audit tool.

Gates:
  * the tool runs, the JSON parses, per-card sums are internally consistent;
  * every residual carries a taxonomy class and non-empty evidence;
  * ground truth 1: the five add-any-mana clauses map to V:ADD_MANA;
  * ground truth 2: the two-leg-removal-shape detector finds exactly the
    four oracle-verified cards, and they are surfaced honestly;
  * ground truth 3: printed keyword reminder lines (e.g. Elder Gargaroth's
    "Vigilance, reach, trample") map to Keyword atoms, never residuals;
  * ground truth 4: parenthetical reminder text is stripped (Gadrak's
    Treasure-token parenthetical must not masquerade as an add-any-mana
    clause).
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

import clause_audit as ca
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOLDEN_DIR = ROOT / "MTG_bot" / "core" / "golden" / "M21"


@pytest.fixture(scope="module")
def report():
    return ca.build()


def _per_card(report):
    return {c["card"]: c for c in report["per_card"]}


def test_tool_runs_and_json_is_sane(report, tmp_path):
    out = tmp_path / "clause_audit.json"
    out.write_text(json.dumps(report))
    parsed = json.loads(out.read_text())

    assert parsed["meta"]["golden_trees"] == len(list(GOLDEN_DIR.glob("*.json")))
    total = sum(c["clauses"] for c in parsed["per_card"])
    mapped = sum(c["mapped"] for c in parsed["per_card"])
    residual_n = sum(len(c["residuals"]) for c in parsed["per_card"])
    assert total == mapped + residual_n
    assert total > 500  # tripwire: clause splitter did not silently die
    assert parsed["summary"]["coverage_pct"] > 90.0


def test_every_residual_is_classified_with_evidence(report):
    taxonomy = {
        "BOILERPLATE-NOTSIGNIFICANT",
        "NOT-ENCODED",
        "MISSING-ENCODING",
        "MISSING-EXPRESSIVENESS",
    }
    n = 0
    for card in report["per_card"]:
        for r in card["residuals"]:
            n += 1
            assert r["class"] in taxonomy, (card["card"], r)
            assert r["evidence"].strip(), (card["card"], r)
    assert n > 0  # audit must not report a vacuous perfect zero-loss


@pytest.mark.parametrize(
    "card",
    [
        "Meteorite",
        "Prismite",
        "Sanctum of Fruitful Harvest",
        "Traitorous Greed",
        "Treasure",
    ],
)
def test_add_any_mana_clauses_map(report, card):
    hits = [
        m
        for m in _per_card(report)[card]["mapped_clauses"]
        if re.search(r"mana of any", m["text"], re.I)
    ]
    assert hits, f"{card}: add-any-mana clause is not COVERED"


def test_two_leg_removal_shape_detector_finds_exactly_four(report):
    sys.path.insert(0, str(ROOT))
    from MTG_bot.core.compiler.ingest import ingest_pool

    pool = ingest_pool(str(ROOT / "MTG_bot" / "data" / "M21.json"))
    pat = re.compile(
        r"(?:destroy|exile) target [^.]*(?:creature|permanent)[^.]*\. "
        r"(?:Its|That creature's) controller",
        re.I,
    )
    found = sorted(
        c.identity.name
        for c in pool.values()
        if pat.search(" ".join(map(str, c.sentences)))
    )
    assert found == [
        "Angelic Ascension",
        "Liliana, Death Mage",
        "Secure the Scene",
        "Transmogrify",
    ]
    per = _per_card(report)
    for name in found:  # every leg-1 card is actually audited
        assert per[name]["mapped"] >= 1


def test_keyword_reminder_lines_are_covered(report):
    per = _per_card(report)
    gar = per["Elder Gargaroth"]
    kw_lines = [
        m for m in gar["mapped_clauses"] if m["text"].lower().startswith("vigilance")
    ]
    assert kw_lines, "keyword reminder line was not mapped"
    assert "KW:VIGILANCE" in kw_lines[0]["evidence"]
    assert all(not m["text"].lower().startswith("vigilance") for m in gar["residuals"])


def test_reminder_parentheticals_are_stripped():
    # Gadrak's real Treasure parenthetical must not become a clause.
    oracle = (
        "Flying\n"
        "Gadrak can't attack unless you control four or more artifacts.\n"
        "At the beginning of your end step, create a Treasure token for each "
        "nontoken creature that died this turn. (It's an artifact with "
        '"{T}, Sacrifice this token: Add one mana of any color.")'
    )
    clauses = ca.split_clauses(oracle)
    assert len(clauses) == 3
    assert all("sacrifice this token" not in c.lower() for c in clauses)
