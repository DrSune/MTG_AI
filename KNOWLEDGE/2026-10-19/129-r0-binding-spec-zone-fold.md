# 129 — R0 BINDING SPEC: Selector zone∪zones schema fold (ONE set field)

Date: 2026-10-19. Round of the binding ontology (docs/DESIGN_ATOM_ONTOLOGY.md §3
SET-R0, §8 R0). Evidence, commit-resident: inventory `reports/r0_consumer_inventory
.json` + `reports/R0_CONSUMER_REPORT.md` (scanners `tools/audit/r0/`), byte-delta
`reports/r0_sortdelta.json` + summary (script `tools/audit/r0/mk_sortdelta_r0.py`).
Gate protocol: this spec → adversarial SPEC gate → implement (no commit by implementer)
→ diff gate → orchestrator one-commit landing (golden-wave law /127).

## 1. DECISION (schema)
`Selector.zone: Zone` and `Selector.zones: tuple[Zone, …]` collapse to ONE field
`Selector.zones: tuple[Zone, …]` (heterogeneous Zone objects kept WHOLE: kind +
controller + position all carry meaning; the set is of Zone SPECS, not kinds).
Construction invariants (new `__post_init__`): zones non-empty; dedup by
canonical_json; SORT by canonical_json (Zone is not orderable — bare sorted()
TypeError trap, pinned); C2 referent convention rewritten: referent selectors ⇒
`zones == (Zone(ANY, ANY),)` exactly (was zone=neutral + zones=()).
`to_dict`/`from_dict`: single key `zones`; stale goldens carrying `zone` FAIL LOUD at
from_dict (measured behavior, kept) — no silent migration anywhere.
Semantics: every consumer treats the field as the legal-zone SET. Pre-fold effective
set was {zone} ∪ zones (additive docstring rule) — the fold preserves it exactly
(content-preservation measured PASS: 0 selectors added/lost a zone across 549).

## 2. Migration surface (MEASURED, supersedes the v-spec's "~64" estimate)
- Constructions: **263 prod** (239 POSITIONAL slot-4 — must be reordered/keyworded
  together with the __post_init__ change in ONE pass; positional args are the silent
  mis-slot risk) + **309 test** constructions.
- **KEYED-LOSS site (must-fix)**: compiler.py:1050 positionally rebuilds Selector and
  SILENTLY DROPS zones today (measured twin-loss vector; corpus twins are safe pre-fold
  only because the meta-filter lane doesn't carry them). Fix: full-set rebuild +
  regression test pinning zones-survival through meta-filter fold.
- **KEYED lanes (6, each gets a ∃/singleton rewrite + executor-observed falsifier)**:
  L1 selectors.py r19b ONE_OF/REST TOP-window (now incl. :445 matched-zone CONTROLLER
  extraction — extract the matched LIBRARY+TOP Zone, never reuse sel.zone);
  L2 selectors.py:484 PLAYER-side CARD→controller re-point;
  L3/L5 **SINGLETON-predicates, NOT ∃** — ∃-form resurrects the r21a Magmutt/Leafkin
  bug (folded len-2 zones prove ∃ re-opens it);
  L4 Necromentia clause-shape;
  **L6 NEW (this inventory, A1-class)**: legality.py:947-951 CostDiscard.target
  zone.kind is HAND activation gate — population **10** (Waker of Waves, Thrill of
  Possibility, Demonic Embrace, Ghostly Pilferer, Seasoned Hallowblade, Sanctum of
  Shattered Heights, Niambi, Subira, Sparkhunter Manticore, Tormenting Voice/ZNR).
  Rewrite: singleton-HAND predicate on the set.
- Tests: 163 selector-typed `.zone/.zones` asserts across 16 files re-pin (identity-
  keyed, strictly-stronger precedent of R1a re-pins; NO relaxation).

## 3. Pre-registered predictions (MEASURED 2026-10-19; deviation = FINDING)
- Record bytes: **M21 219/305 + ZNR 108/281** change (exact names in
  r0_sortdelta.json — changed set == cards-with-selectors: universal `zone`-key
  removal; causes zone_key_removed 219, twin_fold 10, neutral_zone_drop 31,
  zone_position_change 9). ZNR expectation was NOT 0 (earlier hypothesis REFUTED by
  measurement — 108).
- **219 goldens re-baseline** (the golden store is M21-only, 305 files; the 108 ZNR
  changed records have no golden store — guards green immediately before commit per
  golden-wave law; 219 + 183 M21-unchanged == 305).
- PC-1/PC-2/PC-8/PC-6 (measure_grammar instrument; PRE anchors M21 4/.1265 MOVE_ZONE,
  ZNR 26/.1547 MODIFY_PT) **Δ0** — normalization is value-preserving for all lanes
  IF the 6 KEYED rewrites are behavior-identical (the falsifier battery is what
  proves the "if").
- PC-5 p99: sort cost per construction trivial (R1a measured .369ms with more sorting
  than R0 adds) — expect <0.45ms, report actual.
- packs 428/428 (or current sibling truth at run time — sibling eval lane is LIVE,
  packs are moving; take the pre-wave count same-invocation), fuzz 40/40 clean,
  corpus re-encode drift 0.

## 4. Falsifier battery (EXECUTOR-OBSERVED, from r0_sortdelta twin-lane map)
Named per lane, must FAIL on a deliberately naive-∃ variant (red-first discipline):
L1: Warsteed/Liliana's Scorn/Sanctum of All/Wavecaster/Basri's Aegis/Firemaw
(ONE_OF/REST top-partition offered iff primary TOP present; naive-∃ false-offer =
the r21a-class hover-the-pile bug — red-first test proves ∃ FAILS); +L5 draw-guard on
Firemaw + Wavecaster into-hand lanes; L2/L3: Magmutt + Leafkin counter-styles with
len-2 folded zones (singleton test holds; ∃ rewrite red-first shows it would re-point
wrongly); L4: Necromentia exile-from-graveyard/hand/library clause; L6: Waker of Waves
discard-cost activation window (non-during-your-raise cases); Unsubstantiate =
content-only control (no lane, bytes only).

## 5. Sequencing within R0 (single landable wave)
(1) `ability_tree.py`: new field + invariants + to_dict/from_dict (breaks ALL 239
positional constructions — same commit); (2) EVERY construction migrated mechanically
(single-zone → zones=(Z,); multi → set; compiler.py:1050 fix with regression pin);
(3) 6 KEYED rewrites + L6; (4) tests re-pin (identity-keyed); (5) goldens re-bake
(219) + guards; (6) checker V1′ table update: ('Selector','zones') remains SET (now
sole), row for ('Selector','zone') DELETED — atom_field_table.py CLASSIFY single
source updated (stale-entry check makes forgetting this fail); (7) falsifier battery
green + naive-∃ red-first artifacts kept as tests; (8) census re-run: zone twins 0 by
construction, map drift Δ0 vs R1a post-full; (9) NUMBERS.md row.
RISK CALL: largest migration so far (~600 sites incl. tests); mitigation = mechanical
pass + the FULL battery is the exit; sibling lanes disjoint (eval packs + model lane);
executor clean since 1c3dac6 (verified pre-dispatch).

## 6. Out of scope (stays queued)
R1b (Cost.parts + additional_costs + hybrid colors sort after planner-determinization),
R2 (F4 damage fold, F1 residuals), R3 (CHOOSE blindness audit — emission freeze stays
armed: V4′ baseline now committed, new-CHOOSE fails the gate).
