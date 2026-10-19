#!/usr/bin/env python3
"""R0 corpus-side blast radius: compile the pools (same pass as
tools/audit/ontology_shape_census.py) and census Selector zone/zones VALUES
(the signature registry cannot see values). Read-only; writes /tmp only."""

from __future__ import annotations

import dataclasses
import json
import sys
from collections import Counter
from enum import Enum
from pathlib import Path

REPO = Path("/home/sune/Desktop/MTG_AI")
sys.path.insert(0, str(REPO))

from MTG_bot.core import ability_tree as at  # noqa: E402
from MTG_bot.core.ability_tree import (  # noqa: E402
    ControllerRef,
    Selector,
    SelectorMode,
    Zone,
    ZoneKind,
    ZonePosition,
)
from MTG_bot.core.compiler.coverage import (  # noqa: E402
    _compile_pool_tolerant,
    build_full_registry,
)
from MTG_bot.core.compiler.ingest import ingest_pool  # noqa: E402
from MTG_bot.core.compiler.compiler import Verb  # noqa: E402


def descend(node):
    """Own recursive walk (PITFALL: at.walk skips list-valued fields)."""
    yield node
    if dataclasses.is_dataclass(node) and not isinstance(node, type):
        for f in dataclasses.fields(node):
            v = getattr(node, f.name)
            for x in descend_value(v):
                yield x
    elif isinstance(node, (list, tuple, set, frozenset)):
        for x in node:
            for y in descend(x):
                yield y


def descend_value(v):
    if isinstance(v, dict):
        for x in v.values():
            yield from descend(x)
    else:
        yield from descend(v)


def card_name(rec):
    ident = getattr(rec, "identity", None)
    return getattr(ident, "name", None) or getattr(rec, "name", "?")


def main():
    registry = build_full_registry()
    out = {"pools": {}, "totals": {}}
    all_twin_cards = []
    lane_hits = {}

    def lane(name, bucket):
        lane_hits.setdefault(name, []).append(bucket)

    for set_name in ("M21", "ZNR"):
        pool = ingest_pool(REPO / "MTG_bot" / "data" / f"{set_name}.json")
        results, gaps = _compile_pool_tolerant(pool, registry)
        p = {
            "cards_compiled": len(results),
            "cards_gapped": len(gaps),
            "selectors_total": 0,
            "selectors_zones_nonempty": 0,
            "selectors_zones_nonempty_cards": set(),
            "selectors_neutral_any_empty": 0,  # zone.kind ANY + zones == ()
            "selectors_any_kind_any_total": 0,  # zone.kind ANY (any zones)
            "selectors_any_kind_with_zones": 0,
            "selectors_single_zone": 0,
            "cards_with_selector": set(),
        }
        for oid, res in results.items():
            rec = res.card
            name = card_name(rec)
            for node in descend(rec):
                if not isinstance(node, Selector):
                    continue
                p["selectors_total"] += 1
                p["cards_with_selector"].add(name)
                zs = tuple(node.zones)
                if zs:
                    p["selectors_zones_nonempty"] += 1
                    p["selectors_zones_nonempty_cards"].add(name)
                    all_twin_cards.append(
                        {
                            "set": set_name,
                            "card": name,
                            "mode": node.mode.name,
                            "primary": f"{node.zone.kind.name}/{node.zone.controller.name}"
                            + (
                                f"/{node.zone.position.name}"
                                if node.zone.position
                                else ""
                            ),
                            "extras": [
                                f"{z.kind.name}/{z.controller.name}"
                                + (f"/{z.position.name}" if z.position else "")
                                for z in zs
                            ],
                            "referent": node.referent,
                        }
                    )
                if node.zone.kind is ZoneKind.ANY:
                    p["selectors_any_kind_any_total"] += 1
                    if not zs:
                        p["selectors_neutral_any_empty"] += 1
                    else:
                        p["selectors_any_kind_with_zones"] += 1
                elif not zs:
                    p["selectors_single_zone"] += 1
                # ---- KEYED-lane population census (per compiled selector)
                b = {"set": set_name, "card": name, "mode": node.mode.name}
                if (
                    node.mode in (SelectorMode.ONE_OF, SelectorMode.REST)
                    and node.zone.kind is ZoneKind.LIBRARY
                    and node.zone.position is ZonePosition.TOP
                ):
                    lane("L1_one_of_rest_library_top", dict(b, zones=len(zs)))
                if node.zone.kind is ZoneKind.PLAYER and not zs:
                    lane("L3_player_side_pure", dict(b))
                if node.zone.kind is ZoneKind.PLAYER and zs:
                    lane(
                        "L2_player_with_extras",
                        dict(b, extras=[z.kind.name for z in zs]),
                    )
        out["pools"][set_name] = {
            k: (sorted(v) if isinstance(v, set) else v) for k, v in p.items()
        }

    out["totals"]["selectors_total"] = sum(
        out["pools"][s]["selectors_total"] for s in out["pools"]
    )
    out["totals"]["selectors_zones_nonempty"] = sum(
        out["pools"][s]["selectors_zones_nonempty"] for s in out["pools"]
    )
    out["totals"]["neutral_c2_class"] = sum(
        out["pools"][s]["selectors_neutral_any_empty"] for s in out["pools"]
    )
    twin = sorted({(t["set"], t["card"]) for t in all_twin_cards})
    out["totals"]["twin_cards"] = [f"{c} [{s}]" for s, c in twin]
    out["twin_selectors"] = all_twin_cards
    out["keyed_lane_populations"] = {k: v for k, v in sorted(lane_hits.items())}

    # ---- lane 4/5/6 need atom context: walk Atoms with their Selectors.
    for set_name in ("M21", "ZNR"):
        pool = ingest_pool(REPO / "MTG_bot" / "data" / f"{set_name}.json")
        results, _gaps = _compile_pool_tolerant(pool, registry)
        for oid, res in results.items():
            rec = res.card
            name = card_name(rec)
            for node in descend(rec):
                if not isinstance(node, at.Atom):
                    continue
                dest = node.args.get("destination") if node.args else None
                for _role, value in node.args.pairs if node.args else ():
                    if not isinstance(value, Selector):
                        continue
                    zs = tuple(value.zones)
                    uni = (
                        isinstance(value.filter, at.FAnd) and not value.filter.children
                    )
                    b = {
                        "set": set_name,
                        "card": name,
                        "verb": node.verb.name,
                        "mode": value.mode.name,
                    }
                    if (
                        node.verb is Verb.MOVE_ZONE
                        and isinstance(dest, Zone)
                        and dest.kind is ZoneKind.EXILE
                        and value.mode is SelectorMode.ALL
                        and uni
                        and value.zone.kind is ZoneKind.GRAVEYARD
                        and value.zone.controller is ControllerRef.TARGET_PLAYER
                    ):
                        lane("L4_graveyard_sweep", dict(b, zones=len(zs)))
                    if (
                        node.verb is Verb.MOVE_ZONE
                        and isinstance(dest, Zone)
                        and dest.kind is ZoneKind.HAND
                        and value.mode not in (SelectorMode.ONE_OF, SelectorMode.REST)
                        and value.zone.kind is ZoneKind.LIBRARY
                        and value.referent is None
                        and uni
                    ):
                        lane("L5_firemaw_topdraw", dict(b, zones=len(zs)))
                    if value.mode is SelectorMode.ALL and zs:
                        lane("L7_all_mode_multizone_ORDER", dict(b, zones=len(zs)))
            for cost in getattr(rec, "costs", ()) or ():
                pass
        # cost-side Selector.zone consumers (legality.py:950 CostDiscard HAND)
        for oid, res in results.items():
            rec = res.card
            name = card_name(rec)
            for node in descend(rec):
                if isinstance(node, at.CostDiscard) and node.target is not None:
                    t = node.target
                    uni_src = any(
                        c.pred is at.FAtomPred.IS_SOURCE
                        for c in descend(t.filter)
                        if isinstance(c, at.FAtom)
                    )
                    if t.zone.kind is ZoneKind.HAND and uni_src:
                        lane(
                            "L6_costdiscard_self_hand",
                            {"set": set_name, "card": name, "zones": len(t.zones)},
                        )

    out["keyed_lane_populations"] = {k: v for k, v in sorted(lane_hits.items())}
    json.dump(out, sys.stdout, indent=1)


main()
