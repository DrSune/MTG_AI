# 132 — R0 zone-fold LANDED (execution record of /129)

Date: 2026-10-19. Spec: `129-r0-binding-spec-zone-fold.md` (binding). Status: **landed,
uncommitted** (orchestrator lands; ~83 files touched by the wave, all uncommitted).

## What shipped (spec §5 order)
1. **Schema** (`ability_tree.py`): `zone` + `zones` → one `zones: tuple[Zone, ...]`;
   `__post_init__` = non-empty ∧ dedup ∧ `canonical_json`-sorted (Zone unorderable);
   C2 referent ⇒ exactly `(Zone(ANY,ANY),)`; `zones` always serializes (omit-if-empty row
   deleted); `from_dict` fails LOUD on stale `zone` bytes naming **"R0 zone-fold"**.
2. **Mechanical migration**: `/tmp/opencode/r0_migrate.py` (AST, rules A1/A2/B0–B3) —
   572 Selector constructions across the repo; final dry-run = 0 pending edits;
   `tools/audit/r0/r0_scan.py` ⇒ **0 positional-4 / 0 `zone=` of 572** (`/tmp/opencode/r0_scan_post.json`);
   grep-zero clauses held (`Selector(**`, `getattr(…,"zone")`). Residual `.zone` reads are
   legitimate FAtom/AtomArgs scalar-role decoys only.
3. **Six keyed lanes** (all executor-visible, each with a comment naming /129 §2):
   L1 `selectors.py` matched-zone EXTRACTION (controller from the MATCHED LIBRARY+TOP zone;
   ∃-LIBRARY refuted — r21a hover-the-pile class); L2 `query.py` ∃-PLAYER (kept: correct there);
   L3 `selectors.py` PURE = `len(zones)==1 ∧ PLAYER`; L4 one-zone BOTH-conjuncts via new
   production helper `graveyard_sweep_shape()`; L5 `verbs.py` SINGLETON-LIBRARY draw guard;
   L6 `legality.py` SINGLETON-HAND self-discard window. Plus `legality.py:509` enumeration merge,
   `_is_any_universal`, census sig, and the KEYED-LOSS fix `compiler.py:1050` (rebuild carries
   `zones=value.zones` AND `referent` — gate F6).
4. **Test re-pins**: 151 mechanical `.zones[0]`-identity re-pins (16 files, strictly stronger,
   no relaxation) + fingerprints re-baked (r3–r11, t3, t3r2, r3b `856e64→64d3fa`) + hand pins.
5. **Golden re-bake (Step 5)**: EXACTLY the 219 `/129` names; git shows exactly **219** golden
   files modified, 86 untouched byte-identical to a fresh compile; `verify_goldens` **0 diffs**;
   independent **zone-leaf multiset audit: 305/305 preserved** (fold is content-neutral).
6. **Falsifier battery** `MTG_bot/core/test_ontology_r0.py` (40 checks): every lane carries a
   PRODUCTION-predicate-vs-naive-∃ divergence pin on the REAL folded golden selectors, plus
   EXECUTOR-observed probes (ONE_OF graveyard answer for all 6 L1 twins; trio no-blind-draw;
   Magmutt walker designation stands; Unsub STACK+BATTLEFIELD ask enumeration; Waker window
   open/closed; F4 split-zone unit synthetic; C2/dedup/sort/fail-loud schema laws; :554 same-seed
   determinism; compiler-rebuild zones survival). 23 tests + 17 subtests green.

## Measured (all Δ0 vs the /129 §3 anchors unless noted)
core **2853 passed 0 failed** · tools **294 passed** · packs **428/428** · fuzz ZNR **40/40,
0 sigs** · conformance **errors=0 warns=7** · census **469 clusters = Δ0**, zone twins **B 2→0**
(new artifact `reports/ontology_census_2026-10-19_r0_post_full.json`; tracked baseline regenerated)
· scenarios double-run **byte-identical** · PC: M21 PC-4 0 diffs, PC-6 4/.1265, PC-8 .3213,
PC-5 **.359→.326 ms** (improved); ZNR PC-1 .3830/.5496, PC-6 26/.1547, PC-5 .308 ms, PC-9 stable.

## Deviations from /129 (findings, not shortcuts)
- **D1 (F1-foreseen)**: 6 twin-shaped test asserts (`zones[0]` = old PRIMARY) broke on canonical
  ORDER (schema re-sorts), NOT membership: Sanctum/Basri-tutor ×2/b2b named-search/deal-dmg ×2/
  return-spell/search-name-exile — re-pinned by hand to full-set pins whose order IS the canonical
  law (verified against template sources, not compiler output).
- **D2**: `test_v5_live_new_branchings_are_all_census_tail_rows` consults the frozen R1a census;
  fused multi-zone menus (`zones:BATTLEFIELD+STACK` etc.) exist only post-fold → test now merges
  the new uncapped R0 artifact (+1:1 `zone:`→`zones:` relabel of R1a rows). Checker itself unchanged.
- **D3**: `:554` ALL-order lane shows deterministic canonical-order drift exactly as the F1
  clause pre-registered; the required same-seed determinism pin ships in the battery.
- **D4**: fold_meta_filter referent-carry is LATENT on legal IR (C2 forbids TARGET+referent);
  pinned as such (zones-carry is live-pinned).

## Standing traps hit (→ PITFALLS candidates)
- Mechanical `.zone → .zones[0]` re-pins are SAFE only for single-zone selectors; twin-shaped
  sites must fail loud by design (they did) and get set-membership re-pins.
- `tools/audit/atomics_census.json` (conformance findings) ≠ `reports/ontology_census_*.json`
  (shape census): same-wave tooling must not cross-write them.
- Golden-dependent tests fail LOUD pre-re-bake BY DESIGN — the correct fix is the scoped Step-5
  bake, never a test edit.
