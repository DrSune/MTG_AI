#!/usr/bin/env python3
"""R1a sort-delta re-measurement under normalization N-v4.

N-v4 (R0/R1b EXCLUDED — no Selector.zone/zones, no Cost.parts, no
SpellAbility.additional_costs, no CostManaHybrid.colors):
  (i)  FAnd/FOr: recurse children FIRST; exactly-1-child -> replace node by
       that child (unwrap); same-class child -> splice in (flatten); then
       sort children by canonical_json.
  (ii) construction-sort (recursively, by canonical_json) ONLY:
       CardRecord.keywords (kwds_sort),
       TokenSpec.{types,subtypes,keywords} (tokenspec_sort),
       FAtom.colors (fatom_colors_sort),
       EtBState.initial_counters (counters_sort).
       AtomArgs.pairs is already constructor-sorted: verified no-op here.
  (iii) everything else unchanged.

Pools compiled exactly like the predecessor (mk_r1a_sortdelta.py):
ingest_pool + build_full_registry + coverage._compile_pool_tolerant.
Checks: idempotence (N(N(c)) == N(c) by canonical_json) and content
preservation (multiset of canonical_json of every dataclass leaf node, and
multiset of every Atom node, invariant under N).

Writes reports/atom_sortdelta_2026-10-19.json (repo-relative to this file).
"""

from __future__ import annotations

import dataclasses
import json
import sys
import traceback
from collections import Counter
from enum import Enum
from pathlib import Path

REPO = Path("/home/sune/Desktop/MTG_AI")
sys.path.insert(0, str(REPO))

from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.ability_tree import canonical_json  # noqa: E402
from MTG_bot.core.compiler.coverage import (  # noqa: E402
    _compile_pool_tolerant,
    build_full_registry,
)
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402

FAnd, FOr = at.FAnd, at.FOr
CardRecord, TokenSpec, FAtom, EtBState, AtomArgs = (
    at.CardRecord,
    at.TokenSpec,
    at.FAtom,
    at.EtBState,
    at.AtomArgs,
)

# class -> (field -> rule token) construction-sort targets of N-v4
SORT_RULES: dict[type, dict[str, str]] = {
    CardRecord: {"keywords": "kwds_sort"},
    TokenSpec: {
        "types": "tokenspec_sort",
        "subtypes": "tokenspec_sort",
        "keywords": "tokenspec_sort",
    },
    FAtom: {"colors": "fatom_colors_sort"},
    EtBState: {"initial_counters": "counters_sort"},
}

RULE_KEYS = (
    "fand_order",
    "or_order",
    "fand_flatten_single",
    "fand_flatten_nested",
    "or_flatten_single",
    "or_flatten_nested",
    "kwds_sort",
    "tokenspec_sort",
    "fatom_colors_sort",
    "counters_sort",
)

EXCEPTIONS: list[str] = []
PAIRS_NOT_SORTED: list[str] = []  # AtomArgs.pairs must already be sorted (0)


def _rebuild(obj, changes: dict, ctx: str):
    try:
        return dataclasses.replace(obj, **changes)
    except Exception as exc:  # noqa: BLE001 — verbatim per exit criteria
        EXCEPTIONS.append(
            f"{ctx}: replace({type(obj).__name__}, {sorted(changes)}): {exc!r}"
        )
        return obj


def norm(obj, fired: Counter, ctx: str):
    """Rebuild the frozen IR under N-v4; `fired` counts rule firings."""
    if obj is None or isinstance(obj, (Enum, str, int, float, bool)):
        return obj
    if isinstance(obj, (tuple, list)):
        return type(obj)(norm(x, fired, ctx) for x in obj)
    if isinstance(obj, (frozenset, set)):
        return type(obj)(norm(x, fired, ctx) for x in obj)
    if not (dataclasses.is_dataclass(obj) and not isinstance(obj, type)):
        return obj

    cls = type(obj)
    changes = {}
    for f in dataclasses.fields(obj):
        val = getattr(obj, f.name)
        nv = norm(val, fired, f"{ctx}.{f.name}")
        if nv != val:
            changes[f.name] = nv

    if cls in (FAnd, FOr):
        tag = "fand" if cls is FAnd else "or"
        kids = list(changes.get("children", obj.children))
        while True:
            if len(kids) == 1:
                fired[f"{tag}_flatten_single"] += 1
                return kids[0]
            if any(type(k) is cls for k in kids):
                kids = [
                    x
                    for k in kids
                    for x in (list(k.children) if type(k) is cls else [k])
                ]
                fired[f"{tag}_flatten_nested"] += 1
                continue
            break
        srt = sorted(kids, key=canonical_json)
        if any(a is not b for a, b in zip(kids, srt)):
            fired[f"{tag}_order"] += 1
        kids = tuple(srt)
        if kids != obj.children:
            changes["children"] = kids
    else:
        for fld, token in SORT_RULES.get(cls, {}).items():
            items = list(changes.get(fld, getattr(obj, fld)))
            srt = sorted(items, key=canonical_json)
            if any(a is not b for a, b in zip(items, srt)):
                fired[token] += 1
            if tuple(srt) != getattr(obj, fld):
                changes[fld] = tuple(srt)
        if cls is AtomArgs:
            pairs = changes.get("pairs", obj.pairs)
            if sorted(pairs, key=canonical_json) != list(pairs):
                PAIRS_NOT_SORTED.append(ctx)

    if not changes:
        return obj
    return _rebuild(obj, changes, ctx)


def _contains_dc(v) -> bool:
    """True if v is, or containers of v contain, a dataclass instance."""
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return True
    if isinstance(v, (tuple, list, frozenset, set)):
        return any(_contains_dc(x) for x in v)
    return False


def content_key(card):
    """(leaf-node multiset, Atom multiset) as sorted canonical_json lists.

    N-v4 only reorders / re-parents; it never creates or destroys a leaf
    dataclass node (unwrap/flatten only remove FAnd/FOr wrappers, which are
    non-leaf) nor any Atom — so both multisets must be invariant.
    Comparison happens on the NORMALIZED form of each collected node: a
    node's own canonical_json legitimately changes when a set-classified
    container inside it (FAnd children, FAtom.colors) is sorted, so the
    content invariant is multiset-of-NORMALIZED-leaves / -atoms."""
    leaves: list[str] = []
    atoms: list[str] = []
    for node in at.walk(card):
        if isinstance(node, at.Atom):
            atoms.append(canonical_json(norm(node, Counter(), "content")))
        if not any(
            _contains_dc(getattr(node, f.name)) for f in dataclasses.fields(node)
        ):
            leaves.append(canonical_json(norm(node, Counter(), "content")))
    return sorted(leaves), sorted(atoms)


def main() -> int:
    registry = build_full_registry()
    out: dict = {"sets": {}, "exceptions": None}
    golden_dir = REPO / "MTG_bot" / "core" / "golden" / "M21"

    for set_name in ("M21", "ZNR"):
        pool = ingest_pool(REPO / "MTG_bot" / "data" / f"{set_name}.json")
        results, gaps = _compile_pool_tolerant(pool, registry)

        changed: list[dict] = []
        fired_cards: dict[str, list[str]] = {k: [] for k in RULE_KEYS}
        idem_fail: list[str] = []
        content_fail: list[str] = []

        for oid in sorted(results):
            card = results[oid].card
            fired: Counter = Counter()
            try:
                ncard = norm(card, fired, oid)
                # idempotence: N(N(c)) must be identical to N(c)
                fired2: Counter = Counter()
                nn = norm(ncard, fired2, oid)
                if canonical_json(ncard) != canonical_json(nn) or fired2:
                    idem_fail.append(f"{oid} ({card.name!r}): refire={dict(fired2)}")
                # content preservation: leaf + Atom multisets invariant
                if content_key(card) != content_key(ncard):
                    content_fail.append(f"{oid} ({card.name!r})")
            except Exception:  # noqa: BLE001
                EXCEPTIONS.append(f"N({card.name!r} {oid}):\n{traceback.format_exc()}")
                continue
            for k in fired:
                if k in fired_cards and oid not in fired_cards[k]:
                    fired_cards[k].append(oid)
            if canonical_json(card) != canonical_json(ncard):
                changed.append({"oracle_id": oid, "name": card.name})

        by_rule = {k: len(v) for k, v in fired_cards.items()}
        # map fired rule cards to names for auditability
        name_of = {oid: results[oid].card.name for oid in results}
        entry = {
            "changed_count": len(changed),
            "total": len(results),
            "shape_gaps": len(gaps),
            "by_change_kind": by_rule,
            "by_change_kind_card_names": {
                k: sorted(name_of[oid] for oid in v) for k, v in fired_cards.items()
            },
            "changed_card_names": [c["name"] for c in changed],
            "idempotence_failures": idem_fail,
            "content_preservation_failures": content_fail,
        }

        if set_name == "M21":
            files = {p.name for p in golden_dir.glob("*.json")}
            gmap, missing = [], []
            for c in changed:
                fn = f"{c['oracle_id']}.json"
                if fn in files:
                    gmap.append(
                        {
                            "golden_file": f"MTG_bot/core/golden/M21/{fn}",
                            "card_name": c["name"],
                        }
                    )
                else:
                    missing.append(fn)
            entry["m21_golden_map"] = {
                "golden_dir": str(golden_dir),
                "golden_files_total": len(files),
                "golden_files_to_rebaseline": gmap,
                "changed_cards_without_golden_file": missing,
            }

        out["sets"][set_name] = entry
        print(
            f"{set_name}: changed {entry['changed_count']}/{entry['total']} "
            f"by_rule={by_rule} idem_fail={len(idem_fail)} "
            f"content_fail={len(content_fail)}",
            flush=True,
        )

    out["atomargs_pairs_not_sorted_ctxs"] = PAIRS_NOT_SORTED
    out["exceptions"] = EXCEPTIONS
    dest = (
        Path(__file__).resolve().parents[2]
        / "reports"
        / "atom_sortdelta_2026-10-19.json"
    )
    dest.write_text(json.dumps(out, indent=2))
    print(f"wrote {dest}; exceptions: {len(EXCEPTIONS)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
