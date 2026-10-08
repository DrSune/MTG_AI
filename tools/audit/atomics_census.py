#!/usr/bin/env python3
"""T5 Phase A — full-pool atomics CENSUS (KNOWLEDGE/2026-10-08/50 charter).

Machine inventory of every non-canonical / fused / duplicate / stale encoding
across ALL 305 golden M21 trees (MTG_bot/core/golden/M21/*.json). Pure
offline read: engine imports are used ONLY to reuse the REAL promotion
predicate (compiler._is_liftable_pick) and the node deserialiser — zero
engine mutation, goldens untouched.

Emits tools/audit/atomics_census.json:
    findings: {pattern -> {count, tree_count, trees[], severity, note}}
    rewrite_ledger: [{pattern, proposed_canonical, effort, rationale}]
and prints the census table + ledger. Run: python tools/audit/atomics_census.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from collections import Counter
from datetime import UTC, datetime

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOLDEN_DIR = ROOT / "MTG_bot" / "core" / "golden" / "M21"
EXECUTOR_DIR = ROOT / "MTG_bot" / "core" / "executor"
EPISODES = ROOT / "tools" / "training" / "episodes_v2.jsonl"
BC_DATA = ROOT / "tools" / "training" / "bc_data.py"
OUT_PATH = ROOT / "tools" / "audit" / "atomics_census.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from MTG_bot.core.ability_tree import (
    VERB_CLASS,
    Keyword,
    from_dict,
)
from MTG_bot.core.compiler.compiler import (
    PICK_ASK_FORCE_SILENT,
    _is_liftable_pick,
)

# P1a merged MOVE's legacy twins — unemitted members (ability_tree.py
# VERB_CLASS comment): any survival in a golden tree is CRITICAL drift.
MOVE_TWINS = frozenset({"MILL", "DISCARD", "EXILE"})

# the canonical {6 OPERATION, 7 POLICY, 36 EFFECT} partition, by name
_PARTITION_NAMES = frozenset(v.name for v in VERB_CLASS)

# /32 E1 (merge pending): controller-direction encodings. Style A = a
# `controller` ControllerRef field on an event node; style B = the
# FAtomPred.CONTROLLER_IS `who` slot inside subject filters. Zone-level
# controller (the dominant "… you control" filter) is census context.
EVENT_STYLE_A_TREES_KEY = "event_direction_field"
EVENT_STYLE_B_TREES_KEY = "event_direction_controllers_is"

# Keywords whose ENFORCEMENT is delegated to a verb handler or a rules hook
# rather than a Keyword.X token (each pointer verified 2026-10-08):
KEYWORD_DELEGATION = {
    "SCRY": "executor/verbs.py _v_scry (Verb.SCRY table 1941)",
    "MILL": "executor/verbs.py Verb.MILL shape (107/133) via MOVE_ZONE",
    "FIGHT": "executor/verbs.py _v_fight (Verb.FIGHT table 1982)",
}


class Findings:
    """pattern -> {count, trees (ordered set), severity, note}."""

    def __init__(self) -> None:
        self._d: dict[str, dict] = {}

    def add(self, pattern: str, tree: str, severity: str, note: str = "") -> None:
        f = self._d.setdefault(
            pattern, {"count": 0, "trees": [], "severity": severity, "note": note}
        )
        f["count"] += 1
        if tree not in f["trees"]:
            f["trees"].append(tree)

    def ensure(self, pattern: str, severity: str, note: str) -> None:
        self._d.setdefault(
            pattern, {"count": 0, "trees": [], "severity": severity, "note": note}
        )

    def set_note(self, pattern: str, note: str, severity: str | None = None) -> None:
        f = self._d.setdefault(
            pattern, {"count": 0, "trees": [], "severity": "info", "note": note}
        )
        f["note"] = note
        if severity:
            f["severity"] = severity

    def as_json(self) -> dict:
        out = {}
        for k, f in self._d.items():
            out[k] = {
                "count": f["count"],
                "tree_count": len(f["trees"]),
                "trees": f["trees"],
                "severity": f["severity"],
                "note": f["note"],
            }
        return out


def _iter_tagged(node: object, in_cost: bool, verb: str):
    """Yield (dict, in_cost, verb) for every tagged dict, mirroring the
    compiler's own traversal context rules: entering a Cost* node (except
    CostLoyalty) flips in_cost; entering an Atom sets the verb context."""
    if isinstance(node, dict):
        tag = node.get("tag")
        yield node, in_cost, verb
        child_cost = in_cost or (
            isinstance(tag, str) and tag.startswith("Cost") and tag != "CostLoyalty"
        )
        child_verb = node["verb"]["name"] if tag == "Atom" else verb
        for v in node.values():
            yield from _iter_tagged(v, child_cost, child_verb)
    elif isinstance(node, list):
        for v in node:
            yield from _iter_tagged(v, in_cost, verb)


def _is_qconst1(count: dict) -> bool:
    return count.get("tag") == "QConst" and count.get("value") == 1


def scan_tree(card: dict, F: Findings) -> None:
    """One golden CardRecord -> findings. `tree` label = card name."""
    tree = card.get("name", "?")
    # emblem (if any) is a node tree too (charter /29 probe lesson) — the
    # generic walk below starts at the whole record, so it is covered.
    for node, in_cost, verb in _iter_tagged(card, False, ""):
        tag = node.get("tag")

        # ---- (1) duplicate {choose} encodings -------------------------------
        if tag == "Choose":
            F.add(
                "choose_combinator",
                tree,
                "info",
                "node-Choose k-of-menu: KEEP-SEPARATE per /31 (menu = effect "
                "branches, not entity pick) — §9 merge candidate for the menu axis only",
            )
        if tag == "SelectorMode" and node.get("name") == "ONE_OF":
            F.add("choose_one_of_asking", tree, "info", "T4 canonical asking pick")
        if tag == "Selector":
            mode = node["mode"]["name"]
            count = node["count"]
            if mode == "CHOOSE":
                referent = node.get("referent")
                if referent is not None:
                    F.add(
                        "choose_referent_anaphoric",
                        tree,
                        "info",
                        "C2 anaphoric CHOOSE (bound object, not a decision) — legit",
                    )
                    continue
                shape1 = _is_qconst1(count)
                if not shape1:
                    # ---- (5) k-of-n non-canonical ------------------------
                    if count.get("tag") == "QUnbounded":
                        F.add(
                            "choose_up_to_any",
                            tree,
                            "info",
                            "CHOOSE QUnbounded = canonical up-to-any designation",
                        )
                    else:
                        F.add(
                            "kofn_legacy_choose_multicount",
                            tree,
                            "medium",
                            "entity CHOOSE with concrete count k>1/QAtMost — "
                            "pick-k encoded ad hoc, not the T2 ONE_OF want-loop",
                        )
                    continue
                sel = from_dict("Selector", node)  # faithful predicate input
                key = (tree, verb)
                if key in PICK_ASK_FORCE_SILENT:
                    F.add(
                        "choose_silent_force_silent",
                        tree,
                        "info",
                        "P1b FORCE_SILENT (gap ledger L-27/28/29) — LEGITIMATE",
                    )
                elif _is_liftable_pick(sel, in_cost):
                    F.add(
                        "choose_silent_promotable",
                        tree,
                        "medium",
                        "lifts to ONE_OF at compile time; disk shape is the "
                        "legacy duplicate — T5-C should persist ONE_OF",
                    )
                elif in_cost:
                    F.add(
                        "choose_silent_cost_lane",
                        tree,
                        "info",
                        "cost-position CHOOSE (sacrifice lane r22a) — legit lane",
                    )
                else:
                    F.add(
                        "choose_silent_is_source_lane",
                        tree,
                        "info",
                        "IS_SOURCE self-designation (CR 602.2c) — legit lane",
                    )
            if mode == "ONE_OF" and count.get("tag") not in ("QConst",):
                F.add(
                    "kofn_one_of_loop_canonical",
                    tree,
                    "info",
                    "ONE_OF with non-const count = canonical T2 want-loop shape",
                )
            # selector counts outside {QConst,QAtMost,QUnbounded} = ad-hoc bound risk
            if count.get("tag") not in ("QConst", "QAtMost", "QUnbounded"):
                F.add(
                    "count_adhoc_bound_shape",
                    tree,
                    "high",
                    "Selector count is not a T3-recognised shape — resolve-guard "
                    "NotImplementedError territory",
                )

        # ---- (2) fused axes: verb outside the P1a partition -----------------
        if tag == "Verb":
            name = node["name"]
            if name not in _PARTITION_NAMES:
                F.add(
                    "verb_outside_partition",
                    tree,
                    "critical",
                    "verb not in the {6 OPERATION, 7 POLICY, 36 EFFECT} partition",
                )
            # ---- (4) MOVE leftovers ------------------------------------------
            if name in MOVE_TWINS:
                F.add(
                    "move_verb_leftover",
                    tree,
                    "critical",
                    "P1a merged MOVE's legacy twin still emitted — CRITICAL",
                )

        # ---- (3) event direction dual encoding (/32 E1) ---------------------
        if isinstance(tag, str) and tag.endswith("Event") and "controller" in node:
            ctl = node["controller"]
            if isinstance(ctl, dict) and ctl.get("name") not in (None, "ANY"):
                F.add(
                    EVENT_STYLE_A_TREES_KEY,
                    tree,
                    "medium",
                    "style A: event.controller field carries direction (E1 merge pending)",
                )
        if tag == "FAtom" and node.get("pred", {}).get("name") == "CONTROLLER_IS":
            F.add(
                EVENT_STYLE_B_TREES_KEY,
                tree,
                "medium",
                "style B: FAtomPred.CONTROLLER_IS who-slot (E1 merge pending)",
            )
        if tag == "Zone":
            ctl = node.get("controller") or {}
            if ctl.get("name") not in (None, "ANY"):
                F.add(
                    "event_direction_zone_field",
                    tree,
                    "info",
                    "zone.controller (dominant 'you control' filter) — E1 census context",
                )

        # ---- (6) keywords on the card record --------------------------------
        if tag == "Keyword":
            F.add(f"kw_present::{node['name']}", tree, "info", "carried by card pool")


# ---- (6) enforcement scan ----------------------------------------------------


def keyword_enforcement() -> dict[str, tuple[str, str]]:
    """keyword -> (status, evidence). status in {direct, delegated-verb,
    delegated-hook, DECORATIVE}. Direct = Keyword.X or "X" on a non-comment
    executor line; delegated-hook = a verified hard pointer; delegated-verb =
    a Verb.X handler table entry in the executor."""
    files = sorted(EXECUTOR_DIR.glob("*.py"))
    sources = {p.name: p.read_text().splitlines() for p in files}
    out: dict[str, tuple[str, str]] = {}
    for kw in Keyword:
        name = kw.name
        direct = ""
        for fname, lines in sources.items():
            pat = re.compile(rf'(Keyword\.{name}\b|["\']{name}["\'])')
            for i, line in enumerate(lines, 1):
                s = line.strip()
                if s.startswith("#"):
                    continue
                if pat.search(line):
                    direct = f"executor/{fname}:{i}"
                    break
            if direct:
                break
        if direct:
            out[name] = ("direct", direct)
            continue
        if name in KEYWORD_DELEGATION:
            out[name] = ("delegated", KEYWORD_DELEGATION[name])
            continue
        if any(
            re.search(rf"Verb\.{name}\b", l)
            for lines in sources.values()
            for l in lines
            if not l.strip().startswith("#")
        ):
            out[name] = ("delegated", "Verb handler table in executor")
            continue
        out[name] = ("DECORATIVE", "no enforcement site found in executor")
    return out


# ---- (7) count_semantics surfaces (static grep) ------------------------------


def count_semantics_sites() -> dict[str, int]:
    out = {}
    for p in sorted((ROOT / "MTG_bot" / "core").rglob("*.py")):
        if "test" in p.name:
            continue
        n = sum(
            1
            for line in p.read_text().splitlines()
            if "count_semantics" in line or "_choice_bounds" in line
        )
        if n:
            out[str(p.relative_to(ROOT))] = n
    return out


# ---- (8) site:? audit over compiled episodes ---------------------------------


def site_kind_audit() -> tuple[dict, Counter]:
    src = BC_DATA.read_text()
    m = re.search(r"SITE_KINDS = \((.*?)\n\)", src, re.DOTALL)
    if m is None:
        raise RuntimeError("SITE_KINDS tuple not found in bc_data.py")
    kinds = set(re.findall(r'"([a-z_0-9]+)"', m.group(1)))
    unknown: Counter = Counter()
    total_asks = 0
    for line in EPISODES.read_text().splitlines():
        ep = json.loads(line)
        for row in ep.get("asks", []):
            total_asks += 1
            kind = str(row.get("what", "")).split(":", 1)[0]
            if kind not in kinds:
                unknown[kind] += 1
    return {"known_kinds": sorted(kinds), "total_asks": total_asks}, unknown


def build() -> dict:
    F = Findings()
    files = sorted(GOLDEN_DIR.glob("*.json"))
    for f in files:
        scan_tree(json.loads(f.read_text()), F)

    # zero-hit tripwires stay visible in the report
    F.ensure(
        "choose_silent_promotable",
        "medium",
        "0 = goldens already persist the P1b-promoted ONE_OF shape — "
        "no on-disk silent-CHOOSE duplicate survives; tripwire",
    )
    F.ensure("move_verb_leftover", "critical", "0 = P1a clean; tripwire")
    F.ensure("verb_outside_partition", "critical", "0 = partition complete; tripwire")
    F.ensure("count_adhoc_bound_shape", "high", "0 = no ad-hoc bound shapes; tripwire")

    # E1: trees carrying BOTH direction styles simultaneously = merge surface.
    a = set(F._d.get(EVENT_STYLE_A_TREES_KEY, {}).get("trees", []))
    b = set(F._d.get(EVENT_STYLE_B_TREES_KEY, {}).get("trees", []))
    both = sorted(a & b)
    F.set_note(
        "event_direction_both_styles",
        f"{len(both)} trees encode controller-direction with BOTH an event "
        f"field and CONTROLLER_IS — E1 unification must rewrite these: {both}",
        severity="medium",
    )
    for t in both:
        F.add("event_direction_both_styles", t, "medium", "E1 merge surface")

    kw_status = keyword_enforcement()
    for name, (status, ev) in kw_status.items():
        if status == "DECORATIVE":
            carriers = F._d.get(f"kw_present::{name}", {}).get("trees", [])
            for t in carriers:
                F.add(
                    "keyword_decorative",
                    t,
                    "critical",
                    f"{name}: carried by cards, no executor enforcement site "
                    f"(TREASURE precedent)",
                )
    F.set_note(
        "keyword_enforcement_map", json.dumps(kw_status, indent=1), severity="info"
    )

    cs = count_semantics_sites()
    F.set_note(
        "count_semantics_surfaces",
        f"consumer call-sites per file {cs}; _choice_bounds (query.py) is the "
        f"T3-deferred 4th surface — fold into count_semantics in T5-C",
        severity="medium",
    )
    F._d["count_semantics_surfaces"]["count"] = sum(cs.values())
    F._d["count_semantics_surfaces"]["trees"] = sorted(cs)

    site_meta, unknown = site_kind_audit()
    F.set_note(
        "site_unknown_kind",
        f"{site_meta['total_asks']} asks scanned in episodes_v2.jsonl; "
        f"unknown site kinds: {unknown or 'NONE'}",
        severity="high" if unknown else "info",
    )
    F._d["site_unknown_kind"]["count"] = sum(unknown.values()) if unknown else 0
    F._d["site_unknown_kind"]["trees"] = sorted(unknown)

    # prune pure-carrier bookkeeping rows from the report body
    findings = {
        k: v for k, v in F.as_json().items() if not k.startswith("kw_present::")
    }

    ledger = [
        {
            "pattern": "choose_silent_promotable",
            "proposed_canonical": "persist ONE_OF (write promoted shape into goldens; retire silent-CHOOSE twin)",
            "effort": "M",
            "rationale": "compiler already lifts; §9 duplicate lives only on disk",
        },
        {
            "pattern": "choose_combinator",
            "proposed_canonical": "KEEP-SEPARATE (menu = effect branches, /31 ruling)",
            "effort": "S",
            "rationale": "documented; merge only the shared menu axis",
        },
        {
            "pattern": "choose_silent_force_silent",
            "proposed_canonical": "stay silent until L-27 provider-seat routing lands",
            "effort": "L",
            "rationale": "gap ledger, blocked on routing",
        },
        {
            "pattern": "event_direction_*",
            "proposed_canonical": "E1: single {controller-direction} encoding (event field vs CONTROLLER_IS)",
            "effort": "L",
            "rationale": "/32 registered, pool-wide rewrite + recert",
        },
        {
            "pattern": "kofn_legacy_choose_multicount",
            "proposed_canonical": "ONE_OF + QConst(k)/QAtMost want-loop (T2 atom)",
            "effort": "M",
            "rationale": "T2 loop exists (27 unit seeds), pool volume 0 — tokenize it now",
        },
        {
            "pattern": "keyword_decorative",
            "proposed_canonical": "enforce in executor or encode as flavour metadata (never a silent keyword token)",
            "effort": "M",
            "rationale": "TREASURE precedent; EQUIP audit pending",
        },
        {
            "pattern": "count_semantics_surfaces",
            "proposed_canonical": "fold _choice_bounds into count_semantics (kill 4th surface)",
            "effort": "M",
            "rationale": "T3 deferred item",
        },
        {
            "pattern": "move_verb_leftover",
            "proposed_canonical": "none expected — P1a clean",
            "effort": "S",
            "rationale": "tripwire census",
        },
        {
            "pattern": "verb_outside_partition",
            "proposed_canonical": "none expected — partition complete",
            "effort": "S",
            "rationale": "tripwire census",
        },
        {
            "pattern": "site_unknown_kind",
            "proposed_canonical": "extend SITE_KINDS additively if any appear",
            "effort": "S",
            "rationale": "/38 law",
        },
    ]

    return {
        "meta": {
            "generated": datetime.now(UTC).isoformat(),
            "golden_trees": len(files),
            "engine": "reuses compiler._is_liftable_pick + ability_tree.from_dict",
            "charter": "KNOWLEDGE/2026-10-08/50-t5-full-pool-reaudit-charter.md",
        },
        "findings": findings,
        "rewrite_ledger": ledger,
    }


SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "info": 3}


def main() -> None:
    report = build()
    OUT_PATH.write_text(json.dumps(report, indent=1))
    rows = sorted(
        report["findings"].items(),
        key=lambda kv: (SEV_ORDER[kv[1]["severity"]], -kv[1]["count"]),
    )
    print(f"{'pattern':38} {'count':>5} {'trees':>5}  severity  example trees")
    print("-" * 100)
    for pat, f in rows:
        ex = ", ".join(f["trees"][:3])
        print(
            f"{pat:38} {f['count']:>5} {f['tree_count']:>5}  {f['severity']:>8}  {ex[:40]}"
        )
    print("\n== REWRITE LEDGER ==")
    for e in report["rewrite_ledger"]:
        print(f"  [{e['effort']}] {e['pattern']}: {e['proposed_canonical']}")
    print(f"\nwrote {OUT_PATH}")


if __name__ == "__main__":
    main()
