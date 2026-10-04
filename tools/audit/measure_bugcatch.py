"""BUGCATCH B5 — PC-11..PC-14 campaign metrics wired into one gate.

Design: KNOWLEDGE/2026-10-02/12-bugcatch-design.md §F.  This harness is the
acceptance instrument for the whole BUGCATCH campaign; it *computes* every
number fresh from the instruments on disk (bcs.json + live disk membership,
branch_coverage.json, pair_coverage.json) and from an in-process D1–D6 scan
of the 10 catalog seeds.  Nothing is hardcoded: the baseline rows you see on
first run are the current TRUE numbers, re-derived.

Gate policy (2026-10-05 B5 ruling, mirrors the design's B5 row):
* PC-11 and PC-14 GATE the exit code.  PC-11 passes iff the BCS >= T residue
  equals the ruled-deferral exception list in ``deferrals.json`` (every
  residue card not covered by a cited deferral fails).  PC-14 passes iff the
  anomaly scan (D1–D6 HITs + crashes) is 0.
* PC-12 and PC-13 are REPORT-ONLY until the B3/H hunts drain the DARK-branch
  and untested-pair queues — a below-target litness fraction must NOT fail
  the exit code.  They print PASS/FAIL against their targets, tagged
  (report-only).

House format (same as tools/measure_grammar.py): each PC is a
name/value/target/pass record; the run writes ``reports/bugcatch_<date>.json``
and prepends a dated headline section to KNOWLEDGE/NUMBERS.md.

``--deep`` additionally runs the N-game replay lane (default N=20, the
detectors.py defaults) — real engine games with full journal payloads, so
D1/D3/D4/D5/D6 run with data instead of catalog EXEMPTs.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import detectors  # same-package instrument; engine import stays deferred
import membership

BCS_JSON = HERE / "bcs.json"
BRANCH_JSON = HERE / "branch_coverage.json"
PAIR_JSON = HERE / "pair_coverage.json"
DEFERRALS_JSON = HERE / "deferrals.json"

PC12_TARGET = 0.90  # §F: corpus lit/declared >= 0.9
COMMAND = "python tools/audit/measure_bugcatch.py"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _report_date() -> str:
    """House convention (measure_grammar.py:418): local timezone calendar date."""
    return datetime.now().astimezone().date().isoformat()


# ---------------------------------------------------------------------------
# PC-11 — complexity census residue vs ruled deferrals


def measure_pc11(t: int) -> dict[str, Any]:
    bcs = _load(BCS_JSON)
    bcs, _block = membership.refresh(bcs, membership.disk_membership())
    raw = membership.pc11(bcs, t)
    deferrals = _load(DEFERRALS_JSON)
    deferred = {d["card"] for d in deferrals["deferrals"]}
    ungated = sorted(set(raw["residue_names"]) - deferred)
    covered_by_deferral = sorted(set(raw["residue_names"]) & deferred)
    return {
        "name": "complexity_census",
        "target": f"residue at BCS>={t} == deferrals.json exception list (ungated 0)",
        "pass": not ungated,
        "gated": True,
        "t": t,
        "value": raw["residue"],
        "cards_at_or_above_t": raw["cards_at_or_above_t"],
        "covered_by_packs_or_suspects": raw["covered"],
        "residue_names": raw["residue_names"],
        "residue_deferred_cited": covered_by_deferral,
        "residue_ungated": ungated,
        "deferral_law": deferrals.get("law", ""),
    }


# ---------------------------------------------------------------------------
# PC-12 — branch litness (report-only)


def measure_pc12(t: int) -> dict[str, Any]:
    bc = _load(BRANCH_JSON)
    totals = bc["totals"]
    declared = int(totals["branches_declared"])
    lit = int(totals["LIT"])
    fraction = lit / declared if declared else 0.0
    bcs_cards = _load(BCS_JSON)["cards"]
    dark_high = sorted(
        (
            {
                "branch_id": br["branch_id"],
                "card": br["card"],
                "kind": br["kind"],
                "bcs": int(bcs_cards.get(br["card"], {}).get("bcs", 0)),
                "heat": br.get("heat"),
            }
            for br in bc["branches"]
            if br["status"] == "DARK"
            and int(bcs_cards.get(br["card"], {}).get("bcs", 0)) >= t
        ),
        key=lambda r: (-r["bcs"], r["branch_id"]),
    )
    return {
        "name": "branch_coverage",
        "target": f"lit/declared >= {PC12_TARGET:.2f}; zero DARK on BCS>={t}",
        "pass": fraction >= PC12_TARGET and not dark_high,
        "gated": False,  # report-only until B3/H queues drain
        "value": round(fraction, 4),
        "lit": lit,
        "declared": declared,
        "dark": int(totals["DARK"]),
        "unmatchable": int(totals["UNMATCHABLE"]),
        "dark_on_high_bcs": dark_high,
    }


# ---------------------------------------------------------------------------
# PC-13 — pair coverage per collision class (report-only)


def measure_pc13() -> dict[str, Any]:
    pc = _load(PAIR_JSON)
    totals = pc["totals"]
    candidate = int(totals["candidate_pairs"])
    tested = int(totals["tested"])
    per_class = {
        cls: {
            "tested": int(rec["tested"]),
            "candidate_pairs": int(rec["candidate_pairs"]),
            "coverage_pct": float(rec["coverage_pct"]),
        }
        for cls, rec in pc["per_class"].items()
    }
    return {
        "name": "interaction_coverage",
        "target": "every collision-class pair (both ends in class, BCS>=T on one "
        "end) tested — report-only until B4 splices land",
        "pass": False,  # §F full-coverage target not yet attainable; report-only
        "gated": False,
        "value": round(tested / candidate, 4) if candidate else 0.0,
        "tested": tested,
        "candidate_pairs": candidate,
        "per_class": per_class,
        "classes_with_zero_tested": totals["classes_with_zero_tested"],
        "co_fire_pairs": int(totals["pairs_co_fired_in_corpus"]),
        "designed_pair_packs": int(totals["pairs_designed_in_packs"]),
    }


# ---------------------------------------------------------------------------
# PC-14 — D1–D6 anomaly scan (gated)


def measure_pc14(
    deep: bool, seeds: int, pool: str, deck_pairs_seed: int, turns: int
) -> dict[str, Any]:
    lanes: dict[str, Any] = {}

    t0 = time.perf_counter()
    catalog_games = detectors.load_catalog()
    catalog_scan = detectors.scan(catalog_games, "catalog")
    catalog_sum = detectors.summarize(catalog_scan)
    catalog_crashes = sum(1 for r in catalog_scan.values() if r["crash"])
    lanes["catalog"] = {
        "seeds": len(catalog_scan),
        "seconds": round(time.perf_counter() - t0, 2),
        "per_detector": catalog_sum["per_detector"],
        "hits": len(catalog_sum["all_hits"]),
        "crashes": catalog_crashes,
        "hit_detail": catalog_sum["all_hits"],
    }

    if deep:
        t0 = time.perf_counter()
        games = {}
        for seed in range(seeds):
            games[str(seed)] = detectors.replay_game(seed, pool, deck_pairs_seed, turns)
        replay_scan = detectors.scan(games, "replay")
        replay_sum = detectors.summarize(replay_scan)
        lanes["replay"] = {
            "seeds": seeds,
            "seconds": round(time.perf_counter() - t0, 1),
            "pool": pool,
            "deck_pairs_seed": deck_pairs_seed,
            "turn_cap": turns,
            "per_detector": replay_sum["per_detector"],
            "hits": len(replay_sum["all_hits"]),
            "crashes": sum(1 for r in replay_scan.values() if r["crash"]),
            "hit_detail": replay_sum["all_hits"],
        }

    anomalies = sum(l["hits"] + l["crashes"] for l in lanes.values())
    return {
        "name": "anomaly_scan",
        "target": "0 D1–D6 anomalies (HITs + crashes) over the stress lanes",
        "pass": anomalies == 0,
        "gated": True,
        "value": anomalies,
        "lanes_run": sorted(lanes),
        "lanes": lanes,
    }


# ---------------------------------------------------------------------------
# NUMBERS.md (house mechanism, mirrors measure_grammar._append_numbers_md)


def _append_numbers_md(path: Path, date: str, pcs: dict[str, Any], deep: bool) -> None:
    p11, p12, p13, p14 = pcs["PC-11"], pcs["PC-12"], pcs["PC-13"], pcs["PC-14"]
    rows = [
        "| Number | Value | Command | Notes |",
        "|---|---|---|---|",
        (
            f"| PC-11 residue @ BCS>={p11['t']} | **{p11['value']} "
            f"({len(p11['residue_ungated'])} ungated)** | `{COMMAND}` | "
            f"{p11['cards_at_or_above_t']} cards at/above T; "
            f"{p11['covered_by_packs_or_suspects']} in packs/suspects; deferred-by-rule: "
            f"{', '.join(p11['residue_deferred_cited']) or 'none'} — "
            f"{'PASS' if p11['pass'] else 'FAIL'} (GATED) |"
        ),
        (
            f"| PC-12 branch litness | **{p12['value']:.4f}** "
            f"({p12['lit']}/{p12['declared']} LIT; {p12['dark']} DARK) | `{COMMAND}` | "
            f"target >= {PC12_TARGET:.2f} — {'PASS' if p12['pass'] else 'FAIL'} "
            f"(report-only); {len(p12['dark_on_high_bcs'])} DARK on BCS>=T cards |"
        ),
        (
            f"| PC-13 pair coverage | **{p13['value']:.4f}** "
            f"({p13['tested']}/{p13['candidate_pairs']}) | `{COMMAND}` | "
            f"{len(p13['per_class'])} collision classes; "
            f"{len(p13['classes_with_zero_tested'])} zero-tested classes; "
            f"report-only until B4 splices land |"
        ),
        (
            f"| PC-14 anomalies | **{p14['value']}** over "
            f"{' + '.join(p14['lanes_run'])} lane(s) | "
            f"`{COMMAND}{' --deep' if deep else ''}` | D1–D6; target 0 — "
            f"{'PASS' if p14['pass'] else 'FAIL'} (GATED) |"
        ),
    ]
    section = (
        f"## {date} (B5 — BUGCATCH campaign metrics PC-11..PC-14)\n\n"
        + "\n".join(rows)
        + "\n\n"
    )
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    insert_at = next(i for i, line in enumerate(lines) if line.startswith("## "))
    lines[insert_at:insert_at] = section.split("\n")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BUGCATCH B5 PC-11..PC-14 gate")
    ap.add_argument(
        "--t", type=int, default=membership.T_DEFAULT, help="PC-11 BCS floor"
    )
    ap.add_argument("--deep", action="store_true", help="add the N-game replay lane")
    ap.add_argument("--seeds", type=int, default=20, help="--deep replay game count")
    ap.add_argument("--pool", default="all")
    ap.add_argument("--deck-pairs-seed", type=int, default=1409)
    ap.add_argument("--turns", type=int, default=60)
    args = ap.parse_args(argv)

    pcs = {
        "PC-11": measure_pc11(args.t),
        "PC-12": measure_pc12(args.t),
        "PC-13": measure_pc13(),
        "PC-14": measure_pc14(
            args.deep, args.seeds, args.pool, args.deck_pairs_seed, args.turns
        ),
    }
    gate_ok = all(p["pass"] for p in pcs.values() if p["gated"])

    # -- human table ----------------------------------------------------------
    p11, p12, p13, p14 = (pcs[k] for k in ("PC-11", "PC-12", "PC-13", "PC-14"))

    def verdict(p: dict[str, Any]) -> str:
        return ("PASS" if p["pass"] else "FAIL") + (
            " (GATED)" if p["gated"] else " (report-only)"
        )

    print(
        f"PC-11 residue @ BCS>={p11['t']}     {p11['value']} total / "
        f"{len(p11['residue_ungated'])} ungated  "
        f"({p11['covered_by_packs_or_suspects']}/{p11['cards_at_or_above_t']} covered; "
        f"deferred: {', '.join(p11['residue_deferred_cited']) or 'none'})  "
        f"target ungated 0  {verdict(p11)}"
    )
    print(
        f"PC-12 branch litness          {p12['value']:.4f}  "
        f"({p12['lit']}/{p12['declared']} LIT, {p12['dark']} DARK, "
        f"{p12['unmatchable']} UNMATCHABLE)  target >= {PC12_TARGET:.2f}  {verdict(p12)}"
    )
    for d in p12["dark_on_high_bcs"]:
        print(
            f"      DARK-on-highBCS: {d['branch_id']}  (BCS {d['bcs']}, heat {d['heat']})"
        )
    print(
        f"PC-13 pair coverage           {p13['value']:.4f}  "
        f"({p13['tested']}/{p13['candidate_pairs']} pairs, "
        f"{len(p13['classes_with_zero_tested'])} zero-tested classes)  {verdict(p13)}"
    )
    for cls, rec in sorted(
        p13["per_class"].items(), key=lambda kv: -kv[1]["coverage_pct"]
    ):
        print(
            f"      {cls:<18} {rec['tested']:>5}/{rec['candidate_pairs']:<5} "
            f"{rec['coverage_pct']:6.2f}%"
        )
    for lane in p14["lanes_run"]:
        l = p14["lanes"][lane]
        det = "  ".join(
            f"{name}: {v.get('HIT', 0)}HIT/{v.get('EXEMPT', 0)}EXEMPT"
            for name, v in sorted(l["per_detector"].items())
        )
        print(
            f"PC-14 anomalies [{lane:<7}]   hits={l['hits']} crashes={l['crashes']} "
            f"({l['seeds']} seeds, {l['seconds']}s)  {det}"
        )
    print(
        f"PC-14 gate total              {p14['value']} anomalies  "
        f"target 0  {verdict(p14)}"
    )

    # -- report json + NUMBERS row (house format) -----------------------------
    date = _report_date()
    reports_dir = REPO / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"bugcatch_{date}.json"
    report_path.write_text(
        json.dumps(
            {
                "generated": datetime.now(UTC).isoformat(timespec="seconds"),
                "command": COMMAND + (" --deep" if args.deep else ""),
                "design": "KNOWLEDGE/2026-10-02/12-bugcatch-design.md §F",
                "gate_policy": "exit 0 iff PC-11 ungated residue == 0 and PC-14 "
                "anomalies == 0; PC-12/PC-13 report-only until B3/B4 queues drain",
                "gate": "PASS" if gate_ok else "FAIL",
                "pcs": pcs,
            },
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    _append_numbers_md(REPO / "KNOWLEDGE" / "NUMBERS.md", date, pcs, args.deep)
    print(f"report                          {report_path.relative_to(REPO)}")
    print(f"NUMBERS.md                      row appended ({date})")

    if not gate_ok:
        failed = [k for k, p in pcs.items() if p["gated"] and not p["pass"]]
        print(f"GATE FAIL: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("GATE PASS (PC-11 + PC-14; PC-12/PC-13 report-only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
