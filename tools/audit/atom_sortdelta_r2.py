#!/usr/bin/env python3
"""R2 F4 damage-fold byte-delta PRE-REGISTRATION (measurement-only; NO repo
edit; reads repo, writes reports/r2_sortdelta.json (repo-relative)).

Pattern precedent: tools/audit/atom_sortdelta_r1b.py.

FOLD RULE F4: every compiled CombatDamageEvent(filter=F) canonicalizes to
  DamageDealtEvent(amount=QUnbounded, filter=FAnd(()), source=F, combat=True)
— exactly the shape Garruk's Harbinger / Subira already compile to; the
empty-FAnd recipient is the grammar's own universal marker (executor
_is_universal, binding.py:177). Behavior-preserving: today's CDE lane
(binding.py:875) evaluates ONLY the dealer filter (no recipient check), so
filter=FAnd() preserves the folded cards' current semantics; making
"to a player" faithful is a SEPARATE engine-lane step (DEFER), not this fold.

Checks:
  (1) exact changed-cards name sets per pool (expected: Jeskai Elder,
      Feline Sovereign [M21]; Nimble Trapfinder [ZNR]);
  (2) content preservation: dealer filter subtree moves VERBATIM from
      CDE.filter to DDE.source; any lost leaf = LOUD failure; the only
      allowed gains are the canonical shell per fold;
  (3) idempotence: fold(fold(tree)) == fold(tree), zero second-pass firings;
  (4) convergence proof: post-fold Jeskai Elder event bytes == Garruk's
      Harbinger event bytes VERBATIM;
  (5) M21 golden-file exposure for the changed set;
  (6) population census: CDE counts, DDE by combat value.

Output: Path(__file__).resolve().parents[2] / "reports" / "r2_sortdelta.json".
"""

from __future__ import annotations

from pathlib import Path
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

CONTENT_FAILURES: list[str] = []
IDEM_FAILURES: list[str] = []
EXCEPTIONS: list[str] = []

EMPTY_FAND = {"children": [], "tag": "FAnd"}


def cj(v) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


def is_tag(node, tag: str) -> bool:
    return isinstance(node, dict) and node.get("tag") == tag


def fold_node(cde: dict) -> dict:
    return {
        "tag": "DamageDealtEvent",
        "amount": {"tag": "QUnbounded"},
        "filter": copy.deepcopy(EMPTY_FAND),
        "source": copy.deepcopy(cde["filter"]),
        "combat": True,
    }


def fold_tree(node, fired: Counter, second_pass=False):
    if isinstance(node, list):
        return [fold_tree(x, fired, second_pass) for x in node]
    if not isinstance(node, dict):
        return node
    if is_tag(node, "CombatDamageEvent"):
        if not second_pass:
            fired["cde_fold"] += 1
        node = fold_node(node)  # second pass can never re-match: not a CDE
    return {k: fold_tree(v, fired, second_pass) for k, v in node.items()}


def content_multiset(node, acc: Counter):
    """Multiset of subtree identities, FAtoms keyed by full bytes, others by
    tag; CDE roots are marked so their filter content is followed but the
    root identity itself is excluded from the before/after comparison."""
    if isinstance(node, list):
        for x in node:
            content_multiset(x, acc)
        return
    if not isinstance(node, dict):
        return
    tag = node.get("tag")
    if tag == "CombatDamageEvent":
        acc["<<CDE_ROOT>>"] += 1
    elif tag == "FAtom":
        acc[cj(node)] += 1
    elif tag:
        acc[f"<{tag}>"] += 1
    for k, v in node.items():
        if k == "tag":
            continue
        content_multiset(v, acc)


def iter_tag(node, tag: str):
    if isinstance(node, list):
        for x in node:
            yield from iter_tag(x, tag)
    elif isinstance(node, dict):
        if node.get("tag") == tag:
            yield node
        else:
            for v in node.values():
                yield from iter_tag(v, tag)


def main():
    registry = build_full_registry()
    out: dict = {
        "rule": "CDE{F} -> DDE(amount=QUnbounded, filter=FAnd(()), source=F, combat=True)"
    }
    post_fold_events: dict[str, list[str]] = {}

    for set_name in ("M21", "ZNR"):
        pool = ingest_pool(REPO / "MTG_bot" / "data" / f"{set_name}.json")
        results, gaps = _compile_pool_tolerant(pool, registry)
        changed: list[str] = []
        changed_names: list[str] = []
        idem_fail: list[str] = []
        content_fail: list[str] = []
        fired_all: Counter = Counter()
        dde_combat: Counter = Counter()

        for oid in sorted(results):
            card = results[oid].card
            try:
                tree = to_dict(card)
                baseline = cj(tree)
                assert baseline == canonical_json(card)
                for n in iter_tag(tree, "DamageDealtEvent"):
                    dde_combat[f"combat={n.get('combat', 'ABSENT')}"] += 1
                fired: Counter = Counter()
                mark = len(CONTENT_FAILURES)
                folded = fold_tree(copy.deepcopy(tree), fired)
                content_fail.extend(CONTENT_FAILURES[mark:])

                if fired["cde_fold"]:
                    b2: Counter = Counter()
                    a2: Counter = Counter()
                    content_multiset(tree, b2)
                    content_multiset(folded, a2)
                    b2.pop("<<CDE_ROOT>>", None)
                    a2.pop("<<CDE_ROOT>>", None)
                    lost = b2 - a2
                    gained = a2 - b2
                    if lost:
                        content_fail.append(f"{card.name}: lost {dict(lost)}")
                    shell = Counter(
                        {
                            "<DamageDealtEvent>": fired["cde_fold"],
                            "<QUnbounded>": fired["cde_fold"],
                            "<FAnd>": fired["cde_fold"],
                        }
                    )
                    undeclared = Counter(
                        {k: v for k, v in (gained - shell).items() if v > 0}
                    )
                    if undeclared:
                        content_fail.append(
                            f"{card.name}: undeclared gain {dict(undeclared)}"
                        )
                    post_fold_events[f"{set_name}|{card.name}"] = [
                        cj(n) for n in iter_tag(folded, "DamageDealtEvent")
                    ]

                fired2: Counter = Counter()
                folded2 = fold_tree(copy.deepcopy(folded), fired2, second_pass=True)
                if cj(folded2) != cj(folded) or fired2:
                    idem_fail.append(f"{set_name} {card.name!r}: refire={dict(fired2)}")

                if cj(folded) != baseline:
                    changed.append(oid)
                    changed_names.append(card.name)
                    fired_all.update(fired)
            except Exception:
                EXCEPTIONS.append(
                    f"{set_name} {card.name!r}:\n{traceback.format_exc()}"
                )
                continue

        entry = {
            "changed_count": len(changed),
            "changed_oids": sorted(changed),
            "changed_names": sorted(changed_names),
            "total_compiled": len(results),
            "shape_gaps": len(gaps),
            "folds": dict(fired_all),
            "dde_by_combat": dict(dde_combat),
            "idempotence_failures": idem_fail,
            "content_failures": content_fail,
        }
        if set_name == "M21":
            gdir = REPO / "MTG_bot" / "core" / "golden" / "M21"
            entry["golden_files_total"] = len(list(gdir.glob("*.json")))
            entry["goldens_flagged"] = sorted(
                oid for oid in changed if (gdir / f"{oid}.json").exists()
            )
            entry["goldens_flagged_names"] = sorted(changed_names)
        out.setdefault("sets", {})[set_name] = entry
        print(
            f"{set_name}: changed {len(changed)}/{len(results)} {sorted(changed_names)}"
        )

    # convergence proof: post-fold Jeskai == untouched Garruk's Harbinger
    harbinger_bytes: str | None = None
    pool = ingest_pool(REPO / "MTG_bot" / "data" / "M21.json")
    results, _ = _compile_pool_tolerant(pool, registry)
    for oid, r in results.items():
        if r.card.name == "Garruk's Harbinger":
            harbinger_bytes = next(
                cj(n) for n in iter_tag(to_dict(r.card), "DamageDealtEvent")
            )
    jes = post_fold_events.get("M21|Jeskai Elder", [])
    out["convergence"] = {
        "harbinger_event_bytes": harbinger_bytes,
        "jeskai_post_fold_event_bytes": jes,
        "byte_equal": bool(harbinger_bytes)
        and len(jes) == 1
        and jes[0] == harbinger_bytes,
    }
    out["idempotence_all_pass"] = (
        all(not s["idempotence_failures"] for s in out["sets"].values())
        and not IDEM_FAILURES
    )
    out["content_all_pass"] = (
        all(not s["content_failures"] for s in out["sets"].values())
        and not CONTENT_FAILURES
    )
    out["exceptions"] = EXCEPTIONS
    _dest = Path(__file__).resolve().parents[2] / "reports" / "r2_sortdelta.json"
    _dest.write_text(json.dumps(out, indent=1))
    print(
        f"wrote {_dest}; "
        f"conv={out['convergence']['byte_equal']} "
        f"idem={out['idempotence_all_pass']} content={out['content_all_pass']} "
        f"exc={len(EXCEPTIONS)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
