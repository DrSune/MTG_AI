# 08 — Wave-2 closeout (2026-10-01)

## Loop execution (all five steps, first full cycle on a fresh cohort)
1. **Derive**: 67-row spell cohort frozen in tools/audit/wave2.json (f50e335; wrong commit message, content correct — logged in /02).
2. **Author** (engine frozen): 42 green packs + 25 suspects with code-pinned root causes (0ff4d7f; findings /03 /04).
3. **Adjudicate/fix** (engine unfrozen, sequential batches):
   - 19a (39e01ba): 5 silent bugs killed — counter→PT fold, IS_PERMANENT type-line, died-branch, cultivate tapped delivery, walker cast seed. Tampering STOPPED (IR).
   - 19b (8b4b6b9): 9 killed — Slag binding-precedence, IS_ATTACHED_TO evaluator, controller/attachment semantics, cost-replacement, + 3-pass sweep. 3 STOPPED.
   - 19c (this commit): cast-lane machinery — positional multi-slot designation, IS_SOURCE auto-skip + lone-population auto-designation, CR 601.2b mode pre-declaration, take_decision fall-through, enchant-op fire_triggers. 8 FIXED incl. BOTH original carry-overs (capture_sphere promoted). 2 STOPPED. Docs /05 /06 /07.
4. **Gates**: packs 84→148 green; suite 2112→2168; PC-1 301/305 · PC-2 634/639 · PC-3 0 · PC-4 0 EXACT at every batch (zero IR movement); catalog repinned per batch, 6144 entries, 0/10 diverge; pyright clean; ruff Δ0.
5. **Owner artifact**: reports/replays/replay_s8.html — seed 8 (the 19c-attribution seed; multi-spell designations visible in the decision log).

## Compiler-campaign backlog (5 STOPs — golden/IR work, orchestrator-gated only)
- tampering_no_block: can't-block clause compiles to PtDelta INCREASE QConst(0) — zero payload; clause unrepresentable in frozen IR.
- secure_the_scene: CREATE_TOKEN has no controller-role; printed "its controller creates" needs the DESTROYED permanent's controller.
- transmogrify: root cause in /06.
- peer_into_the_abyss, wildwood_scourge: cast-lane IR gaps; root causes in /07.

## Convention settled (19c flag)
Directory is the promotion marker: tools/audit/suspects/*.json keep the status field;
promoted packs live in tools/scenarios/ with the field stripped (18b→19c convention).

## Next waves (loop identical, cohort via wave_builder)
- Wave 3: static/keyword cohort derivation. Wave 4: mana/activation cohort.
- Standing gaps unchanged (omniscient-v1 hidden-info, Kinetic Augur may-lost-at-IR, search-shuffle tail, PHASE_IN/HAS_COUNTER_GE, PC-8 compiler-side).
