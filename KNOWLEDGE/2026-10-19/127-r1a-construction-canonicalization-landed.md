# 127 — R1a landed: construction-time canonicalization (ontology rollout round 1a)

Date: 2026-10-19. Builds on the binding ontology (docs/DESIGN_ATOM_ONTOLOGY.md, /126).
Round protocol: implement (ultra wave) → adversarial diff gate (FIX-THEN-GO) → blocker
fixes → orchestrator commit.

## What landed
- `ability_tree.py` construction normalization (§3 SET-R1a): FAnd/FOr children sorted by
  canonical_json + same-class flatten; CardRecord.keywords, TokenSpec.{types,subtypes,
  keywords}, FAtom.colors, EtBState.initial_counters sorted at construction. Single-child
  FAnd/FOr KEPT by the node (value semantics pinned by law test) — the 2 corpus wrappers
  (Negate `FAnd{FNot}`, Dauntless Survivor `FAnd{FAtom}`) unwrapped at their compiler
  EMISSION sites (templates_b5a/b9).
- Checker `tools/audit/ontology_conformance.py` (V1′ 25/25, V2′ 0/0/0 phantoms with EMPTY
  whitelist, V3′ 4 WARN = D8 class, V4′ CHOOSE-freeze **fail-closed** on missing baseline
  — r2 found it failed open, gate blocker B2 fixed + self-tested). Baseline + whitelist
  commit-tracked.
- 122 M21 goldens re-baked (name set == reports/atom_sortdelta_2026-10-19.json EXACTLY,
  sym-diff 0; leaf-multiset audit 0 failures; guards green). 183 untouched goldens
  byte-match.
- 10 re-pinned test files: positional unpacks → identity-keyed lookups + collision guards
  + sort-law asserts — strictly STRONGER, 0 deletions (gate re-pin audit 10/10).
- NEW tests: test_ontology_r1a.py (24: law tests + B3 EXECUTION pins for Negate [RUNG-1
  counter lane, offer-window negative: creature spell ⇒ Negate never offered] + Dauntless
  Survivor [ETB ask vocab exactly the two creatures, counter lands]) +
  tools/audit/test_ontology_conformance.py (16, incl. fail-closed + synthetic V3′ TPs).
- DIVERGENCES rows D8 (V3′-WARN canonization: Garruk Unleashed, Ranger's Guile, Sure
  Strike, Archpriest of Iona — same-function Selectors fused BY DESIGN) + D9 (empty-FAnd
  universal-truth asymmetry: TRUE quantity.py:658/binding.py:220, FALSE
  replacements.py:338 — registered confound, pre-existing).

## Pre-registered predictions (all HIT)
M21 golden-changed set 122 (exact names) | ZNR 80 exact | PC-1/2/8 Δ0 | PC-6 gate metric
4/.1265 Δ0 | PC-4 post-rebake verify 0/305 | PC-5 p99 0.369ms (<50, construction sort
cost negligible) | corpus drift 0 (11 files/11032 eps byte-identical) | suite
2829+36st + tools 271, 0 fail | packs 428/428 (sibling +13 packs mid-window — truthful
baseline shift) | census emission delta = exactly the 2 unwraps (struct 2/2, branchings
1/2), FAnd 434→434, FOr 48→48, near-dup pairs 2→0, order-variant groups 2→0.

## FINDINGS
1. **Cross-wave golden restore** (coordination, third VCS incident class): my UNCOMMITTED
   122-golden re-bake was reverted mid-flight by sibling ops commit cebdab6's "worktree
   goldens restored" sweep (they were right on their law: stale-code goldens poison PC-4
   self-heal; my wave was legitimate but indistinguishable). LAW (appended PITFALLS):
   golden re-bakes are TRANSIENT on a shared tree — code+goldens must land in ONE commit
   (this commit), guards re-run immediately before the commit, and re-bake waves announce
   via KNOWLEDGE scaffolding earliest.
2. Dauntless Survivor printed text is "put a +1/+1 counter on target creature" (no
   sacrifice cost — the gate's blocker description assumed otherwise); execution pin
   follows TRUE text. Truth-over-instruction law worked as designed.
3. Census truncation (`most_common(40)`) hid tail branchings → `--out/--cap` flags added;
   full uncapped pre/post censuses committed (`reports/ontology_census_..._r1a_{pre,post}
   _full.json`); regression test is truncation-proof.
4. Clobber-class tool audit re-enacted the day's PITFALL (eval --out clobbers tracked
   ledgers): atom_sortdelta/shape_census got TRUTH annotations; measure_grammar
   --refresh-goldens NOT used (touches all 305 — rejected on blast radius, 122-file
   targeted script used).

## Gate verdict
Diff gate (ontology adversarial session): logic CLEAN — 0 semantic defects across all
executed probes (golden triple-confirmation, re-pin strictness, evaluator equivalence
all([])≡x verified, latency, determinism, sibling-leak zero). FIX-THEN-GO on 3 mechanics
(B1 re-bake lost-to-restore, B2 fail-open V4′, B3 zero execution coverage) — ALL fixed
and independently re-verified by orchestrator (18 golden guards + 40 ontology tests +
checker rc=0) before this commit.

## Next (per §8)
R0 zone-set schema fold (siblings now CLOSED — selectors.py lane free? verify liveness
before dispatch) → R1b cost/planner determinization → R2 F4 damage fold + F1 residual.
R0 pre-work: full consumer inventory is in spec §8 (positional Selector@compiler.py:1050,
lane-body :445 extraction, ~111 test asserts, offer-order pre-registration).
