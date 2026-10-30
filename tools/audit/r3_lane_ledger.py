#!/usr/bin/env python3
"""R3 silent-CHOOSE blindness ledger — COMMITTED lane-split generator (/141 §6).

Regenerates ``reports/r3_blindness.json`` (default out, ``--out`` overrides)
byte-for-byte from the compiled pools: the rerun must leave the committed
ledger unmodified (``git diff`` empty). The traversal, classification rules
and field shapes are the ORIGINAL audit law (the /tmp/opencode/r3_src_saved/
final.py pass), ported into the repo because a NUMBERS-law evidence row was
previously produced by an uncommitted scratch script (gate finding, /141 §6:
"lane-split generator COMMITTED").

On top of the committed fields this generator derives the LIFT-NOW set from
the three gate rules (/141 §6 amendment):
  (i)   count kind is QConst            (QUnbounded DEFERRED: the ONE_OF ask
        lane hard-raises NotImplementedError on it, selectors.py:681-685 —
        Chandra x5 nodes, Necromentia, Siege Striker);
  (ii)  menu zone public or controller-owned (no hidden-zone enumeration to
        a non-owner; NO merged multi-seat zones — HAND:ANY is the Bad Deal /
        Waker +1 merged-hand ZND-7(a) bug lane);
  (iii) chooser == card controller (TARGET_PLAYER zones / EachPlayer paths /
        the ledger's own "NOT the source controller" label are opponent
        choosers → ZND-9 seat-in-tag lane; see GROUND_TRUTH below).

The lift table is PRINTED every run (never silent, like the whitelist law);
``--lift-out PATH`` additionally writes it as JSON. Nothing in this tool
mutates the IR: compiled bytes are untouched by design (IR Δ0 law).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO))

from MTG_bot.core import ability_tree as at  # noqa: E402
import tools.audit.ontology_conformance as oc  # noqa: E402


def texts(s):
    d = json.loads((REPO / "MTG_bot" / "data" / f"{s}.json").read_text())["data"][
        "cards"
    ]
    return {c["name"]: (c.get("text") or "") for c in d}


TX = {**texts("M21"), **texts("ZNR")}


def fpreds(f):
    out = []

    def rec(x):
        if x is None:
            return
        if isinstance(x, (at.FAnd, at.FOr)):
            for c in x.children:
                rec(c)
        elif isinstance(x, at.FNot):
            rec(x.inner)
        elif isinstance(x, at.FAtom):
            v = (
                x.string_value
                or (x.who.name if getattr(x, "who", None) else None)
                or x.count
            )
            out.append(f"{x.pred.name}" + (f"({v})" if v not in (None, "", 0) else ""))

    rec(f)
    return out


def walk(obj, stack, role):
    cls = type(obj).__name__
    if isinstance(obj, (tuple, list, frozenset, set)):
        for i, x in enumerate(obj):
            nr = (
                str(x[0])
                if (
                    stack
                    and stack[-1][0] == "AtomArgs"
                    and isinstance(x, tuple)
                    and len(x) == 2
                )
                else role
            )
            yield from walk(x, stack + [(cls, f"[{i}]")], nr)
        return
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        if isinstance(obj, at.Selector) and obj.mode is at.SelectorMode.CHOOSE:
            yield stack, role, obj
        vn = getattr(obj, "verb", None)
        vname = vn.name if hasattr(vn, "name") else None
        for f in dataclasses.fields(obj):
            yield from walk(
                getattr(obj, f.name),
                stack
                + [(cls + (f"({vname})" if cls == "Atom" and vname else ""), f.name)],
                role,
            )


RULES = {
    "referent": "selectors.resolve_selector referent lane (selectors.py:419-452): candidates = the bound source/controller/register object — zero selection by construction",
    "self": "r20c self-designation (selectors.py:896-910; CostDiscard carve-back legality.py:814-824): IS_SOURCE filter denotes the effect's OWN source (CR 602.2c) — single-candidate population",
    "seat": "enumerate_zone(PLAYER, controller-ref) yields exactly the denoted seat(s); EachPlayer 14f rotation (__init__.py:966-995) re-points YOU-relative specs per iteration — single-candidate per resolution",
    "top": "Zone(LIBRARY, *, TOP) window = exactly one card (enumerate_zone TOP lane; R0 /129 §2 L1 matched-zone extraction)",
    "scope": "CHOOSE-QUnbounded fold returns sorted(candidates) ENTIRELY (selectors.py:576-577): the node's resolution is rule-forced (scope = whole population). For play-permission scopes the real choice is the SEPARATE cast op with its own offer/legality lanes (B1/B2 CAST clamp, query.py)",
    "sacask": "r22a sacrifice-cost vocabulary law (legality.py:1407-1440): pay_costs re-opens the choice through the 14b channel (ask key sacrifice:<seat>:<source>:<digest>, vocabulary = Handle strings) when len(pool) > need; forced segments auto-fill (§1.4, never asked)",
    "saptap": "CostTap planner witness cands[:need] (legality.py:756-770): Handle-sorted first-need; NO tap_options lane exists (contrast sacrifice_options, legality.py:288) — silent first-n",
    "disco": "CostDiscard plan-time fold discard.extend(cands[:need]) (legality.py:801-830; only correction is r19b CR 601.2h self-exclusion); pay_costs binds the PRE-CHOSEN handles into the journalled MOVE_ZONE (legality.py:1449-1464) — silent first-n",
    "topn": "r18a/B-13 top-n idiom (verbs.py:233-245 + singleton-library guard /129 L5 verbs.py:247-249): unfiltered referent-less CHOOSE over LIBRARY resolves the library's own top order, not a player choice",
    "firstn": "finite CHOOSE = deterministic 12a stand-in ordered[:count] (selectors.py:575-579 'first count of the Handle-sorted candidates'; CAST-lane twin law verbs.py:1421); legality range 0..min(want, n) (query.py:389-397) admits multiple selections — engine silently picks",
}


def classify(n, text):
    tl = text.lower()
    path = n["node_path"]
    if n["referent"] is not None:
        return "L-A", "referent", None
    if "IS_SOURCE" in n["filter"]:
        return "L-A", "self", None
    if any(z.endswith(":TOP") for z in n["zones"]):
        return "L-A", "top", None
    if len(n["zones"]) == 1 and n["zones"][0].startswith("PLAYER:YOU"):
        return "L-A", "seat", None
    if n["count"] == "QUnbounded":
        if n["verb"] == "CAST":
            return "L-A", "scope", None
        if "any number" in tl:
            return "L-B", "firstn", "quantity selection (any-number)"
        return "L-A", "scope", None
    if "CostSacrifice" in path:
        return "L-C", "sacask", None
    if "CostTap" in path:
        return "L-B", "saptap", "ability controller (payer)"
    if "CostDiscard" in path:
        return "L-B", "disco", "ability controller (payer)"
    if n["universal_filter"] and any(z.startswith("LIBRARY") for z in n["zones"]):
        return "L-A", "topn", None
    chooser = None
    zones = " ".join(n["zones"])
    # V21 (2026-10-29): "target opponent" zones carry TARGET_OPPONENT.
    if "TARGET_PLAYER" in zones or "TARGET_OPPONENT" in zones or "EachPlayer" in path:
        chooser = "affected/controlled player, NOT the source controller"
    return "L-B", "firstn", chooser


# --------------------------------------------------------------------------
# LIFT-NOW derivation (the three gate rules, /141 §6 — the amendments that
# OVERRIDE §3's 24-card ask battery).
# --------------------------------------------------------------------------

#: Executor ground truth vs the committed ledger's permissive legal_chooser
#: label. The ledger classifies chooser from the Selector's STRUCTURE (zones/
#: path); a SpellAbility whose English direction is "TARGET OPPONENT sacrifices
#: a creature OF THEIR CHOICE" makes the opponent the CR chooser even though
#: the compiled selector sits in a public zone with no EachPlayer/TARGET_PLAYER
#: trace (the direction is simply NOT encoded — ZND-7 recipient-fidelity defer,
#: and /141 §2's opponent-chooser subset names Run Afoul explicitly). Lifting
#: it through the controller seat would ask the CASTER to choose the victim —
#: a rules change, and unroutable to the true seat (no seat param in the
#: provider lane until ZND-9). Deferred, not lifted.
GROUND_TRUTH_CHOOSER = {
    ("M21", "Run Afoul"): (
        "defer ZND-9/ZND-7: text 'Target opponent sacrifices a creature of "
        "their choice with flying' — opponent is the CR chooser; direction "
        "unencoded in the selector (ledger label says controller: FINDING)"
    )
}

#: Hidden kinds: enumerating these to (or through) a non-owner is a
#: hidden-info leak; a hidden zone owned by the chooser (:YOU / payer) is fine.
HIDDEN_KINDS = ("HAND", "LIBRARY")


def lift_verdict(n):
    """Return (lifted, reason). Rules are the /141 §6 amendment, in order."""
    if n["lane"] != "L-B":
        return False, "not-L-B"
    gt = GROUND_TRUTH_CHOOSER.get((n["set"], n["card"]))
    if gt and n["rule_key"] == "firstn":
        return False, gt
    # rule (i): the ONE_OF ask channel takes QConst/QAtMost only; every
    # QUnbounded node here would CRASH it (selectors.py:681-685).
    if "QUnbounded" in n["count"]:
        return False, "defer: QUnbounded (ONE_OF lane raises on it, /141 §6)"
    if "QConst" not in n["count"]:
        return False, "defer: count kind is not QConst"
    # rule (iii): chooser must be the card controller.
    if "NOT the source controller" in n["legal_chooser"]:
        return False, "defer ZND-9: opponent chooser (seat-in-tag lane)"
    # rule (ii): public or controller-owned menu; merged multi-seat zones and
    # hidden zones denied to a non-owner are out.
    for z in n["zones"]:
        kind, _, rest = z.partition(":")
        owner = rest.split(":")[0]
        if kind in HIDDEN_KINDS and owner != "YOU":
            return False, (
                f"defer: hidden zone {z} not controller-owned "
                "(merged multi-seat / non-owner enumeration, ZND-7(a) lane)"
            )
    owners = {z.partition(":")[2].split(":")[0] for z in n["zones"]}
    if "ANY" in owners and len(n["zones"]) > 1:
        return False, "defer: merged multi-seat zone set"
    return True, "lift"


def build_nodes():
    compiled = oc.compile_pools()
    nodes = []
    for s, v in compiled.items():
        for oid, card in v["cards"].items():
            for st, role, sel in walk(card, [("Root", "")], None):
                stl = list(st)
                ai, abcls, holder = None, None, "card"
                for j, (c, f) in enumerate(stl):
                    if f == "abilities":
                        holder = (
                            "emblem"
                            if any(ff == "emblem" for _, ff in stl[:j])
                            else "card"
                        )
                        if j + 1 < len(stl):
                            try:
                                ai = int(stl[j + 1][1].strip("[]"))
                            except ValueError:
                                ai = None
                        if j + 2 < len(stl):
                            abcls = stl[j + 2][0]
                        break
                stackstr = " > ".join(f"{c}.{f}" for c, f in st)
                ms = list(re.finditer(r"Atom\((\w+)\)", stackstr))
                verb = ms[-1].group(1) if ms else None
                zn = [
                    f"{z.kind.name}:{getattr(z.controller, 'name', z.controller)}"
                    + (
                        f":{getattr(z.position, 'name', None)}"
                        if getattr(z.position, "name", None) not in (None, "NONE")
                        else ""
                    )
                    for z in sel.zones
                ]
                rec = {
                    "set": s,
                    "card": card.name,
                    "oracle_id": oid,
                    "holder": holder,
                    "ability_idx": ai,
                    "ability_class": abcls,
                    "node_path": stackstr,
                    "verb": verb,
                    "role": role,
                    "count": at.canonical_json(sel.count),
                    "zones": zn,
                    "filter": fpreds(sel.filter),
                    "universal_filter": isinstance(sel.filter, at.FAnd)
                    and not sel.filter.children,
                    "referent": sel.referent,
                }
                lane, rulekey, chooser = classify(rec, TX.get(card.name, ""))
                rec["lane"] = lane
                rec["rule_key"] = rulekey
                rec["engine_resolver"] = RULES[rulekey]
                rec["legal_chooser"] = chooser or (
                    "effect controller / payer"
                    if rulekey == "firstn"
                    else "none (engine-forced)"
                )
                rec["text_excerpt"] = TX.get(card.name, "").replace("\n", " ⏎ ")[:220]
                nodes.append(rec)
    return nodes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(REPO / "reports" / "r3_blindness.json"))
    ap.add_argument("--lift-out", default=None)
    args = ap.parse_args()

    nodes = build_nodes()

    per_card: dict = {}
    for n in nodes:
        per_card.setdefault(n["set"], {})[n["card"]] = (
            per_card.setdefault(n["set"], {}).get(n["card"], 0) + 1
        )
    base = json.loads((HERE / "ontology_conformance_v4_baseline.json").read_text())

    def _bcnt(s: str, name: str) -> int:
        # R3 V4′ upgrade: baseline entries became {"count", "shapes"} per
        # card (shape-hash census). Count extraction is format-agnostic so
        # this ledger reproduces byte-identically across the baseline v2
        # migration.
        e = base.get(s, {}).get(name, 0)
        return e["count"] if isinstance(e, dict) else e

    diffs = []
    for s, per in per_card.items():
        for name, cnt in per.items():
            if cnt != _bcnt(s, name):
                diffs.append(f"{s}:{name} {_bcnt(s, name)}->{cnt}")
    for s, bper in base.items():
        for name, entry in bper.items():
            b = _bcnt(s, name)
            if per_card.get(s, {}).get(name, 0) < b:
                d = f"{s}:{name} baseline {b} -> live {per_card.get(s, {}).get(name, 0)} (DECREASE)"
                if d not in diffs:
                    diffs.append(d)

    out = {
        "audit": "R3 silent SelectorMode.CHOOSE blindness audit (docs/DESIGN_ATOM_ONTOLOGY.md §8 R3; V4′ freeze gate)",
        "date": "2026-10-20",
        "method_census": "oc.compile_pools() (ingest_pool(M21,ZNR) + build_full_registry + _compile_pool_tolerant) + card-root dataclass walk incl. emblem/TokenSpec — identical traversal law to V4′ choose_census (never walk()).",
        "population": {
            "nodes": len(nodes),
            "cards": len({(n["set"], n["card"]) for n in nodes}),
            "per_set_nodes": {
                s: sum(1 for n in nodes if n["set"] == s) for s in ("M21", "ZNR")
            },
            "per_set_cards": {
                s: len({n["card"] for n in nodes if n["set"] == s})
                for s in ("M21", "ZNR")
            },
            "doc_174_explained": "174 = CHOOSE count inside the CAPPED top-40 branching rows of the committed reports/ontology_census_2026-10-19.json §C (census default cap=40; most_common(40) truncation). Full-cap artifacts (…_r1a_pre/post_full, …_r0_post_full) count CHOOSE 192; live card-root walk = 193 (+1 = emblem-attached node class the capped row-merge folds). §8-F2/§8-R3 '174 cards' is a nodes-count AND a truncation artifact; the V4′ freeze baseline itself holds 193 nodes / 146 cards.",
            "vs_v4_baseline_diffs": diffs,
        },
        "lane_counts": dict(Counter(n["lane"] for n in nodes)),
        "rule_counts": {
            f"{k[0]}/{k[1]}": c
            for k, c in Counter((n["lane"], n["rule_key"]) for n in nodes).items()
        },
        "nodes": nodes,
    }
    dest = Path(args.out)
    dest.write_text(json.dumps(out, indent=1))
    print("nodes:", len(nodes), "cards:", out["population"]["cards"])
    print("lanes:", out["lane_counts"])
    print("baseline diffs:", diffs or "NONE (reproduces the V4′ freeze census exactly)")

    lift = [n for n in nodes if lift_verdict(n)[0]]
    print(
        f"\nLIFT-NOW: {len({(n['set'], n['card']) for n in lift})} cards / {len(lift)} nodes"
    )
    for n in lift:
        print(
            f"  LIFT  {n['set']:4} {n['card']:32} {n['rule_key']:7} {n['zones']} {n['count']}"
        )
    print("DEFERRED / EXCLUDED (L-B only):")
    for n in nodes:
        if n["lane"] == "L-B":
            lifted, reason = lift_verdict(n)
            if not lifted:
                print(
                    f"  HOLD  {n['set']:4} {n['card']:32} {n['rule_key']:7} — {reason}"
                )
    if args.lift_out:
        rows = [
            {
                "set": n["set"],
                "card": n["card"],
                "oracle_id": n["oracle_id"],
                "rule_key": n["rule_key"],
                "verb": n["verb"],
                "zones": n["zones"],
                "count": n["count"],
                "node_path": n["node_path"],
            }
            for n in lift
        ]
        held = [
            {
                "set": n["set"],
                "card": n["card"],
                "rule_key": n["rule_key"],
                "node_path": n["node_path"],
                "reason": lift_verdict(n)[1],
            }
            for n in nodes
            if n["lane"] == "L-B" and not lift_verdict(n)[0]
        ]
        Path(args.lift_out).write_text(
            json.dumps({"lift_now": rows, "held": held}, indent=1)
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
