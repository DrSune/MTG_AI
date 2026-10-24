"""Smoke test for the T5 Phase A atomics census tool.

Gates: the tool runs, the JSON parses, and the counts are internally
sane (tripwires at zero, tree lists consistent, and the independent
identity that every entity CHOOSE selector lands in exactly one bucket).
"""

from __future__ import annotations

import json
import pathlib

import atomics_census as ac

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOLDEN_DIR = ROOT / "MTG_bot" / "core" / "golden" / "M21"


def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def test_census_runs_and_json_is_sane(tmp_path, capsys, monkeypatch):
    report = ac.build()
    out = tmp_path / "atomics_census.json"
    out.write_text(json.dumps(report, indent=1))
    parsed = json.loads(out.read_text())  # json parses

    assert parsed["meta"]["golden_trees"] == len(list(GOLDEN_DIR.glob("*.json")))
    findings = parsed["findings"]
    sev_ok = {"critical", "high", "medium", "info"}
    for pat, f in findings.items():
        assert f["count"] >= 0, pat
        assert f["tree_count"] == len(f["trees"]), pat
        assert 0 <= f["tree_count"] <= parsed["meta"]["golden_trees"], pat
        assert f["severity"] in sev_ok, pat

    # tripwires: P1a MOVE merge + VerbClass partition must be clean
    assert findings["move_verb_leftover"]["count"] == 0
    assert findings["verb_outside_partition"]["count"] == 0
    assert findings["count_adhoc_bound_shape"]["count"] == 0
    assert findings["site_unknown_kind"]["count"] == 0

    # independence identity: every referent-free entity CHOOSE selector is
    # classified into exactly one of the seven CHOOSE buckets
    choose_total = 0
    for f in GOLDEN_DIR.glob("*.json"):
        for n in _walk(json.loads(f.read_text())):
            if (
                n.get("tag") == "Selector"
                and n["mode"]["name"] == "CHOOSE"
                and n.get("referent") is None
            ):
                choose_total += 1
    buckets = [
        "choose_silent_force_silent",
        "choose_silent_promotable",
        "choose_silent_cost_lane",
        "choose_silent_is_source_lane",
        "choose_up_to_any",
        "kofn_legacy_choose_multicount",
    ]
    assert sum(findings[b]["count"] for b in buckets) == choose_total
    # anaphoric CHOOSEs sit outside that total but must be counted
    assert findings["choose_referent_anaphoric"]["count"] >= 1

    # rewrite ledger present with effort grades
    assert any(e["effort"] in ("S", "M", "L") for e in parsed["rewrite_ledger"])
    # CLI path: prints the table and writes the census. Point it at tmp_path: writing the TRACKED
    # tools/audit/atomics_census.json from a test dirtied the tree on every run (2026-10-24).
    monkeypatch.setattr(ac, "OUT_PATH", tmp_path / "cli_atomics_census.json")
    ac.main()
    assert (tmp_path / "cli_atomics_census.json").exists()
    assert "REWRITE LEDGER" in capsys.readouterr().out
