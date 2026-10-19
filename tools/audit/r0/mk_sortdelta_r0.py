#!/usr/bin/env python3
"""R0 zone-fold byte-delta MEASUREMENT (pre-registration, R1a precedent).

N-R0 (measurement-only simulation; NO repo edit): for every Selector node in
the serialized tree, zone_set = dedup({zone} U {zones}) keyed by
canonical_json of the Zone dict, sorted by that canonical_json string; the
folded record serializes Selector with zones = sorted tuple and NO zone
field — same class/tag shape (task phrased it "__class"; the real schema tag
is the class name, so {"tag":"Selector","zones":[...], count/mode/filter/
referent unchanged}). Neutral class C2 (zone=Zone(ANY,ANY), zones=()) folds
to zones=[Zone(ANY,ANY)] single element.

Baseline = canonical_json(card) of the live compile (== committed golden body
when goldens are fresh; freshness is checked for M21).

Checks:
  (1) changed-cards exact name-sets (M21 vs predicted 219, ZNR; deviation IS
      the finding), per-card cause rules fired;
  (3) content preservation: per Selector, multiset-after == set(multiset-
      before) with multiplicity 1 (dedup of a LITERAL duplicate zone inside
      `zones` is the spec-legal twin-collapse, counted separately as
      dedup_collapse; any zone LOST that is not a literal duplicate = hidden
      zones-drop bug like compiler.py:1050 -> LOUD content failure);
  (4) idempotence: fold(fold(tree)) == fold(tree), zero second-pass firings;
  (5) twin -> KEYED-lane cross-map + executor-observed falsifier battery;
  (6) Waker of Waves (L6 CostDiscard target zone=HAND singleton) membership.

Writes /tmp/opencode/r0_sortdelta.json. READ-ONLY vs repo.
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

PREDICTED = {"M21": 219}  # inventory corpus census; ZNR expectation: 108
INVENTORY = json.load(open("/tmp/opencode/r0_consumer_inventory.json"))

RULE_KEYS = (
    "zone_key_removed",  # every Selector: "zone" key disappears
    "twin_fold",  # Selector with non-empty zones (zone joins set)
    "neutral_zone_drop",  # C2 neutral Zone(ANY,ANY)+() -> zones=[ANY/ANY]
    "zone_position_change",  # sorted(set) order != [zone]+zones concat order
    "dedup_collapse",  # literal duplicate: zone also present in zones
)

EXCEPTIONS: list[str] = []
CONTENT_FAILURES: list[str] = []
IDEM_FAILURES: list[str] = []


def cj(v) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


def zone_sort_key(zdict) -> str:
    return cj(zdict)


def fold_tree(node, fired: Counter, path: str, second_pass=False):
    """Return (mutated copy, stats). Operates on the to_dict() JSON tree."""
    if isinstance(node, list):
        for i, x in enumerate(node):
            node[i] = fold_tree(x, fired, f"{path}[{i}]", second_pass)
        return node
    if not isinstance(node, dict):
        return node
    for k in list(node):
        node[k] = fold_tree(node[k], fired, f"{path}.{k}", second_pass)
    if node.get("tag") == "Selector":
        zone = node.get("zone")
        zones = list(node.get("zones", []))
        # content check (first pass only)
        if not second_pass:
            before = [zone] + zones if zone is not None else zones
            seen: list = []
            for zd in before:
                if not any(cj(zd) == cj(s) for s in seen):
                    seen.append(zd)
            if len(seen) < len(before):
                fired["dedup_collapse"] += 1  # spec-legal literal duplicate
            after = sorted(seen, key=zone_sort_key)
            # LOUD content invariant: set(after) == set(before), every entry
            # once; nothing added, nothing lost except literal duplicates.
            if {cj(z) for z in after} != {cj(z) for z in before} or len(after) != len(
                {cj(z) for z in before}
            ):
                CONTENT_FAILURES.append(f"{path}: selector zone multiset lost")
            # cause rules
            fired["zone_key_removed"] += 1 if zone is not None else 0
            if zones:
                fired["twin_fold"] += 1
            if (
                zone is not None
                and not zones
                and zone.get("kind", {}).get("name") == "ANY"
                and zone.get("controller", {}).get("name") == "ANY"
                and "position" not in zone
            ):
                fired["neutral_zone_drop"] += 1
            if after != before:
                fired["zone_position_change"] += 1
        # fold: zones = sorted dedup set, drop zone key
        base = zone if zone is not None else None
        pool = ([base] if base is not None else []) + zones
        uniq: list = []
        for zd in pool:
            if not any(cj(zd) == cj(s) for s in uniq):
                uniq.append(zd)
        folded = sorted(uniq, key=zone_sort_key)
        if second_pass and folded != zones:
            fired["second_pass_moved"] += 1
        node.pop("zone", None)
        node["zones"] = folded
    return node


def selector_dicts(tree, path="$"):
    if isinstance(tree, list):
        for i, x in enumerate(tree):
            yield from selector_dicts(x, f"{path}[{i}]")
    elif isinstance(tree, dict):
        if tree.get("tag") == "Selector":
            yield path, tree
        for k, v in tree.items():
            yield from selector_dicts(v, f"{path}.{k}")


def zkind(z):
    return z.get("kind", {}).get("name") if isinstance(z, dict) else None


def zctrl(z):
    return z.get("controller", {}).get("name") if isinstance(z, dict) else None


def zpos(z):
    return z.get("position", {}).get("name") if isinstance(z, dict) else None


def is_universal(f):
    return isinstance(f, dict) and f.get("tag") == "FAnd" and not f.get("children")


def lane_map(card_name, sel, path):
    """KEYED-lane exposure of one twin selector under PRE-fold lane keys and
    under the naive-rewrite risk (what each lane's key becomes if written as
    a naive ∃ instead of the inventory-prescribed matched/singleton form)."""
    lanes = []
    mode = sel.get("mode", {}).get("name")
    zone = sel.get("zone")
    zones = list(sel.get("zones", []))
    allz = ([zone] if zone else []) + zones
    kinds = {zkind(z) for z in allz}
    # L1 strict key: ONE_OF/REST ∧ LIBRARY ∧ TOP
    if mode in ("ONE_OF", "REST") and any(zkind(z) == "LIBRARY" for z in allz):
        if any(zkind(z) == "LIBRARY" and zpos(z) == "TOP" for z in allz):
            lanes.append("L1-strict")
        else:
            lanes.append("L1-naive-exists-exposed")
    # L2 key (pre-fold primary PLAYER) / naive ∃-PLAYER
    if zkind(zone) == "PLAYER":
        lanes.append("L2-primary-PLAYER")
    # L3: naive ∃ rewrite flips behavior iff PLAYER ∃ ∧ not singleton-PLAYER
    if "PLAYER" in kinds and not (
        len({cj(z) for z in allz}) == 1 and zkind(zone) == "PLAYER" and not zones
    ):
        lanes.append("L3-naive-exists-repoint-exposed")
    # L4 zone clause: GRAVEYARD ∧ TARGET_PLAYER present (verb/ALL-mode
    # context checked separately in the report note)
    if any(zkind(z) == "GRAVEYARD" and zctrl(z) == "TARGET_PLAYER" for z in allz):
        lanes.append("L4-graveyard-target-player-clause")
    # L5 draw-guard selector-level keys (dest-HAND is verb context, noted)
    if (
        zkind(zone) == "LIBRARY"
        and sel.get("referent") is None
        and is_universal(sel.get("filter"))
    ):
        lanes.append("L5-draw-guard-shape")
    return lanes


def l6_costdiscard_hits(tree):
    """Dicts CostDiscard whose target selector has a HAND zone (pre-fold:
    target.zone.kind is HAND — legality.py:950 key)."""
    hits = []

    def rec(n, path):
        if isinstance(n, list):
            for i, x in enumerate(n):
                rec(x, f"{path}[{i}]")
        elif isinstance(n, dict):
            if n.get("tag") == "CostDiscard":
                t = n.get("target")
                if isinstance(t, dict):
                    zz = [t.get("zone")] + list(t.get("zones", []))
                    if any(zkind(z) == "HAND" for z in zz if z):
                        hits.append(path)
            for k, v in n.items():
                rec(v, f"{path}.{k}")

    rec(tree, "$")
    return hits


def main() -> int:
    registry = build_full_registry()
    out: dict = {"method": "N-R0 zone-fold simulation on to_dict() tree"}
    twin_index: dict[str, list] = {}  # card -> [(path, sel)] twins
    l6_by_card: dict[str, tuple] = {}  # card -> (set, hits)
    name_by_key: dict[str, str] = {}

    for set_name in ("M21", "ZNR"):
        pool = ingest_pool(REPO / "MTG_bot" / "data" / f"{set_name}.json")
        results, gaps = _compile_pool_tolerant(pool, registry)

        changed: list[str] = []
        causes: dict[str, list[str]] = {k: [] for k in RULE_KEYS}
        idem_fail: list[str] = []
        content_fail: list[str] = []
        census = Counter()
        baseline_stale_goldens: list[str] = []

        for oid in sorted(results):
            card = results[oid].card
            name_by_key[f"{set_name}:{oid}"] = card.name
            try:
                tree = to_dict(card)
                baseline = cj(tree)
                assert baseline == canonical_json(card)
                fired: Counter = Counter()
                _cf_before = len(CONTENT_FAILURES)
                folded = fold_tree(copy.deepcopy(tree), fired, oid)
                content_fail.extend(CONTENT_FAILURES[_cf_before:])
                # idempotence
                fired2: Counter = Counter()
                folded2 = fold_tree(
                    copy.deepcopy(folded), fired2, oid, second_pass=True
                )
                if cj(folded2) != cj(folded) or fired2:
                    idem_fail.append(
                        f"{set_name} {oid} ({card.name!r}): refire={dict(fired2)}"
                    )
                # census
                sels = list(selector_dicts(tree))
                census["selectors_total"] += len(sels)
                for p, s in sels:
                    z, zs = s.get("zone"), list(s.get("zones", []))
                    if zs:
                        census["selectors_twin"] += 1
                        twin_index.setdefault(card.name, []).append((p, s, set_name))
                    if (
                        z is not None
                        and not zs
                        and zkind(z) == "ANY"
                        and zctrl(z) == "ANY"
                        and "position" not in z
                    ):
                        census["neutral_c2"] += 1
                    if z is not None and zkind(z) == "ANY":
                        census["any_kind_with_zones_seen"] += 1 if zs else 0
                hits = l6_costdiscard_hits(tree)
                if hits:
                    l6_by_card[card.name] = (set_name, hits)
                census["cards_with_selectors"] += 1 if sels else 0
                changed_here = cj(folded) != baseline
                if changed_here:
                    changed.append(card.name)
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
                if gp.exists():
                    if gp.read_text().strip() != cj(to_dict(card)):
                        baseline_stale_goldens.append(card.name)

        entry = {
            "changed_count": len(changed),
            "changed_names": sorted(changed),
            "total_compiled": len(results),
            "shape_gaps": len(gaps),
            "census": dict(census),
            "per_cause_card_counts": {k: len(v) for k, v in causes.items()},
            "per_cause_cards": {k: sorted(set(v)) for k, v in causes.items()},
            "idempotence_failures": idem_fail,
            "content_failures_set": content_fail,
        }
        if set_name == "M21":
            gdir = REPO / "MTG_bot" / "core" / "golden" / "M21"
            gfiles = {p.name for p in gdir.glob("*.json")}
            entry["golden_files_total"] = len(gfiles)
            entry["baseline_stale_goldens"] = baseline_stale_goldens
            missing = [
                oid
                for oid in results
                if results[oid].card.name in set(changed)
                and f"{oid}.json" not in gfiles
            ]
            entry["changed_cards_without_golden_file"] = [
                name_by_key[f"M21:{o}"] for o in missing
            ]
        IDEM_FAILURES.extend(idem_fail)
        out["sets"] = out.get("sets", {})
        out["sets"][set_name] = entry
        print(
            f"{set_name}: changed {len(changed)}/{len(results)} census={dict(census)}",
            flush=True,
        )

    # predictions vs measurement
    pred = {
        "M21": PREDICTED["M21"],
        "ZNR": INVENTORY["corpus"]["cards_with_selectors"]["ZNR"],
    }
    out["prediction_check"] = {
        s: {
            "predicted": pred[s],
            "measured": out["sets"][s]["changed_count"],
            "deviation": out["sets"][s]["changed_count"] - pred[s],
        }
        for s in ("M21", "ZNR")
    }

    # twin -> lane cross-map
    twin_lane_map = {}
    for card, entries in twin_index.items():
        lanes, paths, modes = set(), [], set()
        for p, s, sn in entries:
            paths.append(f"{sn}:{p}")
            modes.add(s.get("mode", {}).get("name"))
            for ln in lane_map(card, s, p):
                lanes.add(ln)
        twin_lane_map[card] = {
            "selector_paths": paths,
            "modes": sorted(m for m in modes if m),
            "lanes": sorted(lanes),
            "l6_costdiscard": card in l6_by_card,
        }
    out["twin_lane_map"] = twin_lane_map
    out["twin_card_count"] = len(twin_lane_map)
    out["l6_population"] = {
        c: {"set": sn, "paths": h} for c, (sn, h) in l6_by_card.items()
    }
    waker = "Waker of Waves"
    out["waker_of_waves"] = {
        "in_changed_m21": waker in out["sets"]["M21"]["changed_names"],
        "in_changed_znr": waker in out["sets"]["ZNR"]["changed_names"],
        "l6_costdiscard_hits": l6_by_card.get(waker, (None, []))[1],
        "is_twin": waker in twin_lane_map,
    }

    out["falsifier_battery"] = [
        # one executor-observed falsifier per behavior-risk card (twin under a
        # KEYED lane, or L6 population card); Unsubstantiate is the
        # content-only control (no KEYED lane keys on its STACK∪BATTLEFIELD).
        {
            "card": "Basri's Aegis",
            "lane": "L1",
            "observation": "ONE_OF search of LIBRARY∪GRAVEYARD must NOT enter the r19b look-window lane post-fold: partition_window stays None, the ask enumerates filter-matching cards from BOTH zones (a naive ∃-LIBRARY rewrite would open the window lane)",
        },
        {
            "card": "Chandra's Firemaw",
            "lane": "L1+L5",
            "observation": "firemaw over-draw probe (wave-1b): LIBRARY∪GRAVEYARD ONE_OF put-into-hand resolves via the filter's answer; never the blind top-n DRAW lane (pre-fold guard key sel.zone.kind is LIBRARY is TRUE for this twin; post-fold SINGLETON-LIBRARY must be FALSE)",
        },
        {
            "card": "Garruk's Warsteed",
            "lane": "L1+L5",
            "observation": "LIBRARY∪GRAVEYARD search-into-hand resolves by filter answer, no blind top-draw; folded zones=[GRAVEYARD,LIBRARY] keeps the draw guard closed",
        },
        {
            "card": "Liliana's Scorn",
            "lane": "L1",
            "observation": "ONE_OF LIBRARY∪GRAVEYARD pick does not take the TOP-window partition branch post-fold",
        },
        {
            "card": "Sanctum of All",
            "lane": "L1",
            "observation": "ONE_OF LIBRARY∪GRAVEYARD land search does not take the TOP-window partition branch post-fold",
        },
        {
            "card": "Teferi's Wavecaster",
            "lane": "L1+L5",
            "observation": "LIBRARY∪GRAVEYARD ONE_OF into-hand resolves by filter answer; no blind top-n draw (wave-1b probe, Firemaw sibling)",
        },
        {
            "card": "Chandra's Magmutt",
            "lane": "L2/L3",
            "observation": "Magmutt/Leafkin printed-damage-target pack (r21a): TARGET selector PLAYER∪BATTLEFIELD — a designation the player made (a creature) must STAND; L3 must be SINGLETON len(zones)==1∧PLAYER (folded len 2 -> no re-point); ∃-PLAYER rewrite re-opens the damage-re-point bug",
        },
        {
            "card": "Leafkin Avenger",
            "lane": "L2/L3",
            "observation": "same r21a pack: PLAYER∪BATTLEFIELD walker designation not silently re-pointed to the player through the primary PLAYER zone alone",
        },
        {
            "card": "Necromentia",
            "lane": "L4-clause-shape",
            "observation": "Tormod's Crypt graveyard-sweep pin (r21b): Necromentia's CHOOSE selector carries the GRAVEYARD∧TARGET_PLAYER zone clause — the folded set must NOT route it into the ALL-mode MOVE_ZONE graveyard-sweep lane (mode/verb context still gates; executor must show the replacement-effect population unchanged)",
        },
        {
            "card": "Unsubstantiate",
            "lane": "none (content control)",
            "observation": "no KEYED lane keys on STACK∪BATTLEFIELD: falsifier is the counter-target ask enumerating both STACK and BATTLEFIELD candidates after the fold (bytes change, behavior control)",
        },
        {
            "card": "Waker of Waves",
            "lane": "L6",
            "observation": "activation-from-hand legality: CostDiscard.target folds zone=HAND singleton -> zones=[HAND]; the ∃-HAND gate at legality.py:950 must keep the 'Discard this card:' battlefield window open and the ability LEGAL while the card sits in hand",
        },
    ]

    out["content_failures"] = sorted(set(CONTENT_FAILURES))
    out["idempotence"] = {
        "failures": sorted(set(IDEM_FAILURES)),
        "all_pass": not IDEM_FAILURES,
    }
    out["exceptions"] = EXCEPTIONS

    dest = Path("/tmp/opencode/r0_sortdelta.json")
    dest.write_text(json.dumps(out, indent=2))
    print(
        f"wrote {dest}; exceptions={len(EXCEPTIONS)} content_fail={len(CONTENT_FAILURES)} idem_fail={len(IDEM_FAILURES)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
