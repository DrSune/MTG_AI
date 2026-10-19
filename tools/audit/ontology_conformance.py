#!/usr/bin/env python3
"""ATOMIC-ONTOLOGY conformance checker — docs/DESIGN_ATOM_ONTOLOGY.md §6.

Read-only pool pass (M21 + ZNR compiled IR). NEVER uses
``ability_tree.walk()``: ``_walk_value`` (:4704) skips plain lists, so a
walk-based audit would silently miss list-valued fields — this module does
its own recursion over dataclass fields, tuples, lists and frozensets.

Checks (ontology §6):
  V1′ FIELD-COVERAGE  ERROR  every runtime container field has a CLASSIFY
                     token and no CLASSIFY entry is stale. The CLASSIFY dict
                     is IMPORTED from tools/audit/atom_field_table.py (single
                     source; the same module regenerates the §3 table), so
                     doc/code duplication is structurally impossible.
  V2′ PHANTOM         ERROR  Seq[1] / single-child FAnd-FOr /
                     Choose(count == len(options)). The R1a construction rule
                     keeps a single-child filter node (a node cannot replace
                     itself in its parent), so this check is what forbids the
                     EMISSION of new phantoms; the unwrap lives at the
                     compiler filter builders. A measured corpus shape that
                     the owner has ruled acceptable may be whitelisted by card
                     name in ``ontology_conformance_whitelist.json`` (the file
                     ships with this checker; every whitelisted name is
                     re-printed on every run — a whitelist is never silent).
  V3′ SPLIT           WARN   two steps of one Seq carrying BYTE-IDENTICAL
                     fresh (referent-free) TARGET-mode Selectors — the
                     canonical form re-uses the referent-bound selector (C2
                     :1180). ALL/ONE_OF/REST/referent modes are excluded
                     (legal identical repeats: independent designations,
                     all-of loops). Corpus has 0 true positives, so the check
                     ships with SYNTHETIC FIXTURES
                     (tools/audit/test_ontology_conformance.py, gate A3).
  V4′ EMISSION FREEZE ERROR  no NEW SelectorMode.CHOOSE node in the COMPILED
                     IR (not template source text — compiler.py:1242/1280/1292
                     generic lanes emit CHOOSE without the token appearing in
                     a template diff, gate A4). Baseline
                     ``ontology_conformance_v4_baseline.json``, per card.
  V5′ MAP DRIFT       WARN   a compiled shape (ability STRUCT signature or
                     branching triple) with no §5 map row. Map rows live in
                     reports/ontology_census_2026-10-19.json; this is a
                     report-only delta against that committed baseline
                     (registration law: a new branching needs a dated,
                     card-cited map row + NUMBERS count in the same commit).

Exit 1 iff any ERROR-class violation; WARNs are reported and counted only.
Gate law: template rounds carry checker Δ0 (V1′/V2′/V4′) + Δreview (V3′/V5′).

Run::

    .venv/bin/python tools/audit/ontology_conformance.py            # both pools
    .venv/bin/python tools/audit/ontology_conformance.py --out reports/x.json
    .venv/bin/python tools/audit/ontology_conformance.py --write-v4-baseline
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from MTG_bot.core import ability_tree as at
from MTG_bot.core.ability_tree import canonical_json
from MTG_bot.core.compiler.coverage import (
    _compile_pool_tolerant,
    build_full_registry,
)
from MTG_bot.core.compiler.ingest import ingest_pool

# V1′ single source: the same module that regenerates the §3 table.
from tools.audit.atom_field_table import (
    CLASSIFY,
    runtime_container_fields,
)

WHITELIST = HERE / "ontology_conformance_whitelist.json"
V4_BASELINE = HERE / "ontology_conformance_v4_baseline.json"
CENSUS = REPO / "reports" / "ontology_census_2026-10-19.json"

# R1a wave: uncapped (``--cap 0``) census artefacts compiled from the SAME
# card pools with the PRE- and POST-R1a compiler code. Their order-canonical
# diff is the R1a-attributable MAP DELTA, free of the committed census'
# ``most_common(40)`` row truncation (which inflates the live-vs-committed
# branching view with ~54 long-tail rows — see V5 note there).
CENSUS_R1A_PRE_FULL = REPO / "reports" / "ontology_census_2026-10-19_r1a_pre_full.json"
CENSUS_R1A_POST_FULL = (
    REPO / "reports" / "ontology_census_2026-10-19_r1a_post_full.json"
)
SETS = ("M21", "ZNR")


# ---------------------------------------------------------------------------
# traversal (never ability_tree.walk(): _walk_value skips lists)
# ---------------------------------------------------------------------------
def iter_nodes(obj):
    """Yield every dataclass node in ``obj``'s tree (fields, tuples, lists,
    frozensets, Optionals) — pre-order, self included."""
    if isinstance(obj, (tuple, list, frozenset, set)):
        for x in obj:
            yield from iter_nodes(x)
        return
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        yield obj
        for f in dataclasses.fields(obj):
            yield from iter_nodes(getattr(obj, f.name))


def compile_pools(sets=SETS):
    """set -> {"cards": oracle_id -> CardRecord, "gaps": int, "emblem_oids":
    set} — the same tolerant compile pass as tools/audit/atom_sortdelta.py and
    the shape census. ``emblem_oids`` mirrors the census' exclusion (an emblem
    is attached into its owner's record, so counting it as a card of its own
    would inflate every shape census against the committed baseline)."""
    registry = build_full_registry()
    out = {}
    for s in sets:
        pool = ingest_pool(REPO / "MTG_bot" / "data" / f"{s}.json")
        results, gaps = _compile_pool_tolerant(pool, registry)
        out[s] = {
            "cards": {oid: r.card for oid, r in results.items()},
            "gaps": len(gaps),
            "emblem_oids": {
                oid for oid, raw in pool.items() if getattr(raw, "is_emblem", False)
            },
        }
    return out


# ---------------------------------------------------------------------------
# V1′ field coverage
# ---------------------------------------------------------------------------
def check_v1():
    runtime = runtime_container_fields()
    unclassified = sorted(k for k in runtime if k not in CLASSIFY)
    stale = sorted(k for k in CLASSIFY if k not in runtime)
    return {
        "container_fields": len(runtime),
        "classify_tokens": len(CLASSIFY),
        "unclassified": [f"{c}.{f}" for c, f in unclassified],
        "stale": [f"{c}.{f}" for c, f in stale],
    }


# ---------------------------------------------------------------------------
# V2′ phantom wrappers
# ---------------------------------------------------------------------------
def _choose_is_phantom(node) -> bool:
    """``Choose(count == len(options))`` — the phantom menu (F8): choosing all
    of a fixed menu is not a decision; it must be encoded ALL."""
    return (
        isinstance(node.count, at.QConst)
        and not isinstance(node.count.value, bool)
        and node.count.value == len(node.options)
    )


def check_v2(cards_by_set, whitelist):
    seq1, filt1, phantom = [], [], []
    for s, cards in cards_by_set.items():
        for card in cards.values():
            for n in iter_nodes(card):
                cls = type(n).__name__
                if cls == "Seq" and len(n.steps) == 1:
                    seq1.append(f"{s}:{card.name}")
                elif cls in ("FAnd", "FOr") and len(n.children) == 1:
                    filt1.append(f"{s}:{card.name}:{cls}")
                elif cls == "Choose" and _choose_is_phantom(n):
                    phantom.append(f"{s}:{card.name}")
    wl = set(whitelist.get("choose_count_eq_len", []))
    kept = [p for p in phantom if p.split(":", 1)[1] not in wl]
    whitelisted = [p for p in phantom if p.split(":", 1)[1] in wl]
    return {
        "seq_single_child": seq1,
        "filter_single_child": filt1,
        "choose_count_eq_len": kept,
        "choose_count_eq_len_whitelisted": whitelisted,
    }


# ---------------------------------------------------------------------------
# V3′ split-designation heuristic (WARN)
# ---------------------------------------------------------------------------
def _fresh_target_selectors(node):
    """Every TARGET-mode, referent-free Selector inside ``node`` (a fresh
    designation), as its canonical JSON."""
    out = []
    for n in iter_nodes(node):
        if (
            isinstance(n, at.Selector)
            and n.mode is at.SelectorMode.TARGET
            and not n.referent
        ):
            out.append(canonical_json(n))
    return out


def check_v3(cards_by_set):
    warns = []
    for s, cards in cards_by_set.items():
        for card in cards.values():
            for n in iter_nodes(card):
                if type(n).__name__ != "Seq" or len(n.steps) < 2:
                    continue
                seen = defaultdict(list)
                for i, step in enumerate(n.steps):
                    for blob in _fresh_target_selectors(step):
                        seen[blob].append(i)
                for blob, steps in seen.items():
                    if len(set(steps)) >= 2:
                        warns.append(
                            f"{s}:{card.name}: Seq steps {sorted(set(steps))} "
                            f"re-designate the same fresh TARGET selector "
                            f"{blob[:120]}"
                        )
    return {"split_seq_designations": warns}


# ---------------------------------------------------------------------------
# V4′ CHOOSE emission freeze (compiled IR diff)
# ---------------------------------------------------------------------------
def choose_census(cards_by_set):
    """set -> {card name: number of SelectorMode.CHOOSE selector nodes}."""
    out = {}
    for s, cards in cards_by_set.items():
        per = {}
        for card in cards.values():
            n = sum(
                1
                for x in iter_nodes(card)
                if isinstance(x, at.Selector) and x.mode is at.SelectorMode.CHOOSE
            )
            if n:
                per[card.name] = n
        out[s] = per
    return out


def _git_tracked(path: Path) -> bool:
    import subprocess

    r = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(path)],
        cwd=REPO,
        capture_output=True,
    )
    return r.returncode == 0


def check_v4(current, baseline, write_baseline: bool):
    """CHOOSE-emission freeze vs the baseline file.

    FAIL-CLOSED: a missing baseline is an ERROR (exit nonzero in main), never
    a silent empty diff — a fresh clone must not green-light new CHOOSE
    surfaces just because the artefact was not checked out."""
    if write_baseline:
        return {
            "baseline_written": True,
            "new_emissions": [],
            "total": _totals(current),
        }
    if not baseline.exists():
        return {
            "baseline_written": False,
            "baseline_missing": True,
            "new_emissions": [],
            "total": _totals(current),
        }
    base = json.loads(baseline.read_text())
    news = []
    for s, per in current.items():
        bper = base.get(s, {})
        for name, cnt in sorted(per.items()):
            if cnt > bper.get(name, 0):
                news.append(f"{s}:{name}: CHOOSE {bper.get(name, 0)} -> {cnt}")
    return {"baseline_written": False, "new_emissions": news, "total": _totals(current)}


def _totals(current):
    return {s: sum(per.values()) for s, per in current.items()}


# ---------------------------------------------------------------------------
# V5′ branching/shape map drift (WARN, report-only)
# ---------------------------------------------------------------------------
def _split_top(content: str, sep: str) -> list[str]:
    """Split ``content`` on ``sep`` at brace/bracket depth 0."""
    parts, depth, cur = [], 0, []
    for ch in content:
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


# census STRUCT renders every list field as ``name=[n]{elem;elem}``. Only the
# SET-R1a fields below may be re-sorted by the checker (order-free containers).
# ``steps=`` (TIME), Choose ``options=`` (MENU) and AtomArgs ``pairs=`` stay
# untouched — their order is semantic (§3 O2/MENU).
_SET_STRUCT_FIELDS = (
    "children",
    "colors",
    "keywords",
    "types",
    "subtypes",
    "initial_counters",
)


def _canon_struct_sig(sig: str) -> str:
    """Order-canonicalize a CENSUS STRUCT signature for SET-R1a fields: the
    ``;``-separated elements of every SET-R1a ``name=[n]{...}`` group
    (children/colors/keywords/types/subtypes/initial_counters) are sorted,
    innermost group first.

    Both sides of the V5′ diff go through this function, so a child that only
    MOVED (the R1a sort) can no longer register as a new shape; a shape that
    is genuinely new still does."""
    out: list[str] = []
    i = 0
    while True:
        hits = [(sig.find(f"{name}=[", i), name) for name in _SET_STRUCT_FIELDS]
        hits = [(j, n) for j, n in hits if j >= 0]
        if not hits:
            out.append(sig[i:])
            break
        j, fname = min(hits)
        try:
            open_b = sig.index("{", j)
        except ValueError:  # malformed fragment: leave it alone
            out.append(sig[i:])
            break
        depth, k = 0, open_b
        while k < len(sig):
            if sig[k] in "{[":
                depth += 1
            elif sig[k] in "}]":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        else:  # unbalanced: leave the remainder untouched
            out.append(sig[i:])
            break
        inner = _canon_struct_sig(sig[open_b + 1 : k])
        out.append(sig[i:open_b])
        out.append("{")
        out.append(";".join(sorted(_split_top(inner, ";"))))
        out.append("}")
        i = k + 1
    return "".join(out)


def _canon_fshape(text: str) -> str:
    """Order-canonicalize a census ``fshape()`` skeleton for SET-R1a fields.

    fshape renders a container as ``children[N]A|B|C`` with NO delimiters
    around the alternatives (nesting is carried by ``Class(...)`` parens), so
    the group has to be read with a paren-aware scan: alternatives are the
    ``|``-separated pieces at depth 0 after the header, each canonicalized
    recursively, then sorted. ``steps``/``options`` are untouched (TIME/MENU)."""
    out: list[str] = []
    i = 0
    while True:
        j = text.find("children[", i)
        if j < 0:
            out.append(text[i:])
            break
        k = text.index("]", j) + 1  # past [N]
        depth, end = 0, k
        parts: list[str] = []
        cur: list[str] = []
        while end < len(text):
            ch = text[end]
            if ch == "(":
                depth += 1
            elif ch == ")":
                if depth == 0:
                    break  # this closer is the group's own end
                depth -= 1
            if ch == "|" and depth == 0:
                parts.append("".join(cur))
                cur = []
            else:
                cur.append(ch)
            end += 1
        else:  # unbalanced: leave the remainder untouched
            out.append(text[i:])
            break
        parts.append("".join(cur))
        out.append(text[i:k])
        out.append("|".join(sorted(_canon_fshape(p) for p in parts)))
        out.append(")")  # re-emit the group closer we stopped on
        i = end + 1
    return "".join(out)


def _live_shapes(cards_by_set):
    """(struct-sig set, per-class branching triple set) recomputed with the
    CENSUS module's own machinery (single source for what a 'shape' is)."""
    from tools.audit.ontology_shape_census import sig_struct, traverse

    sigs, branches = set(), defaultdict(set)
    for entry in cards_by_set.values():
        cards = (
            entry["cards"] if isinstance(entry, dict) and "cards" in entry else entry
        )
        skip = entry.get("emblem_oids", set()) if isinstance(entry, dict) else set()
        for oid, card in cards.items():
            if oid in skip:
                continue
            abilities = list(card.abilities) + list(card.keywords)
            if card.emblem is not None:
                abilities += list(card.emblem.abilities) + list(card.emblem.keywords)
            for ab in abilities:
                sig = sig_struct(ab)
                sigs.add(sig)
                # traverse(node, path, card, struct_sig, seq_stats, branches,
                #          verb_roles, order_rec) — census accumulators are
                #                branches[cls][(menu, count_kind, children)] += 1
                # so a per-call Counter is enough to harvest the triples.
                harvested: dict = defaultdict(Counter)
                traverse(
                    ab,
                    "",
                    card.name,
                    sig,
                    {"multi": 0, "single": 0, "by_parent": []},
                    harvested,
                    defaultdict(lambda: defaultdict(Counter)),
                    {},
                )
                for cls, counter in harvested.items():
                    branches[cls] |= set(counter)
    return sigs, branches


def _r1a_map_delta():
    """R1a-attributable census map delta: FULL (uncapped) census artefacts of
    the same pools compiled with PRE- vs POST-R1a code, diffed after the
    SET-R1a order canonicalizers so only CONTENT shape changes remain (the
    two emission-site unwraps). Unavailable on a checkout without the two
    artefacts — the checker never generates them itself."""
    if not (CENSUS_R1A_PRE_FULL.exists() and CENSUS_R1A_POST_FULL.exists()):
        return {"available": False}
    pre = json.loads(CENSUS_R1A_PRE_FULL.read_text())
    post = json.loads(CENSUS_R1A_POST_FULL.read_text())

    def structs(d):
        return {_canon_struct_sig(v["struct"]) for v in d["signatures"].values()}

    def branch(d):
        return {
            cls: {
                (
                    _canon_fshape(r["menu"]),
                    r["count_kind"],
                    tuple(_canon_fshape(c) for c in r["children"]),
                )
                for r in rows
            }
            for cls, rows in d["C_branching"]["branchings"].items()
        }

    new_sigs = sorted(structs(post) - structs(pre))
    gone_sigs = sorted(structs(pre) - structs(post))
    bp, bq = branch(pre), branch(post)

    def rows(a, b):
        return {
            cls: sorted(
                f"{m} / {c} / {list(k)}"
                for m, c, k in (b.get(cls, set()) - a.get(cls, set()))
            )
            for cls in sorted(set(a) | set(b))
            if b.get(cls, set()) - a.get(cls, set())
        }

    nb, gb = rows(bp, bq), rows(bq, bp)
    return {
        "available": True,
        "pre": str(CENSUS_R1A_PRE_FULL.relative_to(REPO)),
        "post": str(CENSUS_R1A_POST_FULL.relative_to(REPO)),
        "note": (
            "uncapped censuses, both order-canonicalized: content delta only "
            "(the FAnd single-child unwrap at its two emission sites)"
        ),
        "new_struct_sigs": new_sigs,
        "gone_struct_sigs": gone_sigs,
        "new_branchings": nb,
        "gone_branchings": gb,
        "new_struct_sig_count": len(new_sigs),
        "gone_struct_sig_count": len(gone_sigs),
        "new_branching_count": sum(len(v) for v in nb.values()),
        "gone_branching_count": sum(len(v) for v in gb.values()),
    }


def check_v5(cards_by_set):
    if not CENSUS.exists():
        return {"available": False}
    base = json.loads(CENSUS.read_text())
    base_sigs = {_canon_struct_sig(c["struct"]) for c in base["A_clusters"]}
    base_branch = {
        cls: {
            # every element of the triple goes through the SET-R1a order
            # canonicalizers, so the row-delta measures SHAPE drift, not the
            # R1a child sort (both sides of the diff, same rule).
            (
                _canon_fshape(row["menu"]),
                row["count_kind"],
                tuple(_canon_fshape(c) for c in row["children"]),
            )
            for row in rows
        }
        for cls, rows in base["C_branching"]["branchings"].items()
    }
    live_sigs, live_branch = _live_shapes(cards_by_set)
    live_sigs = {_canon_struct_sig(s) for s in live_sigs}
    live_branch = {
        cls: {
            (
                _canon_fshape(menu),
                cnt,
                tuple(_canon_fshape(k) for k in kids),
            )
            for menu, cnt, kids in rows
        }
        for cls, rows in live_branch.items()
    }
    new_sigs = sorted(live_sigs - base_sigs)
    gone_sigs = sorted(base_sigs - live_sigs)
    # Branching rows embed the census' fshape skeleton; both sides go through
    # _canon_fshape, so a row that only RE-ORDERED SET-R1a children cannot
    # register as new (registration law applies to a real new branching).
    new_branch = {
        cls: sorted(
            f"{menu} / {cnt} / {list(kids)}"
            for menu, cnt, kids in (live_branch.get(cls, set()) - rows)
        )
        for cls, rows in base_branch.items()
        if live_branch.get(cls, set()) - rows
    }
    gone_branch = {
        cls: sorted(
            f"{menu} / {cnt} / {list(kids)}"
            for menu, cnt, kids in (rows - live_branch.get(cls, set()))
        )
        for cls, rows in base_branch.items()
        if rows - live_branch.get(cls, set())
    }
    return {
        "available": True,
        "baseline": str(CENSUS.relative_to(REPO)),
        "note": (
            "live-vs-committed view: struct sigs AND branching triples are "
            "both SET-R1a-order-canonicalized; committed census rows are "
            "top-40-per-class (most_common(40)), so this view's NEW branchings "
            "are dominated by long-tail rows the census never stored — the "
            "authoritative R1a content delta is r1a_content_delta below"
        ),
        "new_struct_sigs": new_sigs,
        "gone_struct_sigs": gone_sigs,
        "new_branchings": new_branch,
        "gone_branchings": gone_branch,
        "new_struct_sig_count": len(new_sigs),
        "gone_struct_sig_count": len(gone_sigs),
        "new_branching_count": sum(len(v) for v in new_branch.values()),
        "gone_branching_count": sum(len(v) for v in gone_branch.values()),
        "r1a_content_delta": _r1a_map_delta(),
    }


# ---------------------------------------------------------------------------
def _load_whitelist():
    if WHITELIST.exists():
        return json.loads(WHITELIST.read_text())
    return {
        "_comment": "card names ruled acceptable by a dated owner decision",
        "choose_count_eq_len": [],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sets", default=",".join(SETS))
    ap.add_argument(
        "--out", default=None, help="write the machine-readable report here"
    )
    ap.add_argument("--write-v4-baseline", action="store_true")
    ap.add_argument(
        "--strict-warn", action="store_true", help="WARNs also fail the run"
    )
    a = ap.parse_args(argv)
    sets = tuple(s.strip() for s in a.sets.split(",") if s.strip())

    compiled = compile_pools(sets)
    cards = {s: v["cards"] for s, v in compiled.items()}
    print("compiled: " + ", ".join(f"{s}={len(c)}" for s, c in cards.items()))

    v1 = check_v1()
    v2 = check_v2(cards, _load_whitelist())
    v3 = check_v3(cards)
    v4 = check_v4(choose_census(cards), V4_BASELINE, a.write_v4_baseline)
    if a.write_v4_baseline:
        V4_BASELINE.write_text(
            json.dumps(choose_census(cards), indent=2, sort_keys=True)
        )
        print(f"wrote {V4_BASELINE}")
    v5 = check_v5(cards)

    errors = []
    errors += [f"V1′ unclassified {u}" for u in v1["unclassified"]]
    errors += [f"V1′ stale {u}" for u in v1["stale"]]
    errors += [f"V2′ Seq[1] {u}" for u in v2["seq_single_child"]]
    errors += [f"V2′ single-child filter {u}" for u in v2["filter_single_child"]]
    errors += [f"V2′ phantom menu {u}" for u in v2["choose_count_eq_len"]]
    if v4.get("baseline_missing"):
        # FAIL-CLOSED: no baseline artefact -> the freeze check cannot run,
        # and absence of evidence is NOT evidence of conformance.
        errors.append(f"V4 baseline missing — fail-closed: {V4_BASELINE}")
    errors += [f"V4′ new CHOOSE emission {u}" for u in v4["new_emissions"]]
    warns = list(v3["split_seq_designations"])
    if v5.get("available"):
        # Authoritative source when both uncapped censuses exist: the R1a
        # content delta. The live-vs-committed view is kept in the JSON for
        # transparency but floods WARN with committed-census truncation
        # artefacts (long-tail rows never stored in the top-40-per-class
        # baseline), so it only drives WARN when no delta artefacts exist.
        delta = v5.get("r1a_content_delta", {})
        src = delta if delta.get("available") else v5
        warns += [f"V5′ new struct sig {s}" for s in src["new_struct_sigs"]]
        warns += [
            f"V5′ new branching {cls}: {t}"
            for cls, rows in src["new_branchings"].items()
            for t in rows
        ]

    print(
        f"V1′ field-coverage   container_fields={v1['container_fields']} "
        f"classify={v1['classify_tokens']} unclassified={len(v1['unclassified'])} "
        f"stale={len(v1['stale'])}  -> {'ERROR' if v1['unclassified'] or v1['stale'] else 'OK'}"
    )
    print(
        f"V2′ phantom          Seq[1]={len(v2['seq_single_child'])} "
        f"single-child-filter={len(v2['filter_single_child'])} "
        f"choose(count==len)={len(v2['choose_count_eq_len'])} "
        f"whitelisted={len(v2['choose_count_eq_len_whitelisted'])}  -> "
        f"{'ERROR' if (v2['seq_single_child'] or v2['filter_single_child'] or v2['choose_count_eq_len']) else 'OK'}"
    )
    print(f"V3′ split-designation WARN count={len(v3['split_seq_designations'])}")
    if v4.get("baseline_missing"):
        v4_state = f"MISSING at {V4_BASELINE}"
    elif v4["baseline_written"]:
        v4_state = "written this run"
    else:
        v4_state = ("TRACKED " if _git_tracked(V4_BASELINE) else "UNTRACKED ") + str(
            V4_BASELINE.relative_to(REPO)
        )
    print(
        f"V4′ CHOOSE freeze    total={v4['total']} new_emissions={len(v4['new_emissions'])} "
        f"baseline={v4_state}  -> "
        f"{'ERROR' if (v4['new_emissions'] or v4.get('baseline_missing')) else 'OK'}"
    )
    if v5.get("available"):
        delta = v5.get("r1a_content_delta", {})
        if delta.get("available"):
            print(
                f"V5′ map drift        vs committed census: struct_sigs "
                f"new={v5['new_struct_sig_count']} gone={v5['gone_struct_sig_count']} "
                f"branchings new={v5['new_branching_count']} gone={v5['gone_branching_count']} "
                f"(top-40-truncated baseline, see note)"
            )
            print(
                f"                   R1a content delta (uncapped pre/post): struct "
                f"new={delta['new_struct_sig_count']} gone={delta['gone_struct_sig_count']} "
                f"| branchings new={delta['new_branching_count']} "
                f"gone={delta['gone_branching_count']} ({delta['pre']} vs {delta['post']})"
            )
        else:
            print(
                f"V5′ map drift        struct_sigs new={v5['new_struct_sig_count']} "
                f"gone={v5['gone_struct_sig_count']} | branchings new={v5['new_branching_count']} "
                f"gone={v5['gone_branching_count']} (report-only, vs {v5['baseline']})"
            )
    else:
        print("V5′ map drift        no committed census baseline (not evaluated)")
    for e in errors[:20]:
        print("  ERROR:", e)
    for w in warns[:20]:
        print("  WARN:", w)

    if a.out:
        Path(a.out).write_text(
            json.dumps(
                {
                    "sets": {
                        s: {
                            "compiled": len(cards[s]),
                            "shape_gaps": compiled[s]["gaps"],
                        }
                        for s in sets
                    },
                    "V1": v1,
                    "V2": v2,
                    "V3": v3,
                    "V4": v4,
                    "V5": v5,
                    "errors": errors,
                    "warn_count": len(warns),
                },
                indent=2,
            )
        )
        print(f"report {a.out}")
    fail = bool(errors) or (a.strict_warn and bool(warns))
    print(
        "CONFORMANCE",
        "FAIL" if fail else "PASS",
        f"(errors={len(errors)} warns={len(warns)})",
    )
    return 1 if fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
