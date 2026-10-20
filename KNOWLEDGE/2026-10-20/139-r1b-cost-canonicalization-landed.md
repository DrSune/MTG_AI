# 139 — R1b landed: cost-parts canonical construction-sort (planner neutrality by construction)

Date: 2026-10-20. Round of docs/DESIGN_ATOM_ONTOLOGY.md §8 (R1b), spec /136 (double-gated).

## What landed
- `Cost.__post_init__` sorts parts by canonical_json (the :2541 precedent family) +
  CostManaHybrid.colors + CostModifier.extra_deltas + SpellAbility.additional_costs —
  all four CLASSIFY rows → SET-ENFORCED in the single-source atom_field_table (rc 0).
  Payment planning is now a function of the parts MULTISET by construction:
  payability invariance was gate-PROVEN for the whole corpus first (pooled per-color
  cuts :703-706 + Σ-min-clamp; Orrery global pool; post-loop generic; hybrid
  population 0/0 source-censused).
- Red-first battery `test_ontology_r1b.py` (11): pre-change 7 RED (log retained);
  (i) uses CostLife+CostManaColor (documented deviation — the spec's Color+Generic
  pair is post-loop-order-free and could never go red); (ii) {W/B}+{W/U} pool-1/1
  probe pins the DETERMINISTIC witness (semantics deferred: D10); (iv) constructed
  two-sac ask-sequence tripwire guards the A2 standing assumption (at most one
  asked-kind part per Cost today — Goremand/Kazuul fold worst-case = 1 sac each).
- 226 M21 goldens re-baked (exact predicted set sym-diff 0, order-only vs HEAD across
  all 226 via multiset walk, 79 unchanged byte-match, leaf-multiset 0 failures,
  idempotency-identity corpus-wide); 13 diagnostic-string re-pins across 8 test files,
  identity-keyed, 0 relaxations (the r1a `untouched` law-test inverted to ENFORCE
  sortedness — strictly stronger).
- D10 (greedy-hybrid payable flip) + D11 (failing-string precedence diagnostic)
  rows in docs/ATOM_DIVERGENCES.md at landing.

## Pre-registered predictions — ALL HIT
M21 226 + ZNR 216 exact sets | 226 goldens | PC pass-set Δ0 (PC-5 p99 0.326→0.332 ms
= +1.8% construction-sort cost, passes both gates — the only PC movement) |
suite `core+tools` 3149 + 53st, 0 failed (orchestrator re-attested) | golden guards
20/20 pre-commit | packs 428/428 | fuzz 40/40 0 sigs | census Δ0 semantic.

## Coordination notes (third + fourth VCS-incident datapoints)
- Mid-implementation, an external `git checkout` reverted the implementer's first
  re-pin pass (sibling sweep, same family as R1a's golden restore) — re-done fresh;
  the one-commit law held and the wave landed inside one capture window.
- The 23 legacy full-scope reds re-confirmed as the BACKLOG B-19..B-21 set (name-level
  identical at HEAD-tree vs dirty; B-22 scope question still owner-open: core+tools is
  the operative contract).
- Sibling-owned files EXCLUDED from the wave commit: tools/audit/atomics_census.json
  (regenerated content, sibling lane), tools/test_self_improvement_loop.py (1-line
  zones alignment, suite-inert — gate classified as unrelated cleanup),
  reports/*engine_smoke*, tools/eval/*, gameplay ledgers.

## Ontology rollout status (spec §8)
R0 LANDED /132 · R1a LANDED /127 · R1b LANDED (this) · remaining: R2 (F4 damage-event
fold + F1 direction-residual re-audit), R3 (silent-CHOOSE blindness audit — 174-card
population; V4′ emission freeze stays armed meanwhile), R4+ (cost↔effect twins, gated
on the §9 similar-effects test). Engine-lane handoffs: D10 hybrid-payment matching
(fix = Kuhn-family, same law as /117 blocker completion), ZND-3d/e/f/g, ZND-4d,
ZND-5a..f.
