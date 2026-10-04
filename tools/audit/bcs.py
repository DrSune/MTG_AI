#!/usr/bin/env python3
"""BUGCATCH B1 — Bug-Primitive Complexity Score (BCS) + branch inventory.

Design: KNOWLEDGE/2026-10-02/12-bugcatch-design.md sections A + B.
Substrate: tools/audit/coverage.json (per-card coverage rows) joined with the
golden IR dumps MTG_bot/core/golden/M21/<oracle_id>.json (tagged node trees).

Pure offline: reads only; emits tools/audit/bcs.json. Zero engine imports so
goldens and engine stay byte-frozen (law: B1 acceptance gate is offline).

Primitive vocabulary was verified 2026-10-04 against the real tag set of the
305 golden IR files + ability_tree.py serialiser table (_TAG_FIELDS); the
design's listed names that differ from real tags are recorded in
meta.node_mappings below.

Run:  python tools/audit/bcs.py
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
from collections import Counter
from datetime import UTC, datetime

ROOT = pathlib.Path(__file__).resolve().parents[2]
GOLDEN_DIR = ROOT / "MTG_bot" / "core" / "golden" / "M21"
COVERAGE_PATH = ROOT / "tools" / "audit" / "coverage.json"
OUT_PATH = ROOT / "tools" / "audit" / "bcs.json"

# ---------------------------------------------------------------------------
# Weights: w_i = number of distinct documented silent-semantic ledger bugs
# whose root cause sits on primitive i (derivation table ships in meta).
# Derivation source: KNOWLEDGE/2026-10-01 fix docs 11/12/13/18/19/23/24/25 +
# 2026-10-02 docs 04-09 + design doc section A's per-primitive bug-family column.
# ---------------------------------------------------------------------------
WEIGHTS = {1: 1, 2: 3, 3: 2, 4: 6, 5: 3, 6: 5, 7: 2, 8: 4, 9: 3}

WEIGHT_DERIVATION = {
    1: {"w": 1, "bugs": ["B-4 sequence-length class", "C2 atom-merge"]},
    2: {
        "w": 3,
        "bugs": [
            "Life Goes On died-branch",
            "Destructive Tampering entanglement",
            "Fabled Passage one_of/rest branch",
        ],
    },
    3: {
        "w": 2,
        "bugs": [
            "Tormod's Crypt TARGET_PLAYER swallowed (24a)",
            "Chandra's Magmutt designation re-point (24a)",
            "(Sanctum of Tranquil Light TARGETS_SOURCE fold 23a counted at p4)",
        ],
    },
    4: {
        "w": 6,
        "bugs": [
            "Sanctum of Calm Waters NAME_EQ census->0",
            "Sanctum of Fruitful Harvest NAME_EQ census->0",
            "Sanctum of Stone Fangs NAME_EQ census->0",
            "Sanctum of Tranquil Light cost-modifier lane-dead (23a)",
            "Ornery Dilophosaur count-vs-print quantifier",
            "Adherent of Hope dropped 'you control' quantifier",
        ],
    },
    5: {
        "w": 3,
        "bugs": [
            "Deathbloom Thallid self-dies spore",
            "Secure the Scene token controller",
            "Treasure {T} gap",
        ],
    },
    6: {
        "w": 5,
        "bugs": [
            "Fiery Emancipation x3",
            "Teferi, Master of Time draw lane (22b)",
            "Containment Priest ETB replacement",
            "Destructive Tampering can't-block (C5)",
            "Ghostly Pilferer pair-veto subject",
        ],
    },
    7: {
        "w": 2,
        "bugs": [
            "Basri's Solidarity counter->PT missing",
            "Trufflesnout counter-blind",
        ],
    },
    8: {
        "w": 4,
        "bugs": [
            "B-9 referent detach",
            "B-16 referent detach",
            "Malefic Scythe self-dies ordering law (22a)",
            "Caged Zombie DIED_THIS_TURN handle misread",
        ],
    },
    9: {
        "w": 3,
        "bugs": [
            "Hobblefiend role bleed",
            "Wildwood Scourge QX-at-ETB anaphor",
            "Basri Ket THAT_MANY_COUNT producer register",
        ],
    },
}

# r20a green-on-silent-bug class (granted keyword/ability with no consumer)
# attributes to p6/p7/p8 per design; their cards are in the calibration set.

# ---------------------------------------------------------------------------
# IR-read vocabulary (verified against golden tag census 2026-10-04).
# ---------------------------------------------------------------------------
ATOMIC_TAGS = {"Atom"}
BRANCH_TAGS = {"Conditional", "Choose", "OptionalEffect", "EachPlayer", "Repeat"}
BRANCH_MODES = {"ONE_OF", "REST"}
BRANCH_BOOLEAN_TAGS = {"FOr", "FNot"}
ROLE_COST_TAGS = {
    "CostTap",
    "CostSacrifice",
    "CostDiscard",
    "CostLife",
    "CostLoyalty",
    "CostPutCounter",
}
QUANT_TAGS = {
    "QX",
    "QBin",
    "QProp",
    "QCount",
    "QAtLeast",
    "QAtMost",
    "QThisTurn",
    "QDistinctColorCount",
}
TOKEN_VERBS = {"CREATE_TOKEN"}
TOKEN_TAGS = {"TokenSpec"}
REPLACE_TAGS = {"ReplacementAbility"}
REPLACE_VERBS = {"PREVENT_EFFECT", "COUNTER_SPELL"}
LAYER_VERBS = {
    "SET_PT",
    "MODIFY_PT",
    "PUT_COUNTER",
    "REMOVE_COUNTER",
    "GRANT_ABILITY",
    "GRANT_TYPE",
}
TRIGGER_TAGS = {"TriggeredAbility", "DelayedTrigger"}
ANAPHORA_PREDS = {
    "IS_SOURCE",
    "IS_ANY_TARGET",
    "TARGETS_SOURCE",
    "IS_ATTACHED_TO_SOURCE",
    "IS_ATTACHED_TO",
    "IS_EXILED_WITH_SOURCE",
    "DIED_THIS_TURN",
    "MOVED_TO_ZONE_THIS_TURN",
}
ANAPHORA_FIELDS = {"THAT_MANY_COUNT", "THIS_WAY_COUNT"}
ANAPHORA_REFERENTS = {"event", "result"}
# r20a dead-keyword class: these keyword notations are ability payloads whose
# CONSUMER lives in engine layers/verbs — the documented silent-bug family
# (LIFELINK/PROWESS/BATTALION granted with no consumer; five packs were green
# on the bug). Notated in the CardRecord top-level `keywords` list, NOT in
# abilities[]. Counted under p7 (static grants).
KEYWORD_CONSUMER_BUGS = {"LIFELINK", "PROWESS", "BATTALION"}

# Design name -> real IR read, where the design's name is not the real tag.
NODE_MAPPINGS = {
    "Repeat": "real IR class (ability_tree.py:2395, serialiser table:3735) — 0 occurrences "
    "in the 305-card M21 corpus; counted as-is, always 0 here",
    "IS_TARGET (FAtom pred)": "no such pred; real anaphora preds are IS_ANY_TARGET / "
    "TARGETS_SOURCE / IS_SOURCE / IS_ATTACHED_TO* / "
    "IS_EXILED_WITH_SOURCE / DIED_THIS_TURN / "
    "MOVED_TO_ZONE_THIS_TURN (golden census 2026-10-04)",
    "activation_target_slots": "no IR tag; runtime helper (query.py). IR read substituted: "
    "Selector[SelectorMode=TARGET] + non-mana Cost part tags",
    "TARGET_PLAYER": "never appears in the golden IR — runtime-synthesized player slot "
    "(24a); proxied by TARGET selectors in role-slot count",
    "QProp(QPropField)": "QProp node count; the count-vs-power field choice lives in "
    "QPropField.name (AMOUNT/POWER/COUNTER_COUNT/THAT_MANY_COUNT/...)",
    "result/event referents": "node field `referent` in {event, result} on Selector/QProp "
    "nodes (golden census)",
    "THAT_MANY_COUNT": "QPropField enum member on QProp nodes (exists; 3 corpus uses)",
    "static grants (p7)": "GRANT_ABILITY/GRANT_TYPE verbs PLUS KeywordAbility notations "
    "for {LIFELINK, PROWESS, BATTALION} — these live in the CardRecord top-level "
    "keywords[] field, not abilities[] (golden census 2026-10-04); they are the "
    "r20a dead-keyword bug payloads (design section C collision class 4)",
}

VERB_TO_JOURNAL = {
    "DEAL_DAMAGE": "DAMAGE",
    "FIGHT": "DAMAGE",
    "PREVENT_EFFECT": "DAMAGE_PREVENTED",
    "DRAW": "CARD_DRAWN",
    "GAIN_LIFE": "LIFE_GAINED",
    "LOSE_LIFE": "LIFE_GAINED",
    "PUT_COUNTER": "COUNTER_PLACED",
    "REMOVE_COUNTER": "COUNTER_PLACED",
    "TAP": "TAP_STATE",
    "UNTAP": "TAP_STATE",
    "CAST": "CAST",
    "COUNTER_SPELL": "CAST",
    "MANDATE_ATTACK": "DECLARE_ATTACKERS",
    "MANDATE_BLOCK": "DECLARE_BLOCKERS",
    "SACRIFICE": "ZONE_CHANGE",
    "DESTROY": "ZONE_CHANGE",
    "EXILE": "ZONE_CHANGE",
    "MOVE_ZONE": "ZONE_CHANGE",
    "DISCARD": "ZONE_CHANGE",
    "MILL": "ZONE_CHANGE",
    "PHASE_OUT": "ZONE_CHANGE",
    "GAIN_CONTROL": "ZONE_CHANGE",
    "ATTACH": "ZONE_CHANGE",
    "CREATE_TOKEN": "ZONE_CHANGE",
}
DEATHY_VERBS = {"SACRIFICE", "DESTROY"}


def iter_nodes(obj):
    """Yield every dict carrying a 'tag' in a golden IR tree."""
    stack = [obj]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if "tag" in cur:
                yield cur
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)


def first_verb(node):
    for n in iter_nodes(node):
        if n.get("tag") == "Verb":
            return n.get("name")
    return None


def describe_condition(node):
    """Compact textual predicate of a Conditional's condition subtree."""
    parts = []
    for n in iter_nodes(node):
        t = n.get("tag")
        if t == "FAtom" and isinstance(n.get("pred"), dict):
            p = n["pred"].get("name", "?")
            sv = n.get("string_value")
            parts.append(f"{p}({sv})" if sv else p)
    return " & ".join(dict.fromkeys(parts)) or "unconditional"


def primitive_counts(nodes):
    """nodes: list of tagged dicts from one card's golden IR."""
    c = Counter(n.get("tag") for n in nodes)
    verb_names = [n.get("name") for n in nodes if n.get("tag") == "Verb"]
    vc = Counter(verb_names)
    modes = Counter(n.get("name") for n in nodes if n.get("tag") == "SelectorMode")
    preds = Counter(
        n["pred"].get("name")
        for n in nodes
        if n.get("tag") == "FAtom" and isinstance(n.get("pred"), dict)
    )
    fields = Counter(n.get("name") for n in nodes if n.get("tag") == "QPropField")
    kw_bugs = sum(
        1
        for n in nodes
        if n.get("tag") == "KeywordAbility"
        and isinstance(n.get("keyword"), dict)
        and n["keyword"].get("name") in KEYWORD_CONSUMER_BUGS
    )
    referents = sum(
        1
        for n in nodes
        if isinstance(n.get("referent"), str) and n["referent"] in ANAPHORA_REFERENTS
    )
    counts = {
        "p1_atomic_ops": sum(c[t] for t in ATOMIC_TAGS),
        "p2_branch_slots": (
            sum(c[t] for t in BRANCH_TAGS)
            + sum(modes[m] for m in BRANCH_MODES)
            + sum(c[t] for t in BRANCH_BOOLEAN_TAGS)
        ),
        "p3_role_slots": modes["TARGET"] + sum(c[t] for t in ROLE_COST_TAGS),
        "p4_quantifiers": sum(c[t] for t in QUANT_TAGS),
        "p5_token_minting": sum(vc[v] for v in TOKEN_VERBS)
        + sum(c[t] for t in TOKEN_TAGS),
        "p6_replacement": sum(c[t] for t in REPLACE_TAGS)
        + sum(vc[v] for v in REPLACE_VERBS),
        "p7_layers": sum(vc[v] for v in LAYER_VERBS) + kw_bugs,
        "p8_triggers": sum(c[t] for t in TRIGGER_TAGS),
        "p9_anaphora": (
            sum(preds[p] for p in ANAPHORA_PREDS)
            + sum(fields[f] for f in ANAPHORA_FIELDS)
            + referents
        ),
    }
    return counts


def score(counts):
    return sum(
        WEIGHTS[i] * counts[f"p{i}_{k}"]
        for i, k in [
            (1, "atomic_ops"),
            (2, "branch_slots"),
            (3, "role_slots"),
            (4, "quantifiers"),
            (5, "token_minting"),
            (6, "replacement"),
            (7, "layers"),
            (8, "triggers"),
            (9, "anaphora"),
        ]
    )


def branch_inventory(card_handle, abilities):
    """Declared branch slots with discriminating-signature hypotheses (design B)."""
    out = []
    seq = 0
    for node in iter_nodes({"abilities": abilities}):
        t = node.get("tag")
        kind = None
        sig = None
        if t == "Conditional":
            # serialiser fields: pred / then_effect / else_effect
            seq += 1
            kind = "Conditional"
            inner = first_verb(node.get("then_effect"))
            cond = describe_condition(node.get("pred") or {})
            deathy = any(p in cond for p in ("DIED_THIS_TURN",)) or (
                inner in DEATHY_VERBS
            )
            sig = {
                "journal_kind": "CREATURE_DIES"
                if deathy
                else VERB_TO_JOURNAL.get(inner or "", "NONE"),
                "data_predicate": (
                    f"cause==own-handle & {cond}"
                    if deathy
                    else f"row for verb {inner} present iff {cond}"
                ),
                "note": "the row can only appear on the side of the condition that fires",
            }
        elif t == "Choose":
            seq += 1
            kind = "Choose"
            opt_kinds = sorted(
                {
                    VERB_TO_JOURNAL.get(first_verb(opt) or "", "NONE")
                    for opt in node.get("options") or []
                }
            )
            sig = {
                "journal_kind": "|".join(opt_kinds) or "CAST",
                "data_predicate": "data carries chosen mode index (one row per option)",
                "note": "one branch per option; falsifiable per-option lane",
            }
        elif t == "OptionalEffect":
            seq += 1
            kind = "OptionalEffect"
            inner = first_verb(node.get("inner") or node)
            sig = {
                "journal_kind": VERB_TO_JOURNAL.get(inner or "", "NONE"),
                "data_predicate": f"row for verb {inner} present == may-accepted; "
                "absence == declined (needs a positive control lane)",
                "note": "decline side is only lit by a forced-decline probe",
            }
        elif t == "EachPlayer":
            seq += 1
            kind = "EachPlayer"
            inner = first_verb(node.get("effect") or node)
            sig = {
                "journal_kind": VERB_TO_JOURNAL.get(inner or "", "NONE"),
                "data_predicate": f"one row per controller for verb {inner}; "
                "count == seated players",
                "note": "per-player fan-out",
            }
        elif t == "Repeat":
            seq += 1
            kind = "Repeat"
            inner = first_verb(node.get("inner") or node)
            sig = {
                "journal_kind": VERB_TO_JOURNAL.get(inner or "", "NONE"),
                "data_predicate": f"N rows for verb {inner}, N == declared count",
                "note": "repeat-count assertion",
            }
        elif (
            t == "Selector"
            and isinstance(node.get("mode"), dict)
            and node["mode"].get("name") in BRANCH_MODES
        ):
            seq += 1
            kind = f"Selector:{node['mode']['name']}"
            sig = {
                "journal_kind": "TARGETING",
                "data_predicate": "designation row's chosen-set cardinality differs "
                "per branch (ONE_OF=1, REST=rest)",
                "note": "one_of/rest selection branch (tampering class)",
            }
        if kind:
            out.append(
                {
                    "branch_id": f"{card_handle}:{seq:02d}:{kind}",
                    "kind": kind,
                    "signature": sig,
                }
            )
    return out


# ---------------------------------------------------------------------------
# Calibration ledger (assembled 2026-10-04 from the fix docs named in the
# B1 brief; silent-semantic = wrong behaviour the packs/gates missed or
# promoted-to-green; crash-class-only and machinery-only rows do NOT feed the
# >=2-of-p4..9 gate — they are reported in meta with their class.)
# ---------------------------------------------------------------------------
CALIBRATION_SILENT = [
    # life & branch class
    "Life Goes On",
    "Destructive Tampering",
    "Fabled Passage",
    # layers class
    "Basri's Solidarity",
    "Trufflesnout",
    # anaphora / designation class
    "Hobblefiend",
    "Basri Ket",
    # token class
    "Deathbloom Thallid",
    "Secure the Scene",
    # replacement class
    "Fiery Emancipation",
    "Containment Priest",
    "Teferi's Ageless Insight",
    "Ghostly Pilferer",
    # quantifier / census class
    "Sanctum of Calm Waters",
    "Sanctum of Fruitful Harvest",
    "Sanctum of Stone Fangs",
    "Sanctum of Tranquil Light",
    "Ornery Dilophosaur",
    "Adherent of Hope",
    "Wildwood Scourge",
    # trigger-ordering class
    "Malefic Scythe",
    "Caged Zombie",
    # r20a green-on-silent-bug class (granted ability, no consumer)
    "Anointed Chorister",
    "Jeskai Elder",
    "Makeshift Battalion",
    "Infernal Scarring",
    "Mistral Singer",
]
# silent but machine-machinery-rooted (binding/verbs defaults, would fire for ANY
# card with the slot): excluded from the >=2 gate by class, still reported.
# Chandra's Magmutt joined here per doc13 root cause: role_handles' blanket
# PLAYER-zone self-resolve exemption (generic binding.py machinery).
CALIBRATION_MACHINERY = [
    "Tormod's Crypt",
    "Epitaph Golem",
    "Chandra's Magmutt",
]
# crash-class-only (engine raised — never silent): excluded from gate by class.
CALIBRATION_CRASH = [
    "Keral Keep Disciples",
    "Hooded Blightfang",
    "Warden of the Woods",
    "Waker of Waves",
    "Speaker of the Heavens",
    "Conspicuous Snoop",
    "Chandra's Pyreling",
    "Peer into the Abyss",
    "Liliana, Waker of the Dead",
    "Rin and Seri, Inseparable",
]
PRIMITIVES = [
    f"p{i}_{k}"
    for i, k in [
        (1, "atomic_ops"),
        (2, "branch_slots"),
        (3, "role_slots"),
        (4, "quantifiers"),
        (5, "token_minting"),
        (6, "replacement"),
        (7, "layers"),
        (8, "triggers"),
        (9, "anaphora"),
    ]
]
RISK_PRIMITIVES = PRIMITIVES[3:]  # p4..p9


def handle(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def main():
    coverage = json.loads(COVERAGE_PATH.read_text())["cards"]
    cards_out = {}
    for oid, row in sorted(coverage.items(), key=lambda kv: kv[1]["name"]):
        gpath = GOLDEN_DIR / f"{oid}.json"
        golden = json.loads(gpath.read_text()) if gpath.exists() else {"abilities": []}
        abilities = golden.get("abilities", [])
        nodes = list(iter_nodes(golden))
        counts = primitive_counts(nodes)
        s = score(counts)
        name = row["name"]
        hdl = handle(name)
        if name in cards_out:  # duplicate display names in corpus (Cat x2)
            name, hdl = f"{name} (2)", f"{hdl}_2"
        cards_out[name] = {
            "oracle_id": oid,
            "handle": hdl,
            "status": row.get("status"),
            "in_pack": row.get("in_pack"),
            "in_suspect": row.get("in_suspect"),
            "is_token": golden.get("is_token", False),
            "primitives": counts,
            "bcs": s,
            "branches": branch_inventory(hdl, abilities),
        }

    # ----- vanilla-identity residue set: uncovered, only plain keywords/etb ---
    # A creature printed with a consumer-keyword notation (PROWESS etc.) is NOT
    # a vanilla identity — it belongs to the r20a keyword bug class (Goblin
    # Wizard precedent, calibration 2026-10-04).
    vanilla = []
    for name, c in cards_out.items():
        if c["status"] != "uncovered":
            continue
        golden = json.loads((GOLDEN_DIR / f"{c['oracle_id']}.json").read_text())
        ab_tags = {a.get("tag") for a in golden.get("abilities", [])}
        exotic_kw = any(
            k.get("keyword", {}).get("name") in KEYWORD_CONSUMER_BUGS
            for k in golden.get("keywords", [])
        )
        if ab_tags <= {"KeywordAbility", "EtBState"} and not exotic_kw:
            vanilla.append(name)

    # ----- calibration gate -----
    missing = [
        n
        for n in (CALIBRATION_SILENT + CALIBRATION_MACHINERY + CALIBRATION_CRASH)
        if n not in cards_out
    ]
    silent_fail, vanilla_fail = [], []
    for name in CALIBRATION_SILENT:
        c = cards_out[name]
        lit = [p for p in RISK_PRIMITIVES if c["primitives"][p] > 0]
        if len(lit) < 2:
            silent_fail.append(
                {"card": name, "bcs": c["bcs"], "risk_prims_nonzero": len(lit)}
            )
    for name in vanilla:
        c = cards_out[name]
        if c["bcs"] != 0 or any(c["primitives"][p] for p in PRIMITIVES):
            vanilla_fail.append({"card": name, "bcs": c["bcs"]})

    declared = sum(len(c["branches"]) for c in cards_out.values())
    heat = sorted(cards_out.items(), key=lambda kv: -kv[1]["bcs"])

    out = {
        "meta": {
            "built_by": "BUGCATCH batch B1 — tools/audit/bcs.py",
            "date": str(datetime.now(UTC).date()),
            "command": "python tools/audit/bcs.py",
            "design": "KNOWLEDGE/2026-10-02/12-bugcatch-design.md sections A+B",
            "weights": WEIGHTS,
            "weight_derivation": WEIGHT_DERIVATION,
            "weight_law": "w_i = count of distinct documented silent-semantic ledger "
            "bugs whose root cause sits on primitive i (fix docs "
            "2026-10-01:11-13,18-19,23-25 + 2026-10-02:04-09)",
            "node_mappings": NODE_MAPPINGS,
            "calibration": {
                "gate": "every silent-semantic ledger card: >=2 of p4..p9 non-zero; "
                "every vanilla-identity residue card: all nine primitives zero",
                "silent_semantic": CALIBRATION_SILENT,
                "machinery_only_excluded": CALIBRATION_MACHINERY,
                "crash_class_excluded": CALIBRATION_CRASH,
                "vanilla_identity_residue": sorted(vanilla),
                "ledger_names_not_in_corpus": missing,
                "silent_gate_failures": silent_fail,
                "vanilla_gate_failures": vanilla_fail,
                "blind_spot_classes": {
                    "branch_entanglement": "Tampering, Fabled Passage — the bug is in the "
                    "branch machinery (design B) and cross-branch union (§C), invisible to "
                    "per-card primitive counting; p2/p3 carry them (BCS 15/16)",
                    "keyword_x_consumer": "Makeshift Battalion, Mistral Singer — single "
                    "exotic-keyword notation, consumer missing in ENGINE (r20a); IR shows "
                    "one primitive only (§C class 4)",
                    "replacement_x_ordering": "Teferi's Ageless Insight, Caged Zombie — "
                    "one replacement/trigger node whose bug needs a second card or the "
                    "journal-order law to fire (§C classes 2-3)",
                    "single_fold": "Basri's Solidarity, Secure the Scene — the bug is one "
                    "missing fold rule (counter->PT; token controller) on an otherwise "
                    "simple body (engine layers/binder)",
                },
            },
            "branch_totals": {
                "declared": declared,
                "lit_so_far": "deferred — lighting check is batch B3 (pack-journal "
                "signature match over tools/scenarios + 100-seed catalog)",
            },
        },
        "heat": [
            {
                "card": n,
                "bcs": c["bcs"],
                "branches_declared": len(c["branches"]),
                "status": c["status"],
            }
            for n, c in heat
        ],
        "cards": cards_out,
    }
    OUT_PATH.write_text(json.dumps(out, indent=1))

    # ----- printed gates -----
    n = len(cards_out)
    passed = len(CALIBRATION_SILENT) - len(silent_fail) - len(missing)
    print(
        f"bcs.json: {n} cards, {declared} declared branches, "
        f"{vanilla and len(vanilla)} vanilla-identity residue"
    )
    print(
        f"CALIB-GATE silent-semantic >=2 of p4..p9: {passed}/{len(CALIBRATION_SILENT)} pass"
    )
    if silent_fail:
        print(
            "EXCEPTION TABLE (silent bug card looks complexity-free — score incomplete?)"
        )
        for r in silent_fail:
            print(
                f"  {r['card']:35} BCS={r['bcs']:3}  risk-prims={r['risk_prims_nonzero']}"
            )
    print(
        f"CALIB-GATE vanilla-identity all-zero: "
        f"{len(vanilla) - len(vanilla_fail)}/{len(vanilla)} pass"
    )
    for r in vanilla_fail:
        print(f"  ZERO-FAIL {r['card']:30} BCS={r['bcs']}")
    if missing:
        print(f"LEDGER names not found in corpus: {missing}")
    top = [f"{nm}({c['bcs']})" for nm, c in heat[:10]]
    print("TOP-10 BCS:", " ".join(top))
    print(
        "GATE:",
        "PASS" if not silent_fail and not vanilla_fail and not missing else "FINDINGS",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
