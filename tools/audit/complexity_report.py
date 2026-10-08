"""Task-complexity meter for the campaign (owner 2026-10-08).

Atomized components added complexity for BOTH the player model and the
drafter/teacher. This tool turns the raw corpus artifacts into a measured
readout so per-set integrations can show what the tokenizer demands grew by.

PER-SET-INTEGRATION STANDARD READOUT (AGENTS.md §8): run this after every set
integration and diff the printed table / JSON against the previous snapshot.
It measures MENU WIDTH (branching factor), DECISION ENTROPY + gold-position
proxy bits, TASK SIZE (asks, gold lines, vocab/seq from train reports),
INTERACTION COMPLEXITY (engine hexproof/shroud/protection veto load via a
read-only monkeypatch harness — zero engine edits), ATOM COVERAGE vs EXAM
(eval-side ask kinds with zero train-side lines, batch-6 fail-core method),
and DRAFTER LOAD (scripted decisions + expect lanes per scenario pack).

Era trend: v4-era / v5-era / v6-era are pinned to git-traceable artifacts
(git show <sha>:tools/training/episodes_v2.jsonl READ-ONLY + archived bc5/bc6
reports on disk). Nothing outside tools/audit/ is ever written.

Usage:
    python3 tools/audit/complexity_report.py            # full (runs legality harness)
    python3 tools/audit/complexity_report.py --fast     # skip legality harness
    python3 tools/audit/complexity_report.py --out /tmp/x.json
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

EPISODES = REPO / "tools" / "training" / "episodes_v2.jsonl"
EVAL_SPLIT = REPO / "tools" / "audit" / "eval_split.json"
SCENARIO_DIR = REPO / "tools" / "scenarios"

# Era pins: (label, episodes git ref, on-disk train report with vocab/seq/counts)
ERAS = [
    ("v4", "a742c19", REPO / "tools/training/archive_v4_baseline/bc5_S0_report.json"),
    ("v5", "aa882e1~1", REPO / "tools/training/bc5_S0_report.json"),
    ("v6", None, REPO / "tools/training/bc6_S0_s1_report.json"),  # None = working tree
]

HOOK_NOTE = (
    "Legality veto instrumentation is a harness-side monkeypatch of "
    "MTG_bot/core/executor/legality.py:_hexproof_vetoes_target (applied at "
    "enumerate_candidates, legality.py:520). A permanent counter hook belongs "
    "at that line (file:symbol legality.py:enumerate_candidates)."
)


def ask_kind(what: str) -> str:
    return str(what).split(":", 1)[0]


def _p90(sorted_vals):
    if not sorted_vals:
        return 0
    return sorted_vals[min(len(sorted_vals) - 1, int(0.9 * (len(sorted_vals) - 1)))]


def _stats(vals):
    if not vals:
        return {"n": 0}
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    median = s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0
    return {
        "n": n,
        "mean": round(sum(s) / n, 3),
        "median": median,
        "p90": _p90(s),
        "max": s[-1],
    }


def load_episodes_text(ref) -> str | None:
    """git show <ref>:<path> READ-ONLY. None if not fetchable/parseable."""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "show", f"{ref}:{EPISODES.relative_to(REPO)}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        ).stdout
    except Exception:
        return None
    return out if out.strip() else None


def episodes_metrics(recs, notes):
    """Core per-file metrics: menu width, entropy, gold-proxy, asks, coverage input."""
    menus, per_kind = [], {}
    ent = []
    gold_first = 0
    proxy_bits_needed = 0.0
    total_bits = 0.0
    total_asks = 0
    kind_train_eval = {}  # filled by caller using split; keep kinds here
    kinds = set()
    for r in recs:
        for a in r.get("asks", []):
            cands = a.get("candidates") or []
            n = len(cands)
            k = ask_kind(a.get("what", ""))
            kinds.add(k)
            menus.append(n)
            per_kind.setdefault(k, []).append(n)
            total_asks += 1
            h = math.log2(n) if n > 1 else 0.0
            ent.append(h)
            total_bits += h
            gi = a.get("gold_idx")
            if gi == 0:
                gold_first += 1
            else:
                proxy_bits_needed += h  # PROXY: position-0 prior is wrong; full menu must be discriminated
    nrec = max(1, len(recs))
    return {
        "episodes": len(recs),
        "distinct_cards": len({r.get("card") for r in recs}),
        "distinct_packs": len({r.get("pack") for r in recs}),
        "total_asks": total_asks,
        "asks_per_episode": round(total_asks / nrec, 3),
        "ask_kinds": sorted(kinds),
        "menu_width_overall": _stats(menus),
        "menu_width_by_kind": {k: _stats(v) for k, v in sorted(per_kind.items())},
        "decision_entropy": {
            "mean_uniform_bits": round(sum(ent) / len(ent), 4) if ent else 0.0,
            "PROXY_gold_bits_required": round(
                proxy_bits_needed / max(1.0, total_asks), 4
            ),
            "PROXY_note": (
                "proxy: bits REQUIRED to beat a vocab[0]-first prior; 0 when "
                "gold_idx==0, full log2(|menu|) otherwise (honest positional "
                "shortcut measure, not a learned-model entropy)"
            ),
            "PROXY_fraction_gold_is_first_candidate": round(
                gold_first / max(1, total_asks), 4
            ),
        },
    }


def era_task_size(report_path: Path, notes, label):
    if not report_path.exists():
        notes.append(
            f"task-size era {label}: report {report_path.name} missing — skipped"
        )
        return None
    d = json.loads(report_path.read_text())
    seq = d.get("seq_len") or {}
    counts = d.get("counts") or {}
    return {
        "head": d.get("head"),
        "date": d.get("date"),
        "vocab_size": d.get("vocab_size"),
        "seq_len_median": seq.get("median"),
        "seq_len_max": seq.get("max"),
        "gold_lines_eval_joined": counts.get("eval_joined"),
        "train_episodes": counts.get("train_episodes"),
    }


def coverage_vs_exam(recs, notes):
    """batch-6 fail-core method: eval-side ask kinds with zero train-side lines."""
    split = json.loads(EVAL_SPLIT.read_text())
    ev_fams, tr_fams = set(split["eval_families"]), set(split["train_families"])
    tr_kinds, ev_kind_fams = set(), {}
    for r in recs:
        kinds = {ask_kind(a.get("what", "")) for a in r.get("asks", [])}
        if r.get("card") in tr_fams:
            tr_kinds |= kinds
        elif r.get("card") in ev_fams:
            for k in kinds:
                ev_kind_fams.setdefault(k, set()).add(r["card"])
    holes = sorted(k for k in ev_kind_fams if k not in tr_kinds)
    return {
        "train_families_with_episodes": len(
            {r["card"] for r in recs if r.get("card") in tr_fams}
        ),
        "eval_families_with_episodes": len(
            {r["card"] for r in recs if r.get("card") in ev_fams}
        ),
        "train_ask_kinds": sorted(tr_kinds),
        "eval_only_ask_kinds_COVERAGE_HOLES": holes,
        "hole_count": len(holes),
        "eval_families_per_hole": {
            k: sorted(v) for k, v in sorted(ev_kind_fams.items()) if k not in tr_kinds
        },
    }


def drafter_load(notes):
    packs = sorted(SCENARIO_DIR.glob("*.json"))
    if not packs:
        notes.append("drafter: no scenario packs found — skipped")
        return None
    asks, lanes, lane_vocab = [], [], {}
    for p in packs:
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        n_asks = sum(len(s.get("decisions") or []) for s in d.get("steps", []))
        expect = d.get("expect") or {}
        n_lanes = len(expect)
        for k in expect:
            lane_vocab[k] = lane_vocab.get(k, 0) + 1
        asks.append(n_asks)
        lanes.append(n_lanes)
    return {
        "packs": len(asks),
        "scripted_decisions_per_pack": _stats(asks),
        "distinct_expect_lanes_per_pack": _stats(lanes),
        "lane_marker_vocab_size": len(lane_vocab),
        "PROXY_note": "asks = step.decisions queues; lanes = distinct expect-block keys (packs are JSON, not yaml)",
    }


def legality_harness(notes):
    """Read-only: monkeypatch counts, ZERO edits to engine files."""
    try:
        import importlib.util
        import MTG_bot.core.executor.legality as L

        orig_veto, orig_enum = L._hexproof_vetoes_target, L.enumerate_candidates
        st = {
            "veto_tests": 0,
            "vetoed": 0,
            "enum_calls": 0,
            "survivors": 0,
            "packs_with_veto": 0,
        }

        def veto(c, ctx):
            st["veto_tests"] += 1
            r = orig_veto(c, ctx)
            if r:
                st["vetoed"] += 1
            return r

        def enum(sel, ctx):
            st["enum_calls"] += 1
            out = orig_enum(sel, ctx)
            st["survivors"] += len(out)
            return out

        L._hexproof_vetoes_target, L.enumerate_candidates = veto, enum
        try:
            spec = importlib.util.spec_from_file_location(
                "run_scenarios_x", REPO / "tools/run_scenarios.py"
            )
            if spec is None or spec.loader is None:
                raise RuntimeError("cannot load run_scenarios.py")
            rs = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(rs)
            supply = rs.get_supply("all")
            for p in sorted(SCENARIO_DIR.glob("*.json")):
                before = st["vetoed"]
                rs.run_pack(p, supply)
                if st["vetoed"] > before:
                    st["packs_with_veto"] += 1
        finally:
            L._hexproof_vetoes_target, L.enumerate_candidates = orig_veto, orig_enum
        raw_supply = st["survivors"] + st["vetoed"]
        return {
            "instrumented": True,
            "veto_tests": st["veto_tests"],
            "candidates_vetoed": st["vetoed"],
            "veto_rate_per_candidate_tested": round(
                st["vetoed"] / max(1, st["veto_tests"]), 4
            ),
            "vetoed_share_of_raw_candidates": round(
                st["vetoed"] / max(1, raw_supply), 4
            ),
            "enumerate_calls": st["enum_calls"],
            "packs_with_at_least_one_veto": st["packs_with_veto"],
            "note": "counts hexproof/shroud/protection vetoes in enumerate_candidates (proxy; all selector kinds, not only target asks). "
            "VALIDITY: the same wrapper sees 12 real vetoes in MTG_bot/core/test_executor_hexproof.py, so a 0 here means the "
            "scenario-pack set today has no board where a hexproof target is chosen (coverage lives in unit tests); the meter "
            "starts counting as sets add hexproof boards to packs. " + HOOK_NOTE,
        }
    except Exception as e:  # graceful skip, no edits
        notes.append(f"metric 4 SKIPPED ({type(e).__name__}: {e}). " + HOOK_NOTE)
        return {"instrumented": False, "note": HOOK_NOTE}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--episodes", default=str(EPISODES))
    ap.add_argument("--out", default=str(REPO / "tools/audit/complexity_v6.json"))
    ap.add_argument(
        "--fast", action="store_true", help="skip legality harness (metric 4)"
    )
    ap.add_argument("--no-git", action="store_true", help="skip git-history era trend")
    args = ap.parse_args(argv)

    notes: list[str] = []
    recs = [
        json.loads(l) for l in Path(args.episodes).read_text().splitlines() if l.strip()
    ]
    cur = episodes_metrics(recs, notes)
    cur["task_size_reports"] = {lbl: era_task_size(p, notes, lbl) for lbl, _, p in ERAS}
    cur["coverage_vs_exam"] = coverage_vs_exam(recs, notes)
    cur["drafter_load"] = drafter_load(notes)
    cur["interaction_complexity"] = (
        {"instrumented": False, "note": "skipped via --fast"}
        if args.fast
        else legality_harness(notes)
    )

    trend = {}
    if args.no_git:
        notes.append("era trend skipped via --no-git")
    else:
        for lbl, ref, _ in ERAS:
            if ref is None:
                trend[lbl] = {
                    "episodes": cur["episodes"],
                    "total_asks": cur["total_asks"],
                    "asks_per_episode": cur["asks_per_episode"],
                    "menu_mean": cur["menu_width_overall"].get("mean"),
                    "menu_p90": cur["menu_width_overall"].get("p90"),
                    "mean_uniform_bits": cur["decision_entropy"]["mean_uniform_bits"],
                    "ask_kinds": cur["ask_kinds"],
                }
                continue
            text = load_episodes_text(ref)
            if text is None:
                notes.append(f"era {lbl}: git show {ref} unparseable — skipped")
                continue
            try:
                old = [json.loads(l) for l in text.splitlines() if l.strip()]
                m = episodes_metrics(old, notes)
                trend[lbl] = {
                    "episodes": m["episodes"],
                    "total_asks": m["total_asks"],
                    "asks_per_episode": m["asks_per_episode"],
                    "menu_mean": m["menu_width_overall"].get("mean"),
                    "menu_p90": m["menu_width_overall"].get("p90"),
                    "mean_uniform_bits": m["decision_entropy"]["mean_uniform_bits"],
                    "ask_kinds": m["ask_kinds"],
                }
            except Exception as e:
                notes.append(f"era {lbl}: parse failed ({e}) — skipped")
    cur["era_trend_v4_v5_v6"] = trend
    cur["notes"] = notes

    Path(args.out).write_text(json.dumps(cur, indent=2, default=str) + "\n")

    # ---- compact printed table -------------------------------------------------
    w = cur["menu_width_by_kind"]
    print(f"== COMPLEXITY v6  ({args.out}) ==")
    print(
        f"corpus: {cur['episodes']} episodes / {cur['distinct_cards']} cards / "
        f"{cur['distinct_packs']} packs / {cur['total_asks']} asks / "
        f"{cur['asks_per_episode']} asks-per-episode"
    )
    mo = cur["menu_width_overall"]
    print(
        f"menu width overall: mean={mo['mean']} median={mo['median']} p90={mo['p90']} max={mo['max']}"
    )
    print(f"kind           n    mean  p90  max")
    for k, s in w.items():
        print(
            f"  {k:<14} {s.get('n', 0):>5}  {s.get('mean', 0):>5}  {s.get('p90', 0):>3}  {s.get('max', 0):>3}"
        )
    de = cur["decision_entropy"]
    print(
        f"entropy: mean {de['mean_uniform_bits']} bits/ask | proxy bits-required {de['PROXY_gold_bits_required']} "
        f"| gold-first fraction {de['PROXY_fraction_gold_is_first_candidate']}"
    )
    ts = cur["task_size_reports"]
    for lbl, r in ts.items():
        if r:
            print(
                f"task-size {lbl}: head={r['head']} vocab={r['vocab_size']} seq_med={r['seq_len_median']} gold_lines={r['gold_lines_eval_joined']}"
            )
    cv = cur["coverage_vs_exam"]
    print(
        f"coverage holes (eval-only ask kinds): {cv['hole_count']} -> {cv['eval_only_ask_kinds_COVERAGE_HOLES']}"
    )
    dl = cur["drafter_load"]
    if dl:
        print(
            f"drafter load: {dl['packs']} packs, decisions/pack mean={dl['scripted_decisions_per_pack']['mean']} "
            f"max={dl['scripted_decisions_per_pack']['max']}, lanes/pack mean={dl['distinct_expect_lanes_per_pack']['mean']}"
        )
    ic = cur["interaction_complexity"]
    if ic.get("instrumented"):
        print(
            f"legality veto: {ic['candidates_vetoed']} vetoed / {ic['veto_tests']} tests "
            f"(share {ic['vetoed_share_of_raw_candidates']} of raw candidates) across {ic['packs_with_at_least_one_veto']} packs"
        )
    else:
        print(f"legality veto: SKIPPED — {ic['note']}")
    tr = cur["era_trend_v4_v5_v6"]
    if len(tr) > 1:
        print("era  episodes asks/ep menu-mean p90  bits")
        for lbl in ("v4", "v5", "v6"):
            if lbl in tr:
                t = tr[lbl]
                print(
                    f" {lbl}  {t['episodes']:>7} {t['asks_per_episode']:>7} {t['menu_mean']:>10} "
                    f"{t['menu_p90']:>3}  {t['mean_uniform_bits']:.4f}"
                )
    for n in notes:
        print(f"note: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
