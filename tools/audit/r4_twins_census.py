#!/usr/bin/env python3
"""R4 TWINS census (ontology §4 F-row F3; gated on the §9 similar-effects test).

READ-ONLY vs repo; writes ONLY reports/r4_twins_census.json.

Hypothesis: cost<->effect pairs ('discard a card', 'tap a creature',
'sacrifice a creature' as COST vs as EFFECT) SHOULD share the menu/count axes.
Post-R3 (/144) the cost side asks through tap:/discard:/sacrifice: payment
lanes and the effect side through choose: (ask_choose lifts). Question the
census answers:
  (1) population: cost-node counts by class; effect-node counts by the SAME
      menu axes (count, zones, filter) of the paired verb;
  (2) cards using BOTH shapes with IDENTICAL menu axes (the similar-effects
      evidence);
  (3) ask-surface byte comparison for 3 sampled pairs: Selector canonical
      bytes, site tag, vocabulary construction (from the landed code paths).
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path("/home/sune/Desktop/MTG_AI")
OUT = (Path(__file__).resolve().parents[2] / "reports" / "r4_twins_census.json")
sys.path.insert(0, str(REPO))

from MTG_bot.core.ability_tree import canonical_json, to_dict  # noqa: E402
from MTG_bot.core.compiler.coverage import (  # noqa: E402
    _compile_pool_tolerant,
    build_full_registry,
)
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402


def _enum(v):
    return v.get("name") if isinstance(v, dict) else v


def menu_axes(sel: dict) -> str:
    """The comparable menu/count axes of a Selector: count + zones + filter
    (mode excluded: cost/effect lanes may spell it differently)."""
    return json.dumps(
        {
            "count": sel.get("count"),
            "zones": sel.get("zones"),
            "filter": sel.get("filter"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def zone_kinds(sel) -> tuple:
    return tuple(
        (_enum(z.get("kind")), _enum(z.get("controller"))) for z in sel.get("zones", [])
    )


def classify_effect(verb, args_pairs, sel) -> str | None:
    """Effect-side twin family of a verb-atom Selector."""
    if verb == "TAP":
        return "tap"
    if verb == "UNTAP":
        return None  # no CostUntap — not a twin family
    if verb == "SACRIFICE":
        return "sacrifice"
    if verb == "PUT_COUNTER":
        return "putcounter"
    if verb == "MOVE_ZONE":
        zk = zone_kinds(sel)
        dest = None
        for k, v in args_pairs:
            if k == "dest" and isinstance(v, dict):
                dest = _enum(v.get("kind")) or str(v.get("kind"))
            if k == "destination" and isinstance(v, dict):
                dest = _enum(v.get("kind")) or str(v.get("kind"))
        kinds = {k for k, _ in zk}
        if "HAND" in kinds and dest == "GRAVEYARD":
            return "discard"
        if "BATTLEFIELD" in kinds and dest == "GRAVEYARD":
            return "sacrifice"
    return None


def walk(node, parent_cost_ctx, out_cost, out_eff):
    """out_cost: (cost_class, selector-dict); out_eff: (family, selector-dict)."""
    if isinstance(node, list):
        for x in node:
            walk(x, False, out_cost, out_eff)
        return
    if not isinstance(node, dict):
        return
    tag = node.get("tag")
    if tag in ("CostTap", "CostSacrifice", "CostDiscard", "CostPutCounter"):
        t = node.get("target")
        if isinstance(t, dict) and t.get("tag") == "Selector":
            fam = tag[4:].lower()  # Tap->tap etc.
            out_cost.append((tag, fam, t))
        return
    if tag == "Atom":
        verb = _enum(node.get("verb"))
        pairs = []
        for p in (node.get("args") or {}).get("pairs", []):
            if isinstance(p, list) and len(p) == 2:
                pairs.append((p[0], p[1]))
        for _role, v in pairs:
            for sel in sels_in(v):
                fam = classify_effect(verb, pairs, sel)
                if fam:
                    out_eff.append((fam, verb, sel))
        return
    for v in node.values():
        walk(v, False, out_cost, out_eff)


def sels_in(v):
    """Selector(s) directly carried by an arg value (Selector or magnitude-
    wrapper dicts carrying .selector)."""
    res = []
    if isinstance(v, dict):
        if v.get("tag") == "Selector":
            res.append(v)
        else:
            inner = v.get("selector")
            if isinstance(inner, dict) and inner.get("tag") == "Selector":
                res.append(inner)
    return res


def main() -> int:
    registry = build_full_registry()
    out = {"method": "R4 F3 twins census on to_dict() of live compile"}
    cost_mode: Counter = Counter()
    cost_sel_shape: dict[str, Counter] = defaultdict(Counter)
    eff_sel_shape: dict[str, Counter] = defaultdict(Counter)
    per_card_cost: dict[tuple, list] = defaultdict(list)
    per_card_eff: dict[tuple, list] = defaultdict(list)
    samples = []

    for set_name in ("M21", "ZNR"):
        pool = ingest_pool(REPO / "MTG_bot" / "data" / f"{set_name}.json")
        results, _ = _compile_pool_tolerant(pool, registry)
        for oid in sorted(results):
            card = results[oid].card
            tree = to_dict(card)
            oc, oe = [], []
            walk(tree, False, oc, oe)
            for tag, fam, sel in oc:
                cost_mode[(fam, _enum(sel.get("mode")))] += 1
                shape = menu_axes(sel)
                cost_sel_shape[fam][shape] += 1
                per_card_cost[(set_name, card.name)].append((fam, shape, sel))
            for fam, verb, sel in oe:
                shape = menu_axes(sel)
                eff_sel_shape[fam][shape] += 1
                per_card_eff[(set_name, card.name)].append((fam, shape, verb))

    # exact menu-axis twins ON THE SAME CARD
    same_card_twins = []
    for key, costs in per_card_cost.items():
        effs = per_card_eff.get(key, [])
        for fam, shape, sel in costs:
            for efam, eshape, everb in effs:
                if fam == efam and shape == eshape:
                    same_card_twins.append(
                        {"set": key[0], "card": key[1], "family": fam, "verb": everb}
                    )
    # loose: family twins on same card (menu may differ, e.g. count)
    same_card_family = []
    for key, costs in per_card_cost.items():
        effs = per_card_eff.get(key, [])
        cfams = {f for f, _, _ in costs}
        efams = {f for f, _, _ in effs}
        for f in sorted(cfams & efams):
            same_card_family.append({"set": key[0], "card": key[1], "family": f})

    # cross-pool shape intersection (does ANY cost shape == ANY effect shape?)
    shared = {}
    for fam in set(cost_sel_shape) | set(eff_sel_shape):
        cs = set(cost_sel_shape.get(fam, {}))
        es = set(eff_sel_shape.get(fam, {}))
        shared[fam] = {
            "cost_shapes": len(cs),
            "effect_shapes": len(es),
            "identical_menu_shape_pairs": len(cs & es),
            "example_shared": [s[:200] for s in sorted(cs & es)[:3]],
        }

    # 3 byte-level pair samples: prefer same-card twins, else per-family
    picked = []
    seen_fams = set()
    for t in same_card_twins:
        if t["family"] in seen_fams:
            continue
        seen_fams.add(t["family"])
        picked.append(t)
    for fam in ("discard", "tap", "sacrifice"):
        if fam in seen_fams or fam not in shared:
            continue
        cs = cost_sel_shape.get(fam, Counter())
        es = eff_sel_shape.get(fam, Counter())
        inter = set(cs) & set(es)
        src = inter or (set(cs) | set(es))
        if not src:
            continue
        s = sorted(src)[0]
        # find one cost card + one effect card carrying shape s (or nearest)
        cex = next(
            (
                k
                for k, v in per_card_cost.items()
                if any(x[0] == fam and x[1] == s for x in v)
            ),
            None,
        )
        eex = next(
            (
                k
                for k, v in per_card_eff.items()
                if any(x[0] == fam and x[1] == s for x in v)
            ),
            None,
        )
        if cex and eex:
            picked.append(
                {
                    "set": f"{cex[0]}/{eex[0]}",
                    "card": f"{cex[1]} | {eex[1]}",
                    "family": fam,
                }
            )
    for p in picked[:3]:
        fam = p["family"]
        cs = cost_sel_shape.get(fam, Counter())
        es = eff_sel_shape.get(fam, Counter())
        p["cost_shape_examples"] = [s[:300] for s in list(cs)[:2]]
        p["effect_shape_examples"] = [s[:300] for s in list(es)[:2]]
        p["ask_sites"] = {
            "cost": f"{fam if fam != 'putcounter' else 'putcounter'}:…"
            " -> landed tags: tap:{controller}:{source}:{digest} / "
            "discard:{controller}:{source}:{digest} / "
            "sacrifice:{controller}:{source}:{digest} (legality.py pay_costs)",
            "effect": "choose:{source}[:{i}of{k}]:{digest12} (selectors.resolve_selector ask_choose)",
        }
        samples.append(p)

    out["cost_node_modes"] = {f"{k[0]}/{k[1]}": v for k, v in cost_mode.items()}
    out["family_shape_summary"] = shared
    out["same_card_EXACT_twins"] = same_card_twins
    out["same_card_family_twins"] = same_card_family
    out["cost_nodes_by_family"] = {
        f: sum(c.values()) for f, c in cost_sel_shape.items()
    }
    out["effect_nodes_by_family"] = {
        f: sum(c.values()) for f, c in eff_sel_shape.items()
    }
    out["byte_samples"] = samples
    OUT.write_text(json.dumps(out, indent=2))
    print(
        json.dumps(
            {
                "cost_nodes": out["cost_nodes_by_family"],
                "effect_nodes": out["effect_nodes_by_family"],
                "exact_twins_same_card": len(same_card_twins),
                "family_twins_same_card": len(same_card_family),
                "shared_menu_shapes": {
                    f: v["identical_menu_shape_pairs"] for f, v in shared.items()
                },
                "cost_modes": out["cost_node_modes"],
            },
            indent=1,
        )
    )
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
