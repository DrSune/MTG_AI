"""Phase-1 grammar measurement harness (task T5).

Measures PC-1..PC-10 for a card pool against the pre-registered targets in
KNOWLEDGE/2026-09-14/02-phase1-plan.md, writes ``reports/grammar_<date>.json``,
appends the dated headline rows to KNOWLEDGE/NUMBERS.md, and prints a human
summary table.

Usage:
    python tools/measure_grammar.py [--set M21] [--runs 3] [--refresh-goldens]
                                    [--with-engine-flags]

Exit code: 0 when every evaluated pre-registered target passes, 1 when any
target fails.  PC-7 is reported as ``pending_executor`` (deferred, not a
failure) until T6 ships ``core/executor.py``.  A failed target is a real
finding — the report is written either way and never fudges a denominator.

PC-4 is measured **verify-only by default**: the fresh compile is
byte-compared against the committed, VCS-tracked golden baseline under
``MTG_bot/core/golden/`` and the harness never rewrites goldens.  A
missing or drifted golden file is reported as a diff, never silently
repaired.  ``--refresh-goldens`` is the explicit re-baselining action
(full regenerate before verify); the report JSON then notes
``"goldens": "refreshed"`` instead of ``"goldens": "verified"``.
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import platform
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from MTG_bot.core.compiler.compiler import compile_pool
from MTG_bot.core.compiler.coverage import (
    PINNED_ENTRIES,
    PINNED_SENTENCES,
    PINNED_SENTENCES_UNIQUE,
    build_full_registry,
    check_pinned_denominators,
    measure_pool,
)
from MTG_bot.core.compiler.golden import (
    fingerprint_multiset,
    verify_goldens,
    write_goldens,
)
from MTG_bot.core.compiler.ingest import RawCard, ingest_pool
from MTG_bot.core.identity import CardIdentity

# PC-10 planted unknown fragment (single sentence; no template matches it).
PLANTED_UNPARSED = "Nobody understands this."


# ---------------------------------------------------------------------------
# 12e engine-support pass (only with --with-engine-flags)
# ---------------------------------------------------------------------------


def _engine_support(pool, registry) -> dict:
    """Second compile_pool pass gated on the executor's real dispatch set.

    ``legality.engine_supported`` is an AND-fold over every compiled Atom:
    a card is engine-supported iff every atom verb is in
    ``SUPPORTED_VERBS_V2`` (compiler.py lines 1459-1472; ``supported_verbs
    is None`` short-circuits to the template's True stamp).  A card carrying
    a CAST atom is recorded as proof the fold is load-bearing.
    """
    from MTG_bot.core.ability_tree import Atom, SpellAbility, walk
    from MTG_bot.core.executor import SUPPORTED_VERBS_V2

    gated = compile_pool(pool, registry, supported_verbs=set(SUPPORTED_VERBS_V2))
    supported = 0
    flip: dict | None = None
    flip_rank = -1
    for result in gated.results.values():
        if result.legality.engine_supported:
            supported += 1
            continue
        offenders = sorted(
            {
                node.verb.name
                for node in walk(result.card)
                if isinstance(node, Atom) and node.verb not in SUPPORTED_VERBS_V2
            }
        )
        if not offenders:
            continue
        spell_only = bool(result.card.abilities) and all(
            isinstance(a, SpellAbility) for a in result.card.abilities
        )
        # Prefer a card whose gap is a CAST atom, then a SpellAbility-only one.
        rank = 2 * int("CAST" in offenders) + int(spell_only)
        if rank > flip_rank:
            flip_rank = rank
            flip = {
                "card": result.card.name,
                "spell_ability_only": spell_only,
                "default_engine_supported": True,
                "gated_engine_supported": False,
                "offending_verbs": offenders,
            }
    return {
        "engine_supported_cards": supported,
        "of_total": len(gated.results),
        "supported_verbs": sorted(v.name for v in SUPPORTED_VERBS_V2),
        "flip_proof": flip,
    }


# ---------------------------------------------------------------------------
# PC-10 synthetic pool (in-memory only — never written to disk)
# ---------------------------------------------------------------------------


def _synthetic_raw(oid: str, name: str, sentences: tuple[str, ...]) -> RawCard:
    return RawCard(
        identity=CardIdentity(oracle_id=oid, name=name),
        type_line="Instant",
        types=("Instant",),
        subtypes=(),
        supertypes=(),
        colors=(),
        color_identity=frozenset(),
        mana_cost_raw=None,
        mana_value=0,
        power_raw=None,
        toughness_raw=None,
        loyalty_raw=None,
        keywords=(),
        sentences=sentences,
        layout="normal",
        is_token=False,
        is_emblem=False,
        token_name_refs=(),
        related_names=(),
    )


def _pc10_null_test(registry) -> dict:
    """Instrument null test: one fully-parseable card (100%) and one with a
    planted unknown fragment (0%, exact unparsed queue)."""
    good = _synthetic_raw(
        "00000000-0000-0000-0000-000000000001", "Null Good", ("Draw a card.",)
    )
    bad = _synthetic_raw(
        "00000000-0000-0000-0000-000000000002", "Null Bad", (PLANTED_UNPARSED,)
    )
    good_report = measure_pool({good.identity.oracle_id: good}, registry, "null-good")
    bad_report = measure_pool({bad.identity.oracle_id: bad}, registry, "null-bad")

    good_full = good_report.pc1_card_coverage == 1.0 and not good_report.unparsed_queue
    bad_zero = bad_report.pc1_card_coverage == 0.0
    exact = (
        len(bad_report.unparsed_queue) == 1
        and bad_report.unparsed_queue[0].sentence == PLANTED_UNPARSED
    )
    return {
        "name": "instrument_null_test",
        "good_card_coverage": good_report.pc1_card_coverage,
        "bad_card_coverage": bad_report.pc1_card_coverage,
        "bad_unparsed_sentence": (
            bad_report.unparsed_queue[0].sentence if bad_report.unparsed_queue else None
        ),
        "target": "100% / 0% respectively, unparsed queue exact",
        "pass": good_full and bad_zero and exact,
    }


# ---------------------------------------------------------------------------
# Latency + determinism
# ---------------------------------------------------------------------------


def _p99_nearest_rank(values: list[float]) -> float:
    """p99 by nearest-rank (ceil(0.99*n)-th smallest)."""
    ordered = sorted(values)
    rank = max(1, math.ceil(0.99 * len(ordered)))
    return ordered[rank - 1]


def _latency_and_determinism(pool, registry, runs: int) -> dict:
    """Run >= 3 full pool compilations; per-card p99 latency (PC-5) and
    fingerprint multisets from two independent runs (PC-9)."""
    per_card_ms: list[float] = []
    multisets = []
    entries = len(pool)
    for _ in range(runs):
        start = time.perf_counter()
        compile_pool(pool, registry)
        per_card_ms.append((time.perf_counter() - start) * 1000.0 / entries)
    # Two independent compilations (first and last run) for PC-9.
    multisets.append(fingerprint_multiset(pool, registry))
    multisets.append(fingerprint_multiset(pool, registry))
    p99_ms = _p99_nearest_rank(per_card_ms)
    deterministic = multisets[0] == multisets[1]
    return {
        "p99_ms_per_card": round(p99_ms, 3),
        "runs": runs,
        "per_card_ms": [round(v, 3) for v in per_card_ms],
        "deterministic": deterministic,
    }


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------


def _git_head() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
        return out.stdout.strip() if out.returncode == 0 else "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _append_numbers_md(
    path: Path,
    date: str,
    pcs: dict,
    golden_files: int,
    diffs: list[str],
    golden_mode: str,
    engine: dict | None = None,
) -> None:
    """Insert a new dated section at the top of NUMBERS.md, above the
    newest existing section."""
    rows = [
        "| Number | Value | Command | Notes |",
        "|---|---|---|---|",
        f"| PC-1 card_coverage | **{pcs['PC-1']['value']:.4f}** ({pcs['PC-1']['cards_zero_unparsed']}/{pcs['PC-1']['denominator']}) | `python tools/measure_grammar.py --set M21` | target >= 0.90 / stretch >= 0.95 — {'PASS' if pcs['PC-1']['pass'] else 'FAIL'} |",
        f"| PC-2 sentence_coverage | **{pcs['PC-2']['value']:.4f}** ({pcs['PC-2']['sentences_matched']}/{pcs['PC-2']['denominator']}) | `python tools/measure_grammar.py --set M21` | target >= 0.95 / stretch >= 0.98 — {'PASS' if pcs['PC-2']['pass'] else 'FAIL'} |",
        f"| PC-3 ambiguity | **{pcs['PC-3']['value']}** entries | `python tools/measure_grammar.py --set M21` | target 0 — {'PASS' if pcs['PC-3']['pass'] else 'FAIL'} |",
        f"| PC-4 golden_stability | **{len(diffs)} diffs** ({golden_files} files, {golden_mode}) | `python tools/measure_grammar.py --set M21` | target 0 — {'PASS' if pcs['PC-4']['pass'] else 'FAIL'} |",
        f"| PC-5 compile_latency p99 | **{pcs['PC-5']['value']} ms/card** ({pcs['PC-5']['runs']} runs) | `python tools/measure_grammar.py --set M21` | target < 50 / stretch < 20 — {'PASS' if pcs['PC-5']['pass'] else 'FAIL'} |",
        f"| PC-6 vocabulary_health | orphans **{pcs['PC-6']['orphan_verbs']['value']}** / max share **{pcs['PC-6']['max_verb_share']['value']:.4f}** ({pcs['PC-6']['max_share_verb']}) | `python tools/measure_grammar.py --set M21` | target orphans 0 + max share < 0.20 — {'PASS' if pcs['PC-6']['pass'] else 'FAIL'} |",
        f"| PC-7 executor_coverage | **{pcs['PC-7']['status']}** | `python tools/measure_grammar.py --set M21` | deferred to T6 (core/executor.py) — not evaluated |",
        f"| PC-8 targetable_fraction | **{pcs['PC-8']['value']:.4f}** ({pcs['PC-8']['targetable_entries']}/{pcs['PC-8']['denominator']}) | `python tools/measure_grammar.py --set M21` | target >= 0.40 / stretch >= 0.50 — {'PASS' if pcs['PC-8']['pass'] else 'FAIL'} |",
        f"| PC-9 determinism | **{'stable' if pcs['PC-9']['pass'] else 'UNSTABLE'}** | `python tools/measure_grammar.py --set M21` | 2 independent compilations, identical fingerprint multiset |",
        f"| PC-10 null_test | **{pcs['PC-10']['good_card_coverage']:.0%} / {pcs['PC-10']['bad_card_coverage']:.0%}**, unparsed exact | `python tools/measure_grammar.py --set M21` | synthetic in-memory cards — {'PASS' if pcs['PC-10']['pass'] else 'FAIL'} |",
    ]
    if engine is not None:
        rows.append(
            f"| PC-7 engine_supported_cards | **{engine['engine_supported_cards']}/{engine['of_total']}** ({engine['engine_supported_cards'] / engine['of_total']:.4f}) | `python tools/measure_grammar.py --with-engine-flags` | T6 executor dispatch over {len(engine['supported_verbs'])} verbs (SUPPORTED_VERBS_V2) — honest flag, not a target |"
        )
    section = (
        f"## {date} (T5 — Phase-1 grammar measurement harness)\n\n"
        + "\n".join(rows)
        + "\n\n"
    )
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    insert_at = next(i for i, line in enumerate(lines) if line.startswith("## "))
    lines[insert_at:insert_at] = section.split("\n")
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", default="M21", help="pool set code (default M21)")
    parser.add_argument(
        "--runs", type=int, default=3, help="pool compilations for PC-5 (>= 3)"
    )
    parser.add_argument(
        "--refresh-goldens",
        action="store_true",
        help="explicit re-baselining: (re)write every golden file before "
        "verify (default: verify-only against the committed baseline)",
    )
    parser.add_argument(
        "--with-engine-flags",
        action="store_true",
        help="12e: run a second compile_pool pass gated on "
        "SUPPORTED_VERBS_V2 and report the honest engine_supported card "
        "count (adds an 'engine_support' field to the report JSON; "
        "coverage/golden behavior is otherwise unchanged)",
    )
    args = parser.parse_args(argv)
    if args.runs < 3:
        parser.error("--runs must be >= 3 (p99 needs a distribution)")

    set_name = args.set
    pool_path = REPO / "MTG_bot" / "data" / f"{set_name}.json"
    if not pool_path.exists():
        print(f"error: pool file not found: {pool_path}", file=sys.stderr)
        return 2

    pool = ingest_pool(pool_path)
    if set_name == "M21":
        check_pinned_denominators(pool)
    registry = build_full_registry()

    report = measure_pool(pool, registry, set_name)

    golden_dir = REPO / "MTG_bot" / "core" / "golden" / set_name
    golden_mode = "refreshed" if args.refresh_goldens else "verified"
    if args.refresh_goldens:
        # Explicit re-baseline: full regenerate, then verify what was written.
        golden_files = write_goldens(pool, registry, set_name)
        golden_diffs = verify_goldens(pool, registry, set_name)
    else:
        # Default measurement path: read-only verify against the committed
        # (VCS-tracked) baseline; nothing is written, ever.
        golden_diffs = verify_goldens(pool, registry, set_name)
        golden_files = (
            len(list(golden_dir.glob("*.json"))) if golden_dir.is_dir() else 0
        )

    latency = _latency_and_determinism(pool, registry, args.runs)
    pc10 = _pc10_null_test(registry)
    engine = _engine_support(pool, registry) if args.with_engine_flags else None

    # -- per-PC target evaluation -------------------------------------------
    pcs: dict = {
        "PC-1": {
            "name": "card_coverage",
            "cards_zero_unparsed": report.cards_zero_unparsed,
            "denominator": report.entry_count,
            "value": round(report.pc1_card_coverage, 6),
            "target": ">=0.90",
            "stretch": ">=0.95",
            "pass": report.pc1_card_coverage >= 0.90,
        },
        "PC-2": {
            "name": "sentence_coverage",
            "sentences_matched": report.sentences_matched,
            "denominator": report.sentence_total,
            "value": round(report.pc2_sentence_coverage, 6),
            "target": ">=0.95",
            "stretch": ">=0.98",
            "pass": report.pc2_sentence_coverage >= 0.95,
        },
        "PC-3": {
            "name": "ambiguity",
            "value": report.pc3_ambiguous_entries,
            "target": "0",
            "pass": report.pc3_ambiguous_entries == 0,
            "entries": [e.to_json() for e in report.ambiguous_entries],
        },
        "PC-4": {
            "name": "golden_stability",
            "value": len(golden_diffs),
            "target": "0",
            "pass": not golden_diffs,
            "diffs": golden_diffs,
        },
        "PC-5": {
            "name": "compile_latency_p99_ms_per_card",
            "value": latency["p99_ms_per_card"],
            "target": "<50",
            "stretch": "<20",
            "pass": latency["p99_ms_per_card"] < 50,
            "runs": latency["runs"],
            "per_card_ms": latency["per_card_ms"],
        },
        "PC-6": {
            "name": "vocabulary_health",
            "orphan_verbs": {
                "value": len(report.orphan_verbs),
                "target": "0",
                "pass": not report.orphan_verbs,
                "verbs": list(report.orphan_verbs),
            },
            "max_verb_share": {
                "value": round(report.max_verb_share, 6),
                "target": "<0.20",
                "pass": report.max_verb_share < 0.20,
            },
            "pass": (not report.orphan_verbs) and report.max_verb_share < 0.20,
            "atom_total": report.atom_total,
            "max_share_verb": report.pc6_max_share_verb,
            "verb_histogram": dict(sorted(report.verb_histogram.items())),
        },
        "PC-7": {
            "name": "executor_coverage",
            "status": "pending_executor",
            "target": "25/25; >=0.70",
            "pass": None,
            "note": "core/executor.py ships in T6 — not stubbed by this harness",
        },
        "PC-8": {
            "name": "targetable_card_fraction",
            "targetable_entries": report.targetable_entries,
            "denominator": report.entry_count,
            "value": round(report.pc8_targetable_fraction, 6),
            "target": ">=0.40",
            "stretch": ">=0.50",
            "pass": report.pc8_targetable_fraction >= 0.40,
        },
        "PC-9": {
            "name": "determinism",
            "value": latency["deterministic"],
            "target": "identical fingerprint multiset",
            "pass": latency["deterministic"],
        },
        "PC-10": pc10,
    }

    failed = sorted(
        k for k, v in pcs.items() if isinstance(v.get("pass"), bool) and not v["pass"]
    )
    date = datetime.datetime.now().astimezone().date().isoformat()

    full_report = {
        "set": set_name,
        "generated": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "git_head": _git_head(),
        "python_version": platform.python_version(),
        "pinned_denominators": {
            "entries": PINNED_ENTRIES,
            "sentences": PINNED_SENTENCES,
            "unique": PINNED_SENTENCES_UNIQUE,
        },
        "pool_stats": report.pool_stats,
        "pcs": pcs,
        "failed_targets": failed,
        "golden": {
            "dir": str(REPO / "MTG_bot" / "core" / "golden" / set_name),
            "files": golden_files,
            "diffs": golden_diffs,
            "stable": not golden_diffs,
            "goldens": golden_mode,
            "baseline": "VCS-tracked (committed goldens; verify-only by default)",
        },
        "unparsed_queue": [e.to_json() for e in report.unparsed_queue],
        "unparsed_count": report.unparsed_count,
    }
    if engine is not None:
        full_report["engine_support"] = engine

    reports_dir = REPO / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    report_path = reports_dir / f"grammar_{date}.json"
    report_path.write_text(
        json.dumps(full_report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # -- NUMBERS.md headline rows (top of file, above newest section) --------
    numbers_path = REPO / "KNOWLEDGE" / "NUMBERS.md"
    _append_numbers_md(
        numbers_path, date, pcs, golden_files, golden_diffs, golden_mode, engine
    )

    # -- human summary --------------------------------------------------------
    print(
        f"set={set_name}  entries={report.entry_count}  "
        f"sentences={report.sentence_total}  unique={report.sentence_unique}"
    )
    print(
        f"PC-1 card_coverage       {pcs['PC-1']['value']:.4f}  "
        f"({pcs['PC-1']['cards_zero_unparsed']}/{pcs['PC-1']['denominator']})  "
        f"target {pcs['PC-1']['target']}  {'PASS' if pcs['PC-1']['pass'] else 'FAIL'}"
    )
    print(
        f"PC-2 sentence_coverage   {pcs['PC-2']['value']:.4f}  "
        f"({pcs['PC-2']['sentences_matched']}/{pcs['PC-2']['denominator']})  "
        f"target {pcs['PC-2']['target']}  {'PASS' if pcs['PC-2']['pass'] else 'FAIL'}"
    )
    print(
        f"PC-3 ambiguity           {pcs['PC-3']['value']}  "
        f"target 0  {'PASS' if pcs['PC-3']['pass'] else 'FAIL'}"
    )
    print(
        f"PC-4 golden_stability    {len(golden_diffs)} diffs "
        f"({golden_files} files, {golden_mode})  "
        f"target 0  {'PASS' if pcs['PC-4']['pass'] else 'FAIL'}"
    )
    print(
        f"PC-5 latency p99         {pcs['PC-5']['value']} ms/card "
        f"({pcs['PC-5']['runs']} runs)  target <50  "
        f"{'PASS' if pcs['PC-5']['pass'] else 'FAIL'}"
    )
    print(
        f"PC-6 vocabulary          orphans={len(report.orphan_verbs)}  "
        f"max share={report.max_verb_share:.4f} "
        f"({report.pc6_max_share_verb})  "
        f"{'PASS' if pcs['PC-6']['pass'] else 'FAIL'}"
    )
    print("PC-7 executor            pending_executor (T6) — deferred")
    if engine is not None:
        proof = engine.get("flip_proof") or {}
        print(
            f"PC-7 engine_supported    {engine['engine_supported_cards']}"
            f"/{engine['of_total']} cards dispatch-ready "
            f"({len(engine['supported_verbs'])} verbs in SUPPORTED_VERBS_V2)"
        )
        if proof:
            print(
                f"        flip-proof: {proof['card']} "
                f"(spell_only={proof['spell_ability_only']}) "
                f"True -> False via {proof['offending_verbs']}"
            )
    print(
        f"PC-8 targetable          {pcs['PC-8']['value']:.4f}  "
        f"({pcs['PC-8']['targetable_entries']}/{pcs['PC-8']['denominator']})  "
        f"target {pcs['PC-8']['target']}  {'PASS' if pcs['PC-8']['pass'] else 'FAIL'}"
    )
    print(
        f"PC-9 determinism         {'stable' if pcs['PC-9']['pass'] else 'UNSTABLE'}  "
        f"{'PASS' if pcs['PC-9']['pass'] else 'FAIL'}"
    )
    print(
        f"PC-10 null_test          {pcs['PC-10']['good_card_coverage']:.0%} / "
        f"{pcs['PC-10']['bad_card_coverage']:.0%}, unparsed exact  "
        f"{'PASS' if pcs['PC-10']['pass'] else 'FAIL'}"
    )
    print(f"report                   {report_path}")
    print(f"NUMBERS.md               row appended ({date})")

    if failed:
        print(f"FAILED TARGETS: {', '.join(failed)}", file=sys.stderr)
        return 1
    print("all pre-registered targets pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
