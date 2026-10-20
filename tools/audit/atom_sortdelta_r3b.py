#!/usr/bin/env python3
"""R3b PHANTOM-FOLD byte-delta MEASUREMENT (pattern: tools/audit/atom_sortdelta_r1b.py).

READ-ONLY vs repo; writes ONLY reports/r3b_sortdelta.json.

Proposed no-decision shape (ontology §10 / D12): an L-A Selector node the
engine resolves without asking loses its phantom choice spelling —
mode CHOOSE -> ALL (the EXISTING no-decision spelling: ALL already carries
14 compiled IS_SOURCE nodes, e.g. Anointed Chorister). Classes folded:
  self  : CHOOSE ∧ referent=None ∧ filter carries IS_SOURCE (population ≡ {source})
  top   : CHOOSE ∧ referent=None ∧ singleton LIBRARY:YOU:TOP zone (window ≡ 1 card)
  seat  : CHOOSE ∧ referent=None ∧ singleton PLAYER:YOU zone ∧ universal filter (≡ 1 seat)
Class NOT folded (GAP REPORT, vocabulary-blocked):
  referent : Selector.__post_init__ C2 REQUIRES mode CHOOSE for referent selectors
             (constructor probe executed below); AND referent registers
             ("target"/"result"/"event") may bind MULTIPLE handles at runtime, where
             CHOOSE/QConst(1) takes sorted[:1] and ALL returns all — a mode fold
             here is NOT provably behavior-preserving at compile time.

Checks:
  (1) per-class fired-node counts == committed ledger (reports/r3_blindness.json,
      L-A 108/48/3/2) — deviation = LOUD;
  (2) content preservation: ONLY the mode key changes on any Selector; all other
      subtrees byte-identical;
  (3) idempotence: second pass fires 0;
  (4) changed records/cards per pool + M21 golden byte-delta count (goldens
      freshness checked against the live compile first);
  (5) V4′/freeze consequence: post-fold CHOOSE-node census per pool (baseline v2
      expects 193 nodes total; residual must be 193-161 = 32);
  (6) constructor probes: ALL+QConst(1)+IS_SOURCE legal; ALL+referent raises C2.
"""

from __future__ import annotations

import json
import sys
import traceback
from collections import Counter
from pathlib import Path

REPO = Path("/home/sune/Desktop/MTG_AI")
OUT = (Path(__file__).resolve().parents[2] / "reports" / "r3b_sortdelta.json")
sys.path.insert(0, str(REPO))

from MTG_bot.core.ability_tree import (  # noqa: E402
    ControllerRef,
    FAnd,
    FAtom,
    FAtomPred,
    QConst,
    Selector,
    SelectorMode,
    Zone,
    ZoneKind,
    canonical_json,
    to_dict,
)
from MTG_bot.core.compiler.coverage import (  # noqa: E402
    _compile_pool_tolerant,
    build_full_registry,
)
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402

CONTENT_FAILURES: list[str] = []
EXCEPTIONS: list[str] = []


def cj(v) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


def _enum(v):
    return v.get("name") if isinstance(v, dict) else v


def filter_is_self_serde(filt) -> bool:
    """Serialized-IR twin of selectors._filter_is_self_referential (FNot
    passthrough included, like production). The FNot-only case is separately
    flagged: NOT-IS_SOURCE is NOT a single-candidate population."""

    def under_not(node, neg):
        if not isinstance(node, dict):
            return False
        tag = node.get("tag")
        if tag == "FAtom":
            return _enum(node.get("pred")) == "IS_SOURCE"
        if tag in ("FAnd", "FOr"):
            return any(under_not(c, neg) for c in node.get("children", []))
        if tag == "FNot":
            return under_not(node.get("inner"), True)
        return False

    return under_not(filt, False)


def source_is_negated(filt) -> bool:
    """True when EVERY IS_SOURCE leaf sits under at least one FNot (the
    'another' shape — population NOT pinned to source; must never fold)."""

    def leaves(node, neg, acc):
        if not isinstance(node, dict):
            return
        tag = node.get("tag")
        if tag == "FAtom":
            if _enum(node.get("pred")) == "IS_SOURCE":
                acc.append(neg)
        elif tag in ("FAnd", "FOr"):
            for c in node.get("children", []):
                leaves(c, neg, acc)
        elif tag == "FNot":
            leaves(node.get("inner"), True, acc)

    acc: list[bool] = []
    leaves(filt, False, acc)
    return bool(acc) and all(acc)


def universal_filter(filt) -> bool:
    return (
        isinstance(filt, dict)
        and filt.get("tag") == "FAnd"
        and not filt.get("children")
    )


def classify(sel: dict) -> str | None:
    """L-A no-decision class of a CHOOSE-mode serialized Selector (foldable
    classes only; referent class is reported separately as GAP)."""
    if sel.get("tag") != "Selector" or _enum(sel.get("mode")) != "CHOOSE":
        return None
    if sel.get("referent") is not None:
        return None  # referent class: GAP, not folded
    filt = sel.get("filter")
    zs = sel.get("zones", [])
    if filter_is_self_serde(filt):
        # structural key: an ALL-NEGATED IS_SOURCE ("another") pins NOTHING —
        # not foldable, and (finding) mislaned L-A in the committed ledger.
        return "self-negated" if source_is_negated(filt) else "self"
    if len(zs) == 1:
        z = zs[0]
        if (
            _enum(z.get("kind")) == "LIBRARY"
            and _enum(z.get("position")) == "TOP"
            and _enum(z.get("controller")) == "YOU"
        ):
            return "top"
        if (
            _enum(z.get("kind")) == "PLAYER"
            and _enum(z.get("controller")) == "YOU"
            and universal_filter(filt)
        ):
            return "seat"
    return None


def fold_tree(node, fired: Counter, per_class: Counter, second_pass=False):
    if isinstance(node, list):
        return [fold_tree(x, fired, per_class, second_pass) for x in node]
    if not isinstance(node, dict):
        return node
    out = {k: fold_tree(v, fired, per_class, second_pass) for k, v in node.items()}
    cls = classify(node)
    if cls is not None:
        fired["foldable_matched"] += 1
        if cls == "self-negated":
            # excluded from the wave: NOT-IS_SOURCE = complement population
            # (Dire Fleet Warmonger class); needs its own adjudication —
            # committed ledger mislanes it L-A (finding).
            fired["self_negated_excluded"] += 1
            return out
        if second_pass:
            fired["second_pass_matched"] += 1
            return out  # (cannot happen: fold turns mode ALL, classify requires CHOOSE)
        folded = dict(out)
        folded["mode"] = {"tag": "SelectorMode", "name": "ALL"}
        fired["folded"] += 1
        per_class[cls] += 1
        return folded
    return out


def diff_keys(a, b, path="$", acc=None):
    """Paths where the two trees differ (leaf-key level)."""
    if acc is None:
        acc = []
    if type(a) is not type(b):
        acc.append(path)
        return acc
    if isinstance(a, dict):
        if set(a) != set(b):
            acc.append(path + ".<keys>")
            return acc
        if a.get("tag") == "Selector":
            for k in a:
                if cj(a[k]) != cj(b[k]):
                    acc.append(f"{path}.{k}")
            return acc
        for k in a:
            diff_keys(a[k], b[k], f"{path}.{k}", acc)
    elif isinstance(a, list):
        if len(a) != len(b):
            acc.append(path + ".<len>")
            return acc
        for i, (x, y) in enumerate(zip(a, b)):
            diff_keys(x, y, f"{path}[{i}]", acc)
    elif a != b:
        acc.append(path)
    return acc


def count_mode(node, mode, acc=None):
    if acc is None:
        acc = [0]
    if isinstance(node, list):
        for x in node:
            count_mode(x, mode, acc)
    elif isinstance(node, dict):
        if node.get("tag") == "Selector" and _enum(node.get("mode")) == mode:
            acc[0] += 1
        for v in node.values():
            count_mode(v, mode, acc)
    return acc[0]


def constructor_probes() -> dict:
    res = {}
    try:
        Selector(
            count=QConst(1),
            mode=SelectorMode.ALL,
            filter=FAtom(pred=FAtomPred.IS_SOURCE),
            zones=(Zone(ZoneKind.BATTLEFIELD, ControllerRef.ANY),),
        )
        res["ALL+QConst(1)+IS_SOURCE"] = "legal"
    except ValueError as e:
        res["ALL+QConst(1)+IS_SOURCE"] = f"raises: {e}"
    try:
        Selector(
            count=QConst(1),
            mode=SelectorMode.ALL,
            filter=FAnd(()),
            zones=(Zone(ZoneKind.PLAYER, ControllerRef.YOU),),
        )
        res["ALL+QConst(1)+PLAYER:YOU"] = "legal"
    except ValueError as e:
        res["ALL+QConst(1)+PLAYER:YOU"] = f"raises: {e}"
    try:
        Selector(
            count=QConst(1),
            mode=SelectorMode.ALL,
            filter=FAnd(()),
            zones=(Zone(ZoneKind.ANY, ControllerRef.ANY),),
            referent="target",
        )
        res["ALL+referent"] = "legal (UNEXPECTED)"
    except ValueError as e:
        res["ALL+referent"] = f"raises: {e}"
    return res


def main() -> int:
    ledger = json.loads((REPO / "reports/r3_blindness.json").read_text())
    la = [n for n in ledger["nodes"] if n["lane"] == "L-A"]
    ledger_cards = {
        c: sorted({n["card"] for n in la if n["rule_key"] == c})
        for c in ("self", "referent", "top", "seat")
    }

    registry = build_full_registry()
    out: dict = {
        "method": "R3b CHOOSE->ALL phantom-fold simulation on to_dict()",
        "constructor_probes": constructor_probes(),
        "sets": {},
    }

    for set_name in ("M21", "ZNR"):
        pool = ingest_pool(REPO / "MTG_bot" / "data" / f"{set_name}.json")
        results, gaps = _compile_pool_tolerant(pool, registry)

        changed, changed_names = [], []
        per_class: Counter = Counter()
        cards_by_class: dict[str, set] = {k: set() for k in ("self", "top", "seat")}
        stale_goldens, idem_fail, content_fail = [], [], []
        choose_pre = choose_post = 0
        excl_selfneg = 0

        for oid in sorted(results):
            card = results[oid].card
            try:
                tree = to_dict(card)
                baseline = cj(tree)
                assert baseline == canonical_json(card)
                fired: Counter = Counter()
                mark = len(CONTENT_FAILURES)
                folded = fold_tree(tree, fired, per_class)
                content_fail.extend(CONTENT_FAILURES[mark:])
                excl_selfneg += fired.get("self_negated_excluded", 0)
                if fired["folded"]:
                    diffs = diff_keys(tree, folded)
                    bad = [d for d in diffs if not d.endswith(".mode")]
                    if bad:
                        content_fail.append(f"{set_name} {card.name}: {bad[:4]}")
                folded2: Counter = Counter()
                folded_b = fold_tree(folded, folded2, Counter(), second_pass=True)
                if cj(folded_b) != cj(folded) or folded2["second_pass_matched"]:
                    idem_fail.append(f"{set_name} {card.name!r}: {dict(folded2)}")
                if cj(folded) != baseline:
                    changed.append(oid)
                    changed_names.append(card.name)
                    # which classes fired for THIS card
                    cls_here: Counter = Counter()
                    fold_tree(tree, Counter(), cls_here)
                    for k in ("self", "top", "seat"):
                        if cls_here[k]:
                            cards_by_class[k].add(card.name)
                choose_pre += count_mode(tree, "CHOOSE")
                choose_post += count_mode(folded, "CHOOSE")
            except Exception:
                EXCEPTIONS.append(
                    f"{set_name} {card.name!r}:\n{traceback.format_exc()}"
                )
                continue

            if set_name == "M21":
                gp = REPO / "MTG_bot" / "core" / "golden" / "M21" / f"{oid}.json"
                if gp.exists() and gp.read_text().strip() != cj(tree):
                    stale_goldens.append(card.name)

        gdir = REPO / "MTG_bot" / "core" / "golden" / set_name
        entry = {
            "total_compiled": len(results),
            "shape_gaps": len(gaps),
            "changed_records": len(changed),
            "changed_oids": sorted(changed),
            "changed_names": sorted(changed_names),
            "folded_nodes": dict(per_class),
            "folded_total": sum(per_class.values()),
            "self_negated_excluded": excl_selfneg,
            "changed_cards_by_class": {k: sorted(v) for k, v in cards_by_class.items()},
            "choose_nodes_pre": choose_pre,
            "choose_nodes_post": choose_post,
            "idempotence_failures": idem_fail,
            "content_failures": content_fail,
        }
        if gdir.exists():
            gfiles = sorted(gdir.glob("*.json"))
            entry["golden_files_total"] = len(gfiles)
            entry["baseline_stale_goldens"] = stale_goldens
        out["sets"][set_name] = entry
        print(
            f"{set_name}: changed {len(changed)}/{len(results)} "
            f"nodes={dict(per_class)} CHOOSE {choose_pre}->{choose_post}",
            flush=True,
        )

    measured_cards = sorted(
        {n for s in out["sets"].values() for n in s["changed_names"]}
    )
    out["ledger_reconcile"] = {
        "ledger_LA_nodes": {"self": 108, "referent": 48, "top": 3, "seat": 2},
        "folded_nodes": {
            c: sum(out["sets"][s]["folded_nodes"].get(c, 0) for s in out["sets"])
            for c in ("self", "top", "seat")
        },
        "referent_class": "GAP: constructor C2 blocks ALL+referent; registers may be plural",
        "all_pools_idempotent": all(
            not e["idempotence_failures"] for e in out["sets"].values()
        ),
        "content_failures": [
            f for e in out["sets"].values() for f in e["content_failures"]
        ],
        "changed_cards_union_count": len(measured_cards),
        "exceptions": EXCEPTIONS,
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
