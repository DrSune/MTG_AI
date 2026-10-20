# 145 — R3b BINDING SPEC: phantom-fold (engine-resolved CHOOSE → mode=ALL no-decision)

Date: 2026-10-20. Round scheduled by /141 §6 (D12 phantom debt). Evidence commit-resident
(same commit): `reports/r3b_r4_evidence.md` + `reports/r3b_sortdelta.json`
(`tools/audit/atom_sortdelta_r3b.py`, repo-rerun reproduces) + `reports/r4_twins_census.json`
(`tools/audit/r4_twins_census.py`). Double-gate protocol; one-commit landing (golden-wave law).

## 1. HEADLINE (Type-1) — §9 merge with EXISTING vocabulary, one wave
The no-decision replacement shape already exists: `mode=ALL` (ALL+IS_SOURCE compiles
today: 14 nodes; ALL+QConst(1)+IS_SOURCE / ALL+PLAYER:YOU constructor-probed legal).
Self-reference is coded 3× today (CHOOSE 108 / TARGET 5 / ALL 14) — folding the CHOOSE
leg into ALL is a merge, not a new atom. Measured wave: **112 nodes (self 107 + top 3 +
seat 2) → 93 changed records (M21 61/305, ZNR 32/281), 61 M21 goldens, CHOOSE census
193→81**, `.mode`-bytes-only, idempotent, content-preserving. < ~100 records → one wave.

## 2. SCOPE
(1) Compiler emission: L-A self/library-top/seat-singleton CHOOSE nodes → SelectorMode.
    ALL with the same menu/count/filter hosts (menu resolves to a forced singleton;
    ALL-semantics = take-what-exists = the engine's outcome).
(2) Executor: carve-backs STAY as the implementation of ALL over self-menus; the ONE
    code adaptation: `role_handles` CHOOSE∧IS_SOURCE exemption re-keyed to the
    mode-agnostic `_filter_is_self_referential` (preserves existing TARGET-5 + ALL-14
    consumers — corpus games determinism byte-identical is the proof surface).
(3) LEDGER-FINDER CORRECTION (committed reports/r3_blindness.json + r3_lane_ledger.py):
    **Dire Fleet Warmonger is a MIS-LANE** — its filter is FAnd[…, FNot(IS_SOURCE)]
    ("sacrifice ANOTHER" = genuine multi-candidate choice; the ledger flattener dropped
    FNot). Reclassify L-A→**L-C** (r22a sacrifice-cost lane already asks it). Structural
    self-reference predicate (FNot-aware) replaces naive matching in the generator;
    red-first tripwire test: folding Warmonger would sacrifice ALL other creatures —
    assert NOT folded + correct multi-candidate ask behavior.
(4) referent-bound 48 = **GAP REPORT, deferred R3c** (Type-1): ALL+referent raises
    (executed C2 probe); plural-register hazard makes behavior-equivalence unprovable
    here. D14 ledger row; Waker-emblem node stays CHOOSE/referent meanwhile.
(5) V4′ baseline v3 regen post-fold (shape-hash baseline: 193→81 CHOOSE population) +
    REMOVED/shape probes green; whitelist semantics untouched.
(6) Goldens: targeted re-bake EXACTLY the 61 predicted M21 names (r3b_sortdelta.json);
    ZNR 32 census-only (no golden store); leaf-multiset audit per card.
(7) R4 CLOSED-WITH-EVIDENCE (§4/§8 patch): twins share everything at IR post-R3 (Goremand
    same-card byte-twin; Shacklegeist family); residual divergence = SITE-TAG GRAMMAR
    only (cost tags' ignored {controller}; `choose:` lacks seat) → folded into **ZND-9**
    scope, thin volume per §9 bars an IR round.

## 3. Pre-registered predictions (MEASURED; deviation = FINDING)
- 93 changed records EXACT (61 M21 + 32 ZNR, JSON sets); 61 goldens; CHOOSE census
  193→81 both pools; ALL-mode census +112; `.mode`-only byte diffs (leaf-multiset 0).
- Behavior-preservation battery (red-first where applicable): per-class sample cards
  execute with SAME designation outcomes and NO new asks (self: dealer; top: Snoop idiom;
  seat: Runed Halo constant); Warmonger tripwire (2); packs 428/428 DOUBLE-RUN
  BYTE-IDENTICAL (folded nodes were engine-resolved ⇒ decision stream UNCHANGED — any
  pack ask drift = FOLD BROKE SOMETHING, stop); corpus games fingerprint double-run
  byte-identical (re-key (2) neutrality proof); PC pass-set Δ0 (PC-5 report); suite
  `MTG_bot/core tools` 0 fail; fuzz 40/40 0 sigs; determinism double-run; V4′ v3 probes
  (nested-swap/delete/extinction FAIL, honest PASS); atom_field_table rc 0.

## 4. Registrations at landing
D12 → FOLDED (this round) except referent class; D14 NEW: referent-bound phantom gap
(R3c Type-1, plural-register); ledger row: Warmonger re-class correction (meta-lesson
for PITFALLS: lane classifiers must be structural/FNot-aware, not flattened-text);
R4 → CLOSED with evidence; ZND-9 scope += site-tag grammar fusion (cost `{controller}`).

## 5. NOT in scope
R3c referent fold; Warmonger ask-shape changes (already L-C); model-lane seat-routing of
provider vocab (T-G flag from /144); ZND-7/8; sibling lanes.

## 7. Spec gate (adversarial, 2026-10-20) — FIX-THEN-GO, amendments LAW
Gate re-derived ALL counts independently (self 107/top 3/seat 2/excluded-1 = 112; 81 =
48 referent + 27 L-B + 6 L-C post-Warmonger — arithmetic reconciled); generator rerun
byte-identical; Warmonger FNot(IS_SOURCE) confirmed on real IR (exactly 1 self-negated
node corpus-wide); consumer audit: legal_targets CHOOSE-vs-ALL delta == the `forced`
flag (the phantom switch itself); re-key flip vacuous today (zero role-collisions).
FIX-1: selectors.py:1007 comment PREMISE FALSE — 5 TARGET∧IS_SOURCE nodes exist
(Experimental Overload pos-pure; Niambi, Basri's Acolyte, Hobblefiend, Barrin neg-only);
re-key neutrality today is corpus luck, not design. Rewrite comment; conformance
TRIPWIRE: fail if any flip-node's card gains same-role TARGET designation; pin quintet.
FIX-2: FOr-classifier hazard — both sortdelta classifier AND r3_lane_ledger flattener
must RAISE on non-pure-conjunctive positive IS_SOURCE (FOr(IS_SOURCE,…) would silently
mis-fold); red-first synthetic test; ledger flattener polarity-aware.
FIX-3: name the proof producer — fingerprint hashes are tools/search/* world-state
trajectories (IR-invisible; byte-identical NOT self-contradictory); exact-count gate
query.py:~588 (TARGET/CHOOSE/RANDOM modes) drops folded ALL nodes ⇒ empty-library
Conspicuous Snoop/Furious Rise payability semantics change (rules-defensible): battery
gains EMPTY-LIBRARY edge scenario pinning the chosen semantics.
FIX-4: single fold predicate — landing compiler pass MUST reuse atom_sortdelta_r3b
classify verbatim (measured 112 == shipped 112; no ~13-module drift).
FIX-5: re-pin inventory += compiler/test_pick_ask_promotion.py:155 (counts CHOOSE repr
on folded Obsessive Stitcher); test_ontology_r3.py L-A-lane asserts → no-decision form;
r20c/r22a hand-built CHOOSE pins stay green UNCHANGED (carve-back evidence); ZNR has NO
golden store (generator gate M21-only — stated); stale docstring 'remainder 32' → 81.
No re-gate (no amendment changes the mechanism).
