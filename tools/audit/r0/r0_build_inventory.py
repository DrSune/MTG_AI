"""Assemble /tmp/opencode/r0_consumer_inventory.json from the AST scans +
manual lane classification table."""

import json
import subprocess
from collections import Counter, defaultdict

SCAN = json.load(open("/tmp/opencode/r0_scan_typed.json"))
TESTS = json.load(open("/tmp/opencode/r0_test_sites_typed.json"))
CORP = json.load(open("/tmp/opencode/r0_corpus.json"))

sites = []


def add(file, line, kind, behavior, note, extra=None):
    s = {
        "file": file,
        "line": line,
        "kind": kind,
        "behavior_class": behavior,
        "note": note,
    }
    if extra:
        s["extra"] = extra
    sites.append(s)


# ---------- manual lane / special-site table (prod) ----------
LANES = {
    ("MTG_bot/core/executor/selectors.py", 451): (
        "READ-PRIMARY",
        "KEYED",
        "L1 r19b ONE_OF/REST window gate: `sel.zone.kind is LIBRARY and sel.zone.position is TOP`. "
        "Rewrite: `top_library = [z for z in sel.zones if z.kind is LIBRARY and z.position is TOP]` "
        "and gate on that list being non-empty.",
    ),
    ("MTG_bot/core/executor/selectors.py", 456): (
        "READ-PRIMARY",
        "KEYED",
        "L1 gate clause 1 (zone.kind LIBRARY) — same ∃-predicate as :451.",
    ),
    ("MTG_bot/core/executor/selectors.py", 457): (
        "READ-PRIMARY",
        "KEYED",
        "L1 gate clause 2 (zone.position TOP) — must be the SAME matched zone "
        "as the kind test (∃ over one zone object, not two independent ∃s).",
    ),
    ("MTG_bot/core/executor/selectors.py", 473): (
        "READ-PRIMARY",
        "KEYED-BODY-EXTRACTION",
        "L1 BODY: `players_for_ref(sel.zone.controller, ctx)` — must extract the controller of the "
        "MATCHED LIBRARY+TOP zone (zones[i] that satisfied the gate), NOT the first/primary slot. "
        "An ∃-test that passes on a zone the body then ignores = silent rules change (gate A1).",
    ),
    ("MTG_bot/core/executor/selectors.py", 452): (
        "READ-ZONES",
        "PASS-THROUGH",
        "union population `for extra in sel.zones: extend(...)` — set-iterate.",
    ),
    ("MTG_bot/core/executor/selectors.py", 614): (
        "READ-PRIMARY",
        "KEYED",
        "L2 (16a) PLAYER re-point: `sel.zone.kind is PLAYER` -> bind cards to their controller. "
        "Rewrite ∃ over sel.zones ONLY IF the gate means 'denotes players'; today the corpus selector "
        "is single-zone, so `zones == (PLAYER,)` is the faithful reading (see L3 pairing).",
    ),
    ("MTG_bot/core/executor/selectors.py", 286): (
        "READ-BOTH",
        "PASS-THROUGH",
        "_is_any_universal already unions: `zones = (sel.zone, *sel.zones)` + any(ANY)/all(BATTLEFIELD). "
        "Fold: `zones = sel.zones` — semantics identical.",
    ),
    ("MTG_bot/core/executor/selectors.py", 835): (
        "READ-PRIMARY",
        "KEYED",
        "L3 role_handles player_side: `value.zone.kind is PLAYER and not value.zones`. Post-fold the "
        "faithful rewrite is SINGLETON-AND-KIND (`len(zones)==1 and zones[0].kind is PLAYER`), NOT "
        "∃-PLAYER: a naive ∃ resurrects the r21a Magmutt/Leafkin re-point bug (printed damage aimed "
        "at the player instead of the walker).",
    ),
    ("MTG_bot/core/executor/selectors.py", 836): (
        "READ-ZONES",
        "KEYED",
        "L3 `and not value.zones` = 'primary only' test — becomes the cardinality "
        "test of the singleton rewrite above.",
    ),
    ("MTG_bot/core/executor/selectors.py", 884): (
        "READ-PRIMARY",
        "KEYED",
        "L4 role_handles graveyard_sweep: `value.zone.kind is GRAVEYARD` (Tormod's Crypt pin). "
        "Rewrite: ∃ z in value.zones with kind GRAVEYARD; keep the 5-pin AND-structure.",
    ),
    ("MTG_bot/core/executor/selectors.py", 885): (
        "READ-PRIMARY",
        "KEYED",
        "L4 second clause: `value.zone.controller is TARGET_PLAYER` — must ride on the SAME matched "
        "zone as :884 (one zone satisfying both), not an independent ∃.",
    ),
    ("MTG_bot/core/executor/verbs.py", 248): (
        "READ-PRIMARY",
        "KEYED",
        "L5 firemaw top-draw guard: `sel.zone.kind is LIBRARY` (with dest==HAND, non-partition, "
        "referent None, universal filter). Rewrite as SINGLETON-AND-KIND or all-zones-LIBRARY; a naive "
        "∃-LIBRARY would let a HAND∪LIBRARY selector take the blind top-n DRAW lane.",
    ),
    ("MTG_bot/core/executor/legality.py", 950): (
        "READ-PRIMARY",
        "KEYED",
        "*** NEW LANE (not in the known four) *** _ability_discards_its_source: "
        "`part.target.zone.kind is HAND` over CostDiscard.target (a Selector) + IS_SOURCE filter — the "
        "'Discard this card:' activation-legality window gate. Rewrite: any(z.kind is HAND for z in "
        "part.target.zones).",
    ),
    ("MTG_bot/core/executor/legality.py", 509): (
        "READ-ZONES",
        "PASS-THROUGH",
        "enumerate_candidates union (`sel.zone` + `sel.zones`) then "
        "`handles = sorted(...)` — order-normalized, fold-safe.",
    ),
    ("MTG_bot/core/executor/legality.py", 510): (
        "READ-ZONES",
        "PASS-THROUGH",
        "extras loop — becomes the whole set.",
    ),
    ("MTG_bot/core/executor/query.py", 1315): (
        "READ-BOTH",
        "PASS-THROUGH",
        "_player_widening_applies unions then any(ANY)/all(BATTLEFIELD); "
        "identical shape to selectors._is_any_universal (the §8.3 query/runtime twin).",
    ),
    ("MTG_bot/core/compiler/compiler.py", 1050): (
        "CONSTRUCT-POSITIONAL+READ-PRIMARY",
        "KEYED-LOSS",
        "_fold_meta_filter rebuilds `Selector(value.count, value.mode, new_filter, value.zone)` — "
        "positional AND it DROPS value.zones (a latent union-loss bug TODAY: a meta-filtered TARGET "
        "selector loses its extra zones; corpus-blind because corpus twin TARGET selectors are not "
        "meta-filtered). Post-fold must be zones=value.zones.",
    ),
    ("MTG_bot/core/ability_tree.py", 0): (
        "SCHEMA",
        "VALIDATE",
        "field declaration: delete `zone: Zone`, make `zones: tuple[Zone, ...]` "
        "required (no default) — every positional site then fails LOUD at construction.",
    ),
}
DECISIONS = {
    ("MTG_bot/core/ability_tree.py", 1227): (
        "VALIDATE",
        "VALIDATION",
        "zone type check (scalar isinstance)",
    ),
    ("MTG_bot/core/ability_tree.py", 1229): (
        "VALIDATE",
        "VALIDATION",
        "zone type check message",
    ),
    ("MTG_bot/core/ability_tree.py", 1231): (
        "VALIDATE",
        "VALIDATION",
        "zones tuple-of-Zone check (keep)",
    ),
    ("MTG_bot/core/ability_tree.py", 1232): (
        "VALIDATE",
        "VALIDATION",
        "zones check message",
    ),
    ("MTG_bot/core/ability_tree.py", 1257): (
        "VALIDATE",
        "VALIDATION",
        "C2 referent: zone.kind is ANY",
    ),
    ("MTG_bot/core/ability_tree.py", 1258): (
        "VALIDATE",
        "VALIDATION",
        "C2 referent: zone.controller is ANY",
    ),
    ("MTG_bot/core/ability_tree.py", 1259): (
        "VALIDATE",
        "VALIDATION",
        "C2 referent: zone.position is None",
    ),
    ("MTG_bot/core/ability_tree.py", 1262): (
        "VALIDATE",
        "VALIDATION",
        "C2 error message prints self.zone",
    ),
    ("MTG_bot/core/ability_tree.py", 1264): (
        "VALIDATE",
        "VALIDATION",
        "C2 referent: `if self.zones: raise`",
    ),
    ("MTG_bot/core/ability_tree.py", 1266): (
        "VALIDATE",
        "VALIDATION",
        "C2 message prints self.zones",
    ),
}

# ---------- constructions ----------
arg4_map = {(c["file"], c["line"]): c["arg4"] for c in SCAN if c["test"] == "prod"}
for c in SCAN:
    if c["test"] != "prod":
        continue
    key = (c["file"], c["line"])
    if key in LANES:
        continue
    twin = c["has_zones_kw"]
    if c["has_zone_kw"]:
        kind = "CONSTRUCT-KWARG"
    elif c["npos"] >= 4:
        kind = "CONSTRUCT-POSITIONAL"
    else:
        kind = "CONSTRUCT-OTHER"
    note = f"enclosing={c['enclosing']}"
    if twin:
        note += " | TWIN: also passes zones= -> fold must UNION primary+extras"
    add(
        c["file"],
        c["line"],
        kind,
        "PASS-THROUGH-TWIN-EDIT" if twin else "PASS-THROUGH-MUST-EDIT",
        note,
        {"arg4": arg4_map.get(key), "keywords": c["keywords"], "npos": c["npos"]},
    )

for (f, ln), (kind, beh, note) in LANES.items():
    if ln:
        add(f, ln, kind, beh, note)
add(
    "MTG_bot/core/ability_tree.py",
    1208,
    "SCHEMA",
    "VALIDATION",
    LANES[("MTG_bot/core/ability_tree.py", 0)][2],
)

# ---------- prod .zone/.zones attribute sites ----------
for a in (x for x in SCAN if x["test"] == "prod" if False):
    pass
scan_attrs = json.load(open("/tmp/opencode/r0_scan.json"))["attrs"]
LANE_KIND_DEFAULT = {
    "MTG_bot/core/executor/selectors.py": "READ-PRIMARY",
}
special = {(f, ln) for (f, ln) in LANES if ln} | {(f, ln) for (f, ln) in DECISIONS}
for a in scan_attrs:
    if a["test"] != "prod":
        continue
    key = (a["file"], a["line"])
    if key in special:
        kind, beh, note = LANES.get(key) or DECISIONS[key]
        note = (
            note if key in DECISIONS else LANES[key][2]
        ) + f" [recv={a['recv']}] {a['snippet'][:80]}"
        add(a["file"], a["line"], *DECISIONS[key], note) if key in DECISIONS else None
        continue
    if a["file"].endswith("ability_tree.py") and a["enclosing"].startswith("FAtom"):
        add(
            a["file"],
            a["line"],
            "NOT-SELECTOR",
            "OUT-OF-SCOPE",
            f"DECOY FIELD FAtom.zone (a different Zone field; R0 must NOT touch) :: {a['snippet'][:60]}",
        )
    elif (
        a["called"]
        or "players[" in a["recv"].replace(" ", "")
        or "players[" in a["snippet"].replace(" ", "")
        or a["recv"].startswith(
            ("world.", "player", "p", "after", "before", "self", "pl")
        )
    ):
        add(
            a["file"],
            a["line"],
            "NOT-SELECTOR",
            "OUT-OF-SCOPE",
            f"runtime world side ({a['attr']}) recv={a['recv']} :: {a['snippet'][:70]}",
        )
    elif a["file"].endswith("quantity.py"):
        add(
            a["file"],
            a["line"],
            "NOT-SELECTOR",
            "OUT-OF-SCOPE",
            f"DECOY FIELD FAtom.zone read ({a['enclosing']}) :: {a['snippet'][:60]}",
        )
    elif a["file"].endswith("templates_b5b.py"):
        add(
            a["file"],
            a["line"],
            "READ-PRIMARY-HELPER",
            "PASS-THROUGH-MUST-EDIT",
            f"compiler sibling builders read `.zone` off a helper-built Selector and re-slot it :: {a['snippet'][:70]}",
        )
    elif a["file"].startswith("tools/audit/ontology_shape_census"):
        add(
            a["file"],
            a["line"],
            "READ-BOTH",
            "AUDIT-ORDER-SIGNATURE",
            "census menu signature `zone:{kind}+z{n}` -> signature strings change => the TRACKED "
            f"V5-prime baseline JSON drifts; re-baseline required :: {a['snippet'][:60]}",
        )
    else:
        add(
            a["file"],
            a["line"],
            "CHECK",
            "UNCLASSIFIED",
            f"recv={a['recv']} {a['snippet'][:80]}",
        )

# ---------- serialization / identity sites (manual) ----------
SER = [
    (
        "MTG_bot/core/ability_tree.py",
        4075,
        "SERIALIZE",
        "VALIDATION",
        "_SPECS['Selector'] field table drops ('zone','zone'), keeps ('zones','tup:zone') — from_dict "
        "raises on any stale 'zone' key (loud decode failure on pre-fold goldens).",
    ),
    (
        "MTG_bot/core/ability_tree.py",
        4458,
        "SERIALIZE",
        "BYTE-DELTA",
        "_OMIT_IF_EMPTY['Selector'] = {zones, referent}: the zones-omission rule MUST be dropped (post-fold "
        "zones is load-bearing). Leaving it would serialize a no-zone selector as absent => silent data loss.",
    ),
    (
        "MTG_bot/core/ability_tree.py",
        4661,
        "SERIALIZE",
        "PASS-THROUGH",
        "to_dict generic dataclass field loop: emits one key per field — byte delta is a consequence of the "
        "field set change, no code edit.",
    ),
    (
        "MTG_bot/core/ability_tree.py",
        4714,
        "SERIALIZE",
        "PASS-THROUGH",
        "from_dict spec-driven decode (`missing fields` raise catches the old key; `tup:` default () would "
        "silently create a ZERO-zone selector unless __post_init__ requires >=1).",
    ),
    (
        "MTG_bot/core/ability_tree.py",
        1275,
        "SERIALIZE-ORDER",
        "PASS-THROUGH",
        "_set_sorted (SET-R1a canonical_json sort) — the precedent/helper the new zones normalization reuses.",
    ),
    (
        "MTG_bot/core/executor/stack.py",
        480,
        "READ-IDENTITY-REPR",
        "PASS-THROUGH-REPR",
        "slot_designations = {repr(slot.selector): (one,)} — repr(Selector) is the designation KEY; the fold "
        "changes the repr string but producer+consumer are the same live objects (no persisted repr key found).",
    ),
    (
        "MTG_bot/core/executor/selectors.py",
        784,
        "READ-IDENTITY-REPR",
        "PASS-THROUGH-REPR",
        "atom_target_slot_key: `repr(value) in slot_designations` (consumer side of the same key).",
    ),
    (
        "MTG_bot/core/executor/selectors.py",
        786,
        "READ-IDENTITY-REPR",
        "PASS-THROUGH-REPR",
        "atom_target_slot_key returns repr(value) as the shadow key.",
    ),
    (
        "MTG_bot/core/executor/query.py",
        1096,
        "READ-IDENTITY-REPR",
        "PASS-THROUGH-REPR",
        "spell_target_slots dedups TARGET selectors by repr key (slot identity/dedup).",
    ),
    (
        "MTG_bot/core/executor/query.py",
        1197,
        "READ-IDENTITY-REPR",
        "PASS-THROUGH-REPR",
        "activation_target_slots dedups by the same repr key.",
    ),
    (
        "MTG_bot/core/executor/binding.py",
        1358,
        "READ-IDENTITY-REPR",
        "PASS-THROUGH-REPR",
        "_designate collects designation slots keyed by repr(selector) (multi-slot raise + binding key).",
    ),
    (
        "MTG_bot/core/executor/query.py",
        1036,
        "CONSTRUCT-REPLACE",
        "PASS-THROUGH",
        "replace(selector, filter=stripped) — dataclasses.replace copies zones; fold-safe.",
    ),
    (
        "MTG_bot/core/executor/binding.py",
        759,
        "CONSTRUCT-KWARG",
        "PASS-THROUGH-MUST-EDIT",
        "engine-synthesized triggerBinder._keyword_node Selector(zone=BATTLEFIELD/ANY) (spec's binding.py:759).",
    ),
    (
        "MTG_bot/core/executor/legality.py",
        1303,
        "CONSTRUCT-POSITIONAL",
        "PASS-THROUGH-MUST-EDIT",
        "_binding_atom payment placeholder with the NEUTRAL Zone(ANY,ANY) — post-fold this equals the C2 "
        "neutral shape; keep zones=(Zone(ANY,ANY),) so _is_any_universal keeps widening.",
    ),
    (
        "tools/audit/atom_field_table.py",
        72,
        "SCHEMA-REGISTRY",
        "VALIDATION",
        "CLASSIFY row ('Selector','zones') -> 'SET-R0'; the V1-prime 25-field table + checker dict are "
        "single-source: deleting Selector.zone makes it 24 and the module's drift check must be re-baselined.",
    ),
    (
        "tools/audit/atom_field_table.py",
        75,
        "SCHEMA-REGISTRY",
        "VALIDATION",
        "comment + NOTE 'R0 will delete it' — the detection-rule registry must drop the scalar row.",
    ),
]
for f, ln, k, b, n in SER:
    add(f, ln, k, b, n)

# order-risk / enumeration-order register (no code read of the field, but order semantics)
ORDER = [
    (
        "MTG_bot/core/executor/selectors.py",
        559,
        "ORDER-CONSUMER",
        "ORDER-RISK",
        "mode ALL returns `candidates` RAW in zone-enumeration order (primary zone entries, then each extra). "
        "The canonical_json sort puts GRAVEYARD before LIBRARY, so a multi-zone ALL selector's output order "
        "FLIPS. Corpus population TODAY: 0 (no ALL-mode selector carries zones) => register as latent.",
    ),
    (
        "MTG_bot/core/executor/verbs.py",
        265,
        "ORDER-CONSUMER",
        "ORDER-RISK",
        "_v_move_zone `pool[:n]` slices resolve order for non-partition finite moves (deterministic first-n).",
    ),
    (
        "MTG_bot/core/executor/selectors.py",
        556,
        "ORDER-CONSUMER",
        "PASS-THROUGH",
        "CHOOSE mode sorts candidates -> zone-iteration order irrelevant.",
    ),
    (
        "MTG_bot/core/executor/legality.py",
        511,
        "ORDER-CONSUMER",
        "PASS-THROUGH",
        "enumerate_candidates sorts -> TARGET ask vocab (and its site_digest) unaffected by zone order.",
    ),
    (
        "MTG_bot/core/executor/binding.py",
        1430,
        "ORDER-CONSUMER",
        "PASS-THROUGH",
        "designation asks `sorted(slot.candidates)` -> decision-handle site_digest stays stable.",
    ),
]
for f, ln, k, b, n in ORDER:
    add(f, ln, k, b, n)


# ---------- tests ----------
def final_kind(a):
    k = a["recv_kind"]
    if k in ("SELECTOR", "FATOM"):
        return k
    r = a["recv"].replace(" ", "")
    if "selector" in r.lower() or "_pairs(" in r or "library()" in r:
        return "SELECTOR"
    return "SELECTOR" if k in ("SELECTOR?", "UNKNOWN", "ZONE") else k


test_sites = []
for a in TESTS:
    k = final_kind(a)
    test_sites.append(
        {
            "file": a["file"],
            "line": a["line"],
            "attr": a["attr"],
            "kind": "TEST-ASSERT" if k == "SELECTOR" else "TEST-ASSERT-FATOM-DECOY",
            "behavior_class": "PASS-THROUGH-RE-PIN"
            if k == "SELECTOR"
            else "OUT-OF-SCOPE",
            "recv": a["recv"],
            "snippet": a["snippet"][:90],
        }
    )
# world-side (called) test sites, aggregated
world_by_file = Counter(
    a["file"]
    for a in scan_attrs
    if a["test"] == "test" and (a["called"] or "players[" in a["recv"].replace(" ", ""))
)

# comment/string Selector( mentions (non-AST) for completeness accounting
out_by_file = Counter()
sites_by_kind = Counter((s["kind"], s["behavior_class"]) for s in sites)

prod_cons = [
    s
    for s in sites
    if s["kind"].startswith("CONSTRUCT-POSITIONAL") or s["kind"] == "CONSTRUCT-KWARG"
]
seen = set()
deduped = []
for s in sites:
    k = (
        s["file"],
        s["line"],
        s["kind"],
        s["behavior_class"],
        s["attr"] if "attr" in s else "",
    )
    if k in seen:
        continue
    seen.add(k)
    deduped.append(s)
sites = deduped
inv = {
    "round": "R0 zone+zones -> zones: tuple[Zone,...] fold",
    "spec": "docs/DESIGN_ATOM_ONTOLOGY.md §3 SET-R0 + §8 R0; KNOWLEDGE /126 A1",
    "method": "AST scan of MTG_bot/core + tools (ability_tree/compiler/executor/tests/tools), "
    "value census by recompiling M21+ZNR with coverage._compile_pool_tolerant",
    "sites": sites,
    "counts_by_kind": {f"{k} | {b}": v for (k, b), v in sorted(sites_by_kind.items())},
    "counts_totals": {
        "prod_selector_construct_sites": sum(
            1
            for s in sites
            if s["kind"].startswith("CONSTRUCT") and s["file"].startswith("MTG_bot")
        ),
        "prod_construct_positional": sum(
            1 for s in sites if s["kind"] == "CONSTRUCT-POSITIONAL"
        ),
        "prod_construct_kwarg": sum(1 for s in sites if s["kind"] == "CONSTRUCT-KWARG"),
        "prod_construct_twin_zones_kwarg": sum(1 for s in sites if "TWIN" in s["note"]),
        "test_selector_construct_sites": 309,
        "test_construct_positional": 293,
        "selector_typed_test_assert_sites": sum(
            1 for t in test_sites if t["kind"] == "TEST-ASSERT"
        ),
        "selector_typed_test_assert_lines": len(
            {(t["file"], t["line"]) for t in test_sites if t["kind"] == "TEST-ASSERT"}
        ),
        "fatom_decoy_test_sites": sum(
            1 for t in test_sites if t["kind"] == "TEST-ASSERT-FATOM-DECOY"
        ),
        "world_side_test_zone_call_sites": sum(world_by_file.values()),
        "comment_or_docstring_Selector_mentions": 23,
    },
    "keyed_lane_candidates": [
        {
            "id": "L1",
            "file": "MTG_bot/core/executor/selectors.py",
            "lines": "451-457 + body 473-474",
            "spec_lines": "428-430 + body 445",
            "keys_on": "ONE_OF/REST mode AND primary zone.kind LIBRARY AND primary zone.position TOP; body "
            "then reads sel.zone.controller",
            "rewrite": "mw = [z for z in sel.zones if z.kind is LIBRARY and z.position is TOP]; if mode in "
            "(ONE_OF,REST) and mw: players_for_ref(mw[0].controller, ctx)",
            "corpus_population": 15,
            "falsifier": "r19b window (See the Truth / Garruk's Harbinger / Waker of Waves / Transmogrify / "
            "ZNR REST-lane cards)",
        },
        {
            "id": "L2",
            "file": "MTG_bot/core/executor/selectors.py",
            "lines": "614-618",
            "spec_lines": "484",
            "keys_on": "sel.zone.kind is PLAYER (designation re-point face)",
            "rewrite": "any(z.kind is PLAYER for z in sel.zones) — BUT see L3: pairing with the "
            "singleton test decides whether PLAYER∪BATTLEFIELD re-points",
            "corpus_population": 10,
            "falsifier": "Brash Taunter echo re-point",
        },
        {
            "id": "L3",
            "file": "MTG_bot/core/executor/selectors.py",
            "lines": "833-837 (reads 835-836)",
            "spec_lines": "705",
            "keys_on": "value.zone.kind is PLAYER and not value.zones (pure player selector)",
            "rewrite": "len(value.zones) == 1 and value.zones[0].kind is PLAYER  (SINGLETON, not ∃: "
            "∃-PLAYER re-opens the r21a Magmutt/Leafkin damage re-point bug)",
            "corpus_population": 8,
            "twin_risk_cards": ["Chandra's Magmutt", "Leafkin Avenger"],
            "falsifier": "Magmutt/Leafkin printed-damage-target pack",
        },
        {
            "id": "L4",
            "file": "MTG_bot/core/executor/selectors.py",
            "lines": "877-886 (reads 884-885)",
            "spec_lines": "754-755",
            "keys_on": "zone.kind GRAVEYARD AND zone.controller TARGET_PLAYER "
            "(Tormod's Crypt sweep pin)",
            "rewrite": "gs = [z for z in value.zones if z.kind is GRAVEYARD and z.controller is TARGET_PLAYER]; "
            "if gs: ...  (one zone satisfying BOTH clauses)",
            "corpus_population": 1,
            "falsifier": "Tormod's Crypt full-graveyard sweep (r21b)",
        },
        {
            "id": "L5",
            "file": "MTG_bot/core/executor/verbs.py",
            "lines": "246-250 (read 248)",
            "spec_lines": "247-249",
            "keys_on": "dest HAND AND sel.zone.kind LIBRARY AND non-partition AND "
            "referent None AND universal filter -> blind top-n DRAW",
            "rewrite": "len(sel.zones) == 1 and sel.zones[0].kind is LIBRARY (or all(z.kind is LIBRARY ...)); "
            "∃-LIBRARY would let HAND∪LIBRARY take the draw lane",
            "corpus_population": 0,
            "falsifier": "firemaw over-draw probe (wave-1b) — lane is a GUARD, no corpus card hits it today",
        },
        {
            "id": "L6-NEW",
            "file": "MTG_bot/core/executor/legality.py",
            "lines": "947-951 (read 950)",
            "spec_lines": "NOT IN THE SPEC (gate A1 enumerated only the four)",
            "keys_on": "CostDiscard.target.zone.kind is HAND AND IS_SOURCE filter -> the 'Discard this card:' "
            "activation window gate (ability_playable)",
            "rewrite": "any(z.kind is HAND for z in part.target.zones)",
            "corpus_population": 1,
            "falsifier": "Waker of Waves s4 activation-from-hand legality",
        },
    ],
    "corpus_twin_selectors": CORP["twin_selectors"],
    "neutral_count": CORP["totals"]["neutral_c2_class"],
    "corpus": {
        "selectors_total": CORP["totals"]["selectors_total"],
        "selectors_zones_nonempty": CORP["totals"]["selectors_zones_nonempty"],
        "twin_cards": CORP["totals"]["twin_cards"],
        "neutral_any_zone_empty_zones": CORP["totals"]["neutral_c2_class"],
        "any_kind_with_zones": 0,
        "cards_with_selectors": {"M21": 219, "ZNR": 108, "total": 327},
        "golden_files_M21": 305,
        "goldens_byte_delta_expected": 219,
        "byte_delta_note": "zone is a NON-omitted serialized key and zones is omitted when empty; deleting "
        "the scalar and always emitting zones changes EVERY Selector dict, so all 219 "
        "M21 goldens of cards carrying a Selector re-bake (the 86 selector-free goldens "
        "stay byte-identical), and every stale golden FAILS from_dict loudly on the "
        "unknown 'zone' key.",
    },
    "test_assert_sites": test_sites,
    "test_world_side_calls_by_file": dict(world_by_file),
    "unclassified_sites": [s for s in sites if s["behavior_class"] == "UNCLASSIFIED"],
    "out_of_scope_justification": {
        "runtime_world_side": "PlayerState.zone(kind)/.zones dict (state.py, games.py, events.py, stack.py, "
        "verbs.py, legality.py, selectors.enumerate_zone, run_scenarios.py, ab_duel.py, "
        "packrec*.py) — the RUNTIME world container, a different type from the IR Zone/Selector.",
        "FAtom_zone_decoy": "FAtom carries its OWN `zone: Zone | None` field (ability_tree.py:1476-1478, "
        "quantity.py:1178/1180/1326-1369 ZONE_COUNT_GE / ENTERED_THIS_TURN_FROM / "
        "CAST_THIS_TURN_FROM, + 9 test asserts). R0 must NOT touch it; a global "
        ".zone->.zones rename sweep would break it. LOUD warning for the implementer.",
        "comment_mentions": "23 textual `Selector(` hits sit in module docstrings/comments (listed by file:line "
        "in the completeness ledger) — no code.",
        "attic": "attic/mtg_rule_engine.py card.zone: a legacy engine with a different Zone enum; dead code.",
    },
}
json.dump(inv, open("/tmp/opencode/r0_consumer_inventory.json", "w"), indent=1)
print("sites:", len(sites))
for k, v in sorted(sites_by_kind.items()):
    print(f"  {v:4d} {k[0]} | {k[1]}")
print("UNCLASSIFIED:", len(inv["unclassified_sites"]))
for s in inv["unclassified_sites"]:
    print("   ", s["file"], s["line"], s["note"][:90])
