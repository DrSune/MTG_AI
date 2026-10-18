"""Un-askable eval-item audit (R3 generalization program, /85 memo).

Concept (KNOWLEDGE/2026-10-07/24+/25): an eval item's tested mechanic is
UN-ASKABLE if it never surfaces through any ask the engine presents for the
card's compiled tree — the ceiling is engine decision observability, not data
volume. /24 froze 9 such survivors; this tool re-measures CURRENTLY.

Method (two lanes, dynamic preferred, static backstop — NO engine edits):
  1. DYNAMIC: re-run each eval item's scenario pack through
     tools.audit.puzzle_cert.extract_items (its recorder patches ExecCtx
     in-process; nothing on disk changes) and check the item's ask still
     SURFACES: matched by (step, ask_kind, occurrence-in-pack).
  2. STATIC: compile-tree ask-kind reachability from the cards' golden trees
     (MTG_bot/core/golden/M21/<oracle_id>.json), UNIONED over every card the
     item's pack contains (corpus item attribution is the pack's first card,
     but the ask may belong to a co-card): OptionalEffect->may,
     Selector TARGET->target, CHOOSE mode/Verb CHOOSE->choose,
     ONE_OF->one_of, Verb SCRY->scry, CHOOSE_NAME->name, ADD_MANA->mana,
     CostSacrifice/Verb SACRIFICE->sacrifice. ALL/RANDOM/REST selectors and
     triggers without an OptionalEffect resolve silently (no ask kind).
     attack/block are COMBAT-offer lanes (offer_or_autopick in
     executor/__init__.py) — not tree-derivable; static evidence is n-a.

Verdicts per eval item: askable | unaskable(reason) | n-a.
Additionally reports the corpus-wide un-askable backlog (fail_registered
items, any split side) and /24-era named-backlog follow-up.

Usage:
  systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 \
    bash -c '.venv/bin/python tools/eval/unaskable_audit.py \
      --out tools/eval/unaskable_audit.json > /tmp/opencode/unaskable.log 2>&1'
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

GOLDEN = REPO / "MTG_bot" / "core" / "golden" / "M21"
CORPUS = REPO / "tools" / "audit" / "puzzle_corpus.json"
SPLIT = REPO / "tools" / "audit" / "eval_split.json"
BCS = REPO / "tools" / "audit" / "bcs.json"
SCENARIOS = REPO / "tools" / "scenarios"

#: /24 fail-core survivor names (checked by name, whatever side they sit on)
BACKLOG_24 = ("Meteorite", "Read the Tides", "Waker of Waves", "Havoc Jester")

#: combat-offer ask kinds: presented by executor combat code per turn, never
#: encoded as a tree node — static lane cannot see them (dynamic lane can).
COMBAT_KINDS = {"attack", "block"}


# ------------------------------------------------------------------ statics
def _walk(o: Any):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def tree_ask_kinds(tree: dict) -> Counter:
    """Ask-kind reachability features of one compiled golden tree."""
    hits: Counter = Counter()
    for node in _walk(tree):
        tag = node.get("tag")
        if tag == "OptionalEffect":
            hits["may"] += 1
        elif tag == "SelectorMode":
            name = node.get("name")
            if name == "TARGET":
                hits["target"] += 1
            elif name == "CHOOSE":
                hits["choose"] += 1
            elif name == "ONE_OF":
                hits["one_of"] += 1
        elif tag == "Verb":
            name = node.get("name")
            if name == "SCRY":
                hits["scry"] += 1
            elif name == "CHOOSE_NAME":
                hits["name"] += 1
            elif name in ("CHOOSE",):  # modal CHOOSE combinator
                hits["choose"] += 1
            elif name == "ADD_MANA":
                hits["mana"] += 1
            elif name == "SACRIFICE":
                hits["sacrifice"] += 1
        elif tag in ("CostSacrifice", "Choose"):
            hits["sacrifice" if tag == "CostSacrifice" else "choose"] += 1
    return hits


def load_golden_index() -> dict[str, dict]:
    """card name -> compiled golden tree (name via bcs oracle_id, fallback
    to each golden's own ``name`` field)."""
    idx: dict[str, dict] = {}
    bcs_names: dict[str, str] = {}
    if BCS.exists():
        cards = json.loads(BCS.read_text())["cards"]
        bcs_names = {n: m["oracle_id"] for n, m in cards.items() if m.get("oracle_id")}
    for n, oid in bcs_names.items():
        f = GOLDEN / f"{oid}.json"
        if f.exists():
            idx[n] = json.loads(f.read_text())
    for f in GOLDEN.glob("*.json"):  # fill names the bcs map missed
        try:
            t = json.loads(f.read_text())
        except Exception as e:  # noqa: BLE001 - corrupt golden: item goes n-a
            print(f"golden {f.name}: unreadable ({e})", file=sys.stderr)
            continue
        nm = t.get("name")
        if nm and nm not in idx:
            idx[nm] = t
    return idx


# ------------------------------------------------------------------ dynamic
def dynamic_asks_for_packs(
    pack_names: set[str],
) -> tuple[dict[str, list[dict]], set[str]]:
    """Freshly extract the item specs each pack SURFACES under current code.
    Returns ({pack_file: [spec,...]}, set of pack files that failed to run).
    Degrades to empty maps (caller falls back to static) if the harness
    cannot be imported or a pack raises."""
    out: dict[str, list[dict]] = {}
    failed: set[str] = set()
    try:
        from MTG_bot.core.executor.games import get_supply
        from tools.audit.puzzle_cert import extract_items  # installs recorder
    except Exception as e:  # noqa: BLE001
        print(f"dynamic lane unavailable ({e}); static-only", file=sys.stderr)
        return out, set(pack_names)
    supply = get_supply("all")
    for name in sorted(pack_names):
        path = SCENARIOS / name
        try:
            pack = json.loads(path.read_text())
            out[name] = extract_items(pack, supply)
        except Exception as e:  # noqa: BLE001
            failed.add(name)
            print(f"pack {name}: replay failed ({e})", file=sys.stderr)
    return out, failed


def _occurrence_key(spec: dict) -> tuple[int, str]:
    return (spec["step"], spec["ask_kind"])


def match_surface(stored: dict, fresh_specs: list[dict]) -> tuple[bool, dict | None]:
    """Does the stored item's ask still surface? Match by (step, ask_kind,
    occurrence-order-within-that-pair). Returns (surfaced, matching_spec)."""
    key = _occurrence_key(stored)
    same = [s for s in fresh_specs if _occurrence_key(s) == key]
    # stored ordinal is pack-global; count earlier same-key specs on both sides
    stored_rank = stored.get("_rank", 0)
    if stored_rank < len(same):
        return True, same[stored_rank]
    return False, None


# -------------------------------------------------------------------- audit
def audit(dynamic: bool = True) -> dict:
    corpus = json.loads(CORPUS.read_text())
    items = corpus["items"]
    eval_families = set(json.loads(SPLIT.read_text())["eval_families"])
    golden = load_golden_index()

    eval_items = [i for i in items if i["card"] in eval_families]
    for i in eval_items:
        i["_key"] = (i["card"], i["pack"], i["step"], i["ask_kind"])

    # rank each stored item within its (pack, step, ask_kind) group
    ranks: dict[tuple, int] = {}
    for i in eval_items:
        k = (i["pack"], _occurrence_key(i))
        i["_rank"] = ranks.get(k, 0)
        ranks[k] = i["_rank"] + 1

    fresh: dict[str, list[dict]] = {}
    failed_packs: set[str] = set()
    if dynamic:
        fresh, failed_packs = dynamic_asks_for_packs({i["pack"] for i in eval_items})

    # Static lane is PACK-level: corpus items attribute to the pack's first
    # real card, but the ask may belong to a co-card (Opt's scry in
    # jeskai_elder.json, Hobblefiend's sacrifice cost in
    # ladder_jester_double_sac.json). Reachable kinds = union over every
    # golden tree the pack's cards contribute.
    pack_kinds: dict[str, Counter] = {}
    pack_nogolden: dict[str, set[str]] = {}
    for pack_name in {i["pack"] for i in eval_items}:
        acc: Counter = Counter()
        nogolden: set[str] = set()
        try:
            p = json.loads((SCENARIOS / pack_name).read_text())
            names = {c.get("real") or c.get("name") for c in p.get("cards", [])}
        except Exception as e:  # noqa: BLE001
            print(f"pack {pack_name}: unreadable ({e})", file=sys.stderr)
            names = set()
        for nm in sorted(n for n in names if n):
            if nm in golden:
                acc += tree_ask_kinds(golden[nm])
            else:
                nogolden.add(nm)
        pack_kinds[pack_name] = acc
        pack_nogolden[pack_name] = nogolden

    results: list[dict] = []
    for it in eval_items:
        kind, pack = it["ask_kind"], it["pack"]
        kinds = pack_kinds.get(pack, Counter())
        nogolden = pack_nogolden.get(pack, set())
        rec: dict[str, Any] = {
            "id": f"{it['card']}|{pack}|step{it['step']}|{kind}#{it['_rank']}",
            "card": it["card"],
            "pack": pack,
            "ask_kind": kind,
            "candidates_n": it["candidates_n"],
            "gold": it["gold"],
            "eval_side": True,
        }
        # declared un-askable (author triage baked into the pack)
        if it["fail_registered"]:
            rec["verdict"] = "unaskable"
            rec["reason"] = f"declared:{it['fail_verdict']}: {it['reclass_reason']}"
            rec["basis"] = "corpus-triage"
            results.append(rec)
            continue
        # dynamic ground truth
        if pack in fresh:
            surfaced, spec = match_surface(it, fresh[pack])
            if surfaced:
                rec["verdict"] = "askable"
                rec["reason"] = ""
                rec["basis"] = "dynamic"
                rec["gold_still_matches"] = spec["gold"] == it["gold"]
                results.append(rec)
                continue
            # ask vanished under current code
            rec["verdict"] = "unaskable"
            if kinds.get(kind, 0) == 0:
                rec["reason"] = (
                    f"ask not presented; no tree of the pack's cards carries a "
                    f"{kind}-shaped decision node"
                    + (f" (no golden for {sorted(nogolden)})" if nogolden else "")
                )
            else:
                rec["reason"] = (
                    f"ask vanished though tree carries {kinds[kind]} "
                    f"{kind}-shaped node(s) (engine auto-resolves the site)"
                )
            rec["basis"] = "dynamic"
            results.append(rec)
            continue
        # dynamic inconclusive (pack failed / skipped) -> static backstop
        if kind in COMBAT_KINDS:
            rec["verdict"] = "n-a"
            rec["reason"] = (
                "combat-offer lane: not static-decidable; dynamic inconclusive"
            )
            rec["basis"] = "static"
        elif kinds.get(kind, 0) > 0:
            rec["verdict"] = "askable"
            rec["reason"] = ""
            rec["basis"] = "static-tree"
        elif nogolden:
            rec["verdict"] = "n-a"
            rec["reason"] = (
                f"kind absent from available trees, but pack cards lack "
                f"goldens: {sorted(nogolden)}"
            )
            rec["basis"] = "static"
        else:
            rec["verdict"] = "unaskable"
            rec["reason"] = (
                f"no tree of the pack's cards carries a {kind}-shaped decision node"
            )
            rec["basis"] = "static-tree"
        results.append(rec)

    # ---- corpus-wide un-askable backlog (any side, currently registered)
    backlog = [
        {
            "card": i["card"],
            "pack": i["pack"],
            "ask_kind": i["ask_kind"],
            "verdict": i["fail_verdict"],
            "reason": i["reclass_reason"],
            "eval_side": i["card"] in eval_families,
        }
        for i in items
        if i["fail_registered"]
    ]

    # ---- /24-era named survivors follow-up (current verdicts if eval-side)
    follow24: dict[str, Any] = {}
    for name in BACKLOG_24:
        its = [r for r in results if r["card"] == name]
        follow24[name] = (
            {"eval_side": True, "items": [r["verdict"] for r in its]}
            if its
            else {
                "eval_side": name in eval_families,
                "corpus_items": sum(1 for i in items if i["card"] == name),
                "fail_registered": sum(
                    1 for i in items if i["card"] == name and i["fail_registered"]
                ),
            }
        )

    # ---- designation-lane packs (scripted words consumed at CAST time, no
    # menu ask ever presented) touching eval families
    lanes = corpus.get("summary", {}).get("designation_lane_packs", [])
    lane_eval = []
    for pname in lanes:
        try:
            p = json.loads((SCENARIOS / pname).read_text())
        except Exception as e:  # noqa: BLE001
            print(f"lane pack {pname}: unreadable ({e})", file=sys.stderr)
            continue
        cards = {c.get("real") or c.get("name") for c in p.get("cards", [])}
        hit = sorted(c for c in cards if c in eval_families)
        if hit:
            lane_eval.append({"pack": pname, "eval_cards": hit})

    summary: dict[str, dict[str, int]] = defaultdict(
        lambda: dict.fromkeys(("askable", "unaskable", "n_a"), 0)
    )
    for r in results:
        summary[r["ask_kind"]]["n_a" if r["verdict"] == "n-a" else r["verdict"]] += 1
    verdicts = Counter(r["verdict"] for r in results)
    basis = Counter(r["basis"] for r in results)

    return {
        "tool": "tools/eval/unaskable_audit.py",
        "corpus_items": len(items),
        "eval_families": len(eval_families),
        "eval_items": len(eval_items),
        "dynamic_lane_ran": bool(fresh),
        "packs_replayed": len(fresh),
        "packs_replay_failed": sorted(failed_packs),
        "verdicts": dict(verdicts),
        "basis": dict(basis),
        "by_ask_kind": {k: dict(v) for k, v in sorted(summary.items())},
        "items": results,
        "unaskable_backlog_registered": backlog,
        "followup_24_named": follow24,
        "designation_lane_eval_cards": lane_eval,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, required=True, help="json report path")
    ap.add_argument(
        "--static-only",
        action="store_true",
        help="skip per-item pack replays (static tree lane only)",
    )
    args = ap.parse_args(argv)
    report = audit(dynamic=not args.static_only)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1) + "\n")
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "eval_items",
                    "dynamic_lane_ran",
                    "packs_replayed",
                    "packs_replay_failed",
                    "verdicts",
                    "basis",
                    "by_ask_kind",
                )
            },
            indent=1,
        )
    )
    print(
        f"unaskable_backlog_registered: {len(report['unaskable_backlog_registered'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
