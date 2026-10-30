#!/usr/bin/env python3
"""R2 EVIDENCE census (READ-ONLY vs repo; writes reports/r2_census.json (repo-relative)).

Part A: every damage-EVENT node (CombatDamageEvent / DamageDealtEvent) in the
compiled IR of M21+ZNR: class, full canonical bytes, struct skeleton, host
ability, printed wording sentence, population per set, samples. Fold test:
CDE(filter F) vs DDE(source F, combat=True) byte sketches + same-wording
buckets with byte variance.

Part B: direction-residual census: StepEvent.controller values; event.actor
encodings (CONTROLLER_IS vs old ControllerRef residue); Zone.controller value
distribution (esp. BATTLEFIELD with YOU/OPPONENT = control/zone overlap
probe); FAtom(CONTROLLER_IS) nodes by host class.field.

Compile pass reuses ontology_shape_census.py precedent (walk() NOT used —
PITFALLS list-skip law). Output: Path(__file__).resolve().parents[2] / "reports" / "r2_census.json"
"""

from __future__ import annotations

from pathlib import Path
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path("/home/sune/Desktop/MTG_AI")
sys.path.insert(0, str(REPO))

from MTG_bot.core.ability_tree import canonical_json, to_dict  # noqa: E402
from MTG_bot.core.compiler.coverage import (  # noqa: E402
    _compile_pool_tolerant,
    build_full_registry,
)
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402

SETS = ("M21", "ZNR")


def cj(v) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


STR_PH, NUM_PH, ENUM_PH = "<S>", "<N>", "~"
CLOSED_STR: set[str] = set()
for _name in (
    "_COLORS",
    "_COLORLESS",
    "_ANY_COLOR",
    "_QPROP_STR_REFERENTS",
    "_MANA_POLICY_SCOPES",
    "_DAMAGE_ASSIGN_SCOPES",
    "_MOVE_JOURNAL_KINDS",
    "_MOVE_POP_ORDERS",
):
    CLOSED_STR.update(
        getattr(__import__("MTG_bot.core.ability_tree", fromlist=["x"]), _name, ())
        or ()
    )


def skel(obj):
    """struct skeleton: strings/numbers elided, class+field skeleton kept."""
    if isinstance(obj, str):
        return obj if obj in CLOSED_STR else STR_PH
    if isinstance(obj, bool) or isinstance(obj, (int, float)):
        return obj  # enum-ish bools (combat) and small counts are semantics
    if isinstance(obj, list):
        return [skel(x) for x in obj]
    if isinstance(obj, dict):
        return {k: skel(v) for k, v in obj.items()}
    return obj


def walk_nodes(node, path, host, out):
    """Yield (tag, node, host_chain) for every dict-tagged node."""
    if isinstance(node, list):
        for i, x in enumerate(node):
            walk_nodes(x, f"{path}[{i}]", host, out)
        return
    if not isinstance(node, dict):
        return
    tag = node.get("tag")
    h2 = host + ((tag,) if tag else ())
    if tag:
        out.append((tag, node, h2, path))
    for k, v in node.items():
        if k == "tag":
            continue
        walk_nodes(v, f"{path}.{k}", h2, out)


DAMAGE_EVENT_TAGS = {"CombatDamageEvent", "DamageDealtEvent"}
ACTOR_EVENTS = {
    "CastSpellEvent",
    "TurnPhaseEvent",
    "CardDrawnEvent",
    "LifeGainedEvent",
    "SacrificeEvent",
    "AbilityActivatedEvent",  # R5-7: replaced LoyaltyActivatedEvent
}


def enumname(v):
    """to_dict serializes enums as {'name': X, 'tag': EnumClass}."""
    if isinstance(v, dict) and "name" in v and "tag" in v:
        return v["name"]
    return v if isinstance(v, str) else cj(v) if v is not None else "null"


def fatom_pred(node):
    return enumname(node.get("pred"))


def sentences_with(word, text):
    return [
        s.strip() for s in re.split(r"(?<=[.;])\s+", text or "") if word in s.lower()
    ]


def main():
    registry = build_full_registry()
    per_set = {}
    for sn in SETS:
        pool = ingest_pool(REPO / "MTG_bot" / "data" / f"{sn}.json")
        results, gaps = _compile_pool_tolerant(pool, registry)
        per_set[sn] = {"results": results, "gaps": len(gaps), "pool": pool}
        print(f"{sn}: compiled {len(results)} gaps {len(gaps)}", file=sys.stderr)

    # ---------------- Part A ----------------
    dmg_nodes = []  # flat records
    for sn in SETS:
        results = per_set[sn]["results"]
        pool = per_set[sn]["pool"]
        for oid in sorted(results):
            card = results[oid].card
            tree = to_dict(card)
            try:
                oracle = pool[oid].identity.oracle_text
            except Exception:
                oracle = ""
            nodes = []
            walk_nodes(tree, "$", (), nodes)
            for tag, node, host, path in nodes:
                if tag not in DAMAGE_EVENT_TAGS:
                    continue
                rec = {
                    "set": sn,
                    "oid": oid,
                    "name": card.name,
                    "class": tag,
                    "path": path,
                    "host_chain": "|".join(host),
                    "bytes": cj(node),
                    "skel": cj(skel(node)),
                    "amount": cj(node.get("amount"))
                    if tag == "DamageDealtEvent"
                    else None,
                    "combat": node.get("combat")
                    if tag == "DamageDealtEvent"
                    else "N/A",
                    "filter": cj(node.get("filter")),
                    "source": cj(node.get("source"))
                    if tag == "DamageDealtEvent"
                    else None,
                    "cde_filter": cj(node.get("filter"))
                    if tag == "CombatDamageEvent"
                    else None,
                    "wording": sentences_with("damage", oracle),
                }
                dmg_nodes.append(rec)

    clusters = defaultdict(lambda: {"n": 0, "M21": 0, "ZNR": 0, "samples": []})
    for r in dmg_nodes:
        key = (r["class"], r["skel"])
        c = clusters[key]
        c["n"] += 1
        c[r["set"]] += 1
        if len(c["samples"]) < 6:
            c["samples"].append(
                {
                    "name": r["name"],
                    "set": r["set"],
                    "wording": r["wording"],
                    "bytes": r["bytes"],
                }
            )

    # fold probe: CDE(F) vs DDE(source=F, combat in (True,None)) same filter bytes
    dde_by_source = defaultdict(list)
    for r in dmg_nodes:
        if r["class"] == "DamageDealtEvent" and r["source"] and r["source"] != "null":
            dde_by_source[r["source"]].append(r)
    fold_pairs = []
    for r in [x for x in dmg_nodes if x["class"] == "CombatDamageEvent"]:
        for m in dde_by_source.get(r["cde_filter"], []):
            fold_pairs.append(
                {
                    "cde": {
                        "name": r["name"],
                        "set": r["set"],
                        "bytes": r["bytes"],
                        "wording": r["wording"],
                    },
                    "dde": {
                        "name": m["name"],
                        "set": m["set"],
                        "bytes": m["bytes"],
                        "wording": m["wording"],
                    },
                    "shared_source_filter": r["cde_filter"],
                }
            )

    # wording-bucket byte variance: same printed pattern, different bytes
    def wording_key(wlist):
        joined = " ".join(wlist).lower()
        pat = []
        if "combat damage" in joined:
            pat.append("combat")
        else:
            pat.append("noncombat-or-any")
        if re.search(r"is dealt damage|dealt damage to", joined):
            pat.append("passive-receive")
        elif re.search(r"deals? that much damage|deals? damage", joined):
            pat.append("active-deal")
        else:
            pat.append("other")
        return "|".join(pat)

    wbuckets = defaultdict(list)
    for r in dmg_nodes:
        wbuckets[wording_key(r["wording"])].append(r)
    wording_variants = {
        k: {
            "n": len(v),
            "distinct_bytes": len({x["bytes"] for x in v}),
            "classes": sorted({x["class"] for x in v}),
            "cards": sorted({(x["set"], x["name"]) for x in v}),
        }
        for k, v in sorted(wbuckets.items())
    }

    # ---------------- Part B ----------------
    dir_census = {
        sn: {
            "StepEvent_controller": Counter(),
            "actor_field": Counter(),  # Event.actor -> encoding shape
            "CONTROLLER_IS_by_host": Counter(),
            "Zone_controller_by_kind": Counter(),
            "battlefield_dir_selectors": [],
        }
        for sn in SETS
    }

    for sn in SETS:
        results = per_set[sn]["results"]
        pool = per_set[sn]["pool"]
        dc = dir_census[sn]
        for oid in sorted(results):
            card = results[oid].card
            tree = to_dict(card)
            nodes = []
            walk_nodes(tree, "$", (), nodes)
            for tag, node, host, path in nodes:
                if tag == "StepEvent":
                    dc["StepEvent_controller"][enumname(node.get("controller"))] += 1
                if tag in ACTOR_EVENTS:
                    a = node.get("actor")
                    if a is None:
                        dc["actor_field"][f"{tag}:null"] += 1
                    elif isinstance(a, dict) and fatom_pred(a) == "CONTROLLER_IS":
                        dc["actor_field"][
                            f"{tag}:CONTROLLER_IS:{enumname(a.get('who'))}"
                        ] += 1
                    else:
                        dc["actor_field"][f"{tag}:OTHER:{cj(a)[:60]}"] += 1
                if tag == "FAtom" and fatom_pred(node) == "CONTROLLER_IS":
                    holder = host[-2] if len(host) >= 2 else "?"
                    field = path.rsplit(".", 1)[-1].split("[")[0]
                    dc["CONTROLLER_IS_by_host"][f"{holder}.{field}"] += 1
                if tag == "Zone":
                    _kind = enumname(node.get("kind"))
                    _ctrl = enumname(node.get("controller"))
                    dc["Zone_controller_by_kind"][f"{_kind}/{_ctrl}"] += 1
                    if _kind == "BATTLEFIELD" and _ctrl in ("YOU", "OPPONENT"):
                        dc["battlefield_dir_selectors"].append(
                            {
                                "name": card.name,
                                "path": path,
                                "host": "|".join(host),
                                "zone": cj(node),
                            }
                        )

    out = {
        "partA": {
            "total_damage_event_nodes": len(dmg_nodes),
            "by_class_set": {
                f"{k[0]}/{k[1]}": v
                for k, v in Counter((r["class"], r["set"]) for r in dmg_nodes).items()
            },
            "clusters": [
                {"class": k[0], "skel": k[1], **v}
                for k, v in sorted(
                    clusters.items(), key=lambda kv: (-kv[1]["n"], kv[0])
                )
            ],
            "fold_pairs_shared_source_filter": fold_pairs,
            "wording_buckets": wording_variants,
            "nodes": dmg_nodes,
        },
        "partB": {
            sn: {k: (dict(v) if isinstance(v, Counter) else v) for k, v in dc.items()}
            for sn, dc in dir_census.items()
        },
    }
    _dest = Path(__file__).resolve().parents[2] / "reports" / "r2_census.json"
    _dest.write_text(json.dumps(out, indent=1))
    print(f"wrote {_dest} nodes={len(dmg_nodes)}", file=sys.stderr)
    # compact stdout digest
    print("A: damage nodes", out["partA"]["by_class_set"])
    print("A: clusters", len(out["partA"]["clusters"]), "fold_pairs", len(fold_pairs))
    for k, v in wording_variants.items():
        print(
            f"A wording[{k}] n={v['n']} bytes={v['distinct_bytes']} cls={v['classes']}"
        )
    for sn in SETS:
        b = out["partB"][sn]
        print(
            f"B {sn}: StepEvent.ctrl={b['StepEvent_controller']} "
            f"bf-dir={len(b['battlefield_dir_selectors'])}"
        )
        print(f"B {sn}: actor={b['actor_field']}")
        print(f"B {sn}: CONTROLLER_IS hosts={b['CONTROLLER_IS_by_host']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
