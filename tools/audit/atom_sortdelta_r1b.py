#!/usr/bin/env python3
"""R1b cost-sort byte-delta MEASUREMENT (pre-registration, r0/r1a precedent).

N-R1b (measurement-only simulation; NO repo edit): for every Cost node in the
serialized tree, parts are SORTED by canonical_json(part) (dedup is NOT a
rule — Cost is a list, not a set-fold; identical parts are legal {W}{W});
every CostManaHybrid.colors tuple is sorted by the color string. Baseline =
canonical_json(card) of the live compile (== committed golden body when
goldens are fresh; freshness checked for M21).

Pre-registered hypothesis (task brief, R1a costs_sort=0): "all IR Costs are
single-part; byte-delta = 0". MEASUREMENT DECIDES — deviation IS the finding.

Checks:
  (1) changed-cards exact name-sets per pool, per-rule cause counts
      (cost_parts_sort, hybrid_colors_sort);
  (2) content preservation: parts multiset-after == multiset-before (by cj),
      hybrid colors set preserved — any drift = LOUD content failure;
  (3) idempotence: sort(sort(tree)) == sort(tree), zero second-pass firings;
  (4) population census: Cost nodes by (host-tag, field), multi-part Costs,
      multi-entry SpellAbility.additional_costs, hybrid nodes with
      non-alphabetical printed colors;
  (5) RUNTIME-exposure map: kicker/additional-cost carriers whose RUNTIME
      spell_cost() fold (legality.py:1113, printed ++ additional) creates a
      multi-part Cost the construction-sort of the IR nodes does NOT cover
      byte-wise but the planner entry-sort would canonicalize (which of
      those runtime folds are themselves order-changers).

Writes reports/r1b_sortdelta.json (repo-relative). READ-ONLY vs repo.
"""

from __future__ import annotations

import copy
import json
import sys
import traceback
from collections import Counter
from pathlib import Path

REPO = Path("/home/sune/Desktop/MTG_AI")
sys.path.insert(0, str(REPO))

from MTG_bot.core.ability_tree import canonical_json, to_dict  # noqa: E402
from MTG_bot.core.compiler.coverage import (  # noqa: E402
    _compile_pool_tolerant,
    build_full_registry,
)
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402

RULE_KEYS = ("cost_parts_sort", "hybrid_colors_sort")

CONTENT_FAILURES: list[str] = []
IDEM_FAILURES: list[str] = []
EXCEPTIONS: list[str] = []


def cj(v) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


def sort_tree(node, fired: Counter, host: tuple, stats: Counter, second_pass=False):
    """Return a mutated copy with Cost.parts sorted and hybrid colors sorted.
    `host` = (nearest enclosing tag, field) pair for the census census path."""
    if isinstance(node, list):
        return [sort_tree(x, fired, host, stats, second_pass) for x in node]
    if not isinstance(node, dict):
        return node
    tag = node.get("tag")
    out = {}
    for k, v in node.items():
        child_host = (tag, k) if tag else host
        out[k] = sort_tree(v, fired, child_host, stats, second_pass)
    if tag == "CostManaHybrid":
        colors = list(out.get("colors", []))
        canon = sorted(colors)
        if not second_pass:
            stats["hybrid_nodes"] += 1
            if colors != canon:
                fired["hybrid_colors_sort"] += 1
        if set(canon) != set(colors) or len(canon) != len(colors):
            CONTENT_FAILURES.append(f"{host}: hybrid colors lost")
        out["colors"] = canon
    if tag == "Cost":
        parts = list(out.get("parts", []))
        canon = sorted(parts, key=cj)
        if not second_pass:
            stats[f"cost@{host[0]}.{host[1]}"] += 1
            if len(parts) > 1:
                stats[f"multipart@{host[0]}.{host[1]}"] += 1
            fired["cost_parts_sort"] += 1 if parts != canon else 0
            if Counter(cj(p) for p in canon) != Counter(cj(p) for p in parts):
                CONTENT_FAILURES.append(f"{host}: cost parts multiset lost")
        else:
            if parts != canon:
                fired["second_pass_moved"] += 1
        out["parts"] = canon
    return out


def census_runtime_fold(tree, card_name, runtime_map):
    """Kicker/additional-cost exposure: a card whose IR holds >=2 Cost nodes
    that spell_cost() concatenates at runtime (mana_cost ++ additional/kicker
    parts). Record the printed runtime part sequence and whether the
    canonical sort would reorder that FOLDED sequence (planner order exposure
    TODAY, independent of the IR-node byte-delta)."""
    mana = tree.get("mana_cost")
    adds: list = []

    def collect(n):
        if isinstance(n, list):
            for x in n:
                collect(x)
        elif isinstance(n, dict):
            if n.get("tag") == "KickerAbility" and isinstance(n.get("cost"), dict):
                adds.append(("kicker", n["cost"].get("parts", [])))
            if n.get("tag") == "SpellAbility":
                for c in n.get("additional_costs", []):
                    adds.append(("additional", c.get("parts", [])))
            for v in n.values():
                collect(v)

    collect(tree)
    if not adds:
        return
    printed = list((mana or {}).get("parts", []))
    for kind, cost_parts in adds:
        printed = printed + list(cost_parts)
    canon = sorted(printed, key=cj)
    runtime_map[card_name] = {
        "fold_len": len(printed),
        "fold_tags": [p.get("tag") for p in printed],
        "fold_reorders_under_sort": printed != canon,
        "addition_kinds": sorted(k for k, _ in adds),
    }


def main() -> int:
    registry = build_full_registry()
    out: dict = {
        "method": "N-R1b cost-parts/hybrid-colors sort simulation on to_dict() tree"
    }
    runtime_map_all: dict = {}

    for set_name in ("M21", "ZNR"):
        pool = ingest_pool(REPO / "MTG_bot" / "data" / f"{set_name}.json")
        results, gaps = _compile_pool_tolerant(pool, registry)

        changed: list[str] = []
        changed_names: list[str] = []
        causes: dict[str, list[str]] = {k: [] for k in RULE_KEYS}
        idem_fail: list[str] = []
        content_fail: list[str] = []
        stats: Counter = Counter()
        stale_goldens: list[str] = []

        for oid in sorted(results):
            card = results[oid].card
            try:
                tree = to_dict(card)
                baseline = cj(tree)
                assert baseline == canonical_json(card)
                fired: Counter = Counter()
                mark = len(CONTENT_FAILURES)
                folded = sort_tree(copy.deepcopy(tree), fired, ("root", "$"), stats)
                content_fail.extend(CONTENT_FAILURES[mark:])
                fired2: Counter = Counter()
                folded2 = sort_tree(
                    copy.deepcopy(folded),
                    fired2,
                    ("root", "$"),
                    Counter(),
                    second_pass=True,
                )
                if cj(folded2) != cj(folded) or fired2:
                    idem_fail.append(
                        f"{set_name} {oid} ({card.name!r}): refire={dict(fired2)}"
                    )
                census_runtime_fold(
                    tree, card.name, runtime_map_all.setdefault(set_name, {})
                )
                if cj(folded) != baseline:
                    changed.append(oid)
                    changed_names.append(card.name)
                    for k in RULE_KEYS:
                        if fired[k]:
                            causes[k].append(card.name)
            except Exception:
                EXCEPTIONS.append(
                    f"{set_name} {card.name!r}:\n{traceback.format_exc()}"
                )
                continue

            if set_name == "M21":
                gp = REPO / "MTG_bot" / "core" / "golden" / "M21" / f"{oid}.json"
                if gp.exists() and gp.read_text().strip() != cj(to_dict(card)):
                    stale_goldens.append(card.name)

        entry = {
            "changed_count": len(changed),
            "changed_oids": sorted(changed),
            "changed_names": sorted(changed_names),
            "total_compiled": len(results),
            "shape_gaps": len(gaps),
            "census": dict(stats),
            "per_cause_card_counts": {k: len(set(v)) for k, v in causes.items()},
            "per_cause_cards": {k: sorted(set(v)) for k, v in causes.items()},
            "idempotence_failures": idem_fail,
            "content_failures": content_fail,
        }
        if set_name == "M21":
            gdir = REPO / "MTG_bot" / "core" / "golden" / "M21"
            entry["golden_files_total"] = len(list(gdir.glob("*.json")))
            entry["baseline_stale_goldens"] = stale_goldens
        out["sets"] = out.get("sets", {})
        out["sets"][set_name] = entry
        print(
            f"{set_name}: changed {len(changed)}/{len(results)} census={dict(stats)}",
            flush=True,
        )

    out["hypothesis_check"] = {
        "brief_prediction": "byte-delta = 0 (all IR Costs single-part)",
        "measured": {s: out["sets"][s]["changed_count"] for s in ("M21", "ZNR")},
        "verdict": "REFUTED"
        if any(out["sets"][s]["changed_count"] for s in ("M21", "ZNR"))
        else "CONFIRMED",
    }
    # runtime kicker/additional folds that reorder under canonical sort
    out["runtime_fold_exposure"] = {
        s: {
            "cards_with_runtime_fold": len(v),
            "folds_reordered_by_sort": sorted(
                c for c, info in v.items() if info["fold_reorders_under_sort"]
            ),
        }
        for s, v in runtime_map_all.items()
    }
    out["runtime_fold_detail"] = runtime_map_all
    out["idempotence_all_pass"] = not IDEM_FAILURES
    out["exceptions"] = EXCEPTIONS

    dest = Path(__file__).resolve().parents[2] / "reports" / "r1b_sortdelta.json"
    dest.write_text(json.dumps(out, indent=2))
    print(
        f"wrote {dest}; exceptions={len(EXCEPTIONS)} content_fail={len(set(CONTENT_FAILURES))} "
        f"idem_fail={len(IDEM_FAILURES)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
